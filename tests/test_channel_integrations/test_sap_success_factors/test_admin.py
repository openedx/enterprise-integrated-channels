"""
Tests for the SAP Success Factors admin module.
"""

import datetime
from unittest.mock import MagicMock, patch

import ddt
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponseRedirect
from django.test import TestCase
from pytest import mark
from requests import RequestException

from channel_integrations.exceptions import ClientError
from channel_integrations.sap_success_factors.admin import (
    SAPSuccessFactorsEnterpriseCustomerConfigurationAdmin,
    SAPSuccessFactorsEnterpriseCustomerConfigurationForm,
)
from channel_integrations.sap_success_factors.client import SAPSuccessFactorsAPIClient
from channel_integrations.sap_success_factors.models import (
    SAPAuthType,
    SAPSuccessFactorsEnterpriseCustomerConfiguration,
)
from test_utils import factories, generate_test_private_key_pem


@ddt.ddt
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
        self.request.user = MagicMock(has_perm=MagicMock(return_value=True))

    CREDENTIAL_FIELDS = (
        "decrypted_key",
        "decrypted_secret",
        "decrypted_private_key",
        "decrypted_private_key_passphrase",
        "saml_assertion_audience",
    )

    def test_media_includes_auth_type_toggle_script(self):
        """
        The admin form loads the JS that shows/hides credential fields based on auth_type,
        so both auth types' fields stay in the form (and validate) but aren't shown at once.

        This only confirms the script is registered -- there's no JS test runner in this repo,
        so the actual show/hide behavior isn't executed by this test suite.
        """
        media_js = self.admin_instance.media._js  # pylint:disable=protected-access

        assert any("toggle_auth_type_fields" in js_path for js_path in media_js)

    def test_add_form_retains_all_credential_fields(self):
        """
        The Add form keeps every credential field server-side -- visibility toggling is
        JS-only, so whichever auth_type an admin picks still has its fields to validate.
        """
        form_class = self.admin_instance.get_form(self.request, obj=None)

        for field_name in self.CREDENTIAL_FIELDS:
            assert field_name in form_class.base_fields

    def test_change_form_retains_all_credential_fields(self):
        """
        The Change form (an existing config) also keeps every credential field server-side.
        """
        form_class = self.admin_instance.get_form(self.request, obj=self.sap_config)

        for field_name in self.CREDENTIAL_FIELDS:
            assert field_name in form_class.base_fields

    def test_get_form_for_view_only_user_does_not_raise(self):
        """
        Regression: Django excludes every field from the change form when the request user has
        view but not change permission -- the form must not assume the passphrase field is there.
        """
        with patch.object(self.admin_instance, "has_change_permission", return_value=False):
            form_class = self.admin_instance.get_form(self.request, obj=self.sap_config, change=True)
            form = form_class(instance=self.sap_config)

        assert "decrypted_private_key_passphrase" not in form.fields

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

    def test_has_access_token_success(self):
        """
        Returns True when the client returns a token.
        """
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        with patch(
            "channel_integrations.sap_success_factors.admin.SAPSuccessFactorsAPIClient"
        ) as mock_client_class:
            mock_client_class.return_value.get_access_token.return_value = ("a-token", expires_at)
            result = self.admin_instance.has_access_token(self.sap_config)

        assert result is True
        mock_client_class.assert_called_once_with(self.sap_config)
        mock_client_class.return_value.get_access_token.assert_called_once_with(
            self.sap_config.sapsf_user_id,
            self.sap_config.user_type,
            timeout=mock_client_class.return_value.SESSION_TIMEOUT,
        )

    def test_has_access_token_request_exception_returns_false(self):
        """
        Returns False, instead of raising, when token acquisition raises a RequestException.
        """
        with patch(
            "channel_integrations.sap_success_factors.admin.SAPSuccessFactorsAPIClient"
        ) as mock_client_class:
            mock_client_class.return_value.get_access_token.side_effect = RequestException("boom")
            result = self.admin_instance.has_access_token(self.sap_config)

        assert result is False

    def test_has_access_token_client_error_returns_false(self):
        """
        Returns False, instead of raising, when token acquisition raises a ClientError.
        """
        with patch(
            "channel_integrations.sap_success_factors.admin.SAPSuccessFactorsAPIClient"
        ) as mock_client_class:
            mock_client_class.return_value.get_access_token.side_effect = ClientError("bad response", 500)
            result = self.admin_instance.has_access_token(self.sap_config)

        assert result is False

    @ddt.data(SAPAuthType.SAP_SIGNED_ASSERTION, SAPAuthType.SELF_SIGNED_ASSERTION)
    def test_has_access_token_does_not_raise_attribute_error(self, auth_type):
        """
        Regression test: exercises the real client (only the network call, and for self-signed the
        assertion signing, are mocked) for both auth types, to confirm has_access_token no longer
        raises AttributeError and that the configured timeout reaches the HTTP call.
        """
        self.sap_config.auth_type = auth_type
        with patch("channel_integrations.sap_success_factors.client.requests.post") as mock_post, patch(
            "channel_integrations.sap_success_factors.client.generate_saml_assertion", return_value="<assertion/>"
        ):
            mock_post.side_effect = RequestException("network unreachable")
            result = self.admin_instance.has_access_token(self.sap_config)

        assert result is False
        assert mock_post.call_args.kwargs['timeout'] == SAPSuccessFactorsAPIClient.SESSION_TIMEOUT

    def test_has_access_token_returns_none_for_unsaved_config(self):
        """
        Regression test: returns None, without making a request, for an unsaved config (e.g. the
        admin Add form) -- it has no pk yet for the request to be logged against.
        """
        unsaved_config = factories.SAPSuccessFactorsEnterpriseCustomerConfigurationFactory.build()
        with patch("channel_integrations.sap_success_factors.client.requests.post") as mock_post:
            result = self.admin_instance.has_access_token(unsaved_config)

        assert result is None
        mock_post.assert_not_called()


@ddt.ddt
@mark.django_db
class TestSAPSuccessFactorsEnterpriseCustomerConfigurationForm(TestCase):
    """
    Tests for the ``SAPSuccessFactorsEnterpriseCustomerConfigurationForm``.
    """

    def setUp(self):
        super().setUp()
        self.sap_config = factories.SAPSuccessFactorsEnterpriseCustomerConfigurationFactory()

    def _form_data(self, **overrides):
        data = {
            "enterprise_customer": self.sap_config.enterprise_customer_id,
            "sapsf_base_url": "https://sapsf.example.com",
            "sapsf_company_id": "company",
            "sapsf_user_id": "user",
            "user_type": SAPSuccessFactorsEnterpriseCustomerConfiguration.USER_TYPE_USER,
            "auth_type": SAPAuthType.SAP_SIGNED_ASSERTION,
            "saml_assertion_audience": "www.successfactors.com",
            "transmission_chunk_size": 1,
        }
        data.update(overrides)
        return data

    @ddt.data(
        (SAPAuthType.SELF_SIGNED_ASSERTION, None, "decrypted_private_key"),  # key required
        (SAPAuthType.SELF_SIGNED_ASSERTION, "not-a-pem-key", "decrypted_private_key"),  # malformed
        (SAPAuthType.SAP_SIGNED_ASSERTION, "not-a-pem-key", "decrypted_private_key"),  # malformed, either auth type
    )
    @ddt.unpack
    def test_private_key_rejected(self, auth_type, private_key, expected_error_field):
        overrides = {"auth_type": auth_type}
        if private_key is not None:
            overrides["decrypted_private_key"] = private_key
        form = SAPSuccessFactorsEnterpriseCustomerConfigurationForm(
            data=self._form_data(**overrides), instance=self.sap_config,
        )
        assert not form.is_valid()
        assert expected_error_field in form.errors

    @ddt.data(SAPAuthType.SELF_SIGNED_ASSERTION, SAPAuthType.SAP_SIGNED_ASSERTION)
    def test_valid_private_key_or_none_accepted(self, auth_type):
        overrides = {"auth_type": auth_type}
        if auth_type == SAPAuthType.SELF_SIGNED_ASSERTION:
            overrides["decrypted_private_key"] = generate_test_private_key_pem()
        form = SAPSuccessFactorsEnterpriseCustomerConfigurationForm(
            data=self._form_data(**overrides), instance=self.sap_config,
        )
        assert form.is_valid(), form.errors

    def test_self_signed_auth_requires_sapsf_base_url(self):
        """Regression: is_valid_url('') is True, so a blank URL must be checked separately."""
        form = SAPSuccessFactorsEnterpriseCustomerConfigurationForm(
            data=self._form_data(
                auth_type=SAPAuthType.SELF_SIGNED_ASSERTION,
                decrypted_private_key=generate_test_private_key_pem(),
                sapsf_base_url="",
            ),
            instance=self.sap_config,
        )
        assert not form.is_valid()
        assert "sapsf_base_url" in form.errors

    def test_passphrase_with_meaningful_whitespace_is_not_stripped(self):
        """Regression: the default CharField strips whitespace, but decryption needs exact bytes."""
        passphrase = " has leading and trailing spaces "
        form = SAPSuccessFactorsEnterpriseCustomerConfigurationForm(
            data=self._form_data(
                auth_type=SAPAuthType.SELF_SIGNED_ASSERTION,
                decrypted_private_key=generate_test_private_key_pem(passphrase=passphrase),
                decrypted_private_key_passphrase=passphrase,
            ),
            instance=self.sap_config,
        )
        assert form.is_valid(), form.errors
        assert form.save().decrypted_private_key_passphrase == passphrase

    def test_oversized_base_url_is_invalid_without_crashing(self):
        """Regression: an over-max_length sapsf_base_url used to crash is_valid_url(None)."""
        form = SAPSuccessFactorsEnterpriseCustomerConfigurationForm(
            data=self._form_data(sapsf_base_url="https://example.com/" + "x" * 250),
            instance=self.sap_config,
        )
        assert not form.is_valid()
        assert "sapsf_base_url" in form.errors

    def test_oversized_base_url_does_not_hide_a_second_unrelated_error(self):
        """
        Regression: one credential field already having its own error (the oversized URL) must
        not suppress validation of the others -- here, the missing private key for self-signed.
        """
        form = SAPSuccessFactorsEnterpriseCustomerConfigurationForm(
            data=self._form_data(
                auth_type=SAPAuthType.SELF_SIGNED_ASSERTION,
                sapsf_base_url="https://example.com/" + "x" * 250,
            ),
            instance=self.sap_config,
        )
        assert not form.is_valid()
        assert "sapsf_base_url" in form.errors
        assert "decrypted_private_key" in form.errors

    def test_self_signed_to_sap_signed_switch_in_one_save_succeeds(self):
        self.sap_config.auth_type = SAPAuthType.SELF_SIGNED_ASSERTION
        self.sap_config.decrypted_private_key = generate_test_private_key_pem()
        self.sap_config.save()

        form = SAPSuccessFactorsEnterpriseCustomerConfigurationForm(
            data=self._form_data(auth_type=SAPAuthType.SAP_SIGNED_ASSERTION),
            instance=self.sap_config,
        )
        assert form.is_valid(), form.errors
        saved = form.save()
        assert saved.auth_type == SAPAuthType.SAP_SIGNED_ASSERTION

    def test_blank_private_key_submission_clears_stored_value(self):
        """Matches ``decrypted_key``/``decrypted_secret``: blank means blank, not "unchanged"."""
        self.sap_config.auth_type = SAPAuthType.SAP_SIGNED_ASSERTION
        self.sap_config.decrypted_private_key = generate_test_private_key_pem()
        self.sap_config.save()

        form = SAPSuccessFactorsEnterpriseCustomerConfigurationForm(
            data=self._form_data(decrypted_private_key=""),
            instance=self.sap_config,
        )
        assert form.is_valid(), form.errors
        saved = form.save()
        assert saved.decrypted_private_key == ""


@mark.django_db
class TestSAPSuccessFactorsEnterpriseCustomerConfigurationAdminAddPage(TestCase):
    """
    Tests that exercise the admin's actual ``get_form`` machinery, the way the real add page does,
    rather than instantiating the form directly.
    """

    def setUp(self):
        super().setUp()
        self.admin_site = AdminSite()
        self.admin_instance = SAPSuccessFactorsEnterpriseCustomerConfigurationAdmin(
            SAPSuccessFactorsEnterpriseCustomerConfiguration, self.admin_site
        )
        self.request = HttpRequest()
        self.request.session = {}
        self.request._messages = MagicMock()  # pylint:disable=protected-access
        self.request.user = MagicMock(has_perm=MagicMock(return_value=True))

    def test_add_page_requires_private_key_for_self_signed_auth_type(self):
        """
        Regression: on the add page (no ``obj`` yet), a self-signed submission with no key must
        be blocked, not silently saved -- this was the actual reported vulnerability.
        """
        enterprise_customer = factories.EnterpriseCustomerFactory()
        FormClass = self.admin_instance.get_form(self.request, obj=None)
        form = FormClass(data={
            "enterprise_customer": enterprise_customer.uuid,
            "sapsf_base_url": "http://sapsf.example.com",
            "sapsf_company_id": "company",
            "sapsf_user_id": "user",
            "user_type": SAPSuccessFactorsEnterpriseCustomerConfiguration.USER_TYPE_USER,
            "auth_type": SAPAuthType.SELF_SIGNED_ASSERTION,
            "transmission_chunk_size": 1,
        })
        assert not form.is_valid()
        assert "decrypted_private_key" in form.errors
