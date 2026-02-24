# Percipio Webhook Harness

A manual testing harness for exercising the Percipio OAuth token flow and webhook transmission system.

## Overview

This harness allows you to test the Percipio integration end-to-end with three operating modes:

1. **dry-run** (Default, Safest): Shows exactly what would be sent without making any HTTP calls
2. **stubbed**: Mocks HTTP responses to test the full flow locally without hitting real endpoints
3. **real**: Actually sends to real Percipio endpoints (use with caution)

## Initial Setup

### Database Setup

The harness requires a working database with migrations applied. The first time you run it (or if you encounter database issues):

1. **Run migrations** to create the required tables:
   ```bash
   python manage.py migrate --settings=test_settings
   ```

2. **If you need to start fresh**, delete the SQLite database and re-run migrations:
   ```bash
   rm default.db
   python manage.py migrate --settings=test_settings
   ```

3. **If migrations fail** due to dependency issues, you may need to run mock app migrations:
   ```bash
   python manage.py migrate --settings=test_settings
   ```

**Common database issues:**
- `no such table: integrated_channel_webhooktransmissionqueue` → Run migrations
- `UNIQUE constraint failed` → The harness uses `get_or_create` to allow repeated runs, but if you encounter issues, delete and recreate the database
- `relation "enterprise_enterprisecustomer" does not exist` → Make sure mock app migrations are applied

## Quick Start

### Dry-Run Mode (Recommended for Initial Testing)

The safest way to test - no network calls are made, just shows what would happen:

```bash
# Via Django shell (recommended)
python manage.py shell -c "import scripts.percipio_webhook_harness as h; h.main(['--mode=dry-run'])"

# Or as a standalone script
DJANGO_SETTINGS_MODULE=test_settings python scripts/percipio_webhook_harness.py --mode=dry-run
```

**What it does:**
- Creates realistic test data (webhook config, queue item, completion payload)
- Shows the exact payload that would be sent to Percipio
- Shows the authentication flow that would be used
- Shows the HTTP request that would be made
- **Does NOT make any actual HTTP calls**

### Stubbed Mode (Local Testing with Mocked Network)

Tests the full code path including HTTP calls, but with mocked responses:

```bash
# Set Percipio credentials (can be dummy values for stubbed mode)
export PERCIPIO_CLIENT_ID="aa"
export PERCIPIO_CLIENT_SECRET="bb"

# Basic stubbed run with default webhook URL
python manage.py shell -c "import scripts.percipio_webhook_harness as h; h.main(['--mode=stubbed'])"

# Or with a custom webhook URL
python manage.py shell -c "import scripts.percipio_webhook_harness as h; h.main(['--mode=stubbed', '--webhook-url=https://api.develop.squads-dev.com/content-aggregation/v1/partners/edx/track'])"
```

**What it does:**
- Creates test data and realistic completion payload
- Mocks the Percipio OAuth token endpoint (returns fake token)
- Mocks the webhook POST endpoint (returns success)
- Exercises the full `process_webhook_queue` code path
- Shows all captured HTTP requests and headers

### Real Mode (Live Network Testing)

⚠️ **Use with real credentials and webhook URL**

```bash
# Set real Percipio credentials
export PERCIPIO_CLIENT_ID="your-real-client-id"
export PERCIPIO_CLIENT_SECRET="your-real-client-secret"

# Test against development environment
python manage.py shell -c "import scripts.percipio_webhook_harness as h; h.main(['--mode=real', '--webhook-url=https://api.develop.squads-dev.com/content-aggregation/v1/partners/edx/track'])"

# Or use a test webhook receiver like RequestBin
python scripts/percipio_webhook_harness.py \
  --mode=real \
  --webhook-url=https://your-requestbin-url.example/webhook
```

**What it does:**
- Creates test data and realistic completion payload
- Fetches a real OAuth token from Percipio
- Sends a real HTTP POST to the specified webhook URL
- Shows the final status and any errors

## Command-Line Options

| Option | Default | Description |
|--------|---------|-------------|
| `--mode` | `dry-run` | Operation mode: `dry-run`, `stubbed`, or `real` |
| `--region` | `US` | Percipio region: `US`, `EU`, or `OTHER` |
| `--webhook-url` | `https://example.com/webhook` | Webhook endpoint URL |
| `--username` | `harness_user` | Username for the test user |
| `--event-type` | `course_completion` | Event type (e.g., `course_completion`, `course_enrollment`) |
| `--course-id` | `course-v1:TestX+Harness+2026` | Course identifier |
| `--grade` | `Pass` | Grade value (e.g., `Pass`, `85`, `A`) |
| `--completion-percentage` | `100` | Completion percentage (0-100) |
| `--payload` | (auto-generated) | Custom JSON payload (overrides generated payload) |

## Examples

### Test a Failing Student (50% complete)

```bash
python manage.py shell -c "
import scripts.percipio_webhook_harness as h
h.main(['--mode=dry-run', '--completion-percentage=50', '--grade=Incomplete'])
"
```

### Test with EU Region

```bash
python manage.py shell -c "
import scripts.percipio_webhook_harness as h
h.main(['--mode=dry-run', '--region=EU'])
"
```

### Test with Custom Payload

```bash
python scripts/percipio_webhook_harness.py --mode=dry-run \
  --payload='{"content_id":"custom-course-123","user":"john_doe","status":"completed","event_date":"2026-02-24T12:00:00","completion_percentage":100,"duration_spent":7200,"grade":"95"}'
```

### Test Different Event Types

```bash
# Enrollment event
python manage.py shell -c "
import scripts.percipio_webhook_harness as h
h.main(['--mode=dry-run', '--event-type=course_enrollment', '--completion-percentage=0', '--grade=N/A'])
"
```

## Payload Format

The harness generates Percipio-compliant payloads matching the format from `handlers.py`:

```json
{
  "content_id": "course-v1:TestX+Harness+2026",
  "user": "harness_user",
  "status": "completed",
  "event_date": "2026-02-24T10:30:00.000000",
  "completion_percentage": 100,
  "duration_spent": null,
  "grade": "Pass"
}
```

## Configuration Requirements

### For Dry-Run Mode
- No special configuration needed
- Works out of the box with test settings

### For Stubbed Mode
- `PERCIPIO_CLIENT_ID` must be set (can be dummy value like "test-id")
- `PERCIPIO_CLIENT_SECRET` must be set (can be dummy value like "test-secret")

### For Real Mode
- `PERCIPIO_CLIENT_ID` - Real Percipio OAuth client ID
- `PERCIPIO_CLIENT_SECRET` - Real Percipio OAuth client secret
- Use a safe webhook URL (RequestBin, webhook.site, etc.)

## Troubleshooting

### "PERCIPIO_CLIENT_ID and PERCIPIO_CLIENT_SECRET must be non-empty"

For stubbed mode, set dummy values:
```bash
export PERCIPIO_CLIENT_ID="test-client-id"
export PERCIPIO_CLIENT_SECRET="test-client-secret"
```

### Django not configured

Make sure to either:
1. Run via `python manage.py shell -c "..."`
2. Or set `DJANGO_SETTINGS_MODULE` environment variable

### Testing OAuth Token Caching

The OAuth tokens are cached per region. To test cache behavior:
```python
from django.core.cache import cache
cache.clear()  # Clear all cached tokens
```

## Development Workflow

1. **Start with dry-run** to verify payload structure
2. **Move to stubbed** to test the full OAuth flow with mocked responses
3. **Use real mode** only when ready to test against actual Percipio sandbox/staging

## See Also

- [SKILLSOFT_OAUTH_IMPLEMENTATION.md](../SKILLSOFT_OAUTH_IMPLEMENTATION.md) - OAuth implementation details
- [percipio_auth.py](../channel_integrations/integrated_channel/percipio_auth.py) - OAuth client implementation
- [tasks.py](../channel_integrations/integrated_channel/tasks.py) - `process_webhook_queue` implementation
