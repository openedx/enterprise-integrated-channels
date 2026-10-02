"""Regression tests for mixed SAP-signed and self-signed SAP background workers."""

import json
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urljoin

import responses
from pytest import mark

from channel_integrations.integrated_channel.models import (
    IntegratedChannelAPIRequestLogs,
)
from channel_integrations.integrated_channel.tasks import transmit_content_metadata, transmit_learner_data
from channel_integrations.sap_success_factors.models import (
    SAPSuccessFactorsEnterpriseCustomerConfiguration,
    SAPSuccessFactorsGlobalConfiguration,
)
from test_utils import factories, generate_test_private_key_pem


def _create_tenants():
    SAPSuccessFactorsGlobalConfiguration.objects.create(
        completion_status_api_path='learning/completion',
        course_api_path='learning/course',
        oauth_api_path='legacy/token',
        oauth_token_api_path='saml/token',
    )
    worker = factories.UserFactory(username='sap-worker')
    tenants = []
    for name, host, token in (
        ('sap_signed', 'sap-signed.sap.example.test', 'sap-signed-bearer-token'),
        ('self_signed', 'self-signed.sap.example.test', 'self-signed-bearer-token'),
    ):
        customer = factories.EnterpriseCustomerFactory(name=f'{name} customer')
        config = factories.SAPSuccessFactorsEnterpriseCustomerConfigurationFactory(
            enterprise_customer=customer,
            sapsf_base_url=f'https://{host}/',
            sapsf_company_id=f'{name}-company',
            sapsf_user_id=f'{name}-service-user',
            decrypted_key=f'{name}-client-id',
            **(
                {'self_signed': True, 'decrypted_private_key': generate_test_private_key_pem()}
                if name == 'self_signed' else {'decrypted_secret': f'{name}-client-secret'}
            ),
        )
        tenants.append((name, config, token))
    return worker, tenants


def _register_mock_endpoints(tenants, downstream_path, response_for_tenant):
    for name, config, access_token in tenants:
        token_path = (
            'saml/token' if config.uses_self_signed_assertion else 'legacy/token'
        )
        responses.add(
            responses.POST,
            urljoin(config.sapsf_base_url, token_path),
            json={'access_token': access_token, 'expires_in': 1800},
            status=200,
        )
        responses.add(
            responses.POST,
            urljoin(config.sapsf_base_url, downstream_path),
            # The echoed credential only gets redacted if the response goes through store_api_call.
            json={**response_for_tenant(name), 'access_token': f'{name}-echoed-token'},
            status=200,
        )


def _request_to(url):
    matches = [call.request for call in responses.calls if call.request.url == url]
    assert matches, f'no request was sent to {url}'
    return matches[0]


def _assert_tenant_logs_are_redacted(tenants):
    for name, config, access_token in tenants:
        token_path = 'saml/token' if config.uses_self_signed_assertion else 'legacy/token'
        token_call = _request_to(urljoin(config.sapsf_base_url, token_path))
        # The signed assertion and the key that signed it are what must never reach the stored logs.
        secrets = [access_token, f'{name}-echoed-token']
        if config.decrypted_secret:
            secrets.append(config.decrypted_secret)
        if config.uses_self_signed_assertion:
            secrets += [parse_qs(token_call.body)['assertion'][0], config.decrypted_private_key]

        records = IntegratedChannelAPIRequestLogs.objects.filter(
            enterprise_customer_configuration_id=config.id
        )
        assert records.count() >= 2
        for record in records:
            record.refresh_from_db()
            logged_values = f'{record.payload} {record.response_body}'
            assert not any(secret in logged_values for secret in secrets)
        if config.uses_self_signed_assertion:
            assert '[REDACTED]' in records.get(endpoint=token_call.url).payload


@mark.django_db
@responses.activate
def test_content_metadata_worker_isolates_sap_signed_and_self_signed_tenants():
    worker, tenants = _create_tenants()
    payloads = {}
    transmissions = {}
    for name, config, _ in tenants:
        content_id = f'{name}-course'
        transmission = factories.ContentMetadataItemTransmissionFactory(
            enterprise_customer=config.enterprise_customer,
            integrated_channel_code=config.channel_code(),
            plugin_configuration_id=config.id,
            enterprise_customer_catalog_uuid=factories.EnterpriseCustomerCatalogFactory(
                enterprise_customer=config.enterprise_customer
            ).uuid,
            content_id=content_id,
            channel_metadata={'key': content_id, 'title': f'{name} course'},
        )
        transmissions[config.id] = transmission
        payloads[config.id] = ({content_id: transmission}, {}, {})

    _register_mock_endpoints(
        tenants,
        'learning/course',
        lambda name: {'ocnCourses': [{'courseID': f'{name}-course'}]},
    )

    def exporter_for(config, _user):
        return SimpleNamespace(export=lambda: payloads[config.id])

    with patch.object(
        SAPSuccessFactorsEnterpriseCustomerConfiguration,
        'get_content_metadata_exporter',
        autospec=True,
        side_effect=exporter_for,
    ):
        for _, config, _ in tenants:
            transmit_content_metadata(worker.username, config.channel_code(), config.pk)

    for name, config, token in tenants:
        transmission = transmissions[config.id]
        transmission.refresh_from_db()
        assert transmission.api_response_status_code == 200
        assert transmission.remote_created_at is not None

        api_call = _request_to(urljoin(config.sapsf_base_url, 'learning/course'))
        assert api_call.headers['Authorization'] == f'Bearer {token}'

    _assert_tenant_logs_are_redacted(tenants)


@mark.django_db
@responses.activate
def test_learner_data_worker_isolates_sap_signed_and_self_signed_tenants():
    worker, tenants = _create_tenants()
    exporters = {}
    audits = {}
    for name, config, _ in tenants:
        ecu = factories.EnterpriseCustomerUserFactory(
            enterprise_customer=config.enterprise_customer,
            user_id=worker.id,
        )
        enrollment = factories.EnterpriseCourseEnrollmentFactory(
            enterprise_customer_user=ecu,
            course_id=f'{name}-course',
        )
        audit = factories.SapSuccessFactorsLearnerDataTransmissionAuditFactory(
            enterprise_course_enrollment_id=enrollment.id,
            sapsf_user_id=f'{name}-sap-user',
            course_id=f'{name}-course',
            course_completed=True,
            completed_timestamp=None,
            sap_completed_timestamp=123456,
            grade='Pass',
            enterprise_customer_uuid=config.enterprise_customer.uuid,
            plugin_configuration_id=config.id,
            is_transmitted=False,
        )
        audits[config.id] = audit
        exporters[config.id] = SimpleNamespace(
            export=lambda audit=audit, **kwargs: iter([audit])
        )

    _register_mock_endpoints(
        tenants,
        'learning/completion',
        lambda _name: {'success': True},
    )

    def exporter_for(config, _user):
        return exporters[config.id]

    with patch.object(
        SAPSuccessFactorsEnterpriseCustomerConfiguration,
        'get_learner_data_exporter',
        autospec=True,
        side_effect=exporter_for,
    ):
        for _, config, _ in tenants:
            transmit_learner_data(worker.username, config.channel_code(), config.pk)

    for name, config, token in tenants:
        audit = audits[config.id]
        audit.refresh_from_db()
        assert audit.is_transmitted
        assert audit.status == '200'

        api_call = _request_to(urljoin(config.sapsf_base_url, 'learning/completion'))
        assert api_call.headers['Authorization'] == f'Bearer {token}'
        assert json.loads(api_call.body)['userID'] == f'{name}-sap-user'

    _assert_tenant_logs_are_redacted(tenants)
