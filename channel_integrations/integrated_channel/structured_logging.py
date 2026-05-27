"""
Structured logging utilities for Integrated Channels.
"""

import hashlib
import json
import logging
import re
import traceback
from datetime import datetime, timezone
from importlib import import_module

from django.conf import settings

SERVICE_NAME = 'integrated_channels'

LOG_STATUS_BY_LEVEL = {
    logging.CRITICAL: 'critical',
    logging.ERROR: 'error',
    logging.WARNING: 'warning',
    logging.INFO: 'info',
    logging.DEBUG: 'debug',
}

PAYLOAD_PATTERN = re.compile(r'integrated_channel_serialized_payload_base64=([^,\s]+)')
ENROLLMENT_ID_PATTERN = re.compile(r'integrated_channel_enterprise_enrollment_id=([^,\s]+)')
REMOTE_USER_ID_PATTERN = re.compile(r'integrated_channel_remote_user_id=([^,\s]+)')
ERROR_STATUS_PATTERN = re.compile(r'Error status code:\s*(\d+)')
ERROR_MESSAGE_PATTERN = re.compile(r'Error message:\s*(.*?)(?:\s+Error status code:|$)')

AUTHENTICATION_PATTERNS = (
    'authentication',
    'authorization',
    'credentials',
    'forbidden',
    'invalid_grant',
    'refresh_token',
    'token',
    'unauthorized',
)
NETWORK_PATTERNS = (
    'connection',
    'dns',
    'network',
    'ssl',
    'timeout',
    'timed out',
    'tls',
)
RATE_LIMIT_PATTERNS = (
    'quota',
    'rate limit',
    'rate-limit',
    'throttle',
    'too many requests',
)
CONFIGURATION_PATTERNS = (
    'configuration',
    'disabled',
    'missing configuration',
    'missing url',
    'not configured',
)
VALIDATION_PATTERNS = (
    'bad request',
    'invalid payload',
    'malformed',
    'missing required',
    'schema',
    'validation',
)


def get_optional_attribute(module_name, attribute_name):
    """
    Return an optional dependency attribute without requiring the dependency at import time.
    """
    try:
        return getattr(import_module(module_name), attribute_name)
    except (AttributeError, ImportError):
        return None


ENTERPRISE_GET_REQUEST_ID = get_optional_attribute('enterprise.logging', 'get_request_id')
CELERY_CURRENT_TASK = get_optional_attribute('celery', 'current_task')
DD_TRACER = get_optional_attribute('ddtrace', 'tracer')


def is_json_logging_enabled():
    """
    Return whether Integrated Channels JSON logging is enabled.
    """
    return getattr(settings, 'INTEGRATED_CHANNELS_JSON_LOGGING', False)


def normalize_value(value):
    """
    Return a JSON-safe value without changing identifier semantics.
    """
    if value is None:
        return None

    if isinstance(value, (int, float, bool)):
        return value

    return str(value)


def normalize_numeric_value(value):
    """
    Return a JSON-safe numeric value for fields that are known to be numeric.
    """
    value = normalize_value(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return value


def hash_payload(payload):
    """
    Return a stable SHA-256 hash for a serialized payload without exposing the payload itself.
    """
    if payload is None:
        return None

    if not isinstance(payload, str):
        payload = json.dumps(payload, sort_keys=True)

    return f'sha256:{hashlib.sha256(payload.encode("utf-8")).hexdigest()}'


def categorize_error(error=None, status_code=None, message=None):
    """
    Categorize an integrated channel error into a stable Datadog facet value.
    """
    if status_code is None and error is not None:
        status_code = getattr(error, 'status_code', None)

    try:
        status_code = int(status_code) if status_code is not None else None
    except (TypeError, ValueError):
        status_code = None

    if status_code in (401, 403):
        return 'authentication'
    if status_code == 429:
        return 'rate_limit'
    if status_code is not None and 500 <= status_code <= 599:
        return 'upstream_5xx'

    haystack = ' '.join(
        str(item).lower()
        for item in (message, error, error.__class__.__name__ if error else None)
        if item
    )

    if any(pattern in haystack for pattern in AUTHENTICATION_PATTERNS):
        return 'authentication'
    if any(pattern in haystack for pattern in RATE_LIMIT_PATTERNS):
        return 'rate_limit'
    if any(pattern in haystack for pattern in NETWORK_PATTERNS):
        return 'network'
    if any(pattern in haystack for pattern in CONFIGURATION_PATTERNS):
        return 'configuration'
    if any(pattern in haystack for pattern in VALIDATION_PATTERNS):
        return 'validation'
    if status_code is not None and 400 <= status_code <= 499:
        return 'validation'

    return 'unknown'


def get_correlation_id(record=None):
    """
    Return the best available correlation id for the current logging context.
    """
    if record is not None:
        for attribute in ('correlation_id', 'request_id', 'task_id'):
            value = getattr(record, attribute, None)
            if value:
                return str(value)

    if ENTERPRISE_GET_REQUEST_ID:
        request_id = ENTERPRISE_GET_REQUEST_ID()
        if request_id:
            return str(request_id)

    if CELERY_CURRENT_TASK:
        task_request = getattr(CELERY_CURRENT_TASK, 'request', None)
        task_id = getattr(task_request, 'id', None)
        if task_id:
            return str(task_id)

    return None


def get_datadog_trace_id():
    """
    Return the active Datadog trace id when ddtrace is installed and active.
    """
    if not DD_TRACER:
        return None

    span = DD_TRACER.current_span() or DD_TRACER.current_root_span()
    trace_id = getattr(span, 'trace_id', None) if span else None
    return str(trace_id) if trace_id else None


def format_log_timestamp(created):
    """
    Format a LogRecord timestamp as ISO-8601 UTC with millisecond precision.
    """
    return datetime.fromtimestamp(created, tz=timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def level_to_status(levelno):
    """
    Map a Python logging level to Datadog's status field.
    """
    for threshold, status in sorted(LOG_STATUS_BY_LEVEL.items(), reverse=True):
        if levelno >= threshold:
            return status
    return 'debug'


def infer_event_type(message, levelno):
    """
    Infer a stable event type from common Integrated Channels log messages.
    """
    message = (message or '').lower()
    if levelno >= logging.ERROR or 'error status code:' in message or 'failed' in message:
        return 'transmission_error'
    if 'started' in message:
        return 'transmission_started'
    if 'successfully completed' in message or 'finished successfully' in message:
        return 'transmission_success'
    if 'finished' in message:
        return 'transmission_finished'
    if 'skipping' in message or 'skipped' in message:
        return 'transmission_skipped'
    return 'integrated_channel_log'


def extract_message_fields(message):
    """
    Extract known Integrated Channels key/value fields from the legacy message tail.
    """
    fields = {}
    if not message:
        return fields

    enrollment_match = ENROLLMENT_ID_PATTERN.search(message)
    if enrollment_match:
        fields['integrated_channel.enterprise_enrollment_id'] = normalize_numeric_value(enrollment_match.group(1))

    remote_user_match = REMOTE_USER_ID_PATTERN.search(message)
    if remote_user_match:
        fields['integrated_channel.remote_user_id'] = normalize_value(remote_user_match.group(1))

    payload_match = PAYLOAD_PATTERN.search(message)
    if payload_match:
        fields['error.payload_hash'] = hash_payload(payload_match.group(1))

    status_match = ERROR_STATUS_PATTERN.search(message)
    if status_match:
        fields['http.status_code'] = normalize_numeric_value(status_match.group(1))

    error_message_match = ERROR_MESSAGE_PATTERN.search(message)
    if error_message_match:
        fields['error.message'] = error_message_match.group(1).strip()

    return fields


def sanitize_message(message):
    """
    Remove raw serialized payloads from the human-readable log message.
    """
    if message is None:
        return None
    return PAYLOAD_PATTERN.sub('integrated_channel_serialized_payload_base64=<omitted>', str(message))


class StructuredLogMessage:
    """
    Structured representation of the existing Integrated Channels formatted log message.
    """

    def __init__(
        self,
        channel_name=None,
        enterprise_customer_uuid=None,
        lms_user_id=None,
        course_or_course_run_key=None,
        message=None,
        plugin_configuration_id=None,
    ):
        self.channel_name = channel_name
        self.enterprise_customer_uuid = enterprise_customer_uuid
        self.lms_user_id = lms_user_id
        self.course_or_course_run_key = course_or_course_run_key
        self.message = message
        self.plugin_configuration_id = plugin_configuration_id

    def legacy_message(self):
        """
        Return the existing flat key/value log format.
        """
        return f'integrated_channel={self.channel_name}, ' \
            f'integrated_channel_enterprise_customer_uuid={self.enterprise_customer_uuid}, ' \
            f'integrated_channel_lms_user={self.lms_user_id}, ' \
            f'integrated_channel_course_key={self.course_or_course_run_key}, ' \
            f'integrated_channel_plugin_configuration_id={self.plugin_configuration_id}, {self.message}'

    def structured_fields(self):
        """
        Return Datadog-ready fields derived from the formatted log inputs.
        """
        fields = {
            'integrated_channel.code': self.channel_name,
            'integrated_channel.customer_uuid': (
                str(self.enterprise_customer_uuid) if self.enterprise_customer_uuid is not None else None
            ),
            'integrated_channel.user_id': normalize_numeric_value(self.lms_user_id),
            'integrated_channel.course_key': (
                str(self.course_or_course_run_key) if self.course_or_course_run_key is not None else None
            ),
            'integrated_channel.plugin_configuration_id': normalize_numeric_value(self.plugin_configuration_id),
        }
        fields.update(extract_message_fields(self.message))
        return {key: value for key, value in fields.items() if value is not None}

    def datadog_message(self):
        """
        Return a sanitized human-readable log message.
        """
        channel_prefix = f'[{self.channel_name}] ' if self.channel_name else ''
        return f'{channel_prefix}{sanitize_message(self.message)}'

    def __str__(self):
        return self.legacy_message()


class JsonChannelFormatter(logging.Formatter):
    """
    Logging formatter that emits Datadog-ready JSON when the feature flag is enabled.
    """

    def format(self, record):
        if not is_json_logging_enabled():
            return super().format(record)

        return json.dumps(build_datadog_log_record(record), sort_keys=True)


def build_datadog_log_record(record):
    """
    Build a Datadog-ready dictionary from a Python LogRecord.
    """
    structured_message = record.msg if isinstance(record.msg, StructuredLogMessage) else None
    if structured_message:
        message = structured_message.datadog_message()
        fields = structured_message.structured_fields()
    else:
        message = sanitize_message(record.getMessage())
        fields = extract_message_fields(record.getMessage())

    exc_type = exc_value = exc_traceback = None
    if record.exc_info:
        exc_type, exc_value, exc_traceback = record.exc_info

    error_message = fields.get('error.message')
    status_code = fields.get('http.status_code')
    if exc_value is not None:
        fields.setdefault('error.kind', exc_type.__name__)
        fields.setdefault('error.message', str(exc_value))
        fields.setdefault('error.stack', ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback)))
        status_code = status_code or getattr(exc_value, 'status_code', None)
        if status_code is not None:
            fields.setdefault('http.status_code', normalize_numeric_value(status_code))
        error_message = fields.get('error.message')

    if 'error.message' in fields or record.levelno >= logging.ERROR:
        fields.setdefault('error.category', categorize_error(exc_value, status_code, error_message or message))

    correlation_id = get_correlation_id(record)
    if correlation_id:
        fields['correlation_id'] = correlation_id

    trace_id = get_datadog_trace_id()
    if trace_id:
        fields['dd.trace_id'] = trace_id

    log_record = {
        'timestamp': format_log_timestamp(record.created),
        'status': level_to_status(record.levelno),
        'service': getattr(settings, 'INTEGRATED_CHANNELS_LOG_SERVICE_NAME', SERVICE_NAME),
        'message': message,
        'event_type': infer_event_type(message, record.levelno),
        'logger.name': record.name,
    }
    log_record.update(fields)
    return log_record
