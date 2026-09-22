"""
Generate self-signed SAML assertions for SAP SuccessFactors OAuth bearer authentication.

Not yet called anywhere: ENT-12305 will use this from
``SAPSuccessFactorsAPIClient.get_oauth_access_token`` for customers configured for
self-signed assertion auth.
"""

import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import signxml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from lxml import etree

SAML_ASSERTION_NAMESPACE = 'urn:oasis:names:tc:SAML:2.0:assertion'
XMLDSIG_NAMESPACE = 'http://www.w3.org/2000/09/xmldsig#'
XSI_NAMESPACE = 'http://www.w3.org/2001/XMLSchema-instance'
XSD_NAMESPACE = 'http://www.w3.org/2001/XMLSchema'
SAML_AUTHN_CONTEXT_UNSPECIFIED = 'urn:oasis:names:tc:SAML:2.0:ac:classes:unspecified'
CLOCK_SKEW_TOLERANCE_MINUTES = 5
SAML_TAG_PREFIX = f'{{{SAML_ASSERTION_NAMESPACE}}}'
XMLDSIG_TAG_PREFIX = f'{{{XMLDSIG_NAMESPACE}}}'
XSI_TYPE_ATTRIB = f'{{{XSI_NAMESPACE}}}type'

# SAP SuccessFactors requires the API key (client_id) to appear as this AttributeStatement
# attribute, in addition to the Issuer; see "Generating a SAML Assertion" in the SAP
# SuccessFactors OData v2 API reference guide.
SAML_API_KEY_ATTRIBUTE_NAME = 'api_key'

# signxml hardcodes this exact value: it locates the unsigned <ds:Signature> element to
# replace via the XPath `Signature[@Id='placeholder']`, so this string must not change.
UNSIGNED_SIGNATURE_ELEMENT_ID = 'placeholder'


class SAMLAssertionGenerationError(Exception):
    """
    Raised when SAML assertion construction or signing fails.
    """


class InvalidPrivateKeyError(SAMLAssertionGenerationError):
    """
    Raised when the provided RSA private key is malformed or invalid.
    """


class InvalidAssertionParameterError(SAMLAssertionGenerationError):
    """
    Raised when a required SAML assertion parameter is missing or malformed.
    """


def _validate_assertion_parameters(client_id: str, user_id: str, audience: str, token_url: str) -> None:
    """
    Validate the parameters that populate schema-required SAML assertion fields.

    SAML 2.0 requires non-empty ``Issuer``, ``NameID``, and ``Audience`` values, and the
    ``Recipient`` attribute must be a URI; SAP SuccessFactors' OAuth token endpoint is always
    HTTPS, so an https URL is required here too.
    """
    for name, value in (
        ('client_id', client_id),
        ('user_id', user_id),
        ('audience', audience),
        ('token_url', token_url),
    ):
        if not value or not value.strip():
            raise InvalidAssertionParameterError(f'{name} must be a non-empty string.')

    parsed_token_url = urlparse(token_url)
    if parsed_token_url.scheme != 'https' or not parsed_token_url.netloc:
        raise InvalidAssertionParameterError('token_url must be an absolute HTTPS URL.')


def _load_rsa_private_key(
    private_key_pem: str,
    private_key_passphrase: str | None = None,
) -> rsa.RSAPrivateKey:
    """
    Parse and validate the RSA private key used to sign the assertion.

    Returns the parsed key after verifying that the PEM contains an RSA private key.
    """
    try:
        passphrase_bytes = private_key_passphrase.encode('utf-8') if private_key_passphrase else None
        key = serialization.load_pem_private_key(
            private_key_pem.encode('utf-8'),
            password=passphrase_bytes,
        )
    except (TypeError, ValueError) as exc:
        # The underlying error can quote fragments of the key/passphrase input, so it is
        # deliberately not included in the raised message; the original exception is still
        # available via `__cause__` for logging.
        raise InvalidPrivateKeyError('Failed to load RSA private key: invalid PEM data or passphrase.') from exc

    if not isinstance(key, rsa.RSAPrivateKey):
        raise InvalidPrivateKeyError('Provided key is not an RSA private key.')

    return key


def _build_saml_assertion(
    client_id: str,
    user_id: str,
    audience_value: str,
    token_url: str,
    issue_instant: datetime,
    not_before: datetime,
    not_on_or_after: datetime,
    assertion_id: str,
) -> etree._Element:
    """
    Construct the unsigned SAML 2.0 assertion XML tree in schema-valid element order.
    """
    issue_instant_str = issue_instant.strftime('%Y-%m-%dT%H:%M:%SZ')
    not_before_str = not_before.strftime('%Y-%m-%dT%H:%M:%SZ')
    not_on_or_after_str = not_on_or_after.strftime('%Y-%m-%dT%H:%M:%SZ')

    assertion = etree.Element(
        f'{SAML_TAG_PREFIX}Assertion',
        attrib={
            'ID': assertion_id,
            'Version': '2.0',
            'IssueInstant': issue_instant_str,
        },
        nsmap={
            'ds': XMLDSIG_NAMESPACE,
            'saml': SAML_ASSERTION_NAMESPACE,
            'xsi': XSI_NAMESPACE,
            'xs': XSD_NAMESPACE,
        },
    )

    issuer = etree.SubElement(assertion, f'{SAML_TAG_PREFIX}Issuer')
    issuer.text = client_id

    # signxml replaces this placeholder in-place, which keeps the Signature immediately after
    # the Issuer as required by the SAML assertion schema.
    etree.SubElement(
        assertion, f'{XMLDSIG_TAG_PREFIX}Signature', attrib={'Id': UNSIGNED_SIGNATURE_ELEMENT_ID},
    )

    subject = etree.SubElement(assertion, f'{SAML_TAG_PREFIX}Subject')
    name_id = etree.SubElement(
        subject,
        f'{SAML_TAG_PREFIX}NameID',
        attrib={'Format': 'urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified'},
    )
    name_id.text = user_id

    subject_confirmation = etree.SubElement(
        subject,
        f'{SAML_TAG_PREFIX}SubjectConfirmation',
        attrib={'Method': 'urn:oasis:names:tc:SAML:2.0:cm:bearer'},
    )
    etree.SubElement(
        subject_confirmation,
        f'{SAML_TAG_PREFIX}SubjectConfirmationData',
        attrib={'Recipient': token_url, 'NotOnOrAfter': not_on_or_after_str},
    )

    conditions = etree.SubElement(
        assertion,
        f'{SAML_TAG_PREFIX}Conditions',
        attrib={'NotBefore': not_before_str, 'NotOnOrAfter': not_on_or_after_str},
    )
    audience_restriction = etree.SubElement(conditions, f'{SAML_TAG_PREFIX}AudienceRestriction')
    audience = etree.SubElement(audience_restriction, f'{SAML_TAG_PREFIX}Audience')
    audience.text = audience_value

    authn_statement = etree.SubElement(
        assertion,
        f'{SAML_TAG_PREFIX}AuthnStatement',
        attrib={
            'AuthnInstant': issue_instant_str,
            'SessionIndex': assertion_id,
        },
    )
    authn_context = etree.SubElement(authn_statement, f'{SAML_TAG_PREFIX}AuthnContext')
    authn_context_class_ref = etree.SubElement(authn_context, f'{SAML_TAG_PREFIX}AuthnContextClassRef')
    authn_context_class_ref.text = SAML_AUTHN_CONTEXT_UNSPECIFIED

    attribute_statement = etree.SubElement(assertion, f'{SAML_TAG_PREFIX}AttributeStatement')
    attribute = etree.SubElement(
        attribute_statement, f'{SAML_TAG_PREFIX}Attribute', attrib={'Name': SAML_API_KEY_ATTRIBUTE_NAME},
    )
    attribute_value = etree.SubElement(
        attribute, f'{SAML_TAG_PREFIX}AttributeValue', attrib={XSI_TYPE_ATTRIB: 'xs:string'},
    )
    attribute_value.text = client_id

    return assertion


def generate_saml_assertion(
    *,
    client_id: str,
    user_id: str,
    audience: str,
    token_url: str,
    private_key_pem: str,
    private_key_passphrase: str | None = None,
    validity_minutes: int = 10,
) -> str:
    """
    Construct and digitally sign a SAML 2.0 XML assertion for SAP SuccessFactors.

    Args:
        client_id: The OAuth client ID (Issuer).
        user_id: The API user identifier (Subject NameID).
        audience: The SAML audience restriction value expected by SAP SuccessFactors.
        token_url: The OAuth token endpoint URL that receives the bearer assertion.
        private_key_pem: PEM-encoded RSA private key string used for signing.
        private_key_passphrase: Optional passphrase for the encrypted private key.
        validity_minutes: Duration in minutes for which the assertion is valid.

    Returns:
        str: Signed SAML 2.0 XML assertion string.

    Raises:
        InvalidAssertionParameterError: If client_id, user_id, audience, or token_url is
            missing, if token_url is not an absolute HTTPS URL, or if validity_minutes is
            not a positive integer.
        InvalidPrivateKeyError: If the private key is malformed, unparseable, or invalid.
        SAMLAssertionGenerationError: If assertion building or signing fails.
    """
    _validate_assertion_parameters(
        client_id=client_id, user_id=user_id, audience=audience, token_url=token_url,
    )
    if validity_minutes < 1:
        raise InvalidAssertionParameterError('validity_minutes must be a positive integer.')
    private_key = _load_rsa_private_key(private_key_pem, private_key_passphrase)

    now = datetime.now(timezone.utc)
    not_before = now - timedelta(minutes=CLOCK_SKEW_TOLERANCE_MINUTES)
    not_on_or_after = now + timedelta(minutes=validity_minutes)
    assertion_id = f'_{uuid.uuid4()}'

    assertion = _build_saml_assertion(
        client_id=client_id,
        user_id=user_id,
        audience_value=audience,
        token_url=token_url,
        issue_instant=now,
        not_before=not_before,
        not_on_or_after=not_on_or_after,
        assertion_id=assertion_id,
    )

    try:
        signer = signxml.XMLSigner(
            method=signxml.methods.enveloped,
            signature_algorithm='rsa-sha256',
            digest_algorithm='sha256',
            # SAML verifiers expect exclusive c14n; signxml would otherwise default to Canonical XML 1.1.
            c14n_algorithm=(
                signxml.algorithms.CanonicalizationMethod.EXCLUSIVE_XML_CANONICALIZATION_1_0
            ),
        )
        signed_assertion = signer.sign(
            assertion,
            key=private_key,
        )
        return etree.tostring(signed_assertion, encoding='utf-8').decode('utf-8')
    except Exception as exc:
        # signxml/lxml internals raise a wide variety of exception types here, so this stays
        # broad; the message omits str(exc) since it can echo fragments of the signed XML
        # (which embeds the assertion's key material context), and the original exception is
        # still available via `__cause__` for logging.
        raise SAMLAssertionGenerationError('XML-DSig signing failed.') from exc
