Datadog Structured Logging
##########################

Integrated Channels can emit Datadog-ready JSON logs while preserving the legacy
plain-text log format by default.

Enable JSON Logging
*******************

Set the feature flag in the host Django application's settings:

.. code-block:: python

   INTEGRATED_CHANNELS_JSON_LOGGING = True

Then configure the Integrated Channels logger to use
``channel_integrations.integrated_channel.structured_logging.JsonChannelFormatter``.
The formatter is the integration point for the feature flag: once it is installed
on the relevant handlers, ``INTEGRATED_CHANNELS_JSON_LOGGING=True`` emits JSON
and ``False`` keeps the legacy key/value message output.
For example:

.. code-block:: python

   LOGGING = {
       "version": 1,
       "formatters": {
           "integrated_channels_json": {
               "()": "channel_integrations.integrated_channel.structured_logging.JsonChannelFormatter",
           },
       },
       "handlers": {
           "console": {
               "class": "logging.StreamHandler",
               "formatter": "integrated_channels_json",
           },
       },
       "loggers": {
           "channel_integrations": {
               "handlers": ["console"],
               "level": "INFO",
               "propagate": False,
           },
       },
   }

When ``INTEGRATED_CHANNELS_JSON_LOGGING`` is unset or ``False``, existing
``generate_formatted_log()`` callers continue to emit the legacy key/value
message string.

Datadog Fields
**************

Structured logs include Datadog-friendly fields such as:

* ``status``
* ``service``
* ``event_type``
* ``integrated_channel.code``
* ``integrated_channel.customer_uuid``
* ``integrated_channel.user_id``
* ``integrated_channel.course_key``
* ``error.kind``
* ``error.category``
* ``http.status_code``
* ``error.payload_hash``
* ``correlation_id``
* ``dd.trace_id`` when Datadog tracing context is available

Payload Safety
**************

Raw serialized payloads are not emitted in JSON mode. When a legacy log message
contains ``integrated_channel_serialized_payload_base64``, the JSON formatter
replaces it in the human-readable message and emits ``error.payload_hash``
instead.
