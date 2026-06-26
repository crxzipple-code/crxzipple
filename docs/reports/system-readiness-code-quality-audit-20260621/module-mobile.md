# Module Audit: mobile

## Verdict

Low-medium risk. Mobile is capability-runtime oriented and relatively self-contained. Engine helpers are now split, though ADB/device integration remains inherently infrastructure-heavy.

## Evidence

- 24 Python files, about 4081 lines.
- Large files include `infrastructure/engines.py` (686), `infrastructure/adb_client.py` (690), `application/services.py` (338), `infrastructure/vision_layout.py` (285), `infrastructure/snapshot_builders.py` (268), and `infrastructure/adb_engine_helpers.py` (177).

## Findings

- Capability runtime boundary is appropriate.
- Engine/ADB details belong in infrastructure.
- Application service is modest. ADB action/control helpers are now split out of the engine entrypoint.
- Device execution now has a formal file-backed lease store wired through the
  coordinator, so simultaneous owners cannot drive the same device state path.
- ADB subprocess failures now report bounded diagnostics instead of propagating
  unbounded stdout/stderr into runtime events or UI payloads.

## Launch Risks

- Device/host adapter reliability and cleanup can affect long-running sessions.
- External device access needs strong isolation and observability.

## Recommendations

- Split engine responsibilities if adding gestures, screen parsing, app lifecycle, or device pool behavior.
- Keep device lease/cleanup and ADB subprocess error behavior covered by tests.
- Keep mobile capability exposed through Tool/Context surfaces, not direct orchestration logic.

## Detailed Pass 1

### Files Reviewed

- `application/services.py`
- `application/ports.py`
- `domain/entities.py`
- `domain/value_objects.py`
- `infrastructure/engines.py`
- `infrastructure/adb_client.py`
- `infrastructure/vision_layout.py`
- `infrastructure/stores.py`
- `interfaces/http.py`
- `interfaces/cli.py`

### File-Level Assessment

`infrastructure/engines.py` is now 686 lines and owns mobile action/control execution
flow. UI XML selector/node resolution moved to `infrastructure/ui_node_resolution.py`;
UI-tree/OCR/vision snapshot construction moved to `infrastructure/snapshot_builders.py`;
ADB action/control helper policy moved to `infrastructure/adb_engine_helpers.py`.
Artifact capture remains in the action engine because it is part of command execution,
but result payloads stay ref/metadata-backed rather than inline image bytes.

`infrastructure/adb_client.py` is 690 lines and uses subprocess-backed ADB operations.
It is correctly in infrastructure. Timeout handling exists at the subprocess call
site; large command/probe failure output is now truncated before entering
`MobileExecutionError` or probe diagnostics.

`application/services.py` is only 320 lines and properly focuses on capability
resolution, command assembly, planning, and execution coordination.

### Boundary Cleanliness

Mobile owns mobile capability runtime, device/profile state, ADB adapter, vision/OCR
layout integration, and action refs. It should not own task strategy or orchestration
run state.

### Lifecycle Clarity

Mobile lifecycle should be:

1. device/profile is resolved
2. command/action is assembled
3. execution planner selects engine
4. ADB/engine executes bounded action
5. screenshot/OCR/artifact refs are recorded if needed
6. device state/refs are persisted or cleaned up

### Persistence And Efficiency

Mobile stores local runtime refs/state and may create artifacts/screenshots. Retention
and size budgets are needed if long runs use screenshots heavily.

### Concurrency And Multi-User Readiness

Device access is now leased by `MobileExecutionCoordinatorService` before
device-bound control/action engine execution. Current lease persistence is
file-backed under the Mobile state root and guarded with file locks. ADB command
failures now have bounded output diagnostics; external-device cleanup still depends
on the engine/action paths.

### External Integration Readiness

Mobile should be exposed through stable tools/capability actions, not raw ADB access.

### Remediation Checklist

- [x] Split `infrastructure/engines.py` by control execution, action execution, screenshot/artifact capture, OCR/layout interpretation, and reference storage.
- [x] Add ADB timeout/error/output truncation tests.
- [x] Add device lease/isolation tests.
- [x] Add screenshot/artifact retention budget tests.
- [x] Keep app/task-specific mobile flows in skills/tools, not Mobile core.

### Verification

- `PYTHONPATH=src pytest -q tests/unit/test_mobile_device_leases.py --tb=short` -> 3 passed.
- `PYTHONPATH=src pytest -q tests/unit/test_mobile_domain.py tests/unit/test_mobile_device_leases.py tests/unit/test_mobile_cli.py tests/unit/test_mobile_http.py tests/unit/test_mobile_tool_http.py --tb=short` -> 49 passed.
- `python -m ruff check src/crxzipple/modules/mobile/infrastructure/adb_client.py tests/unit/test_mobile_domain.py` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_module_architecture_guards.py::test_mobile_core_has_no_app_or_task_specific_flow_logic --tb=short` -> 1 passed.
- `python -m ruff check tests/unit/test_module_architecture_guards.py --ignore F401,I001,E501` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_mobile_domain.py tests/unit/test_mobile_device_leases.py tests/unit/test_mobile_cli.py tests/unit/test_mobile_http.py tests/unit/test_mobile_tool_http.py tests/unit/test_module_architecture_guards.py::test_mobile_core_has_no_app_or_task_specific_flow_logic --tb=short` -> 52 passed.
- `python -m ruff check src/crxzipple/modules/mobile/infrastructure/engines.py src/crxzipple/modules/mobile/infrastructure/adb_engine_helpers.py tests/unit/test_mobile_domain.py tests/unit/test_mobile_device_leases.py tests/unit/test_module_architecture_guards.py` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_mobile_domain.py tests/unit/test_mobile_device_leases.py tests/unit/test_mobile_cli.py tests/unit/test_mobile_http.py tests/unit/test_mobile_tool_http.py tests/unit/test_module_architecture_guards.py::test_mobile_core_has_no_app_or_task_specific_flow_logic --tb=short --maxfail=1` -> 52 passed.

### Notes From Current Remediation

- Snapshot refs now have explicit budget coverage: a new snapshot generation prunes
  the previous generation's refs, so stale refs cannot accumulate indefinitely.
- Screenshot results now have artifact-ref coverage: the action result returns
  `artifact_id`/mime/name/dimensions and does not inline image bytes.
