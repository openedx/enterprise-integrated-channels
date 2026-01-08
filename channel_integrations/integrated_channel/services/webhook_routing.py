"""
Service for routing events to appropriate webhook configurations.
"""
import logging

from django.utils import timezone

from channel_integrations.integrated_channel.models import EnterpriseWebhookConfiguration, WebhookTransmissionQueue
from channel_integrations.integrated_channel.services.region_service import get_user_region
from channel_integrations.integrated_channel.tasks import process_webhook_queue

log = logging.getLogger(__name__)


class NoWebhookConfigured(Exception):
    """Raised when no matching webhook configuration is found."""


def route_webhook_by_region(user, enterprise_customer, course_id, event_type, payload):
    """
    Route an event to the appropriate webhook based on user region.

    Args:
        user: The user object
        enterprise_customer: The enterprise customer object
        course_id: The course ID string
        event_type: 'course_completion' or 'course_enrollment'
        payload: The JSON payload to send

    Returns:
        WebhookTransmissionQueue: The created queue item

    Raises:
        NoWebhookConfigured: If no matching configuration is found
    """
    # 1. Detect User Region
    region = get_user_region(user)

    # 2. Find Matching Configuration
    # Try specific region first
    config = EnterpriseWebhookConfiguration.objects.filter(
        enterprise_customer=enterprise_customer,
        region=region,
        active=True
    ).first()

    # Fallback to 'OTHER' if specific region not found
    if not config and region != 'OTHER':
        config = EnterpriseWebhookConfiguration.objects.filter(
            enterprise_customer=enterprise_customer,
            region='OTHER',
            active=True
        ).first()

    if not config:
        raise NoWebhookConfigured(
            f"No active webhook found for enterprise {enterprise_customer.uuid} "
            f"in region {region} (or OTHER)"
        )

    # 3. Generate Deduplication Key
    # Key: {user_id}:{course_id}:{event_type}:{date}
    # This prevents duplicate events for the same thing on the same day
    today = timezone.now().strftime('%Y-%m-%d')
    deduplication_key = f"{user.id}:{course_id}:{event_type}:{today}"

    # 4. Create Queue Item
    # Use get_or_create to handle race conditions (idempotency)
    queue_item, created = WebhookTransmissionQueue.objects.get_or_create(
        deduplication_key=deduplication_key,
        defaults={
            'enterprise_customer': enterprise_customer,
            'user': user,
            'course_id': course_id,
            'event_type': event_type,
            'user_region': region,
            'webhook_url': config.webhook_url,
            'payload': payload,
            'status': 'pending',
            'next_retry_at': timezone.now()
        }
    )

    if created:
        log.info(
            f"[Webhook] Queued {event_type} for user {user.id} "
            f"to {config.webhook_url} (Region: {region})"
        )
        # 5. Trigger Celery Task
        process_webhook_queue.delay(queue_item.id)
    else:
        log.info(
            f"[Webhook] Duplicate event detected for key {deduplication_key}. "
            f"Existing status: {queue_item.status}"
        )

    return queue_item
