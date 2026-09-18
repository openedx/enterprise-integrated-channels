"""
Tests for the SAP Success Factors admin module.
"""

from unittest.mock import MagicMock, patch

from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponseRedirect
from django.test import TestCase
from pytest import mark

from channel_integrations.sap_success_factors.admin import (
    SAPSuccessFactorsEnterpriseCustomerConfigurationAdmin,
    SAPSuccessFactorsEnterpriseCustomerConfigurationForm,
)
from channel_integrations.sap_success_factors.models import SAPSuccessFactorsEnterpriseCustomerConfiguration
from test_utils import factories


@mark.django_db
class TestSAPSuccessFactorsEnterpriseCustomerConfigurationAdmin(TestCase):
    """
    Tests for the ``SAPSuccessFactorsEnterpriseCustomerConfigurationAdmin`` admin class.
    """

    def setUp(self):
        """
        Set up test data.
        """
        super().setUp()
        self.admin_site = AdminSite()
        self.admin_instance = SAPSuccessFactorsEnterpriseCustomerConfigurationAdmin(
            SAPSuccessFactorsEnterpriseCustomerConfiguration, self.admin_site
        )
        self.sap_config = factories.SAPSuccessFactorsEnterpriseCustomerConfigurationFactory()
        self.request = HttpRequest()
        self.request.session = {}
        self.request._messages = MagicMock()  # pylint:disable=protected-access

    def test_force_content_metadata_transmission_success(self):
        """
        Test force_content_metadata_transmission method with successful save.
        """
        with patch.object(self.sap_config.enterprise_customer, 'save') as mock_save:
            response = self.admin_instance.force_content_metadata_transmission(
                self.request, self.sap_config
            )

            # Verify the enterprise customer save was called
            mock_save.assert_called_once()

            # Verify the response is a redirect to the correct URL
            assert isinstance(response, HttpResponseRedirect)
            assert response.url == "/admin/sap_success_factors_channel/sapsuccessfactorsenterprisecustomerconfiguration"

    def test_force_content_metadata_transmission_validation_error(self):
        """
        Test force_content_metadata_transmission method with ValidationError.
        """
        with patch.object(
            self.sap_config.enterprise_customer, 'save',
            side_effect=ValidationError("Test validation error")
        ) as mock_save:
            response = self.admin_instance.force_content_metadata_transmission(
                self.request, self.sap_config
            )

            # Verify the enterprise customer save was called
            mock_save.assert_called_once()

            # Verify the response is a redirect to the correct URL
            assert isinstance(response, HttpResponseRedirect)
            assert response.url == "/admin/sap_success_factors_channel/sapsuccessfactorsenterprisecustomerconfiguration"

    def test_force_content_metadata_transmission_label(self):
        """
        Test that the force_content_metadata_transmission method has the correct label.
        """
        assert self.admin_instance.force_content_metadata_transmission.label == "Force content metadata transmission"


@mark.django_db
class TestSAPSuccessFactorsEnterpriseCustomerConfigurationForm(TestCase):
    """
    Tests for the write-only handling of ``decrypted_private_key`` on the admin form.
    """

    PRIVATE_KEY = (
        '-----BEGIN PRIVATE KEY-----\n'
        'MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDfakeKeyMaterial\n'
        '-----END PRIVATE KEY-----\n'
    )

    def setUp(self):
        super().setUp()
        self.sap_config = factories.SAPSuccessFactorsEnterpriseCustomerConfigurationFactory(
            decrypted_private_key=self.PRIVATE_KEY,
        )

    def _form_data(self, **overrides):
        """
        Build a POST payload mirroring the stored configuration, with ``overrides`` applied.
        """
        data = {
            'enterprise_customer': self.sap_config.enterprise_customer.uuid,
            'display_name': self.sap_config.display_name,
            'idp_id': self.sap_config.idp_id,
            'sapsf_base_url': self.sap_config.sapsf_base_url,
            'sapsf_company_id': self.sap_config.sapsf_company_id,
            'sapsf_user_id': self.sap_config.sapsf_user_id,
            'decrypted_key': self.sap_config.decrypted_key,
            'decrypted_secret': self.sap_config.decrypted_secret,
            'auth_type': self.sap_config.auth_type,
            'decrypted_private_key': '',
            'saml_assertion_api_path': self.sap_config.saml_assertion_api_path,
            'saml_assertion_audience': self.sap_config.saml_assertion_audience,
            'oauth_token_api_path': self.sap_config.oauth_token_api_path,
            'user_type': self.sap_config.user_type,
            'transmission_chunk_size': self.sap_config.transmission_chunk_size,
            'additional_locales': '',
            'catalogs_to_transmit': '',
            'channel_worker_username': '',
        }
        data.update(overrides)
        return data

    def test_stored_private_key_is_not_rendered(self):
        """
        The stored key must never reach the rendered page, only a placeholder standing in for it.
        """
        rendered = str(SAPSuccessFactorsEnterpriseCustomerConfigurationForm(instance=self.sap_config))

        assert 'fakeKeyMaterial' not in rendered
        assert 'BEGIN PRIVATE KEY' not in rendered
        assert 'leave blank to keep the existing key' in rendered

    def test_blank_private_key_keeps_stored_value(self):
        """
        Saving the form without re-entering the key must not wipe the stored one.
        """
        form = SAPSuccessFactorsEnterpriseCustomerConfigurationForm(
            data=self._form_data(), instance=self.sap_config
        )

        assert form.is_valid(), form.errors
        form.save()
        self.sap_config.refresh_from_db()
        assert self.sap_config.decrypted_private_key == self.PRIVATE_KEY

    def test_submitted_private_key_replaces_stored_value(self):
        """
        Pasting a new key rotates it, which is the only supported way to change it here.
        """
        rotated = self.PRIVATE_KEY.replace('fakeKeyMaterial', 'rotatedKeyMaterial')
        form = SAPSuccessFactorsEnterpriseCustomerConfigurationForm(
            data=self._form_data(decrypted_private_key=rotated), instance=self.sap_config
        )

        assert form.is_valid(), form.errors
        form.save()
        self.sap_config.refresh_from_db()
        # CharField strips surrounding whitespace, which PEM parsing does not depend on.
        assert self.sap_config.decrypted_private_key == rotated.strip()
        assert 'rotatedKeyMaterial' in self.sap_config.decrypted_private_key
