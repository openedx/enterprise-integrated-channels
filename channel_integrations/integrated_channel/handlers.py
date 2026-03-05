"""
Event handlers for OpenEdX Events consumed from event bus.
These handlers are called directly by the consume_events management command and are customized
towards the requirements of the Percipio LMS Content Submission Guidelines.
https://documentation.skillsoft.com/en_us/pes/Integration/iX-Studio/iX_Studio_onboarding_content_guidelines.htm
"""
import logging
import waffle  # pylint: disable=invalid-django-waffle-import
from django.contrib.auth import get_user_model
from enterprise.models import EnterpriseCustomerUser
from openedx_events.learning.data import CourseEnrollmentData, PersistentCourseGradeData
from social_django.models import UserSocialAuth

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
            payload = _prepare_completion_payload(grade_data, user)

            # Check if learning time enrichment feature is enabled
            feature_enabled = waffle.switch_is_active('enable_webhook_learning_time_enrichment')

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
            payload = _prepare_enrollment_payload(enrollment_data, user)
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


def _get_percipio_user_id(user):
    """
    Extract Percipio user UUID from SSO metadata.

    Args:
        user: Django User object

    Returns:
        str: Percipio user UUID or None if not found
    """
    try:
        social_auth = UserSocialAuth.objects.filter(user=user).first()
        if social_auth and social_auth.extra_data:
            return social_auth.extra_data.get('PercipioUserUUID')
    except Exception as e:  # pylint: disable=broad-exception-caught
        log.warning(f'[Webhook] Error extracting Percipio user UUID for user {user.id}: {e}')
    return None


def _get_percipio_org_id(user):
    """
    Extract Percipio organization UUID from SSO metadata.

    Args:
        user: Django User object

    Returns:
        str: Percipio organization UUID or None if not found
    """
    try:
        social_auth = UserSocialAuth.objects.filter(user=user).first()
        if social_auth and social_auth.extra_data:
            return social_auth.extra_data.get('percipioOrganizationUuid')
    except Exception as e:  # pylint: disable=broad-exception-caught
        log.warning(f'[Webhook] Error extracting Percipio org UUID for user {user.id}: {e}')
    return None


def _get_course_id_from_course_key(course_key):
    """
    Extract course ID from course run key.

    Converts course-v1:Org+Course+Run to course:Org+Course format.

    Args:
        course_key: CourseKey object

    Returns:
        str: Course ID in format 'course:{org}+{course}'
    """
    return f"course:{course_key.org}+{course_key.course}"


def _build_webhook_payload(user, content_id, status, event_date, completion_percentage):
    """
    Build webhook payload with Percipio identifiers and event data.

    Args:
        user: Django User object
        content_id: Course ID string
        status: Event status ('completed' or 'started')
        event_date: ISO formatted timestamp string
        completion_percentage: Integer percentage (0-100)

    Returns:
        dict: Webhook payload
    """
    # Extract Percipio identifiers from SSO metadata
    percipio_user_id = _get_percipio_user_id(user)
    percipio_org_id = _get_percipio_org_id(user)

    payload = {
        'content_id': content_id,
        'user': percipio_user_id,
        'status': status,
        'event_date': event_date,
        'completion_percentage': completion_percentage,
        'duration_spent': None,  # TODO: populate duration_spent (ENT-11477)
        'org_id': percipio_org_id,  # Always include org_id, even if None
    }

    return payload


def _prepare_completion_payload(grade_data, user):
    """
    Prepare webhook payload for Percipio course completion event.

    Args:
        grade_data: PersistentCourseGradeData object
        user: Django User object

    Returns:
        dict: Webhook payload with course completion data
    """
    return _build_webhook_payload(
        user=user,
        content_id=_get_course_id_from_course_key(grade_data.course.course_key),
        status='completed',
        event_date=grade_data.passed_timestamp.isoformat(),
        completion_percentage=100
    )


def _prepare_enrollment_payload(enrollment_data, user):
    """
    Prepare webhook payload for course enrollment event.

    Args:
        enrollment_data: CourseEnrollmentData object
        user: Django User object

    Returns:
        dict: Webhook payload with course enrollment data
    """
    return _build_webhook_payload(
        user=user,
        content_id=_get_course_id_from_course_key(enrollment_data.course.course_key),
        status='started',
        event_date=enrollment_data.creation_date.isoformat(),
        completion_percentage=0
    )
