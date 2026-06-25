# Module Audit: dispatch

## Verdict

Medium importance, medium risk. Dispatch is relatively compact but concurrency-critical.

## Evidence

- 22 Python files, about 2656 lines.
- Large files include `interfaces/http.py` (402), `domain/entities.py` (400), `interfaces/cli.py` (345), `application/services.py` (301), `infrastructure/in_memory_repository.py` (164).

## Findings

- Dispatch task ownership is appropriate for durable work queue semantics.
- The module is small enough to reason about, but queue/claim/lease behavior must be tested under concurrency.
- In-memory repository should not be production fallback.
- SQL claim now uses a single atomic candidate-update path rather than a separate
  select-then-update race window; concurrent worker tests cover duplicate-claim
  prevention.
- Terminal transitions are now stable: repeated same terminal operation is
  idempotent, while completed/failed/cancelled tasks cannot be overwritten by a
  different terminal state.

## Launch Risks

- Duplicate claims or stuck tasks would impact all long-running services.
- HTTP/CLI operations can become unsafe if they bypass claim invariants.

## Recommendations

- Add concurrent claim/lease expiration/idempotency tests.
- Enforce persistent repository for production runtime.
- Keep orchestration lane safety independent from worker-only behavior.

## Detailed Pass 1

### Files Reviewed

- `application/services.py`
- `application/worker.py`
- `application/observers/wakeup.py`
- `application/event_contracts.py`
- `domain/entities.py`
- `domain/value_objects.py`
- `infrastructure/persistence/repositories.py`
- `infrastructure/in_memory_repository.py`
- `interfaces/http.py`
- `interfaces/cli.py`
- `interfaces/dto.py`

### File-Level Assessment

`application/services.py` is 301 lines and cleanly expresses create/enqueue/wait,
heartbeat, requeue, complete, cancel, fail, and recover abandoned task inputs. This
is appropriately compact for a queue application service.

`domain/entities.py` is 400 lines and contains the task state machine. That is an
acceptable place for claim/lease/status invariants, but it needs concurrency tests
against persistence.

`interfaces/http.py` and `interfaces/cli.py` are moderate. They should remain admin
surfaces and not bypass application service state transitions.

### Boundary Cleanliness

Dispatch owns durable work queue facts and wakeup signaling. It should not own
orchestration lane policy or business run state. Orchestration can use dispatch, but
its lane safety must not rely only on worker behavior.

### Lifecycle Clarity

Dispatch lifecycle should be:

1. task created/enqueued
2. worker claims task under lease
3. worker heartbeats
4. task completes/fails/cancels/requeues
5. abandoned tasks are recovered
6. wakeup events notify consumers

This lifecycle is clear and compact.

### Persistence And Efficiency

SQL persistence is the only runtime repository path. The unused
`InMemoryDispatchTaskRepository` implementation has been retired instead of guarded
behind another configuration branch.

### Concurrency And Multi-User Readiness

The key risk is duplicate claim or stale lease recovery. SQL repository tests now
simulate multiple workers claiming the same queued pool concurrently, and lifecycle
tests cover heartbeat plus lease expiry recovery. Terminal transition tests now cover
idempotent same-state completion and rejection of terminal overwrites. Remaining
hardening should focus on production repository guards.
An architecture guard now asserts the retired in-memory repository does not
reappear in Dispatch infrastructure exports.
HTTP/CLI interfaces are also guarded against direct repository access or entity
state mutation; they must go through `DispatchApplicationService`.

### Remediation Checklist

- [x] Add concurrent claim tests against SQL repository.
- [x] Add lease expiry/recover abandoned task tests.
- [x] Add idempotent complete/fail/cancel tests.
- [x] Retire production-mode in-memory repository path for shared runtime.
- [x] Ensure HTTP/CLI use application service state transitions only.

### Remediation Verification

Commands passed after the SQL concurrent claim fix:

```bash
PYTHONPATH=src pytest -q tests/unit/test_dispatch.py::DispatchTestCase::test_sql_repository_concurrent_claims_do_not_duplicate_tasks --tb=short
PYTHONPATH=src pytest -q tests/unit/test_dispatch.py tests/unit/test_dispatch_cli.py tests/unit/test_dispatch_http.py --tb=short
python -m ruff check src/crxzipple/modules/dispatch/domain/entities.py src/crxzipple/modules/dispatch/infrastructure/persistence/repositories.py tests/unit/test_dispatch.py
PYTHONPATH=src pytest -q tests/unit/test_module_architecture_guards.py::test_dispatch_runtime_has_no_in_memory_repository_backdoor tests/unit/test_module_architecture_guards.py::test_dispatch_interfaces_do_not_bypass_application_service tests/unit/test_dispatch.py tests/unit/test_dispatch_cli.py tests/unit/test_dispatch_http.py --tb=short
python -m ruff check src/crxzipple/modules/dispatch/infrastructure/__init__.py tests/unit/test_module_architecture_guards.py
```

Result:

- Focused concurrent claim regression: 1 passed
- Dispatch unit / CLI / HTTP suite: 11 passed
- Targeted ruff over changed Dispatch files: passed
- Dispatch architecture guards plus Dispatch suite: 13 passed
- Targeted ruff over Dispatch infrastructure export and architecture guard: passed
