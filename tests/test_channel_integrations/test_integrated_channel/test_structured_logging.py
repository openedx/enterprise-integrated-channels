"""
Tests for Integrated Channels structured logging utilities.
"""

import io
import json
import logging
import sys
import time
import unittest
from unittest import mock

import ddt
from django.test import override_settings

from channel_integrations.exceptions import ClientError
from channel_integrations.integrated_channel import structured_logging
from channel_integrations.integrated_channel.structured_logging import (
    JsonChannelFormatter,
    StructuredLogMessage,
    build_datadog_log_record,
    categorize_error,
    extract_message_fields,
    format_log_timestamp,
    get_correlation_id,
    get_datadog_trace_id,
    hash_payload,
    infer_event_type,
    level_to_status,
    normalize_numeric_value,
    normalize_value,
    redact_credentials,
    sanitize_message,
)
from channel_integrations.utils import generate_formatted_log
from test_utils import generate_test_private_key_pem


@ddt.ddt
class TestStructuredLogging(unittest.TestCase):
    """
    Test Datadog structured logging helpers.
    """

    @override_settings(INTEGRATED_CHANNELS_JSON_LOGGING=False)
    def test_generate_formatted_log_preserves_legacy_output_when_disabled(self):
        log_str = generate_formatted_log(1, 2, 3, 4, 5, 6)

        assert log_str == 'integrated_channel=1, '\
            'integrated_channel_enterprise_customer_uuid=2, '\
            'integrated_channel_lms_user=3, '\
            'integrated_channel_course_key=4, '\
            'integrated_channel_plugin_configuration_id=6, 5'

        log_str = generate_formatted_log(1, 2, 3, 4, 'Authorization: Bearer synthetic-auth-token', 6)

        assert 'synthetic-auth-token' not in log_str
        assert log_str.endswith('integrated_channel_plugin_configuration_id=6, [REDACTED]')

    @override_settings(INTEGRATED_CHANNELS_JSON_LOGGING=True)
    def test_generate_formatted_log_returns_structured_message_when_enabled(self):
        log_msg = generate_formatted_log(
            channel_name='CSOD',
            enterprise_customer_uuid='1f27a478-9ff3-4a10-aec0-746a0accef88',
            lms_user_id=67949678,
            course_or_course_run_key='HarvardX+LBTechX1',
            message='transmit_single_learner_data started.',
            plugin_configuration_id=None,
        )

        assert isinstance(log_msg, StructuredLogMessage)
        assert str(log_msg) == (
            'integrated_channel=CSOD, '
            'integrated_channel_enterprise_customer_uuid=1f27a478-9ff3-4a10-aec0-746a0accef88, '
            'integrated_channel_lms_user=67949678, '
            'integrated_channel_course_key=HarvardX+LBTechX1, '
            'integrated_channel_plugin_configuration_id=None, transmit_single_learner_data started.'
        )

        secret_msg = generate_formatted_log(channel_name='CSOD', message='Authorization: Bearer synthetic-auth-token')

        assert str(secret_msg).endswith('integrated_channel_plugin_configuration_id=None, [REDACTED]')

    @override_settings(INTEGRATED_CHANNELS_JSON_LOGGING=True)
    @mock.patch('channel_integrations.integrated_channel.structured_logging.get_datadog_trace_id')
    def test_json_formatter_emits_datadog_fields(self, mock_get_trace_id):
        mock_get_trace_id.return_value = '9234851012345'
        raw_payload = 'eyJzZXNzaW9uVG9rZW4iOiAic2VjcmV0In0='
        log_msg = generate_formatted_log(
            channel_name='CSOD',
            enterprise_customer_uuid='1f27a478-9ff3-4a10-aec0-746a0accef88',
            lms_user_id=67949678,
            course_or_course_run_key='HarvardX+LBTechX1',
            message=(
                'Failed to send completion status call for cornerstone_channel '
                'integrated_channel_enterprise_enrollment_id=4334751, '
                'integrated_channel_remote_user_id=000123, '
                f'integrated_channel_serialized_payload_base64={raw_payload}, '
                'Error message: Client create_course_completion failed: '
                'CSOD Unauthorized Exception:Check your credentials. Error status code: 401'
            ),
            plugin_configuration_id=None,
        )
        record = logging.LogRecord(
            name='channel_integrations.integrated_channel.transmitters.learner_data',
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg=log_msg,
            args=(),
            exc_info=None,
        )
        record.correlation_id = 'c1a8540d-37c5-4dee-a53f-e36148e04598'

        data = json.loads(JsonChannelFormatter().format(record))

        assert data['status'] == 'error'
        assert data['service'] == 'integrated_channels'
        assert data['event_type'] == 'transmission_error'
        assert data['integrated_channel.code'] == 'CSOD'
        assert data['integrated_channel.customer_uuid'] == '1f27a478-9ff3-4a10-aec0-746a0accef88'
        assert data['integrated_channel.user_id'] == 67949678
        assert data['integrated_channel.course_key'] == 'HarvardX+LBTechX1'
        assert data['integrated_channel.enterprise_enrollment_id'] == 4334751
        assert data['integrated_channel.remote_user_id'] == '000123'
        assert data['http.status_code'] == 401
        assert data['error.category'] == 'authentication'
        assert data['error.payload_hash'] == hash_payload(raw_payload)
        assert data['correlation_id'] == 'c1a8540d-37c5-4dee-a53f-e36148e04598'
        assert data['dd.trace_id'] == '9234851012345'
        assert raw_payload not in data['message']
        assert raw_payload not in json.dumps(data)

    @override_settings(INTEGRATED_CHANNELS_JSON_LOGGING=True)
    def test_json_formatter_includes_exception_context(self):
        log_msg = generate_formatted_log(
            channel_name='CANVAS',
            enterprise_customer_uuid='5d566680-12a8-4b85-89d8-d9eacbf0f9eb',
            lms_user_id='57164631',
            course_or_course_run_key='HP+HPGG02.en',
            message='Failed to transmit learner_data create: refresh_token not found',
        )
        record = None

        try:
            raise ClientError('refresh_token not found Authorization: Bearer synthetic-auth-token', 400)
        except ClientError:
            record = logging.LogRecord(
                name='channel_integrations.integrated_channel.transmitters.learner_data',
                level=logging.ERROR,
                pathname=__file__,
                lineno=1,
                msg=log_msg,
                args=(),
                exc_info=sys.exc_info(),
            )

        data = json.loads(JsonChannelFormatter().format(record))

        assert data['status'] == 'error'
        assert data['integrated_channel.user_id'] == 57164631
        assert data['error.kind'] == 'ClientError'
        assert data['error.message'] == 'refresh_token not found [REDACTED]'
        assert data['http.status_code'] == 400
        assert data['error.category'] == 'authentication'
        assert 'Traceback' in data['error.stack']
        assert 'synthetic-auth-token' not in data['error.stack']

    @ddt.data(
        (401, 'CSOD Unauthorized Exception:Check your credentials.', 'authentication'),
        (403, 'Forbidden', 'authentication'),
        (400, 'Missing required field', 'validation'),
        (429, 'Too many requests', 'rate_limit'),
        (500, 'Internal server error', 'upstream_5xx'),
        (None, 'Connection timed out', 'network'),
        (None, 'Channel configuration missing URL', 'configuration'),
    )
    @ddt.unpack
    def test_categorize_error(self, status_code, message, expected_category):
        assert categorize_error(status_code=status_code, message=message) == expected_category

    def test_categorize_error_handles_edge_cases(self):
        error = ClientError('rate limit exceeded', 429)

        assert categorize_error(error=error) == 'rate_limit'
        assert categorize_error(status_code='invalid', message='no known pattern') == 'unknown'
        assert categorize_error(status_code=418, message='unexpected client response') == 'validation'
        assert categorize_error(message='OAuth token expired') == 'authentication'
        assert categorize_error(message='rate limit exceeded') == 'rate_limit'

    def test_sanitize_message_redacts_credentials_and_saml_assertions(self):
        private_key = '-----BEGIN PRIVATE KEY-----\nsynthetic-private-key\n-----END PRIVATE KEY-----'
        assertion = '<saml:Assertion ID="_test">synthetic-saml-assertion</saml:Assertion>'
        message = json.dumps({
            'private_key': private_key,
            'assertion': assertion,
            'headers': {'Authorization': 'Bearer synthetic-auth-token'},
            'access_token': 'synthetic-oauth-token',
        })

        sanitized = sanitize_message(message)

        assert private_key not in sanitized
        assert assertion not in sanitized
        assert 'synthetic-private-key' not in sanitized
        assert 'synthetic-saml-assertion' not in sanitized
        assert 'synthetic-auth-token' not in sanitized
        assert 'synthetic-oauth-token' not in sanitized
        real_private_key = generate_test_private_key_pem()
        assert sanitize_message(real_private_key).strip() == '[REDACTED]'
        assert sanitize_message(json.dumps([{'access_token': 'synthetic-oauth-token'}])) == (
            '[{"access_token": "[REDACTED]"}]'
        )

        plain_message = sanitize_message(
            f'Authorization: Bearer synthetic-auth-token private_key={private_key} {assertion}'
        )
        assert 'synthetic-auth-token' not in plain_message
        assert 'synthetic-private-key' not in plain_message
        assert 'synthetic-saml-assertion' not in plain_message
        assert 'synthetic-oauth-token' not in sanitize_message('access_token=synthetic-oauth-token')

        # Redaction is stable when a message passes through more than one logging layer.
        header = sanitize_message('Authorization: Bearer synthetic-auth-token')
        assert header == '[REDACTED]'
        assert sanitize_message(header) == header

        assert sanitize_message('{"client_secret": "s1", "password": "s2"}') == (
            '{"client_secret": "[REDACTED]", "password": "[REDACTED]"}'
        )
        assert 's1' not in sanitize_message('client_secret=s1&password=s2')

        # Pathologically nested JSON falls back to pattern redaction instead of raising.
        assert sanitize_message('[' * 100000 + 'Authorization: Bearer synthetic-auth-token') == (
            '[' * 100000 + '[REDACTED]'
        )

        # A truncated body must not leak the part of a key or assertion that did arrive.
        assert 'synthetic-private-key' not in sanitize_message(
            '-----BEGIN PRIVATE KEY-----\nsynthetic-private-key'
        )
        assert 'synthetic-saml-assertion' not in sanitize_message(
            '<saml:Assertion ID="_test">synthetic-saml-assertion'
        )

    @ddt.data(
        ('Authorization: Token synthetic-secret', '[REDACTED]'),
        ('Authorization: JWT synthetic-secret', '[REDACTED]'),
        ("{'Authorization': 'Basic synthetic-secret'}", "{'[REDACTED]'}"),
        ('{"Authorization": "Token synthetic-secret"}', '{"Authorization": "[REDACTED]"}'),
        (
            'Request Headers: {"Authorization": "JWT synthetic-secret"}',
            'Request Headers: {"[REDACTED]"}',
        ),
        ('[{"access_token": "synthetic-secret"}]', '[{"access_token": "[REDACTED]"}]'),
        ('{"token": "synthetic-secret"}', '{"token": "[REDACTED]"}'),
        ('{"id_token": "synthetic-secret"}', '{"id_token": "[REDACTED]"}'),
        ('token=synthetic-secret', '[REDACTED]'),
        ('id_token=synthetic-secret', '[REDACTED]'),
        ('failed with Bearer synthetic-secret', 'failed with [REDACTED]'),
        ('{\\"client_secret\\": \\"synthetic-secret\\"}', None),
        (
            '{"name": "\u00c9conomie", "password": "synthetic-secret"}',
            '{"name": "\u00c9conomie", "password": "[REDACTED]"}',
        ),
    )
    @ddt.unpack
    def test_redact_credentials_variants(self, message, expected):
        redacted = redact_credentials(message)
        assert 'synthetic-secret' not in redacted
        if expected:
            assert redacted == expected

    @ddt.data(
        'Invalid assertion: signature expired',
        'password: must contain 8 characters',
        'Error message: token not found',
        'SAP error: missing <Assertion element; request id 77 status 400',
    )
    def test_redact_credentials_preserves_normal_text(self, message):
        assert redact_credentials(message) == message

    def test_redact_credentials_handles_long_saml_opening_tag(self):
        extra_namespaces = ' '.join(f'xmlns:ns{index}="urn:test:{index}"' for index in range(60))
        opening_tag = '<saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" ' + extra_namespaces + '>'
        assert len(opening_tag) > 1000
        assertion = f'{opening_tag}<saml:Issuer>client</saml:Issuer></saml:Assertion>'
        assert redact_credentials(assertion) == '[REDACTED]'

    def test_redact_credentials_is_linear_on_unterminated_assertion_tags(self):
        message = '<Assertion ' * 20000
        started = time.monotonic()
        redact_credentials(message)
        assert time.monotonic() - started < 2

    def test_flat_logs_keep_serialized_payload_and_sanitize_message_omits_it(self):
        message = 'integrated_channel_serialized_payload_base64=abc123'
        assert redact_credentials(message) == message
        assert sanitize_message(message) == 'integrated_channel_serialized_payload_base64=<omitted>'

    def test_helper_edge_cases(self):
        raw_payload = {'b': 2, 'a': 1}

        assert hash_payload(None) is None
        assert hash_payload(raw_payload) == hash_payload({'a': 1, 'b': 2})
        assert normalize_value('000123') == '000123'
        assert normalize_numeric_value('000123') == 123
        assert not extract_message_fields(None)
        assert not extract_message_fields('plain message')
        assert sanitize_message(None) is None
        assert format_log_timestamp(0) == '1970-01-01T00:00:00.000Z'
        assert level_to_status(1) == 'debug'

    @ddt.data(
        ('transmit_single_learner_data started.', logging.INFO, 'transmission_started'),
        ('successfully completed learner transmission', logging.INFO, 'transmission_success'),
        ('transmit_single_learner_data finished.', logging.INFO, 'transmission_finished'),
        ('skipping learner transmission', logging.INFO, 'transmission_skipped'),
        ('heartbeat', logging.INFO, 'integrated_channel_log'),
        ('anything', logging.ERROR, 'transmission_error'),
    )
    @ddt.unpack
    def test_infer_event_type_variants(self, message, levelno, expected_event_type):
        assert infer_event_type(message, levelno) == expected_event_type

    def test_get_correlation_id_uses_available_sources(self):
        record = logging.LogRecord(
            name='channel_integrations.test',
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg='plain message',
            args=(),
            exc_info=None,
        )
        record.request_id = 'record-request-id'

        assert get_correlation_id(record) == 'record-request-id'

        with mock.patch.object(structured_logging, 'ENTERPRISE_GET_REQUEST_ID', lambda: 'request-id'):
            assert get_correlation_id() == 'request-id'

        task = mock.Mock()
        task.request.id = 'task-id'
        task_without_id = mock.Mock()
        task_without_id.request.id = None
        with mock.patch.object(structured_logging, 'ENTERPRISE_GET_REQUEST_ID', lambda: None), \
                mock.patch.object(structured_logging, 'CELERY_CURRENT_TASK', task):
            assert get_correlation_id() == 'task-id'

        with mock.patch.object(structured_logging, 'ENTERPRISE_GET_REQUEST_ID', lambda: None), \
                mock.patch.object(structured_logging, 'CELERY_CURRENT_TASK', task_without_id):
            assert get_correlation_id() is None

        with mock.patch.object(structured_logging, 'ENTERPRISE_GET_REQUEST_ID', None), \
                mock.patch.object(structured_logging, 'CELERY_CURRENT_TASK', task):
            assert get_correlation_id() == 'task-id'

        with mock.patch.object(structured_logging, 'ENTERPRISE_GET_REQUEST_ID', None), \
                mock.patch.object(structured_logging, 'CELERY_CURRENT_TASK', None):
            assert get_correlation_id() is None

    def test_get_datadog_trace_id_uses_active_span(self):
        tracer = mock.Mock()
        tracer.current_span.return_value = mock.Mock(trace_id=12345)

        with mock.patch.object(structured_logging, 'DD_TRACER', tracer):
            assert get_datadog_trace_id() == '12345'

    def test_get_datadog_trace_id_uses_root_span(self):
        tracer = mock.Mock()
        tracer.current_span.return_value = None
        tracer.current_root_span.return_value = mock.Mock(trace_id=67890)

        with mock.patch.object(structured_logging, 'DD_TRACER', tracer):
            assert get_datadog_trace_id() == '67890'

    @override_settings(INTEGRATED_CHANNELS_JSON_LOGGING=True)
    def test_build_datadog_log_record_handles_plain_string_messages(self):
        record = logging.LogRecord(
            name='channel_integrations.test',
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg='Unexpected learner transmission failure',
            args=(),
            exc_info=None,
        )

        data = build_datadog_log_record(record)

        assert data['status'] == 'error'
        assert data['message'] == 'Unexpected learner transmission failure'
        assert data['event_type'] == 'transmission_error'
        assert data['error.category'] == 'unknown'

    @override_settings(INTEGRATED_CHANNELS_JSON_LOGGING=True)
    def test_build_datadog_log_record_handles_info_without_error_context(self):
        record = logging.LogRecord(
            name='channel_integrations.test',
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg='transmit_single_learner_data finished.',
            args=(),
            exc_info=None,
        )

        data = build_datadog_log_record(record)

        assert data['status'] == 'info'
        assert data['event_type'] == 'transmission_finished'
        assert 'error.category' not in data

    @override_settings(INTEGRATED_CHANNELS_JSON_LOGGING=True)
    def test_build_datadog_log_record_handles_exception_without_status_code(self):
        record = None

        try:
            raise RuntimeError('unexpected failure')
        except RuntimeError:
            record = logging.LogRecord(
                name='channel_integrations.test',
                level=logging.ERROR,
                pathname=__file__,
                lineno=1,
                msg='Unexpected learner transmission failure',
                args=(),
                exc_info=sys.exc_info(),
            )

        data = build_datadog_log_record(record)

        assert data['error.kind'] == 'RuntimeError'
        assert data['error.message'] == 'unexpected failure'
        assert data['error.category'] == 'unknown'
        assert 'http.status_code' not in data

    @override_settings(INTEGRATED_CHANNELS_JSON_LOGGING=False)
    def test_json_formatter_falls_back_to_plain_message_when_disabled(self):
        record = logging.LogRecord(
            name='channel_integrations.test',
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg='plain message Authorization: Bearer synthetic-auth-token',
            args=(),
            exc_info=None,
        )

        assert JsonChannelFormatter().format(record) == 'plain message [REDACTED]'

    @override_settings(INTEGRATED_CHANNELS_JSON_LOGGING=True)
    @mock.patch('channel_integrations.integrated_channel.structured_logging.get_datadog_trace_id')
    def test_configured_logger_emits_json_when_enabled(self, mock_get_trace_id):
        mock_get_trace_id.return_value = None
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonChannelFormatter())
        logger = logging.getLogger('channel_integrations.test.structured_logging')
        original_handlers = logger.handlers[:]
        original_level = logger.level
        original_propagate = logger.propagate

        try:
            logger.handlers = [handler]
            logger.setLevel(logging.INFO)
            logger.propagate = False

            logger.error(generate_formatted_log(
                channel_name='CANVAS',
                enterprise_customer_uuid='5d566680-12a8-4b85-89d8-d9eacbf0f9eb',
                lms_user_id='57164631',
                course_or_course_run_key='HP+HPGG02.en',
                message='Failed to transmit learner_data create: refresh_token not found',
            ))
        finally:
            logger.handlers = original_handlers
            logger.setLevel(original_level)
            logger.propagate = original_propagate

        data = json.loads(stream.getvalue())

        assert data['status'] == 'error'
        assert data['event_type'] == 'transmission_error'
        assert data['integrated_channel.code'] == 'CANVAS'
        assert data['integrated_channel.customer_uuid'] == '5d566680-12a8-4b85-89d8-d9eacbf0f9eb'
        assert data['integrated_channel.user_id'] == 57164631
        assert data['integrated_channel.course_key'] == 'HP+HPGG02.en'

    def _reset_channel_logger(self):
        """
        Isolate the shared ``channel_integrations`` logger and restore it after the test.
        """
        logger = logging.getLogger('channel_integrations')
        original_handlers = logger.handlers[:]
        original_propagate = logger.propagate
        original_level = logger.level

        def restore():
            logger.handlers = original_handlers
            logger.propagate = original_propagate
            logger.setLevel(original_level)

        self.addCleanup(restore)
        logger.handlers = []
        logger.propagate = True
        logger.setLevel(logging.NOTSET)
        return logger

    @override_settings(INTEGRATED_CHANNELS_JSON_LOGGING=True)
    def test_configure_structured_logging_wires_channel_logger_when_enabled(self):
        logger = self._reset_channel_logger()

        structured_logging.configure_structured_logging()

        json_handlers = [h for h in logger.handlers if isinstance(h.formatter, JsonChannelFormatter)]
        assert len(json_handlers) == 1
        assert logger.level == logging.INFO
        assert logger.propagate is False

        # ready() can run more than once; a second call must not stack another handler.
        structured_logging.configure_structured_logging()
        json_handlers = [h for h in logger.handlers if isinstance(h.formatter, JsonChannelFormatter)]
        assert len(json_handlers) == 1

    def test_configure_structured_logging_noop_when_disabled(self):
        # With the flag off the logger must be left untouched so records keep
        # propagating to the root logger (this is what keeps pytest's caplog working).
        logger = self._reset_channel_logger()

        structured_logging.configure_structured_logging()

        assert not any(isinstance(h.formatter, JsonChannelFormatter) for h in logger.handlers)
        assert logger.propagate is True

    @override_settings(INTEGRATED_CHANNELS_JSON_LOGGING=True)
    @mock.patch('channel_integrations.integrated_channel.structured_logging.get_datadog_trace_id')
    def test_configure_structured_logging_emits_json_when_enabled(self, mock_get_trace_id):
        mock_get_trace_id.return_value = None
        logger = self._reset_channel_logger()
        structured_logging.configure_structured_logging()

        handler = next(h for h in logger.handlers if isinstance(h.formatter, JsonChannelFormatter))
        stream = io.StringIO()
        handler.stream = stream

        logging.getLogger('channel_integrations.test_enabled').error('boom')

        data = json.loads(stream.getvalue())
        assert data['message'] == 'boom'
        assert data['status'] == 'error'
