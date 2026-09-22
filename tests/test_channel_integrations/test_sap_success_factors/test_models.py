"""
Tests for the `channel_integrations.sap_success_factors.models` models module.
"""

import unittest

from django.db import connection
from pytest import mark

from channel_integrations.sap_success_factors.models import (
    SAPAuthType,
    SAPSuccessFactorsEnterpriseCustomerConfiguration,
)
from test_utils.factories import EnterpriseCustomerFactory, SAPSuccessFactorsGlobalConfigurationFactory

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

    def test_auth_type_defaults_to_sap_signed_assertion(self):
        """
        A freshly created configuration keeps asking SAP's OAuth IdP API to mint the assertion.
        """
        assert self.config.auth_type == SAPAuthType.SAP_SIGNED_ASSERTION
        assert self.config.uses_self_signed_assertion is False

    def test_uses_self_signed_assertion(self):
        """
        ``uses_self_signed_assertion`` follows the configured auth type.
        """
        self.config.auth_type = SAPAuthType.SELF_SIGNED_ASSERTION
        assert self.config.uses_self_signed_assertion is True

    def test_saml_assertion_audience_default(self):
        """
        The SAML assertion audience defaults to SAP's standard audience and is overridable per customer.
        """
        assert self.config.saml_assertion_audience == 'www.successfactors.com'

        self.config.saml_assertion_audience = 'tenant.successfactors.eu'
        self.config.save()
        self.config.refresh_from_db()

        assert self.config.saml_assertion_audience == 'tenant.successfactors.eu'

    def test_global_endpoint_path_defaults(self):
        """
        The SAML assertion / OAuth token endpoint paths are global, defaulting to SAP's standard paths.
        """
        global_config = SAPSuccessFactorsGlobalConfigurationFactory()
        assert global_config.saml_assertion_api_path == '/oauth/idp'
        assert global_config.oauth_token_api_path == '/oauth/token'

        global_config.saml_assertion_api_path = '/global/assertion'
        global_config.oauth_token_api_path = '/global/token'
        global_config.save()
        global_config.refresh_from_db()

        assert global_config.saml_assertion_api_path == '/global/assertion'
        assert global_config.oauth_token_api_path == '/global/token'

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

    def test_is_valid_requires_private_key_for_self_signed_assertion(self):
        """
        A configuration using a self-signed assertion is only valid once a private key and the
        (global) token endpoint are set.
        """
        missing, _ = self.config.is_valid
        assert 'private_key' not in missing['missing']

        self.config.auth_type = SAPAuthType.SELF_SIGNED_ASSERTION
        missing, _ = self.config.is_valid
        assert 'private_key' in missing['missing']

        self.config.decrypted_private_key = PRIVATE_KEY
        missing, _ = self.config.is_valid
        assert 'private_key' not in missing['missing']

        SAPSuccessFactorsGlobalConfigurationFactory(oauth_token_api_path='')
        self.config.saml_assertion_audience = ''
        missing, _ = self.config.is_valid
        assert 'oauth_token_api_path' in missing['missing']
        assert 'saml_assertion_audience' in missing['missing']

    def test_is_valid_does_not_require_key_and_secret_for_self_signed_assertion(self):
        """
        The OAuth client credentials are only needed when SAP signs the assertion, which a
        self-signed assertion replaces entirely.
        """
        self.config.auth_type = SAPAuthType.SELF_SIGNED_ASSERTION
        self.config.decrypted_private_key = PRIVATE_KEY
        self.config.decrypted_key = ''
        self.config.decrypted_secret = ''

        missing, _ = self.config.is_valid
        assert 'key' not in missing['missing']
        assert 'secret' not in missing['missing']
        assert not missing['missing']

    def test_is_valid_requires_key_and_secret_for_sap_signed_assertion(self):
        """
        A SAP-signed assertion still authenticates with the OAuth client credentials, so both stay
        mandatory.
        """
        assert self.config.auth_type == SAPAuthType.SAP_SIGNED_ASSERTION
        self.config.decrypted_key = ''
        self.config.decrypted_secret = ''

        missing, _ = self.config.is_valid
        assert 'key' in missing['missing']
        assert 'secret' in missing['missing']
        # The self-signed-only fields must not leak into a SAP-signed config's requirements.
        assert 'private_key' not in missing['missing']
        assert 'saml_assertion_audience' not in missing['missing']

    def test_encrypted_private_key_passphrase(self):
        """
        Test the encrypted_private_key_passphrase property getter and setter.
        """
        assert self.config.encrypted_private_key_passphrase == ''

        self.config.decrypted_private_key_passphrase = 'a-passphrase'
        encrypted_value = self.config.encrypted_private_key_passphrase
        assert encrypted_value != 'a-passphrase'
        assert isinstance(encrypted_value, str)

        self.config.encrypted_private_key_passphrase = encrypted_value
        assert self.config.decrypted_private_key_passphrase == encrypted_value
