"""
Tests for the TPA Org Allowlist API.
"""
from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from django.contrib.auth import get_user_model

from enterprise.models import SystemWideEnterpriseRole, SystemWideEnterpriseUserRoleAssignment

from channel_integrations.integrated_channel.constants import TPA_ORG_ALLOWLIST_ADMIN_ROLE
from channel_integrations.integrated_channel.models import TpaOrgAllowlist
from test_utils.factories import EnterpriseCustomerFactory, UserFactory

User = get_user_model()

TPA_ORG_ALLOWLIST_URL = '/channel_integrations/api/v1/tpa-org-allowlist/'


@pytest.fixture
def enterprise_customer():
    return EnterpriseCustomerFactory()


@pytest.fixture
def admin_user():
    user = UserFactory(username='tpa_test_admin', is_active=True, is_superuser=True, is_staff=True)
    user.set_password('password')
    user.save()
    return user


@pytest.fixture
def regular_user():
    """Non-superuser without any role assignment."""
    user = UserFactory(username='tpa_test_regular', is_active=True, is_superuser=False, is_staff=False)
    user.set_password('password')
    user.save()
    return user


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def authenticated_client(api_client, admin_user):  # pylint: disable=redefined-outer-name
    """
    Return an API client authenticated as a superuser (bypasses permission checks).
    """
    api_client.force_authenticate(user=admin_user)
    return api_client


@pytest.mark.django_db
class TestTpaOrgAllowlistCreate:
    """Tests for POST /tpa-org-allowlist/"""

    def test_create_entry_returns_201(self, authenticated_client, enterprise_customer):  # pylint: disable=redefined-outer-name
        """POST with valid data creates an entry and returns 201."""
        payload = {
            'enterprise_customer': str(enterprise_customer.uuid),
            'tpa_org_id': str(uuid4()),
            'demo_account': False,
        }
        response = authenticated_client.post(TPA_ORG_ALLOWLIST_URL, data=payload, format='json')
        assert response.status_code == 201
        assert TpaOrgAllowlist.objects.filter(
            enterprise_customer=enterprise_customer,
            tpa_org_id=payload['tpa_org_id'],
        ).exists()

    def test_create_duplicate_returns_400(self, authenticated_client, enterprise_customer):  # pylint: disable=redefined-outer-name
        """POST with duplicate (enterprise_customer, tpa_org_id) returns 400."""
        tpa_org_id = str(uuid4())
        TpaOrgAllowlist.objects.create(
            enterprise_customer=enterprise_customer,
            tpa_org_id=tpa_org_id,
        )
        payload = {
            'enterprise_customer': str(enterprise_customer.uuid),
            'tpa_org_id': tpa_org_id,
        }
        response = authenticated_client.post(TPA_ORG_ALLOWLIST_URL, data=payload, format='json')
        assert response.status_code == 400


@pytest.mark.django_db
class TestTpaOrgAllowlistList:
    """Tests for GET /tpa-org-allowlist/?enterprise_customer=<uuid>"""

    def test_list_scoped_to_enterprise_customer(self, authenticated_client):  # pylint: disable=redefined-outer-name
        """GET with enterprise_customer param returns only entries for that customer."""
        ec1 = EnterpriseCustomerFactory()
        ec2 = EnterpriseCustomerFactory()

        TpaOrgAllowlist.objects.create(enterprise_customer=ec1, tpa_org_id=str(uuid4()))
        TpaOrgAllowlist.objects.create(enterprise_customer=ec1, tpa_org_id=str(uuid4()))
        TpaOrgAllowlist.objects.create(enterprise_customer=ec2, tpa_org_id=str(uuid4()))

        response = authenticated_client.get(
            TPA_ORG_ALLOWLIST_URL, {'enterprise_customer': str(ec1.uuid)}
        )
        assert response.status_code == 200
        assert len(response.data) == 2
        for entry in response.data:
            assert str(entry['enterprise_customer']) == str(ec1.uuid)


@pytest.mark.django_db
class TestTpaOrgAllowlistDelete:
    """Tests for DELETE /tpa-org-allowlist/<id>/"""

    def test_delete_returns_204(self, authenticated_client, enterprise_customer):  # pylint: disable=redefined-outer-name
        """DELETE on existing entry removes it and returns 204."""
        entry = TpaOrgAllowlist.objects.create(
            enterprise_customer=enterprise_customer,
            tpa_org_id=str(uuid4()),
        )
        url = f'{TPA_ORG_ALLOWLIST_URL}{entry.id}/'
        response = authenticated_client.delete(url)
        assert response.status_code == 204
        assert not TpaOrgAllowlist.objects.filter(pk=entry.id).exists()

    def test_cannot_delete_entry_belonging_to_different_enterprise(self, api_client, enterprise_customer):  # pylint: disable=redefined-outer-name
        """A scoped user cannot delete an entry belonging to a different enterprise customer."""
        other_enterprise = EnterpriseCustomerFactory()
        entry = TpaOrgAllowlist.objects.create(
            enterprise_customer=other_enterprise,
            tpa_org_id=str(uuid4()),
        )

        scoped_user = UserFactory(username='tpa_svc_del', is_active=True, is_superuser=False, is_staff=False)
        scoped_user.set_password('password')
        scoped_user.save()
        role, _ = SystemWideEnterpriseRole.objects.get_or_create(name=TPA_ORG_ALLOWLIST_ADMIN_ROLE)
        SystemWideEnterpriseUserRoleAssignment.objects.create(
            user=scoped_user,
            role=role,
            enterprise_customer=enterprise_customer,  # scoped to a DIFFERENT enterprise than the entry
        )

        api_client.force_authenticate(user=scoped_user)

        url = f'{TPA_ORG_ALLOWLIST_URL}{entry.id}/'
        response = api_client.delete(url)
        assert response.status_code == 404
        assert TpaOrgAllowlist.objects.filter(pk=entry.id).exists()

    def test_cannot_retrieve_entry_belonging_to_different_enterprise(self, api_client, enterprise_customer):  # pylint: disable=redefined-outer-name
        """A scoped user cannot retrieve an entry belonging to a different enterprise customer."""
        other_enterprise = EnterpriseCustomerFactory()
        entry = TpaOrgAllowlist.objects.create(
            enterprise_customer=other_enterprise,
            tpa_org_id=str(uuid4()),
        )

        scoped_user = UserFactory(username='tpa_svc_get', is_active=True, is_superuser=False, is_staff=False)
        scoped_user.set_password('password')
        scoped_user.save()
        role, _ = SystemWideEnterpriseRole.objects.get_or_create(name=TPA_ORG_ALLOWLIST_ADMIN_ROLE)
        SystemWideEnterpriseUserRoleAssignment.objects.create(
            user=scoped_user,
            role=role,
            enterprise_customer=enterprise_customer,
        )

        api_client.force_authenticate(user=scoped_user)

        url = f'{TPA_ORG_ALLOWLIST_URL}{entry.id}/'
        response = api_client.get(url)
        assert response.status_code == 404


@pytest.mark.django_db
class TestTpaOrgAllowlistValidate:
    """Tests for GET /tpa-org-allowlist/validate/"""

    VALIDATE_URL = f'{TPA_ORG_ALLOWLIST_URL}validate/'

    def test_validate_org_in_allowlist_returns_200(self, authenticated_client, enterprise_customer):  # pylint: disable=redefined-outer-name
        """validate/ returns 200 when tpa_org_id is in the allowlist."""
        tpa_org_id = str(uuid4())
        TpaOrgAllowlist.objects.create(
            enterprise_customer=enterprise_customer,
            tpa_org_id=tpa_org_id,
        )
        response = authenticated_client.get(self.VALIDATE_URL, {
            'enterprise_customer': str(enterprise_customer.uuid),
            'tpa_org_id': tpa_org_id,
        })
        assert response.status_code == 200
        assert response.data['detail'] == 'Authorised.'

    def test_validate_org_not_in_allowlist_returns_404(self, authenticated_client, enterprise_customer):  # pylint: disable=redefined-outer-name
        """validate/ returns 404 when tpa_org_id is not in the allowlist."""
        response = authenticated_client.get(self.VALIDATE_URL, {
            'enterprise_customer': str(enterprise_customer.uuid),
            'tpa_org_id': str(uuid4()),
        })
        assert response.status_code == 404
        assert response.data['detail'] == 'Not found.'

    def test_validate_missing_tpa_org_id_returns_400(self, authenticated_client, enterprise_customer):  # pylint: disable=redefined-outer-name
        """validate/ returns 400 when tpa_org_id is missing."""
        response = authenticated_client.get(self.VALIDATE_URL, {'enterprise_customer': str(enterprise_customer.uuid)})
        assert response.status_code == 400
        assert 'tpa_org_id is required' in response.data['detail']

    def test_validate_global_token_without_enterprise_customer_returns_400(self, authenticated_client):  # pylint: disable=redefined-outer-name
        """validate/ returns 400 when a global-access token omits enterprise_customer."""
        # admin_user is a superuser — has ALL_ACCESS_CONTEXT, so enterprise_customer is required
        response = authenticated_client.get(self.VALIDATE_URL, {'tpa_org_id': str(uuid4())})
        assert response.status_code == 400
        assert 'enterprise_customer is required for tokens with global access' in response.data['detail']

    def test_validate_global_token_with_invalid_enterprise_customer_returns_400(self, authenticated_client):  # pylint: disable=redefined-outer-name
        """validate/ returns 400 (not 500) when enterprise_customer is not a valid UUID."""
        response = authenticated_client.get(
            self.VALIDATE_URL,
            {'tpa_org_id': str(uuid4()), 'enterprise_customer': 'not-a-uuid'},
        )
        assert response.status_code == 400
        assert 'not a valid uuid' in response.data['detail'].lower()

    def test_validate_scoped_user_derives_enterprise_from_role_assignment(self, api_client, enterprise_customer):  # pylint: disable=redefined-outer-name
        """
        A service user with a DB role assignment does not need to pass enterprise_customer —
        the enterprise UUID is derived from their assigned contexts.
        """
        scoped_user = UserFactory(username='tpa_svc', is_active=True, is_superuser=False, is_staff=False)
        scoped_user.set_password('password')
        scoped_user.save()

        role, _ = SystemWideEnterpriseRole.objects.get_or_create(name=TPA_ORG_ALLOWLIST_ADMIN_ROLE)
        SystemWideEnterpriseUserRoleAssignment.objects.create(
            user=scoped_user,
            role=role,
            enterprise_customer=enterprise_customer,
        )

        api_client.force_authenticate(user=scoped_user)

        tpa_org_id = str(uuid4())
        TpaOrgAllowlist.objects.create(enterprise_customer=enterprise_customer, tpa_org_id=tpa_org_id)

        # No enterprise_customer param — derived from the role assignment
        response = api_client.get(self.VALIDATE_URL, {'tpa_org_id': tpa_org_id})
        assert response.status_code == 200
        assert response.data['detail'] == 'Authorised.'


@pytest.mark.django_db
class TestTpaOrgAllowlistAuthentication:
    """Tests for unauthenticated and unauthorised access."""

    def test_unauthenticated_request_is_denied(self):
        """Unauthenticated request to any endpoint is denied."""
        client = APIClient()
        response = client.get(TPA_ORG_ALLOWLIST_URL)
        assert response.status_code in (401, 403)

    def test_user_without_role_is_forbidden(self, api_client, regular_user, enterprise_customer):  # pylint: disable=redefined-outer-name
        """User authenticated but lacking tpa_org_allowlist_admin role receives 403."""
        api_client.force_authenticate(user=regular_user)
        response = api_client.post(
            TPA_ORG_ALLOWLIST_URL,
            data={
                'enterprise_customer': str(enterprise_customer.uuid),
                'tpa_org_id': str(uuid4()),
            },
            format='json',
        )
        assert response.status_code == 403
