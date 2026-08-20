Onboard a Skillsoft Org's Learner Credit Budget
################################################

Background
**********

Skillsoft has a dedicated ``EnterpriseCustomer`` for Exec Ed, with a separate Learner Credit
budget per Skillsoft org (identified by the org id asserted by their SAML IdP,
``percipioOrganizationUuid``). A learner should only be able to redeem from the budget matching
the org they logged in under.

This is enforced by two things working together, both of which already exist:

- ``enterprise-access``'s ``SubsidyAccessPolicy`` can be scoped to a subset of learners via a
  ``PolicyGroupAssociation`` linking the policy to an ``EnterpriseGroup``.
- Once ``enable_tpa_org_group_login_sync`` is enabled (see the ENT-12084 rollout plan), a learner
  is automatically placed into the ``EnterpriseGroup`` mapped to their org's
  :doc:`tpa_org_allowlist_api` entry every time they log in, keeping their membership in sync
  with the org they're currently asserting.

Onboarding a new org's budget means wiring these two things together for that org. No new
engineering work is required to do this - every step below uses tooling that already exists.

Steps
*****

1. Create the budget group
===========================

Create an ``EnterpriseGroup`` with ``group_type="budget"`` for the org, scoped to the Skillsoft
Exec Ed ``EnterpriseCustomer``. Either:

- ``POST /enterprise/api/v1/enterprise-group/`` with ``enterprise_customer``, ``name``, and
  ``group_type: "budget"``, or
- Django admin → **Enterprise → Enterprise groups → Add enterprise group**.

Note the group's ``uuid`` - you'll need it in step 3.

2. Link the budget to the group
================================

Create (or reuse) the org's ``SubsidyAccessPolicy`` in ``enterprise-access``, then link it to the
group from step 1 via a ``PolicyGroupAssociation``. This is Django admin only today - there is no
REST create endpoint for ``PolicyGroupAssociation`` yet (a known gap, not something this doc's
scope covers): Django admin → **Subsidy Access Policy → Policy group associations → Add**.

3. Map the org to the budget group
===================================

Set ``enterprise_group_uuid`` on the org's :doc:`tpa_org_allowlist_api` entry to the group's
``uuid`` from step 1:

.. code-block:: bash

   PATCH /channel_integrations/api/v1/tpa-org-allowlist/<id>/
   {
     "enterprise_group_uuid": "<budget-group-uuid>"
   }

Once this is set, the login-time sync takes over: any learner asserting this org id at login is
automatically added to the budget group, and any stale membership in a *different* org-mapped
budget group under the same customer is cleaned up. Nobody needs to maintain a manual list of
learner emails for this org going forward.

.. note::
   ``enterprise_customer`` and ``tpa_org_id`` are read-only once a row exists - a PATCH can only
   ever set ``enterprise_group_uuid`` (or ``demo_account``) on an existing entry, never move it
   to a different org or enterprise. To fix a typo in either field, delete the row and create a
   new one instead.

.. note::
   Before this field is set, the org is still allowlisted for login (the SSO gate keeps working)
   - it simply has no budget mapped yet. Setting this field is what turns the automation on for
   that specific org; it's a data change, not a deploy.

4. Smoke test
=============

Log in as a test learner asserting this org id, then verify:

- An ``EnterpriseGroupMembership`` was created linking the learner to the budget group from
  step 1.
- ``SubsidyAccessPolicy.can_redeem()`` for that budget returns a positive result for the test
  learner, and a negative result for a learner asserting a *different* org.

Things to watch for
********************

- **Cross-policy uniqueness isn't enforced.** ``includes_learner()`` has no check preventing a
  learner from being a member of two different budget groups under the same customer. If that
  happens, they can redeem from either budget. Double-check step 2 wasn't accidentally repeated
  against the wrong group when onboarding a new org.
- **A null ``enterprise_group_uuid`` is not an error.** If a learner logs in under an org that's
  allowlisted but not yet mapped to a budget (steps 1-3 not done yet), the sync silently no-ops.
  That's expected during rollout, not a bug to chase.
