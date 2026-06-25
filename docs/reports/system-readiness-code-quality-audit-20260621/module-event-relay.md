# Module Audit: event_relay

## Verdict

Low risk and retained as a narrow event-to-Workbench relay bridge. It is not an
Operations projection owner and must not mutate owner module lifecycle state.

## Evidence

- 8 Python files, about 698 lines.
- Largest files: `application/runtime.py` (217), `application/observers.py` (187), `interfaces/worker_cli.py` (126).

## Findings

- Module size is healthy.
- It should remain a relay/observer, not a business projection owner.
- Runtime cursor behavior is now covered for first-run snapshot, replay, handler
  failure, and retry.
- Architecture guard prevents Event Relay from importing owner runtime mutators
  from Orchestration/Tool implementation layers.

## Launch Risks

- Relay failures can delay Workbench realtime updates. Current behavior preserves
  the failed event cursor for retry; broader heartbeat/dead-letter counters remain
  an Operations visibility follow-up.

## Recommendations

- Keep Event Relay as an independent daemon worker target for UI-facing realtime
  update bridging.
- Add heartbeat and dead-letter counters if Operations needs explicit relay health.
- Keep relay contracts declarative and versioned.
- Ensure Operations can report relay health.

## Detailed Pass 1

### Files Reviewed

- `application/runtime.py`
- `application/observers.py`
- `application/events.py`
- `application/ports.py`
- `interfaces/worker_cli.py`

### File-Level Assessment

`application/runtime.py` is 217 lines and `application/observers.py` is 187 lines.
The module is small and focused on watching event topics and forwarding observer
notifications.

`observers.py` imports orchestration ports and tool exceptions. This is acceptable
only if the module remains a bridge that reads owner facts and emits observation
events; it must not decide orchestration/tool lifecycle.

### Boundary Cleanliness

Event Relay should be a narrow observer bridge. It should not replace Events,
Operations observer, or owner module lifecycle logic.

### Lifecycle Clarity

Event Relay lifecycle should be:

1. configure watched topics/cursors
2. consume events
3. call narrow observer ports/read services
4. publish relay/observation result
5. handle replay and errors idempotently

### Persistence And Efficiency

No heavy persistence is visible. Cursor and replay state live in the Events
subscription cursor backend; the relay owns no separate durable truth.

### Concurrency And Multi-User Readiness

If multiple relay workers run, Events subscription cursor ownership and event
dedupe keys protect consumer progress; do not add local relay-owned persistence.

### External Integration Readiness

External systems should subscribe to owner events or Operations projections. Event
Relay should not become the integration API.

### Remediation Checklist

- [x] Decide whether Event Relay remains separate or folds into Operations observer.
- [x] If retained, document watched topics, cursor ownership, and idempotency model.
- [x] Add relay replay/error handling tests.
- [x] Add architecture guard: relay cannot mutate owner module lifecycle state.

### Decision

Retain Event Relay as a narrow bridge from owner/runtime events to Workbench
realtime update topics. It consumes selected event topics through the Events
subscription cursor API and publishes `event_relay.workbench.updated` messages.
Operations remains the durable read-model owner; Event Relay only provides live UI
refresh hints and deltas.

### Verification

- `PYTHONPATH=src pytest -q tests/unit/test_event_relay_runtime.py tests/unit/test_event_relay_cli.py tests/unit/test_module_architecture_guards.py::test_event_relay_does_not_import_owner_runtime_mutators --tb=short` -> 6 passed.
- `python -m ruff check tests/unit/test_event_relay_runtime.py tests/unit/test_module_architecture_guards.py` -> passed.
