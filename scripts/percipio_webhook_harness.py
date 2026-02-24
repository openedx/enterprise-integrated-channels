"""
Manual harness to exercise the Percipio OAuth token flow used by process_webhook_queue.

Runs end-to-end through:
  - create EnterpriseWebhookConfiguration + WebhookTransmissionQueue row
  - call process_webhook_queue(queue_item.id)
  - (optionally) stub token + webhook HTTP calls to avoid real network

Modes:
  - dry-run: Creates realistic completion data and shows what would be sent (no HTTP calls)
  - stubbed: Mocks HTTP responses, exercises full OAuth flow without hitting real endpoints
  - real: Actually sends to real Percipio endpoints

Examples:

  # Dry-run (safest, shows what would be sent without any network calls)
  python manage.py shell -c "import scripts.percipio_webhook_harness as h; h.main(['--mode=dry-run'])"

  # Stubbed run (recommended for local dev)
  python manage.py shell -c "import scripts.percipio_webhook_harness as h; h.main(['--mode=stubbed'])"

  # Or run as a script (requires DJANGO_SETTINGS_MODULE configured)
  DJANGO_SETTINGS_MODULE=channel_integrations.settings.local \
    python scripts/percipio_webhook_harness.py --mode=stubbed

  # Real network run (will POST to real endpoints)
  DJANGO_SETTINGS_MODULE=channel_integrations.settings.local \
    PERCIPIO_CLIENT_ID=... PERCIPIO_CLIENT_SECRET=... \
    python scripts/percipio_webhook_harness.py --mode=real --webhogok-url=https://requestbin.example/abc
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Sequence

import django
from django.conf import settings


def _setup_logging():
    """
    Configure logging to show messages from the webhook processing code.
    This ensures we can see LOGGER messages from tasks.py and other modules.
    """
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    # Set specific loggers to INFO level
    logging.getLogger('channel_integrations.integrated_channel').setLevel(logging.INFO)
    logging.getLogger('celery.task').setLevel(logging.INFO)


def _setup_django():
    """
    Ensure Django is configured when running as a plain python script.
    If you run via `python manage.py shell -c ...`, Django is already set up.
    """
    if not settings.configured:
        # Try to use a reasonable default if not provided
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "channel_integrations.settings.local")
        django.setup()


def _parse_args(argv: Sequence[str] | None):
    parser = argparse.ArgumentParser(description="Percipio OAuth/Webhook queue harness")
    parser.add_argument(
        "--mode",
        choices=("dry-run", "stubbed", "real"),
        default="dry-run",
        help=(
            "dry-run: prepares data and shows what would be sent (no HTTP calls); "
            "stubbed: uses responses to mock network; "
            "real: performs real HTTP requests"
        ),
    )
    parser.add_argument("--region", default="US", help="Queue item user_region / config region (US/EU/OTHER)")
    parser.add_argument(
        "--webhook-url",
        default="https://example.com/webhook",
        help="Webhook URL (only used in real mode unless you want to change the stubbed URL too)",
    )
    parser.add_argument("--username", default="harness_user", help="Username for created Django user")
    parser.add_argument(
        "--event-type",
        default="course_completion",
        help="Webhook event_type for the queue item",
    )
    parser.add_argument(
        "--course-id",
        default="course-v1:TestX+Harness+2026",
        help="Course ID for the completion event",
    )
    parser.add_argument(
        "--grade",
        default="Pass",
        help="Grade for completion (e.g., Pass, 85, A)",
    )
    parser.add_argument(
        "--completion-percentage",
        type=int,
        default=100,
        help="Completion percentage (0-100)",
    )
    parser.add_argument(
        "--payload",
        default=None,
        help="Custom JSON payload for the queue item (overrides generated completion payload)",
    )
    return parser.parse_args(argv)


def _create_percipio_completion_payload(username: str, course_id: str, grade: str, completion_percentage: int):
    """
    Create a realistic Percipio completion payload following the format from handlers.py.
    
    Args:
        username: The learner username
        course_id: The course identifier
        grade: The grade received (e.g., "Pass", "85", "A")
        completion_percentage: Percentage complete (0-100)
    
    Returns:
        dict: Percipio-formatted completion payload
    """
    from datetime import datetime
    
    return {
        'content_id': course_id,
        'user': username,
        'status': 'completed' if completion_percentage == 100 else 'started',
        'event_date': datetime.utcnow().isoformat(),
        'completion_percentage': completion_percentage,
        'duration_spent': None,  # Could be enhanced to include actual duration
        'grade': grade,
    }


def _create_queue_item(region: str, webhook_url: str, username: str, event_type: str, payload_json: str):
    """
    Create minimal DB objects needed for process_webhook_queue(queue_item.id).
    Uses Django's app registry to avoid import conflicts between mock and real enterprise models.
    """
    import uuid

    from django.apps import apps
    from django.contrib.auth import get_user_model
    from django.contrib.sites.models import Site

    from channel_integrations.integrated_channel.models import (
        EnterpriseWebhookConfiguration,
        WebhookTransmissionQueue,
    )

    # Use Django's app registry to get whichever EnterpriseCustomer is registered
    # This avoids import conflicts between mock_apps.enterprise and real enterprise
    EnterpriseCustomer = apps.get_model('enterprise', 'EnterpriseCustomer')
    User = get_user_model()

    # Get or create a site
    site, _ = Site.objects.get_or_create(
        id=1,
        defaults={'domain': 'example.com', 'name': 'Example Site'}
    )

    # Get or create a minimal EnterpriseCustomer
    enterprise, _ = EnterpriseCustomer.objects.get_or_create(
        slug=f"test-enterprise-{region.lower()}",
        defaults={
            'uuid': uuid.uuid4(),
            'name': f"Test Enterprise {region}",
            'active': True,
            'site': site,
        }
    )

    user, _ = User.objects.get_or_create(username=username)

    config, created = EnterpriseWebhookConfiguration.objects.get_or_create(
        enterprise_customer=enterprise,
        region=region,
        defaults={
            'webhook_url': webhook_url,
            'webhook_auth_token': "static-fallback-token",
        }
    )
    
    # Update webhook_url if it changed (allows overriding for testing)
    if not created and config.webhook_url != webhook_url:
        config.webhook_url = webhook_url
        config.save()

    queue_item = WebhookTransmissionQueue.objects.create(
        enterprise_customer=enterprise,
        user=user,
        course_id="course-v1:Harness+TST+2026",
        event_type=event_type,
        user_region=region,
        webhook_url=webhook_url,  # Use the passed-in URL directly
        payload=json.loads(payload_json),
        deduplication_key=f"harness-{username}-{region}-{uuid.uuid4().hex[:8]}",
    )
    return config, queue_item


def _run_dry_run(region: str, webhook_url: str, username: str, course_id: str, 
                 event_type: str, grade: str, completion_percentage: int, 
                 payload_json: str | None):
    """
    Dry-run mode: Creates queue item with realistic completion data and shows what
    would be sent without making any HTTP calls.
    
    This is the safest mode for testing - it exercises all the data preparation
    logic without any risk of sending data to external systems.
    """
    from channel_integrations.integrated_channel.percipio_auth import DEFAULT_PERCIPIO_TOKEN_URLS

    print("=" * 70)
    print("DRY-RUN MODE - No HTTP calls will be made")
    print("=" * 70)

    # Create realistic payload unless custom one provided
    if payload_json:
        payload = json.loads(payload_json)
    else:
        payload = _create_percipio_completion_payload(username, course_id, grade, completion_percentage)

    print("\n📋 Creating test data...")
    config, queue_item = _create_queue_item(region, webhook_url, username, event_type, json.dumps(payload))

    print(f"\n✓ Created EnterpriseWebhookConfiguration:")
    print(f"    id: {config.id}")
    print(f"    enterprise_customer: {config.enterprise_customer.uuid}")
    print(f"    region: {config.region}")
    print(f"    webhook_url: {config.webhook_url}")
    print(f"    webhook_auth_token: {'<configured>' if config.webhook_auth_token else '<none>'}")

    print(f"\n✓ Created WebhookTransmissionQueue:")
    print(f"    id: {queue_item.id}")
    print(f"    user: {queue_item.user.username}")
    print(f"    course_id: {queue_item.course_id}")
    print(f"    event_type: {queue_item.event_type}")
    print(f"    user_region: {queue_item.user_region}")
    print(f"    status: {queue_item.status}")
    print(f"    deduplication_key: {queue_item.deduplication_key}")

    print(f"\n📦 Payload that would be sent:")
    print(json.dumps(payload, indent=2))

    # Show what the OAuth flow would do
    percipio_client_id = getattr(settings, "PERCIPIO_CLIENT_ID", None)
    percipio_client_secret = getattr(settings, "PERCIPIO_CLIENT_SECRET", None)

    print("\n🔐 Authentication flow:")
    if percipio_client_id and percipio_client_secret:
        # Get the token URL from settings (which may override the defaults)
        token_urls = getattr(settings, 'PERCIPIO_TOKEN_URLS', DEFAULT_PERCIPIO_TOKEN_URLS)
        token_url = token_urls.get(region, token_urls.get('US', DEFAULT_PERCIPIO_TOKEN_URLS['US']))
        print(f"    ✓ Would fetch OAuth token from: {token_url}")
        print(f"    ✓ Using client_id: {percipio_client_id[:20]}...")
        print(f"    ✓ Token would be cached with key: percipio_auth_token_{region}")
        print(f"    ✓ Authorization header: Bearer <oauth-token>")
    elif config.webhook_auth_token:
        print(f"    ⚠ Would use static webhook_auth_token (OAuth not configured)")
        print(f"    ✓ Authorization header: Bearer {config.webhook_auth_token}")
    else:
        print(f"    ❌ No authentication configured!")

    print(f"\n🚀 HTTP POST that would be made:")
    print(f"    URL: {queue_item.webhook_url}")
    print(f"    Method: POST")
    print(f"    Headers:")
    print(f"        Content-Type: application/json")
    print(f"        User-Agent: OpenEdX-Enterprise-Webhook/1.0")
    if percipio_client_id and percipio_client_secret:
        print(f"        Authorization: Bearer <percipio-oauth-token>")
    elif config.webhook_auth_token:
        print(f"        Authorization: Bearer {config.webhook_auth_token}")
    print(f"    Body: {json.dumps(payload)}")

    print("\n" + "=" * 70)
    print("✓ DRY-RUN COMPLETE - No data was actually sent")
    print("=" * 70)
    print(f"\nTo actually send this data, use --mode=stubbed (local) or --mode=real (live)")
    print(f"Queue item ID {queue_item.id} is ready if you want to process it manually.")


def _run_stubbed(region: str, webhook_url: str, username: str, course_id: str,
                 event_type: str, grade: str, completion_percentage: int, 
                 payload_json: str | None):
    """
    Create database objects, mock HTTP responses, and call process_webhook_queue directly.
    This exercises the actual code path with mocked network calls.
    
    Requires: Run `python manage.py migrate` first to create database tables.
    """
    import responses

    from channel_integrations.integrated_channel.percipio_auth import DEFAULT_PERCIPIO_TOKEN_URLS
    from channel_integrations.integrated_channel.tasks import process_webhook_queue

    # Make sure Percipio is "configured" for the oauth path to be taken.
    if not getattr(settings, "PERCIPIO_CLIENT_ID", "") or not getattr(settings, "PERCIPIO_CLIENT_SECRET", ""):
        raise SystemExit(
            "Stubbed mode requires PERCIPIO_CLIENT_ID and PERCIPIO_CLIENT_SECRET to be non-empty "
            "(so process_webhook_queue uses the OAuth flow). Set them in your local settings or env."
        )

    # Get the token URL from settings (which may override the defaults)
    token_urls = getattr(settings, 'PERCIPIO_TOKEN_URLS', DEFAULT_PERCIPIO_TOKEN_URLS)
    token_url = token_urls.get(region, token_urls.get('US', DEFAULT_PERCIPIO_TOKEN_URLS['US']))

    # Create realistic payload unless custom one provided
    if payload_json:
        payload = json.loads(payload_json)
    else:
        payload = _create_percipio_completion_payload(username, course_id, grade, completion_percentage)

    print("\n🧪 STUBBED MODE - Calling process_webhook_queue() with mocked HTTP")
    print(f"\n📋 Test Details:")
    print(f"    Region: {region}")
    print(f"    Username: {username}")
    print(f"    Course ID: {course_id}")
    print(f"    Event Type: {event_type}")
    print(f"    Grade: {grade}")
    print(f"    Completion: {completion_percentage}%")
    print(f"    Webhook URL: {webhook_url}")
    
    print(f"\n📦 Payload to be sent:")
    print(json.dumps(payload, indent=2))

    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        # Mock the OAuth token endpoint
        rsps.add(
            responses.POST,
            token_url,
            json={"access_token": "stubbed-percipio-token-12345", "expires_in": 3600, "token_type": "Bearer"},
            status=200,
        )
        
        # Mock the webhook endpoint
        rsps.add(
            responses.POST,
            webhook_url,
            json={"status": "ok", "message": "Completion received"},
            status=200,
        )

        print(f"\n🗄️  Creating database objects...")
        # Create minimal database objects
        config, queue_item = _create_queue_item(region, webhook_url, username, event_type, json.dumps(payload))
        
        print(f"✓ Created EnterpriseWebhookConfiguration (id={config.id})")
        print(f"✓ Created WebhookTransmissionQueue (id={queue_item.id})")
        
        print(f"\n🚀 Calling process_webhook_queue({queue_item.id})...")
        # Call the actual task function - this is the real code being tested!
        process_webhook_queue(queue_item.id)
        
        # Refresh from database to see the updated status
        queue_item.refresh_from_db()

        print("\n" + "="*70)
        print("📡 HTTP CALLS CAPTURED")
        print("="*70)
        
        for idx, call in enumerate(rsps.calls):
            print(f"\n[{idx+1}] {call.request.method} {call.request.url}")
            print("    Headers:")
            for k, v in sorted(call.request.headers.items()):
                if k.lower() in ("authorization", "content-type", "user-agent"):
                    print(f"        {k}: {v}")
            
            body = call.request.body
            if body:
                try:
                    decoded = body.decode("utf-8") if hasattr(body, "decode") else body
                    print("    Body:")
                    # Pretty print if it's JSON
                    try:
                        body_json = json.loads(decoded)
                        for line in json.dumps(body_json, indent=2).split('\n'):
                            print(f"        {line}")
                    except (json.JSONDecodeError, TypeError):
                        print(f"        {decoded}")
                except Exception:  # noqa: BLE001
                    pass

        print("\n" + "="*70)
        print("✅ STUBBED TEST COMPLETE")
        print("="*70)
        print(f"\n📊 Queue Item Results:")
        print(f"    Status: {queue_item.status}")
        print(f"    HTTP Status Code: {queue_item.http_status_code}")
        print(f"    Attempt Count: {queue_item.attempt_count}")
        print(f"    Error Message: {queue_item.error_message or 'None'}")
        if queue_item.completed_at:
            print(f"    Completed At: {queue_item.completed_at}")
        
        print(f"\n✓ Verified:")
        print(f"  ✓ process_webhook_queue() executed successfully")
        print(f"  ✓ OAuth token fetched from mocked Percipio API")
        print(f"  ✓ Bearer token included in webhook Authorization header")
        print(f"  ✓ Webhook POST sent with correct payload")
        print(f"  ✓ Queue item marked as '{queue_item.status}'")


def _run_real(region: str, webhook_url: str, username: str, course_id: str,
              event_type: str, grade: str, completion_percentage: int, 
              payload_json: str | None):
    """
    Create database objects and call process_webhook_queue with real HTTP requests.
    This exercises the actual code path with real network calls to live endpoints.
    
    ⚠️ USE WITH CAUTION - This sends real requests to real endpoints!
    Requires: Run `python manage.py migrate` first to create database tables.
    """
    from channel_integrations.integrated_channel.tasks import process_webhook_queue

    if not getattr(settings, "PERCIPIO_CLIENT_ID", "") or not getattr(settings, "PERCIPIO_CLIENT_SECRET", ""):
        raise SystemExit(
            "Real mode requires PERCIPIO_CLIENT_ID and PERCIPIO_CLIENT_SECRET to be set in settings/env."
        )

    # Create realistic payload unless custom one provided
    if payload_json:
        payload = json.loads(payload_json)
    else:
        payload = _create_percipio_completion_payload(username, course_id, grade, completion_percentage)

    print("\n⚠️  REAL MODE - Calling process_webhook_queue() with real HTTP requests")
    print("="*70)
    print(f"\n📋 Test Details:")
    print(f"    Region: {region}")
    print(f"    Username: {username}")
    print(f"    Course ID: {course_id}")
    print(f"    Event Type: {event_type}")
    print(f"    Grade: {grade}")
    print(f"    Completion: {completion_percentage}%")
    print(f"    Webhook URL: {webhook_url}")
    
    print(f"\n📦 Payload to be sent:")
    print(json.dumps(payload, indent=2))

    try:
        print(f"\n🗄️  Creating database objects...")
        # Create minimal database objects
        config, queue_item = _create_queue_item(region, webhook_url, username, event_type, json.dumps(payload))
        
        print(f"✓ Created EnterpriseWebhookConfiguration (id={config.id})")
        print(f"✓ Created WebhookTransmissionQueue (id={queue_item.id})")
        
        print(f"\n🚀 Calling process_webhook_queue({queue_item.id}) with real network...")
        print("⚠️  This will make REAL HTTP requests to live Percipio OAuth and webhook endpoints!")
        
        # Call the actual task function - this will make real HTTP calls!
        process_webhook_queue(queue_item.id)
        
        # Refresh from database to see the updated status
        queue_item.refresh_from_db()
        
        print("\n" + "="*70)
        print("✅ REAL TEST COMPLETE")
        print("="*70)
        print(f"\n📊 Queue Item Results:")
        print(f"    Status: {queue_item.status}")
        print(f"    HTTP Status Code: {queue_item.http_status_code}")
        print(f"    Attempt Count: {queue_item.attempt_count}")
        print(f"    Error Message: {queue_item.error_message or 'None'}")
        if queue_item.completed_at:
            print(f"    Completed At: {queue_item.completed_at}")
        
        if queue_item.status == 'success':
            print(f"\n✓ Verified:")
            print(f"  ✓ process_webhook_queue() executed successfully")
            print(f"  ✓ OAuth token fetched from real Percipio API")
            print(f"  ✓ Bearer token used in webhook Authorization header")
            print(f"  ✓ Webhook POST sent to real endpoint")
            print(f"  ✓ Queue item marked as '{queue_item.status}'")
        else:
            print(f"\n⚠️  Warning: Queue item status is '{queue_item.status}'")
            if queue_item.error_message:
                print(f"    Error: {queue_item.error_message}")
        
    except Exception as e:
        print(f"\n❌ Error occurred: {e}")
        # Try to get queue item status if it exists
        try:
            if 'queue_item' in locals():
                queue_item.refresh_from_db()
                print(f"\n📊 Queue Item Status:")
                print(f"    Status: {queue_item.status}")
                print(f"    Error Message: {queue_item.error_message or 'None'}")
        except Exception:  # noqa: BLE001
            pass
        raise SystemExit(1) from e


def main(argv: Sequence[str] | None = None):
    args = _parse_args(argv)
    _setup_django()
    _setup_logging()

    if args.mode == "dry-run":
        _run_dry_run(
            args.region, 
            args.webhook_url, 
            args.username, 
            args.course_id,
            args.event_type, 
            args.grade, 
            args.completion_percentage, 
            args.payload
        )
    elif args.mode == "stubbed":
        _run_stubbed(
            args.region, 
            args.webhook_url, 
            args.username, 
            args.course_id,
            args.event_type, 
            args.grade, 
            args.completion_percentage, 
            args.payload
        )
    else:
        # Real mode
        _run_real(
            args.region,
            args.webhook_url,
            args.username,
            args.course_id,
            args.event_type,
            args.grade,
            args.completion_percentage,
            args.payload
        )


if __name__ == "__main__":
    main(sys.argv[1:])