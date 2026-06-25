# Module Audit: daemon

## Verdict

Low-medium risk. Daemon owns service specs, instances, leases, and process supervision. It is compact and aligned with the current runtime contract.

## Evidence

- 17 Python files, about 3324 lines.
- Large files include `interfaces/cli.py` (736), `application/manager.py` (671), `application/services.py` (649), `infrastructure/stores.py` (327).

## Findings

- Daemon correctly owns long-running service management rather than business state.
- CLI is large but acceptable for operational control; should not gain business decisions.
- Store behavior should be explicit for production vs local.
- Existing daemon service/manager/CLI/HTTP tests now provide lifecycle smoke coverage
  for ensure/start/status, healthcheck, stop/down, reconcile/recover, service sets,
  and lease behavior.
- Lease contention is covered by atomic store-update, cross-owner blocking, and
  same-owner reentrant lease-depth tests.
- Endpoint healthcheck failure mapping is covered for process-backed services:
  probe errors mark the instance degraded and preserve the endpoint.

## Launch Risks

- Mismanaged daemon state can make worker/browser/observer availability misleading.
- Multi-user deployment needs clear process isolation and service health reporting.

## Recommendations

- Add daemon service lifecycle smoke tests for start/ensure/status/stop/recover.
- Keep business module state out of daemon metadata.
- Surface health through Operations projection, not direct frontend polling of daemon internals.

## Detailed Pass 1

### Files Reviewed

- `application/services.py`
- `application/manager.py`
- `application/ports.py`
- `domain/entities.py`
- `domain/value_objects.py`
- `infrastructure/stores.py`
- `infrastructure/state_root.py`
- `infrastructure/state_migrations.py`
- `interfaces/cli.py`
- `interfaces/http.py`
- `interfaces/presenters.py`

### File-Level Assessment

`application/manager.py` is 671 lines and coordinates daemon service specs, process
interaction, HTTP health checks, and manager-level operations. It imports Process and
uses HTTP requests for health checks, which is appropriate for a supervisor manager
but should stay bounded to runtime availability.

`application/services.py` is 649 lines and owns daemon service specs, instances,
leases, and lease event logs. It is compact enough for now but central to long-running
runtime correctness.

`interfaces/cli.py` is 736 lines. A large operational CLI is acceptable, but it must
not gain business-module decisions.

### Boundary Cleanliness

Daemon owns long-running service definitions, instances, leases, and process
supervision. It should not own worker/tool/browser/orchestration business facts.

### Lifecycle Clarity

Daemon lifecycle should be:

1. service spec is registered
2. daemon ensure/start creates process/session
3. instance and lease are recorded
4. health/status is checked
5. recovery restarts or marks unhealthy
6. stop/release cleans up process and lease

This lifecycle is present and reasonably contained.

### Persistence And Efficiency

State root/file store is acceptable for local daemon management. Shared/multi-user
deployment must clarify whether daemon state is per host, per workspace, or global.

### Concurrency And Multi-User Readiness

Daemon needs host-level isolation and lease correctness. Multiple agents/users should
not fight over the same host service unless explicitly configured.

### External Integration Readiness

External systems should read service health through Operations projections or a narrow
daemon status API. They should not inspect daemon store files.

### Remediation Checklist

- [x] Add start/ensure/status/stop/recover smoke tests.
- [x] Add lease contention tests for repeated ensure/start calls.
- [x] Add health-check timeout/error mapping tests.
- [x] Document daemon state scope: host/workspace/user/global.
- [x] Ensure Operations health projection is the preferred UI source.

### Remediation Verification

Command passed for daemon lifecycle smoke coverage:

```bash
PYTHONPATH=src pytest -q tests/unit/test_daemon_service.py tests/unit/test_daemon_manager.py tests/unit/test_daemon_cli.py tests/unit/test_daemon_http.py --tb=short
python -m ruff check tests/unit/test_daemon_service.py tests/unit/test_daemon_manager.py
PYTHONPATH=src pytest -q tests/unit/test_daemon_manager.py::DaemonManagerTestCase::test_healthcheck_service_marks_process_backed_endpoint_degraded_on_probe_error tests/unit/test_daemon_service.py::DaemonServiceTestCase::test_acquire_lease_blocks_other_owner_until_released tests/unit/test_daemon_service.py::DaemonServiceTestCase::test_same_owner_reentrant_lease_requires_matching_release_count --tb=short
PYTHONPATH=src pytest -q tests/unit/test_module_architecture_guards.py::test_operations_frontend_uses_operations_daemon_projection_not_daemon_owner_api tests/unit/test_ui_operations_http.py::UiOperationsHttpTestCase::test_ui_operations_daemon_overview_reads_projection_without_runtime_refresh tests/unit/test_operations_daemon_read_model.py::OperationsDaemonReadModelTestCase::test_browser_host_instances_expose_runtime_semantics --tb=short
```

Result:

- Daemon service / manager / CLI / HTTP suite: 74 passed
- Targeted ruff over daemon service/manager tests: passed
- Focused lease contention and healthcheck failure mapping regressions: 3 passed
- Daemon state scope / Operations projection preference regressions: 3 passed
