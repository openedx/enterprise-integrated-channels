"""
Tests for the `channel_integrations` success factors configuration api.
"""
import json
from unittest import mock
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.apps import apps
from django.urls import reverse

from enterprise.constants import ENTERPRISE_ADMIN_ROLE
from enterprise.utils import localized_utcnow
from channel_integrations.sap_success_factors.models import (
    SAPAuthType,
    SAPSuccessFactorsEnterpriseCustomerConfiguration,
)
from channel_integrations.sap_success_factors.utils import populate_decrypted_fields_sap_success_factors
from channel_integrations.utils import MAX_PRIVATE_KEY_PEM_LENGTH
from test_utils import APITest, factories, generate_test_private_key_pem

ENTERPRISE_ID = str(uuid4())


class SAPSuccessFactorsConfigurationViewSetTests(APITest):
    """
    Tests for SAPSuccessFactorsConfigurationViewSet REST endpoints
    """
    def setUp(self):
        super().setUp()
        self.user.is_superuser = True
        self.user.save()

        self.enterprise_customer = factories.EnterpriseCustomerFactory(uuid=ENTERPRISE_ID)
        self.enterprise_customer_user = factories.EnterpriseCustomerUserFactory(
            enterprise_customer=self.enterprise_customer,
            user_id=self.user.id,
        )

        self.sap_config = factories.SAPSuccessFactorsEnterpriseCustomerConfigurationFactory(
            enterprise_customer=self.enterprise_customer
        )

    @mock.patch('enterprise.rules.crum.get_current_request')
    def test_soft_deleted_content_in_lists(self, mock_current_request):
        factories.SAPSuccessFactorsEnterpriseCustomerConfigurationFactory(
            enterprise_customer=self.enterprise_customer,
            deleted_at=localized_utcnow(),
        )
        mock_current_request.return_value = self.get_request_with_jwt_cookie(
            system_wide_role=ENTERPRISE_ADMIN_ROLE,
            context=self.enterprise_customer.uuid,
        )

        url = reverse('api:v1:sap_success_factors:configuration-list')
        response = self.client.get(url)
        data = json.loads(response.content.decode('utf-8')).get('results')

        assert len(data) == 1
        assert data[0]['id'] == self.sap_config.id
        assert len(SAPSuccessFactorsEnterpriseCustomerConfiguration.all_objects.all()) == 2
        assert len(SAPSuccessFactorsEnterpriseCustomerConfiguration.objects.all()) == 1

    @mock.patch('enterprise.rules.crum.get_current_request')
    def test_get(self, mock_current_request):
        mock_current_request.return_value = self.get_request_with_jwt_cookie(
            system_wide_role=ENTERPRISE_ADMIN_ROLE,
            context=self.enterprise_customer.uuid,
        )
        url = reverse('api:v1:sap_success_factors:configuration-detail', args=[self.sap_config.id])
        response = self.client.get(url)
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data.get('sapsf_base_url'),
                         self.sap_config.sapsf_base_url)
        self.assertEqual(data.get('sapsf_company_id'),
                         self.sap_config.sapsf_company_id)
        self.assertEqual(int(data.get('sapsf_user_id')),
                         self.sap_config.sapsf_user_id)
        self.assertEqual(data.get('user_type'),
                         self.sap_config.user_type)
        self.assertEqual(data.get('enterprise_customer'),
                         str(self.sap_config.enterprise_customer.uuid))

    @mock.patch('enterprise.rules.crum.get_current_request')
    def test_update(self, mock_current_request):
        mock_current_request.return_value = self.get_request_with_jwt_cookie(
            system_wide_role=ENTERPRISE_ADMIN_ROLE,
            context=self.enterprise_customer.uuid,
        )
        url = reverse('api:v1:sap_success_factors:configuration-detail', args=[self.sap_config.id])
        payload = {
            'sapsf_base_url': 'http://testing2',
            'sapsf_company_id': 'test',
            'enterprise_customer': ENTERPRISE_ID,
            'sapsf_user_id': 893489,
            'key': '',
            'secret': '',
            'user_type': 'user',
        }
        response = self.client.put(url, payload)
        self.sap_config.refresh_from_db()
        self.assertEqual(self.sap_config.sapsf_base_url, 'http://testing2')
        self.assertEqual(self.sap_config.sapsf_company_id, 'test')
        self.assertEqual(self.sap_config.decrypted_key, '')
        self.assertEqual(self.sap_config.decrypted_secret, '')
        self.assertEqual(self.sap_config.user_type, 'user')
        self.assertEqual(self.sap_config.sapsf_user_id, '893489')
        self.assertEqual(response.status_code, 200)

    @mock.patch('enterprise.rules.crum.get_current_request')
    def test_populate_decrypted_fields(self, mock_current_request):
        mock_current_request.return_value = self.get_request_with_jwt_cookie(
            system_wide_role=ENTERPRISE_ADMIN_ROLE,
            context=self.enterprise_customer.uuid,
        )
        url = reverse('api:v1:sap_success_factors:configuration-detail', args=[self.sap_config.id])
        client_secret = getattr(self.sap_config, 'secret', '')
        payload = {
            'sapsf_base_url': 'http://testing2',
            'sapsf_company_id': 'test',
            'enterprise_customer': ENTERPRISE_ID,
            'sapsf_user_id': 893489,
            'user_type': 'user',
            'secret': '1000',
        }
        self.client.put(url, payload)
        self.sap_config.refresh_from_db()
        self.assertEqual(self.sap_config.decrypted_secret, '1000')
        populate_decrypted_fields_sap_success_factors(apps)
        self.sap_config.refresh_from_db()
        self.assertEqual(self.sap_config.encrypted_secret, client_secret)

    @mock.patch('enterprise.rules.crum.get_current_request')
    def test_patch(self, mock_current_request):
        mock_current_request.return_value = self.get_request_with_jwt_cookie(
            system_wide_role=ENTERPRISE_ADMIN_ROLE,
            context=self.enterprise_customer.uuid,
        )
        url = reverse('api:v1:sap_success_factors:configuration-detail', args=[self.sap_config.id])
        payload = {
            'sapsf_base_url': 'http://testingchange',
            'enterprise_customer': ENTERPRISE_ID,
        }
        response = self.client.patch(url, payload)
        self.sap_config.refresh_from_db()
        self.assertEqual(self.sap_config.sapsf_base_url, 'http://testingchange')
        self.assertEqual(response.status_code, 200)

    @mock.patch('enterprise.rules.crum.get_current_request')
    def test_delete(self, mock_current_request):
        mock_current_request.return_value = self.get_request_with_jwt_cookie(
            system_wide_role=ENTERPRISE_ADMIN_ROLE,
            context=self.enterprise_customer.uuid,
        )
        url = reverse('api:v1:sap_success_factors:configuration-detail', args=[self.sap_config.id])
        response = self.client.delete(url)
        configs = SAPSuccessFactorsEnterpriseCustomerConfiguration.objects.filter()
        self.assertEqual(response.status_code, 204)
        self.assertEqual(len(configs), 0)

    @mock.patch('enterprise.rules.crum.get_current_request')
    def test_update_self_signed_auth_type_with_private_key(self, mock_current_request):
        mock_current_request.return_value = self.get_request_with_jwt_cookie(
            system_wide_role=ENTERPRISE_ADMIN_ROLE,
            context=self.enterprise_customer.uuid,
        )
        url = reverse('api:v1:sap_success_factors:configuration-detail', args=[self.sap_config.id])
        private_key = generate_test_private_key_pem()
        payload = {
            'sapsf_base_url': 'https://testing2',
            'sapsf_company_id': 'test',
            'enterprise_customer': ENTERPRISE_ID,
            'sapsf_user_id': 893489,
            'user_type': 'user',
            'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION,
            'private_key': private_key,
        }
        response = self.client.put(url, payload)
        self.sap_config.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.sap_config.auth_type, SAPAuthType.SELF_SIGNED_ASSERTION)
        self.assertEqual(self.sap_config.decrypted_private_key.strip(), private_key.strip())

    @mock.patch('enterprise.rules.crum.get_current_request')
    def test_update_rejects_malformed_private_key(self, mock_current_request):
        mock_current_request.return_value = self.get_request_with_jwt_cookie(
            system_wide_role=ENTERPRISE_ADMIN_ROLE,
            context=self.enterprise_customer.uuid,
        )
        url = reverse('api:v1:sap_success_factors:configuration-detail', args=[self.sap_config.id])
        payload = {
            'sapsf_base_url': 'http://testing2',
            'sapsf_company_id': 'test',
            'enterprise_customer': ENTERPRISE_ID,
            'sapsf_user_id': 893489,
            'user_type': 'user',
            'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION,
            'private_key': 'not-a-pem-key',
        }
        response = self.client.put(url, payload)
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content.decode('utf-8'))
        self.assertIn('private_key', data)
        self.sap_config.refresh_from_db()
        self.assertEqual(self.sap_config.decrypted_private_key, '')

    @mock.patch('enterprise.rules.crum.get_current_request')
    def test_passphrase_only_update_rejected_if_it_cannot_unlock_stored_key(self, mock_current_request):
        mock_current_request.return_value = self.get_request_with_jwt_cookie(
            system_wide_role=ENTERPRISE_ADMIN_ROLE,
            context=self.enterprise_customer.uuid,
        )
        self.sap_config.auth_type = SAPAuthType.SELF_SIGNED_ASSERTION
        self.sap_config.decrypted_private_key = generate_test_private_key_pem()
        self.sap_config.save()

        url = reverse('api:v1:sap_success_factors:configuration-detail', args=[self.sap_config.id])
        response = self.client.patch(
            url,
            data=json.dumps({'private_key_passphrase': 'a-passphrase-the-stored-key-does-not-use'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content.decode('utf-8'))
        self.assertIn('private_key', data)

    @mock.patch('enterprise.rules.crum.get_current_request')
    def test_switching_auth_type_alone_requires_an_existing_or_submitted_key(self, mock_current_request):
        """
        Regression: a PATCH touching only ``auth_type`` (no ``private_key`` field at all) used to
        skip credential validation entirely, since the check only ran when ``private_key`` or
        ``private_key_passphrase`` were present in the request. That let a configuration switch to
        self-signed with no usable key.
        """
        mock_current_request.return_value = self.get_request_with_jwt_cookie(
            system_wide_role=ENTERPRISE_ADMIN_ROLE,
            context=self.enterprise_customer.uuid,
        )
        url = reverse('api:v1:sap_success_factors:configuration-detail', args=[self.sap_config.id])
        response = self.client.patch(
            url,
            data=json.dumps({'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content.decode('utf-8'))
        self.assertIn('private_key', data)
        self.sap_config.refresh_from_db()
        self.assertNotEqual(self.sap_config.auth_type, SAPAuthType.SELF_SIGNED_ASSERTION)

    @mock.patch('enterprise.rules.crum.get_current_request')
    def test_new_encrypted_key_validated_against_stored_passphrase(self, mock_current_request):
        mock_current_request.return_value = self.get_request_with_jwt_cookie(
            system_wide_role=ENTERPRISE_ADMIN_ROLE,
            context=self.enterprise_customer.uuid,
        )
        passphrase = 'correct-horse'
        encrypted_key = generate_test_private_key_pem(passphrase=passphrase)
        self.sap_config.auth_type = SAPAuthType.SELF_SIGNED_ASSERTION
        self.sap_config.decrypted_private_key_passphrase = passphrase
        self.sap_config.save()

        url = reverse('api:v1:sap_success_factors:configuration-detail', args=[self.sap_config.id])
        payload = {
            'sapsf_base_url': 'https://testing2',
            'sapsf_company_id': 'test',
            'enterprise_customer': ENTERPRISE_ID,
            'sapsf_user_id': 893489,
            'user_type': 'user',
            'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION,
            'private_key': encrypted_key,
        }
        response = self.client.put(url, payload)
        self.assertEqual(response.status_code, 200)
        self.sap_config.refresh_from_db()
        self.assertEqual(self.sap_config.decrypted_private_key.strip(), encrypted_key.strip())

    @mock.patch('enterprise.rules.crum.get_current_request')
    def test_blank_private_key_passphrase_clears_stored_passphrase(self, mock_current_request):
        """Matches MoodleConfigSerializer: an omitted field is unchanged, a blank one clears it."""
        mock_current_request.return_value = self.get_request_with_jwt_cookie(
            system_wide_role=ENTERPRISE_ADMIN_ROLE,
            context=self.enterprise_customer.uuid,
        )
        unencrypted_key = generate_test_private_key_pem()
        self.sap_config.auth_type = SAPAuthType.SELF_SIGNED_ASSERTION
        self.sap_config.sapsf_base_url = 'https://testing2'
        self.sap_config.saml_assertion_audience = 'www.successfactors.com'
        self.sap_config.decrypted_private_key = generate_test_private_key_pem(passphrase='old-passphrase')
        self.sap_config.decrypted_private_key_passphrase = 'old-passphrase'
        self.sap_config.save()

        url = reverse('api:v1:sap_success_factors:configuration-detail', args=[self.sap_config.id])
        response = self.client.patch(
            url,
            data=json.dumps({
                'private_key': unencrypted_key,
                'private_key_passphrase': '',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.sap_config.refresh_from_db()
        self.assertEqual(self.sap_config.decrypted_private_key.strip(), unencrypted_key.strip())
        self.assertEqual(self.sap_config.decrypted_private_key_passphrase, '')

    @mock.patch('enterprise.rules.crum.get_current_request')
    def test_blank_private_key_clears_stored_key(self, mock_current_request):
        """Matches MoodleConfigSerializer: an omitted field is unchanged, a blank one clears it."""
        mock_current_request.return_value = self.get_request_with_jwt_cookie(
            system_wide_role=ENTERPRISE_ADMIN_ROLE,
            context=self.enterprise_customer.uuid,
        )
        self.sap_config.auth_type = SAPAuthType.SELF_SIGNED_ASSERTION
        self.sap_config.decrypted_private_key = generate_test_private_key_pem()
        self.sap_config.save()

        url = reverse('api:v1:sap_success_factors:configuration-detail', args=[self.sap_config.id])
        response = self.client.patch(
            url,
            data=json.dumps({
                'auth_type': SAPAuthType.SAP_SIGNED_ASSERTION,
                'private_key': '',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.sap_config.refresh_from_db()
        self.assertEqual(self.sap_config.decrypted_private_key, '')

    @mock.patch('enterprise.rules.crum.get_current_request')
    def test_blank_private_key_while_still_self_signed_rejected(self, mock_current_request):
        """
        Regression: clearing the only private key must not be allowed to leave a self-signed
        configuration with no usable key -- get_credential_errors still requires one.
        """
        mock_current_request.return_value = self.get_request_with_jwt_cookie(
            system_wide_role=ENTERPRISE_ADMIN_ROLE,
            context=self.enterprise_customer.uuid,
        )
        self.sap_config.auth_type = SAPAuthType.SELF_SIGNED_ASSERTION
        self.sap_config.decrypted_private_key = generate_test_private_key_pem()
        self.sap_config.save()

        url = reverse('api:v1:sap_success_factors:configuration-detail', args=[self.sap_config.id])
        response = self.client.patch(
            url,
            data=json.dumps({'private_key': ''}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content.decode('utf-8'))
        self.assertIn('private_key', data)
        self.sap_config.refresh_from_db()
        self.assertNotEqual(self.sap_config.decrypted_private_key, '')

    @mock.patch('enterprise.rules.crum.get_current_request')
    def test_create_self_signed_auth_type_with_private_key(self, mock_current_request):
        mock_current_request.return_value = self.get_request_with_jwt_cookie(
            system_wide_role=ENTERPRISE_ADMIN_ROLE,
            context=self.enterprise_customer.uuid,
        )
        url = reverse('api:v1:sap_success_factors:configuration-list')
        private_key = generate_test_private_key_pem()
        payload = {
            'sapsf_base_url': 'https://testing2',
            'sapsf_company_id': 'test',
            'enterprise_customer': ENTERPRISE_ID,
            'sapsf_user_id': 893489,
            'user_type': 'user',
            'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION,
            'private_key': private_key,
            'saml_assertion_audience': 'www.successfactors.com',
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 201, response.content)
        created = SAPSuccessFactorsEnterpriseCustomerConfiguration.objects.get(
            id=json.loads(response.content.decode('utf-8'))['id']
        )
        self.assertEqual(created.auth_type, SAPAuthType.SELF_SIGNED_ASSERTION)
        self.assertEqual(created.decrypted_private_key.strip(), private_key.strip())

    @mock.patch('enterprise.rules.crum.get_current_request')
    def test_create_self_signed_auth_type_without_audience_uses_model_default(self, mock_current_request):
        """
        Regression: omitting saml_assertion_audience on create must validate against the model
        field's default ('www.successfactors.com'), not an empty string -- the serializer has no
        instance yet to fall back on, so it must use a fresh candidate instead.
        """
        mock_current_request.return_value = self.get_request_with_jwt_cookie(
            system_wide_role=ENTERPRISE_ADMIN_ROLE,
            context=self.enterprise_customer.uuid,
        )
        url = reverse('api:v1:sap_success_factors:configuration-list')
        payload = {
            'sapsf_base_url': 'https://testing2',
            'sapsf_company_id': 'test',
            'enterprise_customer': ENTERPRISE_ID,
            'sapsf_user_id': 893489,
            'user_type': 'user',
            'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION,
            'private_key': generate_test_private_key_pem(),
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 201, response.content)
        created = SAPSuccessFactorsEnterpriseCustomerConfiguration.objects.get(
            id=json.loads(response.content.decode('utf-8'))['id']
        )
        self.assertEqual(created.saml_assertion_audience, 'www.successfactors.com')

    @mock.patch('enterprise.rules.crum.get_current_request')
    def test_create_self_signed_auth_type_without_private_key_rejected(self, mock_current_request):
        mock_current_request.return_value = self.get_request_with_jwt_cookie(
            system_wide_role=ENTERPRISE_ADMIN_ROLE,
            context=self.enterprise_customer.uuid,
        )
        url = reverse('api:v1:sap_success_factors:configuration-list')
        payload = {
            'sapsf_base_url': 'https://testing2',
            'sapsf_company_id': 'test',
            'enterprise_customer': ENTERPRISE_ID,
            'sapsf_user_id': 893489,
            'user_type': 'user',
            'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION,
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content.decode('utf-8'))
        self.assertIn('private_key', data)

    @mock.patch('enterprise.rules.crum.get_current_request')
    def test_create_self_signed_auth_type_without_base_url_rejected(self, mock_current_request):
        """Regression: is_valid_url('') is True, so a blank URL must be checked separately."""
        mock_current_request.return_value = self.get_request_with_jwt_cookie(
            system_wide_role=ENTERPRISE_ADMIN_ROLE,
            context=self.enterprise_customer.uuid,
        )
        url = reverse('api:v1:sap_success_factors:configuration-list')
        payload = {
            'sapsf_company_id': 'test',
            'enterprise_customer': ENTERPRISE_ID,
            'sapsf_user_id': 893489,
            'user_type': 'user',
            'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION,
            'private_key': generate_test_private_key_pem(),
            'saml_assertion_audience': 'www.successfactors.com',
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content.decode('utf-8'))
        self.assertIn('sapsf_base_url', data)

    @mock.patch('enterprise.rules.crum.get_current_request')
    def test_passphrase_with_meaningful_whitespace_is_not_stripped(self, mock_current_request):
        """Regression: DRF's CharField strips whitespace by default, but decryption needs exact bytes."""
        mock_current_request.return_value = self.get_request_with_jwt_cookie(
            system_wide_role=ENTERPRISE_ADMIN_ROLE,
            context=self.enterprise_customer.uuid,
        )
        passphrase = ' has leading and trailing spaces '
        url = reverse('api:v1:sap_success_factors:configuration-detail', args=[self.sap_config.id])
        response = self.client.patch(
            url,
            data=json.dumps({
                'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION,
                'sapsf_base_url': 'https://testing2',
                'private_key': generate_test_private_key_pem(passphrase=passphrase),
                'private_key_passphrase': passphrase,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.sap_config.refresh_from_db()
        self.assertEqual(self.sap_config.decrypted_private_key_passphrase, passphrase)

    @mock.patch('enterprise.rules.crum.get_current_request')
    def test_sap_signed_update_with_schemeless_stored_url_is_not_blocked(self, mock_current_request):
        """
        Regression: ``is_valid`` flags ``sapsf_base_url`` as incorrect for any auth type once it's
        schemeless, but that check is informational there. ``get_credential_errors`` must only
        turn it into a hard validation error for a self-signed configuration -- otherwise an
        existing SAP-signed customer with a schemeless stored URL gets blocked from saving
        anything at all, even an unrelated field.
        """
        mock_current_request.return_value = self.get_request_with_jwt_cookie(
            system_wide_role=ENTERPRISE_ADMIN_ROLE,
            context=self.enterprise_customer.uuid,
        )
        self.sap_config.auth_type = SAPAuthType.SAP_SIGNED_ASSERTION
        self.sap_config.sapsf_base_url = 'sapsf.example.com'
        self.sap_config.save()

        url = reverse('api:v1:sap_success_factors:configuration-detail', args=[self.sap_config.id])
        response = self.client.patch(
            url,
            data=json.dumps({'active': False}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)

    @mock.patch('enterprise.rules.crum.get_current_request')
    def test_create_self_signed_rejects_key_below_minimum_size(self, mock_current_request):
        mock_current_request.return_value = self.get_request_with_jwt_cookie(
            system_wide_role=ENTERPRISE_ADMIN_ROLE,
            context=self.enterprise_customer.uuid,
        )
        weak_key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
        weak_pem = weak_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ).decode('utf-8')

        url = reverse('api:v1:sap_success_factors:configuration-list')
        payload = {
            'sapsf_base_url': 'https://testing2',
            'sapsf_company_id': 'test',
            'enterprise_customer': ENTERPRISE_ID,
            'sapsf_user_id': 893489,
            'user_type': 'user',
            'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION,
            'private_key': weak_pem,
            'saml_assertion_audience': 'www.successfactors.com',
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content.decode('utf-8'))
        self.assertIn('private_key', data)

    @mock.patch('enterprise.rules.crum.get_current_request')
    def test_update_rejects_private_key_over_max_length(self, mock_current_request):
        mock_current_request.return_value = self.get_request_with_jwt_cookie(
            system_wide_role=ENTERPRISE_ADMIN_ROLE,
            context=self.enterprise_customer.uuid,
        )
        url = reverse('api:v1:sap_success_factors:configuration-detail', args=[self.sap_config.id])
        response = self.client.patch(
            url,
            data=json.dumps({
                'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION,
                'private_key': 'x' * (MAX_PRIVATE_KEY_PEM_LENGTH + 1),
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content.decode('utf-8'))
        self.assertIn('private_key', data)

    @mock.patch('enterprise.rules.crum.get_current_request')
    def test_update_rejects_private_key_passphrase_over_max_length(self, mock_current_request):
        mock_current_request.return_value = self.get_request_with_jwt_cookie(
            system_wide_role=ENTERPRISE_ADMIN_ROLE,
            context=self.enterprise_customer.uuid,
        )
        url = reverse('api:v1:sap_success_factors:configuration-detail', args=[self.sap_config.id])
        response = self.client.patch(
            url,
            data=json.dumps({'private_key_passphrase': 'x' * 256}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content.decode('utf-8'))
        self.assertIn('private_key_passphrase', data)

    @mock.patch('enterprise.rules.crum.get_current_request')
    def test_private_key_never_returned_in_get(self, mock_current_request):
        """
        Regression: asserting only that the ``private_key``/``private_key_passphrase`` keys are
        absent from the response can't fail even if ``write_only`` were accidentally dropped --
        DRF silently omits a field it can't resolve from the instance (there's no matching model
        attribute) regardless of ``write_only``. Assert the key's actual PEM content is nowhere in
        the response body instead, so this test would actually catch that regression.
        """
        mock_current_request.return_value = self.get_request_with_jwt_cookie(
            system_wide_role=ENTERPRISE_ADMIN_ROLE,
            context=self.enterprise_customer.uuid,
        )
        self.sap_config.auth_type = SAPAuthType.SELF_SIGNED_ASSERTION
        stored_key = generate_test_private_key_pem(passphrase='a-passphrase')
        self.sap_config.decrypted_private_key = stored_key
        self.sap_config.decrypted_private_key_passphrase = 'a-passphrase'
        self.sap_config.save()

        url = reverse('api:v1:sap_success_factors:configuration-detail', args=[self.sap_config.id])
        response = self.client.get(url)
        body = response.content.decode('utf-8')
        data = json.loads(body)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('private_key', data)
        self.assertNotIn('private_key_passphrase', data)
        # A raw substring check on the PEM would always pass: JSON escapes its newlines, so the
        # unescaped key never literally matches even if it leaked under another field name.
        pem_body_line = stored_key.strip().splitlines()[1]
        self.assertNotIn(pem_body_line, body)
        self.assertNotIn('a-passphrase', body)
        self.assertEqual(data.get('auth_type'), SAPAuthType.SELF_SIGNED_ASSERTION)

    @mock.patch('enterprise.rules.crum.get_current_request')
    def test_is_valid_field(self, mock_current_request):
        self.user.is_superuser = True
        self.user.save()

        mock_current_request.return_value = self.get_request_with_jwt_cookie(
            system_wide_role=ENTERPRISE_ADMIN_ROLE,
            context=self.enterprise_customer.uuid,
        )
        url = reverse('api:v1:sap_success_factors:configuration-list')

        self.sap_config.sapsf_base_url = 'sad'
        self.sap_config.display_name = 'suchalongdisplaynamelikewowww'
        self.sap_config.save()
        response = self.client.get(url)
        data = json.loads(response.content.decode('utf-8')).get('results')

        missing, incorrect = data[0].get('is_valid')
        assert missing.get('missing') == ['key', 'secret']
        assert incorrect.get('incorrect') == ['sapsf_base_url', 'display_name']

        self.sap_config.sapsf_base_url = ''
        self.sap_config.sapsf_company_id = ''
        self.sap_config.sapsf_user_id = ''
        self.sap_config.save()
        response = self.client.get(url)
        data = json.loads(response.content.decode('utf-8')).get('results')

        missing, _ = data[0].get('is_valid')
        assert missing.get('missing') == ['key', 'sapsf_base_url', 'sapsf_company_id', 'sapsf_user_id', 'secret']

        self.sap_config.decrypted_key = 'ayy'
        self.sap_config.decrypted_secret = 'lmao'
        self.sap_config.sapsf_company_id = '1'
        self.sap_config.sapsf_user_id = '1'
        self.sap_config.sapsf_base_url = 'http://happy.com'
        self.sap_config.display_name = 'better'
        self.sap_config.save()
        response = self.client.get(url)
        data = json.loads(response.content.decode('utf-8')).get('results')
        missing, incorrect = data[0].get('is_valid')
        assert not missing.get('missing') and not incorrect.get('incorrect')
