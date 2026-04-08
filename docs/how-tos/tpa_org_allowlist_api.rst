TPA Org Allowlist API
#####################

The TPA Org Allowlist API lets you manage which third-party auth (TPA) org IDs are
permitted to log in to an enterprise customer's edX environment. The Auth0 Post-Login
Action calls the ``validate`` endpoint on every login to decide whether to allow or
deny the attempt.

Endpoints
*********

All endpoints are under ``/channel_integrations/api/v1/tpa-org-allowlist/``.

.. list-table::
   :widths: 10 40 50
   :header-rows: 1

   * - Method
     - URL
     - Description
   * - ``GET``
     - ``/tpa-org-allowlist/?enterprise_customer=<uuid>``
     - List all allowlisted org IDs for an enterprise customer
   * - ``POST``
     - ``/tpa-org-allowlist/``
     - Add an org ID to the allowlist
   * - ``GET``
     - ``/tpa-org-allowlist/<id>/``
     - Retrieve a single allowlist entry
   * - ``DELETE``
     - ``/tpa-org-allowlist/<id>/``
     - Remove an org ID from the allowlist
   * - ``GET``
     - ``/tpa-org-allowlist/validate/?tpa_org_id=<uuid>``
     - Returns ``200`` if the org is allowlisted, ``404`` if not

The ``validate`` endpoint is the one called by the Auth0 Action at login time. It only
checks the HTTP status code — ``200`` means authorised, ``404`` means denied.

Request / response examples
****************************

Add an org (``POST /tpa-org-allowlist/``)
==========================================

.. code-block:: json

   {
     "enterprise_customer": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
     "tpa_org_id": "11111111-2222-3333-4444-555555555555",
     "demo_account": false
   }

Returns ``201 Created`` with the created record, or ``400 Bad Request`` if the
``(enterprise_customer, tpa_org_id)`` combination already exists.

Validate an org (``GET /tpa-org-allowlist/validate/``)
=======================================================

The enterprise scope is derived automatically from the caller's credentials — the
service user's token encodes which enterprise it belongs to, so no ``enterprise_customer``
parameter is needed:

.. code-block:: bash

   GET /channel_integrations/api/v1/tpa-org-allowlist/validate/?tpa_org_id=11111111-2222-3333-4444-555555555555
   Authorization: Bearer <service-user-token>

Returns ``200 {"detail": "Authorised."}`` if the org is in the allowlist, or
``404 {"detail": "Not found."}`` if it is not.

Callers whose token has global (superuser) access must supply ``enterprise_customer``
explicitly — the API cannot infer a single enterprise from an unrestricted token:

.. code-block:: bash

   GET /channel_integrations/api/v1/tpa-org-allowlist/validate/
       ?enterprise_customer=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee
       &tpa_org_id=11111111-2222-3333-4444-555555555555

Authentication and permissions
*******************************

All endpoints require a valid JWT (``Authorization: Bearer <token>``). Beyond
authentication, callers also need the ``tpa_org_allowlist_admin`` role.

This is a dedicated role — separate from the general ``enterprise_admin`` role — so
that it can be granted narrowly. The role is checked in two ways:

- **Implicit (JWT):** The JWT ``roles`` claim must contain
  ``tpa_org_allowlist_admin:<enterprise_customer_uuid>``.
- **Explicit (database):** A ``SystemWideEnterpriseUserRoleAssignment`` row must exist
  linking the user to the ``tpa_org_allowlist_admin`` role for the relevant enterprise.

Setting up the service user
***************************

The Auth0 Post-Login Action needs a long-lived bearer token to call ``validate``.
The recommended approach is a dedicated edX service account so that the token scope
is limited to this API.

Via the Django admin UI
=======================

Step 1 — Create the service account user
-----------------------------------------

Go to **Django admin → Authentication and Authorization → Users → Add user**.

Fill in:

- **Username:** ``auth0-tpa-allowlist-svc``
- **Password:** generate a strong random password (it will never be used interactively)

Save, then on the detail page ensure **Active** is checked. Leave ``Staff status`` and
``Superuser status`` unchecked.

Step 2 — Create an OAuth2 application
---------------------------------------

Go to **Django admin → Django OAuth Toolkit → Applications → Add application**.

Fill in:

- **User:** ``auth0-tpa-allowlist-svc`` (the user created above)
- **Client type:** ``Confidential``
- **Authorization grant type:** ``Client credentials``
- **Name:** ``auth0-tpa-allowlist-svc``

Save and note the generated **Client id** and **Client secret**.

Step 3 — Obtain a bearer token
--------------------------------

Exchange the client credentials for a token:

.. code-block:: bash

   curl -X POST https://<edx-host>/oauth2/access_token \
     -d "client_id=<client_id>&client_secret=<client_secret>&grant_type=client_credentials"

Store the ``access_token`` from the response — this goes into the Auth0 Action Secret
``TPA_ORG_API_TOKEN``.

.. note::
   Check ``expires_in`` against your Auth0 Action caching policy. If the token expires
   before the Action cache is refreshed, subsequent logins will get 401 errors. Either
   configure a sufficiently long token lifetime in the OAuth2 application settings, or
   add token-refresh logic to the Action.

Step 4 — Assign the role
--------------------------

Go to **Django admin → Enterprise → System wide enterprise user role assignments →
Add system wide enterprise user role assignment**.

Fill in:

- **User:** ``auth0-tpa-allowlist-svc``
- **Role:** ``tpa_org_allowlist_admin`` (create it if it does not yet exist)
- **Enterprise customer:** select the target enterprise customer (e.g. Skillsoft)

Save. This role assignment is what allows the service user to call ``validate`` without
passing ``enterprise_customer`` as a query parameter — the enterprise scope is read
directly from the assignment.

Step 5 — Configure Auth0 Action Secrets
-----------------------------------------

See `Configure Auth0 Action Secrets`_ below.

Via the Django shell
====================

Step 1 — Create the service account user
-----------------------------------------

.. code-block:: python

   from django.contrib.auth import get_user_model
   User = get_user_model()
   user = User.objects.create_user(
       username='auth0-tpa-allowlist-svc',
       email='auth0-tpa-allowlist-svc@example.com',
       is_active=True,
   )

Step 2 — Issue an OAuth2 application and obtain a token
---------------------------------------------------------

.. code-block:: python

   from oauth2_provider.models import Application
   import secrets

   app = Application.objects.create(
       user=user,
       name='auth0-tpa-allowlist-svc',
       client_type=Application.CLIENT_CONFIDENTIAL,
       authorization_grant_type=Application.GRANT_CLIENT_CREDENTIALS,
       client_secret=secrets.token_urlsafe(40),
   )
   print('client_id:', app.client_id)
   print('client_secret:', app.client_secret)

Then exchange for a token:

.. code-block:: bash

   curl -X POST https://<edx-host>/oauth2/access_token \
     -d "client_id=<client_id>&client_secret=<client_secret>&grant_type=client_credentials"

Store the ``access_token`` as ``TPA_ORG_API_TOKEN`` in Auth0 Action Secrets.

Step 3 — Assign the role
--------------------------

.. code-block:: python

   from enterprise.models import EnterpriseCustomer, SystemWideEnterpriseRole, SystemWideEnterpriseUserRoleAssignment

   enterprise_customer = EnterpriseCustomer.objects.get(uuid='aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee')
   role, _ = SystemWideEnterpriseRole.objects.get_or_create(name='tpa_org_allowlist_admin')
   SystemWideEnterpriseUserRoleAssignment.objects.get_or_create(
       user=user,
       role=role,
       enterprise_customer=enterprise_customer,
   )

.. _Configure Auth0 Action Secrets:

Configure Auth0 Action Secrets
================================

Add the following secrets to the Auth0 Post-Login Action:

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Secret name
     - Value
   * - ``TPA_ORG_API_URL``
     - Base URL, e.g. ``https://courses.edx.org/channel_integrations/api/v1/tpa-org-allowlist``
   * - ``TPA_ORG_API_TOKEN``
     - The bearer token obtained in Step 2

Note that ``TPA_ENTERPRISE_CUSTOMER_UUID`` is no longer needed — the enterprise scope
is derived from the service user's role assignment, not from a query parameter.

The Action calls ``validate`` like this:

.. code-block:: javascript

   const response = await fetch(
     `${event.secrets.TPA_ORG_API_URL}/validate/?tpa_org_id=${percipioOrganizationUuid}`,
     { headers: { Authorization: `Bearer ${event.secrets.TPA_ORG_API_TOKEN}` } }
   );

   if (response.status === 404) {
     api.access.deny('Unauthorized organisation.');
     return;
   }
   if (!response.ok) {
     // Fail closed: deny if the API is unreachable
     api.access.deny('Unable to verify organisation authorization.');
     return;
   }
   // 200 — authorised, continue
