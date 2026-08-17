"""
Tests for tpa_org_id_service.py.
"""
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from social_django.models import UserSocialAuth

from channel_integrations.integrated_channel.services.tpa_org_id_service import get_tpa_org_id
from test_utils.factories import EnterpriseCustomerFactory, EnterpriseCustomerIdentityProviderFactory

User = get_user_model()


@pytest.mark.django_db
class TestGetTpaOrgId:
    """Tests for get_tpa_org_id."""

    def test_returns_scalar_org_id(self):
        """A scalar percipioOrganizationUuid in extra_data is returned as-is."""
        user = User.objects.create(username='testuser', email='test@example.com')
        enterprise_customer = EnterpriseCustomerFactory()

        with patch(
            'channel_integrations.integrated_channel.services.tpa_org_id_service.get_user_social_auth'
        ) as mock_get_social_auth:
            mock_social = MagicMock()
            mock_social.extra_data = {'percipioOrganizationUuid': 'org-123'}
            mock_get_social_auth.return_value = mock_social

            assert get_tpa_org_id(user, enterprise_customer) == 'org-123'

    def test_returns_first_item_of_list_wrapped_org_id(self):
        """A single-item list value is normalized to a scalar string."""
        user = User.objects.create(username='testuser', email='test@example.com')
        enterprise_customer = EnterpriseCustomerFactory()

        with patch(
            'channel_integrations.integrated_channel.services.tpa_org_id_service.get_user_social_auth'
        ) as mock_get_social_auth:
            mock_social = MagicMock()
            mock_social.extra_data = {'percipioOrganizationUuid': ['org-456']}
            mock_get_social_auth.return_value = mock_social

            assert get_tpa_org_id(user, enterprise_customer) == 'org-456'

    def test_returns_none_when_no_social_auth(self):
        """No UserSocialAuth record for the user returns None."""
        user = User.objects.create(username='testuser', email='test@example.com')
        enterprise_customer = EnterpriseCustomerFactory()

        with patch(
            'channel_integrations.integrated_channel.services.tpa_org_id_service.get_user_social_auth'
        ) as mock_get_social_auth:
            mock_get_social_auth.return_value = None

            assert get_tpa_org_id(user, enterprise_customer) is None

    def test_returns_none_when_extra_data_empty(self):
        """Empty extra_data returns None."""
        user = User.objects.create(username='testuser', email='test@example.com')
        enterprise_customer = EnterpriseCustomerFactory()

        with patch(
            'channel_integrations.integrated_channel.services.tpa_org_id_service.get_user_social_auth'
        ) as mock_get_social_auth:
            mock_social = MagicMock()
            mock_social.extra_data = {}
            mock_get_social_auth.return_value = mock_social

            assert get_tpa_org_id(user, enterprise_customer) is None

    def test_returns_none_when_key_missing(self):
        """extra_data present but missing the org id key returns None."""
        user = User.objects.create(username='testuser', email='test@example.com')
        enterprise_customer = EnterpriseCustomerFactory()

        with patch(
            'channel_integrations.integrated_channel.services.tpa_org_id_service.get_user_social_auth'
        ) as mock_get_social_auth:
            mock_social = MagicMock()
            mock_social.extra_data = {'country': ['US']}
            mock_get_social_auth.return_value = mock_social

            assert get_tpa_org_id(user, enterprise_customer) is None

    def test_swallows_exceptions_and_returns_none(self):
        """Any unexpected exception is caught and logged, never raised."""
        user = User.objects.create(username='testuser', email='test@example.com')
        enterprise_customer = EnterpriseCustomerFactory()

        with patch(
            'channel_integrations.integrated_channel.services.tpa_org_id_service.get_user_social_auth'
        ) as mock_get_social_auth:
            mock_get_social_auth.side_effect = Exception('boom')

            assert get_tpa_org_id(user, enterprise_customer) is None

    def test_outer_exception_handler_catches_errors_after_social_auth_resolved(self):
        """
        The outer try/except must catch errors that happen AFTER a social auth row is
        successfully resolved (e.g. malformed extra_data), not just the ones inside
        `_get_social_auth`'s own inner fallback - those are two distinct safety nets.
        """
        user = User.objects.create(username='testuser', email='test@example.com')
        enterprise_customer = EnterpriseCustomerFactory()

        with patch(
            'channel_integrations.integrated_channel.services.tpa_org_id_service.get_user_social_auth'
        ) as mock_get_social_auth:
            mock_social = MagicMock()
            mock_social.extra_data = 42  # malformed: truthy, but has no .get() like a real dict
            mock_get_social_auth.return_value = mock_social

            assert get_tpa_org_id(user, enterprise_customer) is None

    def test_returns_none_when_user_is_none(self):
        """A None user (should never happen, but must not crash) returns None."""
        enterprise_customer = EnterpriseCustomerFactory()

        assert get_tpa_org_id(None, enterprise_customer) is None

    def test_falls_back_to_plain_lookup_when_get_user_social_auth_raises(self):
        """
        Regression test: get_user_social_auth (real edx-enterprise implementation) raises when
        an enterprise's configured identity provider isn't registered in the third_party_auth
        Registry (get_identity_provider returns None, and .backend_name on None raises). Before
        this fallback existed, that exception was swallowed by the outer try/except and silently
        dropped the org id from the Percipio webhook payload for any customer hitting that edge
        case - even though the plain per-user lookup that worked before this function existed
        would still have found the right UserSocialAuth row. This locks in that the fallback is
        used instead of losing the org id.
        """
        user = User.objects.create(username='testuser', email='test@example.com')
        enterprise_customer = EnterpriseCustomerFactory()
        UserSocialAuth.objects.create(
            user=user,
            provider='tpa-saml',
            uid='skillsoft-us:abc',
            extra_data={'percipioOrganizationUuid': 'org-789'},
        )

        with patch(
            'channel_integrations.integrated_channel.services.tpa_org_id_service.get_user_social_auth'
        ) as mock_get_social_auth:
            mock_get_social_auth.side_effect = AttributeError(
                "'NoneType' object has no attribute 'backend_name'"
            )

            assert get_tpa_org_id(user, enterprise_customer) == 'org-789'

    def test_disambiguates_between_multiple_social_auth_rows(self):
        """
        With more than one UserSocialAuth row for a user, the one matching the enterprise
        customer's configured identity provider is preferred over an unrelated one.
        """
        user = User.objects.create(username='testuser', email='test@example.com')
        enterprise_customer = EnterpriseCustomerFactory()
        EnterpriseCustomerIdentityProviderFactory(
            enterprise_customer=enterprise_customer,
            provider_id='skillsoft-us',
        )

        UserSocialAuth.objects.create(
            user=user,
            provider='tpa-saml',
            uid='some-other-idp:abc',
            extra_data={'percipioOrganizationUuid': 'wrong-org'},
        )
        UserSocialAuth.objects.create(
            user=user,
            provider='tpa-saml',
            uid='skillsoft-us:abc',
            extra_data={'percipioOrganizationUuid': 'correct-org'},
        )

        assert get_tpa_org_id(user, enterprise_customer) == 'correct-org'
