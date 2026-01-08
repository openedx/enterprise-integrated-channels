"""
Event handlers for OpenEdX Events consumed from event bus.
These handlers are called directly by the consume_events management command.
"""
import logging
from django.contrib.auth import get_user_model
from django.utils import timezone
from openedx_events.learning.data import (
    PersistentCourseGradeData,
    CourseEnrollmentData
)
from enterprise.models import EnterpriseCustomerUser
from channel_integrations.integrated_channel.services.webhook_routing import (
    route_webhook_by_region,
    NoWebhookConfigured
)

User = get_user_model()
log = logging.getLogger(__name__)

def handle_grade_change_for_webhooks(sender, signal, **kwargs):
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
    
    # Only process passing grades
    if not grade_data.passed_timestamp:
        log.debug(f'[Webhook] Skipping non-passing grade for user {grade_data.user_id}')
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
    
    for ecu in enterprise_customer_users:
        try:
            payload = _prepare_completion_payload(grade_data, user, ecu.enterprise_customer)
            route_webhook_by_region(
                user=user,
                enterprise_customer=ecu.enterprise_customer,
                course_id=str(grade_data.course.course_key),
                event_type='course_completion',
                payload=payload
            )
            log.info(
                f'[Webhook] Queued completion webhook for user {user.id}, '
                f'enterprise {ecu.enterprise_customer.uuid}, '
                f'course {grade_data.course.course_key}'
            )
        except NoWebhookConfigured as e:
            log.debug(f'[Webhook] No webhook configured: {e}')
        except Exception as e:
            log.error(
                f'[Webhook] Failed to queue completion webhook: {e}',
                exc_info=True
            )

def handle_enrollment_for_webhooks(sender, signal, **kwargs):
    """
    Handle enrollment event from event bus.
    Called directly by consume_events command.
    """
    enrollment_data: CourseEnrollmentData = kwargs.get('enrollment')
    if not enrollment_data:
        log.warning('[Webhook] COURSE_ENROLLMENT_CREATED event without enrollment data')
        return
    
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
    
    for ecu in enterprise_customer_users:
        try:
            payload = _prepare_enrollment_payload(enrollment_data, user, ecu.enterprise_customer)
            route_webhook_by_region(
                user=user,
                enterprise_customer=ecu.enterprise_customer,
                course_id=str(enrollment_data.course.course_key),
                event_type='course_enrollment',
                payload=payload
            )
            log.info(
                f'[Webhook] Queued enrollment webhook for user {user.id}, '
                f'enterprise {ecu.enterprise_customer.uuid}, '
                f'course {enrollment_data.course.course_key}'
            )
        except NoWebhookConfigured as e:
            log.debug(f'[Webhook] No webhook configured: {e}')
        except Exception as e:
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
