"""
Tests for the `channel_integrations.sap_success_factors.models` models module.
"""

import unittest

from pytest import mark

from django.db import connection

from channel_integrations.sap_success_factors.models import SAPSuccessFactorsEnterpriseCustomerConfiguration
from test_utils.factories import EnterpriseCustomerFactory

PRIVATE_KEY = (
    '-----BEGIN PRIVATE KEY-----\n'
    'MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDfakeKeyMaterial\n'
    '-----END PRIVATE KEY-----\n'
)


@mark.django_db
class TestSAPSuccessFactorsEnterpriseCustomerConfiguration(unittest.TestCase):
    """
    Tests of the ``SAPSuccessFactorsEnterpriseCustomerConfiguration`` model.
    """

    def setUp(self):
        self.enterprise_customer = EnterpriseCustomerFactory()
        self.config = SAPSuccessFactorsEnterpriseCustomerConfiguration(
            enterprise_customer=self.enterprise_customer,
            active=True,
            sapsf_base_url='https://sap.example.com',
            sapsf_company_id='COMP1',
            sapsf_user_id='user-1',
            decrypted_key='a-key',
            decrypted_secret='a-secret',
        )
        self.config.save()
        super().setUp()

    def test_auth_type_defaults_to_legacy(self):
        """
        A freshly created configuration keeps using the legacy SAP OAuth IdP API.
        """
        assert self.config.auth_type == SAPSuccessFactorsEnterpriseCustomerConfiguration.AUTH_TYPE_LEGACY
        assert self.config.uses_modern_saml_bearer_auth is False

    def test_uses_modern_saml_bearer_auth(self):
        """
        ``uses_modern_saml_bearer_auth`` follows the configured auth type.
        """
        self.config.auth_type = SAPSuccessFactorsEnterpriseCustomerConfiguration.AUTH_TYPE_MODERN_SAML_BEARER
        assert self.config.uses_modern_saml_bearer_auth is True

    def test_tenant_endpoint_path_defaults(self):
        """
        The tenant-specific endpoint paths default to SAP's standard paths and are overridable per customer.
        """
        assert self.config.saml_assertion_api_path == '/oauth/idp'
        assert self.config.oauth_token_api_path == '/oauth/token'
        assert self.config.saml_assertion_audience == 'www.successfactors.com'

        self.config.saml_assertion_api_path = '/tenant/assertion'
        self.config.oauth_token_api_path = '/tenant/token'
        self.config.saml_assertion_audience = 'tenant.successfactors.eu'
        self.config.save()
        self.config.refresh_from_db()

        assert self.config.saml_assertion_api_path == '/tenant/assertion'
        assert self.config.oauth_token_api_path == '/tenant/token'
        assert self.config.saml_assertion_audience == 'tenant.successfactors.eu'

    def test_encrypted_private_key(self):
        """
        Test the encrypted_private_key property getter and setter.
        """
        assert self.config.encrypted_private_key == ''

        self.config.decrypted_private_key = PRIVATE_KEY
        encrypted_value = self.config.encrypted_private_key
        assert encrypted_value != PRIVATE_KEY
        assert isinstance(encrypted_value, str)

        self.config.encrypted_private_key = encrypted_value
        assert self.config.decrypted_private_key == encrypted_value

    def test_private_key_is_encrypted_at_rest(self):
        """
        The private key is stored encrypted in the database but reads back as plaintext through the ORM.
        """
        self.config.decrypted_private_key = PRIVATE_KEY
        self.config.save()

        table = SAPSuccessFactorsEnterpriseCustomerConfiguration._meta.db_table
        with connection.cursor() as cursor:
            cursor.execute(
                f'SELECT decrypted_private_key FROM {table} WHERE id = %s',
                [self.config.id],
            )
            stored_value = cursor.fetchone()[0]

        assert stored_value
        assert PRIVATE_KEY not in str(stored_value)
        assert 'fakeKeyMaterial' not in str(stored_value)

        self.config.refresh_from_db()
        assert self.config.decrypted_private_key == PRIVATE_KEY

    def test_is_valid_requires_private_key_for_modern_auth(self):
        """
        A configuration on modern auth is only valid once a private key and the token endpoint are set.
        """
        missing, _ = self.config.is_valid
        assert 'private_key' not in missing['missing']

        self.config.auth_type = SAPSuccessFactorsEnterpriseCustomerConfiguration.AUTH_TYPE_MODERN_SAML_BEARER
        missing, _ = self.config.is_valid
        assert 'private_key' in missing['missing']

        self.config.decrypted_private_key = PRIVATE_KEY
        missing, _ = self.config.is_valid
        assert 'private_key' not in missing['missing']

        self.config.oauth_token_api_path = ''
        self.config.saml_assertion_audience = ''
        missing, _ = self.config.is_valid
        assert 'oauth_token_api_path' in missing['missing']
        assert 'saml_assertion_audience' in missing['missing']

    def test_is_valid_ignores_saml_assertion_api_path_for_modern_auth(self):
        """
        Modern auth signs the assertion itself, so SAP's IdP endpoint is not part of a valid config.
        """
        self.config.auth_type = SAPSuccessFactorsEnterpriseCustomerConfiguration.AUTH_TYPE_MODERN_SAML_BEARER
        self.config.decrypted_private_key = PRIVATE_KEY
        self.config.saml_assertion_api_path = ''

        missing, _ = self.config.is_valid
        assert 'saml_assertion_api_path' not in missing['missing']
        assert not missing['missing']

    def test_is_valid_does_not_require_key_and_secret_for_modern_auth(self):
        """
        The OAuth client credentials belong to the legacy flow, which modern auth replaces entirely.
        """
        self.config.auth_type = SAPSuccessFactorsEnterpriseCustomerConfiguration.AUTH_TYPE_MODERN_SAML_BEARER
        self.config.decrypted_private_key = PRIVATE_KEY
        self.config.decrypted_key = ''
        self.config.decrypted_secret = ''

        missing, _ = self.config.is_valid
        assert 'key' not in missing['missing']
        assert 'secret' not in missing['missing']
        assert not missing['missing']

    def test_is_valid_requires_key_and_secret_for_legacy_auth(self):
        """
        Legacy auth still authenticates with the OAuth client credentials, so both stay mandatory.
        """
        assert self.config.auth_type == SAPSuccessFactorsEnterpriseCustomerConfiguration.AUTH_TYPE_LEGACY
        self.config.decrypted_key = ''
        self.config.decrypted_secret = ''

        missing, _ = self.config.is_valid
        assert 'key' in missing['missing']
        assert 'secret' in missing['missing']
        # The modern-only fields must not leak into a legacy config's requirements.
        assert 'private_key' not in missing['missing']
        assert 'saml_assertion_audience' not in missing['missing']
