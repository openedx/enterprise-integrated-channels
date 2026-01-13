# Technical Specification: Add Learning Time to Webhook Payloads

---

## Overview

### Purpose
Enhance webhook payloads sent to third-party integrators (e.g., Skillsoft) by including **total learning time** data for learners in courses. This provides partners with comprehensive learner engagement metrics.

### Scope
- Add `learning_time` field to **course_completion** webhook payloads only
- Query learning time data from Snowflake data warehouse
- Implement async enrichment with caching for performance
- Ensure graceful degradation if Snowflake is unavailable

### Related Documentation
- [Webhook Integration Guide PDF|./OpenEdX_Enterprise_Webhook_Integration_Guide.pdf]
- [Integration Test Evaluation|./INTEGRATION_TEST_EVALUATION.md]

---

## Background

### Current State
Webhook payloads currently include:
- **Course Completion Events:** completion_date, percent_grade, letter_grade, is_passing
- **Course Enrollment Events:** enrollment_date, mode, is_active

### Gap
Third-party integrators (like Skillsoft) require **total time spent by learners** in completed courses to:
- Track learner engagement and course effectiveness
- Calculate ROI on course subscriptions
- Measure actual learning effort vs course completion
- Generate compliance and training reports with time-on-task metrics

### Learning Time Data Source
Learning time is calculated in the **warehouse-transforms** repository and stored in Snowflake:
- **Table:** `PROD.BUSINESS_INTELLIGENCE.LEARNING_TIME`
- **Calculation Method:** Based on Segment event data (page views, video interactions, LTI block completions)
- **Logic:** Time between sequential events, capped at 30 minutes per session
- **Granularity:** Daily rollup per user/course/enterprise

---

## Architecture

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. LMS Event Triggered (Course Completion)                 │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Event Handler (handle_grade_change_for_webhooks)        │
│    - Determines affected integrations                       │
│    - Queues Celery task per integration                     │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Celery Task (enrich_and_send_completion_webhook)        │
│    - Checks feature flag                                    │
│    - Queries learning time from Snowflake (with cache)      │
│    - Falls back to standard payload if Snowflake fails      │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Webhook Routing (route_event)                           │
│    - Sends HTTP POST to integration endpoint                │
│    - Handles retries and error responses                    │
└─────────────────────────────────────────────────────────────┘
```

### Component Diagram

```
┌────────────────────┐        ┌──────────────────────┐
│   LMS (edxapp)     │        │   Redis (Celery)     │
│                    │        │                      │
│  Event Handler ────┼───────▶│  Task Queue          │
│  (handlers.py)     │        │  (webhook_enrichment)│
└────────────────────┘        └──────────┬───────────┘
                                         │
                                         ▼
┌────────────────────┐        ┌──────────────────────┐
│   Celery Worker    │◀───────│   Snowflake          │
│                    │  Query │   (LEARNING_TIME)    │
│  Enrichment Task   │────────▶                      │
│  (tasks.py)        │        └──────────────────────┘
└────────┬───────────┘
         │                     ┌──────────────────────┐
         │                     │   Memcache           │
         └────────────────────▶│   (Cache Layer)      │
         │                     └──────────────────────┘
         │
         ▼
┌────────────────────┐        ┌──────────────────────┐
│  Webhook Router    │        │  Third-Party         │
│  (route_event)     │───────▶│  Integration         │
│                    │  POST  │  (e.g., Skillsoft)   │
└────────────────────┘        └──────────────────────┘
```

### Async Processing Rationale
- **Performance:** Snowflake queries take 2-5 seconds initially; caching reduces to <10ms
- **Reliability:** Network issues or Snowflake downtime won't block webhook delivery
- **Scalability:** Celery workers can process tasks in parallel
- **Graceful Degradation:** Webhooks still sent even if learning time unavailable

---

## Implementation Details

### 3.1 Snowflake Client

**New File:** `enterprise-integrated-channels/channel_integrations/integrated_channel/snowflake_client.py`

```python
"""
Snowflake client for querying learning time data.
"""
import logging
from contextlib import contextmanager
from django.conf import settings
from django.core.cache import cache
import snowflake.connector

logger = logging.getLogger(__name__)

LEARNING_TIME_CACHE_KEY_TEMPLATE = 'learning_time:{user_id}:{course_id}:{enterprise_id}'
LEARNING_TIME_CACHE_TTL = 3600  # 1 hour


class SnowflakeLearningTimeClient:
    """Client for querying learning time data from Snowflake."""
    
    def __init__(self):
        self.account = settings.SNOWFLAKE_ACCOUNT
        self.warehouse = settings.SNOWFLAKE_WAREHOUSE
        self.database = settings.SNOWFLAKE_DATABASE
        self.schema = settings.SNOWFLAKE_SCHEMA
        self.role = settings.SNOWFLAKE_ROLE
        self.user = settings.SNOWFLAKE_SERVICE_USER
        self.password = settings.SNOWFLAKE_SERVICE_USER_PASSWORD
    
    @contextmanager
    def _get_connection(self):
        """Context manager for Snowflake connections."""
        conn = None
        try:
            conn = snowflake.connector.connect(
                account=self.account,
                user=self.user,
                password=self.password,
                warehouse=self.warehouse,
                database=self.database,
                schema=self.schema,
                role=self.role,
            )
            yield conn
        except Exception as e:
            logger.error(f"Failed to connect to Snowflake: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def get_learning_time(self, user_id, course_id, enterprise_customer_uuid):
        """
        Query total learning time for a user/course/enterprise combination.
        
        Args:
            user_id (int): LMS user ID
            course_id (str): Course key (e.g., 'course-v1:edX+DemoX+Demo_Course')
            enterprise_customer_uuid (str): Enterprise customer UUID
        
        Returns:
            int: Total learning time in seconds, or None if not found
        """
        # Check cache first
        cache_key = LEARNING_TIME_CACHE_KEY_TEMPLATE.format(
            user_id=user_id,
            course_id=course_id,
            enterprise_id=enterprise_customer_uuid
        )
        cached_value = cache.get(cache_key)
        if cached_value is not None:
            logger.info(f"Cache hit for learning time: {cache_key}")
            return cached_value
        
        # Query Snowflake
        query = """
        SELECT SUM(LEARNING_TIME_SECONDS) as total_learning_time
        FROM PROD.BUSINESS_INTELLIGENCE.LEARNING_TIME
        WHERE USER_ID = %s
          AND COURSE_KEY = %s
          AND ENTERPRISE_CUSTOMER_UUID = %s
        """
        
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (user_id, course_id, enterprise_customer_uuid))
                result = cursor.fetchone()
                cursor.close()
                
                if result and result[0] is not None:
                    learning_time = int(result[0])
                    # Cache the result
                    cache.set(cache_key, learning_time, LEARNING_TIME_CACHE_TTL)
                    logger.info(f"Learning time retrieved from Snowflake: {learning_time}s for {cache_key}")
                    return learning_time
                else:
                    logger.warning(f"No learning time found for {cache_key}")
                    # Cache negative result to avoid repeated queries
                    cache.set(cache_key, 0, LEARNING_TIME_CACHE_TTL)
                    return None
        
        except Exception as e:
            logger.error(f"Error querying Snowflake for learning time: {e}")
            return None
```

### 3.2 Updated Payload Structure

**File:** `enterprise-integrated-channels/channel_integrations/integrated_channel/handlers.py`

**Modified Function:**
- `_prepare_completion_payload()` - Add optional `learning_time_seconds` parameter

**Note:** Enrollment payloads remain unchanged (no learning time added)

**New Payload Fields (Completion Events Only):**

```json
{
  "user": {
    "id": 12345,
    "email": "learner@example.com",
    "username": "learner_user"
  },
  "course": {
    "course_id": "course-v1:edX+DemoX+Demo_Course",
    "course_name": "edX Demo Course"
  },
  "completion": {
    "completion_date": "2026-01-10T15:30:00Z",
    "percent_grade": 0.92,
    "letter_grade": "A",
    "is_passing": true
  },
  "learning_time": {
    "total_seconds": 18540,
    "total_hours": 5.15,
    "last_updated": "2026-01-10T00:00:00Z"
  },
  "enterprise": {
    "enterprise_customer_uuid": "a1b2c3d4-...",
    "enterprise_customer_name": "Demo Corp"
  }
}
```

**Field Descriptions:**
- `learning_time.total_seconds` (integer, optional): Total cumulative learning time in seconds
- `learning_time.total_hours` (float, optional): Total learning time in hours (rounded to 2 decimals)
- `learning_time.last_updated` (string, optional): Timestamp when learning time was last calculated (warehouse batch date)

> ****ℹ️ Note:****
**Note:** The `learning_time` object is optional and will be omitted if:
- Feature flag is disabled
- Snowflake query fails
- No learning time data exists for the user/course/enterprise combination
> ****ℹ️ Note:****

### 3.3 Celery Task for Enrichment

**New File:** `enterprise-integrated-channels/channel_integrations/integrated_channel/tasks.py`

```python
"""
Celery tasks for webhook enrichment.
"""
import logging
from celery import shared_task
from datetime import datetime
from django.conf import settings
from enterprise.utils import get_enterprise_customer
from .snowflake_client import SnowflakeLearningTimeClient
from .router import route_event

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def enrich_and_send_completion_webhook(self, event_data, integration_config_id):
    """
    Enrich completion webhook with learning time and send to integration.
    
    Args:
        event_data (dict): Course completion event data
        integration_config_id (int): Integration configuration ID
    """
    try:
        # Check feature flag
        if not settings.FEATURES.get('ENABLE_WEBHOOK_LEARNING_TIME_ENRICHMENT', False):
            logger.info("Learning time enrichment disabled, sending standard webhook")
            route_event(event_data, integration_config_id)
            return
        
        # Extract identifiers
        user_id = event_data['user']['id']
        course_id = event_data['course']['course_id']
        enterprise_uuid = event_data['enterprise']['enterprise_customer_uuid']
        
        # Query learning time
        client = SnowflakeLearningTimeClient()
        learning_time_seconds = client.get_learning_time(
            user_id=user_id,
            course_id=course_id,
            enterprise_customer_uuid=enterprise_uuid
        )
        
        # Add learning time to payload if available
        if learning_time_seconds:
            event_data['learning_time'] = {
                'total_seconds': learning_time_seconds,
                'total_hours': round(learning_time_seconds / 3600, 2),
                'last_updated': datetime.utcnow().strftime('%Y-%m-%dT00:00:00Z')
            }
            logger.info(f"Enriched webhook with learning time: {learning_time_seconds}s")
        else:
            logger.warning(f"No learning time available for user {user_id}, course {course_id}")
        
        # Send webhook (with or without learning time)
        route_event(event_data, integration_config_id)
        
    except Exception as exc:
        logger.error(f"Error enriching webhook: {exc}")
        # Retry on transient errors
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        else:
            # Send webhook without learning time after max retries
            logger.error("Max retries reached, sending webhook without learning time")
            route_event(event_data, integration_config_id)
```

### 3.4 Updated Event Handler

**File:** `enterprise-integrated-channels/channel_integrations/integrated_channel/handlers.py`

**Changes:**
- Modify `handle_grade_change_for_webhooks()` to queue Celery task instead of immediate routing

```python
from .tasks import enrich_and_send_completion_webhook

def handle_grade_change_for_webhooks(sender, ****kwargs):
    """
    Handle grade change events and trigger webhook enrichment tasks.
    """
    grade = kwargs.get('grade')
    user = grade.user
    course_id = str(grade.course_id)
    
    # Find all webhook integrations for this course
    integrations = get_active_webhook_integrations(course_id)
    
    for integration in integrations:
        # Prepare base event data
        event_data = _prepare_completion_payload(user, grade, integration)
        
        # Queue async enrichment task
        enrich_and_send_completion_webhook.apply_async(
            args=[event_data, integration.id],
            queue='edx.lms.core.webhook_enrichment'
        )
        logger.info(f"Queued webhook enrichment task for integration {integration.id}")
```

---

## Configuration

### 4.1 Snowflake Configuration

**File:** `lms/envs/production.py` (or via environment variables)

```python
# Snowflake Configuration for Learning Time
SNOWFLAKE_ACCOUNT = 'edx.us-east-1'  # Verify with Data Engineering
SNOWFLAKE_WAREHOUSE = 'REPORTING_WH'
SNOWFLAKE_DATABASE = 'PROD'
SNOWFLAKE_SCHEMA = 'BUSINESS_INTELLIGENCE'
SNOWFLAKE_ROLE = 'ANALYST'
SNOWFLAKE_SERVICE_USER = os.environ.get('SNOWFLAKE_SERVICE_USER', 'ENTERPRISE_SERVICE_USER')
SNOWFLAKE_SERVICE_USER_PASSWORD = os.environ.get('SNOWFLAKE_SERVICE_USER_PASSWORD')
```

> ****⚠️ Warning:****
**Security Note:** `SNOWFLAKE_SERVICE_USER_PASSWORD` must be stored in secure secrets management (e.g., AWS Secrets Manager) and injected as environment variable. Never commit passwords to version control.
> ****⚠️ Warning:****

### 4.2 Cache Configuration

**File:** `lms/envs/production.py`

```python
# Cache configuration (already exists, no changes needed)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.memcached.PyMemcacheCache',
        'LOCATION': [
            'prod-edxapp-004.6sxrym.0001.use1.cache.amazonaws.com:11211',
            'prod-edxapp-004.6sxrym.0002.use1.cache.amazonaws.com:11211',
            'prod-edxapp-004.6sxrym.0003.use1.cache.amazonaws.com:11211',
        ],
        'TIMEOUT': 3600,
        'OPTIONS': {
            'no_delay': True,
            'ignore_exc': True,
            'max_pool_size': 10,
        }
    }
}
```

### 4.3 Celery Queue Configuration

**File:** `lms/envs/production.py`

```python
# Add new Celery queue for webhook enrichment
CELERY_TASK_ROUTES = {
    'enterprise-integrated-channels.tasks.enrich_and_send_completion_webhook': {
        'queue': 'edx.lms.core.webhook_enrichment'
    },
}

# Celery broker (already configured)
CELERY_BROKER_URL = 'redis://edx-prod-queues-edxapp.6sxrym.ng.0001.use1.cache.amazonaws.com:6379/0'
```

### 4.4 Feature Flag

**Django Admin:** `/admin/waffle/`

```
Flag Name: ENABLE_WEBHOOK_LEARNING_TIME_ENRICHMENT
Type: Feature Flag (Waffle)
Default: False
Purpose: Enable/disable learning time enrichment for webhooks
Rollout Strategy:
  - Stage 1: Enable for 1 pilot customer (e.g., Skillsoft)
  - Stage 2: Enable for 10% of customers
  - Stage 3: Enable for 50% of customers
  - Stage 4: Enable for all customers (100%)
```

---

## Dependencies

### New Python Packages

**File:** `requirements/production.txt`

```text
snowflake-connector-python==3.7.0
```

### Existing Dependencies (Already Available)
- `django` (LMS framework)
- `celery` (async task queue)
- `redis` (Celery broker)
- `pymemcache` (cache backend)
- `requests` (HTTP client for webhooks)

---

## Testing Strategy

### 6.1 Unit Tests

**File:** `tests/test_snowflake_client.py`

```python
import pytest
from unittest.mock import patch, MagicMock
from channel_integrations.integrated_channel.snowflake_client import SnowflakeLearningTimeClient

class TestSnowflakeLearningTimeClient:
    
    @patch('snowflake.connector.connect')
    @patch('django.core.cache.cache.get')
    @patch('django.core.cache.cache.set')
    def test_get_learning_time_cache_hit(self, mock_cache_set, mock_cache_get, mock_connect):
        """Test that cached learning time is returned without Snowflake query."""
        mock_cache_get.return_value = 12345
        
        client = SnowflakeLearningTimeClient()
        result = client.get_learning_time(
            user_id=100,
            course_id='course-v1:edX+Demo+2024',
            enterprise_customer_uuid='abc-123'
        )
        
        assert result == 12345
        mock_connect.assert_not_called()
    
    @patch('snowflake.connector.connect')
    @patch('django.core.cache.cache.get')
    @patch('django.core.cache.cache.set')
    def test_get_learning_time_query_success(self, mock_cache_set, mock_cache_get, mock_connect):
        """Test successful Snowflake query."""
        mock_cache_get.return_value = None
        
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (18540,)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value.__enter__.return_value = mock_conn
        
        client = SnowflakeLearningTimeClient()
        result = client.get_learning_time(
            user_id=100,
            course_id='course-v1:edX+Demo+2024',
            enterprise_customer_uuid='abc-123'
        )
        
        assert result == 18540
        mock_cache_set.assert_called_once()
    
    @patch('snowflake.connector.connect')
    @patch('django.core.cache.cache.get')
    def test_get_learning_time_no_data(self, mock_cache_get, mock_connect):
        """Test handling when no learning time data exists."""
        mock_cache_get.return_value = None
        
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value.__enter__.return_value = mock_conn
        
        client = SnowflakeLearningTimeClient()
        result = client.get_learning_time(
            user_id=100,
            course_id='course-v1:edX+Demo+2024',
            enterprise_customer_uuid='abc-123'
        )
        
        assert result is None
```

**File:** `tests/test_webhook_tasks.py`

```python
import pytest
from unittest.mock import patch, MagicMock
from channel_integrations.integrated_channel.tasks import enrich_and_send_completion_webhook

class TestWebhookEnrichmentTask:
    
    @patch('channel_integrations.integrated_channel.tasks.SnowflakeLearningTimeClient')
    @patch('channel_integrations.integrated_channel.tasks.route_event')
    @patch('django.conf.settings.FEATURES', {'ENABLE_WEBHOOK_LEARNING_TIME_ENRICHMENT': True})
    def test_enrich_and_send_success(self, mock_route_event, mock_client_class):
        """Test successful enrichment and webhook send."""
        mock_client = MagicMock()
        mock_client.get_learning_time.return_value = 18540
        mock_client_class.return_value = mock_client
        
        event_data = {
            'user': {'id': 100},
            'course': {'course_id': 'course-v1:edX+Demo+2024'},
            'enterprise': {'enterprise_customer_uuid': 'abc-123'}
        }
        
        enrich_and_send_completion_webhook(event_data, integration_config_id=5)
        
        assert 'learning_time' in event_data
        assert event_data['learning_time']['total_seconds'] == 18540
        mock_route_event.assert_called_once()
    
    @patch('channel_integrations.integrated_channel.tasks.SnowflakeLearningTimeClient')
    @patch('channel_integrations.integrated_channel.tasks.route_event')
    @patch('django.conf.settings.FEATURES', {'ENABLE_WEBHOOK_LEARNING_TIME_ENRICHMENT': False})
    def test_feature_flag_disabled(self, mock_route_event, mock_client_class):
        """Test that enrichment is skipped when feature flag is off."""
        event_data = {
            'user': {'id': 100},
            'course': {'course_id': 'course-v1:edX+Demo+2024'},
            'enterprise': {'enterprise_customer_uuid': 'abc-123'}
        }
        
        enrich_and_send_completion_webhook(event_data, integration_config_id=5)
        
        assert 'learning_time' not in event_data
        mock_client_class.assert_not_called()
        mock_route_event.assert_called_once()
```

### 6.2 Integration Tests

**Environment:** Stage

**Test Scenarios:**

# **Test 1: End-to-End Completion Event with Learning Time**
-  Trigger a course completion in stage environment
-  Verify Celery task is queued
-  Verify Snowflake query executes successfully
-  Verify webhook payload includes `learning_time` object
-  Verify webhook is delivered to integration endpoint

# **Test 2: Snowflake Unavailable (Graceful Degradation)**
-  Temporarily disable Snowflake connectivity
-  Trigger a course completion
-  Verify webhook is still sent (without `learning_time`)
-  Verify error is logged but webhook delivery succeeds

# **Test 3: Cache Behavior**
-  Trigger completion for same user/course twice
-  First request: Verify Snowflake query executes
-  Second request: Verify cache hit (no Snowflake query)
-  Verify both webhooks sent successfully

# **Test 4: Feature Flag Off**
-  Disable `ENABLE_WEBHOOK_LEARNING_TIME_ENRICHMENT`
-  Trigger course completion
-  Verify webhook is sent immediately (no Celery task)
-  Verify `learning_time` field is absent

### 6.3 Load Testing

**Tool:** Locust or Apache JMeter

**Scenarios:**
- Simulate 100 concurrent course completions
- Measure Celery task queue depth
- Monitor Snowflake query performance
- Verify cache hit rate >80% after warmup
- Ensure webhook delivery latency <5 seconds (p95)

---

## Monitoring & Observability

### 7.1 Metrics

**DataDog Custom Metrics:**

|Metric Name|Type|Description|Alert Threshold|
|`webhook.learning_time.query.duration`|Histogram|Snowflake query duration (ms)|>5000ms (p95)|
|`webhook.learning_time.query.success`|Counter|Successful queries|<95% success rate|
|`webhook.learning_time.query.failure`|Counter|Failed queries|>5% failure rate|
|`webhook.learning_time.cache.hit_rate`|Gauge|Cache hit percentage|<80% hit rate|
|`webhook.enrichment.task.queued`|Counter|Tasks queued|>10,000 backlog|
|`webhook.enrichment.task.duration`|Histogram|Task execution time (s)|>10s (p95)|
|`webhook.delivery.success_with_learning_time`|Counter|Webhooks with learning time|Monitor trend|
|`webhook.delivery.success_without_learning_time`|Counter|Webhooks without learning time|>20% of total|

### 7.2 Logging

**Log Levels:**
- `INFO`: Successful queries, cache hits, webhook delivery
- `WARNING`: No learning time data found, feature flag disabled
- `ERROR`: Snowflake connection failures, query errors, task retries exhausted

**Log Examples:**

```json
{
  "timestamp": "2026-01-12T10:30:00Z",
  "level": "INFO",
  "message": "Learning time retrieved from Snowflake: 18540s",
  "context": {
    "user_id": 12345,
    "course_id": "course-v1:edX+DemoX+Demo_Course",
    "enterprise_uuid": "abc-123",
    "query_duration_ms": 2340
  }
}

{
  "timestamp": "2026-01-12T10:31:00Z",
  "level": "ERROR",
  "message": "Failed to connect to Snowflake",
  "context": {
    "error": "Connection timeout after 30s",
    "retry_count": 2
  }
}
```

### 7.3 Dashboards

**DataDog Dashboard: Webhook Learning Time Enrichment**

**Panels:**
# Snowflake Query Performance (p50, p95, p99 latency)
# Cache Hit Rate (gauge, target: >80%)
# Task Queue Depth (line chart)
# Enrichment Success Rate (gauge, target: >95%)
# Webhook Delivery Status (stacked bar: with/without learning time)
# Error Rate by Type (pie chart: connection, query, timeout)

---

## Security Considerations

### Data Privacy
- Learning time data is **aggregated** (no individual session details exposed)
- Snowflake query only accesses `LEARNING_TIME` table (read-only access)
- Service user has minimal permissions (`ANALYST` role, no write access)

### Credential Management
- Snowflake password stored in **AWS Secrets Manager**
- Credentials rotated every 90 days
- No credentials in version control or logs

### Network Security
- Snowflake connection over TLS 1.2+
- Webhook endpoints must use HTTPS
- IP whitelisting for Snowflake access (LMS worker IPs only)

---

## Operations

### 9.1 Performance Characteristics

|Operation|Cold (Snowflake)|Warm (Cache)|
|Learning time query|2-5 seconds|<10 milliseconds|
|Celery task execution|3-6 seconds total|<1 second total|
|Webhook delivery|1-2 seconds|1-2 seconds|
|**Total latency (completion → webhook)**|**6-13 seconds**|**2-3 seconds**|

### 9.2 Failure Modes & Recovery

|Failure Mode|Impact|Recovery|
|Snowflake unavailable|Webhooks sent without learning time|Automatic: Task retries 3x, then sends without data|
|Cache unavailable|Increased Snowflake load|Automatic: Falls back to direct queries|
|Celery broker down|Webhooks delayed|Manual: Restart Redis, tasks resume from queue|
|Task retries exhausted|Webhook sent without learning time|Automatic: Logged for investigation|

### 9.3 Runbook: Disable Learning Time Enrichment

> ****ℹ️ Note:****
**When to use:** Snowflake outage, performance degradation, or data quality issues
> ****ℹ️ Note:****

**Steps:**
# Navigate to Django Admin: `https://lms.edx.org/admin/waffle/flag/`
# Find flag: `ENABLE_WEBHOOK_LEARNING_TIME_ENRICHMENT`
# Uncheck "Active" checkbox
# Click "Save"
# **Result:** Webhooks will be sent immediately without learning time enrichment

**Verification:**
```bash
# Check recent webhooks do NOT include learning_time field
grep -A 50 "Webhook payload" /var/log/edx/lms.log | grep -c "learning_time"
# Should return 0 if flag is off
```

---

## Rollout Plan

### Phase 1: Pilot (1 Customer)
- **Target:** Skillsoft integration
- **Duration:** 1 week
- **Success Criteria:**
-  100% webhook delivery success rate
-  >80% cache hit rate
-  <5 second p95 latency
-  Skillsoft confirms learning time data accuracy

### Phase 2: Limited Rollout (10% of Customers)
- **Target:** Randomly selected 10% of webhook integrations
- **Duration:** 1 week
- **Success Criteria:**
-  No increase in webhook delivery errors
-  Snowflake query volume <500/hour
-  No Celery queue backlog (depth <100)

### Phase 3: Expanded Rollout (50% of Customers)
- **Target:** 50% of webhook integrations
- **Duration:** 1 week
- **Success Criteria:**
-  Snowflake query performance stable (p95 <5s)
-  Cache hit rate >80%
-  No customer complaints about delayed webhooks

### Phase 4: Full Rollout (100% of Customers)
- **Target:** All webhook integrations
- **Duration:** Ongoing
- **Monitoring:**
-  Daily review of error rates
-  Weekly review of performance metrics
-  Monthly review with data engineering on Snowflake costs

---

## Data Flow Examples

### Example 1: Successful Enrichment

```
1. User completes course → Grade updated in LMS
2. Signal handler triggers: handle_grade_change_for_webhooks()
3. Event data prepared:
   {
     "user": {"id": 12345, "email": "learner@example.com"},
     "course": {"course_id": "course-v1:edX+DemoX+Demo"},
     "completion": {"completion_date": "2026-01-10T15:30:00Z", "percent_grade": 0.92}
   }
4. Celery task queued: enrich_and_send_completion_webhook.apply_async()
5. Worker picks up task from queue
6. Query Snowflake:
   SELECT SUM(LEARNING_TIME_SECONDS) FROM LEARNING_TIME
   WHERE USER_ID=12345 AND COURSE_KEY='course-v1:edX+DemoX+Demo'
   → Result: 18540 seconds
7. Add to payload:
   "learning_time": {"total_seconds": 18540, "total_hours": 5.15}
8. Cache result (TTL=1 hour)
9. Send webhook via route_event()
10. Integration receives enriched payload
```

### Example 2: Cache Hit (Duplicate Completion)

```
1. User re-completes course (e.g., retake with higher grade)
2. Signal handler triggers again
3. Celery task queued
4. Worker checks cache:
   Key: learning_time:12345:course-v1:edX+DemoX+Demo:abc-123
   Value: 18540 (from previous query 20 minutes ago)
5. Cache hit! Skip Snowflake query
6. Add cached value to payload
7. Send webhook (total latency: <1 second)
```

### Example 3: Snowflake Unavailable

```
1. User completes course
2. Celery task queued
3. Worker attempts Snowflake query
4. Connection fails: SnowflakeConnectionError (timeout)
5. Task retries (attempt 1 of 3) after 60 seconds
6. Connection fails again
7. Task retries (attempt 2 of 3) after 60 seconds
8. Connection fails again
9. Max retries reached (3/3)
10. Log ERROR: "Max retries reached, sending webhook without learning time"
11. Send webhook WITHOUT learning_time field
12. Integration receives standard payload (graceful degradation)
```

### Example 4: No Learning Time Data Exists

```
1. User completes brand new course (launched yesterday)
2. Celery task queued
3. Worker queries Snowflake
4. Query returns NULL (no data in warehouse yet)
5. Log WARNING: "No learning time found for user 12345, course course-v1:..."
6. Cache negative result (value: 0, TTL: 1 hour)
7. Send webhook WITHOUT learning_time field
8. Integration receives standard payload
```

---

## Success Criteria

### Functional
- ✓ Learning time field present in completion webhooks when data available
- ✓ Webhooks delivered successfully even if learning time unavailable
- ✓ Feature flag controls enrichment behavior
- ✓ Cache reduces Snowflake query load by >80%

### Performance
- ✓ Webhook delivery latency <5 seconds (p95)
- ✓ Snowflake query duration <5 seconds (p95)
- ✓ Cache hit rate >80% after 24 hours
- ✓ Celery queue depth <100 under normal load

### Operational
- ✓ No increase in webhook delivery failures
- ✓ Graceful degradation when Snowflake unavailable
- ✓ Logs and metrics provide visibility into enrichment process
- ✓ Runbook enables quick feature disable if needed

---

## Risks & Mitigation

|Risk|Impact|Likelihood|Mitigation|
|Snowflake query timeout|Delayed webhooks|Medium|Aggressive timeouts (30s), cache, retries|
|Incorrect learning time data|Integrators receive bad data|Low|Validate against sample in stage, data quality checks|
|Celery queue backlog|Webhook delays|Medium|Monitor queue depth, autoscale workers|
|Cache stampede|Snowflake overload|Low|Staggered cache expiry, circuit breaker|
|Increased Snowflake costs|Budget overrun|Low|Monitor query volume, optimize query, cache aggressively|

---

## Open Questions

# **Q: What is the exact Snowflake account ID?**
-  **A:** Pending confirmation from Data Engineering (assumed: `edx.us-east-1`)

# **Q: Does ENTERPRISE_SERVICE_USER have READ access to LEARNING_TIME table?**
-  **A:** Needs verification via `SHOW GRANTS TO USER ENTERPRISE_SERVICE_USER`

# **Q: Should we backfill learning time for historical completions?**
-  **A:** No, only new completions post-launch will include learning time

# **Q: What if multiple enterprises share the same course?**
-  **A:** Query includes `ENTERPRISE_CUSTOMER_UUID` filter for accurate attribution

---

## Appendix

### A. Snowflake Table Schema

```sql
-- PROD.BUSINESS_INTELLIGENCE.LEARNING_TIME
CREATE TABLE LEARNING_TIME (
    USER_ID INTEGER,
    COURSE_KEY VARCHAR(255),
    ENTERPRISE_CUSTOMER_UUID VARCHAR(36),
    DATE DATE,
    LEARNING_TIME_SECONDS INTEGER,
    PRIMARY KEY (USER_ID, COURSE_KEY, ENTERPRISE_CUSTOMER_UUID, DATE)
);

-- Example query
SELECT 
    USER_ID,
    COURSE_KEY,
    SUM(LEARNING_TIME_SECONDS) as TOTAL_LEARNING_TIME
FROM PROD.BUSINESS_INTELLIGENCE.LEARNING_TIME
WHERE USER_ID = 12345
  AND COURSE_KEY = 'course-v1:edX+DemoX+Demo_Course'
  AND ENTERPRISE_CUSTOMER_UUID = 'a1b2c3d4-...'
GROUP BY USER_ID, COURSE_KEY;
```

### B. Cache Key Format

```text
Key Template: learning_time:{user_id}:{course_id}:{enterprise_id}

Example: learning_time:12345:course-v1:edX+DemoX+Demo_Course:a1b2c3d4-e5f6-7890-abcd-ef1234567890

Value: Integer (seconds) or 0 (if no data)
TTL: 3600 seconds (1 hour)
```

### C. Related JIRA Tickets

- **EPIC-12345:** Add Learning Time to Webhook Payloads
- **TICKET-12346:** Implement Snowflake Client for Learning Time Queries
- **TICKET-12347:** Create Celery Task for Async Webhook Enrichment
- **TICKET-12348:** Update Webhook Payload Structure
- **TICKET-12349:** Add Feature Flag and Configuration
- **TICKET-12350:** Write Unit and Integration Tests
- **TICKET-12351:** Create DataDog Dashboard and Alerts
- **TICKET-12352:** Update Webhook Integration Guide PDF

### D. Contacts

- **Product Owner:** Jane Doe (jane.doe@openedx.org)
- **Tech Lead:** John Smith (john.smith@openedx.org)
- **Data Engineering:** Alice Johnson (alice.johnson@openedx.org)
- **DevOps:** Bob Lee (bob.lee@openedx.org)
- **Skillsoft Integration Contact:** partner-support@skillsoft.com

---

_Document Version: 1.1_  
_Last Updated: 2026-01-12_  
_Author: Enterprise Integrations Team_
