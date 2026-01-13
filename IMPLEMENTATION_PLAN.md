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

### Status as of 2026-01-13: Steps 1-9 Complete, Paused at Step 10

**Completed:**
- ✅ Steps 1-3: Dependencies, Configuration, Snowflake Client stub
- ✅ Steps 4-6: Full Snowflake Client implementation, Celery Task, Event Handler
- ✅ Steps 7-8: Payload structure updates, enrichment wired up
- ✅ Step 9: Unit tests - 15/15 passing, 94% coverage on snowflake_client.py

**Current State:**
- All existing webhook tests passing (15/15 handler tests)
- Feature flag: ENABLE_WEBHOOK_LEARNING_TIME_ENRICHMENT (disabled by default)
- Backward compatible - no breaking changes
- Graceful degradation implemented

**Next Steps (when resuming):**
- Step 10: Integration tests (end-to-end flow)
- Step 11: Celery queue configuration
- Steps 12-13: Documentation and final verification

**Files Modified:**
- `requirements/test.in` - Added snowflake-connector-python
- `test_settings.py` - Added Snowflake config and feature flag
- `channel_integrations/integrated_channel/snowflake_client.py` - NEW
- `channel_integrations/integrated_channel/tasks.py` - Added enrichment task
- `channel_integrations/integrated_channel/handlers.py` - Updated event handler
- `tests/test_channel_integrations/test_integrated_channel/test_snowflake_client.py` - NEW

**Test Results:**
- Snowflake client tests: 15/15 passing, 94% coverage
- Webhook handler tests: 15/15 passing (no regressions)
