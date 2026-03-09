Percipio webhook payload format
###############################

This integration sends enrollment and completion events to Percipio using a
flat payload structure.

Required identifier field names
*******************************

Percipio expects these identifier keys:

- ``userid``: Percipio user UUID as a scalar string, or ``null``
- ``orgid``: Percipio organization UUID as a scalar string, or ``null``

Do not use ``user`` or ``org_id`` in Percipio payloads.

Completion payload example
**************************

.. code-block:: json

   {
     "content_id": "course:edX+DemoX",
     "userid": "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d",
     "orgid": "f6e5d4c3-b2a1-4f5e-9d8c-7b6a5e4d3c2b",
     "status": "completed",
     "event_date": "2026-03-09T10:12:30.123456+00:00",
     "completion_percentage": 100,
     "duration_spent": null
   }

Enrollment payload example
**************************

.. code-block:: json

   {
     "content_id": "course:edX+DemoX",
     "userid": "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d",
     "orgid": "f6e5d4c3-b2a1-4f5e-9d8c-7b6a5e4d3c2b",
     "status": "started",
     "event_date": "2026-03-09T10:12:30.123456+00:00",
     "completion_percentage": 0,
     "duration_spent": null
   }

Null identifier example
***********************

If Percipio IDs are missing from SSO metadata, identifiers are sent as ``null``:

.. code-block:: json

   {
     "userid": null,
     "orgid": null
   }

Array normalization note
************************

If upstream SSO metadata contains one-element arrays for identifiers, values are
normalized to scalar strings before webhook delivery.
