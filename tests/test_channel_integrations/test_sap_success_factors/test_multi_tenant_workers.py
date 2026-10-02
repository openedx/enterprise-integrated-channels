"""Regression tests for mixed legacy and self-signed SAP background workers."""

import json
from types import SimpleNamespace
from urllib.parse import urljoin, urlparse

import responses
from pytest import mark
from unittest.mock import patch

from channel_integrations.integrated_channel.models import (
    IntegratedChannelAPIRequestLogs,
)
from channel_integrations.integrated_channel.tasks import transmit_content_metadata, transmit_learner_data
from channel_integrations.sap_success_factors.models import (
    SAPSuccessFactorsEnterpriseCustomerConfiguration,
    SAPSuccessFactorsGlobalConfiguration,
)
from test_utils import factories


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
        ('legacy', 'legacy.sap.example.test', 'legacy-bearer-token'),
        ('modern', 'modern.sap.example.test', 'modern-bearer-token'),
    ):
        customer = factories.EnterpriseCustomerFactory(name=f'{name} customer')
        config = factories.SAPSuccessFactorsEnterpriseCustomerConfigurationFactory(
            enterprise_customer=customer,
            sapsf_base_url=f'https://{host}/',
            sapsf_company_id=f'{name}-company',
            sapsf_user_id=f'{name}-service-user',
            decrypted_key=f'{name}-client-id',
            decrypted_secret=f'{name}-client-secret',
            **({'self_signed': True} if name == 'modern' else {}),
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
            json=response_for_tenant(name),
            status=200,
        )


def _assert_tenant_logs_are_redacted(tenants):
    for _, config, access_token in tenants:
        records = IntegratedChannelAPIRequestLogs.objects.filter(
            enterprise_customer_configuration_id=config.id
        )
        assert records.count() == 2
        for record in records:
            logged_values = f'{record.payload} {record.response_body}'
            assert '-----BEGIN PRIVATE KEY-----' not in logged_values
            assert '<saml:Assertion' not in logged_values
            assert 'Authorization:' not in logged_values
            assert 'assertion=' not in logged_values
            assert access_token not in logged_values


@mark.django_db
@responses.activate
def test_content_metadata_worker_isolates_legacy_and_modern_tenants():
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

    def exporter_for(config, user):
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

        api_call = next(
            call.request for call in responses.calls
            if call.request.url == urljoin(config.sapsf_base_url, 'learning/course')
        )
        assert api_call.headers['Authorization'] == f'Bearer {token}'
        assert urlparse(api_call.url).hostname.startswith(name)

    _assert_tenant_logs_are_redacted(tenants)


@mark.django_db
@responses.activate
def test_learner_data_worker_isolates_legacy_and_modern_tenants():
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

    def exporter_for(config, user):
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

        api_call = next(
            call.request for call in responses.calls
            if call.request.url == urljoin(config.sapsf_base_url, 'learning/completion')
        )
        assert api_call.headers['Authorization'] == f'Bearer {token}'
        assert json.loads(api_call.body)['userID'] == f'{name}-sap-user'

    _assert_tenant_logs_are_redacted(tenants)
