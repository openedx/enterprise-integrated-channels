"""
Tests for integrated_channel admin.
"""
import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory

from channel_integrations.integrated_channel.admin import WebhookTransmissionQueueAdmin
from channel_integrations.integrated_channel.models import WebhookTransmissionQueue


@pytest.mark.django_db
class TestWebhookTransmissionQueueAdmin:
    """Tests for WebhookTransmissionQueueAdmin."""

    def test_has_add_permission_returns_false(self):
        """
        Verify that manual creation of webhook queue items is disabled.
        Queue items should be created automatically by signal handlers.
        """
        site = AdminSite()
        admin = WebhookTransmissionQueueAdmin(WebhookTransmissionQueue, site)
        request = RequestFactory().get('/admin/')

        assert admin.has_add_permission(request) is False
