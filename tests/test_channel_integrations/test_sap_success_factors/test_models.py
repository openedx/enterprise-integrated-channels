"""
Tests for the `channel_integrations.sap_success_factors.models` models module.
"""

import unittest

import ddt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from django.db import connection
from edx_django_utils.cache import TieredCache
from pytest import mark

from channel_integrations.sap_success_factors.models import (
    SAPAuthType,
    SAPSuccessFactorsEnterpriseCustomerConfiguration,
)
from test_utils.factories import EnterpriseCustomerFactory, SAPSuccessFactorsGlobalConfigurationFactory

PASSPHRASE = 'a-passphrase'


def _pem(private_key, passphrase=None):
    """
    Serialize ``private_key`` as a PKCS#8 PEM string, encrypted with ``passphrase`` if given.
    """
    encryption = (
        serialization.BestAvailableEncryption(passphrase.encode())
        if passphrase else serialization.NoEncryption()
    )
    return private_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, encryption,
    ).decode()


_RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PRIVATE_KEY = _pem(_RSA_KEY)
ENCRYPTED_PRIVATE_KEY = _pem(_RSA_KEY, PASSPHRASE)
EC_PRIVATE_KEY = _pem(ec.generate_private_key(ec.SECP256R1()))
PUBLIC_KEY = _RSA_KEY.public_key().public_bytes(
    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
).decode()

# Named (private key, passphrase) cases, so ddt test ids don't embed the randomly generated keys.
LOADABLE_PRIVATE_KEYS = {
    'unprotected': (PRIVATE_KEY, ''),
    'passphrase_protected': (ENCRYPTED_PRIVATE_KEY, PASSPHRASE),
}
UNLOADABLE_PRIVATE_KEYS = {
    'not_pem': ('not a private key', ''),
    'public_key': (PUBLIC_KEY, ''),
    'missing_passphrase': (ENCRYPTED_PRIVATE_KEY, ''),
    'wrong_passphrase': (ENCRYPTED_PRIVATE_KEY, 'wrong-passphrase'),
    'unexpected_passphrase': (PRIVATE_KEY, PASSPHRASE),
    # Cannot sign an RSA-SHA256 assertion.
    'not_rsa': (EC_PRIVATE_KEY, ''),
}


@mark.django_db
@ddt.ddt
class TestSAPSuccessFactorsEnterpriseCustomerConfiguration(unittest.TestCase):
    """
    Tests of the ``SAPSuccessFactorsEnterpriseCustomerConfiguration`` model.
    """

    def setUp(self):
        # ``SAPSuccessFactorsGlobalConfiguration.current()`` is cached and outlives the test
        # transaction, so a global config created by one test would otherwise leak into others.
        TieredCache.dangerous_clear_all_tiers()
        self.addCleanup(TieredCache.dangerous_clear_all_tiers)
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

    def test_global_token_endpoint_path_default(self):
        """
        The OAuth token endpoint path is global, defaulting to SAP's standard path.
        """
        global_config = SAPSuccessFactorsGlobalConfigurationFactory()
        assert global_config.oauth_token_api_path == '/oauth/token'

        global_config.oauth_token_api_path = '/global/token'
        global_config.save()
        global_config.refresh_from_db()

        assert global_config.oauth_token_api_path == '/global/token'

    @ddt.data(
        ('decrypted_private_key', PRIVATE_KEY),
        ('decrypted_private_key_passphrase', PASSPHRASE),
    )
    @ddt.unpack
    def test_private_key_fields_are_encrypted_at_rest(self, field_name, value):
        """
        The private key and its passphrase are stored encrypted in the database but read back as
        plaintext through the ORM.
        """
        setattr(self.config, field_name, value)
        self.config.save()

        table = SAPSuccessFactorsEnterpriseCustomerConfiguration._meta.db_table
        with connection.cursor() as cursor:
            cursor.execute(
                f'SELECT {field_name} FROM {table} WHERE id = %s',
                [self.config.id],
            )
            stored_value = cursor.fetchone()[0]

        assert stored_value
        # Neither the value nor any line of a PEM key's base64 body is stored in the clear.
        assert all(line not in str(stored_value) for line in value.splitlines()[1:-1] or [value])

        self.config.refresh_from_db()
        assert getattr(self.config, field_name) == value

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

    def test_is_valid_does_not_require_secret_for_self_signed_assertion(self):
        """
        A self-signed assertion replaces the client secret, so it is only mandatory for a SAP-signed
        assertion.
        """
        self.config.auth_type = SAPAuthType.SELF_SIGNED_ASSERTION
        self.config.decrypted_private_key = PRIVATE_KEY
        self.config.decrypted_secret = ''

        missing, incorrect = self.config.is_valid
        assert not missing['missing']
        assert not incorrect['incorrect']

    def test_is_valid_requires_key_for_self_signed_assertion(self):
        """
        A self-signed assertion still carries the OAuth client id (as its Issuer and ``api_key``
        attribute), so the key stays mandatory.
        """
        self.config.auth_type = SAPAuthType.SELF_SIGNED_ASSERTION
        self.config.decrypted_private_key = PRIVATE_KEY
        self.config.decrypted_key = ''

        missing, _ = self.config.is_valid
        assert missing['missing'] == ['key']

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

    def test_is_valid_rejects_blank_saml_assertion_audience(self):
        """
        A whitespace-only audience is as unusable in a SAML assertion as an empty one.
        """
        self.config.auth_type = SAPAuthType.SELF_SIGNED_ASSERTION
        self.config.decrypted_private_key = PRIVATE_KEY
        self.config.saml_assertion_audience = '   '

        missing, _ = self.config.is_valid
        assert missing['missing'] == ['saml_assertion_audience']

    @ddt.data(
        (SAPAuthType.SELF_SIGNED_ASSERTION, ['sapsf_base_url']),
        (SAPAuthType.SAP_SIGNED_ASSERTION, []),
    )
    @ddt.unpack
    def test_is_valid_requires_https_base_url_for_self_signed_assertion(self, auth_type, expected_incorrect):
        """
        A self-signed assertion's Recipient is the token endpoint on the base URL, which must be HTTPS.
        """
        self.config.auth_type = auth_type
        self.config.decrypted_private_key = PRIVATE_KEY
        self.config.sapsf_base_url = 'http://sap.example.com'

        missing, incorrect = self.config.is_valid
        assert not missing['missing']
        assert incorrect['incorrect'] == expected_incorrect

    def test_is_valid_reports_malformed_base_url_once_for_self_signed_assertion(self):
        """
        A base URL that is not an absolute URL at all is reported as incorrect only once.
        """
        self.config.auth_type = SAPAuthType.SELF_SIGNED_ASSERTION
        self.config.decrypted_private_key = PRIVATE_KEY
        self.config.sapsf_base_url = 'sap.example.com'

        _, incorrect = self.config.is_valid
        assert incorrect['incorrect'] == ['sapsf_base_url']

    @ddt.data(*LOADABLE_PRIVATE_KEYS)
    def test_is_valid_accepts_loadable_private_key(self, case):
        """
        An RSA private key that the configured passphrase (if any) unlocks is valid.
        """
        private_key, passphrase = LOADABLE_PRIVATE_KEYS[case]
        self.config.auth_type = SAPAuthType.SELF_SIGNED_ASSERTION
        self.config.decrypted_private_key = private_key
        self.config.decrypted_private_key_passphrase = passphrase

        missing, incorrect = self.config.is_valid
        assert not missing['missing']
        assert not incorrect['incorrect']

    @ddt.data(*UNLOADABLE_PRIVATE_KEYS)
    def test_is_valid_rejects_unloadable_private_key(self, case):
        """
        A private key that cannot be loaded as an RSA key with the configured passphrase is
        reported as incorrect, rather than failing later when an assertion is signed.
        """
        private_key, passphrase = UNLOADABLE_PRIVATE_KEYS[case]
        self.config.auth_type = SAPAuthType.SELF_SIGNED_ASSERTION
        self.config.decrypted_private_key = private_key
        self.config.decrypted_private_key_passphrase = passphrase

        missing, incorrect = self.config.is_valid
        assert not missing['missing']
        assert incorrect['incorrect'] == ['private_key']

    def test_is_valid_ignores_private_key_for_sap_signed_assertion(self):
        """
        The private key is only checked when it is actually used.
        """
        self.config.decrypted_private_key = 'not a private key'

        _, incorrect = self.config.is_valid
        assert not incorrect['incorrect']
