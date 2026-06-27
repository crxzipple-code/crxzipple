# Module Audit: tool

## Verdict

High importance, medium-high risk after the current split wave. Tool owns catalog, source packages, execution, worker lifecycle, runtime targets, and artifacts. Worker execution, source command/query, CLI source config/runtime, result/artifact handling, source package helper seams, service support contracts/projections, persistence repositories, HTTP route shaping, domain entity grouping, OpenAPI discovery parsing/projection, OpenAPI remote runtime request/security/result projection, and MCP HTTP/protocol/stdio-message boundaries are now much cleaner, but worker execution and live MCP stdio/runtime lifecycle edge cases remain substantial.

## Evidence

- 207 Python files, about 29598 lines.
- Cross-module import signal: very high.
- Large files include `application/worker_service.py` (503), `interfaces/http.py`
  (494), and `domain/tool_run_entity.py` (445).
- `application/worker_service.py` delegates worker registration/admin operations
  to `application/worker_admin.py`, cancellation/recovered-dispatch control to
  `application/worker_run_control.py`, and in-flight launch/reap/failover/
  heartbeat/runnable-run selection to `application/worker_inflight.py`.
- `infrastructure/tool_packages.py`, `infrastructure/tool_package_access.py`,
  `application/service_support.py`, `application/provider_backend_service.py`,
  `domain/runtime_entities.py`, `domain/entities.py`, and
  `application/catalog_models.py` are now thin export surfaces over focused
  helpers.
- `application/catalog_function_models.py` is now a 19-line export surface after
  moving function candidates, catalog records, and schema-hash computation to
  focused modules.
- `application/submission_service.py`, `application/settings_integration.py`,
  `application/surface.py`, `application/tool_result_artifacts.py`,
  `infrastructure/provider_catalog.py`, `infrastructure/cli_source_config.py`,
  `infrastructure/mcp_client.py`, `infrastructure/discovery/openapi.py`, and
  `infrastructure/runtimes/openapi_remote.py` have all been split into
  lifecycle-specific helpers while preserving their public import surfaces.
- `interfaces/http.py` is now 494 lines after splitting Pydantic models and
  payload projection into focused HTTP helper modules.
- `app/assembly/tool.py` is now a 466-line composition surface after service graph
  adapters moved to `app/assembly/tool_service_graph.py` and runtime
  infrastructure construction moved to `app/assembly/tool_runtime_infrastructure.py`.

## Findings

- Tool ownership boundary is mostly correct: tool runs and catalog belong here; orchestration only coordinates.
- Source/package discovery, runtime worker execution, catalog models, persistence repositories, domain entity groups, and HTTP DTO/payload projection have been split into focused helpers; several provider/runtime adapters remain large.
- Runtime-domain aggregates now keep run, assignment, and worker lifecycle methods
  in separate files while preserving the public domain export surface.
- Runtime SQLAlchemy persistence now keeps ToolRun, ToolRunAssignment, and
  ToolWorker repository/query/mapping behavior in separate files while preserving
  the persistence package export surface.
- ToolFunction and ToolFunctionCatalog SQLAlchemy persistence now live in
  separate repository modules instead of sharing one mixed function/catalog
  persistence file.
- CLI source configuration now keeps main command/path policy, credential binding
  projection, and promoted function argument parsing in focused modules.
- CLI source discovery now keeps candidate/spec assembly separate from guided
  action parameter/policy/effect contracts and Access credential requirement
  projection.
- CLI source runtime now keeps guided action routing and process lifecycle separate
  from one-shot help subprocess execution and process-output display redaction.
- Configured provider catalog now keeps discovery/activation orchestration separate
  from source record/config projection and persisted OpenAPI/MCP metadata conversion.
- Tool package access now keeps OpenAPI provider manifest parsing and manifest
  credential requirement parsing in separate infrastructure helpers behind a small
  package access export surface; credential requirement set assembly, declaration
  parsing, forbidden direct-source policy, and OpenAPI credential binding parsing
  now live in separate helpers.
- Tool package discovery/apply now keeps the public package export surface,
  namespace compatibility model, manifest loader, activation resolution/validation,
  and registry apply flow in separate modules.
- Tool package activation now keeps entrypoint import/validation and typed local
  handler dependency injection in focused helpers, leaving the activation module
  as a 122-line registration resolver.
- Tool package manifest parsing now keeps generic YAML scalar/list/enum/mapping
  parsers separate from package manifest semantics such as dependency,
  capability, runtime request, and runtime requirement set loading.
- Tool package catalog projection now keeps the public discovery adapter separate
  from source record/config projection, function/provider-backend candidate
  projection, and stable payload helpers.
- Provider backend application logic now keeps DTO/payload models, policy parsing,
  backend resolution, readiness evaluation, and execution-context payload projection
  in focused helpers behind a small provider backend export surface.
- Tool application service support now keeps service contracts, ToolFunction-to-Tool
  projection, credential requirement payload restoration, and attachment decoding in
  focused helpers while removing duplicate credential payload parsing.
- Tool result artifact handling now keeps orchestration of result externalization in
  a small entrypoint while artifact writes and artifact envelope merge policy live in
  focused helpers.
- ToolSurface query construction now keeps persisted/public DTOs separate from
  function/source/group projection policy.
- Tool submission now keeps the public batch entrypoint separate from catalog/access/
  runtime preparation, ToolRun/dispatch construction, and execution context/id helpers.
- Tool Settings bootstrap now keeps provider/root scanning separate from config value
  lookup, OpenAPI credential binding validation, and provider settings projection.
- OpenAPI discovery now keeps provider caching, operation models, document parsing,
  schema projection, security parsing, and Access credential requirement projection
  in separate discovery helpers.
- OpenAPI remote runtime now keeps HTTP invocation separate from request parameter
  construction, security/credential projection, request URL redaction, and
  response text/details projection.
- Daemon runtime readiness adapter now keeps daemon service/group metadata and
  Browser proxy credential readiness projection in focused helpers, leaving the
  adapter to own requirement evaluation flow.
- MCP client code now keeps the factory/export surface, stdio client facade,
  stdio sync process lifecycle, stdio async process lifecycle, HTTP transport,
  JSON-RPC protocol payload validation, and shared stdio message/error projection
  in separate modules.
- MCP adapter diagnostics now redact transport errors, JSON-RPC error messages,
  and stdio stderr details before raising `ToolValidationError`, so provider
  failures remain useful without leaking raw tokens, bearer headers, URL
  passwords, or sensitive query parameters.
- Worker service complexity is lower after execution/runtime/artifact/error/helper extraction, but worker concurrency and backpressure remain launch-critical.
- Worker assignment selection now resolves candidate tool/function metadata inside the
  same UoW that loaded assignments and runs, avoiding a closed-UoW lookup during
  capacity/backpressure decisions.
- Worker in-flight launch now guards the execution boundary against duplicate
  selector output, already-running run ids, and selector output longer than the
  available slot budget.
- Worker in-flight reap now removes cancelled child tasks and logs the cleanup
  instead of letting child-task cancellation interrupt worker shutdown cleanup.
- Tool package/source adapters are the main external integration surface; they need stable contracts and clear failure modes.

## Launch Risks

- Tool worker bottlenecks or hidden sync IO can affect every long-chain run.
- Mixed source types can produce adapter-specific redundancy if package/source contracts are unclear.
- HTTP surface is cleaner after DTO/payload split, but large external source/provider contracts can still expose owner internals if package/runtime adapters drift.

## Recommendations

- Continue hardening MCP stdio/runtime lifecycle and worker execution paths with
  cleanup, timeout, and backpressure coverage.
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
- `infrastructure/cli_source_config.py`
- `infrastructure/tool_packages.py`
- `infrastructure/provider_catalog.py`
- `infrastructure/mcp_client.py`
- `infrastructure/persistence/repositories.py`
- `interfaces/http.py`
- `domain/entities.py`

### File-Level Assessment

`application/worker_service.py` was 1713 lines and is now 503 lines after moving
artifact externalization, result validation, runtime execution, error normalization,
background tracking, capability payloads, execution context decoration, completion and
failure application, recovered dispatch handling, registration/stale/prune helpers,
assignment selection, in-flight assignment launch/reap/failover/heartbeat, wakeup
waiting, processing heartbeat threading, worker run-loop control, run catalog/function
resolution, ToolRun persistence transitions, and run/assignment/worker/dispatch
heartbeat persistence into focused application
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
validation into focused infrastructure helpers. `cli_source_discovery.py` is now a
179-line candidate/spec assembly entrypoint; guided action names, descriptions,
parameters, effects, and execution policy live in `cli_source_discovery_guided.py`;
Access credential requirement projection lives in `cli_source_discovery_credentials.py`.
`cli_source_runtime.py` is now a 307-line guided runtime entrypoint; one-shot help
subprocess execution lives in `cli_source_runtime_help.py`, and process-output
display redaction lives in `cli_source_runtime_output.py`. Credential-bearing CLI
process output now preserves the Process module's raw owner fact while the ToolRun
result details and provider replay payload returned by `cli_execute` /
`cli_read_output` use the CLI source redaction projection.

`infrastructure/cli_source_config.py` is now 250 lines after moving credential
binding DTO/parsing/validation to `cli_source_config_credentials.py` and promoted
function parameter projection, argv template rendering, and argument validation to
`cli_source_config_promoted.py`. The file now focuses on provider command/path
policy and argv construction.

`application/service_support.py` is now a 39-line application support export
surface. Service DTOs, UoW/runtime gateway protocols, dependency bundle, and base
class live in `application/service_contracts.py`; ToolFunction-to-Tool projection
lives in `application/tool_function_projection.py`; credential requirement payload
restoration lives in `application/credential_requirement_payloads.py` and is reused
by `source_requirements.py`; attachment base64 decoding lives in
`application/tool_attachment_payloads.py`.

`application/catalog_function_models.py` is now a 19-line export surface. Function
candidate and provider-backend candidate normalization lives in
`application/catalog_function_candidates.py`; persisted catalog record lifecycle
methods live in `application/catalog_function_records.py`; schema hash construction
lives in `application/catalog_function_hash.py`.

`application/provider_backend_service.py` is now a 28-line provider backend export
surface. Provider backend DTOs/constants live in `provider_backend_models.py`;
policy parsing and execution-context payload projection live in
`provider_backend_policy.py`; backend selection and not-available error projection
live in `provider_backend_resolution.py`; readiness aggregation and backend-to-tool
projection live in `provider_backend_readiness.py`.

`application/tool_result_artifacts.py` is now a 117-line result artifact entrypoint.
Raw output, large text, inline image/file externalization, artifact naming, and
attachment decoding live in `application/tool_result_artifact_externalization.py`.
Artifact result envelope construction, summary text, provider replay payloads, and
merge policy live in `application/tool_result_artifact_envelopes.py`. This keeps
Tool result replay bounded and artifact-backed without turning the worker result
path into a task-specific evidence layer.

`application/surface.py` is now a 180-line ToolSurface query service/export surface.
ToolSurface DTOs and payload methods live in `application/surface_models.py`;
function/source/group projection, runtime-request group parsing, and serial
concurrency-key derivation live in `application/surface_projection.py`.

`application/submission_service.py` is now a 203-line submission entrypoint.
Catalog function lookup, source/function executable checks, Access/runtime readiness
checks, and provider backend resolution live in `application/submission_preparation.py`.
ToolRun construction, background dispatch enqueue, inline start, and commit timing live
in `application/submission_run_creation.py`. Tool call/surface id extraction and
execution context decoration live in `application/submission_context.py`.

`application/settings_integration.py` is now a 76-line Settings bootstrap entrypoint.
Config lookup, enabled checks, value coercion, and de-duplication live in
`application/settings_config_values.py`; OpenAPI credential binding parsing and
legacy direct-source rejection live in `application/settings_openapi_credentials.py`;
OpenAPI/MCP provider settings and local-root projection live in
`application/settings_provider_projection.py`. This keeps Settings materialization
translation explicit without making Tool Settings bootstrap a second config parser.

`infrastructure/mcp_client.py` is now a 40-line builder/export surface. HTTP MCP
transport remains in `mcp_http_client.py`, JSON-RPC protocol payload/response
validation remains in `mcp_protocol.py`, stdio facade behavior lives in
`mcp_stdio_client.py`, sync/async stdio process lifecycles live in
`mcp_stdio_sync_session.py` and `mcp_stdio_async_session.py`, and shared stdio
message encoding, response-id validation, timeout/EOF/send error text, and
session-unavailable messages live in `mcp_stdio_messages.py`. Async stdio loop
thread startup/shutdown now lives in `mcp_stdio_async_loop.py`, leaving the async
session focused on request serialization, process lifecycle, and protocol IO. Sync/
async process start, close, and start-failure projection now live in
`mcp_stdio_processes.py`. External MCP diagnostic text is redacted through
`mcp_diagnostics.py` before it is exposed as
Tool validation errors, including HTTP transport failures, JSON-RPC error payloads,
stdio stderr details, stdio command startup failures, and URL query/fragment token
parameters.

`infrastructure/tool_packages.py` is now a 54-line package export surface.
Namespace compatibility properties live in `tool_package_models.py`; manifest
discovery/loading, local handler parsing, runtime binding parsing, provider backend
plan loading, and OpenAPI plan loading live in `tool_package_manifest_loader.py`;
generic manifest scalar/list/enum/mapping parsing lives in
`tool_package_manifest_parsers.py`; package manifest semantics for dependencies,
capabilities, runtime requests, and runtime requirement sets live in
`tool_package_manifest_values.py`;
activation resolution, duplicate validation, capability checks, and local handler
catalog filtering live in `tool_package_activation_resolution.py`; local/runtime
activation registration lives in the 122-line `tool_package_activation.py`;
entrypoint import validation lives in `tool_package_entrypoints.py`; typed local
handler dependency injection and external runtime requirement validation live in
`tool_package_activation_dependencies.py`; registry application for local, remote,
sandbox, and OpenAPI runtimes lives in the 150-line `tool_package_apply.py`.

`infrastructure/package_catalog.py` is now a 66-line bundled package discovery
adapter. Bundled source records, source config payloads, display text, runtime
requirements, and package source ids live in `package_catalog_records.py`; local
function candidates, OpenAPI function candidates, provider backend candidates,
and provider-backend policy metadata live in `package_catalog_candidates.py`;
stable payload and dependency payload helpers live in `package_catalog_payloads.py`.

`infrastructure/tool_package_access.py` is now a 20-line export surface.
OpenAPI provider manifest parsing lives in the 88-line
`infrastructure/tool_package_openapi_manifest.py`; OpenAPI credential binding
validation and legacy direct-credential-source rejection live in
`infrastructure/tool_package_openapi_credentials.py`; local package credential
requirement set assembly lives in the 79-line
`infrastructure/tool_package_credential_requirements.py`; credential declaration
parsing, setup-flow parsing, and transport/kind validation live in
`infrastructure/tool_package_credential_declarations.py`; shared forbidden
credential-source detection lives in
`infrastructure/tool_package_credential_source_policy.py`.

`infrastructure/provider_catalog.py` is now a 258-line discovery/activation surface
after moving configured provider source/config projection to
`provider_catalog_config.py` and OpenAPI/MCP persisted metadata conversion to
`provider_catalog_metadata.py`.

`infrastructure/discovery/openapi.py` is now a 57-line discovery provider
entrypoint. Operation/security dataclasses live in `discovery/openapi_models.py`,
document loading/path operation construction lives in `discovery/openapi_document.py`,
OpenAPI schema-to-ToolParameter projection lives in `discovery/openapi_schema.py`,
security scheme/requirement parsing lives in `discovery/openapi_security.py`, and
Access credential requirement projection remains in
`discovery/openapi_access_requirements.py`.

`infrastructure/runtimes/openapi_remote.py` is now a 109-line remote invocation
entrypoint. Path/query/body request construction lives in
`runtimes/openapi_remote_requests.py`; security requirement application,
credential binding resolution, Authorization/Cookie/query credential projection,
and request URL redaction live in `runtimes/openapi_remote_security.py`; response
body decoding, text summary, and compact details projection live in
`runtimes/openapi_remote_results.py`.

`application/catalog_models.py` was 943 lines and is now a 37-line application
export surface. Catalog enums/requirement types live in `catalog_model_types.py`,
stable payload/hash/schema helpers live in `catalog_model_helpers.py`, function
candidate/backend/function record models live in `catalog_function_models.py`, and
source/discovery records live in `catalog_source_models.py`.

`domain/entities.py` was 1147 lines and is now a 61-line domain export surface.
Catalog/source/function/provider/tool definition aggregates live in
`domain/catalog_entities.py`; runtime run, assignment, and worker aggregates live in
`domain/tool_run_entity.py`, `domain/tool_assignment_entity.py`, and
`domain/tool_worker_entity.py`; `domain/runtime_entities.py` is now the public
runtime export surface; common field normalization lives in
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

- ToolRun lifecycle remains substantial in `domain/tool_run_entity.py`
- catalog record composition is now split; keep it from accumulating provider logic again
- provider/runtime adapter behavior
- worker execution coordination

### Persistence And Efficiency

Tool persistence repositories are substantial and expected. Runtime run,
assignment, and worker persistence is now split by owner fact; remaining risk
comes from catalog/source reconciliation and tool run listing/filtering under many
tool runs.

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

- [x] Split `worker_service.py` into execution coordinator shell plus artifact externalizer, result validation/envelope, provider replay merger, runtime executor, tracking, completion/failure, recovery, assignment, in-flight task management, wakeup, processing heartbeat, run heartbeat persistence, run-loop, run-resolution, and error mapper helpers.
- [x] Split `source_service.py` into source query facade plus source command, function command, runtime bundle builder, provider backend sync, requirement parser, mapping, state, events, validation, UoW, and command DTO helpers.
- [x] Split `infrastructure/cli_source.py` into focused CLI source config, discovery, runtime, process observer, credential, envelope, redaction, and path helpers.
- [x] Split Tool package OpenAPI provider manifest parsing and manifest credential
      requirement parsing out of `infrastructure/tool_package_access.py`.
- [x] Split Tool package export surface, namespace compatibility model, manifest
      loading, activation resolution, registry apply policy, and package catalog
      projection out of the old package files.
- [x] Split CLI source config credential binding and promoted function parsing out
      of `infrastructure/cli_source_config.py`.
- [x] Split configured provider source/config projection and OpenAPI/MCP metadata
      payload conversion out of `infrastructure/provider_catalog.py`.
- [x] Add worker concurrency/backpressure tests.
- [x] Add package/source validation golden tests for CLI, MCP, OpenAPI, and local runtime packages.
- [x] Add query-budget tests for tool run listing and Operations Tool page inputs.
- [x] Keep browser/flight/site-specific behavior out of Tool core.
- [x] Split Tool HTTP Pydantic models and payload projection out of `interfaces/http.py`.
- [x] Split broad Tool domain entities into catalog/runtime entity modules plus shared normalization.
- [x] Split runtime-domain aggregates into ToolRun, ToolRunAssignment, and
      ToolWorkerRegistration focused modules.
- [x] Split Tool catalog models into type, helper, function-record, and source/discovery modules.
- [x] Split Tool application service support contracts, ToolFunction projection,
      credential requirement payload parsing, and attachment decoding out of
      `application/service_support.py`.
- [x] Split Tool provider backend DTOs, policy parsing, backend resolution,
      readiness evaluation, and execution-context projection out of
      `application/provider_backend_service.py`.
- [x] Split Tool result artifact externalization and artifact envelope merge policy
      out of `application/tool_result_artifacts.py`.
- [x] Split ToolSurface DTOs and source/function projection policy out of
      `application/surface.py`.
- [x] Split Tool submission preparation, ToolRun construction, and execution context
      helpers out of `application/submission_service.py`.
- [x] Split OpenAPI discovery Access credential requirement projection out of
      `infrastructure/discovery/openapi.py`.
- [x] Split OpenAPI discovery operation models, document parsing, schema
      projection, and security parsing out of
      `infrastructure/discovery/openapi.py`.
- [x] Split OpenAPI remote request/security construction and response
      projection out of `infrastructure/runtimes/openapi_remote.py`.
- [x] Split MCP HTTP transport and JSON-RPC protocol helpers out of
      `infrastructure/mcp_client.py`.
- [x] Split shared MCP stdio message/error projection helpers out of sync/async
      session lifecycle classes.
- [x] Split MCP async stdio loop thread startup/shutdown out of the async session.
- [x] Split MCP stdio process start/close helpers out of sync/async session classes.

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

Additional CLI source config split verification:

```bash
PYTHONPATH=src ruff check src/crxzipple/modules/tool/infrastructure/cli_source_config.py src/crxzipple/modules/tool/infrastructure/cli_source_config_credentials.py src/crxzipple/modules/tool/infrastructure/cli_source_config_promoted.py src/crxzipple/modules/tool/infrastructure/cli_source.py src/crxzipple/modules/tool/infrastructure/cli_source_runtime.py src/crxzipple/modules/tool/infrastructure/cli_source_discovery.py tests/unit/test_tool_source_service.py tests/unit/test_tool_providers.py
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/tool/infrastructure/cli_source_config.py src/crxzipple/modules/tool/infrastructure/cli_source_config_credentials.py src/crxzipple/modules/tool/infrastructure/cli_source_config_promoted.py src/crxzipple/modules/tool/infrastructure/cli_source.py src/crxzipple/modules/tool/infrastructure/cli_source_runtime.py src/crxzipple/modules/tool/infrastructure/cli_source_discovery.py
PYTHONPATH=src pytest -q tests/unit/test_tool_source_service.py -k 'cli or credential' --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_tool_providers.py -k '(cli or provider) and not discovers_and_executes_openapi_remote_tools' --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_tool_source_service.py::ToolSourceServiceTestCase::test_cli_source_discovers_guided_functions tests/unit/test_tool_source_service.py::ToolSourceServiceTestCase::test_cli_source_promoted_function_uses_source_runtime_policy tests/unit/test_tool_source_service.py::ToolSourceServiceTestCase::test_query_service_preserves_function_credential_requirements --tb=short --maxfail=1
```

Result:

- CLI source config split ruff and compile checks: passed
- Tool source CLI/credential scoped suite: 8 passed, 12 deselected
- Tool provider CLI/provider scoped suite: 21 passed, 1 deselected
- CLI discovery guided/promoted/credential projection suite: 3 passed
- Public config import surface check: passed

Additional CLI source runtime help/output split verification:

```bash
PYTHONPATH=src ruff check src/crxzipple/modules/tool/infrastructure/cli_source_runtime.py src/crxzipple/modules/tool/infrastructure/cli_source_runtime_help.py src/crxzipple/modules/tool/infrastructure/cli_source_runtime_output.py tests/unit/test_tool_source_service.py
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/tool/infrastructure/cli_source_runtime.py src/crxzipple/modules/tool/infrastructure/cli_source_runtime_help.py src/crxzipple/modules/tool/infrastructure/cli_source_runtime_output.py tests/unit/test_tool_source_service.py
PYTHONPATH=src pytest -q tests/unit/test_tool_source_service.py::ToolSourceServiceTestCase::test_cli_promoted_function_initial_output_limit_controls_first_read --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_tool_source_service.py --tb=short --maxfail=1
```

Result:

- CLI source runtime help/output split ruff and compile checks: passed
- Promoted function first-read output limit regression: 1 passed
- Full Tool source service suite: 21 passed

Additional configured provider catalog split verification:

```bash
PYTHONPATH=src ruff check src/crxzipple/modules/tool/infrastructure/provider_catalog.py src/crxzipple/modules/tool/infrastructure/provider_catalog_config.py src/crxzipple/modules/tool/infrastructure/provider_catalog_metadata.py tests/unit/test_tool_providers.py tests/unit/test_tool_source_service.py tests/unit/test_openapi_access.py
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/tool/infrastructure/provider_catalog.py src/crxzipple/modules/tool/infrastructure/provider_catalog_config.py src/crxzipple/modules/tool/infrastructure/provider_catalog_metadata.py
PYTHONPATH=src pytest -q tests/unit/test_tool_source_service.py -k 'configured or openapi or mcp or cli or credential' --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_openapi_access.py --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_tool_providers.py -k '(configured or mcp or openapi or cli) and not discovers_and_executes_openapi_remote_tools' --tb=short --maxfail=1
```

Result:

- Configured provider catalog split ruff and compile checks: passed
- Tool source configured/OpenAPI/MCP/CLI/credential suite: 12 passed, 8 deselected
- OpenAPI access suite: 10 passed
- Tool provider configured/MCP/OpenAPI/CLI scoped suite excluding socket-bound
  OpenAPI remote execution: 3 passed, 19 deselected
- Public provider catalog import surface check: passed

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

Additional Tool domain/runtime entity split verification:

```bash
python -m ruff check src/crxzipple/modules/tool/domain
python -m compileall -q src/crxzipple/modules/tool/domain
PYTHONPATH=src ruff check src/crxzipple/modules/tool/domain/runtime_entities.py src/crxzipple/modules/tool/domain/tool_run_entity.py src/crxzipple/modules/tool/domain/tool_assignment_entity.py src/crxzipple/modules/tool/domain/tool_worker_entity.py src/crxzipple/modules/tool/domain/entities.py
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/tool/domain/runtime_entities.py src/crxzipple/modules/tool/domain/tool_run_entity.py src/crxzipple/modules/tool/domain/tool_assignment_entity.py src/crxzipple/modules/tool/domain/tool_worker_entity.py src/crxzipple/modules/tool/domain/entities.py
PYTHONPATH=src pytest -q tests/unit/test_tool_http.py tests/unit/test_tool_provider_backend_service.py --tb=short --maxfail=1 -k 'not openapi_provider_endpoints_discover_and_execute_remote_tools'
PYTHONPATH=src pytest -q tests/unit/test_tool_background.py --tb=short --maxfail=1 -k 'not executes_local_background_process_tool_and_updates_lifecycle'
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_metrics.py tests/unit/test_operations_tool_run_filters.py tests/unit/test_operations_tool_run_error_diagnostics.py tests/unit/test_operations_tool_scheduling_sections.py --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_tool_execution.py tests/unit/test_tool_source_service.py tests/unit/test_tool_catalog_reconcile.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_context_tree_tool.py tests/unit/test_module_architecture_guards.py --tb=short --maxfail=1 -k 'not executes_local_inline_process_tool_and_reports_process_context'
```

Result:

- Tool domain and runtime aggregate ruff/compile checks: passed
- Tool HTTP/provider backend suite: 28 passed, 1 deselected
- Tool background suite excluding local process sandbox case: 23 passed, 1 deselected
- Operations Tool projection subset: 10 passed
- Tool execution/source/catalog/Context/architecture subset excluding local process sandbox case: 95 passed, 1 deselected
- Focused runtime aggregate behavior slice: Tool background 23 passed, 1
  deselected; Tool execution 20 passed, 1 deselected

Additional Tool catalog model split verification:

```bash
python -m ruff check src/crxzipple/modules/tool/application/catalog_models.py src/crxzipple/modules/tool/application/catalog_model_types.py src/crxzipple/modules/tool/application/catalog_model_helpers.py src/crxzipple/modules/tool/application/catalog_function_models.py src/crxzipple/modules/tool/application/catalog_source_models.py
python -m compileall -q src/crxzipple/modules/tool/application/catalog_models.py src/crxzipple/modules/tool/application/catalog_model_types.py src/crxzipple/modules/tool/application/catalog_model_helpers.py src/crxzipple/modules/tool/application/catalog_function_models.py src/crxzipple/modules/tool/application/catalog_source_models.py
PYTHONPATH=src pytest -q tests/unit/test_tool_catalog_reconcile.py tests/unit/test_tool_source_service.py tests/unit/test_tool_source_catalog_persistence.py tests/unit/test_tool_providers.py tests/unit/test_openapi_access.py tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_access_http.py --tb=short --maxfail=1 -k 'not discovers_and_executes_openapi_remote_tools and not openapi_provider_endpoints_discover_and_execute_remote_tools'
```

Result:

- Tool catalog model ruff and compile checks: passed
- Tool catalog/source/provider/access/UI subset: 73 passed, 1 deselected

Additional OpenAPI discovery Access projection split verification:

```bash
PYTHONPATH=src ruff check src/crxzipple/modules/tool/infrastructure/discovery/openapi.py src/crxzipple/modules/tool/infrastructure/discovery/openapi_access_requirements.py tests/unit/test_openapi_access.py
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/tool/infrastructure/discovery/openapi.py src/crxzipple/modules/tool/infrastructure/discovery/openapi_access_requirements.py
PYTHONPATH=src pytest -q tests/unit/test_openapi_access.py --tb=short --maxfail=1
```

Result:

- OpenAPI discovery Access projection ruff and compile checks: passed
- OpenAPI Access discovery/runtime suite: 10 passed

Additional OpenAPI remote runtime request/security/result split verification:

```bash
PYTHONPATH=src ruff check src/crxzipple/modules/tool/infrastructure/runtimes/openapi_remote.py src/crxzipple/modules/tool/infrastructure/runtimes/openapi_remote_requests.py src/crxzipple/modules/tool/infrastructure/runtimes/openapi_remote_security.py src/crxzipple/modules/tool/infrastructure/runtimes/openapi_remote_results.py tests/unit/test_openapi_access.py tests/unit/test_tool_providers.py
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/tool/infrastructure/runtimes/openapi_remote.py src/crxzipple/modules/tool/infrastructure/runtimes/openapi_remote_requests.py src/crxzipple/modules/tool/infrastructure/runtimes/openapi_remote_security.py src/crxzipple/modules/tool/infrastructure/runtimes/openapi_remote_results.py
PYTHONPATH=src pytest -q tests/unit/test_openapi_access.py --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_tool_providers.py::ToolProvidersTestCase::test_discovers_and_executes_openapi_remote_tools --tb=short --maxfail=1
```

Result:

- OpenAPI remote request/security/result split ruff and compile checks: passed
- OpenAPI Access runtime suite: 10 passed
- Tool provider OpenAPI remote execution test: 1 passed. Remote execution uses a
  patched async HTTP client instead of a local socket while preserving full
  container/source discovery, Access credential resolution, async transport,
  bearer header injection, and URL redaction assertions.

Additional tool package activation resolver split verification:

```bash
PYTHONPATH=src ruff check src/crxzipple/modules/tool/infrastructure/tool_package_apply.py src/crxzipple/modules/tool/infrastructure/tool_package_activation_resolution.py src/crxzipple/modules/tool/infrastructure/tool_packages.py tests/unit/test_tool_access_architecture.py tests/unit/test_tool_providers.py tests/unit/test_tool_capabilities.py
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/tool/infrastructure/tool_package_apply.py src/crxzipple/modules/tool/infrastructure/tool_package_activation_resolution.py src/crxzipple/modules/tool/infrastructure/tool_packages.py
PYTHONPATH=src pytest -q tests/unit/test_tool_providers.py -k 'package_apply or duplicate or remote_tools or openapi_remote_tools or mcp_remote_tools' --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_tool_capabilities.py --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_tool_access_architecture.py::test_tool_package_activation_filters_local_handlers_by_function_catalog --tb=short --maxfail=1
```

Result:

- Tool package activation resolver split ruff and compile checks: passed
- Tool provider package/remote scoped suite: 6 passed, 16 deselected
- Tool capability suite: 12 passed
- Tool package local handler catalog-filter architecture guard: 1 passed

Additional bundled package catalog projection split verification:

```bash
PYTHONPATH=src ruff check src/crxzipple/modules/tool/infrastructure/package_catalog.py src/crxzipple/modules/tool/infrastructure/package_catalog_candidates.py src/crxzipple/modules/tool/infrastructure/package_catalog_records.py src/crxzipple/modules/tool/infrastructure/package_catalog_payloads.py tests/unit/test_tool_source_service.py tests/unit/test_tool_providers.py
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/tool/infrastructure/package_catalog.py src/crxzipple/modules/tool/infrastructure/package_catalog_candidates.py src/crxzipple/modules/tool/infrastructure/package_catalog_records.py src/crxzipple/modules/tool/infrastructure/package_catalog_payloads.py
PYTHONPATH=src pytest -q tests/unit/test_tool_source_service.py -k 'package or bundled or local_tools or remote_runtimes or sandbox_runtimes or openapi or provider_backend' --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_tool_providers.py -k 'package or provider or local_tools or remote_runtimes or sandbox_runtimes or openapi' --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_app_assembly_targets.py tests/unit/test_app_assembly_module_local.py -k 'package or tool or source' --tb=short --maxfail=1
```

Result:

- Bundled package catalog projection split ruff and compile checks: passed
- Tool source package projection scoped suite: 4 passed, 16 deselected
- Tool provider package/provider scoped suite: 22 passed
- App assembly package/source scoped suite: 6 passed, 34 deselected

Additional MCP client HTTP/protocol/stdio lifecycle split verification:

```bash
PYTHONPATH=src ruff check src/crxzipple/modules/tool/infrastructure/mcp_client.py src/crxzipple/modules/tool/infrastructure/mcp_stdio_client.py src/crxzipple/modules/tool/infrastructure/mcp_stdio_sync_session.py src/crxzipple/modules/tool/infrastructure/mcp_stdio_async_session.py src/crxzipple/modules/tool/infrastructure/mcp_http_client.py src/crxzipple/modules/tool/infrastructure/mcp_protocol.py tests/unit/test_tool_mcp_client.py tests/unit/test_tool_providers.py
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/tool/infrastructure/mcp_client.py src/crxzipple/modules/tool/infrastructure/mcp_stdio_client.py src/crxzipple/modules/tool/infrastructure/mcp_stdio_sync_session.py src/crxzipple/modules/tool/infrastructure/mcp_stdio_async_session.py src/crxzipple/modules/tool/infrastructure/mcp_http_client.py src/crxzipple/modules/tool/infrastructure/mcp_protocol.py
PYTHONPATH=src pytest -q tests/unit/test_tool_mcp_client.py --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_tool_providers.py -k 'mcp and not http' --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_tool_source_service.py -k 'mcp or provider_backend' --tb=short --maxfail=1
```

Result:

- MCP client split ruff and compile checks: passed
- MCP client protocol/lifecycle unit suite: 3 passed
- Tool provider MCP scoped suite: 2 passed, 20 deselected
- Tool source MCP/provider-backend scoped suite: 1 passed, 19 deselected
- The MCP HTTP client test no longer binds a local socket; it patches the HTTP
  transport boundary and verifies session-header propagation. Sync and async
  stdio lifecycle guards verify timeout/EOF cleanup and session reset without
  launching a real child process.

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

Additional Tool worker admin/control split verification:

```bash
PYTHONPATH=src ruff check src/crxzipple/modules/tool/application/worker_service.py src/crxzipple/modules/tool/application/worker_admin.py src/crxzipple/modules/tool/application/worker_run_control.py src/crxzipple/modules/tool/application/worker_inflight.py
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/tool/application/worker_service.py src/crxzipple/modules/tool/application/worker_admin.py src/crxzipple/modules/tool/application/worker_run_control.py src/crxzipple/modules/tool/application/worker_inflight.py
PYTHONPATH=src pytest -q tests/unit/test_tool_background.py -k 'not executes_local_background_process_tool_and_updates_lifecycle' --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_tool_execution.py -k 'not executes_local_inline_process_tool_and_reports_process_context' --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_worker_loops.py --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_tool_http.py -k 'not openapi_provider_endpoints_discover_and_execute_remote_tools' --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_dispatch_http.py --tb=short --maxfail=1
```

Result:

- Tool worker admin/control ruff and compile checks: passed.
- Tool background suite excluding local process sandbox case: 23 passed, 1 deselected.
- Tool execution suite excluding local process sandbox case: 20 passed, 1 deselected.
- Worker loop suite: 14 passed.
- Tool HTTP suite excluding socket-bound OpenAPI sample server case: 24 passed,
  1 deselected.
- Dispatch HTTP suite: 2 passed.

Additional Tool catalog function model split verification:

```bash
PYTHONPATH=src ruff check src/crxzipple/modules/tool/application/catalog_function_models.py src/crxzipple/modules/tool/application/catalog_function_candidates.py src/crxzipple/modules/tool/application/catalog_function_records.py src/crxzipple/modules/tool/application/catalog_function_hash.py
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/tool/application/catalog_function_models.py src/crxzipple/modules/tool/application/catalog_function_candidates.py src/crxzipple/modules/tool/application/catalog_function_records.py src/crxzipple/modules/tool/application/catalog_function_hash.py
PYTHONPATH=src pytest -q tests/unit/test_tool_catalog_reconcile.py tests/unit/test_tool_source_catalog_persistence.py tests/unit/test_tool_source_service.py -k 'catalog or candidate or reconcile or source' --tb=short --maxfail=1
```

Result:

- Tool catalog function model ruff and compile checks: passed.
- Catalog/source scoped regression: 28 passed.

Additional Tool result artifact split verification:

```bash
PYTHONPATH=src ruff check src/crxzipple/modules/tool/application/tool_result_artifacts.py src/crxzipple/modules/tool/application/tool_result_artifact_externalization.py src/crxzipple/modules/tool/application/tool_result_artifact_envelopes.py
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/tool/application/tool_result_artifacts.py src/crxzipple/modules/tool/application/tool_result_artifact_externalization.py src/crxzipple/modules/tool/application/tool_result_artifact_envelopes.py
PYTHONPATH=src pytest -q tests/unit/test_tool_execution.py tests/unit/test_tool_background.py tests/unit/test_command_tools.py -k 'not executes_local_inline_process_tool_and_reports_process_context and not executes_local_background_process_tool_and_updates_lifecycle' --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_tool_execution.py tests/unit/test_tool_background.py -k 'large_text or artifact_ids or result_envelope' --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_orchestration_tools.py -k 'tool_result_session_item_uses_result_envelope_payload' --tb=short --maxfail=1
```

Result:

- Tool result artifact ruff and compile checks: passed
- Tool execution/background/command suite excluding local process sandbox cases:
  47 passed, 2 deselected
- Focused large-text/artifact envelope suite: 2 passed, 43 deselected
- Orchestration tool result envelope session projection: 1 passed, 36 deselected

Additional ToolSurface split verification:

```bash
PYTHONPATH=src ruff check src/crxzipple/modules/tool/application/surface.py src/crxzipple/modules/tool/application/surface_models.py src/crxzipple/modules/tool/application/surface_projection.py src/crxzipple/modules/tool/infrastructure/persistence/repository_surface_payloads.py tests/unit/test_tool_catalog.py
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/tool/application/surface.py src/crxzipple/modules/tool/application/surface_models.py src/crxzipple/modules/tool/application/surface_projection.py
PYTHONPATH=src pytest -q tests/unit/test_tool_catalog.py tests/unit/test_llm_runtime_request_factory.py tests/unit/test_orchestration_tools.py -k 'surface or tool_surface' --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_context_tree_tool.py -k 'tool' --tb=short --maxfail=1
```

Result:

- ToolSurface ruff/import/compile checks: passed
- ToolSurface/catalog/request/orchestration scoped suite: 6 passed, 61 deselected
- Context Workspace tool adapter/tree tool suite: 32 passed

Additional Tool submission split verification:

```bash
PYTHONPATH=src ruff check src/crxzipple/modules/tool/application/submission_service.py src/crxzipple/modules/tool/application/submission_context.py src/crxzipple/modules/tool/application/submission_preparation.py src/crxzipple/modules/tool/application/submission_run_creation.py tests/unit/test_tool_access_architecture.py
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/tool/application/submission_service.py src/crxzipple/modules/tool/application/submission_context.py src/crxzipple/modules/tool/application/submission_preparation.py src/crxzipple/modules/tool/application/submission_run_creation.py
PYTHONPATH=src pytest -q tests/unit/test_tool_execution.py -k 'not executes_local_inline_process_tool_and_reports_process_context' --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_tool_background.py -k 'not executes_local_background_process_tool_and_updates_lifecycle' --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_tool_source_service.py tests/unit/test_tool_provider_backend_service.py -k 'provider_backend or credential or openapi or configured' --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_tool_access_architecture.py --tb=short --maxfail=1
```

Result:

- Tool submission ruff and compile checks: passed
- Tool execution suite excluding local process sandbox case: 20 passed, 1 deselected
- Tool background suite excluding local process sandbox case: 23 passed, 1 deselected
- Tool source/provider backend scoped suite: 12 passed, 12 deselected
- Tool Access architecture guard suite: 7 passed
- MCP diagnostic redaction ruff and compile checks: passed
- MCP diagnostic redaction unit suite: 7 passed
- Tool MCP/settings/provider scoped regression: 53 passed, 15 deselected
- Worker in-flight backpressure guard ruff and compile checks: passed
- Worker in-flight backpressure/cleanup unit suite: 2 passed
- Worker loop/background scoped regression: 24 passed, 14 deselected
- Tool background suite excluding local process sandbox case: 23 passed, 1 deselected
- Tool execution suite excluding local process sandbox case: 20 passed, 1 deselected
- Worker loop plus in-flight helper suite: 16 passed
