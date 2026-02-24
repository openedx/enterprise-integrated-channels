"""
Celery tasks for integrated channel management commands.
"""

import time
from functools import wraps

import requests
import waffle  # pylint: disable=invalid-django-waffle-import
from celery import shared_task
from celery.utils.log import get_task_logger
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from edx_django_utils.monitoring import set_code_owner_attribute
from enterprise.models import EnterpriseCustomer
from enterprise.utils import get_enterprise_uuids_for_user_and_course

from channel_integrations.integrated_channel.constants import TASK_LOCK_EXPIRY_SECONDS
from channel_integrations.integrated_channel.management.commands import (
    INTEGRATED_CHANNEL_CHOICES,
    IntegratedChannelCommandUtils,
)
from channel_integrations.integrated_channel.models import (
    ContentMetadataItemTransmission,
    OrphanedContentTransmissions,
    WebhookTransmissionQueue,
)
from channel_integrations.integrated_channel.services.webhook_routing import route_webhook_by_region
from channel_integrations.integrated_channel.snowflake_client import SnowflakeLearningTimeClient
from channel_integrations.utils import generate_formatted_log

LOGGER = get_task_logger(__name__)
User = get_user_model()


def locked(expiry_seconds, lock_name_kwargs):
    """
    A decorator to wrap a method in a cache-based lock with a cache-key derrived from function name and selected kwargs
    """
    def task_decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):  # lint-amnesty, pylint: disable=inconsistent-return-statements
            cache_key = f'{func.__name__}'
            for key in lock_name_kwargs:
                cache_key += f'-{key}:{kwargs.get(key)}'
            if cache.add(cache_key, "true", expiry_seconds):
                exception = None
                try:
                    LOGGER.info('Locking task in cache with key: %s for %s seconds', cache_key, expiry_seconds)
                    return func(*args, **kwargs)
                except Exception as error:  # lint-amnesty, pylint: disable=broad-except
                    LOGGER.exception(error)
                    exception = error
                finally:
                    LOGGER.info('Unlocking task in cache with key: %s', cache_key)
                    cache.delete(cache_key)
                    if exception:
                        LOGGER.error(f'Re-raising exception from inside locked task: {type(exception).__name__}')
                        raise exception
            else:
                LOGGER.info('Task with key %s already exists in cache', cache_key)
                return None
        return wrapper
    return task_decorator


def _log_batch_task_start(task_name, channel_code, job_user_id, integrated_channel_full_config, extra_message=''):
    """
    Logs a consistent message on the start of a batch integrated channel task.
    """
    LOGGER.info(
        '[Integrated Channel: {channel_name}] Batch {task_name} started '
        '(api user: {job_user_id}). Configuration: {configuration}. {details}'.format(
            channel_name=channel_code,
            task_name=task_name,
            job_user_id=job_user_id,
            configuration=integrated_channel_full_config,
            details=extra_message
        ))


def _log_batch_task_finish(task_name, channel_code, job_user_id,
                           integrated_channel_full_config, duration_seconds, extra_message=''):
    """
    Logs a consistent message on the end of a batch integrated channel task.
    """

    LOGGER.info(
        '[Integrated Channel: {channel_name}] Batch {task_name} finished in {duration_seconds} '
        '(api user: {job_user_id}). Configuration: {configuration}. {details}'.format(
            channel_name=channel_code,
            task_name=task_name,
            job_user_id=job_user_id,
            configuration=integrated_channel_full_config,
            duration_seconds=duration_seconds,
            details=extra_message
        ))


@shared_task
@set_code_owner_attribute
def remove_null_catalog_transmission_audits():
    """
    Task to remove content transmission audit records that do not contain a catalog UUID.
    """
    start = time.time()

    _log_batch_task_start('remove_null_catalog_transmission_audits', None, None, None)

    deleted_null_catalog_uuids = ContentMetadataItemTransmission.objects.filter(
        enterprise_customer_catalog_uuid=None
    ).delete()

    duration_seconds = time.time() - start
    _log_batch_task_finish(
        'remove_null_catalog_transmission_audits',
        channel_code=None,
        job_user_id=None,
        integrated_channel_full_config=None,
        duration_seconds=duration_seconds,
        extra_message=f"{deleted_null_catalog_uuids[0]} transmission audits with no catalog UUIDs removed"
    )


@shared_task
@set_code_owner_attribute
def remove_duplicate_transmission_audits():
    """
    Task to remove duplicate transmission audits, keeping the most recently modified one.
    """
    start = time.time()
    _log_batch_task_start('remove_duplicate_transsmision_audits', None, None, None)
    unique_transmissions = ContentMetadataItemTransmission.objects.values_list(
        'content_id',
        'plugin_configuration_id',
        'integrated_channel_code',
    ).distinct()
    duplicates_found = 0
    for unique_transmission in unique_transmissions:
        content_id = unique_transmission[0]
        duplicates = ContentMetadataItemTransmission.objects.filter(
            id__in=ContentMetadataItemTransmission.objects.filter(
                content_id=content_id,
                plugin_configuration_id=unique_transmission[1],
                integrated_channel_code=unique_transmission[2]
            ).values_list('id', flat=True)
        ).order_by('-modified')
        # Subtract one because we're keeping the most recently modified one
        num_duplicates = duplicates.count() - 1
        duplicates_found += num_duplicates
        # Mysql doesn't support taking the count of a sliced queryset
        duplicates_to_delete = duplicates[1:]

        dry_run_flag = getattr(settings, "DRY_RUN_MODE_REMOVE_DUP_TRANSMISSION_AUDIT", True)
        LOGGER.info(
            f"remove_duplicate_transmission_audits task dry run mode set to: {dry_run_flag}"
        )
        if dry_run_flag:
            LOGGER.info(
                f"Found {num_duplicates} duplicate content transmission audits for course: {content_id}"
            )
        else:
            LOGGER.info(f'Beginning to delete duplicate content transmission audits for course: {content_id}')
            for duplicate in duplicates_to_delete:
                LOGGER.info(f"Deleting duplicate transmission audit: {duplicate.id}")
                duplicate.delete()

    duration_seconds = time.time() - start
    _log_batch_task_finish(
        'remove_duplicate_transsmision_audits',
        channel_code=None,
        job_user_id=None,
        integrated_channel_full_config=None,
        duration_seconds=duration_seconds,
        extra_message=f"{duplicates_found} duplicates found"
    )


@shared_task
@set_code_owner_attribute
def mark_orphaned_content_metadata_audit():
    """
    Task to mark content metadata audits as orphaned if they are not linked to any customer catalogs.
    """
    start = time.time()
    _log_batch_task_start('mark_orphaned_content_metadata_audit', None, None, None)

    orphaned_metadata_audits = ContentMetadataItemTransmission.objects.none()
    # Go over each integrated channel
    for individual_channel in INTEGRATED_CHANNEL_CHOICES.values():
        try:
            # Iterate through each configuration for the channel
            for config in individual_channel.objects.all():
                # fetch orphaned content
                orphaned_metadata_audits |= config.fetch_orphaned_content_audits()
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.exception(
                f'[Integrated Channel] mark_orphaned_content_metadata_audit failed with exception {exc}.',
                exc_info=True
            )
    # Generate orphaned content records for each fetched audit record
    for orphaned_metadata_audit in orphaned_metadata_audits:
        OrphanedContentTransmissions.objects.get_or_create(
            integrated_channel_code=orphaned_metadata_audit.integrated_channel_code,
            plugin_configuration_id=orphaned_metadata_audit.plugin_configuration_id,
            transmission=orphaned_metadata_audit,
            content_id=orphaned_metadata_audit.content_id,
        )

    duration = time.time() - start
    _log_batch_task_finish(
        'mark_orphaned_content_metadata_audit',
        channel_code=None,
        job_user_id=None,
        integrated_channel_full_config=None,
        duration_seconds=duration,
        extra_message=f'Orphaned content metadata audits marked: {orphaned_metadata_audits.count()}'
    )


@shared_task
@set_code_owner_attribute
@locked(expiry_seconds=TASK_LOCK_EXPIRY_SECONDS, lock_name_kwargs=['channel_code', 'channel_pk'])
def transmit_content_metadata(username, channel_code, channel_pk):
    """
    Task to send content metadata to each linked integrated channel.

    Arguments:
        username (str): The username of the User for making API requests to retrieve content metadata.
        channel_code (str): Capitalized identifier for the integrated channel.
        channel_pk (str): Primary key for identifying integrated channel.

    """
    start = time.time()
    api_user = User.objects.get(username=username)
    integrated_channel = INTEGRATED_CHANNEL_CHOICES[channel_code].objects.get(pk=channel_pk)

    _log_batch_task_start('transmit_content_metadata', channel_code, api_user.id, integrated_channel)

    try:
        integrated_channel.transmit_content_metadata(api_user)
    except Exception:  # pylint: disable=broad-except
        LOGGER.exception(
            '[Integrated Channel: {channel_name}] Batch transmit_content_metadata failed with exception. '
            '(api user: {job_user_id}). Configuration: {configuration}'.format(
                channel_name=channel_code,
                job_user_id=api_user.id,
                configuration=integrated_channel
            ), exc_info=True)

    duration = time.time() - start
    _log_batch_task_finish('transmit_content_metadata', channel_code, api_user.id, integrated_channel, duration)


@shared_task
@set_code_owner_attribute
@locked(expiry_seconds=TASK_LOCK_EXPIRY_SECONDS, lock_name_kwargs=['channel_code', 'channel_pk'])
def transmit_learner_data(username, channel_code, channel_pk):
    """
    Task to send learner data to a linked integrated channel.

    Arguments:
        username (str): The username of the User to be used for making API requests for learner data.
        channel_code (str): Capitalized identifier for the integrated channel
        channel_pk (str): Primary key for identifying integrated channel
    """
    start = time.time()
    api_user = User.objects.get(username=username)
    integrated_channel = INTEGRATED_CHANNEL_CHOICES[channel_code].objects.get(pk=channel_pk)
    _log_batch_task_start('transmit_learner_data', channel_code, api_user.id, integrated_channel)

    # Note: learner data transmission code paths don't raise any uncaught exception,
    # so we don't need a broad try-except block here.
    integrated_channel.transmit_learner_data(api_user)

    duration = time.time() - start
    _log_batch_task_finish('transmit_learner_data', channel_code, api_user.id, integrated_channel, duration)


@shared_task
@set_code_owner_attribute
def cleanup_duplicate_assignment_records(username, channel_code, channel_pk):
    """
    Task to remove transmitted duplicate assignment records of provided integrated channel.

    Arguments:
        username (str): The username of the User to be used for making API requests for learner data.
        channel_code (str): Capitalized identifier for the integrated channel
        channel_pk (str): Primary key for identifying integrated channel
    """
    start = time.time()
    api_user = User.objects.get(username=username)
    integrated_channel = INTEGRATED_CHANNEL_CHOICES[channel_code].objects.get(pk=channel_pk)
    _log_batch_task_start('cleanup_duplicate_assignment_records', channel_code, api_user.id, integrated_channel)

    integrated_channel.cleanup_duplicate_assignment_records(api_user)
    duration = time.time() - start
    _log_batch_task_finish(
        'cleanup_duplicate_assignment_records',
        channel_code,
        api_user.id,
        integrated_channel,
        duration
    )


@shared_task
@set_code_owner_attribute
def update_content_transmission_catalog(username, channel_code, channel_pk):
    """
    Task to retrieve all transmitted content items under a specific channel and update audits to contain the content's
    associated catalog.

    Arguments:
        username (str): The username of the User to be used for making API requests for learner data.
        channel_code (str): Capitalized identifier for the integrated channel
        channel_pk (str): Primary key for identifying integrated channel
    """
    start = time.time()
    api_user = User.objects.get(username=username)

    integrated_channel = INTEGRATED_CHANNEL_CHOICES[channel_code].objects.get(pk=channel_pk)

    _log_batch_task_start('update_content_transmission_catalog', channel_code, api_user.id, integrated_channel)

    integrated_channel.update_content_transmission_catalog(api_user)
    duration = time.time() - start
    _log_batch_task_finish(
        'update_content_transmission_catalog',
        channel_code,
        api_user.id,
        integrated_channel,
        duration
    )


@shared_task
@set_code_owner_attribute
def transmit_single_learner_data(username, course_run_id):
    """
    Task to send single learner data to each linked integrated channel.

    Arguments:
        username (str): The username of the learner whose data it should send.
        course_run_id (str): The course run id of the course it should send data for.
    """
    user = User.objects.get(username=username)
    enterprise_customer_uuids = get_enterprise_uuids_for_user_and_course(user, course_run_id, is_customer_active=True)

    # Transmit the learner data to each integrated channel for each related customer.
    # Starting Export. N customer is usually 1 but multiple are supported in codebase.
    for enterprise_customer_uuid in enterprise_customer_uuids:
        channel_utils = IntegratedChannelCommandUtils()
        enterprise_integrated_channels = channel_utils.get_integrated_channels(
            {'channel': None, 'enterprise_customer': enterprise_customer_uuid}
        )
        for channel in enterprise_integrated_channels:
            integrated_channel = INTEGRATED_CHANNEL_CHOICES[channel.channel_code()].objects.get(pk=channel.pk)

            LOGGER.info(generate_formatted_log(
                integrated_channel.channel_code(),
                enterprise_customer_uuid,
                user.id,
                course_run_id,
                'transmit_single_learner_data started.'
            ))

            integrated_channel.transmit_single_learner_data(
                learner_to_transmit=user,
                course_run_id=course_run_id,
                completed_date=timezone.now(),
                grade='Pass',
                is_passing=True
            )
            LOGGER.info(generate_formatted_log(
                integrated_channel.channel_code(),
                enterprise_customer_uuid,
                user.id,
                course_run_id,
                "transmit_single_learner_data finished."
            ))


@shared_task
@set_code_owner_attribute
def transmit_single_subsection_learner_data(username, course_run_id, subsection_id, grade):
    """
    Task to send an assessment level learner data record to each linked
    integrated channel. This task is fired off
    when an enterprise learner completes a subsection of their course, and
    only sends the data for that sub-section.

    Arguments:
        username (str): The username of the learner whose data it should send.
        course_run_id  (str): The course run id of the course it should send data for.
        subsection_id (str): The completed subsection id whose grades are being reported.
        grade (str): The grade received, used to ensure we are not sending duplicate transmissions.
    """

    user = User.objects.get(username=username)
    enterprise_customer_uuids = get_enterprise_uuids_for_user_and_course(user, course_run_id, is_customer_active=True)
    channel_utils = IntegratedChannelCommandUtils()

    # Transmit the learner data to each integrated channel for each related customer.
    # Starting Export. N customer is usually 1 but multiple are supported in codebase.
    for enterprise_customer_uuid in enterprise_customer_uuids:
        enterprise_integrated_channels = channel_utils.get_integrated_channels(
            {'channel': None, 'enterprise_customer': enterprise_customer_uuid, 'assessment_level_support': True}
        )

        for channel in enterprise_integrated_channels:
            start = time.time()
            integrated_channel = INTEGRATED_CHANNEL_CHOICES[channel.channel_code()].objects.get(pk=channel.pk)

            LOGGER.info(generate_formatted_log(
                channel.channel_code(),
                enterprise_customer_uuid,
                user.id,
                course_run_id,
                'transmit_single_subsection_learner_data for Subsection_id: {} started.'.format(subsection_id)
            ))

            integrated_channel.transmit_single_subsection_learner_data(
                learner_to_transmit=user,
                course_run_id=course_run_id,
                grade=grade,
                subsection_id=subsection_id
            )

            duration = time.time() - start
            LOGGER.info(generate_formatted_log(
                None,
                enterprise_customer_uuid,
                user.id,
                course_run_id,
                'transmit_single_subsection_learner_data for channels {channels} and for Subsection_id: '
                '{subsection_id} finished in {duration}s.'.format(
                        channels=[c.channel_code() for c in enterprise_integrated_channels],
                        subsection_id=subsection_id,
                        duration=duration)
            ))


@shared_task
@set_code_owner_attribute
@locked(expiry_seconds=TASK_LOCK_EXPIRY_SECONDS, lock_name_kwargs=['channel_code', 'channel_pk'])
def transmit_subsection_learner_data(job_username, channel_code, channel_pk):
    """
    Task to send assessment level learner data to a linked integrated channel.

    Arguments:
        job_username (str): The username of the User making API requests for learner data.
        channel_code (str): Capitalized identifier for the integrated channel
        channel_pk (str): Primary key for identifying integrated channel
    """
    start = time.time()
    api_user = User.objects.get(username=job_username)
    integrated_channel = INTEGRATED_CHANNEL_CHOICES[channel_code].objects.get(pk=channel_pk)
    _log_batch_task_start('transmit_subsection_learner_data', channel_code, api_user.id, integrated_channel)

    # Exceptions during transmission are caught and saved within the audit so no need to try/catch here
    integrated_channel.transmit_subsection_learner_data(api_user)
    duration = time.time() - start
    _log_batch_task_finish('transmit_subsection_learner_data', channel_code, api_user.id, integrated_channel, duration)


@shared_task
@set_code_owner_attribute
def unlink_inactive_learners(channel_code, channel_pk):
    """
    Task to unlink inactive learners of provided integrated channel.

    Arguments:
        channel_code (str): Capitalized identifier for the integrated channel
        channel_pk (str): Primary key for identifying integrated channel
    """
    start = time.time()
    integrated_channel = INTEGRATED_CHANNEL_CHOICES[channel_code].objects.get(pk=channel_pk)

    _log_batch_task_start('unlink_inactive_learners', channel_code, None, integrated_channel)

    # Note: learner data transmission code paths don't raise any uncaught exception, so we don't need a broad
    # try-except block here.
    integrated_channel.unlink_inactive_learners()

    duration = time.time() - start
    _log_batch_task_finish('unlink_inactive_learners', channel_code, None, integrated_channel, duration)


@shared_task
@set_code_owner_attribute
def enrich_and_send_completion_webhook(user_id, enterprise_customer_uuid, course_id, payload_dict):
    """
    Enrich completion webhook payload with learning time data (if feature enabled) and route it.

    This task is routed to 'edx.lms.core.webhook_enrichment' queue for processing.

    Args:
        user_id: User ID
        enterprise_customer_uuid: Enterprise customer UUID string
        course_id: Course key string
        payload_dict: The webhook payload dictionary
    """
    # Check feature flag
    feature_enabled = waffle.switch_is_active('enable_webhook_learning_time_enrichment')

    if feature_enabled:
        try:
            # Query learning time from Snowflake
            client = SnowflakeLearningTimeClient()
            learning_time = client.get_learning_time(
                user_id=user_id,
                course_id=course_id,
                enterprise_customer_uuid=enterprise_customer_uuid
            )

            # Add to payload if we got a value
            if learning_time is not None:
                # Add learning_time to the completion section
                if 'completion' not in payload_dict:
                    payload_dict['completion'] = {}
                payload_dict['completion']['learning_time'] = learning_time

                LOGGER.info(
                    f'[Webhook] Enriched payload with learning_time={learning_time}s '
                    f'(user={user_id}, course={course_id}, enterprise={enterprise_customer_uuid})'
                )
            else:
                LOGGER.debug(
                    f'[Webhook] No learning_time data available '
                    f'(user={user_id}, course={course_id}, enterprise={enterprise_customer_uuid})'
                )
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Log error but continue - webhook should still be sent
            LOGGER.warning(
                f'[Webhook] Failed to enrich with learning_time: {e} '
                f'(user={user_id}, course={course_id}, enterprise={enterprise_customer_uuid})',
                exc_info=True
            )

    # Route webhook (with or without learning time enrichment)
    try:
        user = User.objects.get(id=user_id)
        enterprise_customer = EnterpriseCustomer.objects.get(uuid=enterprise_customer_uuid)

        queue_item, created = route_webhook_by_region(
            user=user,
            enterprise_customer=enterprise_customer,
            course_id=course_id,
            event_type='course_completion',
            payload=payload_dict
        )
        if created:
            process_webhook_queue.delay(queue_item.id)

        LOGGER.info(
            f'[Webhook] Routed enriched completion webhook '
            f'(user={user_id}, enterprise={enterprise_customer_uuid}, course={course_id})'
        )
    except Exception as e:
        LOGGER.error(
            f'[Webhook] Failed to route enriched webhook: {e} '
            f'(user={user_id}, enterprise={enterprise_customer_uuid}, course={course_id})',
            exc_info=True
        )
        raise


@shared_task
@set_code_owner_attribute
def process_webhook_queue(queue_item_id):
    """
    Process a single webhook queue item.

    This task is routed to 'edx.lms.enterprise.webhooks' queue.

    Args:
        queue_item_id: ID of WebhookTransmissionQueue item
    """
    try:
        queue_item = WebhookTransmissionQueue.objects.get(id=queue_item_id)
    except WebhookTransmissionQueue.DoesNotExist:
        LOGGER.error(f"[Webhook] Queue item {queue_item_id} not found")
        return

    # Don't process if already done or cancelled
    if queue_item.status in ['success', 'cancelled']:
        return

    queue_item.status = 'processing'
    queue_item.attempt_count += 1
    queue_item.last_attempt_at = timezone.now()
    queue_item.save(update_fields=['status', 'attempt_count', 'last_attempt_at'])

    try:
        # Get configuration for timeout
        config = queue_item.enterprise_customer.webhook_configurations.filter(
            region=queue_item.user_region,
            active=True
        ).first()

        if not config:
            # Fallback to OTHER
            config = queue_item.enterprise_customer.webhook_configurations.filter(
                region='OTHER',
                active=True
            ).first()

        if not config:
            raise Exception("No active webhook configuration found during processing")

        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'OpenEdX-Enterprise-Webhook/1.0',
        }

        percipio_client_id = getattr(settings, 'PERCIPIO_CLIENT_ID', None)
        percipio_client_secret = getattr(settings, 'PERCIPIO_CLIENT_SECRET', None)

        if percipio_client_id and percipio_client_secret:
            from channel_integrations.integrated_channel.percipio_auth import PercipioAuthClient  # pylint: disable=import-outside-toplevel
            token = PercipioAuthClient().get_token(queue_item.user_region)
            headers['Authorization'] = f"Bearer {token}"
        elif config.webhook_auth_token:
            # TODO: Remove this fallback once PERCIPIO_CLIENT_ID /
            # PERCIPIO_CLIENT_SECRET are configured in all environments and the
            # static webhook_auth_token field can be retired.
            headers['Authorization'] = f"Bearer {config.webhook_auth_token}"

        response = requests.post(
            queue_item.webhook_url,
            json=queue_item.payload,
            headers=headers,
            timeout=config.webhook_timeout_seconds
        )

        queue_item.http_status_code = response.status_code
        queue_item.response_body = response.text[:10000]  # Truncate to 10KB

        if 200 <= response.status_code < 300:
            queue_item.status = 'success'
            queue_item.completed_at = timezone.now()
            queue_item.error_message = None
            LOGGER.info(f"[Webhook] Successfully transmitted item {queue_item.id}")
        else:
            queue_item.status = 'failed'
            queue_item.error_message = f"HTTP {response.status_code}"
            LOGGER.warning(f"[Webhook] Failed to transmit item {queue_item.id}: HTTP {response.status_code}")
            _schedule_retry(queue_item, config)

    except Exception as e:  # pylint: disable=broad-exception-caught
        queue_item.status = 'failed'
        # Get a meaningful error message
        error_msg = str(e) if str(e) else repr(e)
        queue_item.error_message = error_msg
        LOGGER.error(f"[Webhook] Error processing item {queue_item.id}: {e}", exc_info=True)

        # Only retry on transient errors, not permanent failures like missing config
        is_permanent_error = "No active webhook configuration found" in error_msg
        if not is_permanent_error:
            _schedule_retry(queue_item, config if 'config' in locals() and config else None)

    queue_item.save()


def _schedule_retry(queue_item, config):
    """Schedule a retry if attempts remain."""
    max_retries = config.webhook_retry_attempts if config else 3

    if queue_item.attempt_count <= max_retries:
        # Exponential backoff: 30s, 120s, 300s...
        delay = 30 * (2 ** (queue_item.attempt_count - 1))
        # Cap at 1 hour
        delay = min(delay, 3600)

        queue_item.next_retry_at = timezone.now() + timezone.timedelta(seconds=delay)
        queue_item.status = 'pending'

        LOGGER.info(f"[Webhook] Scheduling retry #{queue_item.attempt_count} for item {queue_item.id} in {delay}s")

        # Re-queue task with delay
        process_webhook_queue.apply_async((queue_item.id,), countdown=delay)
    else:
        LOGGER.warning(f"[Webhook] Max retries reached for item {queue_item.id}")
