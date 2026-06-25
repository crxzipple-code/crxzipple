# Module Audit: tool

## Verdict

High importance, medium-high risk after the current split wave. Tool owns catalog, source packages, execution, worker lifecycle, runtime targets, and artifacts. Worker execution, source command/query, CLI source runtime, result/artifact handling, and source package helper seams are now much cleaner, but package parsing, persistence repositories, HTTP, and broad domain entities remain substantial.

## Evidence

- 110 Python files, about 27065 lines.
- Cross-module import signal: very high.
- Large files include `infrastructure/tool_packages.py` (1857), `infrastructure/persistence/repositories.py` (1553), `domain/entities.py` (1147), `interfaces/http.py` (1106), `application/catalog_models.py` (943), `application/worker_service.py` (888), `infrastructure/discovery/openapi.py` (814), `infrastructure/mcp_client.py` (767), `infrastructure/runtimes/openapi_remote.py` (761), and `infrastructure/cli_source_config.py` (620).

## Findings

- Tool ownership boundary is mostly correct: tool runs and catalog belong here; orchestration only coordinates.
- Source/package discovery, runtime worker execution, and catalog models have been split into focused helpers; package parsing and persistence remain large.
- Worker service complexity is lower after execution/runtime/artifact/error/helper extraction, but worker concurrency and backpressure remain launch-critical.
- Tool package/source adapters are the main external integration surface; they need stable contracts and clear failure modes.

## Launch Risks

- Tool worker bottlenecks or hidden sync IO can affect every long-chain run.
- Mixed source types can produce adapter-specific redundancy if package/source contracts are unclear.
- Large HTTP surface can expose owner internals.

## Recommendations

- Continue splitting Tool package materialization, persistence mapping, HTTP DTO/route shaping, and catalog read models into smaller units.
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

`application/worker_service.py` was 1713 lines and is now 888 lines after moving
artifact externalization, result validation, runtime execution, error normalization,
background tracking, capability payloads, execution context decoration, completion and
failure application, recovered dispatch handling, registration/stale/prune helpers,
assignment selection, wakeup waiting, and processing heartbeat threading into focused
application helpers. It remains a real execution hot path and should keep gaining
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

`infrastructure/tool_packages.py` remains 1857 lines and is now the largest Tool
hotspot. It is the next external integration surface to split or harden because package
ingestion will be a major extension point.

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

- package ingestion/materialization
- persistence repository mapping/query behavior
- HTTP route/DTO shaping

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

- [x] Split `worker_service.py` into execution coordinator shell plus artifact externalizer, result validation/envelope, provider replay merger, runtime executor, tracking, completion/failure, recovery, assignment, wakeup, heartbeat, and error mapper helpers.
- [x] Split `source_service.py` into source query facade plus source command, function command, runtime bundle builder, provider backend sync, requirement parser, mapping, state, events, validation, UoW, and command DTO helpers.
- [x] Split `infrastructure/cli_source.py` into focused CLI source config, discovery, runtime, process observer, credential, envelope, redaction, and path helpers.
- [x] Add worker concurrency/backpressure tests.
- [x] Add package/source validation golden tests for CLI, MCP, OpenAPI, and local runtime packages.
- [x] Add query-budget tests for tool run listing and Operations Tool page inputs.
- [x] Keep browser/flight/site-specific behavior out of Tool core.

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
