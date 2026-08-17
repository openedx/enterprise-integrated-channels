"""
Tests for org_group_sync_service.py.
"""
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from enterprise.models import EnterpriseGroupMembership

from channel_integrations.integrated_channel.models import TpaOrgAllowlist
from channel_integrations.integrated_channel.services.org_group_sync_service import sync_learner_budget_group
from test_utils.factories import (
    EnterpriseCustomerFactory,
    EnterpriseCustomerUserFactory,
    EnterpriseGroupFactory,
    EnterpriseGroupMembershipFactory,
    UserFactory,
)

User = get_user_model()

PATCH_GET_TPA_ORG_ID = 'channel_integrations.integrated_channel.services.org_group_sync_service.get_tpa_org_id'


@pytest.mark.django_db
class TestSyncLearnerBudgetGroup:
    """Tests for sync_learner_budget_group."""

    def test_noop_when_no_org_id_found(self):
        """No org id resolved from SSO metadata is a silent no-op."""
        user = UserFactory()
        enterprise_customer = EnterpriseCustomerFactory()

        with patch(PATCH_GET_TPA_ORG_ID, return_value=None):
            sync_learner_budget_group(user, enterprise_customer)

        assert not EnterpriseGroupMembership.available_objects.exists()

    def test_noop_when_no_allowlist_entry(self):
        """An org id with no matching TpaOrgAllowlist row is a silent no-op."""
        user = UserFactory()
        enterprise_customer = EnterpriseCustomerFactory()

        with patch(PATCH_GET_TPA_ORG_ID, return_value=str(uuid4())):
            sync_learner_budget_group(user, enterprise_customer)

        assert not EnterpriseGroupMembership.available_objects.exists()

    def test_noop_when_group_mapping_is_null(self):
        """An allowlisted org with no enterprise_group_uuid set yet is a silent no-op."""
        user = UserFactory()
        enterprise_customer = EnterpriseCustomerFactory()
        tpa_org_id = str(uuid4())
        TpaOrgAllowlist.objects.create(enterprise_customer=enterprise_customer, tpa_org_id=tpa_org_id)

        with patch(PATCH_GET_TPA_ORG_ID, return_value=tpa_org_id):
            sync_learner_budget_group(user, enterprise_customer)

        assert not EnterpriseGroupMembership.available_objects.exists()

    def test_noop_when_mapped_group_belongs_to_different_enterprise(self):
        """A group mapping pointing at another enterprise's group is rejected, not applied."""
        user = UserFactory()
        enterprise_customer = EnterpriseCustomerFactory()
        other_enterprise = EnterpriseCustomerFactory()
        group = EnterpriseGroupFactory(enterprise_customer=other_enterprise)
        tpa_org_id = str(uuid4())
        TpaOrgAllowlist.objects.create(
            enterprise_customer=enterprise_customer,
            tpa_org_id=tpa_org_id,
            enterprise_group_uuid=group.uuid,
        )

        with patch(PATCH_GET_TPA_ORG_ID, return_value=tpa_org_id):
            sync_learner_budget_group(user, enterprise_customer)

        assert not EnterpriseGroupMembership.available_objects.exists()

    def test_noop_when_mapped_group_is_not_budget_type(self):
        """A group mapping pointing at a flex-type group is rejected, not applied."""
        user = UserFactory()
        enterprise_customer = EnterpriseCustomerFactory()
        group = EnterpriseGroupFactory(enterprise_customer=enterprise_customer, group_type='flex')
        tpa_org_id = str(uuid4())
        TpaOrgAllowlist.objects.create(
            enterprise_customer=enterprise_customer,
            tpa_org_id=tpa_org_id,
            enterprise_group_uuid=group.uuid,
        )

        with patch(PATCH_GET_TPA_ORG_ID, return_value=tpa_org_id):
            sync_learner_budget_group(user, enterprise_customer)

        assert not EnterpriseGroupMembership.available_objects.exists()

    def test_noop_when_no_matching_enterprise_customer_user(self):
        """No EnterpriseCustomerUser link for this user+customer is a silent no-op."""
        user = UserFactory()
        enterprise_customer = EnterpriseCustomerFactory()
        group = EnterpriseGroupFactory(enterprise_customer=enterprise_customer)
        tpa_org_id = str(uuid4())
        TpaOrgAllowlist.objects.create(
            enterprise_customer=enterprise_customer,
            tpa_org_id=tpa_org_id,
            enterprise_group_uuid=group.uuid,
        )

        with patch(PATCH_GET_TPA_ORG_ID, return_value=tpa_org_id):
            sync_learner_budget_group(user, enterprise_customer)

        assert not EnterpriseGroupMembership.available_objects.exists()

    def test_happy_path_creates_membership(self):
        """A fully valid mapping creates a new EnterpriseGroupMembership."""
        enterprise_customer = EnterpriseCustomerFactory()
        ecu = EnterpriseCustomerUserFactory(enterprise_customer=enterprise_customer)
        user = User.objects.get(id=ecu.user_id)
        group = EnterpriseGroupFactory(enterprise_customer=enterprise_customer)
        tpa_org_id = str(uuid4())
        TpaOrgAllowlist.objects.create(
            enterprise_customer=enterprise_customer,
            tpa_org_id=tpa_org_id,
            enterprise_group_uuid=group.uuid,
        )

        with patch(PATCH_GET_TPA_ORG_ID, return_value=tpa_org_id):
            sync_learner_budget_group(user, enterprise_customer)

        membership = EnterpriseGroupMembership.available_objects.get(group=group, enterprise_customer_user=ecu)
        assert not membership.is_removed

    def test_happy_path_is_idempotent(self):
        """Running the sync twice for the same learner/org doesn't create a duplicate row."""
        enterprise_customer = EnterpriseCustomerFactory()
        ecu = EnterpriseCustomerUserFactory(enterprise_customer=enterprise_customer)
        user = User.objects.get(id=ecu.user_id)
        group = EnterpriseGroupFactory(enterprise_customer=enterprise_customer)
        tpa_org_id = str(uuid4())
        TpaOrgAllowlist.objects.create(
            enterprise_customer=enterprise_customer,
            tpa_org_id=tpa_org_id,
            enterprise_group_uuid=group.uuid,
        )

        with patch(PATCH_GET_TPA_ORG_ID, return_value=tpa_org_id):
            sync_learner_budget_group(user, enterprise_customer)
            sync_learner_budget_group(user, enterprise_customer)

        assert EnterpriseGroupMembership.available_objects.filter(
            group=group, enterprise_customer_user=ecu
        ).count() == 1

    def test_revives_soft_deleted_membership(self):
        """A previously soft-deleted membership for the same (group, ecu) pair is revived, not duplicated."""
        enterprise_customer = EnterpriseCustomerFactory()
        ecu = EnterpriseCustomerUserFactory(enterprise_customer=enterprise_customer)
        user = User.objects.get(id=ecu.user_id)
        group = EnterpriseGroupFactory(enterprise_customer=enterprise_customer)
        tpa_org_id = str(uuid4())
        TpaOrgAllowlist.objects.create(
            enterprise_customer=enterprise_customer,
            tpa_org_id=tpa_org_id,
            enterprise_group_uuid=group.uuid,
        )
        existing = EnterpriseGroupMembershipFactory(group=group, enterprise_customer_user=ecu)
        existing.delete()  # soft delete: is_removed=True
        assert EnterpriseGroupMembership.all_objects.get(pk=existing.pk).is_removed

        with patch(PATCH_GET_TPA_ORG_ID, return_value=tpa_org_id):
            sync_learner_budget_group(user, enterprise_customer)

        revived = EnterpriseGroupMembership.all_objects.get(pk=existing.pk)
        assert not revived.is_removed
        assert EnterpriseGroupMembership.all_objects.filter(group=group, enterprise_customer_user=ecu).count() == 1

    def test_stale_membership_cleanup_removes_other_mapped_group(self):
        """
        A learner whose org id changed loses membership in their OLD org-mapped group once
        synced into the new one.
        """
        enterprise_customer = EnterpriseCustomerFactory()
        ecu = EnterpriseCustomerUserFactory(enterprise_customer=enterprise_customer)
        user = User.objects.get(id=ecu.user_id)

        old_group = EnterpriseGroupFactory(enterprise_customer=enterprise_customer)
        old_org_id = str(uuid4())
        TpaOrgAllowlist.objects.create(
            enterprise_customer=enterprise_customer,
            tpa_org_id=old_org_id,
            enterprise_group_uuid=old_group.uuid,
        )
        EnterpriseGroupMembershipFactory(group=old_group, enterprise_customer_user=ecu)

        new_group = EnterpriseGroupFactory(enterprise_customer=enterprise_customer)
        new_org_id = str(uuid4())
        TpaOrgAllowlist.objects.create(
            enterprise_customer=enterprise_customer,
            tpa_org_id=new_org_id,
            enterprise_group_uuid=new_group.uuid,
        )

        with patch(PATCH_GET_TPA_ORG_ID, return_value=new_org_id):
            sync_learner_budget_group(user, enterprise_customer)

        assert EnterpriseGroupMembership.available_objects.filter(
            group=new_group, enterprise_customer_user=ecu
        ).exists()
        assert not EnterpriseGroupMembership.available_objects.filter(
            group=old_group, enterprise_customer_user=ecu
        ).exists()

    def test_stale_cleanup_noop_when_no_membership_in_other_mapped_group(self):
        """
        Other org-mapped groups existing under the same enterprise doesn't mean there's anything
        to clean up - a first-time sync where the learner never had a membership anywhere else
        must not error or delete anything.
        """
        enterprise_customer = EnterpriseCustomerFactory()
        ecu = EnterpriseCustomerUserFactory(enterprise_customer=enterprise_customer)
        user = User.objects.get(id=ecu.user_id)

        other_group = EnterpriseGroupFactory(enterprise_customer=enterprise_customer)
        TpaOrgAllowlist.objects.create(
            enterprise_customer=enterprise_customer,
            tpa_org_id=str(uuid4()),
            enterprise_group_uuid=other_group.uuid,
        )

        new_group = EnterpriseGroupFactory(enterprise_customer=enterprise_customer)
        tpa_org_id = str(uuid4())
        TpaOrgAllowlist.objects.create(
            enterprise_customer=enterprise_customer,
            tpa_org_id=tpa_org_id,
            enterprise_group_uuid=new_group.uuid,
        )

        with patch(PATCH_GET_TPA_ORG_ID, return_value=tpa_org_id):
            sync_learner_budget_group(user, enterprise_customer)

        assert EnterpriseGroupMembership.available_objects.filter(
            group=new_group, enterprise_customer_user=ecu
        ).exists()

    def test_stale_membership_cleanup_does_not_touch_non_allowlist_backed_group(self):
        """
        Cleanup must never remove membership in a group that isn't itself referenced by a
        TpaOrgAllowlist row - e.g. a manually-curated budget group or a flex group.
        """
        enterprise_customer = EnterpriseCustomerFactory()
        ecu = EnterpriseCustomerUserFactory(enterprise_customer=enterprise_customer)
        user = User.objects.get(id=ecu.user_id)

        manual_group = EnterpriseGroupFactory(enterprise_customer=enterprise_customer, group_type='flex')
        EnterpriseGroupMembershipFactory(group=manual_group, enterprise_customer_user=ecu)

        new_group = EnterpriseGroupFactory(enterprise_customer=enterprise_customer)
        tpa_org_id = str(uuid4())
        TpaOrgAllowlist.objects.create(
            enterprise_customer=enterprise_customer,
            tpa_org_id=tpa_org_id,
            enterprise_group_uuid=new_group.uuid,
        )

        with patch(PATCH_GET_TPA_ORG_ID, return_value=tpa_org_id):
            sync_learner_budget_group(user, enterprise_customer)

        assert EnterpriseGroupMembership.available_objects.filter(
            group=manual_group, enterprise_customer_user=ecu
        ).exists()

    def test_exceptions_are_swallowed_and_never_raise(self):
        """Any unexpected exception during the sync is caught, logged, and never propagates."""
        user = UserFactory()
        enterprise_customer = EnterpriseCustomerFactory()

        with patch(PATCH_GET_TPA_ORG_ID, side_effect=Exception('boom')):
            sync_learner_budget_group(user, enterprise_customer)  # should not raise

        assert not EnterpriseGroupMembership.available_objects.exists()

    def test_none_user_does_not_raise(self):
        """
        a None user must not crash, including inside the outer except's own
        log statement (which previously accessed user.id directly.
        """
        enterprise_customer = EnterpriseCustomerFactory()

        sync_learner_budget_group(None, enterprise_customer)  # should not raise

        assert not EnterpriseGroupMembership.available_objects.exists()
