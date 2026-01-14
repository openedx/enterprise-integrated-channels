# Implementation Plan: Add Learning Time to Webhook Payloads

## Overview
This plan breaks down the technical specification into incremental, testable steps. Each step ensures existing tests pass before proceeding.

---

## Phase 1: Foundation & Dependencies (Steps 1-3)

### ✅ Step 1: Add Dependencies
- Add `snowflake-connector-python==3.7.0` to requirements
- Run: `pip-compile requirements/test.in`
- Verify: No import errors

### ✅ Step 2: Add Configuration Settings
- Add Snowflake configuration to `test_settings.py`
- Add feature flag constants
- Add cache configuration constants
- Verify: Settings load without errors

### ✅ Step 3: Create Snowflake Client (No-Op)
- Create `snowflake_client.py` with stub implementation
- Return `None` for learning time (graceful degradation)
- Add comprehensive docstrings
- Verify: Module imports successfully

---

## Phase 2: Core Implementation (Steps 4-6)

### ✅ Step 4: Implement Snowflake Client
- Implement connection management (context manager)
- Implement `get_learning_time()` with caching
- Add error handling and logging
- **No database calls yet** - client created but not invoked
- Verify: Unit tests for client in isolation

### ✅ Step 5: Add Celery Task for Enrichment
- Create `enrich_and_send_completion_webhook` task
- Check feature flag (disabled by default)
- Call Snowflake client (which returns None)
- Fall back to standard webhook routing
- Verify: Task registration works, existing webhook flow unchanged

### ✅ Step 6: Update Event Handler (Feature Flag OFF)
- Modify `handle_grade_change_for_webhooks()` to call new task
- Keep feature flag OFF by default
- Ensure backward compatibility
- Verify: All existing webhook tests pass

---

## Phase 3: Payload Enhancement (Steps 7-8)

### ✅ Step 7: Update Payload Structure
- Modify `_prepare_completion_payload()` to accept optional `learning_time`
- Add `learning_time` dict to payload if provided
- Keep enrollment payloads unchanged
- Verify: Payload tests pass with and without learning_time

### ✅ Step 8: Wire Up Enrichment Task
- Connect Snowflake client call in task
- Add learning_time to payload if available
- Handle None gracefully (no learning_time in payload)
- Verify: End-to-end flow with learning_time=None

---

## Phase 4: Testing & Validation (Steps 9-11)

### ✅ Step 9: Add Unit Tests
- Test Snowflake client (cache hit, cache miss, no data, error)
- Test Celery task (feature flag on/off, with/without data)
- Test payload structure (with/without learning_time)
- Verify: New tests pass, coverage >90%

### ✅ Step 10: Add Integration Tests
- Test end-to-end flow (event → enrichment → webhook)
- Test graceful degradation (Snowflake unavailable)
- Test cache behavior
- Verify: Integration tests pass

### ✅ Step 11: Add Celery Queue Configuration
- Add queue route for `enrich_and_send_completion_webhook`
- Update Celery configuration in settings
- Verify: Task routes to correct queue

---

## Phase 5: Deployment Preparation (Steps 12-13)

### ✅ Step 12: Add Feature Flag Documentation
- Document feature flag: `ENABLE_WEBHOOK_LEARNING_TIME_ENRICHMENT`
- Add configuration examples
- Add rollout strategy notes
- Verify: Documentation is clear and accurate

### ✅ Step 13: Final Verification
- Run full test suite
- Verify no existing tests broken
- Verify new functionality works with feature flag ON
- Verify graceful degradation with feature flag OFF
- Verify performance (Snowflake queries <5s, cache <10ms)

---

## Rollback Strategy
At any step, if tests fail:
1. Revert changes for that step
2. Investigate failures
3. Fix and retry
4. Do not proceed to next step until all tests pass

## Success Criteria
- ✅ All existing tests pass
- ✅ New tests added for all new functionality
- ✅ Feature flag OFF by default (backward compatible)
- ✅ Graceful degradation if Snowflake unavailable
- ✅ No breaking changes to existing webhook flow
- ✅ Code coverage maintained or improved

---

## Execution Log

### 🎉 Status as of 2026-01-14: IMPLEMENTATION COMPLETE - All 13 Steps Done

**Phase 1 (Steps 1-3): Foundation & Dependencies** ✅
- Step 1: Dependencies - Added snowflake-connector-python==3.7.0
- Step 2: Configuration - Added Snowflake config and feature flag to test_settings.py
- Step 3: Snowflake Client stub - Created with graceful degradation

**Phase 2 (Steps 4-6): Core Implementation** ✅
- Step 4: Snowflake Client - Full implementation with caching and error handling
- Step 5: Celery Task - enrich_and_send_completion_webhook with feature flag
- Step 6: Event Handler - Updated to call enrichment task

**Phase 3 (Steps 7-8): Payload Enhancement** ✅
- Step 7: Payload Structure - learning_time added to completion dict
- Step 8: Enrichment Wired - Task calls Snowflake client and adds learning_time

**Phase 4 (Steps 9-11): Testing & Validation** ✅
- Step 9: Unit Tests - 30 tests (15 Snowflake + 15 webhook handler)
- Step 10: Integration Tests - 5 end-to-end tests
- Step 11: Celery Queue - Configuration verified, 4 routing tests added

**Phase 5 (Steps 12-13): Deployment Preparation** ✅
- Step 12: Feature Flag Documentation - Comprehensive guide created
- Step 13: Final Verification - All 39 tests passing

**Final Test Status:**
- Snowflake client: 15/15 passing (94% coverage)
- Webhook handlers: 15/15 passing (96% coverage)
- Integration tests: 5/5 passing
- Celery routing: 4/4 passing
- **Total: 39/39 tests passing** ✅
- Test execution time: 4.51s
- Feature flag: ENABLE_WEBHOOK_LEARNING_TIME_ENRICHMENT (disabled by default)
- Backward compatible - no breaking changes
- Graceful degradation verified

**Files Created:**
- `channel_integrations/integrated_channel/snowflake_client.py` (172 lines) - NEW
- `tests/test_channel_integrations/test_integrated_channel/test_snowflake_client.py` (371 lines) - NEW
- `tests/test_channel_integrations/test_integrated_channel/test_webhook_learning_time_integration.py` (289 lines) - NEW
- `tests/test_channel_integrations/test_integrated_channel/test_celery_routing.py` (130 lines) - NEW
- `docs/how-tos/celery_queue_configuration.md` (270 lines) - NEW
- `docs/how-tos/webhook_learning_time_feature_flag.md` (430+ lines) - NEW

**Files Modified:**
- `requirements/test.in` - Added snowflake-connector-python
- `test_settings.py` - Added Snowflake config, feature flag, Celery queue routing
- `channel_integrations/integrated_channel/tasks.py` - Added enrichment task (83 lines)
- `channel_integrations/integrated_channel/handlers.py` - Updated event handler (46 lines)

**Test Coverage by Component:**
1. ✅ Snowflake client unit tests (cache, connection, errors, edge cases)
2. ✅ Webhook handler tests (payload structure, logging, error handling)
3. ✅ Integration tests (end-to-end flow, graceful degradation, feature flag)
4. ✅ Celery routing tests (queue configuration, task registration)

**Documentation Complete:**
1. ✅ Celery queue configuration guide for operations team
2. ✅ Feature flag documentation with rollout strategy
3. ✅ Monitoring and troubleshooting guidance
4. ✅ Rollback procedures documented

**Ready for:**
- Code review
- Deployment to staging
- Gradual feature flag rollout in production

