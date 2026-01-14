# Webhook Learning Time Enrichment Feature Flag

## Overview

The `ENABLE_WEBHOOK_LEARNING_TIME_ENRICHMENT` feature flag controls whether webhook payloads for course completion events are enriched with learning time data from Snowflake before being sent to integrated channels.

## Feature Flag Configuration

### Flag Name
```
ENABLE_WEBHOOK_LEARNING_TIME_ENRICHMENT
```

### Default Value
```python
False  # Feature is OFF by default
```

### Location
Configure in Django settings (e.g., `lms/envs/production.py`, `lms/envs/staging.py`):

```python
FEATURES = {
    # ... other features ...
    'ENABLE_WEBHOOK_LEARNING_TIME_ENRICHMENT': True,  # Enable learning time enrichment
}
```

## What This Feature Does

### When ENABLED (`True`)
1. **Enriches webhook payloads** with learning time data from Snowflake
2. **Adds `learning_time` field** to the `completion` object in webhook payloads:
   ```json
   {
     "completion": {
       "learning_time": 3600,  // seconds spent learning
       // ... other completion fields ...
     }
   }
   ```
3. **Uses Celery queue** `edx.lms.core.webhook_enrichment` for async processing
4. **Queries Snowflake** for historical learning time data
5. **Caches results** for 5 minutes to reduce database load

### When DISABLED (`False`)
1. **Sends webhooks immediately** without enrichment
2. **No Snowflake queries** are performed
3. **No additional fields** are added to webhook payloads
4. **Maintains backward compatibility** with existing integrations

## Rollout Strategy

### Phase 1: Development/Testing (Week 1-2)
```python
# In development.py or local settings
FEATURES = {
    'ENABLE_WEBHOOK_LEARNING_TIME_ENRICHMENT': True,
}
```

**Testing Checklist:**
- [ ] Verify Snowflake connection is configured
- [ ] Test webhook payloads include `learning_time` field
- [ ] Confirm graceful degradation when Snowflake is unavailable
- [ ] Validate cache behavior (5-minute TTL)
- [ ] Check Celery queue routing works correctly

### Phase 2: Staging Environment (Week 3)
```python
# In staging.py
FEATURES = {
    'ENABLE_WEBHOOK_LEARNING_TIME_ENRICHMENT': True,
}
```

**Validation Steps:**
1. Enable feature flag in staging
2. Monitor Celery queue `edx.lms.core.webhook_enrichment`
3. Check webhook payload samples for `learning_time` field
4. Verify integrated channel partners can process enriched payloads
5. Monitor Snowflake query performance and error rates

### Phase 3: Production Canary (Week 4)
Enable for a small percentage of traffic using Django Waffle or similar:

```python
# Using Django Waffle for gradual rollout
# In production.py
FEATURES = {
    'ENABLE_WEBHOOK_LEARNING_TIME_ENRICHMENT': True,
}

# Configure Waffle flag for 5% of users
# Via Django admin or API
```

**Canary Metrics:**
- Webhook send latency (target: <5 seconds)
- Snowflake query success rate (target: >99%)
- Error rate for webhook enrichment tasks (target: <1%)
- Cache hit rate (target: >50% after ramp-up)

### Phase 4: Full Production Rollout (Week 5+)
Gradually increase rollout percentage based on canary metrics:

- Week 5: 25% of traffic
- Week 6: 50% of traffic
- Week 7: 75% of traffic
- Week 8: 100% of traffic (full rollout)

```python
# In production.py (full rollout)
FEATURES = {
    'ENABLE_WEBHOOK_LEARNING_TIME_ENRICHMENT': True,
}
```

## Configuration Requirements

### Prerequisites
Before enabling this feature, ensure:

1. **Snowflake Connection** is configured:
   ```python
   SNOWFLAKE_CONFIG = {
       'account': 'your_account',
       'user': 'your_user',
       'password': 'your_password',
       'warehouse': 'COMPUTE_WH',
       'database': 'ANALYTICS',
       'schema': 'LEARNING_DATA',
       'role': 'ANALYTICS_READER',
   }
   ```

2. **Celery Queue** is configured (see [celery_queue_configuration.md](./celery_queue_configuration.md)):
   ```python
   CELERY_TASK_ROUTES = {
       'channel_integrations.integrated_channel.tasks.enrich_and_send_completion_webhook': {
           'queue': 'edx.lms.core.webhook_enrichment'
       },
   }
   ```

3. **Cache Backend** is available (Redis recommended):
   ```python
   CACHES = {
       'default': {
           'BACKEND': 'django_redis.cache.RedisCache',
           'LOCATION': 'redis://localhost:6379/1',
           # ... other cache settings ...
       }
   }
   ```

4. **Celery Workers** are running for the enrichment queue:
   ```bash
   celery -A lms.celery worker -Q edx.lms.core.webhook_enrichment -c 2
   ```

## Monitoring

### Key Metrics to Track

#### 1. Feature Adoption
```python
# Monitor via Django logs or metrics service
feature_enabled = waffle.flag_is_active(request, 'ENABLE_WEBHOOK_LEARNING_TIME_ENRICHMENT')
```

**Expected Value:** Increases according to rollout phase

#### 2. Webhook Enrichment Success Rate
```python
# Monitor Celery task success/failure
task.result  # Success count
task.failed  # Failure count
```

**Target:** >99% success rate

#### 3. Snowflake Query Performance
```python
# Monitor query execution time
query_duration = time.time() - start_time
```

**Target:** <2 seconds for 95th percentile

#### 4. Cache Hit Rate
```python
# Monitor cache hits vs misses
cache_hits / (cache_hits + cache_misses) * 100
```

**Target:** >50% after steady state

#### 5. Webhook Send Latency
```python
# Time from course completion to webhook sent
latency = webhook_sent_time - completion_time
```

**Target:** <5 seconds for 95th percentile

### Monitoring Queries

#### DataDog/Splunk Query Examples
```
# Webhook enrichment task failures
source:celery task:enrich_and_send_completion_webhook status:failure

# Snowflake query timeouts
source:snowflake_client status:timeout

# Cache hit rate
source:django_cache operation:get status:hit | stats count by status

# Webhook send latency
source:webhook_handler | stats avg(latency_ms) by p95
```

## Troubleshooting

### Issue 1: Webhooks Not Being Enriched
**Symptoms:** Webhook payloads missing `learning_time` field

**Diagnosis:**
1. Check feature flag is enabled:
   ```python
   from django.conf import settings
   print(settings.FEATURES.get('ENABLE_WEBHOOK_LEARNING_TIME_ENRICHMENT'))
   ```

2. Verify Celery task is being queued:
   ```bash
   celery -A lms.celery inspect active
   ```

**Resolution:**
- Enable feature flag in settings
- Restart Celery workers
- Check worker logs for errors

### Issue 2: High Snowflake Query Latency
**Symptoms:** Webhook sends taking >10 seconds

**Diagnosis:**
1. Check Snowflake query performance:
   ```python
   # Review Snowflake query plan
   EXPLAIN SELECT learning_time FROM analytics.learning_data WHERE ...
   ```

2. Monitor cache hit rate:
   ```python
   # Should be >50% for steady traffic
   cache.get_stats()
   ```

**Resolution:**
- Optimize Snowflake query (add indexes if needed)
- Increase cache TTL (from 300s to 600s)
- Scale Snowflake warehouse if needed

### Issue 3: Celery Queue Backlog
**Symptoms:** Growing queue depth, delayed webhook sends

**Diagnosis:**
1. Check queue depth:
   ```bash
   celery -A lms.celery inspect active -Q edx.lms.core.webhook_enrichment
   ```

2. Monitor worker utilization:
   ```bash
   celery -A lms.celery inspect stats
   ```

**Resolution:**
- Increase Celery worker concurrency (from 2 to 4)
- Add more worker instances
- Check for slow Snowflake queries

### Issue 4: Snowflake Connection Failures
**Symptoms:** Webhooks sent without `learning_time`, Snowflake errors in logs

**Diagnosis:**
1. Test Snowflake connection:
   ```python
   from channel_integrations.integrated_channel.snowflake_client import SnowflakeLearningTimeClient
   client = SnowflakeLearningTimeClient()
   # Will raise exception if connection fails
   ```

2. Check Snowflake credentials and network connectivity

**Resolution:**
- Verify Snowflake credentials are correct
- Check network/firewall rules allow Snowflake connections
- Review Snowflake account status
- Feature has graceful degradation: webhooks still sent without learning_time

## Rollback Procedure

### Emergency Rollback (Immediate)
If critical issues occur, disable the feature immediately:

```python
# In production.py or via Django admin
FEATURES = {
    'ENABLE_WEBHOOK_LEARNING_TIME_ENRICHMENT': False,
}
```

**Restart Django processes:**
```bash
# For Kubernetes
kubectl rollout restart deployment/lms

# For traditional deployments
supervisorctl restart lms:*
```

**Impact:** Webhooks return to original format (no `learning_time` field)

### Gradual Rollback
If issues are non-critical, gradually reduce rollout percentage:

1. Reduce from 100% → 50% → 25% → 10% → 0%
2. Monitor metrics at each step
3. Investigate and fix root cause
4. Ramp back up when issue is resolved

### Post-Rollback Steps
1. **Notify stakeholders** of rollback and reason
2. **Investigate root cause** of issues
3. **Fix identified problems** in development
4. **Re-test thoroughly** before re-enabling
5. **Document lessons learned** for future rollouts

## Testing the Feature Flag

### Manual Testing
```python
# In Django shell
from django.conf import settings
from channel_integrations.integrated_channel.tasks import enrich_and_send_completion_webhook

# Test with feature ON
settings.FEATURES['ENABLE_WEBHOOK_LEARNING_TIME_ENRICHMENT'] = True
enrich_and_send_completion_webhook(
    user_id=123,
    enterprise_customer_uuid='test-uuid',
    course_id='course-v1:edX+DemoX+Demo_Course',
    payload_dict={'completion': {'passed': True}}
)

# Check payload includes learning_time field
```

### Automated Testing
```bash
# Run feature flag tests
pytest tests/test_channel_integrations/test_integrated_channel/test_webhook_learning_time_integration.py::test_feature_flag_disabled_no_enrichment

pytest tests/test_channel_integrations/test_integrated_channel/test_webhook_learning_time_integration.py::test_enrichment_task_adds_learning_time_to_payload
```

## Integration Partner Communication

### Before Enabling Feature
1. **Notify integration partners** about upcoming payload changes
2. **Share payload schema** with new `learning_time` field
3. **Confirm partners can handle** additional field (should be ignored if not used)
4. **Document backward compatibility**: partners not expecting field will ignore it

### Sample Communication Email
```
Subject: Upcoming Enhancement to Webhook Payloads - Learning Time Data

Dear Partner,

We are planning to enhance our webhook payloads with learning time data. 
Starting [DATE], webhook completion payloads will include a new optional field:

{
  "completion": {
    "learning_time": 3600,  // seconds (new field)
    "passed": true,
    // ... existing fields ...
  }
}

This change is backward compatible. If you do not need this field, your 
integration will continue to work without modification.

If you would like to utilize learning time data, please update your 
webhook handlers to process the new field.

Please confirm receipt and let us know if you have any questions.

Best regards,
edX Integration Team
```

## Additional Resources

- [Celery Queue Configuration](./celery_queue_configuration.md)
- [Snowflake Client Documentation](../api/snowflake_client.md) *(if exists)*
- [Webhook Enrichment Architecture](../architecture/webhook_enrichment.md) *(if exists)*
- [Feature Flag Best Practices](https://docs.djangoproject.com/en/stable/topics/settings/)

## Support

For questions or issues related to this feature flag:

1. Check [Troubleshooting](#troubleshooting) section above
2. Review [Monitoring](#monitoring) metrics
3. Contact the Enterprise Integrations team
4. File a ticket in [JIRA](https://openedx.atlassian.net) *(adjust link as needed)*
