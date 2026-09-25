"""
Tests for the standalone SAML 2.0 XML-DSig assertion generator.
"""

import unittest
from unittest import mock

import ddt
import lxml.etree
import signxml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from freezegun import freeze_time

from channel_integrations.sap_success_factors.saml import (
    CLOCK_SKEW_TOLERANCE_MINUTES,
    SAML_API_KEY_ATTRIBUTE_NAME,
    SAML_AUTHN_CONTEXT_UNSPECIFIED,
    InvalidAssertionParameterError,
    InvalidPrivateKeyError,
    SAMLAssertionGenerationError,
    generate_saml_assertion,
)

SAML_NS = {'saml': 'urn:oasis:names:tc:SAML:2.0:assertion'}
XSI_NS = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance'}
DS_SIGNATURE_TAG = '{http://www.w3.org/2000/09/xmldsig#}Signature'

# The generator embeds the RSA public key as a <ds:KeyValue> rather than an X.509 certificate,
# so verification must be told not to require a certificate-based <ds:X509Data> KeyInfo.
NO_X509_REQUIRED = signxml.verifier.SignatureConfiguration(require_x509=False)


def _generate_rsa_private_key_pem(passphrase=None):
    """
    Return a throwaway, test-only RSA private key PEM string, optionally passphrase-encrypted.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    encryption = (
        serialization.BestAvailableEncryption(passphrase.encode('utf-8'))
        if passphrase else serialization.NoEncryption()
    )
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=encryption,
    ).decode('utf-8')


@ddt.ddt
class TestGenerateSAMLAssertion(unittest.TestCase):
    """
    Tests for ``generate_saml_assertion``.
    """

    def setUp(self):
        super().setUp()
        self.client_id = 'test-client-id'
        self.user_id = 'test-api-user@example.com'
        self.audience = 'www.successfactors.com'
        self.token_url = 'https://api.successfactors.com/oauth/token'
        self.private_key_pem = _generate_rsa_private_key_pem()

    def _generate_saml_assertion(self, **overrides):
        """
        Call ``generate_saml_assertion`` with this test case's default parameters, overriding
        any of them with the keyword arguments passed in.
        """
        params = {
            'client_id': self.client_id,
            'user_id': self.user_id,
            'audience': self.audience,
            'token_url': self.token_url,
            'private_key_pem': self.private_key_pem,
        }
        params.update(overrides)
        return generate_saml_assertion(**params)

    def test_returns_signed_and_verifiable_assertion(self):
        assertion_xml = self._generate_saml_assertion()

        parsed = lxml.etree.fromstring(assertion_xml.encode('utf-8'))
        self.assertEqual(parsed.tag, '{urn:oasis:names:tc:SAML:2.0:assertion}Assertion')
        self.assertIsNotNone(parsed.find(DS_SIGNATURE_TAG))

        verified = signxml.XMLVerifier().verify(assertion_xml, expect_config=NO_X509_REQUIRED)
        self.assertIsNotNone(verified.signed_xml)

    def test_assertion_contains_expected_saml_fields(self):
        assertion_xml = self._generate_saml_assertion()
        parsed = lxml.etree.fromstring(assertion_xml.encode('utf-8'))

        self.assertEqual(parsed.findtext('saml:Issuer', namespaces=SAML_NS), self.client_id)
        self.assertEqual(
            parsed.findtext('saml:Subject/saml:NameID', namespaces=SAML_NS), self.user_id,
        )
        self.assertEqual(
            parsed.find('saml:Conditions/saml:AudienceRestriction/saml:Audience', namespaces=SAML_NS).text,
            self.audience,
        )
        subject_confirmation_data = parsed.find(
            'saml:Subject/saml:SubjectConfirmation/saml:SubjectConfirmationData', namespaces=SAML_NS,
        )
        self.assertEqual(subject_confirmation_data.get('Recipient'), self.token_url)
        self.assertEqual(
            parsed.findtext(
                'saml:AuthnStatement/saml:AuthnContext/saml:AuthnContextClassRef',
                namespaces=SAML_NS,
            ),
            SAML_AUTHN_CONTEXT_UNSPECIFIED,
        )
        self.assertTrue(parsed.get('ID').startswith('_'))
        self.assertEqual(parsed.get('Version'), '2.0')

    def test_assertion_contains_api_key_attribute_statement(self):
        assertion_xml = self._generate_saml_assertion()
        parsed = lxml.etree.fromstring(assertion_xml.encode('utf-8'))

        attribute = parsed.find(
            f"saml:AttributeStatement/saml:Attribute[@Name='{SAML_API_KEY_ATTRIBUTE_NAME}']",
            namespaces=SAML_NS,
        )
        self.assertIsNotNone(attribute)
        attribute_value = attribute.find('saml:AttributeValue', namespaces=SAML_NS)
        self.assertEqual(attribute_value.text, self.client_id)
        self.assertEqual(attribute_value.get(f'{{{XSI_NS["xsi"]}}}type'), 'xs:string')

    def test_signature_is_inserted_immediately_after_issuer(self):
        assertion_xml = self._generate_saml_assertion()

        parsed = lxml.etree.fromstring(assertion_xml.encode('utf-8'))
        child_tags = [child.tag for child in parsed]
        self.assertEqual(child_tags[:4], [
            '{urn:oasis:names:tc:SAML:2.0:assertion}Issuer',
            DS_SIGNATURE_TAG,
            '{urn:oasis:names:tc:SAML:2.0:assertion}Subject',
            '{urn:oasis:names:tc:SAML:2.0:assertion}Conditions',
        ])

    @freeze_time('2026-01-01 12:00:00')
    def test_timestamps_reflect_validity_window(self):
        assertion_xml = self._generate_saml_assertion(validity_minutes=15)
        parsed = lxml.etree.fromstring(assertion_xml.encode('utf-8'))

        conditions = parsed.find('saml:Conditions', namespaces=SAML_NS)
        self.assertEqual(parsed.get('IssueInstant'), '2026-01-01T12:00:00Z')
        self.assertEqual(
            conditions.get('NotBefore'),
            f'2026-01-01T11:{60 - CLOCK_SKEW_TOLERANCE_MINUTES:02d}:00Z',
        )
        self.assertEqual(conditions.get('NotOnOrAfter'), '2026-01-01T12:15:00Z')

    def test_encrypted_private_key_with_correct_passphrase_succeeds(self):
        encrypted_key_pem = _generate_rsa_private_key_pem(passphrase='correct-horse')
        assertion_xml = self._generate_saml_assertion(
            private_key_pem=encrypted_key_pem, private_key_passphrase='correct-horse',
        )
        verified = signxml.XMLVerifier().verify(assertion_xml, expect_config=NO_X509_REQUIRED)
        self.assertIsNotNone(verified.signed_xml)

    def test_encrypted_private_key_with_incorrect_passphrase_raises(self):
        encrypted_key_pem = _generate_rsa_private_key_pem(passphrase='correct-horse')
        with self.assertRaises(InvalidPrivateKeyError):
            self._generate_saml_assertion(
                private_key_pem=encrypted_key_pem, private_key_passphrase='wrong-passphrase',
            )

    def test_malformed_private_key_raises_invalid_private_key_error(self):
        with self.assertRaises(InvalidPrivateKeyError):
            self._generate_saml_assertion(private_key_pem='not-a-valid-pem-key')

    def test_non_rsa_private_key_raises_invalid_private_key_error(self):
        ec_key = ec.generate_private_key(ec.SECP256R1())
        ec_key_pem = ec_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode('utf-8')

        with self.assertRaises(InvalidPrivateKeyError):
            self._generate_saml_assertion(private_key_pem=ec_key_pem)

    def test_tampered_assertion_fails_signature_verification(self):
        assertion_xml = self._generate_saml_assertion()
        parsed = lxml.etree.fromstring(assertion_xml.encode('utf-8'))
        parsed.find('saml:Issuer', namespaces=SAML_NS).text = 'tampered-client-id'
        tampered_xml = lxml.etree.tostring(parsed)

        with self.assertRaises(signxml.exceptions.InvalidSignature):
            signxml.XMLVerifier().verify(tampered_xml, expect_config=NO_X509_REQUIRED)

    def test_signing_failure_raises_saml_assertion_generation_error(self):
        with mock.patch.object(signxml.XMLSigner, 'sign', side_effect=ValueError('boom')):
            with self.assertRaises(SAMLAssertionGenerationError):
                self._generate_saml_assertion()

    def test_empty_client_id_raises_invalid_assertion_parameter_error(self):
        with self.assertRaises(InvalidAssertionParameterError):
            self._generate_saml_assertion(client_id='')

    def test_blank_user_id_raises_invalid_assertion_parameter_error(self):
        with self.assertRaises(InvalidAssertionParameterError):
            self._generate_saml_assertion(user_id='   ')

    def test_missing_audience_raises_invalid_assertion_parameter_error(self):
        with self.assertRaises(InvalidAssertionParameterError):
            self._generate_saml_assertion(audience=None)

    def test_non_https_token_url_raises_invalid_assertion_parameter_error(self):
        with self.assertRaises(InvalidAssertionParameterError):
            self._generate_saml_assertion(token_url='http://api.successfactors.com/oauth/token')

    def test_malformed_token_url_raises_invalid_assertion_parameter_error(self):
        with self.assertRaises(InvalidAssertionParameterError):
            self._generate_saml_assertion(token_url='not-a-url')

    @ddt.data(0, -5)
    def test_non_positive_validity_minutes_raises_invalid_assertion_parameter_error(self, validity_minutes):
        with self.assertRaises(InvalidAssertionParameterError):
            self._generate_saml_assertion(validity_minutes=validity_minutes)
