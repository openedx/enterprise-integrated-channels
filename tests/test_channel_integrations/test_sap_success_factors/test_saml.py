"""
Tests for the standalone SAML 2.0 XML-DSig assertion generator.
"""

import unittest
from unittest import mock

import lxml.etree
import signxml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from freezegun import freeze_time

from channel_integrations.sap_success_factors.saml import (
    InvalidPrivateKeyError,
    SAMLAssertionGenerationError,
    generate_saml_assertion,
)

SAML_NS = {'saml': 'urn:oasis:names:tc:SAML:2.0:assertion'}
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


class TestGenerateSAMLAssertion(unittest.TestCase):
    """
    Tests for ``generate_saml_assertion``.
    """

    def setUp(self):
        super().setUp()
        self.client_id = 'test-client-id'
        self.user_id = 'test-api-user@example.com'
        self.token_url = 'https://api.successfactors.com/oauth/token'
        self.private_key_pem = _generate_rsa_private_key_pem()

    def test_returns_signed_and_verifiable_assertion(self):
        assertion_xml = generate_saml_assertion(
            self.client_id, self.user_id, self.token_url, self.private_key_pem,
        )

        parsed = lxml.etree.fromstring(assertion_xml.encode('utf-8'))
        self.assertEqual(parsed.tag, '{urn:oasis:names:tc:SAML:2.0:assertion}Assertion')
        self.assertIsNotNone(parsed.find(DS_SIGNATURE_TAG))

        verified = signxml.XMLVerifier().verify(assertion_xml, expect_config=NO_X509_REQUIRED)
        self.assertIsNotNone(verified.signed_xml)

    def test_assertion_contains_expected_saml_fields(self):
        assertion_xml = generate_saml_assertion(
            self.client_id, self.user_id, self.token_url, self.private_key_pem,
        )
        parsed = lxml.etree.fromstring(assertion_xml.encode('utf-8'))

        self.assertEqual(parsed.findtext('saml:Issuer', namespaces=SAML_NS), self.client_id)
        self.assertEqual(
            parsed.findtext('saml:Subject/saml:NameID', namespaces=SAML_NS), self.user_id,
        )
        self.assertEqual(
            parsed.find('saml:Conditions/saml:AudienceRestriction/saml:Audience', namespaces=SAML_NS).text,
            self.token_url,
        )
        subject_confirmation_data = parsed.find(
            'saml:Subject/saml:SubjectConfirmation/saml:SubjectConfirmationData', namespaces=SAML_NS,
        )
        self.assertEqual(subject_confirmation_data.get('Recipient'), self.token_url)
        self.assertTrue(parsed.get('ID').startswith('_'))
        self.assertEqual(parsed.get('Version'), '2.0')

    @freeze_time('2026-01-01 12:00:00')
    def test_timestamps_reflect_validity_window(self):
        assertion_xml = generate_saml_assertion(
            self.client_id, self.user_id, self.token_url, self.private_key_pem, validity_minutes=15,
        )
        parsed = lxml.etree.fromstring(assertion_xml.encode('utf-8'))

        conditions = parsed.find('saml:Conditions', namespaces=SAML_NS)
        self.assertEqual(parsed.get('IssueInstant'), '2026-01-01T12:00:00Z')
        self.assertEqual(conditions.get('NotBefore'), '2026-01-01T11:59:00Z')
        self.assertEqual(conditions.get('NotOnOrAfter'), '2026-01-01T12:15:00Z')

    def test_encrypted_private_key_with_correct_passphrase_succeeds(self):
        encrypted_key_pem = _generate_rsa_private_key_pem(passphrase='correct-horse')
        assertion_xml = generate_saml_assertion(
            self.client_id, self.user_id, self.token_url, encrypted_key_pem,
            private_key_passphrase='correct-horse',
        )
        verified = signxml.XMLVerifier().verify(assertion_xml, expect_config=NO_X509_REQUIRED)
        self.assertIsNotNone(verified.signed_xml)

    def test_encrypted_private_key_with_incorrect_passphrase_raises(self):
        encrypted_key_pem = _generate_rsa_private_key_pem(passphrase='correct-horse')
        with self.assertRaises(InvalidPrivateKeyError):
            generate_saml_assertion(
                self.client_id, self.user_id, self.token_url, encrypted_key_pem,
                private_key_passphrase='wrong-passphrase',
            )

    def test_malformed_private_key_raises_invalid_private_key_error(self):
        with self.assertRaises(InvalidPrivateKeyError):
            generate_saml_assertion(
                self.client_id, self.user_id, self.token_url, 'not-a-valid-pem-key',
            )

    def test_non_rsa_private_key_raises_invalid_private_key_error(self):
        ec_key = ec.generate_private_key(ec.SECP256R1())
        ec_key_pem = ec_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode('utf-8')

        with self.assertRaises(InvalidPrivateKeyError):
            generate_saml_assertion(self.client_id, self.user_id, self.token_url, ec_key_pem)

    def test_tampered_assertion_fails_signature_verification(self):
        assertion_xml = generate_saml_assertion(
            self.client_id, self.user_id, self.token_url, self.private_key_pem,
        )
        parsed = lxml.etree.fromstring(assertion_xml.encode('utf-8'))
        parsed.find('saml:Issuer', namespaces=SAML_NS).text = 'tampered-client-id'
        tampered_xml = lxml.etree.tostring(parsed)

        with self.assertRaises(signxml.exceptions.InvalidSignature):
            signxml.XMLVerifier().verify(tampered_xml, expect_config=NO_X509_REQUIRED)

    def test_signing_failure_raises_saml_assertion_generation_error(self):
        with mock.patch.object(signxml.XMLSigner, 'sign', side_effect=ValueError('boom')):
            with self.assertRaises(SAMLAssertionGenerationError):
                generate_saml_assertion(
                    self.client_id, self.user_id, self.token_url, self.private_key_pem,
                )
