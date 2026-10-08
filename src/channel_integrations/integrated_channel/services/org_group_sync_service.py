"""
Service for syncing a learner's EnterpriseGroup membership to the Learner Credit budget group
mapped to the org they logged in under.
"""
import logging

from django.db import transaction

from enterprise.constants import GROUP_TYPE_BUDGET
from enterprise.models import EnterpriseCustomerUser, EnterpriseGroup, EnterpriseGroupMembership

from channel_integrations.integrated_channel.models import TpaOrgAllowlist
from channel_integrations.integrated_channel.services.tpa_org_id_service import get_tpa_org_id

log = logging.getLogger(__name__)


def sync_learner_budget_group(user, enterprise_customer):
    """
    Ensure the learner's EnterpriseGroupMembership reflects the budget group mapped to the org
    they logged in under, based on the TpaOrgAllowlist entry for their org id.

    No-ops if the learner's org id can't be determined, if the org isn't mapped to a budget
    group yet, or if the mapping is misconfigured. Never raises - this must never block a login.
    """
    if not user:
        return

    try:
        with transaction.atomic():
            _sync_learner_budget_group(user, enterprise_customer)
    except Exception as e:  # pylint: disable=broad-exception-caught
        log.warning(
            f'[OrgGroupSync] Error syncing budget group for user {getattr(user, "id", None)}: {e}',
            exc_info=True,
        )


def _sync_learner_budget_group(user, enterprise_customer):
    """
    Do the actual work of `sync_learner_budget_group`, allowed to raise - the caller wraps this
    in a transaction and a broad try/except.
    """
    tpa_org_id = get_tpa_org_id(user, enterprise_customer)
    if not tpa_org_id:
        log.info(f'[OrgGroupSync] No org id found for user {user.id}, skipping sync')
        return

    allowlist_entry = TpaOrgAllowlist.objects.filter(
        enterprise_customer=enterprise_customer,
        tpa_org_id=tpa_org_id,
        enterprise_group_uuid__isnull=False,
    ).first()
    if not allowlist_entry:
        log.info(
            f'[OrgGroupSync] No budget group mapped for org {tpa_org_id} under enterprise '
            f'{enterprise_customer.uuid} (either not allowlisted, or allowlisted with no group '
            f'mapped yet), skipping sync for user {user.id}'
        )
        return

    group = EnterpriseGroup.available_objects.filter(
        uuid=allowlist_entry.enterprise_group_uuid,
        enterprise_customer_id=enterprise_customer.pk,
        group_type=GROUP_TYPE_BUDGET,
    ).first()
    if not group:
        log.warning(
            f'[OrgGroupSync] Mapped group {allowlist_entry.enterprise_group_uuid} for org '
            f'{tpa_org_id} is missing, removed, belongs to a different enterprise, or is not a '
            f'budget group; skipping sync for user {user.id}'
        )
        return

    enterprise_customer_user = EnterpriseCustomerUser.objects.filter(
        user_id=user.id,
        enterprise_customer=enterprise_customer,
    ).first()
    if not enterprise_customer_user:
        log.warning(
            f'[OrgGroupSync] No EnterpriseCustomerUser found for user {user.id} and enterprise '
            f'{enterprise_customer.uuid}, skipping sync'
        )
        return

    # Use all_objects (not the default manager) so a previously soft-deleted membership for this
    # exact (group, enterprise_customer_user) pair is revived in place, rather than colliding with
    # the model's unique_together constraint when we try to insert a new row.
    _, created = EnterpriseGroupMembership.all_objects.update_or_create(
        group=group,
        enterprise_customer_user=enterprise_customer_user,
        defaults={'is_removed': False},
    )
    log.info(
        f'[OrgGroupSync] {"Created" if created else "Confirmed"} membership for user {user.id} '
        f'in group {group.uuid} (org {tpa_org_id})'
    )

    _cleanup_stale_memberships(enterprise_customer_user, enterprise_customer, keep_group=group)


def _cleanup_stale_memberships(enterprise_customer_user, enterprise_customer, keep_group):
    """
    Remove membership in any OTHER org-mapped budget group under this enterprise_customer.

    Covers the rare case of a learner's org id changing between logins. Only ever touches groups
    that are themselves referenced by a TpaOrgAllowlist row for this enterprise_customer - never
    flex groups, and never budget groups that were assigned manually rather than by this sync.
    """
    other_mapped_group_uuids = list(
        TpaOrgAllowlist.objects.filter(
            enterprise_customer=enterprise_customer,
        ).exclude(
            enterprise_group_uuid__isnull=True,
        ).exclude(
            enterprise_group_uuid=keep_group.uuid,
        ).values_list('enterprise_group_uuid', flat=True)
    )
    if not other_mapped_group_uuids:
        return

    stale_memberships = EnterpriseGroupMembership.available_objects.filter(
        enterprise_customer_user=enterprise_customer_user,
        group_id__in=other_mapped_group_uuids,
    )
    count = stale_memberships.count()
    if count:
        stale_memberships.delete()
        log.info(
            f'[OrgGroupSync] Removed {count} stale org-derived group membership(s) for '
            f'EnterpriseCustomerUser {enterprise_customer_user.id}'
        )
