"""
Tests for pipeline.py, the SOCIAL_AUTH_PIPELINE entry point.
"""
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from enterprise.models import EnterpriseGroupMembership
from social_django.models import UserSocialAuth
from waffle.testutils import override_switch

from channel_integrations.integrated_channel.models import TpaOrgAllowlist
from channel_integrations.integrated_channel.pipeline import (
    ENABLE_TPA_ORG_GROUP_LOGIN_SYNC_SWITCH,
    sync_tpa_budget_group,
)
from test_utils.factories import (
    EnterpriseCustomerFactory,
    EnterpriseCustomerIdentityProviderFactory,
    EnterpriseCustomerUserFactory,
    UserFactory,
)

User = get_user_model()

PATCH_SYNC = 'channel_integrations.integrated_channel.pipeline.sync_learner_budget_group'


def make_backend(tpa_hint=None):
    """Build a minimal fake social-auth backend with just what sync_tpa_budget_group needs."""
    request = SimpleNamespace(GET={'tpa_hint': tpa_hint} if tpa_hint else {})
    strategy = SimpleNamespace(request=request)
    return SimpleNamespace(strategy=strategy, name='tpa-saml')


@pytest.mark.django_db
class TestSyncTpaBudgetGroup:
    """Tests for sync_tpa_budget_group."""

    @override_switch(ENABLE_TPA_ORG_GROUP_LOGIN_SYNC_SWITCH, active=False)
    def test_noop_when_switch_off(self):
        """The whole mechanism is a true no-op when the waffle switch is off."""
        user = UserFactory()
        backend = make_backend(tpa_hint='skillsoft-us')

        with patch(PATCH_SYNC) as mock_sync:
            sync_tpa_budget_group(backend, user)

        mock_sync.assert_not_called()

    @override_switch(ENABLE_TPA_ORG_GROUP_LOGIN_SYNC_SWITCH, active=True)
    def test_noop_when_no_enterprise_customer_resolved(self):
        """No matching enterprise customer for the SSO provider is a no-op."""
        user = UserFactory()
        backend = make_backend(tpa_hint='some-unconfigured-provider')

        with patch(PATCH_SYNC) as mock_sync:
            sync_tpa_budget_group(backend, user)

        mock_sync.assert_not_called()

    @override_switch(ENABLE_TPA_ORG_GROUP_LOGIN_SYNC_SWITCH, active=True)
    def test_calls_sync_when_switch_on_and_customer_resolved(self):
        """A resolved enterprise customer triggers the sync service with the right arguments."""
        user = UserFactory()
        enterprise_customer = EnterpriseCustomerFactory()
        EnterpriseCustomerIdentityProviderFactory(
            enterprise_customer=enterprise_customer,
            provider_id='skillsoft-us',
        )
        backend = make_backend(tpa_hint='skillsoft-us')

        with patch(PATCH_SYNC) as mock_sync:
            sync_tpa_budget_group(backend, user)

        mock_sync.assert_called_once_with(user, enterprise_customer)

    @override_switch(ENABLE_TPA_ORG_GROUP_LOGIN_SYNC_SWITCH, active=True)
    def test_exceptions_resolving_enterprise_customer_are_swallowed(self):
        """A malformed backend (e.g. missing .strategy) never raises out of the pipeline."""
        user = UserFactory()
        broken_backend = SimpleNamespace(name='tpa-saml')  # no .strategy attribute

        with patch(PATCH_SYNC) as mock_sync:
            sync_tpa_budget_group(broken_backend, user)  # should not raise

        mock_sync.assert_not_called()

    @override_switch(ENABLE_TPA_ORG_GROUP_LOGIN_SYNC_SWITCH, active=True)
    def test_noop_end_to_end_when_switch_on_but_no_group_mapped_yet(self):
        """
        Locks in the behavior stage 4 of the rollout depends on: with the switch on in
        production but no org yet mapped to a budget group, every login must be a true no-op -
        no membership written, no exception - even running the full chain for real, unmocked.
        """
        enterprise_customer = EnterpriseCustomerFactory()
        EnterpriseCustomerIdentityProviderFactory(
            enterprise_customer=enterprise_customer,
            provider_id='skillsoft-us',
        )
        ecu = EnterpriseCustomerUserFactory(enterprise_customer=enterprise_customer)
        user = User.objects.get(id=ecu.user_id)
        tpa_org_id = str(uuid4())
        # Allowlisted for login, but enterprise_group_uuid intentionally left unset.
        TpaOrgAllowlist.objects.create(enterprise_customer=enterprise_customer, tpa_org_id=tpa_org_id)
        UserSocialAuth.objects.create(
            user=user,
            provider='tpa-saml',
            uid=f'skillsoft-us:{tpa_org_id}',
            extra_data={'percipioOrganizationUuid': tpa_org_id},
        )
        backend = make_backend(tpa_hint='skillsoft-us')

        sync_tpa_budget_group(backend, user)  # real call, nothing mocked

        assert not EnterpriseGroupMembership.available_objects.exists()
