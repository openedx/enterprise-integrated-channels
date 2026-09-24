"""
Database models for Enterprise Integrated Channel SAP SuccessFactors.
"""

import json
from collections.abc import Callable
from datetime import datetime
from logging import getLogger
from urllib.parse import urlparse

from config_models.models import ConfigurationModel
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from django.conf import settings
from django.db import models
from django.utils.encoding import force_bytes, force_str
from django.utils.translation import gettext_lazy as _
from enterprise.models import EnterpriseCustomer
from enterprise.utils import localized_utcnow
from fernet_fields import EncryptedCharField, EncryptedTextField

from channel_integrations.exceptions import ClientError
from channel_integrations.integrated_channel.models import (
    EnterpriseCustomerPluginConfiguration,
    LearnerDataTransmissionAudit,
)
from channel_integrations.sap_success_factors.exporters.content_metadata import SapSuccessFactorsContentMetadataExporter
from channel_integrations.sap_success_factors.exporters.learner_data import (
    SapSuccessFactorsLearnerExporter,
    SapSuccessFactorsLearnerManger,
)
from channel_integrations.sap_success_factors.transmitters.content_metadata import (
    SapSuccessFactorsContentMetadataTransmitter,
)
from channel_integrations.sap_success_factors.transmitters.learner_data import SapSuccessFactorsLearnerTransmitter
from channel_integrations.utils import convert_comma_separated_string_to_list, generate_formatted_log, is_valid_url

LOGGER = getLogger(__name__)


class SAPSuccessFactorsGlobalConfiguration(ConfigurationModel):
    """
    The global configuration for integrating with SuccessFactors.

    .. no_pii:
    """

    completion_status_api_path = models.CharField(max_length=255)
    course_api_path = models.CharField(max_length=255)
    oauth_api_path = models.CharField(max_length=255)
    search_student_api_path = models.CharField(max_length=255)
    provider_id = models.CharField(max_length=100, default='EDX')
    oauth_token_api_path = models.CharField(
        max_length=255,
        blank=True,
        default='/oauth/token',
        verbose_name="OAuth Token API Path",
        help_text=_(
            "Path, relative to a customer's SAP base URL, of the endpoint that exchanges a SAML "
            "bearer assertion for an access token."
        )
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        editable=False,
        null=True,
        on_delete=models.PROTECT,
        # Translators: this label indicates the name of the user who made this change:
        verbose_name=_("Changed by"),
        related_name='sapsf_global_configuration_changed_by'
    )

    class Meta:
        app_label = 'sap_success_factors_channel'

    def __str__(self):
        """
        Return a human-readable string representation of the object.
        """
        return "<SAPSuccessFactorsGlobalConfiguration with id {id}>".format(id=self.id)

    def __repr__(self):
        """
        Return uniquely identifying string representation.
        """
        return self.__str__()


class SAPAuthType(models.TextChoices):
    """
    How the SAML bearer assertion sent to a customer's token endpoint gets signed.
    """
    SAP_SIGNED_ASSERTION = 'sap_signed_assertion', _('SAP-signed SAML assertion (SAP IdP API + client secret)')
    SELF_SIGNED_ASSERTION = 'self_signed_assertion', _('Self-signed SAML assertion (our private key)')


class SAPSuccessFactorsEnterpriseCustomerConfiguration(EnterpriseCustomerPluginConfiguration):
    """
    The Enterprise-specific configuration we need for integrating with SuccessFactors.

    .. no_pii:
    """

    # Problems reported by ``is_valid`` that do not stop SAP being reached, so do not block a sync.
    COSMETIC_CONFIG_PROBLEMS = frozenset({'display_name'})

    USER_TYPE_USER = 'user'
    USER_TYPE_ADMIN = 'admin'

    USER_TYPE_CHOICES = (
        (USER_TYPE_USER, 'User'),
        (USER_TYPE_ADMIN, 'Admin'),
    )

    # TODO: Remove this override when we switch to enterprise-integrated-channels completely
    enterprise_customer = models.ForeignKey(
        EnterpriseCustomer,
        related_name='sapsf_enterprisecustomerpluginconfiguration',
        blank=False,
        null=False,
        help_text=_("Enterprise Customer associated with the configuration."),
        on_delete=models.deletion.CASCADE
    )

    decrypted_key = EncryptedCharField(
        max_length=255,
        verbose_name="Encrypted Client ID",
        blank=True,
        default='',
        help_text=_(
            "The encrypted OAuth client identifier."
            " It will be encrypted when stored in the database."
        ),
        null=True
    )

    @property
    def encrypted_key(self):
        """
        Return encrypted key as a string.
        The data is encrypted in the DB at rest, but is unencrypted in the app when retrieved through the
        decrypted_key field. This method will encrypt the key again before sending.
        """
        if self.decrypted_key:
            return force_str(
                self._meta.get_field('decrypted_key').fernet.encrypt(
                    force_bytes(self.decrypted_key)
                )
            )
        return self.decrypted_key

    @encrypted_key.setter
    def encrypted_key(self, value):
        """
        Set the encrypted key.
        """
        self.decrypted_key = value

    sapsf_base_url = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name="SAP Base URL",
        help_text=_("Base URL of success factors API.")
    )
    sapsf_company_id = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name="SAP Company ID",
        help_text=_("Success factors company identifier.")
    )
    sapsf_user_id = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name="SAP User ID",
        help_text=_("Success factors user identifier.")
    )

    decrypted_secret = EncryptedCharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name="Encrypted Client Secret",
        help_text=_(
            "The encrypted OAuth client secret."
            " It will be encrypted when stored in the database."
        ),
        null=True
    )

    @property
    def encrypted_secret(self):
        """
        Return encrypted secret as a string.
        The data is encrypted in the DB at rest, but is unencrypted in the app when retrieved through the
        decrypted_secret field. This method will encrypt the secret again before sending.
        """
        if self.decrypted_secret:
            return force_str(
                self._meta.get_field('decrypted_secret').fernet.encrypt(
                    force_bytes(self.decrypted_secret)
                )
            )
        return self.decrypted_secret

    @encrypted_secret.setter
    def encrypted_secret(self, value):
        """
        Set the encrypted secret.
        """
        self.decrypted_secret = value

    auth_type = models.CharField(
        max_length=32,
        choices=SAPAuthType.choices,
        default=SAPAuthType.SAP_SIGNED_ASSERTION,
        verbose_name="SAP Auth Type",
        help_text=_(
            "How access tokens are obtained for this customer. 'SAP-signed' asks SAP's OAuth IdP API to "
            "mint the SAML assertion for us, authenticated with the OAuth client id/secret; "
            "'Self-signed' means we sign the assertion ourselves with the configured private key "
            "instead. Self-signed support is still under development and is not yet used to authenticate any "
            "transmissions."
        )
    )

    decrypted_private_key = EncryptedTextField(
        blank=True,
        default='',
        verbose_name="Encrypted Private Key",
        help_text=_(
            "The PEM-encoded private key used to sign the SAML bearer assertion sent to this customer's "
            "token endpoint. Only used for a self-signed SAML assertion."
            " It will be encrypted when stored in the database."
        ),
        null=True
    )

    decrypted_private_key_passphrase = EncryptedCharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name="Encrypted Private Key Passphrase",
        help_text=_(
            "Passphrase protecting the private key, if any. Leave blank if the private key is "
            "not passphrase-protected. Only used for a self-signed SAML assertion."
            " It will be encrypted when stored in the database."
        ),
        null=True
    )

    saml_assertion_audience = models.CharField(
        max_length=255,
        blank=True,
        default='www.successfactors.com',
        verbose_name="SAML Assertion Audience",
        help_text=_(
            "Value of the Audience restriction in the SAML bearer assertion sent to this customer's "
            "token endpoint. Only used for a self-signed SAML assertion."
        )
    )

    user_type = models.CharField(
        max_length=20,
        choices=USER_TYPE_CHOICES,
        default=USER_TYPE_USER,
        verbose_name="SAP User Type",
        help_text=_("Type of SAP User (admin or user).")
    )
    additional_locales = models.TextField(
        blank=True,
        default='',
        verbose_name="Additional Locales",
        help_text=_("A comma-separated list of additional locales.")
    )
    transmit_total_hours = models.BooleanField(
        default=False,
        verbose_name=_("Transmit Total Hours"),
        help_text=_("Include totalHours in the transmitted completion data")
    )
    transmit_course_hours = models.BooleanField(
        default=False,
        verbose_name=_("Transmit Course Hours (Catalog)"),
        help_text=_(
            "Include totalHours/creditHours in the transmitted course catalog (content metadata) payload. "
            "This is independent of 'Transmit Total Hours', which only affects completion data -- some SAP "
            "endpoints reject unrecognized fields, so only enable this for customers who have explicitly "
            "requested it."
        )
    )
    prevent_self_submit_grades = models.BooleanField(
        default=False,
        verbose_name="Prevent Learner From Self-Submitting Grades",
        help_text=_("When set to True, the integration will use the "
                    "generic edX service user ('sapsf_user_id') "
                    "defined in the SAP Customer Configuration for course completion.")
    )

    # overriding base model field, to use chunk size 1 default
    transmission_chunk_size = models.IntegerField(
        default=1,
        help_text=(
            _("The maximum number of data items to transmit to the integrated channel "
              "with each request.")
        )
    )

    def get_locales(self, default_locale=None):
        """
        Get the list of all(default + additional) locales

        Args:
            default_locale (str): Value of the default locale

        Returns:
            list: available locales
        """
        locales = []

        if default_locale is None:
            locales.append('English')
        else:
            locales.append(default_locale)

        return set(
            locales + convert_comma_separated_string_to_list(self.additional_locales)
        )

    class Meta:
        app_label = 'sap_success_factors_channel'

    @property
    def uses_self_signed_assertion(self):
        """
        Whether access tokens for this customer are obtained with a self-signed SAML bearer assertion.
        """
        return self.auth_type == SAPAuthType.SELF_SIGNED_ASSERTION

    def _private_key_is_loadable(self):
        """
        Whether the configured private key is a PEM-encoded RSA private key that the configured
        passphrase (if any) unlocks, as required to sign a SAML assertion.
        """
        passphrase = self.decrypted_private_key_passphrase
        try:
            private_key = load_pem_private_key(
                force_bytes(self.decrypted_private_key),
                password=force_bytes(passphrase) if passphrase else None,
                # is_valid is read on every API serialization and health check, and RSA key
                # consistency checks take tens to hundreds of ms per key; signing still runs them.
                unsafe_skip_rsa_key_validation=True,
            )
        except (TypeError, ValueError, UnsupportedAlgorithm):
            # TypeError: a passphrase was given for an unencrypted key, or vice versa.
            return False
        return isinstance(private_key, rsa.RSAPrivateKey)

    @property
    def is_valid(self):
        """
        Returns whether or not the configuration is valid and ready to be activated

        Args:
            obj: The instance of SAPSuccessFactorsEnterpriseCustomerConfiguration
                being rendered with this admin form.
        """
        missing_items = {'missing': []}
        incorrect_items = {'incorrect': []}
        # The client id is needed in both modes: a self-signed assertion carries it as its Issuer.
        # The secret only authenticates the SAP-signed flow; a self-signed assertion replaces it.
        if not self.decrypted_key:
            missing_items.get('missing').append('key')
        if not self.sapsf_base_url:
            missing_items.get('missing').append('sapsf_base_url')
        if not self.sapsf_company_id:
            missing_items.get('missing').append('sapsf_company_id')
        if not self.sapsf_user_id:
            missing_items.get('missing').append('sapsf_user_id')
        if not self.decrypted_secret and not self.uses_self_signed_assertion:
            missing_items.get('missing').append('secret')
        if self.uses_self_signed_assertion:
            if not self.decrypted_private_key:
                missing_items.get('missing').append('private_key')
            elif not self._private_key_is_loadable():
                incorrect_items.get('incorrect').append('private_key')
            if not (self.saml_assertion_audience or '').strip():
                missing_items.get('missing').append('saml_assertion_audience')
            if not SAPSuccessFactorsGlobalConfiguration.current().oauth_token_api_path:
                missing_items.get('missing').append('oauth_token_api_path')
        if not is_valid_url(self.sapsf_base_url):
            incorrect_items.get('incorrect').append('sapsf_base_url')
        elif (
            self.uses_self_signed_assertion
            and self.sapsf_base_url
            and urlparse(self.sapsf_base_url).scheme != 'https'
        ):
            # A self-signed assertion names the token endpoint on this URL as its Recipient, which
            # must be an HTTPS URL.
            incorrect_items.get('incorrect').append('sapsf_base_url')
        if len(self.display_name) > 20:
            incorrect_items.get('incorrect').append('display_name')
        return missing_items, incorrect_items

    def is_ready_to_transmit(
        self,
        task_name: str,
        record_attempt: Callable[[datetime, bool], None] | None = None,
    ) -> bool:
        """
        Refuse to call SAP when the configuration is incomplete or invalid, and log why.

        Blocks on every problem ``is_valid`` reports, whether missing or incorrect, except those in
        ``COSMETIC_CONFIG_PROBLEMS``: an unparseable private key stops a transmission just as surely as
        an absent one.

        Args:
            task_name: name of the calling method, used in the log line.
            record_attempt: ``update_content_synced_at`` or ``update_learner_synced_at``, called with
                ``(now, False)`` when the run is blocked so the sync shows as errored rather than stale.

        Returns:
            bool: whether the caller should proceed.
        """
        missing_items, incorrect_items = self.is_valid
        missing_fields = [
            field for field in missing_items['missing'] if field not in self.COSMETIC_CONFIG_PROBLEMS
        ]
        invalid_fields = [
            field for field in incorrect_items['incorrect'] if field not in self.COSMETIC_CONFIG_PROBLEMS
        ]
        if not missing_fields and not invalid_fields:
            return True

        problems = []
        if missing_fields:
            problems.append(f'missing: {", ".join(missing_fields)}')
        if invalid_fields:
            problems.append(f'invalid: {", ".join(invalid_fields)}')
        LOGGER.warning(
            generate_formatted_log(
                channel_name=self.channel_code(),
                enterprise_customer_uuid=self.enterprise_customer.uuid,
                plugin_configuration_id=self.id,
                message=(
                    f'{task_name} aborted before any request to the channel because its '
                    f'configuration is incomplete or invalid ({"; ".join(problems)}).'
                ),
            )
        )
        if record_attempt is not None:
            record_attempt(localized_utcnow(), False)
        return False

    def __str__(self):
        """
        Return human-readable string representation.
        """
        return "<SAPSuccessFactorsEnterpriseCustomerConfiguration for Enterprise {enterprise_name}>".format(
            enterprise_name=self.enterprise_customer.name
        )

    def __repr__(self):
        """
        Return uniquely identifying string representation.
        """
        return self.__str__()

    @staticmethod
    def channel_code():
        """
        Returns an capitalized identifier for this channel class, unique among subclasses.
        """
        return 'SAP'

    @property
    def provider_id(self):
        '''
        Fetch ``provider_id`` from global configuration settings
        '''
        return SAPSuccessFactorsGlobalConfiguration.current().provider_id

    def get_learner_data_transmitter(self):
        """
        Return a ``SapSuccessFactorsLearnerTransmitter`` instance.
        """
        return SapSuccessFactorsLearnerTransmitter(self)

    def get_learner_data_exporter(self, user):
        """
        Return a ``SapSuccessFactorsLearnerDataExporter`` instance.
        """
        return SapSuccessFactorsLearnerExporter(user, self)

    def get_content_metadata_transmitter(self):
        """
        Return a ``SapSuccessFactorsContentMetadataTransmitter`` instance.
        """
        return SapSuccessFactorsContentMetadataTransmitter(self)

    def get_content_metadata_exporter(self, user):
        """
        Return a ``SapSuccessFactorsContentMetadataExporter`` instance.
        """
        return SapSuccessFactorsContentMetadataExporter(user, self)

    def get_learner_manger(self):
        """
        Return a ``SapSuccessFactorsLearnerManger`` instance.
        """
        return SapSuccessFactorsLearnerManger(self)

    def unlink_inactive_learners(self):
        """
        Unlink inactive SAP learners form their related enterprises
        """
        if not self.is_ready_to_transmit('unlink_inactive_learners'):
            return
        sap_learner_manager = self.get_learner_manger()
        try:
            sap_learner_manager.unlink_learners()
        except ClientError as exc:
            LOGGER.exception(
                'Failed to unlink learners for integrated channel [%s] [%s] \nError: [%s]',
                self.enterprise_customer.name,
                self.channel_code(),
                str(exc)
            )


class SapSuccessFactorsLearnerDataTransmissionAudit(LearnerDataTransmissionAudit):
    """
    The payload we sent to SuccessFactors at a given point in time for an enterprise course enrollment.

    .. pii: The user_email model field contains PII. Declaring "retained" because I don't know if it's retired.
    .. pii_types: email_address
    .. pii_retirement: retained
    """

    sapsf_user_id = models.CharField(max_length=255, blank=False, null=False)

    # XXX non-standard
    grade = models.CharField(max_length=100, blank=False, null=False)
    credit_hours = models.FloatField(null=True, blank=True)

    sap_completed_timestamp = models.BigIntegerField(null=True, blank=True)

    # override fields here otherwise multiple migrations created.
    plugin_configuration_id = models.IntegerField(blank=True, null=True)
    enterprise_course_enrollment_id = models.IntegerField(blank=True, null=True, db_index=True)

    class Meta:
        app_label = 'sap_success_factors_channel'
        constraints = [
            models.UniqueConstraint(
                fields=['enterprise_course_enrollment_id', 'course_id'],
                name='sap_ch_unique_enrollment_course_id'
            )
        ]
        indexes = [
            models.Index(
                fields=['enterprise_customer_uuid', 'plugin_configuration_id'],
                name='sap_success_factors_audit_idx'
            ),
        ]

    def __str__(self):
        """
        Return a human-readable string representation of the object.
        """
        return (
            '<SapSuccessFactorsLearnerDataTransmissionAudit {transmission_id} for enterprise enrollment '
            '{enterprise_course_enrollment_id}, SAPSF user {sapsf_user_id}, and course {course_id}>'.format(
                transmission_id=self.id,
                enterprise_course_enrollment_id=self.enterprise_course_enrollment_id,
                sapsf_user_id=self.sapsf_user_id,
                course_id=self.course_id
            )
        )

    def __repr__(self):
        """
        Return uniquely identifying string representation.
        """
        return self.__str__()

    @property
    def provider_id(self):
        """
        Fetch ``provider_id`` from global configuration settings
        """
        return SAPSuccessFactorsGlobalConfiguration.current().provider_id

    def serialize(self, *args, **kwargs):
        """
        Return a JSON-serialized representation.

        Sort the keys so the result is consistent and testable.

        # TODO: When we refactor to use a serialization flow consistent with how course metadata
        # is serialized, remove the serialization here and make the learner data exporter handle the work.
        """
        return json.dumps(self._payload_data(), sort_keys=True)

    def _payload_data(self):
        """
        Convert the audit record's fields into SAP SuccessFactors key/value pairs.
        """
        return {
            'userID': self.sapsf_user_id,
            'courseID': self.course_id,
            'providerID': self.provider_id,
            'courseCompleted': 'true' if self.course_completed else 'false',
            'completedTimestamp': self.sap_completed_timestamp,
            'grade': self.grade,
            'totalHours': self.total_hours,
            'creditHours': self.credit_hours,
        }
