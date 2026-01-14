# Celery Queue Configuration for Webhook Learning Time Enrichment

## Overview

The webhook learning time enrichment feature uses a dedicated Celery task that requires proper queue configuration for optimal performance and resource isolation.

## Queue Configuration

### Task Information

- **Task Name**: `channel_integrations.integrated_channel.tasks.enrich_and_send_completion_webhook`
- **Queue Name**: `edx.lms.core.webhook_enrichment`
- **Purpose**: Enriches course completion webhooks with learning time data from Snowflake

### Why a Dedicated Queue?

The enrichment task is routed to a dedicated queue for several reasons:

1. **Resource Isolation**: Separates Snowflake queries from other webhook/celery tasks
2. **Performance Monitoring**: Easy to monitor queue depth and processing times
3. **Scaling**: Can scale webhook enrichment workers independently
4. **Error Handling**: Failures in enrichment don't block other webhook deliveries

## Configuration Steps

### 1. Add Queue Route in LMS Settings

Add the following to your LMS production settings (e.g., `lms/envs/production.py` or via Ansible):

```python
CELERY_TASK_ROUTES = {
    # ... existing routes ...
    
    # Webhook learning time enrichment
    'channel_integrations.integrated_channel.tasks.enrich_and_send_completion_webhook': {
        'queue': 'edx.lms.core.webhook_enrichment'
    },
}
```

### 2. Configure Celery Workers

Start dedicated workers for the webhook enrichment queue:

```bash
# Example: Start 2 worker processes for webhook enrichment
celery -A lms.celery worker \
  --loglevel=info \
  --queues=edx.lms.core.webhook_enrichment \
  --concurrency=2 \
  --hostname=webhook-enrichment@%h
```

### 3. Worker Sizing Recommendations

**Production Recommendations:**
- **Concurrency**: 2-4 workers per instance
- **Memory**: 1-2GB per worker (Snowflake connections)
- **Autoscaling**: Monitor queue depth, scale at >100 pending tasks

**Development/Staging:**
- **Concurrency**: 1-2 workers
- **Memory**: 512MB-1GB per worker

## Monitoring

### Key Metrics to Monitor

1. **Queue Depth**: Number of pending tasks in `edx.lms.core.webhook_enrichment`
2. **Task Duration**: Time to complete enrichment (target: <5s)
3. **Error Rate**: Failed enrichment attempts (should be <1%)
4. **Snowflake Query Time**: Time spent querying Snowflake (target: <3s)

### Celery Flower Dashboard

View queue status in Celery Flower:

```bash
celery -A lms.celery flower
# Access at http://localhost:5555
```

### Example DataDog Query

```
avg:celery.task.runtime{task_name:enrich_and_send_completion_webhook}
```

## Testing Queue Configuration

### 1. Verify Task Registration

```python
from celery import current_app

# List all registered tasks
tasks = current_app.tasks
enrichment_task = 'channel_integrations.integrated_channel.tasks.enrich_and_send_completion_webhook'
print(f"Task registered: {enrichment_task in tasks}")

# Check task routing
route = current_app.conf.task_routes.get(enrichment_task)
print(f"Routes to queue: {route}")
```

### 2. Test Task Execution

```python
from channel_integrations.integrated_channel.tasks import enrich_and_send_completion_webhook

# Queue a test task
result = enrich_and_send_completion_webhook.delay(
    user_id=123,
    course_id='course-v1:edX+DemoX+Demo',
    enterprise_customer_uuid='12345678-1234-1234-1234-123456789abc',
    payload_dict={'completion': {'percent_grade': 0.85}}
)

# Check task status
print(f"Task ID: {result.id}")
print(f"Task state: {result.state}")
```

### 3. Verify Queue in RabbitMQ/Redis

```bash
# For RabbitMQ
rabbitmqctl list_queues name messages consumers

# For Redis
redis-cli LLEN edx.lms.core.webhook_enrichment
```

## Troubleshooting

### Task Not Routing to Correct Queue

**Symptom**: Tasks going to default queue instead of `edx.lms.core.webhook_enrichment`

**Solution**:
1. Verify `CELERY_TASK_ROUTES` is properly configured
2. Restart Celery workers to pick up new configuration
3. Check for typos in task name (must match exactly)

### Workers Not Processing Tasks

**Symptom**: Queue depth growing, but tasks not being processed

**Solution**:
1. Verify workers are listening to the correct queue: `celery inspect active_queues`
2. Check worker logs for errors
3. Verify Snowflake connection settings are correct

### High Task Latency

**Symptom**: Tasks taking >10s to complete

**Solution**:
1. Check Snowflake query performance
2. Verify cache is working (should hit cache on repeated queries)
3. Consider increasing worker concurrency
4. Check network latency to Snowflake

## Rollback Procedure

If issues occur, disable the feature:

1. **Set feature flag to False**:
   ```python
   FEATURES['ENABLE_WEBHOOK_LEARNING_TIME_ENRICHMENT'] = False
   ```

2. **Restart application servers** (Django workers)

3. **Drain existing queue** (let pending tasks complete or purge):
   ```bash
   celery -A lms.celery purge edx.lms.core.webhook_enrichment
   ```

4. **Stop enrichment workers** (optional - can leave running):
   ```bash
   # Stop workers processing webhook_enrichment queue
   celery -A lms.celery control shutdown \
     --destination=webhook-enrichment@hostname
   ```

## Production Deployment Checklist

- [ ] `CELERY_TASK_ROUTES` configured in production settings
- [ ] Dedicated Celery workers started for `edx.lms.core.webhook_enrichment` queue
- [ ] Worker sizing appropriate for expected load
- [ ] Monitoring/alerting configured for queue depth and error rate
- [ ] Snowflake connection settings verified
- [ ] Feature flag `ENABLE_WEBHOOK_LEARNING_TIME_ENRICHMENT` set to desired state
- [ ] Rollback procedure documented and tested in staging
- [ ] On-call team briefed on new queue and monitoring

## Related Documentation

- [Feature Flag Configuration](feature_flag_configuration.md)
- [Snowflake Client Configuration](snowflake_configuration.md)
- [Webhook System Overview](../concepts/webhooks.rst)

## Support

For issues or questions:
- Slack: `#enterprise-integrations`
- JIRA: Create ticket in `ENT` project
- Email: enterprise-team@edx.org
