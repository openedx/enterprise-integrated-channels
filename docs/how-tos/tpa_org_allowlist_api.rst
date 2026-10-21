TPA Org Allowlist API
#####################

The TPA Org Allowlist API lets you manage which third-party auth (TPA) org IDs are
permitted to log in to an enterprise customer's edX environment. The Auth0 Post-Login
Action calls the ``validate`` endpoint on every login to decide whether to allow or
deny the attempt.

Endpoints
*********

All endpoints are served by the LMS under ``/channel_integrations/api/v1/tpa-org-allowlist/``.
In production that is ``https://courses.edx.org/channel_integrations/api/v1/tpa-org-allowlist/``.
The trailing slash is optional on every endpoint.

.. important::
   Call the LMS host directly. ``api.edx.org`` is a separate AWS API Gateway that does not
   route this API: requests sent there fail with ``403`` and
   ``Invalid key=value pair (missing equal-sign) in Authorization header``.

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
   * - ``PATCH``
     - ``/tpa-org-allowlist/<id>/``
     - Update ``enterprise_group_uuid`` or ``demo_account`` on an entry
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
     "demo_account": false,
     "enterprise_group_uuid": null
   }

Returns ``201 Created`` with the created record, or ``400 Bad Request`` if the
``(enterprise_customer, tpa_org_id)`` combination already exists.

``enterprise_group_uuid`` is optional and defaults to ``null``, meaning the org is allowlisted
for login but has no Learner Credit budget mapped yet. When set, it must be the UUID of a
budget-type ``EnterpriseGroup`` belonging to the same ``enterprise_customer`` - see
:doc:`onboard_skillsoft_org_budget` for how this field is used to automatically place learners
into the right budget group at login.

Validate an org (``GET /tpa-org-allowlist/validate/``)
=======================================================

The enterprise scope is derived from the caller's ``tpa_org_allowlist_admin`` role
assignment, so a service user scoped to one enterprise doesn't need to pass
``enterprise_customer``:

.. code-block:: bash

   GET /channel_integrations/api/v1/tpa-org-allowlist/validate/?tpa_org_id=11111111-2222-3333-4444-555555555555
   Authorization: JWT <service-user-access-token>

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

Every request needs a JWT access token sent with the ``JWT`` prefix:

.. code-block:: text

   Authorization: JWT <access_token>

The API accepts only JWT and LMS session authentication. A ``Bearer`` prefix is ignored, and
an opaque (non-JWT) OAuth2 access token is rejected; both fail with ``401``. Request tokens
with ``token_type=jwt`` to get a JWT (see `Setting up the service user`_).

Beyond authentication, callers need the ``tpa_org_allowlist_admin`` role. This is a dedicated
role, separate from ``enterprise_admin`` (which does not grant access here), so that it can be
granted narrowly. Grant it with a ``SystemWideEnterpriseUserRoleAssignment`` row linking the
user to the ``tpa_org_allowlist_admin`` role for the relevant enterprise. Superusers bypass the
role check.

.. note::
   Only the database role assignment is checked. A ``tpa_org_allowlist_admin:<uuid>`` entry in
   the JWT ``roles`` claim doesn't grant access on its own, because the LMS's
   ``SYSTEM_TO_FEATURE_ROLE_MAPPING`` has no entry for this role.

Setting up the service user
***************************

The Auth0 Post-Login Action calls ``validate`` as a dedicated edX service user, using the
OAuth2 client-credentials grant to get a short-lived JWT. A dedicated service account keeps
the credentials scoped to this API.

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

Step 3 — Obtain a JWT access token
------------------------------------

Exchange the client credentials for a JWT access token at the LMS token endpoint. Include
``token_type=jwt``: without it the endpoint returns an opaque token, which this API rejects.

.. code-block:: bash

   curl -X POST https://courses.edx.org/oauth2/access_token \
     -d "client_id=<client_id>&client_secret=<client_secret>&grant_type=client_credentials&token_type=jwt"

Send the ``access_token`` from the response as ``Authorization: JWT <access_token>``.

.. note::
   JWT access tokens are short-lived. ``expires_in`` in the response gives the lifetime in
   seconds: 1 hour by default, set by the LMS's ``JWT_ACCESS_TOKEN_EXPIRE_SECONDS``. Don't
   store a token in the Auth0 Action, because it stops working when it expires. Store the
   client id and secret instead, and have the Action request a new token before the cached
   one expires (see `Configure Auth0 Action Secrets`_).

Step 4 — Assign the role
--------------------------

Go to **Django admin → Enterprise → System wide enterprise user role assignments →
Add system wide enterprise user role assignment**.

Fill in:

- **User:** ``auth0-tpa-allowlist-svc``
- **Role:** ``tpa_org_allowlist_admin`` (create it if it does not yet exist)
- **Enterprise customer:** select the target enterprise customer (e.g. Skillsoft)

Save. This role assignment is what gives the service user access to the API. It also sets
the enterprise scope, so ``validate`` doesn't need an ``enterprise_customer`` query
parameter.

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

Then request a JWT access token (``token_type=jwt`` is required):

.. code-block:: bash

   curl -X POST https://courses.edx.org/oauth2/access_token \
     -d "client_id=<client_id>&client_secret=<client_secret>&grant_type=client_credentials&token_type=jwt"

For the Auth0 Action, store the ``client_id`` and ``client_secret``, not the token (see
`Configure Auth0 Action Secrets`_).

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
   * - ``TPA_ORG_TOKEN_URL``
     - LMS OAuth2 token endpoint, e.g. ``https://courses.edx.org/oauth2/access_token``
   * - ``TPA_ORG_CLIENT_ID``
     - Client id of the service user's OAuth2 application
   * - ``TPA_ORG_CLIENT_SECRET``
     - Client secret of the service user's OAuth2 application

Note that ``TPA_ENTERPRISE_CUSTOMER_UUID`` is no longer needed — the enterprise scope
is derived from the service user's role assignment, not from a query parameter.
``TPA_ORG_API_TOKEN`` is no longer used either: a stored JWT stops working when it expires,
so the Action requests its own tokens.

The Action gets a token and calls ``validate`` like this:

.. code-block:: javascript

   // Requests a JWT with the client-credentials grant and caches it for a
   // little less than its lifetime, so a cached token never expires mid-login.
   async function getAccessToken(event, api) {
     const cached = api.cache.get('tpa_org_api_token');
     if (cached) {
       return cached.value;
     }
     const response = await fetch(event.secrets.TPA_ORG_TOKEN_URL, {
       method: 'POST',
       headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
       body: new URLSearchParams({
         grant_type: 'client_credentials',
         client_id: event.secrets.TPA_ORG_CLIENT_ID,
         client_secret: event.secrets.TPA_ORG_CLIENT_SECRET,
         token_type: 'jwt',
       }),
     });
     if (!response.ok) {
       return null;
     }
     const { access_token: accessToken, expires_in: expiresIn } = await response.json();
     api.cache.set('tpa_org_api_token', accessToken, { ttl: (expiresIn - 60) * 1000 });
     return accessToken;
   }

   // Inside onExecutePostLogin:
   const accessToken = await getAccessToken(event, api);
   if (!accessToken) {
     // Fail closed: deny if no token can be obtained
     api.access.deny('Unable to verify organisation authorization.');
     return;
   }

   const response = await fetch(
     `${event.secrets.TPA_ORG_API_URL}/validate/?tpa_org_id=${percipioOrganizationUuid}`,
     { headers: { Authorization: `JWT ${accessToken}` } }
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

Troubleshooting
***************

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Response
     - Cause and fix
   * - ``403`` with ``{"message": "Invalid key=value pair (missing equal-sign) in Authorization header ..."}``
     - The request went to an AWS API Gateway such as ``api.edx.org``, not the LMS. Send it to
       ``https://courses.edx.org`` (or the LMS host of the environment you're testing).
   * - ``401 {"detail": "Authentication credentials were not provided."}``
     - The request has no usable ``Authorization`` header. Usually the header uses the
       ``Bearer`` prefix; send ``Authorization: JWT <access_token>`` instead.
   * - ``401 {"detail": "Invalid token."}``, or another invalid or expired token message
     - The token isn't a valid, unexpired JWT from this LMS. Request a new one with
       ``token_type=jwt``.
   * - ``403 {"detail": "You do not have permission to perform this action."}``
     - The caller has no ``tpa_org_allowlist_admin`` role assignment. Add one (see
       `Setting up the service user`_).
   * - ``400`` on a ``POST``
     - Usually the ``(enterprise_customer, tpa_org_id)`` pair is already allowlisted. The
       response body names the field that failed validation.
