"""
Tests for integrated_channel admin.
"""
import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from channel_integrations.integrated_channel.admin import WebhookTransmissionQueueAdmin
from channel_integrations.integrated_channel.models import WebhookTransmissionQueue

User = get_user_model()


@pytest.mark.django_db
class TestWebhookTransmissionQueueAdmin:
    """Tests for WebhookTransmissionQueueAdmin."""

    def test_has_add_permission_returns_true_for_superuser(self):
        """
        Verify that superusers can manually create webhook queue items via admin for testing.
        """
        site = AdminSite()
        admin_instance = WebhookTransmissionQueueAdmin(WebhookTransmissionQueue, site)
        request = RequestFactory().get('/admin/')
        request.user = User(is_superuser=True, is_staff=True)

        assert admin_instance.has_add_permission(request) is True

    def test_has_view_permission_returns_true_for_superuser(self):
        """
        Verify that superusers can view webhook queue items in admin.
        """
        site = AdminSite()
        admin_instance = WebhookTransmissionQueueAdmin(WebhookTransmissionQueue, site)
        request = RequestFactory().get('/admin/')
        request.user = User(is_superuser=True, is_staff=True)

        assert admin_instance.has_view_permission(request) is True
