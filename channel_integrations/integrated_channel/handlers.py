"""
Event handlers for OpenEdX Events consumed from event bus.
These handlers are called directly by the consume_events management command.
"""
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from enterprise.models import EnterpriseCustomerUser
from openedx_events.learning.data import CourseEnrollmentData, PersistentCourseGradeData

from channel_integrations.integrated_channel.services.webhook_routing import (
    NoWebhookConfigured,
    route_webhook_by_region,
)
from channel_integrations.integrated_channel.tasks import enrich_and_send_completion_webhook, process_webhook_queue

User = get_user_model()
log = logging.getLogger(__name__)


def handle_grade_change_for_webhooks(sender, signal, **kwargs):  # pylint: disable=unused-argument
    """
    Handle grade change event from event bus.
    Called directly by consume_events command.

    Args:
        sender: The sender class
        signal: The signal definition (for context)
        **kwargs: Contains 'grade' key with PersistentCourseGradeData object
    """
    grade_data: PersistentCourseGradeData = kwargs.get('grade')
    if not grade_data:
        log.warning('[Webhook] PERSISTENT_GRADE_SUMMARY_CHANGED event without grade data')
        return

    log.info(
        f'[Webhook] Processing grade change for user {grade_data.user_id}, '
        f'course {grade_data.course.course_key}, passed: {bool(grade_data.passed_timestamp)}'
    )

    # Only process passing grades
    if not grade_data.passed_timestamp:
        log.info(f'[Webhook] Skipping non-passing grade for user {grade_data.user_id}')
        return

    try:
        user = User.objects.get(id=grade_data.user_id)
    except User.DoesNotExist:
        log.error(f'[Webhook] User {grade_data.user_id} not found')
        return

    # Check if enterprise learner
    enterprise_customer_users = EnterpriseCustomerUser.objects.filter(
        user_id=user.id,
        active=True
    )

    if not enterprise_customer_users.exists():
        log.info(f'[Webhook] User {user.id} is not an enterprise learner, skipping webhook')
        return

    log.info(
        f'[Webhook] Found {enterprise_customer_users.count()} enterprise customer(s) '
        f'for user {user.id}'
    )

    for ecu in enterprise_customer_users:
        try:
            payload = _prepare_completion_payload(grade_data, user, ecu.enterprise_customer)

            # Check if learning time enrichment feature is enabled
            feature_enabled = getattr(settings, 'FEATURES', {}).get(
                'ENABLE_WEBHOOK_LEARNING_TIME_ENRICHMENT',
                False
            )

            log.info(
                f'[Webhook] Learning time enrichment feature enabled: {feature_enabled} '
                f'for enterprise {ecu.enterprise_customer.uuid}'
            )

            if feature_enabled:
                # Use enrichment task to add learning time data
                enrich_and_send_completion_webhook.delay(
                    user_id=user.id,
                    enterprise_customer_uuid=str(ecu.enterprise_customer.uuid),
                    course_id=str(grade_data.course.course_key),
                    payload_dict=payload
                )
                log.info(
                    f'[Webhook] Queued enrichment task for user {user.id}, '
                    f'enterprise {ecu.enterprise_customer.uuid}, '
                    f'course {grade_data.course.course_key}'
                )
            else:
                # Standard webhook routing (backward compatible)
                queue_item, created = route_webhook_by_region(
                    user=user,
                    enterprise_customer=ecu.enterprise_customer,
                    course_id=str(grade_data.course.course_key),
                    event_type='course_completion',
                    payload=payload
                )
                if created:
                    process_webhook_queue.delay(queue_item.id)

                log.info(
                    f'[Webhook] Queued completion webhook for user {user.id}, '
                    f'enterprise {ecu.enterprise_customer.uuid}, '
                    f'course {grade_data.course.course_key}'
                )
        except NoWebhookConfigured as e:
            log.info(f'[Webhook] No webhook configured for completion: {e}')
        except Exception as e:  # pylint: disable=broad-exception-caught
            log.error(
                f'[Webhook] Failed to queue completion webhook: {e}',
                exc_info=True
            )


def handle_enrollment_for_webhooks(sender, signal, **kwargs):  # pylint: disable=unused-argument
    """
    Handle enrollment event from event bus.
    Called directly by consume_events command.
    """
    enrollment_data: CourseEnrollmentData = kwargs.get('enrollment')
    if not enrollment_data:
        log.warning('[Webhook] COURSE_ENROLLMENT_CREATED event without enrollment data')
        return

    log.info(
        f'[Webhook] Processing enrollment for user {enrollment_data.user.id}, '
        f'course {enrollment_data.course.course_key}, mode: {enrollment_data.mode}'
    )

    try:
        user = User.objects.get(id=enrollment_data.user.id)
    except User.DoesNotExist:
        log.error(f'[Webhook] User {enrollment_data.user.id} not found')
        return

    # Check if enterprise learner
    enterprise_customer_users = EnterpriseCustomerUser.objects.filter(
        user_id=user.id,
        active=True
    )

    if not enterprise_customer_users.exists():
        log.info(f'[Webhook] User {user.id} is not an enterprise learner, skipping webhook')
        return

    log.info(
        f'[Webhook] Found {enterprise_customer_users.count()} enterprise customer(s) '
        f'for user {user.id}'
    )

    for ecu in enterprise_customer_users:
        try:
            payload = _prepare_enrollment_payload(enrollment_data, user, ecu.enterprise_customer)
            queue_item, created = route_webhook_by_region(
                user=user,
                enterprise_customer=ecu.enterprise_customer,
                course_id=str(enrollment_data.course.course_key),
                event_type='course_enrollment',
                payload=payload
            )
            if created:
                process_webhook_queue.delay(queue_item.id)

            log.info(
                f'[Webhook] Queued enrollment webhook for user {user.id}, '
                f'enterprise {ecu.enterprise_customer.uuid}, '
                f'course {enrollment_data.course.course_key}'
            )
        except NoWebhookConfigured as e:
            log.info(f'[Webhook] No webhook configured for enrollment: {e}')
        except Exception as e:  # pylint: disable=broad-exception-caught
            log.error(
                f'[Webhook] Failed to queue enrollment webhook: {e}',
                exc_info=True
            )


def _prepare_completion_payload(grade_data, user, enterprise_customer):
    """Prepare webhook payload for course completion event."""
    return {
        'event_type': 'course_completion',
        'event_version': '2.0',
        'event_source': 'openedx_events',
        'timestamp': timezone.now().isoformat(),
        'enterprise_customer': {
            'uuid': str(enterprise_customer.uuid),
            'name': enterprise_customer.name,
        },
        'learner': {
            'user_id': user.id,
            'username': user.username,
            'email': user.email,
        },
        'course': {
            'course_key': str(grade_data.course.course_key),
        },
        'completion': {
            'completed': True,
            'completion_date': grade_data.passed_timestamp.isoformat(),
            'percent_grade': float(grade_data.percent_grade),
            'letter_grade': grade_data.letter_grade,
            'is_passing': True,
        },
    }


def _prepare_enrollment_payload(enrollment_data, user, enterprise_customer):
    """Prepare webhook payload for course enrollment event."""
    return {
        'event_type': 'course_enrollment',
        'event_version': '2.0',
        'event_source': 'openedx_events',
        'timestamp': timezone.now().isoformat(),
        'enterprise_customer': {
            'uuid': str(enterprise_customer.uuid),
            'name': enterprise_customer.name,
        },
        'learner': {
            'user_id': user.id,
            'username': user.username,
            'email': user.email,
        },
        'course': {
            'course_key': str(enrollment_data.course.course_key),
        },
        'enrollment': {
            'mode': enrollment_data.mode,
            'is_active': enrollment_data.is_active,
            'enrollment_date': enrollment_data.creation_date.isoformat(),
        },
    }
