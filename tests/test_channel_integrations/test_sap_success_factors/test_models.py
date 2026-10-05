"""
Tests for the `channel_integrations.sap_success_factors.models` models module.
"""

import unittest
from unittest import mock

import ddt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from django.db import connection
from edx_django_utils.cache import TieredCache
from enterprise.utils import localized_utcnow
from pytest import mark

from channel_integrations.sap_success_factors.models import (
    SAPAuthType,
    SAPSuccessFactorsEnterpriseCustomerConfiguration,
)
from test_utils.factories import EnterpriseCustomerFactory, SAPSuccessFactorsGlobalConfigurationFactory, UserFactory

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
ENCRYPTED_EC_PRIVATE_KEY = _pem(ec.generate_private_key(ec.SECP256R1()), PASSPHRASE)
_WEAK_RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=1024)
WEAK_PRIVATE_KEY = _pem(_WEAK_RSA_KEY)
ENCRYPTED_WEAK_PRIVATE_KEY = _pem(_WEAK_RSA_KEY, PASSPHRASE)
_RSA_NUMBERS = _RSA_KEY.private_numbers()
# Parses with RSA validation skipped, but fails cryptography's full consistency check.
CORRUPT_PRIVATE_KEY = _pem(rsa.RSAPrivateNumbers(
    _RSA_NUMBERS.p, _RSA_NUMBERS.q, _RSA_NUMBERS.d, _RSA_NUMBERS.dmp1 + 2, _RSA_NUMBERS.dmq1,
    _RSA_NUMBERS.iqmp, _RSA_NUMBERS.public_numbers,
).private_key(unsafe_skip_rsa_key_validation=True))
PUBLIC_KEY = _RSA_KEY.public_key().public_bytes(
    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
).decode()


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
        {'field_name': 'decrypted_private_key', 'value': PRIVATE_KEY},
        {'field_name': 'decrypted_private_key_passphrase', 'value': PASSPHRASE},
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
        A configuration using a self-signed assertion is only valid once a private key and an
        assertion audience are set.
        """
        missing, _ = self.config.is_valid
        assert 'private_key' not in missing['missing']

        self.config.auth_type = SAPAuthType.SELF_SIGNED_ASSERTION
        missing, _ = self.config.is_valid
        assert 'private_key' in missing['missing']

        self.config.decrypted_private_key = PRIVATE_KEY
        missing, _ = self.config.is_valid
        assert 'private_key' not in missing['missing']

        self.config.saml_assertion_audience = ''
        missing, _ = self.config.is_valid
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
        {'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION, 'expected_incorrect': ['sapsf_base_url']},
        {'auth_type': SAPAuthType.SAP_SIGNED_ASSERTION, 'expected_incorrect': []},
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

    @ddt.data(
        # accepts an unprotected key.
        {'private_key': PRIVATE_KEY, 'passphrase': ''},
        # accepts a passphrase-protected key with its passphrase.
        {'private_key': ENCRYPTED_PRIVATE_KEY, 'passphrase': PASSPHRASE},
    )
    @ddt.unpack
    def test_is_valid_accepts_loadable_private_key(self, private_key, passphrase):
        """
        An RSA private key that the configured passphrase (if any) unlocks is valid.
        """
        self.config.auth_type = SAPAuthType.SELF_SIGNED_ASSERTION
        self.config.decrypted_private_key = private_key
        self.config.decrypted_private_key_passphrase = passphrase

        missing, incorrect = self.config.is_valid
        assert not missing['missing']
        assert not incorrect['incorrect']

    @ddt.data(
        # rejects an invalid PEM.
        {'private_key': 'not a private key', 'passphrase': ''},
        # rejects a public key.
        {'private_key': PUBLIC_KEY, 'passphrase': ''},
        # rejects a passphrase-protected key without its passphrase.
        {'private_key': ENCRYPTED_PRIVATE_KEY, 'passphrase': ''},
        # rejects a passphrase-protected key with the wrong passphrase.
        {'private_key': ENCRYPTED_PRIVATE_KEY, 'passphrase': 'wrong-passphrase'},
        # rejects an unprotected key given a passphrase.
        {'private_key': PRIVATE_KEY, 'passphrase': PASSPHRASE},
        # rejects a non-RSA key, which cannot sign an RSA-SHA256 assertion.
        {'private_key': EC_PRIVATE_KEY, 'passphrase': ''},
        # rejects an under-2048-bit key, even one already stored and otherwise loadable -- the
        # path is_ready_to_transmit (via is_valid) re-checks on every sync, not just on submit.
        {'private_key': WEAK_PRIVATE_KEY, 'passphrase': ''},
    )
    @ddt.unpack
    def test_is_valid_rejects_unloadable_private_key(self, private_key, passphrase):
        """
        A private key that cannot be loaded as an RSA key with the configured passphrase is
        reported as incorrect, rather than failing later when an assertion is signed.
        """
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

    def test_is_ready_to_transmit_with_a_complete_configuration(self):
        """
        A complete configuration proceeds without logging.
        """
        with mock.patch('channel_integrations.sap_success_factors.models.LOGGER') as logger:
            assert self.config.is_ready_to_transmit('transmit_content_metadata') is True

        logger.warning.assert_not_called()

    def test_is_ready_to_transmit_ignores_an_overlong_display_name(self):
        """
        ``display_name`` is cosmetic, so reporting it must not take a working integration offline.
        """
        self.config.display_name = 'a-display-name-well-over-twenty-characters'

        _, incorrect = self.config.is_valid
        assert incorrect['incorrect'] == ['display_name']
        assert self.config.is_ready_to_transmit('transmit_content_metadata') is True

    def test_is_ready_to_transmit_passes_self_signed_assertion_with_secret(self):
        """
        A complete self-signed configuration, client secret included, proceeds.
        """
        self.config.auth_type = SAPAuthType.SELF_SIGNED_ASSERTION
        self.config.decrypted_private_key = PRIVATE_KEY

        assert self.config.is_ready_to_transmit('transmit_content_metadata') is True

    @ddt.data(
        {'changes': {'decrypted_key': ''}, 'expected_problems': 'missing: key'},
        {'changes': {'decrypted_secret': ''}, 'expected_problems': 'missing: secret'},
        {'changes': {'sapsf_base_url': 'not a url at all'}, 'expected_problems': 'invalid: sapsf_base_url'},
        {
            'changes': {'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION, 'decrypted_private_key': 'not a key'},
            'expected_problems': 'invalid: private_key',
        },
        {
            # A stored key under 2048 bits blocks syncs too, not just a malformed one -- the
            # 2048-bit floor applies on every re-check, not only when the key is first submitted.
            'changes': {'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION, 'decrypted_private_key': WEAK_PRIVATE_KEY},
            'expected_problems': 'invalid: private_key',
        },
        {
            'changes': {
                'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION,
                'decrypted_private_key': 'not a key',
                'saml_assertion_audience': '',
            },
            'expected_problems': 'missing: saml_assertion_audience; invalid: private_key',
        },
    )
    @ddt.unpack
    def test_is_ready_to_transmit_blocks_an_unusable_configuration(self, changes, expected_problems):
        """
        Any missing or invalid field other than ``display_name`` blocks the run, and is logged with
        missing and invalid fields kept apart.
        """
        for field_name, value in changes.items():
            setattr(self.config, field_name, value)

        with mock.patch('channel_integrations.sap_success_factors.models.LOGGER') as logger:
            assert self.config.is_ready_to_transmit('transmit_content_metadata') is False

        logged_message = logger.warning.call_args.args[0]
        assert 'transmit_content_metadata aborted' in logged_message
        assert f'({expected_problems})' in logged_message

    @ddt.data(
        {
            'entry_point': 'transmit_content_metadata',
            'exporter_getter': 'get_content_metadata_exporter',
            'errored_field': 'last_content_sync_errored_at',
            'untouched_field': 'last_learner_sync_errored_at',
        },
        {
            'entry_point': 'transmit_learner_data',
            'exporter_getter': 'get_learner_data_exporter',
            'errored_field': 'last_learner_sync_errored_at',
            'untouched_field': 'last_content_sync_errored_at',
        },
    )
    @ddt.unpack
    def test_blocked_sync_is_recorded_as_errored(self, entry_point, exporter_getter, errored_field, untouched_field):
        """
        A blocked sync shows as erroring now, rather than as a stale timestamp from its last real run.
        """
        self.config.decrypted_secret = ''
        before = localized_utcnow()

        with mock.patch.object(self.config, exporter_getter) as exporter:
            getattr(self.config, entry_point)(UserFactory())

        exporter.assert_not_called()
        self.config.refresh_from_db()
        assert self.config.last_sync_attempted_at >= before
        assert getattr(self.config, errored_field) >= before
        assert getattr(self.config, untouched_field) is None

    @ddt.data(
        {
            'toggle': 'disable_learner_data_transmissions',
            'entry_point': 'transmit_learner_data',
            'exporter_getter': 'get_learner_data_exporter',
            'errored_field': 'last_learner_sync_errored_at',
        },
        {
            'toggle': 'dry_run_mode_enabled',
            'entry_point': 'transmit_content_metadata',
            'exporter_getter': 'get_content_metadata_exporter',
            'errored_field': 'last_content_sync_errored_at',
        },
    )
    @ddt.unpack
    def test_gate_runs_ahead_of_transmitter_toggles(self, toggle, entry_point, exporter_getter, errored_field):
        """
        Both toggles are honoured inside the transmitters, so an unusable configuration is blocked and
        recorded as errored even when one of them is set.
        """
        setattr(self.config, toggle, True)
        self.config.decrypted_secret = ''

        with mock.patch.object(self.config, exporter_getter) as exporter:
            getattr(self.config, entry_point)(UserFactory())

        exporter.assert_not_called()
        self.config.refresh_from_db()
        assert getattr(self.config, errored_field) is not None

    def test_unlink_inactive_learners_runs_with_a_complete_configuration(self):
        """
        A complete configuration still unlinks inactive learners.
        """
        with mock.patch.object(self.config, 'get_learner_manger') as learner_manager:
            self.config.unlink_inactive_learners()

        learner_manager.return_value.unlink_learners.assert_called_once_with()

    def test_unlink_inactive_learners_is_gated(self):
        """
        Unlinking queries SAP, so an unusable configuration does no work, and leaves the sync timestamps
        alone because unlinking is not a sync cycle.
        """
        self.config.decrypted_secret = ''

        with mock.patch.object(self.config, 'get_learner_manger') as learner_manager:
            self.config.unlink_inactive_learners()

        learner_manager.assert_not_called()
        self.config.refresh_from_db()
        assert self.config.last_sync_attempted_at is None


@mark.django_db
@ddt.ddt
class TestGetCredentialErrors(unittest.TestCase):
    """
    Tests of ``SAPSuccessFactorsEnterpriseCustomerConfiguration.get_credential_errors``.
    """

    def setUp(self):
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

    @ddt.data(
        # self-signed, no key.
        {
            'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION, 'private_key': '',
            'private_key_passphrase': '', 'saml_assertion_audience': 'www.successfactors.com',
            'sapsf_base_url': 'https://sap.example.com',
            'expected_errors': {
                'decrypted_private_key': 'A private key is required when the auth type is self-signed.',
            },
        },
        # self-signed, no audience.
        {
            'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION, 'private_key': PRIVATE_KEY,
            'private_key_passphrase': '', 'saml_assertion_audience': '',
            'sapsf_base_url': 'https://sap.example.com',
            'expected_errors': {
                'saml_assertion_audience': 'A SAML assertion audience is required when the auth type is self-signed.',
            },
        },
        # self-signed, schemeless URL.
        {
            'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION, 'private_key': PRIVATE_KEY,
            'private_key_passphrase': '', 'saml_assertion_audience': 'www.successfactors.com',
            'sapsf_base_url': 'sap.example.com',
            'expected_errors': {
                'sapsf_base_url': 'Must be an absolute HTTPS URL when the auth type is self-signed.',
            },
        },
        # self-signed, blank URL -- is_valid_url('') is True, so this must be caught separately.
        {
            'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION, 'private_key': PRIVATE_KEY,
            'private_key_passphrase': '', 'saml_assertion_audience': 'www.successfactors.com',
            'sapsf_base_url': '',
            'expected_errors': {
                'sapsf_base_url': 'A SAP base URL is required when the auth type is self-signed.',
            },
        },
        # self-signed, everything valid.
        {
            'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION, 'private_key': PRIVATE_KEY,
            'private_key_passphrase': '', 'saml_assertion_audience': 'www.successfactors.com',
            'sapsf_base_url': 'https://sap.example.com', 'expected_errors': {},
        },
        # SAP-signed, schemeless URL is informational only -- must not block the save.
        {
            'auth_type': SAPAuthType.SAP_SIGNED_ASSERTION, 'private_key': '',
            'private_key_passphrase': '', 'saml_assertion_audience': '',
            'sapsf_base_url': 'sap.example.com', 'expected_errors': {},
        },
        # self-signed, wrong passphrase on an otherwise valid encrypted key.
        {
            'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION, 'private_key': ENCRYPTED_PRIVATE_KEY,
            'private_key_passphrase': 'wrong-passphrase', 'saml_assertion_audience': 'www.successfactors.com',
            'sapsf_base_url': 'https://sap.example.com',
            'expected_errors': {'decrypted_private_key_passphrase': 'Incorrect passphrase for this private key.'},
        },
        # self-signed, missing passphrase for an encrypted key.
        {
            'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION, 'private_key': ENCRYPTED_PRIVATE_KEY,
            'private_key_passphrase': '', 'saml_assertion_audience': 'www.successfactors.com',
            'sapsf_base_url': 'https://sap.example.com',
            'expected_errors': {
                'decrypted_private_key_passphrase': 'A passphrase is required to unlock this private key.',
            },
        },
        # garbage key with a leftover passphrase must not be blamed on the passphrase.
        {
            'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION, 'private_key': 'garbage text',
            'private_key_passphrase': 'stored-passphrase', 'saml_assertion_audience': 'www.successfactors.com',
            'sapsf_base_url': 'https://sap.example.com',
            'expected_errors': {'decrypted_private_key': 'Must be a PEM-encoded RSA private key.'},
        },
        # truncated PEM with a leftover passphrase: same as above.
        {
            'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION,
            'private_key': '-----BEGIN RSA PRIVATE KEY-----\nMIIEow==',
            'private_key_passphrase': 'stored-passphrase', 'saml_assertion_audience': 'www.successfactors.com',
            'sapsf_base_url': 'https://sap.example.com',
            'expected_errors': {'decrypted_private_key': 'Must be a PEM-encoded RSA private key.'},
        },
        # a public key pasted by mistake, with a leftover passphrase: same as above.
        {
            'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION, 'private_key': PUBLIC_KEY,
            'private_key_passphrase': 'stored-passphrase', 'saml_assertion_audience': 'www.successfactors.com',
            'sapsf_base_url': 'https://sap.example.com',
            'expected_errors': {'decrypted_private_key': 'Must be a PEM-encoded RSA private key.'},
        },
        # weak unencrypted key with a leftover passphrase: key size wins over the passphrase.
        {
            'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION, 'private_key': WEAK_PRIVATE_KEY,
            'private_key_passphrase': 'stored-passphrase', 'saml_assertion_audience': 'www.successfactors.com',
            'sapsf_base_url': 'https://sap.example.com',
            'expected_errors': {'decrypted_private_key': 'RSA key must be at least 2048 bits.'},
        },
        # weak encrypted key with the correct passphrase: key size wins over the passphrase.
        {
            'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION, 'private_key': ENCRYPTED_WEAK_PRIVATE_KEY,
            'private_key_passphrase': PASSPHRASE, 'saml_assertion_audience': 'www.successfactors.com',
            'sapsf_base_url': 'https://sap.example.com',
            'expected_errors': {'decrypted_private_key': 'RSA key must be at least 2048 bits.'},
        },
        # encrypted EC key with the correct passphrase: not-RSA wins over the passphrase.
        {
            'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION, 'private_key': ENCRYPTED_EC_PRIVATE_KEY,
            'private_key_passphrase': PASSPHRASE, 'saml_assertion_audience': 'www.successfactors.com',
            'sapsf_base_url': 'https://sap.example.com',
            'expected_errors': {'decrypted_private_key': 'Not an RSA private key.'},
        },
        # encrypted EC key with the wrong passphrase: the passphrase problem surfaces first --
        # fixing it would then reveal the key isn't RSA either, but one error at a time.
        {
            'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION, 'private_key': ENCRYPTED_EC_PRIVATE_KEY,
            'private_key_passphrase': 'wrong-passphrase', 'saml_assertion_audience': 'www.successfactors.com',
            'sapsf_base_url': 'https://sap.example.com',
            'expected_errors': {'decrypted_private_key_passphrase': 'Incorrect passphrase for this private key.'},
        },
        # unencrypted key with an unnecessary leftover passphrase.
        {
            'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION, 'private_key': PRIVATE_KEY,
            'private_key_passphrase': 'leftover-passphrase', 'saml_assertion_audience': 'www.successfactors.com',
            'sapsf_base_url': 'https://sap.example.com',
            'expected_errors': {'decrypted_private_key': "This private key doesn't use a passphrase."},
        },
        # well-formed but internally inconsistent RSA key: rejected by the full consistency check.
        {
            'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION, 'private_key': CORRUPT_PRIVATE_KEY,
            'private_key_passphrase': '', 'saml_assertion_audience': 'www.successfactors.com',
            'sapsf_base_url': 'https://sap.example.com',
            'expected_errors': {'decrypted_private_key': 'Must be a PEM-encoded RSA private key.'},
        },
        # weak unencrypted key, no passphrase involved at all.
        {
            'auth_type': SAPAuthType.SELF_SIGNED_ASSERTION, 'private_key': WEAK_PRIVATE_KEY,
            'private_key_passphrase': '', 'saml_assertion_audience': 'www.successfactors.com',
            'sapsf_base_url': 'https://sap.example.com',
            'expected_errors': {'decrypted_private_key': 'RSA key must be at least 2048 bits.'},
        },
        # SAP-signed, newly submitted malformed key is still rejected.
        {
            'auth_type': SAPAuthType.SAP_SIGNED_ASSERTION, 'private_key': 'not-a-pem-key',
            'private_key_passphrase': '', 'saml_assertion_audience': '',
            'sapsf_base_url': 'https://sap.example.com',
            'expected_errors': {'decrypted_private_key': 'Must be a PEM-encoded RSA private key.'},
        },
    )
    @ddt.unpack
    def test_get_credential_errors(
        self, auth_type, private_key, private_key_passphrase, saml_assertion_audience, sapsf_base_url,
        expected_errors,
    ):
        errors = self.config.get_credential_errors(
            auth_type=auth_type,
            private_key=private_key,
            private_key_passphrase=private_key_passphrase,
            saml_assertion_audience=saml_assertion_audience,
            sapsf_base_url=sapsf_base_url,
        )
        assert errors == expected_errors

    def test_sap_signed_unchanged_malformed_stored_key_is_not_re_validated(self):
        """
        Regression: re-validating an unchanged leftover key on every save of a non-self-signed
        candidate would block every future save of a config whose key predates a validation rule
        (e.g. one saved before the 2048-bit minimum existed) -- not just the save that introduced
        it. An unchanged key/passphrase is skipped regardless of auth_type; only a newly submitted
        one is checked.
        """
        self.config.decrypted_private_key = 'not-a-pem-key'
        self.config.save()

        errors = self.config.get_credential_errors(
            auth_type=SAPAuthType.SAP_SIGNED_ASSERTION,
            private_key='not-a-pem-key',
            private_key_passphrase='',
            saml_assertion_audience='',
            sapsf_base_url='https://sap.example.com',
        )
        assert not errors

    def test_self_signed_unchanged_valid_key_skips_redundant_full_validation(self):
        """
        An unchanged, already-valid self-signed key/passphrase must not trip up the full
        validation path -- it was already validated in full when first submitted.
        """
        self.config.auth_type = SAPAuthType.SELF_SIGNED_ASSERTION
        self.config.decrypted_private_key = PRIVATE_KEY
        self.config.saml_assertion_audience = 'www.successfactors.com'
        self.config.save()

        errors = self.config.get_credential_errors(
            auth_type=SAPAuthType.SELF_SIGNED_ASSERTION,
            private_key=PRIVATE_KEY,
            private_key_passphrase='',
            saml_assertion_audience='www.successfactors.com',
            sapsf_base_url='https://sap.example.com',
        )
        assert not errors
