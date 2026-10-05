"""
Django admin integration for configuring sap_success_factors app to communicate with SAP SuccessFactors systems.
"""

from config_models.admin import ConfigurationModelAdmin
from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django_object_actions import DjangoObjectActions
from requests import RequestException

from channel_integrations.exceptions import ClientError
from channel_integrations.integrated_channel.admin import BaseLearnerDataTransmissionAuditAdmin
from channel_integrations.sap_success_factors.client import SAPSuccessFactorsAPIClient
from channel_integrations.sap_success_factors.models import (
    SAPSuccessFactorsEnterpriseCustomerConfiguration,
    SAPSuccessFactorsGlobalConfiguration,
    SapSuccessFactorsLearnerDataTransmissionAudit,
)


class SAPSuccessFactorsEnterpriseCustomerConfigurationForm(forms.ModelForm):
    """
    Django admin form for SAPSuccessFactorsEnterpriseCustomerConfiguration.
    """
    class Meta:
        model = SAPSuccessFactorsEnterpriseCustomerConfiguration
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Decryption needs the exact passphrase bytes; the default CharField strips whitespace.
        # The field is absent for a view-only (no change permission) request, which excludes
        # every field from the form -- nothing to patch in that case.
        passphrase_field = self.fields.get("decrypted_private_key_passphrase")
        if passphrase_field is not None:
            passphrase_field.strip = False

    def _cleaned_or_blank(self, cleaned_data, field_name):
        """A field with its own error is absent from cleaned_data, not blank -- substitute
        blank so the credential check still runs and doesn't hide a different field's error."""
        return "" if self.has_error(field_name) else cleaned_data.get(field_name)

    def clean(self):
        cleaned_data = super().clean()
        candidate = self.instance if self.instance.pk else SAPSuccessFactorsEnterpriseCustomerConfiguration()
        errors = candidate.get_credential_errors(
            auth_type=self._cleaned_or_blank(cleaned_data, "auth_type"),
            private_key=self._cleaned_or_blank(cleaned_data, "decrypted_private_key"),
            private_key_passphrase=self._cleaned_or_blank(cleaned_data, "decrypted_private_key_passphrase"),
            saml_assertion_audience=self._cleaned_or_blank(cleaned_data, "saml_assertion_audience"),
            sapsf_base_url=self._cleaned_or_blank(cleaned_data, "sapsf_base_url"),
        )
        for field, message in errors.items():
            self.add_error(field, message)
        return cleaned_data


@admin.register(SAPSuccessFactorsGlobalConfiguration)
class SAPSuccessFactorsGlobalConfigurationAdmin(ConfigurationModelAdmin):
    """
    Django admin model for SAPSuccessFactorsGlobalConfiguration.
    """
    list_display = (
        "completion_status_api_path",
        "course_api_path",
        "oauth_api_path",
        "oauth_token_api_path",
        "provider_id",
        "search_student_api_path",
    )

    class Meta:
        model = SAPSuccessFactorsGlobalConfiguration


@admin.register(SAPSuccessFactorsEnterpriseCustomerConfiguration)
class SAPSuccessFactorsEnterpriseCustomerConfigurationAdmin(DjangoObjectActions, admin.ModelAdmin):
    """
    Django admin model for SAPSuccessFactorsEnterpriseCustomerConfiguration.
    """
    form = SAPSuccessFactorsEnterpriseCustomerConfigurationForm

    fields = (
        "enterprise_customer",
        "idp_id",
        "active",
        "sapsf_base_url",
        "sapsf_company_id",
        "decrypted_key",
        "decrypted_secret",
        "auth_type",
        "decrypted_private_key",
        "decrypted_private_key_passphrase",
        "saml_assertion_audience",
        "sapsf_user_id",
        "user_type",
        "has_access_token",
        "prevent_self_submit_grades",
        "show_course_price",
        "dry_run_mode_enabled",
        "disable_learner_data_transmissions",
        "transmit_total_hours",
        "transmit_course_hours",
        "transmission_chunk_size",
        "additional_locales",
        "catalogs_to_transmit",
        "display_name",
    )

    list_display = (
        "enterprise_customer_name",
        "active",
        "sapsf_base_url",
        "modified",
    )
    ordering = ("enterprise_customer__name",)

    readonly_fields = ("has_access_token",)

    raw_id_fields = ("enterprise_customer",)

    list_filter = ("active",)
    search_fields = ("enterprise_customer__name",)
    change_actions = ("force_content_metadata_transmission",)

    class Media:
        js = ("sap_success_factors/admin/toggle_auth_type_fields.js",)

    class Meta:
        model = SAPSuccessFactorsEnterpriseCustomerConfiguration

    def enterprise_customer_name(self, obj):
        """
        Returns: the name for the attached EnterpriseCustomer.

        Args:
            obj: The instance of SAPSuccessFactorsEnterpriseCustomerConfiguration
                being rendered with this admin form.
        """
        return obj.enterprise_customer.name

    @admin.display(
        description="Has Access Token?",
        boolean=True,
    )
    def has_access_token(self, obj):
        """
        Confirms the presence and validity of the access token for the SAP SuccessFactors client instance

        Returns: True/False once a token request has been attempted, or None for an unsaved obj
            (e.g. the admin Add form) -- there's no config id yet to log the request against.

        Args:
            obj: The instance of SAPSuccessFactorsEnterpriseCustomerConfiguration
                being rendered with this admin form.
        """
        if obj.pk is None:
            return None
        # Request the token the same way _create_session() does, so this reflects whether
        # transmissions can authenticate.
        client = SAPSuccessFactorsAPIClient(obj)
        try:
            access_token, expires_at = client.get_oauth_access_token(
                client_id=obj.decrypted_key,
                client_secret=obj.decrypted_secret,
                company_id=obj.sapsf_company_id,
                user_id=obj.sapsf_user_id,
                user_type=obj.user_type,
                customer_uuid=obj.enterprise_customer.uuid,
                timeout=client.SESSION_TIMEOUT,
            )
        except (RequestException, ClientError):
            return False
        return bool(access_token and expires_at)

    @admin.action(
        description="Force content metadata transmission for this Enterprise Customer"
    )
    def force_content_metadata_transmission(self, request, obj):
        """
        Updates the modified time of the customer record to retransmit courses metadata
        and redirects to configuration view with success or error message.
        """
        try:
            obj.enterprise_customer.save()
            messages.success(
                request,
                f'''The sap success factors enterprise customer content metadata
                “<SAPSuccessFactorsEnterpriseCustomerConfiguration for Enterprise
                {obj.enterprise_customer.name}>” was updated successfully.''',
            )
        except ValidationError:
            messages.error(
                request,
                f'''The sap success factors enterprise customer content metadata
                “<SAPSuccessFactorsEnterpriseCustomerConfiguration for Enterprise
                {obj.enterprise_customer.name}>” was not updated successfully.''',
            )
        return HttpResponseRedirect(
            "/admin/sap_success_factors_channel/sapsuccessfactorsenterprisecustomerconfiguration"
        )
    force_content_metadata_transmission.label = "Force content metadata transmission"


@admin.register(SapSuccessFactorsLearnerDataTransmissionAudit)
class SapSuccessFactorsLearnerDataTransmissionAuditAdmin(
    BaseLearnerDataTransmissionAuditAdmin
):
    """
    Django admin model for SapSuccessFactorsLearnerDataTransmissionAudit.
    """

    list_display = (
        "enterprise_course_enrollment_id",
        "course_id",
        "status",
        "modified",
    )

    readonly_fields = (
        "sapsf_user_id",
        "progress_status",
        "content_title",
        "enterprise_customer_name",
        "friendly_status_message",
        "api_record",
    )

    search_fields = (
        "sapsf_user_id",
        "enterprise_course_enrollment_id",
        "course_id",
        "content_title",
        "friendly_status_message"
    )

    list_per_page = 1000

    class Meta:
        model = SapSuccessFactorsLearnerDataTransmissionAudit
