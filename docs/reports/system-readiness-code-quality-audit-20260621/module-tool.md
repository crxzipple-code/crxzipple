# Module Audit: tool

## Verdict

High importance, medium-high risk after the current split wave. Tool owns catalog, source packages, execution, worker lifecycle, runtime targets, and artifacts. Worker execution, source command/query, CLI source runtime, result/artifact handling, source package helper seams, persistence repositories, HTTP route shaping, and domain entity grouping are now much cleaner, but OpenAPI/MCP runtime code and worker execution remain substantial.

## Evidence

- 133 Python files, about 27666 lines.
- Cross-module import signal: very high.
- Large files include `infrastructure/discovery/openapi.py` (814), `infrastructure/mcp_client.py` (767), `infrastructure/runtimes/openapi_remote.py` (761), `domain/runtime_entities.py` (720), `application/worker_service.py` (624), `infrastructure/cli_source_config.py` (620), `infrastructure/provider_catalog.py` (608), and `infrastructure/tool_packages.py` (589). `domain/entities.py` is now a 61-line public domain export surface after catalog/runtime entity split. `application/catalog_models.py` is now a 37-line application export surface after catalog type/helper/function/source model split. `interfaces/http.py` is now 494 lines after splitting Pydantic models and payload projection into focused HTTP helper modules. `app/assembly/tool.py` is now a 536-line composition surface after service-graph adapters moved to `app/assembly/tool_service_graph.py`.

## Findings

- Tool ownership boundary is mostly correct: tool runs and catalog belong here; orchestration only coordinates.
- Source/package discovery, runtime worker execution, catalog models, persistence repositories, domain entity groups, and HTTP DTO/payload projection have been split into focused helpers; several provider/runtime adapters remain large.
- Worker service complexity is lower after execution/runtime/artifact/error/helper extraction, but worker concurrency and backpressure remain launch-critical.
- Worker assignment selection now resolves candidate tool/function metadata inside the
  same UoW that loaded assignments and runs, avoiding a closed-UoW lookup during
  capacity/backpressure decisions.
- Tool package/source adapters are the main external integration surface; they need stable contracts and clear failure modes.

## Launch Risks

- Tool worker bottlenecks or hidden sync IO can affect every long-chain run.
- Mixed source types can produce adapter-specific redundancy if package/source contracts are unclear.
- HTTP surface is cleaner after DTO/payload split, but large external source/provider contracts can still expose owner internals if package/runtime adapters drift.

## Recommendations

- Continue splitting OpenAPI/MCP runtime adapters and worker execution paths into smaller units.
- Add worker concurrency/backpressure tests and per-tool execution metrics.
- Keep task-specific behavior out of Tool core; specialized browser/flight logic belongs in skill/tool packages.
- Define stable external tool package authoring contract and versioning.

## Detailed Pass 1

### Files Reviewed

- `application/worker_service.py`
- `application/source_service.py`
- `application/catalog_models.py`
- `application/scheduler_service.py`
- `application/submission_service.py`
- `infrastructure/cli_source.py`
- `infrastructure/tool_packages.py`
- `infrastructure/mcp_client.py`
- `infrastructure/persistence/repositories.py`
- `interfaces/http.py`
- `domain/entities.py`

### File-Level Assessment

`application/worker_service.py` was 1713 lines and is now 624 lines after moving
artifact externalization, result validation, runtime execution, error normalization,
background tracking, capability payloads, execution context decoration, completion and
failure application, recovered dispatch handling, registration/stale/prune helpers,
assignment selection, wakeup waiting, processing heartbeat threading, worker run-loop
control, run catalog/function resolution, ToolRun persistence transitions, and
run/assignment/worker/dispatch heartbeat persistence into focused application
helpers. It remains a real execution hot path and should keep gaining
concurrency/backpressure tests.

`application/source_service.py` was 1667 lines and is now 188 lines after moving source
runtime bundle construction, credential/runtime requirement parsing, entity/record
mapping, merge/change state, event payloads, validation, command DTOs, UoW protocol,
function commands, and source commands/sync use cases into focused application helpers.
It now acts as source query facade.

`infrastructure/cli_source.py` was 2102 lines and is now 61 lines after splitting CLI
source config parsing, config values, discovery/spec construction, runtime execution,
process-output observation, credential injection, envelopes, redaction, and path
validation into focused infrastructure helpers.

`infrastructure/tool_packages.py` is now 589 lines after package helper extraction.
It remains an external integration facade, but the largest current hotspots are
`application/worker_service.py` and provider/runtime adapters.

`application/catalog_models.py` was 943 lines and is now a 37-line application
export surface. Catalog enums/requirement types live in `catalog_model_types.py`,
stable payload/hash/schema helpers live in `catalog_model_helpers.py`, function
candidate/backend/function record models live in `catalog_function_models.py`, and
source/discovery records live in `catalog_source_models.py`.

`domain/entities.py` was 1147 lines and is now a 61-line domain export surface.
Catalog/source/function/provider/tool definition aggregates live in
`domain/catalog_entities.py`; runtime run/assignment/worker aggregates live in
`domain/runtime_entities.py`; common field normalization lives in
`domain/entity_normalization.py`.

`interfaces/http.py` was 1106 lines and is now 494 lines after moving FastAPI/Pydantic
request/response models to `interfaces/http_models.py` and HTTP payload/request
projection helpers to `interfaces/http_payloads.py`. The route file now owns route
parsing, authorization handoff, service lookup, and HTTP exception mapping only.

### Boundary Cleanliness

Tool owner boundary is mostly clean:

- Tool owns catalog and tool run facts.
- Orchestration creates ToolRun intent/requests but does not own ToolRun lifecycle.
- Context Workspace/tool surface consumes tool schema projections, not raw internal stores.

Risk pattern:

- Tool package/source and runtime execution can leak provider-specific or task-specific assumptions.
- Artifact externalization currently sits in worker service; that should remain generic and not become task evidence logic.

### Lifecycle Clarity

The tool lifecycle includes catalog source ingestion, function enablement, runtime request surface, run submission, worker execution, result normalization, artifact externalization, and event/projection publication.

The lifecycle is reasonable, but files are too large around:

- runtime entity lifecycle remains substantial in `domain/runtime_entities.py`
- catalog record composition is now split; keep it from accumulating provider logic again
- provider/runtime adapter behavior
- worker execution coordination

### Persistence And Efficiency

Tool persistence repositories are substantial and expected. Risk comes from catalog/source reconciliation and tool run listing/filtering under many tool runs.

Production requirement:

- Tool run queries must be paginated and indexed by status, created time, tool id, call id, and orchestration refs.
- Worker assignment must avoid global serial bottlenecks.

### Concurrency And Multi-User Readiness

Tool worker is a core scalability point. It must support:

- bounded concurrency
- per-tool/provider capability limits
- queue backpressure
- idempotent completion
- long-running background tools
- cancellation or supersession

Worker concurrency now has regression coverage for multi-run async execution,
image-like concurrent execution, scheduler slot filling, shared-state capability
backpressure, blocked-head skipping, cross-worker capacity fallback, and direct
worker `max_in_flight` over-assignment prevention.
Runnable-assignment selection now keeps ToolRun, ToolFunction, and Tool catalog
lookups inside the same UoW scope, so worker launch decisions do not depend on a
repository handle after the transaction context has exited.

Configured source validation now has golden-shape coverage for OpenAPI, MCP, and
CLI sources through the owner command service. Existing package/provider suites
cover bundled local package reconciliation, browser/mobile/session local package
manifests, MCP/OpenAPI runtime activation, duplicate package/tool/runtime-key
rejection, and CLI guided-function discovery.

Tool run queries now expose an owner-level `limit` and Operations Tool page/overview
call that query with an explicit budget instead of forcing full run-list materialization.
Regression coverage locks both the Tool owner limit behavior and the Operations Tool
page input limit.

Tool core now has an architecture guard against site/task-specific flight and airline
markers. Route/provider examples may still live in tests or external tool packages, but
the runtime owner module must remain generic.

### External Integration Readiness

Tool packages are the main extension story. External systems need stable package/source schemas, validation, and clear runtime target contracts.

### Remediation Checklist

- [x] Split `worker_service.py` into execution coordinator shell plus artifact externalizer, result validation/envelope, provider replay merger, runtime executor, tracking, completion/failure, recovery, assignment, wakeup, processing heartbeat, run heartbeat persistence, run-loop, run-resolution, and error mapper helpers.
- [x] Split `source_service.py` into source query facade plus source command, function command, runtime bundle builder, provider backend sync, requirement parser, mapping, state, events, validation, UoW, and command DTO helpers.
- [x] Split `infrastructure/cli_source.py` into focused CLI source config, discovery, runtime, process observer, credential, envelope, redaction, and path helpers.
- [x] Add worker concurrency/backpressure tests.
- [x] Add package/source validation golden tests for CLI, MCP, OpenAPI, and local runtime packages.
- [x] Add query-budget tests for tool run listing and Operations Tool page inputs.
- [x] Keep browser/flight/site-specific behavior out of Tool core.
- [x] Split Tool HTTP Pydantic models and payload projection out of `interfaces/http.py`.
- [x] Split broad Tool domain entities into catalog/runtime entity modules plus shared normalization.
- [x] Split Tool catalog models into type, helper, function-record, and source/discovery modules.

### Remediation Verification

Command passed after the current Tool split wave:

```bash
PYTHONPATH=src pytest -q tests/unit/test_tool_background.py tests/unit/test_tool_execution.py tests/unit/test_tool_source_service.py tests/unit/test_tool_catalog_reconcile.py tests/unit/test_operations_tool_readiness_sections.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_context_tree_tool.py tests/unit/test_module_architecture_guards.py --tb=short
```

Result:

- Tool targeted suite: 106 passed

Additional worker concurrency/backpressure verification:

```bash
PYTHONPATH=src pytest -q tests/unit/test_tool_background.py::ToolBackgroundTestCase::test_scheduler_does_not_assign_beyond_worker_inflight_limit tests/unit/test_tool_background.py::ToolBackgroundTestCase::test_worker_run_loop_processes_multiple_assigned_runs_concurrently tests/unit/test_tool_background.py::ToolBackgroundTestCase::test_scheduler_loop_fills_available_worker_inflight_slots tests/unit/test_tool_background.py::ToolBackgroundTestCase::test_scheduler_limits_shared_state_tool_assignments --tb=short
python -m ruff check tests/unit/test_tool_background.py --ignore F403,F405
```

Result:

- Tool worker concurrency/backpressure suite: 4 passed
- Targeted ruff over `test_tool_background.py` with existing star-import ignores:
  passed

Additional package/source validation verification:

```bash
PYTHONPATH=src pytest -q tests/unit/test_tool_source_service.py::ToolSourceServiceTestCase::test_create_source_accepts_configured_source_golden_shapes tests/unit/test_tool_source_service.py::ToolSourceServiceTestCase::test_create_source_rejects_invalid_configured_source_shapes tests/unit/test_tool_source_service.py::ToolSourceServiceTestCase::test_query_service_uses_openapi_source_runtime_request_metadata tests/unit/test_tool_source_service.py::ToolSourceServiceTestCase::test_cli_source_discovers_guided_functions --tb=short
python -m ruff check tests/unit/test_tool_source_service.py src/crxzipple/modules/tool/application/source_validation.py
```

Result:

- Tool source/package validation suite: 4 passed
- Targeted ruff over source validation paths: passed

Additional Tool run query-budget verification:

```bash
PYTHONPATH=src pytest -q tests/unit/test_tool_execution.py::ToolExecutionTestCase::test_list_tool_runs_applies_latest_run_limit tests/unit/test_operations_tool_read_model.py::test_tool_operations_source_health_exposes_single_browser_source --tb=short
python -m ruff check src/crxzipple/modules/tool/application/submission_service.py src/crxzipple/modules/tool/application/services.py src/crxzipple/modules/tool/application/ports/query.py src/crxzipple/modules/tool/domain/repositories.py src/crxzipple/modules/tool/infrastructure/persistence/repositories.py src/crxzipple/modules/tool/infrastructure/in_memory_repository.py src/crxzipple/modules/tool/interfaces/http.py src/crxzipple/modules/tool/interfaces/cli.py src/crxzipple/modules/operations/application/read_models/tool.py src/crxzipple/modules/operations/application/read_models/ports.py src/crxzipple/app/assembly/tool.py src/crxzipple/modules/workbench/application/read_models.py tests/unit/test_tool_execution.py tests/unit/test_operations_tool_read_model.py tests/unit/test_tool_source_service.py --ignore F401,F403,F405
```

Result:

- Tool run query-budget suite: 2 passed
- Targeted ruff over changed query-budget paths with existing unused/star import
  ignores: passed

Additional generic-core guard verification:

```bash
PYTHONPATH=src pytest -q tests/unit/test_module_architecture_guards.py::test_tool_core_has_no_site_specific_task_logic --tb=short
python -m ruff check tests/unit/test_module_architecture_guards.py tests/unit/test_tool_execution.py tests/unit/test_tool_background.py tests/unit/test_tool_source_service.py --ignore F403,F405
```

Result:

- Tool generic-core architecture guard: passed
- Targeted ruff over updated Tool tests/guard with existing star-import ignores:
  passed

Additional Tool HTTP split verification:

```bash
python -m ruff check src/crxzipple/modules/tool/interfaces/http.py src/crxzipple/modules/tool/interfaces/http_models.py src/crxzipple/modules/tool/interfaces/http_payloads.py
python -m compileall -q src/crxzipple/modules/tool/interfaces/http.py src/crxzipple/modules/tool/interfaces/http_models.py src/crxzipple/modules/tool/interfaces/http_payloads.py
PYTHONPATH=src pytest -q tests/unit/test_tool_http.py -k 'not openapi_provider_endpoints_discover_and_execute_remote_tools' --tb=short --maxfail=1
```

Result:

- Tool HTTP focused route suite: 24 passed, 1 deselected
- Targeted ruff and compile checks: passed

The deselected OpenAPI provider HTTP test requires binding a local
`ThreadingHTTPServer`, which the current sandbox denies with
`PermissionError: [Errno 1] Operation not permitted`. Local process-strategy tool
execution tests are also still blocked in this sandbox by the known
`ProcessPoolExecutor(spawn)` permission restriction; this does not indicate a Tool HTTP
split regression.

Additional Tool domain entity split verification:

```bash
python -m ruff check src/crxzipple/modules/tool/domain
python -m compileall -q src/crxzipple/modules/tool/domain
PYTHONPATH=src pytest -q tests/unit/test_tool_http.py tests/unit/test_tool_provider_backend_service.py --tb=short --maxfail=1 -k 'not openapi_provider_endpoints_discover_and_execute_remote_tools'
PYTHONPATH=src pytest -q tests/unit/test_tool_background.py --tb=short --maxfail=1 -k 'not executes_local_background_process_tool_and_updates_lifecycle'
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_metrics.py tests/unit/test_operations_tool_run_filters.py tests/unit/test_operations_tool_run_error_diagnostics.py tests/unit/test_operations_tool_scheduling_sections.py --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_tool_execution.py tests/unit/test_tool_source_service.py tests/unit/test_tool_catalog_reconcile.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_context_tree_tool.py tests/unit/test_module_architecture_guards.py --tb=short --maxfail=1 -k 'not executes_local_inline_process_tool_and_reports_process_context'
```

Result:

- Tool domain ruff and compile checks: passed
- Tool HTTP/provider backend suite: 28 passed, 1 deselected
- Tool background suite excluding local process sandbox case: 23 passed, 1 deselected
- Operations Tool projection subset: 10 passed
- Tool execution/source/catalog/Context/architecture subset excluding local process sandbox case: 95 passed, 1 deselected

Additional Tool catalog model split verification:

```bash
python -m ruff check src/crxzipple/modules/tool/application/catalog_models.py src/crxzipple/modules/tool/application/catalog_model_types.py src/crxzipple/modules/tool/application/catalog_model_helpers.py src/crxzipple/modules/tool/application/catalog_function_models.py src/crxzipple/modules/tool/application/catalog_source_models.py
python -m compileall -q src/crxzipple/modules/tool/application/catalog_models.py src/crxzipple/modules/tool/application/catalog_model_types.py src/crxzipple/modules/tool/application/catalog_model_helpers.py src/crxzipple/modules/tool/application/catalog_function_models.py src/crxzipple/modules/tool/application/catalog_source_models.py
PYTHONPATH=src pytest -q tests/unit/test_tool_catalog_reconcile.py tests/unit/test_tool_source_service.py tests/unit/test_tool_source_catalog_persistence.py tests/unit/test_tool_providers.py tests/unit/test_openapi_access.py tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_access_http.py --tb=short --maxfail=1 -k 'not discovers_and_executes_openapi_remote_tools and not openapi_provider_endpoints_discover_and_execute_remote_tools'
```

Result:

- Tool catalog model ruff and compile checks: passed
- Tool catalog/source/provider/access/UI subset: 73 passed, 1 deselected

Additional Tool worker run-loop/resolution split verification:

```bash
python -m ruff check src/crxzipple/modules/tool/application/worker_service.py src/crxzipple/modules/tool/application/worker_run_loop.py src/crxzipple/modules/tool/application/worker_run_resolution.py
python -m compileall -q src/crxzipple/modules/tool/application/worker_service.py src/crxzipple/modules/tool/application/worker_run_loop.py src/crxzipple/modules/tool/application/worker_run_resolution.py
PYTHONPATH=src pytest -q tests/unit/test_tool_background.py -k 'not executes_local_background_process_tool_and_updates_lifecycle' --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_tool_execution.py -k 'not executes_local_inline_process_tool_and_reports_process_context' --tb=short --maxfail=1
```

Result:

- Tool worker run-loop/resolution ruff and compile checks: passed
- Tool background suite excluding local process sandbox case: 23 passed, 1 deselected
- Tool execution suite excluding local process sandbox case: 20 passed, 1 deselected
- Tool worker UoW-boundary verification: ruff passed; worker/background/dispatch
  subset excluding local process sandbox cases: 51 passed, 2 deselected
