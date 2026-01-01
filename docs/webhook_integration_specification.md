# Enterprise Webhook Integration - Technical Specification

## Executive Summary

This specification outlines the implementation of a webhook-based integration system that enables Enterprise customers to receive real-time course completion and enrollment notifications via HTTP POST callbacks to their specified endpoints. This solution leverages the OpenEdX Events framework (openedx-events) with Event Bus architecture (Redis/Kafka) to provide a scalable, reliable, event-driven notification system with zone-aware routing and persistent queue-based delivery.

### Key Features

*   **Event-driven architecture** using OpenEdX Events and Event Bus (Redis/Kafka)
*   **Dedicated `consume_events` consumer process** for reliable event consumption
*   **Zone-aware webhook routing** (US/EU/UK/OTHER regions)
*   **Persistent queue** with automatic retry and error handling
*   **Support for both course completions and enrollments**
*   **Full audit trail** for compliance and debugging
*   **Event bus compatible architecture**

---

## 1. Background & Context

### 1.1 Problem Statement

Enterprise customers currently rely on integrated channels (SAP SuccessFactors, Canvas, Cornerstone, etc.) to receive learner completion data. However, many enterprises have custom Learning Management Systems (LMS) or internal platforms that require course completion and enrollment notifications but don't fit into existing channel integrations.

### 1.2 Current State

*   **Existing Integrations**: SAP, Canvas, Cornerstone, Degreed, Moodle, Blackboard
*   **Event Framework**: OpenEdX Events (openedx-events library) with Event Bus
*   **Event Bus**: Redis Streams or Kafka for event distribution
*   **Completion Events**: `org.openedx.learning.student.grade.changed.v1`
*   **Enrollment Events**: `org.openedx.learning.course.enrollment.created.v1`
*   **Consumer**: `consume_events` management command polls event bus
*   **Base Configuration**: `GenericEnterpriseCustomerPluginConfiguration` exists but lacks webhook transmission logic

### 1.3 Proposed Solution

Extend the enterprise integration framework to support webhook-based HTTP POST transmissions when:

*   Learners complete courses with passing grades (consumed from event bus topic `org.openedx.learning.student.grade.changed.v1`)
*   Learners enroll in courses (consumed from event bus topic `org.openedx.learning.course.enrollment.created.v1`)

**Architecture**: Deploy a dedicated `consume_events` consumer process that polls the event bus and directly calls the appropriate handler functions to trigger webhook queueing.

---

## 2. Goals & Objectives

### 2.1 Primary Goals

✅ Enable webhook-based notifications for enterprise events  
✅ Use OpenEdX Events for real-time event handling  
✅ Support zone-aware routing (multiple webhook endpoints per enterprise)  
✅ Provide reliable delivery with retry logic and error handling  
✅ Maintain comprehensive audit trails  
✅ Support both completion and enrollment events  

### 2.2 Non-Goals

❌ Support for non-completion/enrollment events (progress, assessments, etc.) in initial release  
❌ Bi-directional communication (webhook responses beyond success/failure)  
❌ Custom payload templates per enterprise (standardized payload format)  
❌ Webhook signature verification (HMAC) - future enhancement  

---

## 3. Architecture & Design

### 3.1 High-Level Architecture

```
┌─────────────────────────────────────────────────┐
│           LMS Platform (edx-platform)           │
│                                                 │
│  ┌──────────────┐       ┌──────────────┐       │
│  │ Course Grade │       │  Enrollment  │       │
│  │  Calculated  │       │   Created    │       │
│  └──────┬───────┘       └──────┬───────┘       │
│         │                      │                │
│         ▼                      ▼                │
│  ┌──────────────────────────────────────┐      │
│  │      OpenEdX Events Framework        │      │
│  │         (Event Producer)             │      │
│  │  PERSISTENT_GRADE_SUMMARY_CHANGED    │      │
│  │  COURSE_ENROLLMENT_CREATED           │      │
│  └──────────────┬───────────────────────┘      │
└─────────────────┼───────────────────────────────┘
                  │ publish
                  ▼
       ┌──────────────────────────┐
       │   Event Bus              │
       │  (Redis Streams /Kafka)  │
       │                          │
       │  Topics:                 │
       │  • org.openedx.learning. │
       │    student.grade.changed │
       │  • org.openedx.learning. │
       │    course.enrollment...  │
       └──────────┬───────────────┘
                  │ poll/consume
                  ▼
┌─────────────────────────────────────────────────┐
│   Webhook Consumer Service                     │
│   (enterprise-integrated-channels)             │
│                                                 │
│  ┌──────────────────────────────────────┐      │
│  │  Management Command:                 │      │
│  │  consume_events                      │      │
│  │  • Polls event bus                   │      │
│  │  • Calls handler functions           │      │
│  └──────────────┬───────────────────────┘      │
│                 │                               │
│                 ▼                               │
│  ┌──────────────────────────────────────┐      │
│  │  Event Handlers (handlers.py)        │      │
│  │  • handle_grade_change               │      │
│  │  • handle_enrollment                 │      │
│  └──────────────┬───────────────────────┘      │
│                 │                               │
│                 ▼                               │
│  ┌──────────────────────────────────────┐      │
│  │  Zone-Aware Webhook Routing Service  │      │
│  │  • Get user region from SSO          │      │
│  │  • Find matching webhook config      │      │
│  │  • Create queue item                 │      │
│  └──────────────┬───────────────────────┘      │
│                 │                               │
│                 ▼                               │
│  ┌──────────────────────────────────────┐      │
│  │  WebhookTransmissionQueue (DB)       │      │
│  │  • Persistent storage                │      │
│  │  • Status tracking                   │      │
│  │  • Retry scheduling                  │      │
│  └──────────────┬───────────────────────┘      │
│                 │                               │
│                 ▼                               │
│  ┌──────────────────────────────────────┐      │
│  │  Celery Task: process_webhook_queue  │      │
│  │  • HTTP POST to webhook              │      │
│  │  • Handle retry logic                │      │
│  │  • Update queue status               │      │
│  └──────────────┬───────────────────────┘      │
└─────────────────┼───────────────────────────────┘
                  │
                  ▼
         ┌────────────────────────┐
         │  Enterprise Webhook    │
         │  https://client.com/   │
         │  /webhooks/edx         │
         └────────────────────────┘
```

### 3.2 Event Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     Event Flow Timeline                      │
└─────────────────────────────────────────────────────────────┘
1. LMS Event Occurs
   ├─ Grade persisted → PERSISTENT_GRADE_SUMMARY_CHANGED
   └─ Enrollment created → COURSE_ENROLLMENT_CREATED
2. Event Bus (Async)
   ├─ Event published to Redis/Kafka topic
   ├─ Topic: org.openedx.learning.student.grade.changed.v1
   └─ Persisted in event bus stream
3. Consumer Process (consume_events)
   ├─ Polls event bus for new messages
   ├─ Deserializes event data
   └─ Calls handler function directly
4. Event Handler (Sync)
   ├─ Function receives event data
   ├─ Check if enterprise learner
   ├─ Get user region from SSO metadata
   └─ Route to appropriate webhook config
5. Queue Creation (Sync)
   ├─ Create WebhookTransmissionQueue record
   ├─ Status = 'pending'
   └─ Schedule Celery task
6. Async Processing (Celery)
   ├─ Fetch queue item from DB
   ├─ Send HTTP POST to webhook URL
   └─ Handle response
7. Result Handling
   ├─ 2xx → Mark success, done
   ├─ 4xx → Mark failed, no retry
   └─ 5xx/Timeout → Schedule retry with backoff
8. Retry Logic (if needed)
   └─ Retry #1 (30s), #2 (120s), #3 (300s)
```

---

## 4. Data Models

### 4.1 EnterpriseWebhookConfiguration

**Purpose**: Zone-aware webhook configuration for enterprise customers  
**Location**: `enterprise-integrated-channels/integrated_channels/integrated_channel/models.py`

```python
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from model_utils.models import TimeStampedModel
from enterprise.models import EnterpriseCustomer

class EnterpriseWebhookConfiguration(TimeStampedModel):
    """
    Zone-aware webhook configuration for enterprise customers.
    .. no_pii:
    """
    enterprise_customer = models.ForeignKey(
        EnterpriseCustomer,
        on_delete=models.CASCADE,
        related_name='webhook_configurations',
        help_text='Enterprise customer this webhook belongs to'
    )
    region = models.CharField(
        max_length=10,
        choices=[
            ('US', 'United States'),
            ('EU', 'European Union'),
            ('UK', 'United Kingdom'),
            ('OTHER', 'Other'),
        ],
        db_index=True,
        help_text='Geographic region this webhook URL is for'
    )
    webhook_url = models.URLField(
        max_length=500,
        help_text='HTTPS endpoint to receive webhooks'
    )
    webhook_auth_token = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text='Bearer token for webhook authentication'
    )
    webhook_timeout_seconds = models.IntegerField(
        default=30,
        validators=[MinValueValidator(5), MaxValueValidator(300)],
        help_text='HTTP request timeout in seconds (5-300)'
    )
    webhook_retry_attempts = models.IntegerField(
        default=3,
        validators=[MinValueValidator(0), MaxValueValidator(10)],
        help_text='Number of retry attempts on failure (0-10)'
    )
    active = models.BooleanField(
        default=True,
        help_text='Whether this webhook configuration is active'
    )
    class Meta:
        app_label = 'integrated_channel'
        verbose_name = 'Enterprise Webhook Configuration'
        verbose_name_plural = 'Enterprise Webhook Configurations'
        constraints = [
            models.UniqueConstraint(
                fields=['enterprise_customer', 'region'],
                name='unique_enterprise_region_webhook'
            )
        ]
        indexes = [
            models.Index(
                fields=['enterprise_customer', 'region', 'active'],
                name='webhook_config_lookup_idx'
            ),
        ]
    def clean(self):
        """Validate webhook configuration."""
        super().clean()
        if self.webhook_url and not self.webhook_url.startswith('https://'):
            raise ValidationError('Webhook URL must use HTTPS')
```

### 4.2 WebhookTransmissionQueue

**Purpose**: Persistent queue for reliable webhook delivery

```python
class WebhookTransmissionQueue(TimeStampedModel):
    """
    Queue for webhook transmissions to ensure reliable delivery.
    .. pii: Contains user email in payload
    .. pii_types: email_address
    .. pii_retirement: retained
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    enterprise_customer = models.ForeignKey(
        EnterpriseCustomer,
        on_delete=models.CASCADE,
        help_text='Enterprise customer'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        help_text='User whose event is being transmitted'
    )
    course_id = models.CharField(
        max_length=255,
        help_text='Course ID'
    )
    event_type = models.CharField(
        max_length=50,
        choices=[
            ('course_completion', 'Course Completion'),
            ('course_enrollment', 'Course Enrollment'),
        ],
        help_text='Type of event being transmitted'
    )
    user_region = models.CharField(
        max_length=10,
        help_text='User region at time of event'
    )
    webhook_url = models.URLField(
        max_length=500,
        help_text='Webhook URL that was/will be called'
    )
    payload = models.JSONField(
        help_text='JSON payload to be transmitted'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        db_index=True,
        help_text='Transmission status'
    )
    attempt_count = models.IntegerField(
        default=0,
        help_text='Number of transmission attempts'
    )
    last_attempt_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp of last transmission attempt'
    )
    next_retry_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text='Timestamp for next retry attempt'
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp when transmission completed'
    )
    error_message = models.TextField(
        blank=True,
        null=True,
        help_text='Error message from last failed attempt'
    )
    http_status_code = models.IntegerField(
        null=True,
        blank=True,
        help_text='HTTP status code from last attempt'
    )
    response_body = models.TextField(
        blank=True,
        null=True,
        help_text='Response body from last attempt (truncated to 10KB)'
    )
    class Meta:
        app_label = 'integrated_channel'
        indexes = [
            models.Index(fields=['status', 'next_retry_at']),
            models.Index(fields=['enterprise_customer', 'created']),
            models.Index(fields=['user', 'course_id']),
            models.Index(fields=['event_type']),
        ]
```

---

## 5. Event Bus Configuration & Consumer Implementation

### 5.1 Event Bus Settings

**File**: `enterprise-integrated-channels/settings/production.py`

```python
# Event Bus Producer (LMS/CMS publishes events)
EVENT_BUS_PRODUCER = 'edx_event_bus_redis.create_producer'  # or edx_event_bus_kafka.create_producer
EVENT_BUS_REDIS_CONNECTION_URL = 'redis://redis:6379/'
EVENT_BUS_TOPIC_PREFIX = 'prod'

# Event Bus Producer Configuration (LMS/CMS side)
EVENT_BUS_PRODUCER_CONFIG = {
    'org.openedx.learning.student.grade.changed.v1': {
        'enabled': True,
        'event_key_field': 'grade.user_id',
    },
    'org.openedx.learning.course.enrollment.created.v1': {
        'enabled': True,
        'event_key_field': 'enrollment.user.id',
    },
}

# Event Bus Consumer (Webhook service consumes events)
EVENT_BUS_CONSUMER = 'edx_event_bus_redis.RedisEventConsumer'  # or edx_event_bus_kafka.KafkaEventConsumer

# Consumer Group Settings
WEBHOOK_CONSUMER_GROUP = 'enterprise-webhook-consumer'
```

### 5.2 Event Handlers

**File**: `enterprise-integrated-channels/integrated_channels/integrated_channel/handlers.py`

```python
"""
Event handlers for OpenEdX Events consumed from event bus.
These handlers are called directly by the consume_events management command.
"""
import logging
from django.contrib.auth import get_user_model
from openedx_events.learning.data import (
    PersistentGradeData,
    CourseEnrollmentData
)
from enterprise.models import EnterpriseCustomerUser
from integrated_channels.integrated_channel.services.webhook_routing import (
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
        **kwargs: Contains 'grade' key with PersistentGradeData object
    """
    grade_data: PersistentGradeData = kwargs.get('grade')
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
    from django.utils import timezone
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
    from django.utils import timezone
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
            'enrollment_date': enrollment_data.time.isoformat(),
        },
    }
```

### 5.3 Event Consumer Command

#### 5.3.1 Overview

The `consume_events` command is provided by the **edx-event-bus-redis** (or **edx-event-bus-kafka**) library, not by enterprise-integrated-channels. This command:

*   Polls the event bus for messages on specified topics
*   Deserializes event data using the OpenEdX Events framework
*   Dispatches events to registered handler functions
*   Manages consumer group offsets and backlog processing

#### 5.3.2 Handler Registration

To connect your webhook handlers to the event consumer, you must register them in your Django settings using the `EVENT_BUS_CONSUMER_CONFIG` dictionary:

**File**: `enterprise-integrated-channels/settings/production.py`

```python
from integrated_channels.integrated_channel.handlers import (
    handle_grade_change_for_webhooks,
    handle_enrollment_for_webhooks
)

EVENT_BUS_CONSUMER_CONFIG = {
    'org.openedx.learning.student.grade.changed.v1': {
        'event_handler': handle_grade_change_for_webhooks,
    },
    'org.openedx.learning.course.enrollment.created.v1': {
        'event_handler': handle_enrollment_for_webhooks,
    },
}
```

**How it works**:
1.  The `consume_events` command reads `EVENT_BUS_CONSUMER_CONFIG` for the specified topic
2.  It polls the event bus and receives serialized event data
3.  It deserializes the data into the appropriate event data class (e.g., `PersistentGradeData`)
4.  It calls the registered `event_handler` function with the deserialized data
5.  Your handler function processes the event and queues webhooks

#### 5.3.3 Running the Consumer

**Command Syntax**:

```bash
python manage.py consume_events -t <topic> -g <consumer_group> [--extra <json>]
```

**Arguments**:
*   `-t, --topic`: Event topic to consume (required)
*   `-g, --group-id`: Consumer group ID for offset tracking (required)
*   `--extra`: JSON object with additional options (optional)

**Example - Grade Changes**:

```bash
python manage.py consume_events \
    -t org.openedx.learning.student.grade.changed.v1 \
    -g enterprise-webhook-consumer \
    --extra '{"check_backlog": true}'
```

**Example - Enrollments**:

```bash
python manage.py consume_events \
    -t org.openedx.learning.course.enrollment.created.v1 \
    -g enterprise-webhook-consumer \
    --extra '{"check_backlog": true}'
```

**Extra Options**:
*   `check_backlog`: If `true`, process all historical messages in the topic before consuming new ones
*   `claim_msgs_older_than`: Claim messages older than N seconds from other consumers (useful for stale consumer recovery)

#### 5.3.4 Consumer Flow

```
┌─────────────────────────────────────────────────────────────┐
│                  consume_events Command Flow                │
└─────────────────────────────────────────────────────────────┘

1. Command starts
   └─ Reads EVENT_BUS_CONSUMER_CONFIG for topic

2. Initialize consumer
   ├─ Connect to Redis/Kafka
   ├─ Join consumer group
   └─ Load handler function reference

3. Poll loop (infinite)
   ├─ Fetch next message from event bus
   ├─ Deserialize event data
   ├─ Call registered handler: handler(sender, signal, **kwargs)
   ├─ Handler completes (queues webhook)
   └─ Commit offset

4. Error handling
   ├─ Deserialization error → Log and skip message
   ├─ Handler exception → Log and continue
   └─ Connection error → Retry with backoff
```

#### 5.3.5 Important Notes

*   **One consumer process per topic**: Each `consume_events` process handles one topic. Run multiple processes for multiple topics.
*   **Consumer groups**: Using the same group ID across multiple processes enables load balancing. Messages are distributed among group members.
*   **Offset management**: The event bus library automatically tracks which messages have been processed via consumer group offsets.
*   **Graceful shutdown**: The command handles SIGTERM/SIGINT for clean shutdown.

### 5.4 Adding Handlers to Existing Consumers

In most OpenEdX installations, `consume_events` processes are **already running** for grade and enrollment events, managed by the platform infrastructure. You don't need to deploy new consumer processes—you just need to register your webhook handlers.

#### 5.4.1 Configuration Update

**Step 1**: Add handler registration to your settings:

**File**: `enterprise-integrated-channels/settings/production.py` or plugin configuration

```python
from integrated_channels.integrated_channel.handlers import (
    handle_grade_change_for_webhooks,
    handle_enrollment_for_webhooks
)

# Add to existing EVENT_BUS_CONSUMER_CONFIG or create if it doesn't exist
if 'EVENT_BUS_CONSUMER_CONFIG' not in locals():
    EVENT_BUS_CONSUMER_CONFIG = {}

EVENT_BUS_CONSUMER_CONFIG.update({
    'org.openedx.learning.student.grade.changed.v1': {
        'event_handler': handle_grade_change_for_webhooks,
    },
    'org.openedx.learning.course.enrollment.created.v1': {
        'event_handler': handle_enrollment_for_webhooks,
    },
})
```

**Step 2**: Restart the existing consumer processes to pick up the new handlers.

**Important**: If consumers are already processing these topics, adding handlers via `EVENT_BUS_CONSUMER_CONFIG` will automatically invoke your webhook handlers when events arrive. No new processes needed.

#### 5.4.2 Deployment Checklist

- [ ] Implement handler functions in `handlers.py`
- [ ] Add handler registration to `EVENT_BUS_CONSUMER_CONFIG`
- [ ] Deploy updated code to your application servers
- [ ] Restart existing `consume_events` processes (or application servers if using plugin config)
- [ ] Verify handlers are being called by monitoring logs
- [ ] Confirm webhooks are being queued in `WebhookTransmissionQueue`

#### 5.4.3 If Consumers Don't Exist

If your installation does **not** have `consume_events` processes running for these topics, you'll need to start them. Consult your platform operations team or refer to the OpenEdX Event Bus documentation for deployment patterns (Supervisor, Kubernetes, systemd, etc.).

---

## 6. Webhook Payload Formats

### 6.1 Course Completion Webhook

**Event Type**: `course_completion`  
**Triggered By**: `PERSISTENT_GRADE_SUMMARY_CHANGED` (passing grade)

```json
{
  "event_type": "course_completion",
  "event_version": "2.0",
  "event_source": "openedx_events",
  "timestamp": "2025-12-23T16:00:00Z",
  "user_region": "EU",
  "enterprise_customer": {
    "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "name": "Acme Corporation"
  },
  "learner": {
    "user_id": 12345,
    "username": "john.doe",
    "email": "john.doe@acme.com"
  },
  "course": {
    "course_key": "course-v1:edX+DemoX+Demo_Course"
  },
  "completion": {
    "completed": true,
    "completion_date": "2025-12-23T15:45:30Z",
    "percent_grade": 0.85,
    "letter_grade": "B",
    "is_passing": true
  }
}
```

### 6.2 Course Enrollment Webhook

**Event Type**: `course_enrollment`  
**Triggered By**: `COURSE_ENROLLMENT_CREATED`

```json
{
  "event_type": "course_enrollment",
  "event_version": "2.0",
  "event_source": "openedx_events",
  "timestamp": "2025-12-23T10:00:00Z",
  "user_region": "US",
  "enterprise_customer": {
    "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "name": "Acme Corporation"
  },
  "learner": {
    "user_id": 12345,
    "username": "john.doe",
    "email": "john.doe@acme.com"
  },
  "course": {
    "course_key": "course-v1:edX+DemoX+Demo_Course"
  },
  "enrollment": {
    "mode": "verified",
    "is_active": true,
    "enrollment_date": "2025-12-23T10:00:00Z"
  }
}
```

### 6.3 HTTP Request Specifications

**Request Method**: POST  
**Content-Type**: application/json

**Headers**:

```
Authorization: Bearer {webhook_auth_token}
User-Agent: OpenEdX-Enterprise-Integration/2.0
X-Enterprise-Customer-UUID: {enterprise_uuid}
X-Event-Type: {course_completion|course_enrollment}
X-Event-Version: 2.0
X-User-Region: {US|EU|UK|OTHER}
X-Request-ID: webhook-{queue_item_id}
```

**Expected Response**:

| Status Code | Meaning | Action |
|-------------|---------|--------|
| 200-299 | Success | Mark as transmitted, no retry |
| 400-499 | Client error | Mark as failed, no retry |
| 500-599 | Server error | Retry with exponential backoff |
| Timeout | Connection timeout | Retry with exponential backoff |

---

## 7. Error Handling & Retry Logic

### 7.1 Retry Strategy

**Algorithm**: Exponential backoff

```python
retry_delays = [30, 120, 300, 600, 1800, 3600]  # seconds
# 30s, 2min, 5min, 10min, 30min, 1hour
```

**Configuration**:
*   **Maximum retries**: 3 (configurable per webhook)
*   **Retry on**: 5xx errors, timeouts, network failures
*   **No retry on**: 4xx client errors

---

## 8. Additional Implementation Details

### 8.1 Region Detection Service

**File**: `enterprise-integrated-channels/integrated_channels/integrated_channel/services/region_service.py`

```python
"""
Service for determining user region from SSO metadata.
"""
import logging
from typing import Optional

log = logging.getLogger(__name__)

# EU Country Codes (GDPR region)
EU_COUNTRIES = {
    'AT', 'BE', 'BG', 'HR', 'CY', 'CZ', 'DK', 'EE', 'FI', 'FR',
    'DE', 'GR', 'HU', 'IE', 'IT', 'LV', 'LT', 'LU', 'MT', 'NL',
    'PL', 'PT', 'RO', 'SK', 'SI', 'ES', 'SE'
}

def get_user_region(user) -> str:
    """
    Extract user region from SSO metadata with fallback strategy.
    
    Priority:
    1. third_party_auth.UserSocialAuth.extra_data['region'] (explicit)
    2. third_party_auth.UserSocialAuth.extra_data['country'] → map to region
    3. EnterpriseCustomerUser.data_sharing_consent_records (last resort)
    4. Default to 'OTHER'
    
    Args:
        user: Django User instance
        
    Returns:
        str: One of 'US', 'EU', 'UK', 'OTHER'
    """
    try:
        from social_django.models import UserSocialAuth
        
        # Priority 1: Explicit region in SSO extra_data
        social_auth = UserSocialAuth.objects.filter(user=user).first()
        if social_auth and social_auth.extra_data:
            # Check for explicit region
            explicit_region = social_auth.extra_data.get('region')
            if explicit_region in ['US', 'EU', 'UK', 'OTHER']:
                log.debug(f'[Region] User {user.id} has explicit region: {explicit_region}')
                return explicit_region
            
            # Priority 2: Map country code to region
            country_code = social_auth.extra_data.get('country')
            if country_code:
                region = _map_country_to_region(country_code)
                log.debug(f'[Region] User {user.id} mapped from country {country_code} to {region}')
                return region
        
        # Priority 3: Check enterprise customer location (if available)
        from enterprise.models import EnterpriseCustomerUser
        ecu = EnterpriseCustomerUser.objects.filter(user=user, active=True).first()
        if ecu and hasattr(ecu.enterprise_customer, 'country'):
            country_code = ecu.enterprise_customer.country
            region = _map_country_to_region(country_code)
            log.debug(f'[Region] User {user.id} using enterprise country {country_code} -> {region}')
            return region
            
    except Exception as e:
        log.warning(f'[Region] Error detecting region for user {user.id}: {e}')
    
    # Priority 4: Default fallback
    log.info(f'[Region] No region metadata for user {user.id}, defaulting to OTHER')
    return 'OTHER'

def _map_country_to_region(country_code: str) -> str:
    """Map ISO country code to webhook region."""
    country_code = country_code.upper()
    
    if country_code == 'US':
        return 'US'
    elif country_code == 'GB':
        return 'UK'
    elif country_code in EU_COUNTRIES:
        return 'EU'
    else:
        return 'OTHER'
```

### 8.2 Deduplication Strategy

**Update to WebhookTransmissionQueue model**:

```python
class WebhookTransmissionQueue(TimeStampedModel):
    # ... existing fields ...
    
    deduplication_key = models.CharField(
        max_length=255,
        db_index=True,
        help_text='Unique key to prevent duplicate transmissions: {user_id}:{course_id}:{event_type}:{date}'
    )
    
    class Meta:
        app_label = 'integrated_channel'
        constraints = [
            models.UniqueConstraint(
                fields=['deduplication_key'],
                name='unique_webhook_deduplication',
                condition=Q(status__in=['pending', 'processing', 'success'])
            )
        ]
        indexes = [
            models.Index(fields=['status', 'next_retry_at']),
            models.Index(fields=['enterprise_customer', 'created']),
            models.Index(fields=['user', 'course_id']),
            models.Index(fields=['event_type']),
            models.Index(fields=['deduplication_key']),  # New
        ]
```

**Deduplication key generation**:

```python
from django.utils.timezone import now

def generate_deduplication_key(user_id, course_id, event_type):
    """
    Generate unique key for webhook deduplication.
    
    Format: {user_id}:{course_id}:{event_type}:{date}
    
    This prevents duplicate webhooks for the same event on the same day,
    even if multiple consumer instances process the same event.
    """
    date_str = now().strftime('%Y-%m-%d')
    return f"{user_id}:{course_id}:{event_type}:{date_str}"
```

### 8.3 Enhanced Security Validation

**Updated `EnterpriseWebhookConfiguration.clean()` method**:

```python
def clean(self):
    """Validate webhook configuration with comprehensive security checks."""
    super().clean()
    
    if not self.webhook_url:
        return
    
    from urllib.parse import urlparse
    import ipaddress
    
    # 1. Must use HTTPS
    if not self.webhook_url.startswith('https://'):
        raise ValidationError('Webhook URL must use HTTPS')
    
    parsed = urlparse(self.webhook_url)
    hostname = parsed.hostname
    
    if not hostname:
        raise ValidationError('Invalid webhook URL')
    
    # 2. Block localhost (SSRF protection)
    if hostname in ['localhost', '127.0.0.1', '::1', '0.0.0.0']:
        raise ValidationError(
            'Webhook URL cannot point to localhost or loopback addresses'
        )
    
    # 3. Block private IP ranges (SSRF protection)
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_reserved or ip.is_loopback:
            raise ValidationError(
                'Webhook URL cannot point to private or reserved IP addresses'
            )
        # Block cloud metadata endpoints
        if str(ip) == '169.254.169.254':
            raise ValidationError(
                'Webhook URL cannot point to cloud metadata service'
            )
    except ValueError:
        # Hostname is not an IP address, which is fine
        pass
    
    # 4. Block reserved hostnames
    reserved_hostnames = [
        'metadata.google.internal',
        '169.254.169.254',
        'metadata.aws',
        'metadata.azure.com',
    ]
    if hostname in reserved_hostnames:
        raise ValidationError(
            f'Webhook URL cannot use reserved hostname: {hostname}'
        )
```

### 8.4 Rate Limiting Implementation

**Add to `EnterpriseWebhookConfiguration` model** (already mentioned but implementation missing):

```python
max_requests_per_minute = models.IntegerField(
    default=100,
    validators=[MinValueValidator(1), MaxValueValidator(1000)],
    help_text='Maximum webhook requests per minute (1-1000)'
)
```

**Rate limiting logic in Celery task**:

```python
from django.core.cache import cache
from django.utils import timezone

def check_rate_limit(webhook_config):
    """
    Check if webhook transmission is within rate limits.
    
    Returns:
        tuple: (allowed: bool, retry_after_seconds: int)
    """
    cache_key = f'webhook_rate_limit:{webhook_config.id}'
    current_minute = timezone.now().strftime('%Y%m%d%H%M')
    full_cache_key = f'{cache_key}:{current_minute}'
    
    # Get current count for this minute
    current_count = cache.get(full_cache_key, 0)
    
    if current_count >= webhook_config.max_requests_per_minute:
        # Rate limit exceeded, calculate retry time
        retry_after = 60 - timezone.now().second
        return False, retry_after
    
    # Increment counter
    cache.set(full_cache_key, current_count + 1, timeout=70)  # Expire after 70 seconds
    return True, 0
```

### 8.5 Celery Task Implementation

**File**: `enterprise-integrated-channels/integrated_channels/integrated_channel/tasks.py`

```python
"""
Celery tasks for webhook transmission.
"""
import logging
import requests
from celery import shared_task
from django.utils import timezone
from datetime import timedelta

from integrated_channels.integrated_channel.models import (
    WebhookTransmissionQueue,
    EnterpriseWebhookConfiguration
)

log = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=5)
def transmit_webhook(self, queue_item_id):
    """
    Transmit a webhook from the queue.
    
    Args:
        queue_item_id: ID of WebhookTransmissionQueue item
    """
    try:
        queue_item = WebhookTransmissionQueue.objects.get(id=queue_item_id)
    except WebhookTransmissionQueue.DoesNotExist:
        log.error(f'[Webhook] Queue item {queue_item_id} not found')
        return
    
    # Check if already processed
    if queue_item.status in ['success', 'cancelled']:
        log.info(f'[Webhook] Queue item {queue_item_id} already processed: {queue_item.status}')
        return
    
    # Get webhook configuration
    try:
        config = EnterpriseWebhookConfiguration.objects.get(
            enterprise_customer=queue_item.enterprise_customer,
            region=queue_item.user_region,
            active=True
        )
    except EnterpriseWebhookConfiguration.DoesNotExist:
        log.error(f'[Webhook] No active config for {queue_item.enterprise_customer.uuid} / {queue_item.user_region}')
        queue_item.status = 'cancelled'
        queue_item.error_message = 'Webhook configuration no longer active'
        queue_item.save()
        return
    
    # Rate limiting check
    allowed, retry_after = check_rate_limit(config)
    if not allowed:
        log.warning(f'[Webhook] Rate limit exceeded for config {config.id}, retrying in {retry_after}s')
        raise self.retry(countdown=retry_after)
    
    # Update status to processing
    queue_item.status = 'processing'
    queue_item.attempt_count += 1
    queue_item.last_attempt_at = timezone.now()
    queue_item.save()
    
    # Prepare request
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'OpenEdX-Enterprise-Integration/2.0',
        'X-Enterprise-Customer-UUID': str(queue_item.enterprise_customer.uuid),
        'X-Event-Type': queue_item.event_type,
        'X-Event-Version': '1.0',
        'X-User-Region': queue_item.user_region,
        'X-Request-ID': f'webhook-{queue_item.id}',
    }
    
    if config.webhook_auth_token:
        headers['Authorization'] = f'Bearer {config.webhook_auth_token}'
    
    try:
        # Make HTTP request
        response = requests.post(
            queue_item.webhook_url,
            json=queue_item.payload,
            headers=headers,
            timeout=config.webhook_timeout_seconds,
            allow_redirects=False,  # Security: don't follow redirects
        )
        
        # Store response details
        queue_item.http_status_code = response.status_code
        queue_item.response_body = response.text[:10000]  # Truncate to 10KB
        
        # Handle response
        if 200 <= response.status_code < 300:
            # Success
            queue_item.status = 'success'
            queue_item.completed_at = timezone.now()
            queue_item.error_message = None
            log.info(f'[Webhook] Successfully transmitted {queue_item_id} to {queue_item.webhook_url}')
        
        elif 400 <= response.status_code < 500:
            # Client error - don't retry (except 429)
            if response.status_code == 429:
                # Rate limited by customer endpoint
                retry_after = int(response.headers.get('Retry-After', 60))
                raise self.retry(countdown=retry_after)
            else:
                queue_item.status = 'failed'
                queue_item.error_message = f'Client error {response.status_code}: {response.text[:500]}'
                log.error(f'[Webhook] Client error for {queue_item_id}: {response.status_code}')
        
        else:
            # Server error - retry with exponential backoff
            raise self.retry(exc=Exception(f'Server error: {response.status_code}'))
        
        queue_item.save()
        
    except requests.exceptions.Timeout:
        log.warning(f'[Webhook] Timeout for {queue_item_id}')
        queue_item.error_message = 'Request timeout'
        queue_item.save()
        raise self.retry(exc=Exception('Timeout'))
    
    except requests.exceptions.RequestException as e:
        log.error(f'[Webhook] Network error for {queue_item_id}: {e}')
        queue_item.error_message = f'Network error: {str(e)[:500]}'
        queue_item.save()
        raise self.retry(exc=e)
    
    except Exception as e:
        log.error(f'[Webhook] Unexpected error for {queue_item_id}: {e}', exc_info=True)
        queue_item.status = 'failed'
        queue_item.error_message = f'Unexpected error: {str(e)[:500]}'
        queue_item.save()
```

---

## 9. Monitoring & Observability

### 9.1 Metrics

Emit the following metrics to your monitoring system (Datadog, NewRelic, Prometheus, etc.):

**Counters**:
*   `webhook.queued` - Webhook successfully queued
*   `webhook.transmission_attempt` - HTTP POST attempt made
*   `webhook.success` - 2xx response received
*   `webhook.failed` - Permanent failure (4xx or max retries exceeded)
*   `webhook.retried` - Temporary failure, retry scheduled

**Gauges**:
*   `webhook.queue_depth` - Number of pending items in queue
*   `webhook.oldest_pending_age_seconds` - Age of oldest pending webhook

**Histograms**:
*   `webhook.latency_ms` - HTTP request duration
*   `webhook.queue_wait_time_seconds` - Time from queue creation to transmission

**Tags**: All metrics should include tags:
*   `enterprise_customer_uuid`
*   `region` (US/EU/UK/OTHER)
*   `event_type` (course_completion/course_enrollment)
*   `status_code` (for transmission attempts)

### 9.2 Logging

**Log Levels**:
*   `DEBUG`: Event received, region detected
*   `INFO`: Webhook queued, successful transmission
*   `WARNING`: Rate limit hit, retry scheduled
*   `ERROR`: Permanent failure, config not found, unexpected errors

**Log Format**:
```
[Webhook] {action} for user {user_id}, enterprise {uuid}, course {course_id}: {details}
```

### 9.3 Alerts

**Critical Alerts**:
*   **High Failure Rate**: > 5% of webhooks failing over 10 minutes
*   **Queue Stagnation**: Oldest pending item > 1 hour old
*   **Consumer Lag**: Event bus consumer lag > 1000 messages

**Warning Alerts**:
*   **Elevated Retry Rate**: > 20% of transmissions being retried
*   **Queue Depth Growth**: Queue depth increasing for > 30 minutes

### 9.4 Dashboard

Recommended dashboard panels:
1.  Webhook transmission rate (success vs failure)
2.  Queue depth over time
3.  Transmission latency (p50, p95, p99)
4.  Failure breakdown by status code
5.  Top failing webhook configurations

---

## 10. Security & Compliance

### 10.1 Data Privacy (GDPR/CCPA)

**PII in Webhooks**: Webhook payloads contain:
*   User email address
*   Username
*   User ID

**Requirements**:
1.  **Data Processing Agreement (DPA)**: Enterprise customer must sign a DPA before webhook configuration is enabled
2.  **Data Residency**: Zone-aware routing ensures customer data stays in the appropriate region
3.  **Retention**: Webhook transmission logs retained for 30 days for audit, then purged
4.  **Consent**: Only transmit data for users with active `EnterpriseCustomerUser` relationship

### 10.2 Audit Trail

All webhook transmissions are logged in `WebhookTransmissionQueue` with:
*   Full payload sent
*   HTTP response received
*   Timestamp of each attempt
*   Final status (success/failed)

Retention: 30 days in database, archived to cold storage for 7 years for compliance.

### 10.3 Security Best Practices

*   **HTTPS Only**: All webhook URLs must use HTTPS
*   **SSRF Protection**: Comprehensive validation blocks private IPs, localhost, cloud metadata
*   **Bearer Token Auth**: Optional but recommended authentication
*   **No Redirects**: HTTP redirects are not followed to prevent SSRF
*   **Response Size Limit**: Response bodies truncated to 10KB to prevent memory issues

---

## 11. Testing Strategy

### 11.1 Unit Tests

**Test Coverage**:
*   Region detection logic with various SSO provider configurations
*   Deduplication key generation
*   SSRF validation (localhost, private IPs, cloud metadata)
*   Rate limiting calculations
*   Retry backoff logic

**Example Test**:
```python
from django.test import TestCase
from integrated_channels.integrated_channel.services.region_service import get_user_region

class RegionDetectionTestCase(TestCase):
    def test_region_from_sso_country_eu(self):
        """Test EU region mapping from SSO country code."""
        user = UserFactory()
        UserSocialAuthFactory(
            user=user,
            extra_data={'country': 'DE'}
        )
        self.assertEqual(get_user_region(user), 'EU')
    
    def test_region_fallback_to_other(self):
        """Test fallback to OTHER when no SSO data."""
        user = UserFactory()
        self.assertEqual(get_user_region(user), 'OTHER')
```

### 11.2 Integration Tests

**Test Scenarios**:
1.  **End-to-End Flow**: Publish event to mock event bus → verify webhook queued → verify HTTP POST sent
2.  **Duplicate Event Handling**: Publish same event twice → verify only one webhook queued
3.  **Multi-Region Routing**: User with EU region → verify EU webhook URL used
4.  **Retry Logic**: Mock HTTP 503 error → verify retry scheduled with correct backoff

**Mock Event Bus**:
```python
from unittest.mock import patch
from openedx_events.learning.signals import PERSISTENT_GRADE_SUMMARY_CHANGED

class WebhookIntegrationTestCase(TestCase):
    @patch('integrated_channels.integrated_channel.tasks.transmit_webhook.delay')
    def test_grade_event_queues_webhook(self, mock_task):
        """Test that grade change event queues webhook."""
        user = UserFactory()
        enterprise = EnterpriseCustomerFactory()
        EnterpriseCustomerUserFactory(user=user, enterprise_customer=enterprise)
        EnterpriseWebhookConfigurationFactory(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://customer.example.com/webhook'
        )
        
        # Emit event
        PERSISTENT_GRADE_SUMMARY_CHANGED.send_event(
            grade=PersistentGradeData(
                user_id=user.id,
                passed_timestamp=timezone.now(),
                # ... other fields
            )
        )
        
        # Verify webhook queued
        self.assertEqual(WebhookTransmissionQueue.objects.count(), 1)
        queue_item = WebhookTransmissionQueue.objects.first()
        self.assertEqual(queue_item.user, user)
        self.assertEqual(queue_item.event_type, 'course_completion')
        
        # Verify Celery task called
        mock_task.assert_called_once_with(queue_item.id)
```

### 11.3 Load Testing

Use Locust or similar to simulate:
*   1000 concurrent course completions
*   Verify queue handles burst traffic
*   Verify rate limiting prevents overwhelming customer endpoints
*   Measure transmission latency under load

---

## 12. References

*   [OpenEdX Events Documentation](https://docs.openedx.org/projects/openedx-events/)
*   [Event Bus Documentation](https://github.com/openedx/event-bus-redis)
*   [Celery Documentation](https://docs.celeryproject.org/)
*   [GDPR Compliance Guide](https://gdpr.eu/)
