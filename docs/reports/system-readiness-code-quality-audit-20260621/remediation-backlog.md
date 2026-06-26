# System Readiness Remediation Backlog

Date: 2026-06-21

This backlog turns the module audit into implementation waves. It is intentionally conservative: fix architectural pressure points, add executable invariants, and avoid compatibility shims or double-track runtime behavior.

## Ground Rules

- Owner modules keep data truth. Projections, renderers, and UI surfaces do not become hidden owners.
- Context Workspace controls context selection; provider adapters render selected slices into provider protocol.
- Operations and Workbench observe owner facts. They do not infer missing runtime truth.
- LLM/tool/session/orchestration boundaries must stay mechanical and testable.
- No task-specific core logic. Skills/tools can carry task strategy; runtime kernel remains generic.
- No silent production fallback to in-memory, file, or SQLite stores where shared Postgres/Redis runtime is required.
- No uncertain debug summaries enter LLM input.

## Acceptance Gates

### Gate A. Architecture Guards

- [x] Domain packages cannot import FastAPI, SQLAlchemy, Redis, Playwright, infrastructure packages, or other module domain packages directly.
- [x] Access does not import Authorization.
- [x] Authorization does not import Access credential/token infrastructure.
- [x] Orchestration cannot import provider-specific adapter internals.
- [x] LLM request builders cannot read Session repositories directly.
- [x] Workbench/Operations projectors declare owner facts they consume.
- [x] Operations Python files stay focused and are guarded at 250 lines.

Current executable guard coverage lives in `tests/unit/test_module_architecture_guards.py`.
Workbench run projection and Operations Tool/LLM/Orchestration projections now expose
structured owner fact source declarations; Workbench keeps actual owner call sources as
separate diagnostics so architecture declarations and per-request call traces do not drift.
Operations file focus is also guarded so page builders, table/projector helpers,
interface routes, application facades, and lightweight infrastructure stores cannot
silently grow back into aggregate files.

### Gate B. Runtime Lifecycle Invariants

- [x] One LLM invocation yields durable LLM response items.
- [x] Tool calls become tool runs through Tool owner lifecycle.
- [x] Tool results become Session items or artifact refs through approved ports.
- [x] Context render snapshot references selected owner facts only.
- [x] Provider request input is generated from renderer output, not ad hoc orchestration prompt assembly.
- [x] Workbench and Operations render from owner facts/projections without fallback progress that hides missing data.

LLM SQL persistence now has a response-item/event/continuation round-trip test.
The response-item inline tool-loop fixture proves the owner-fact chain across LLM
response item, Tool run, Session tool result, Orchestration execution item, Context
render snapshot metadata, and follow-up provider input. Workbench golden tests lock
debug/progress suppression and owner-linked timeline projection, while Operations
projection tests lock module read-model source declarations and cost/freshness
diagnostics.

Verification:

- `PYTHONPATH=src pytest -q tests/unit/test_llm.py::LlmServiceTestCase::test_invocation_repository_persists_response_items_events_and_continuation tests/unit/test_orchestration_tools.py::OrchestrationToolsTestCase::test_response_items_tool_calls_drive_inline_tool_loop --tb=short` -> 2 passed.
- `PYTHONPATH=src pytest -q tests/unit/test_workbench_read_model.py tests/unit/test_workbench_projection_diagnostics.py tests/unit/test_operations_llm_projection_diagnostics.py tests/unit/test_operations_orchestration_projection_diagnostics.py tests/unit/test_operations_tool_projection_diagnostics.py --tb=short` -> 16 passed.
- 2026-06-24 continuation pass: preflight compaction now refreshes the owning
  orchestration run's active session binding after Session rotates the active
  instance, so context-limit recovery retries write final assistant output into
  the current active segment instead of the compacted historical segment.
  Regression coverage:
  `PYTHONPATH=src pytest -q tests/unit/test_orchestration_memory.py tests/unit/test_orchestration_context.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_request_render_input_projection.py --tb=short --maxfail=1`
  -> 149 passed.
- 2026-06-24 continuation pass: HTTP module tests now isolate
  `APP_MEMORY_STORAGE_ROOT` under the SQLite harness tempdir, preventing runtime
  Memory recall tests from reading or ranking stale workspace `.crxzipple/memory`
  files. Regression coverage:
  `PYTHONPATH=src pytest -q tests/unit/test_memory_http.py --tb=short`
  -> 6 passed.
- 2026-06-24 continuation pass: current sandbox still denies local socket binds
  and Python `ProcessPoolExecutor(spawn)` semaphore probing
  (`os.sysconf("SC_SEM_NSEMS_MAX")` returns `PermissionError`). With socket-bound
  HTTP/CDP/MCP tests and the 13 process-pool/provider-server capability tests
  excluded, the largest runnable unit subset passes:
  `PYTHONPATH=src pytest -q tests/unit ... --tb=short --maxfail=1`
  -> 2376 passed, 13 deselected.

### Gate C. Persistence And Concurrency

- [x] Shared runtime rejects hidden in-memory/file event backend.
- [x] Shared runtime uses Redis event backend.
- [x] Production mode documents/guards SQLite use for Memory index.
- [x] Dispatch claim/lease has concurrent worker tests.
- [x] Daemon service ensure/start/stop/recover has smoke tests.
- [x] Browser profile leases prevent current allocation state bleed.
- [x] Mobile device leases prevent cross-user state bleed.

Shared runtime entrypoints now run the same persistence guard for database and events
backends: Redis events pass by default; file events require
`APP_ALLOW_FILE_EVENTS_RUNTIME_FALLBACK=1` as an explicit one-off fallback.
Production runtime also requires explicit acknowledgement for the current local
Memory SQLite index by setting `APP_ALLOW_SQLITE_MEMORY_INDEX_RUNTIME=1`.
Dispatch SQL claim now uses an atomic candidate-update path and has a concurrent
worker regression test proving queued tasks are not duplicated under simultaneous
claim attempts; existing lease heartbeat/recovery coverage remains in the same suite.
Daemon service/manager/CLI/HTTP smoke coverage now verifies ensure/start/status,
healthcheck, stop/down, reconcile/recover, service sets, lease contention/reentrant
release behavior, and endpoint probe failure mapping.
Mobile device execution now acquires a file-backed device lease in the coordinator
before control/action engine execution and releases it afterward; regression tests
cover same-owner refresh, different-owner conflict, execution-time lease visibility,
and release after execution.
Process output reads now use repository-level bounded stream windows instead of
loading whole stdout/stderr files before slicing; process ids reject traversal
before resolving filesystem paths; stale running process sessions with dead PIDs
refresh into terminal failed state; Process CLI list/output paths avoid full-log
loads.
Event Relay is retained as a narrow daemon-managed event-to-Workbench bridge with
cursor/replay/error retry tests and an architecture guard preventing imports of
owner runtime mutators. The empty Delivery placeholder module has been retired;
Channels and Events remain the current delivery-related owner modules.
OCR host and PP-Structure adapters now normalize timeout/request failures,
invalid JSON payloads, HTTP validation/server errors, and provider error codes
into OCR domain errors.
Authorization temporary grants now filter by run/session plus recorded agent
identity before contributing granted tool/effect ids; regression tests cover run
grant, session grant, and agent-managed allow/revoke state-machine boundaries.
Authorization audit payloads now redact sensitive nested keys before persistence,
with regression coverage against both application read models and stored audit JSON.
Authorization tool execution decision flow now lives in a focused application helper,
leaving the main service responsible for repository access, temporary grant aggregation,
evaluator access, policy lifecycle, and audit.
Authorization impact-preview projection now lives in a focused application helper,
leaving the main service responsible for audit recording around before/after decisions.
Authorization temporary grant construction and scoped aggregation now live in a focused
application helper, leaving the main service responsible for storing grants and auditing
grant creation.
Authorization temporary grant creation/storage/audit coordination now lives in a
focused application use-case service, leaving the main service as the public facade.
Authorization dry-run and impact-preview decision use cases now live in a focused
application helper, leaving the main service to expose the public API only.
Authorization audit record construction now lives in a focused application helper,
leaving the main service responsible for deciding when to write audit records.
Authorization policy create/update/enable/delete/import coordination now lives in a
focused application lifecycle helper. Public service policy, decision, grant, and audit
entry methods now live in focused facade mixins, leaving the main service as the
composition/audit/evaluator/check entrypoint. Agent-managed grant/revoke coordination
now lives in a focused application helper over the policy lifecycle helper.
Authorization SQLAlchemy/domain persistence mapping now lives in a focused repository
mapper helper, leaving repositories responsible for query/commit/bootstrap/pagination
behavior.
Agent profile/home remediation now keeps `AgentApplicationService` as the public facade
while profile lifecycle orchestration lives in `AgentProfileUseCases` and home
migrate/sync/export/inspect/file-update orchestration lives in `AgentHomeUseCases`,
with the Agent Unit of Work protocol split into a shared application port.

### Gate D. Request/Projection Cost

- [x] Long-session LLM request render has budget tests.
- [x] Workbench timeline projection reports owner calls and processed item count.
- [x] Operations projection reports freshness and build cost.
- [x] Context render snapshot records selected node count, selected session item count, provider-visible tool count, rendered chars, and elapsed time.

## Wave 0. Baseline Tests And Visibility

Purpose: add safety nets before splitting large files.

| Task | Modules | Acceptance |
| --- | --- | --- |
| Add architecture import tests | all modules | Done: domain/import boundary guards fail on forbidden dependencies |
| Add runtime lifecycle invariant tests | orchestration, llm, session, tool, context_workspace | Done: response-item tool loop fixture passes owner fact assertions; Orchestration execution chain lifecycle tests now cover bootstrap, LLM start/complete/fail, tool batch, late tool result, approval terminal item, continuation decision, and final response materialization |
| Add projection cost counters | operations, workbench, context_workspace | Complete for current visibility wave: Operations Tool/LLM/Orchestration pages expose owner source declarations, owner calls, item counts, freshness, and elapsed time; Context request render snapshots expose selected node/session item/tool/projected input/char/elapsed cost payloads; Workbench run responses expose owner call sources, owner call count, processed item count, timeline item count, and elapsed time. Remaining deeper work is budget enforcement, not visibility |
| Add production persistence guard tests | events, dispatch, memory, settings | Complete for current runtime guard wave: Redis events are required unless `APP_ALLOW_FILE_EVENTS_RUNTIME_FALLBACK=1`; production Memory SQLite index requires `APP_ALLOW_SQLITE_MEMORY_INDEX_RUNTIME=1`; Dispatch retired the unused in-memory repository path and has an architecture guard; Daemon smoke/concurrency coverage verifies service ensure/start/status/stop/recover and lease behavior |

## Wave 1. Runtime Hot Path Stabilization

Purpose: make model-visible data and runtime facts predictable.

| Task | Modules | Acceptance |
| --- | --- | --- |
| Split session replay/append/compaction services | session | Boundary coverage complete for this wave: append DTO/item construction, lifecycle/routing DTOs, query/window DTOs, Session Unit of Work port, metadata DTO/item merge helper, reset policy, appended item event payload projection, replay window, item range, context frontier, segment handle read-slice construction, pure read/window construction via `SessionQueryReader`, and segment compaction rules/DTOs are outside `SessionApplicationService`; replay protocol preservation is covered; session item/instance sequence uniqueness, stale append sequence race rejection, and stale segment rotation race rejection are enforced at persistence schema boundary; append sequence conflicts retry through an application-level detector port; stale writes into historical segments and stale compaction on closed active instances are rejected; active-only replay stays on the current segment after compaction |
| Lock provider rendering boundary | llm, context_workspace | Provider adapter receives only selected renderer output and tool schemas; LLM runtime request has been split into neutral request shell, render snapshot/control metadata, runtime input item projection, Tool Surface projection, and preview/diagnostic helpers; request factory Tool Surface snapshot projection is isolated behind a focused builder, request-render projected input restoration/orphan tool-call filtering is isolated behind a focused input filter, and request factory metadata/snapshot/mode/validation helpers are isolated behind a focused helper module; LLM profile credential expectation and Access binding metadata checks now live in a focused profile credential helper; profile warmup lifecycle and warmup event recording now live in a focused warmup service; invocation event payload construction is split into runtime summary, terminal payload, completed-payload extraction, and lightweight started/provider/warmup event modules; streaming invocation event normalization, completion projection, and failure recording now live in a focused event recorder; session replay has been split into replay-window facade, item projection/content extraction, content metrics/truncation, tool-result stats, protocol diagnostics, and budget helpers; tool-result replay text now delegates bounded field normalization and detail/result excerpt extraction to focused helpers; LLM persistence repositories now delegate SQLAlchemy/domain mapping to focused mappers; OpenAI Responses and Codex Responses adapters now delegate SSE/WebSocket stream reading and completed-event projection to focused streaming/event-projection modules; Codex completed-event adapter response projection, HTTP SSE retry/dispatch, HTTP wire request construction, HTTP SSE headers/stream dispatch, and WebSocket pool/header/endpoint/retryable-transport helpers live in focused helper/transport modules; Codex renderer runtime-context prompt item construction and provider-native WebSocket continuation delta selection live in focused helper modules; Chat Compatible adapter now delegates wire parsing, completed-event/result projection, XML-ish tool-call fallback parsing, stripped assistant text construction, streamed tool-call chunk merging, and response-item construction to focused projection/event/response-item modules; provider message projection facade is retired, with renderers importing common/OpenAI/Anthropic/Gemini projection modules directly; provider request preview delegates utility fingerprint/truncation and tool-report projection to focused modules; LLM HTTP routes now delegate Pydantic models, request DTO mapping, response DTO mapping, and SSE formatting to focused interface modules with no mixed mapping facade; LLM CLI delegates payload parsing and request-preview reporting to a focused helper, with request/factory/transcript/adapter/renderer/HTTP/CLI regression coverage |
| Split orchestration execution-chain and worker CLI hotspots | orchestration | Done: Execution-chain lifecycle tests and focused modules are in place; execution-chain SQLAlchemy repositories are split from run/wait/ingress/executor-lease persistence; `domain/entities.py` is now a thin export surface over execution entities, run aggregate, ingress aggregate, executor lease aggregate, and payload helpers; run aggregate route/session binding/enqueue/resume, worker claim/heartbeat/lease recovery, and terminal complete/fail/cancel lifecycle methods are split to focused domain mixins; `worker_cli.py` is a thin composition layer over shared runtime helpers, executor commands, scheduler commands, and isolated benchmark/synthetic runtime support; `worker_cli_benchmark.py` delegates common benchmark run/status helpers to `worker_cli_benchmark_common.py` and synthetic tool-IO runtime support to `worker_cli_benchmark_synthetic.py`; executor benchmark command registration lives in `worker_cli_executor_benchmarks.py`; `engine.py` delegates DTO/context records to `engine_models.py`, provider/request helper logic to `engine_runtime_helpers.py`, and outcome projection to `engine_outcomes.py`; progress/waiting duplicated execution-payload helpers are split to `coordinators/execution_payloads.py`, waiting recovery-contract payload helpers are split to `coordinators/waiting_recovery_payloads.py`, waiting approval replay/recovery lives in `coordinators/waiting_approval_recovery.py`, engine session tool-result projection lives in `engine_session_tool_results.py`, maintenance context-budget/compaction-summary/auto-compaction/run-classification flows are split to focused maintenance helper modules, and runtime request draft DTO/session replay/payload helpers are split from the collector; architecture guard keeps benchmark imports lazy for production worker CLI modules; daemon-managed scheduler/executor smoke completed through `benchmark-daemon-runtime` |
| Add Browser lease/action cleanup guard tests | browser | Done: allocation target cleanup is profile/allocation-scoped, CDP command-session context manager detaches on body errors, `cdp-raw` and network-inspect detach CDP sessions after command failure, action-trace snapshot previews are bounded, Browser production core is guarded against task-specific site logic, and the broad Browser unit suite passes |
| Split Browser application services | browser | Done: `services.py` is a thin export layer; profile resolver/capabilities/assemblers/planner/tab ops/selection ops/allocation target adapters, execution coordinator, profile admin, profile pool, profile allocator, lifecycle helpers, profile allocation selection strategy, allocation target recycle policy, and target tracking/reconciliation projection live in focused modules; broad Browser unit suite and architecture tests pass |
| Split Browser action engine internals | browser | Done: `action_engines.py` is now the action-engine dependency assembly surface; execution lifecycle, page dispatch, batch execution, raw CDP execution, action-trace coordination, interaction primitives, locator/ref resolution, primitive page actions, ref/overlay handling, and wait actions live in focused infrastructure modules; unused toolbar/date/bulk-selection interaction helpers were retired instead of moved to another compatibility layer; `action_engine_scripts.py` is now the expression export surface after marker/snapshot/bulk-selection/overlay-picker/target-text script split; `script_insight.py` is now the script-insight action facade after runtime expression, payload coercion, and source-analysis/search/extraction helper split; `action_trace.py` is now the action-trace service entrypoint after payload, snapshot, state, network, and envelope/recommendation helper split; `network_page_fetch.py` is now the page-network fetch service entrypoint after request normalization, page-runtime execution, safety/diff analysis, event payload, and common result helper split; `engines.py` has tab operation orchestration, tab/runtime-state metadata, CDP wire IO, host/process lifecycle helpers, and in-memory engines split out; Browser domain `value_objects.py` is now a thin export surface over type/helper/profile/tab/network/command value modules; Browser HTTP route surface now delegates request models, profile helpers, proxy egress checks, and update-clear payload rules to focused interface helpers; Browser profile payloads now delegate diagnostics/entry/aggregate assembly to focused helpers; Browser CLI is now a thin Typer root over profile/pool/allocation/host/action command modules; Browser observation now delegates value/page/runtime/interaction/projection assembly to focused helpers; broad Browser unit suite and architecture guard pass |
| Remove fallback progress in primary timeline | workbench | Done: primary timeline filters empty agent progress/thinking steps, projects only user-visible LLM response items, hides context-tree control calls and debug-only continuation text, and keeps long-chain timeline shape locked by golden coverage |
| Add request render budget tests | context_workspace, llm, session | Done for the current request-render boundary: long session trees with many large historical session nodes still resolve and project only the current frontier item plus provider-visible schema, and persisted request-render cost reports stay bounded |
| Add tool result/artifact ref invariant | tool, artifacts, session, llm | Done for Tool result replay: large text/raw output is externalized to artifacts, Session stores provider replay refs, and LLM transcript replay ignores trace/debug-only bodies; LLM invocation raw request/response retention remains a separate provider-boundary policy if raw payload retention expands |
| Split Context Workspace root-node bootstrap | context_workspace | Done: root-node constants, section roots, instruction/agent guidance, run/execution seeds, planning seeds, resource roots, and estimate/payload helpers are split into focused `root_node_*` modules; `root_nodes.py` now only preserves default seed order, public constants, and parent lookup. Context Workspace application services are also split by workspace, tree, snapshot, and slice roles into focused modules while `services.py` remains a thin export surface. Context Workspace application DTOs are split by workspace, slice/control, action/upsert, and render/snapshot roles while `models.py` remains a thin export surface. Context Workspace persistence mapping is split into `infrastructure/persistence/repository_mappers.py`, leaving `repositories.py` focused on query/transaction behavior. XML rendering is split into public entry, tree traversal/state labels, value normalization, and tool-node rendering modules. Provider attachment mirroring is split into public mirror flow, tool-surface policy/default parsing, and tool-schema budget/group-visibility accounting modules |
| Add Tool worker lifecycle guards | tool, dispatch, artifacts | Done: background worker tests lock registration/staleness, assignment heartbeat, recovered dispatch handling, retry exhaustion, large-result artifact refs, result envelope persistence, dispatch terminal state, and worker slot release; architecture guard prevents Tool application from importing Orchestration runtime owner layers |

Browser allocation follow-up note: reusable-allocation lookup, explicit/manual pool
selection, candidate availability, runtime-blocked checks, cooldown filtering,
round-robin selection, and least-busy selection now live in
`application/profile_allocation_selection.py`; target recycle defaults,
close-target metadata, target remember/forget projection, and target reconcile/lost
projection live in `application/profile_allocation_targets.py`;
`profile_allocator_service.py` keeps allocation lifecycle, heartbeat,
release/fail/expire/drain, event emission, and persistence. Current verification:
`PYTHONPATH=src ruff check src/crxzipple/modules/browser/application/profile_allocator_service.py src/crxzipple/modules/browser/application/profile_allocation_selection.py src/crxzipple/modules/browser/application/profile_allocation_targets.py tests/unit/test_browser_profile_allocator.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/browser/application/profile_allocator_service.py src/crxzipple/modules/browser/application/profile_allocation_selection.py src/crxzipple/modules/browser/application/profile_allocation_targets.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_browser_profile_allocator.py --tb=short --maxfail=1`
-> 14 passed;
`PYTHONPATH=src pytest -q tests/unit/test_browser_profile_allocator.py tests/unit/test_browser_interfaces.py tests/unit/test_browser_domain.py tests/unit/test_operations_browser_read_model.py --tb=short --maxfail=1`
-> 62 passed.

Orchestration engine follow-up note: `application/engine.py` is now a 747-line
advancement coordinator. Engine preview/context/outcome records live in
`engine_models.py`; request option, response-format, continuation, provider
continuation state, metadata, id de-duplication, optional text, and terminal
diagnostic helpers live in `engine_runtime_helpers.py`; and outcome projection,
tool execution context attributes, and background tool-call intent fallback live in
`engine_outcomes.py`. Tests import the new helper modules directly instead of
relying on private names from `engine.py`. Current verification:
`python -m ruff check src/crxzipple/modules/orchestration/application/engine.py src/crxzipple/modules/orchestration/application/engine_models.py src/crxzipple/modules/orchestration/application/engine_runtime_helpers.py tests/unit/test_llm_runtime_request_factory_builder.py tests/unit/test_orchestration_context_workspace_snapshot.py --ignore F403,F405`
-> passed;
`python -m compileall -q src/crxzipple/modules/orchestration/application/engine.py src/crxzipple/modules/orchestration/application/engine_models.py src/crxzipple/modules/orchestration/application/engine_runtime_helpers.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py::test_engine_carries_context_contract_metadata_for_llm_invocation tests/unit/test_llm_runtime_request_factory_builder.py --tb=short --maxfail=1`
-> 37 passed;
`PYTHONPATH=src pytest -q tests/unit/test_orchestration_tools.py tests/unit/test_orchestration_context.py tests/unit/test_orchestration_context_workspace_snapshot.py --tb=short --maxfail=1`
-> 92 passed;
`PYTHONPATH=src pytest -q tests/unit/test_orchestration_memory.py tests/unit/test_request_render_input_projection.py --tb=short --maxfail=1`
-> 22 passed.

Outcome split verification:
`PYTHONPATH=src ruff check src/crxzipple/modules/orchestration/application/engine.py src/crxzipple/modules/orchestration/application/engine_outcomes.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/orchestration/application/engine.py src/crxzipple/modules/orchestration/application/engine_outcomes.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_orchestration_execution_chain.py --tb=short --maxfail=1`
-> 32 passed;
`PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py --tb=short --maxfail=1`
-> 38 passed;
`PYTHONPATH=src pytest -q tests/unit/test_orchestration_tools.py -k 'tool_call or tool_result or background or inline' --tb=short --maxfail=1`
-> 16 passed, 21 deselected.

Orchestration run aggregate follow-up note: `domain/run_entity.py` is now a
475-line run aggregate. Route/session binding/enqueue/resume lifecycle lives in
`domain/run_queue_lifecycle.py`; worker ownership lifecycle (`claim`, `heartbeat`,
`recover_worker_lease`, `_require_worker`) lives in
`domain/run_worker_lifecycle.py`; terminal lifecycle (`complete`, `fail`, `cancel`)
lives in `domain/run_terminal_lifecycle.py`. The aggregate still owns state fields,
acceptance, and waiting/tool/approval state transitions; the mixins only group
lifecycle methods around the same aggregate state. Current verification:
`PYTHONPATH=src ruff check src/crxzipple/modules/orchestration/domain/run_entity.py src/crxzipple/modules/orchestration/domain/run_queue_lifecycle.py src/crxzipple/modules/orchestration/domain/run_worker_lifecycle.py src/crxzipple/modules/orchestration/domain/run_terminal_lifecycle.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/orchestration/domain/run_entity.py src/crxzipple/modules/orchestration/domain/run_queue_lifecycle.py src/crxzipple/modules/orchestration/domain/run_worker_lifecycle.py src/crxzipple/modules/orchestration/domain/run_terminal_lifecycle.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_orchestration_queue.py tests/unit/test_orchestration_execution_chain.py --tb=short --maxfail=1`
-> 68 passed;
`PYTHONPATH=src pytest -q tests/unit/test_orchestration_executor_leases.py tests/unit/test_workbench_read_model.py tests/unit/test_operations_orchestration_projection_diagnostics.py --tb=short --maxfail=1`
-> 49 passed;
`PYTHONPATH=src pytest -q tests/unit/test_orchestration_tools.py tests/unit/test_orchestration_context.py tests/unit/test_orchestration_context_workspace_snapshot.py --tb=short --maxfail=1`
-> 92 passed.

Orchestration maintenance follow-up note: `application/maintenance.py` is now a
303-line public maintenance service facade. Preflight context-budget detection,
context-window threshold calculation, render-preview metrics, and session pressure
helpers live in `maintenance_context_budget.py`; compaction-summary materialization
lives in `maintenance_compaction_summary.py`; post-run/pre-compaction follow-up
scheduling lives in `maintenance_auto_compaction.py`; and run classification plus
context-limit error recognition lives in `maintenance_run_classification.py`.
Current verification:
`PYTHONPATH=src ruff check src/crxzipple/modules/orchestration/application/maintenance.py src/crxzipple/modules/orchestration/application/maintenance_context_budget.py src/crxzipple/modules/orchestration/application/maintenance_compaction_summary.py src/crxzipple/modules/orchestration/application/maintenance_auto_compaction.py src/crxzipple/modules/orchestration/application/maintenance_run_classification.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/orchestration/application/maintenance.py src/crxzipple/modules/orchestration/application/maintenance_context_budget.py src/crxzipple/modules/orchestration/application/maintenance_compaction_summary.py src/crxzipple/modules/orchestration/application/maintenance_auto_compaction.py src/crxzipple/modules/orchestration/application/maintenance_run_classification.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_orchestration_memory.py -k 'compaction or preflight or context_budget' --tb=short --maxfail=1`
-> 6 passed, 13 deselected;
`PYTHONPATH=src pytest -q tests/unit/test_orchestration_context.py::OrchestrationContextTestCase::test_process_next_orchestration_assignment_scales_context_budget_to_llm_context_window --tb=short --maxfail=1`
-> 1 passed.

Orchestration runtime request draft follow-up note:
`application/runtime_llm_request_draft.py` is now a 511-line collector focused on
runtime request fact collection and LLM resolution. Draft DTO/session context and
the skill runtime request resolver port live in `runtime_llm_request_draft_models.py`;
active-session replay-window selection and transcript construction live in
`runtime_llm_request_draft_session.py`; routing input and transcript-policy payload
projection live in `runtime_llm_request_draft_payloads.py`. Current verification:
`PYTHONPATH=src ruff check src/crxzipple/modules/orchestration/application/runtime_llm_request_draft.py src/crxzipple/modules/orchestration/application/runtime_llm_request_draft_models.py src/crxzipple/modules/orchestration/application/runtime_llm_request_draft_session.py src/crxzipple/modules/orchestration/application/runtime_llm_request_draft_payloads.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/orchestration/application/runtime_llm_request_draft.py src/crxzipple/modules/orchestration/application/runtime_llm_request_draft_models.py src/crxzipple/modules/orchestration/application/runtime_llm_request_draft_session.py src/crxzipple/modules/orchestration/application/runtime_llm_request_draft_payloads.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_llm_runtime_request_factory_builder.py tests/unit/test_request_render_input_projection.py --tb=short --maxfail=1`
-> 52 passed;
`PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py::test_engine_carries_context_contract_metadata_for_llm_invocation --tb=short --maxfail=1`
-> 1 passed.

Orchestration worker CLI benchmark follow-up note: `interfaces/worker_cli_benchmark.py`
is now a 593-line benchmark command module. Common benchmark run creation, status
summaries, daemon runtime snapshots, and wait loops live in
`worker_cli_benchmark_common.py`; synthetic tool-IO benchmark LLM adapter, stats, agent
setup, tool source/function registration, and local sleep runtime live in
`worker_cli_benchmark_synthetic.py`. Current verification:
`python -m ruff check src/crxzipple/modules/orchestration/interfaces/worker_cli_benchmark.py src/crxzipple/modules/orchestration/interfaces/worker_cli_benchmark_common.py src/crxzipple/modules/orchestration/interfaces/worker_cli_benchmark_synthetic.py tests/unit/test_orchestration_cli.py --ignore F403,F405`
-> passed;
`python -m compileall -q src/crxzipple/modules/orchestration/interfaces/worker_cli_benchmark.py src/crxzipple/modules/orchestration/interfaces/worker_cli_benchmark_common.py src/crxzipple/modules/orchestration/interfaces/worker_cli_benchmark_synthetic.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_orchestration_cli.py -k 'benchmark_runtime or benchmark_tool_io or benchmark_daemon_runtime' --tb=short --maxfail=1`
-> 6 passed, 26 deselected.

Orchestration executor CLI follow-up note: `interfaces/worker_cli_executor.py` is now
a 425-line production executor command module. Executor benchmark command
registration and lazy benchmark dispatch wrappers live in
`worker_cli_executor_benchmarks.py`, while benchmark execution remains in
`worker_cli_benchmark.py` and its helper modules. The command names are unchanged,
but production executor lifecycle commands no longer share a file with long
benchmark option declarations. Current verification:

`PYTHONPATH=src ruff check src/crxzipple/modules/orchestration/interfaces/worker_cli_executor.py src/crxzipple/modules/orchestration/interfaces/worker_cli_executor_benchmarks.py`
-> passed;

`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/orchestration/interfaces/worker_cli_executor.py src/crxzipple/modules/orchestration/interfaces/worker_cli_executor_benchmarks.py`
-> passed;

`PYTHONPATH=src pytest -q tests/unit/test_app_assembly_architecture.py::test_orchestration_worker_cli_keeps_benchmark_runtime_lazy --tb=short --maxfail=1`
-> 1 passed;

`PYTHONPATH=src pytest -q tests/unit/test_orchestration_cli.py -k 'benchmark_runtime or benchmark_tool_io or benchmark_daemon_runtime' --tb=short --maxfail=1`
-> 6 passed, 26 deselected;

`PYTHONPATH=src pytest -q tests/unit/test_orchestration_cli.py -k 'heartbeat_executor or list_executor_leases or runtime_metrics or heartbeat_assignment or advance_assignment or wait_assignment_on_tool or complete_assignment or fail_assignment' --tb=short --maxfail=1`
-> 2 passed, 30 deselected.

Full `tests/unit/test_orchestration_cli.py` reached 18 passed, then stopped on
`PermissionError: [Errno 1] Operation not permitted` while binding the local sample
LLM HTTP server under this sandbox.

Orchestration persistence follow-up note: `infrastructure/persistence/repositories.py`
is now a 626-line run/wait/ingress/executor-lease repository module. Execution-chain,
execution-step, and execution-step-item SQLAlchemy repositories live in
`execution_chain_repositories.py`; the shared SQLAlchemy UoW imports those concrete
repositories directly from the new module. Current verification:
`python -m ruff check src/crxzipple/modules/orchestration/infrastructure/persistence/repositories.py src/crxzipple/modules/orchestration/infrastructure/persistence/execution_chain_repositories.py src/crxzipple/modules/orchestration/infrastructure/persistence/__init__.py src/crxzipple/shared/infrastructure/sqlalchemy_uow.py tests/unit/test_orchestration_execution_chain.py --ignore F403,F405`
-> passed;
`python -m compileall -q src/crxzipple/modules/orchestration/infrastructure/persistence/repositories.py src/crxzipple/modules/orchestration/infrastructure/persistence/execution_chain_repositories.py src/crxzipple/modules/orchestration/infrastructure/persistence/__init__.py src/crxzipple/shared/infrastructure/sqlalchemy_uow.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_orchestration_execution_chain.py --tb=short --maxfail=1`
-> 32 passed;
`PYTHONPATH=src pytest -q tests/unit/test_orchestration_queue.py tests/unit/test_orchestration_executor_leases.py --tb=short --maxfail=1`
-> 68 passed.

Orchestration coordinator payload follow-up note: `coordinators/progress.py` now
uses shared execution-payload helpers and is 373 lines. `coordinators/waiting.py`
now delegates LLM step summary, continuation payload, tool-run-link projection,
recovery-contract payload construction, terminal tool-run summary projection,
resume-reason policy, and approval replay/recovery to focused helper modules and is
424 lines. Approval replay, replay failure, replayed background-tool wait,
replayed tool-batch materialization, approval resume metadata, terminal tool-run
marking, and approval replay tool-result lookup live in
`coordinators/waiting_approval_recovery.py`. The split keeps the old behavior
differences explicit: progress includes provider continuation state and assistant
progress text; waiting includes `llm_invocation_id` in its LLM step summary.
Current verification:
`PYTHONPATH=src ruff check src/crxzipple/modules/orchestration/application/coordinators/progress.py src/crxzipple/modules/orchestration/application/coordinators/waiting.py src/crxzipple/modules/orchestration/application/coordinators/waiting_approval_recovery.py src/crxzipple/modules/orchestration/application/coordinators/execution_payloads.py src/crxzipple/modules/orchestration/application/coordinators/waiting_recovery_payloads.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/orchestration/application/coordinators/progress.py src/crxzipple/modules/orchestration/application/coordinators/waiting.py src/crxzipple/modules/orchestration/application/coordinators/waiting_approval_recovery.py src/crxzipple/modules/orchestration/application/coordinators/execution_payloads.py src/crxzipple/modules/orchestration/application/coordinators/waiting_recovery_payloads.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_orchestration_execution_chain.py`
-> 32 passed;
`PYTHONPATH=src pytest -q tests/unit/test_orchestration_tools.py tests/unit/test_orchestration_context.py tests/unit/test_orchestration_context_workspace_snapshot.py`
-> 92 passed;
`PYTHONPATH=src pytest -q tests/unit/test_orchestration_memory.py tests/unit/test_request_render_input_projection.py`
-> 22 passed.
`PYTHONPATH=src pytest -q tests/unit/test_orchestration_approval.py tests/unit/test_orchestration_tools.py tests/unit/test_orchestration_execution_chain.py --tb=short --maxfail=1`
-> 86 passed.

Orchestration engine session recorder follow-up note:
`application/engine_session_recorder.py` is now a 479-line session-write
coordinator. Tool result session item construction, provider replay envelope
projection, model-facing tool error guidance, session metadata filtering, terminal
tool-run text, and background tool execution-step reference resolution live in
`engine_session_tool_results.py`. This keeps the recorder focused on when to write
inbound, LLM response, tool-call, and tool-result session records rather than
owning the payload projection rules. Current verification:

`PYTHONPATH=src ruff check src/crxzipple/modules/orchestration/application/engine_session_recorder.py src/crxzipple/modules/orchestration/application/engine_session_tool_results.py`
-> passed;

`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/orchestration/application/engine_session_recorder.py src/crxzipple/modules/orchestration/application/engine_session_tool_results.py`
-> passed;

`PYTHONPATH=src pytest -q tests/unit/test_orchestration_execution_chain.py::test_background_tool_result_message_uses_execution_item_reference --tb=short --maxfail=1`
-> 1 passed;

`PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py::test_session_adapter_renders_tool_result_envelope_refs --tb=short --maxfail=1`
-> 1 passed;

`PYTHONPATH=src pytest -q tests/unit/test_runtime_transcript.py -k tool_result_envelope --tb=short --maxfail=1`
-> 1 passed, 15 deselected.

LLM follow-up note: the provider message projection compatibility facade and the monolithic
`domain/value_objects.py` have both been retired. Provider renderers now import focused
common/provider-specific projection modules directly, and LLM domain values are split into
focused enum/profile/message/result/response/continuation/error modules. This keeps the
provider boundary explicit without adding a compatibility double track. The LLM application
facade now also synchronizes credential provider reassignment into profile validation and
adapter request building, so runtime credential resolution and profile registration do not
drift after service construction. Error family/retryable classification now lives in
`llm/application/error_classification.py`; Operations LLM error projections consume that
owner classification instead of duplicating provider failure semantics.

Session follow-up note: `SessionApplicationService` no longer owns session entity/instance
construction, runtime binding metadata/payload projection, instance binding sync, instance
existence checks, sequence calculation, or session-kind inference. These live in
`session_instance_lifecycle.py`, keeping the service focused on UoW-backed use-case
coordination.

Events follow-up note: Trace topic discovery now lives in `read_models/trace_topics.py`,
and event console stream/read helpers now live in `interfaces/http_console.py`. The Events
HTTP router remains responsible for route parsing, service lookup, high-level diagnostics
wiring, and stream wiring only. Topic/subscription diagnostics payload helpers now live in
`interfaces/http_diagnostics.py`.

Core config follow-up note: `core/config.py` remains the public Settings/load entrypoint,
but is now a thin export surface. Default runtime paths live in `config_paths.py`,
the immutable `Settings` model lives in `config_settings.py`, and environment-driven
Settings construction lives in `config_loader.py`. Browser profile value objects
and environment parsing are split into `config_browser_models.py` and
`config_browser_loader.py`. LLM profile/request-default value objects and
environment/file parsing are split into `config_llm_profile_models.py` and
`config_llm_profile_loader.py`. Channel profile environment/file parsing is split
into `config_channel_profile_loader.py`. Agent profile value objects and
environment/file/default merge parsing are split into `config_agent_profile_models.py`
and `config_agent_profile_loader.py`. Mobile device value objects and JSON env
parsing are split into `config_mobile_models.py` and `config_mobile_loader.py`.
Runtime persistence guards, environment coercion helpers, Events backend/Redis parsing, Authorization policy/runtime-path parsing,
browser profile parsing, browser runtime parsing,
mobile device parsing, Tool OpenAPI/MCP provider parsing, Tool runtime/worker parsing,
LLM profile/request-default parsing, Agent profile parsing, Channel profile parsing,
Artifact storage/budget parsing, Prompt budget parsing, Orchestration runtime parsing,
OCR backend/host/base-url parsing, Memory retrieval/vector parsing, Sandbox parsing,
and logging parsing now live in focused `core/config_*` modules. This keeps runtime
configuration behavior stable without letting the public Settings module own every
adapter and environment parsing detail. Tool provider config is also split by
public export surface, provider models, MCP env parsing, OpenAPI provider parsing,
and OpenAPI credential binding validation.
The public entrypoint has been reduced from the original 2420-line aggregate to a
79-line export surface; the current Settings loader is isolated in a 304-line
composition helper.
Verification:
`PYTHONPATH=src ruff check src/crxzipple/core/config_mobile.py src/crxzipple/core/config_mobile_loader.py src/crxzipple/core/config_mobile_models.py src/crxzipple/core/config_loader.py src/crxzipple/core/config_settings.py tests/unit/test_config.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/core/config_mobile.py src/crxzipple/core/config_mobile_loader.py src/crxzipple/core/config_mobile_models.py src/crxzipple/core/config_loader.py src/crxzipple/core/config_settings.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_config.py::ConfigTestCase::test_load_settings_reads_mobile_device_specs --tb=short --maxfail=1`
-> 1 passed;
`PYTHONPATH=src ruff check src/crxzipple/core/config_agent_profiles.py src/crxzipple/core/config_agent_profile_loader.py src/crxzipple/core/config_agent_profile_models.py src/crxzipple/core/config_loader.py src/crxzipple/core/config_settings.py tests/unit/test_config.py tests/unit/test_agent_settings_integration.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/core/config_agent_profiles.py src/crxzipple/core/config_agent_profile_loader.py src/crxzipple/core/config_agent_profile_models.py src/crxzipple/core/config_loader.py src/crxzipple/core/config_settings.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_agent_settings_integration.py --tb=short --maxfail=1`
-> 5 passed;
`PYTHONPATH=src ruff check src/crxzipple/core/config_channel_profiles.py src/crxzipple/core/config_channel_profile_loader.py src/crxzipple/core/config_loader.py tests/unit/test_config.py tests/unit/test_channel_memory_runtime_settings_integration.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/core/config_channel_profiles.py src/crxzipple/core/config_channel_profile_loader.py src/crxzipple/core/config_loader.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_config.py::ConfigTestCase::test_load_settings_reads_channel_profiles_from_config_files tests/unit/test_channel_memory_runtime_settings_integration.py --tb=short --maxfail=1`
-> 8 passed;
`PYTHONPATH=src ruff check src/crxzipple/core/config_llm_profiles.py src/crxzipple/core/config_llm_profile_loader.py src/crxzipple/core/config_llm_profile_models.py src/crxzipple/core/config_settings.py src/crxzipple/core/config_loader.py tests/unit/test_config.py tests/unit/test_llm_http.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/core/config_llm_profiles.py src/crxzipple/core/config_llm_profile_loader.py src/crxzipple/core/config_llm_profile_models.py src/crxzipple/core/config_settings.py src/crxzipple/core/config_loader.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_config.py::ConfigTestCase::test_load_settings_reads_llm_profile_concurrency_limits tests/unit/test_llm_http.py::LlmHttpTestCase::test_llm_sync_profiles_endpoint_loads_configured_profiles tests/unit/test_llm_http.py::LlmHttpTestCase::test_llm_sync_profiles_endpoint_ignores_legacy_settings_resources --tb=short --maxfail=1`
-> 3 passed;
`PYTHONPATH=src ruff check src/crxzipple/core/config_browser.py src/crxzipple/core/config_browser_loader.py src/crxzipple/core/config_browser_models.py src/crxzipple/core/config_settings.py src/crxzipple/core/config_loader.py tests/unit/test_config.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/core/config_browser.py src/crxzipple/core/config_browser_loader.py src/crxzipple/core/config_browser_models.py src/crxzipple/core/config_settings.py src/crxzipple/core/config_loader.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_config.py::ConfigTestCase::test_load_settings_reads_browser_profile_fields tests/unit/test_config.py::ConfigTestCase::test_load_settings_rejects_removed_browser_profile_runtime_fields tests/unit/test_config.py::ConfigTestCase::test_load_settings_rejects_static_browser_proxy_credentials tests/unit/test_config.py::ConfigTestCase::test_load_settings_reads_browser_runtime_fields tests/unit/test_config.py::ConfigTestCase::test_load_settings_uses_sandbox_image_for_empty_browser_sandbox_image --tb=short --maxfail=1`
-> 5 passed;
`PYTHONPATH=src ruff check src/crxzipple/core/config.py src/crxzipple/core/config_loader.py src/crxzipple/core/config_paths.py src/crxzipple/core/config_settings.py tests/unit/test_config.py tests/unit/test_tool_cli.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/core/config.py src/crxzipple/core/config_loader.py src/crxzipple/core/config_paths.py src/crxzipple/core/config_settings.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_config.py tests/unit/test_access_migration.py::AccessMigrationTests::test_thin_container_adapter_only_collects_snapshots tests/unit/test_tool_cli.py::ToolCliTestCase::test_tool_roots_do_not_discover_legacy_filesystem_tools --tb=short --maxfail=1`
-> 38 passed;
`PYTHONPATH=src pytest -q tests/unit/test_logger.py tests/unit/test_sandbox_backend.py tests/unit/test_artifacts_http.py tests/unit/test_channel_memory_runtime_settings_integration.py tests/unit/test_settings_materialization.py --tb=short --maxfail=1`
-> 28 passed;
`PYTHONPATH=src ruff check src/crxzipple/core/config_tool_providers.py src/crxzipple/core/config_tool_provider_models.py src/crxzipple/core/config_tool_mcp_providers.py src/crxzipple/core/config_tool_openapi_providers.py src/crxzipple/core/config_tool_openapi_credentials.py tests/unit/test_config.py tests/unit/test_tool_providers.py tests/unit/test_openapi_access.py tests/unit/test_tool_mcp_client.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/core/config_tool_providers.py src/crxzipple/core/config_tool_provider_models.py src/crxzipple/core/config_tool_mcp_providers.py src/crxzipple/core/config_tool_openapi_providers.py src/crxzipple/core/config_tool_openapi_credentials.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_config.py::ConfigTestCase::test_load_settings_reads_remote_tool_concurrency_limits tests/unit/test_config.py::ConfigTestCase::test_load_settings_reads_http_mcp_provider tests/unit/test_openapi_access.py tests/unit/test_tool_mcp_client.py -k 'not http_client_initializes_lists_and_calls_tools' --tb=short --maxfail=1`
-> 12 passed, 1 deselected;
`PYTHONPATH=src pytest -q tests/unit/test_tool_providers.py -k 'not discovers_and_executes_openapi_remote_tools and not mcp_http' --tb=short --maxfail=1`
-> 21 passed, 1 deselected;
The deselected MCP HTTP client and OpenAPI remote execution cases require binding
a local HTTP server, which the current sandbox denies with `PermissionError`.
`PYTHONPATH=src ruff check src/crxzipple/core/config.py src/crxzipple/core/config_authorization.py tests/unit/test_config.py tests/unit/test_authorization.py tests/unit/test_auth_http.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/core/config.py src/crxzipple/core/config_authorization.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_config.py::ConfigTestCase::test_load_settings_reads_authorization_policy_paths tests/unit/test_auth_http.py tests/unit/test_authorization.py --tb=short --maxfail=1`
-> 26 passed;
`PYTHONPATH=src ruff check src/crxzipple/core/config*.py tests/unit/test_config.py tests/unit/test_logger.py tests/unit/test_sandbox_backend.py tests/unit/test_artifacts_http.py tests/unit/test_settings_materialization.py tests/unit/test_channel_memory_runtime_settings_integration.py tests/unit/test_authorization.py tests/unit/test_auth_http.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/core`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_config.py tests/unit/test_logger.py tests/unit/test_sandbox_backend.py tests/unit/test_artifacts_http.py tests/unit/test_serve_cli.py tests/unit/test_channel_memory_runtime_settings_integration.py tests/unit/test_settings_materialization.py tests/unit/test_ocr_service.py tests/unit/test_ocr_http.py tests/unit/test_ocr_host_http.py tests/unit/test_ocr_infrastructure.py tests/unit/test_memory_http.py tests/unit/test_auth_http.py tests/unit/test_authorization.py --tb=short --maxfail=1`
-> 117 passed;
`PYTHONPATH=src pytest -q tests/unit/test_config.py tests/unit/test_logger.py tests/unit/test_sandbox_backend.py tests/unit/test_artifacts_http.py tests/unit/test_serve_cli.py tests/unit/test_channel_memory_runtime_settings_integration.py tests/unit/test_settings_materialization.py tests/unit/test_ocr_service.py tests/unit/test_ocr_http.py tests/unit/test_ocr_host_http.py tests/unit/test_ocr_infrastructure.py tests/unit/test_memory_http.py tests/unit/test_auth_http.py tests/unit/test_authorization.py tests/unit/test_access_migration.py --tb=short --maxfail=1`
-> 121 passed;
`PYTHONPATH=src pytest -q tests/unit/test_config.py tests/unit/test_logger.py tests/unit/test_sandbox_backend.py tests/unit/test_artifacts_http.py tests/unit/test_serve_cli.py tests/unit/test_channel_memory_runtime_settings_integration.py tests/unit/test_settings_materialization.py tests/unit/test_ocr_service.py tests/unit/test_ocr_http.py tests/unit/test_ocr_host_http.py tests/unit/test_ocr_infrastructure.py tests/unit/test_memory_http.py tests/unit/test_auth_http.py tests/unit/test_authorization.py tests/unit/test_access_migration.py tests/unit/test_agent_settings_integration.py --tb=short --maxfail=1`
-> 126 passed;
`PYTHONPATH=src ruff check src/crxzipple/core/config.py src/crxzipple/core/config_artifacts.py tests/unit/test_config.py tests/unit/test_artifacts_http.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/core/config.py src/crxzipple/core/config_artifacts.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_config.py::ConfigTestCase::test_load_settings_reads_artifact_llm_budget_overrides tests/unit/test_artifacts_http.py --tb=short --maxfail=1`
-> 6 passed;
`PYTHONPATH=src ruff check src/crxzipple/core/config.py src/crxzipple/core/config_prompt.py src/crxzipple/core/config_orchestration_runtime.py tests/unit/test_config.py tests/unit/test_channel_memory_runtime_settings_integration.py tests/unit/test_settings_materialization.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/core/config.py src/crxzipple/core/config_prompt.py src/crxzipple/core/config_orchestration_runtime.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_config.py tests/unit/test_channel_memory_runtime_settings_integration.py tests/unit/test_settings_materialization.py --tb=short --maxfail=1`
-> 48 passed;
`PYTHONPATH=src ruff check src/crxzipple/core/config.py src/crxzipple/core/config_browser_runtime.py tests/unit/test_config.py tests/unit/test_browser_cdp_control.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/core/config.py src/crxzipple/core/config_browser_runtime.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_config.py::ConfigTestCase::test_load_settings_reads_browser_runtime_fields tests/unit/test_config.py::ConfigTestCase::test_load_settings_uses_sandbox_image_for_empty_browser_sandbox_image tests/unit/test_config.py::ConfigTestCase::test_load_settings_reads_browser_profile_fields tests/unit/test_config.py::ConfigTestCase::test_load_settings_rejects_removed_browser_profile_runtime_fields --tb=short --maxfail=1`
-> 4 passed;
`PYTHONPATH=src ruff check src/crxzipple/core/config.py src/crxzipple/core/config_logging.py src/crxzipple/core/config_sandbox.py tests/unit/test_config.py tests/unit/test_logger.py tests/unit/test_sandbox_backend.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/core/config.py src/crxzipple/core/config_logging.py src/crxzipple/core/config_sandbox.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_config.py::ConfigTestCase::test_load_settings_reads_sandbox_environment tests/unit/test_logger.py::LoggerTestCase::test_load_settings_reads_logging_environment tests/unit/test_sandbox_backend.py --tb=short --maxfail=1`
-> 5 passed;
`PYTHONPATH=src ruff check src/crxzipple/core/config.py src/crxzipple/core/config_tool_runtime.py tests/unit/test_config.py tests/unit/test_daemon_manager.py tests/unit/test_tool_cli.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/core/config.py src/crxzipple/core/config_tool_runtime.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_config.py tests/unit/test_daemon_manager.py -k 'tool_worker or config or events_backend or serve' tests/unit/test_tool_cli.py -k 'worker or tool_worker' --tb=short --maxfail=1`
-> 13 passed, 61 deselected;
`PYTHONPATH=src pytest -q tests/unit/test_config.py tests/unit/test_serve_cli.py tests/unit/test_ocr_service.py tests/unit/test_ocr_http.py tests/unit/test_ocr_host_http.py tests/unit/test_ocr_infrastructure.py tests/unit/test_memory_http.py --tb=short --maxfail=1`
-> 60 passed;
`PYTHONPATH=src pytest -q tests/unit/test_daemon_manager.py -k 'tool_worker or events_backend' tests/unit/test_tool_cli.py -k 'worker or tool_worker' --tb=short --maxfail=1`
-> 9 passed, 33 deselected;
`PYTHONPATH=src ruff check src/crxzipple/core/config.py src/crxzipple/core/config_events.py src/crxzipple/core/config_ocr.py src/crxzipple/core/config_memory.py tests/unit/test_config.py tests/unit/test_serve_cli.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/core/config.py src/crxzipple/core/config_events.py src/crxzipple/core/config_ocr.py src/crxzipple/core/config_memory.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_config.py tests/unit/test_serve_cli.py tests/unit/test_events.py -k 'not redis_events_backend' --tb=short --maxfail=1`
-> 67 passed, 5 deselected;
`PYTHONPATH=src pytest -q tests/unit/test_config.py tests/unit/test_serve_cli.py --tb=short --maxfail=1`
-> 37 passed;
`PYTHONPATH=src ruff check src/crxzipple/core/config.py src/crxzipple/core/config_ocr.py src/crxzipple/core/config_memory.py tests/unit/test_config.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/core/config.py src/crxzipple/core/config_ocr.py src/crxzipple/core/config_memory.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_config.py tests/unit/test_ocr_service.py tests/unit/test_ocr_http.py tests/unit/test_ocr_host_http.py tests/unit/test_ocr_infrastructure.py tests/unit/test_memory_http.py --tb=short --maxfail=1`
-> 55 passed;
`python -m ruff check src/crxzipple/core/config.py src/crxzipple/core/config_agent_profiles.py src/crxzipple/core/config_browser.py src/crxzipple/core/config_channel_profiles.py src/crxzipple/core/config_env.py src/crxzipple/core/config_llm_profiles.py src/crxzipple/core/config_mobile.py src/crxzipple/core/config_runtime_guards.py src/crxzipple/core/config_tool_providers.py tests/unit/test_config.py tests/unit/test_agent_settings_integration.py tests/unit/test_channel_memory_runtime_settings_integration.py tests/unit/test_llm_settings_integration.py tests/unit/test_tool_access_architecture.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_config.py tests/unit/test_serve_cli.py tests/unit/test_agent_settings_integration.py tests/unit/test_channel_memory_runtime_settings_integration.py tests/unit/test_llm_settings_integration.py tests/unit/test_tool_access_architecture.py --tb=short --maxfail=1`
-> 62 passed;
`PYTHONPATH=src pytest -q tests/unit/test_config.py tests/unit/test_serve_cli.py --tb=short --maxfail=1`
-> 37 passed;
`PYTHONPATH=src pytest -q tests/unit/test_openapi_access.py tests/unit/test_tool_access_architecture.py --tb=short --maxfail=1`
-> 17 passed;
`PYTHONPATH=src pytest -q tests/unit/test_tool_providers.py -k 'not discovers_and_executes_openapi_remote_tools' --tb=short --maxfail=1`
-> 21 passed, 1 deselected;
`PYTHONPATH=src pytest -q tests/unit/test_llm.py tests/unit/test_llm_adapters.py tests/unit/test_llm_settings_integration.py --tb=short --maxfail=1`
-> 118 passed;
`PYTHONPATH=src pytest -q tests/unit/test_llm_http.py -k 'not openai_compatible_adapter and not current_form' --tb=short --maxfail=1`
-> 7 passed, 2 deselected;
`PYTHONPATH=src pytest -q tests/unit/test_config.py tests/unit/test_agent_settings_integration.py --tb=short --maxfail=1`
-> 37 passed;
`PYTHONPATH=src pytest -q tests/unit/test_config.py tests/unit/test_channel_memory_runtime_settings_integration.py --tb=short --maxfail=1`
-> 39 passed. The deselected Tool provider, MCP HTTP client, and LLM HTTP
adapter tests require binding a local HTTP server, which the current sandbox denies with
`PermissionError`.

Channels follow-up note: Shared HTTP request/response DTOs now live in
`interfaces/http_models.py`; shared profile/account/access helpers live in
`interfaces/http_channel_helpers.py`; Lark event verification/decryption and route
handling live in `interfaces/http_lark_events.py`; and the Web channel SSE stream
endpoint, stream-only DTOs, direct live/observe projection, broadcast target matching,
and SSE formatting live in `interfaces/http_web_events.py`. Webhook inbound signature
validation and route handling live in `interfaces/http_webhook_inbound.py`. The duplicate
unused Lark message normalization implementation in the HTTP layer has been retired;
runtime normalization stays in `application/lark_messages.py`. Common runtime helper
values/functions live in `application/runtime_helpers.py`, and the Web runtime service
now lives in `application/web_runtime.py`. The Webhook runtime service now lives in
`application/webhook_runtime.py`. The Lark runtime service now lives in
`application/lark_runtime.py`. Transport-neutral observe cursor/status/settled-state
helpers live in `application/runtime_observation.py`, and Lark session-message observation
payload projection lives in `application/lark_runtime_observation.py`. Lark outbound
observe delivery payload building, artifact upload, and send calls live in
`application/lark_runtime_delivery.py`. Lark tenant-token and bot identity lookup/cache
live in `application/lark_runtime_identity.py`. Lark long-connection thread/SDK ingress
lives in `application/lark_runtime_long_connection.py`. Lark message-to-run submission,
reply-address construction, interaction upsert, and orchestration turn submission live in
`application/lark_runtime_submission.py`. Dead-letter query/replay HTTP shaping lives in
`interfaces/http_dead_letters.py`. The main Channels HTTP router still owns profile,
runtime, and subscription route control flow.

## Wave 2. Operations And UI Projection Cleanup

Purpose: make Operations/Workbench fast and truthful.

| Task | Modules | Acceptance |
| --- | --- | --- |
| Split Operations read model hotspots | operations | Current hotspot wave complete for Tool, LLM, LLM invocation detail projection, Orchestration, Events, Daemon, Channels, Skills, Browser, Memory, Access, module fallback overview, Tool scheduling, Context Workspace, loop-regression diagnostics, Operations persistence stores, Operations observation repository mapping/recording helpers, Operations action-flow helpers, Operations projection materializer routing/payload helpers, Operations projection read-payload/table-filter helpers, Skills table aggregate retirement, Skills event source split, Memory event-table/source-table/health-summary-chart split, Daemon process-table split, Daemon page builder/fact split, Daemon event source split, LLM page tab split, LLM overview action split, Events event detail split, Events overview navigation/contract split, Events page projection split, Operations factory context split, Tool readiness risk split, Tool readiness payload split, Tool worker projection split, Tool worker detail section split, Tool Run detail summary/projection split, Tool Run artifact ref split, Tool Run table label/source/execution split, Tool Run query/time split, Tool lifecycle event projection split, Channels table row/section split, Channels chart/runtime-record/page-summary split, Channels event-record split, Channels detail split, Orchestration status projection split, Orchestration overview/page split, Orchestration ingress state/row/projection split, Orchestration event-log row split, Orchestration worker projection split, Browser common/profile-row/page-filter/page-source/table helper split, Events page fact split, LLM overview/page/facts split, LLM provider request label split, LLM provider readiness split, LLM invocation table row/row-family split, LLM invocation detail item split, LLM invocation request-context item split, Daemon process output detail split, Daemon table row split, Daemon service row split, Daemon chart/drain/common-semantic split, read-model port contract split, LLM lifecycle event split, LLM lifecycle bus split, Events dead-letter table split, Events overview/page split, Operations DTO surface, Operations observation model/event projection, Events overview chart/owner/navigation/contract sections, Tool lifecycle event sources/rows/projection, Tool Run table facts/rows/query/time/detail projection, Tool overview aggregate sections, Tool tab projection, Tool overview/page/facts split, Tool page section wiring, Channels common/event/section/safe-access helpers, Operations observer runtime split, Orchestration execution-chain section/query/diagnostics/row split, Orchestration summary metric/tab projection split, and Operations HTTP interface. Tool Source aggregate sections, catalog rows, and provider backend row projection, Tool Run detail assignment/payload/browser/projection helpers, Tool Run artifact/result parsing helpers, Tool Run table label/source/execution helpers, Tool Run query normalization/pagination/time helpers, Tool lifecycle event priority/tone/details/source/trace helpers, Tool runtime policy metrics, Tool scheduling labels/blockers/run projection/section aggregate, Tool provider limiter facts/snapshots/local-capacity/rows, Tool readiness source/fallback logic, Tool worker detail assembly, Tool worker run projection, Access fallback inventory/readiness and target-row projection, LLM overview/page assembly, overview row projection, page tab projection, page action definitions, and page fact collection, LLM invocation streaming/recent/failed/status row projection, LLM detail response/policy/event/request-context tables, LLM provider context mapping, Orchestration page DTO/ports/overview/page assembly, Orchestration ingress source/status/dispatch/trace/action/age helpers, Orchestration policy/stuck-run sections, Events aggregate state/overview/page assembly, event detail projection, contract matching, page health/topic-selection projection, and topic state, Daemon runtime facts/filter/page helpers, page assembly, page fact collection, event source collection, and Browser Host instance summary projection, Operations factory context DTO, Browser profile/page row/filter/source/table projection, Channels formatting/helpers/details/runtime records/page summary/table section projection, and Skills page facts/event sources have also been split out of their page facades. Current Operations read-model scan has no file above 250 lines, and `test_operations_read_model_files_remain_focused` now enforces that boundary; remaining work is ongoing production query-budget hardening and broad verification. |
| Split Workbench timeline projector | workbench | Complete: timeline refs/sorting, visibility/debug suppression, LLM response item projection, tool lifecycle entry projection, tool result content projection, tool interaction merge, step LLM views, step tool views, and step support views now live in focused modules behind stable Workbench projector facades |
| Add golden timeline tests | workbench | Complete: long-chain golden fixture locks stable timeline order, labels, source refs, duplicate assistant progress suppression, debug continuation suppression, and sanitized tool evidence payloads |
| Add projection freshness metrics | operations | Each module page exposes projection updated_at/staleness |
| Keep frontend data source discipline | frontend, operations | Operations pages consume `/operations/{module}` only |

Operations LLM invocation streaming follow-up: streaming id extraction and
profile capability detection now live in `llm_invocation_streaming.py`, while
`llm_invocation_filters.py` keeps query normalization, filtering, pagination,
empty-state text, search text, and de-duplication only.
LLM page invocation active/failed/filter/visible/streaming/detail set
derivation now lives in `llm_page_invocation_sets.py`; `llm_page_facts.py`
keeps owner reads, cross-owner context collection, health wiring, response-event
detail loading, and final fact DTO assembly.
Tool scheduling queue summary row projection and Waiting IO row selection now
live in `tool_scheduling_queue_rows.py`; `tool_scheduling_queue_sections.py`
keeps queue-related table shells, columns, routes, and empty states only.
LLM run context execution-owner lookup and summary payload projection now lives
in `llm_run_context_execution.py`; `llm_run_contexts.py` keeps invocation
runtime context fallback and runtime/execution context merging only.
LLM resolver replay-window, optional-int, and text label helpers now live in
`llm_resolver_labels.py`; `llm_resolver_sections.py` keeps resolver run mapping,
bucket/chart semantics, and resolver facts section assembly only.
Orchestration runtime bootstrap config parsing and policy display labels now
live in `orchestration_runtime_config_projection.py`; status projection keeps
scheduler/dispatch/observer duration and queue status labels only.

Operations Orchestration page follow-up: page section aggregation now lives in
`orchestration_page_sections.py`; `orchestration_page_builder.py` keeps the
page shell, action wiring, projection diagnostics, and final DTO construction
only.

Operations read-model follow-up: repeated-failure/repeated-probe table row
projection now lives in `orchestration_failure_rows.py`, leaving
`orchestration_failure_sections.py` as the section shell. Access target status,
check, metadata, setup-flow, usage, event matching, and search projection now
live in `access_target_projection.py`; `access_common.py` keeps shared display
labels/tone helpers only, and scalar/list/dict normalization remains in
`access_values.py`.

Operations LLM detail follow-up: request-context key-value projection is now
grouped by runtime/replay/tool-result/artifact facts in
`llm_invocation_request_context_runtime_items.py` and provider wire/renderer
facts in `llm_invocation_request_context_provider_items.py`; the original
`llm_invocation_request_context_items.py` keeps only the stable display order.
LLM error detail facts now live in `llm_error_fact_items.py`, while
`llm_error_sections.py` owns only the failed-invocation summary table.
Provider renderer/render-report/tool-mapping labels now live in
`llm_provider_render_labels.py`; `llm_provider_request_labels.py` keeps request
continuation, transport, input delta, input item, tool count, option, and
continuation-fallback labels.
Tool worker detail summary and runtime registry table now live in
`tool_worker_detail_summary.py` and `tool_worker_runtime_sections.py`, leaving
`tool_worker_detail_sections.py` focused on capability key-value projection.

Operations HTTP DTO follow-up: LLM invocation detail responses and Daemon
instance/lease/process detail responses now live in focused detail DTO modules;
the LLM and Daemon page response modules keep page-shaped DTOs only.

Operations LLM follow-up: overview queue/profile/context rows now live in
`llm_overview_rows.py`; `llm_overview_sections.py` keeps health and page metric
card projection only.

Operations Skills follow-up: profile usage table projection now lives in
`skills_profile_usage_table.py`, keeping `skills_catalog_tables.py` focused on
installed skills, package sources, and conflict/override catalog tables.

Operations Orchestration ingress follow-up: display, dispatch, tone, trace, and
age row-value helpers now live in `orchestration_ingress_row_values.py`;
`orchestration_ingress_projection.py` keeps ingress source, lane, and priority
projection only.

Operations Tool Source follow-up: Provider Backend table row projection and 24h
run count aggregation now live in `tool_source_provider_backend_rows.py`;
credential/readiness/runtime labels and tone rules live in
`tool_source_provider_backend_labels.py`; `tool_source_provider_sections.py`
keeps column and section shell ownership only.
Tool Source CLI process-health row projection now lives in
`tool_source_cli_rows.py`; `tool_source_catalog_rows.py` keeps source health,
discovery failure, and function catalog risk row projection only.

Operations HTTP projection routing follow-up: the former 406-line
`http_projection_routes.py` has been reduced to a 23-line composition module.
Operations read-model follow-up: Tool provider limit projection is now split
between the global provider-limit section and the worker-detail provider-limit
section; worker detail assembly no longer routes through the global
`tool_provider_limits.py` section owner.
Runtime module page routes, support module page routes, detail routes, and
overview/generic routes now live in focused route groups while preserving the
same `/operations/*` API.

Operations support-page HTTP DTO follow-up: the former 388-line
`http_models_support_pages.py` has been reduced to a 23-line export module.
Access, Memory, and Skills page response models now live in focused DTO modules
behind the existing HTTP model export surface.

Operations core HTTP DTO follow-up: the former 363-line `http_models_core.py`
has been reduced to a 49-line export module. Core primitives, diagnostics,
section DTOs, and page/overview DTOs now live in focused model modules behind
the existing HTTP model export surface.

Operations action route follow-up: resource routes are now split into Skills,
Access, Daemon/Memory, and Audit route groups; execution routes are now split
into LLM, Orchestration, and Tool route groups. The former resource and
execution route files are thin composition modules.

Operations read-model follow-up: Skills usage aggregation, Daemon module
overview rows, Events module overview rows, and LLM provider warmup event
projection now live in focused helper modules. Page/section files keep assembly
and owner-fact consumption; row selection, usage aggregation, and warmup
next-action rules are no longer mixed into generic provider/page sections.

Workbench follow-up note: linked entity details are now split by owner concern.
`entity_details.py` keeps the public detail facade and shared summary projection;
LLM invocation detail payloads live in focused LLM/provider/replay helpers, Tool
run detail payloads live in a Tool helper, and common enum/time/bounded-value
normalization lives in `entity_detail_values.py`.

Workbench step follow-up note: `step_projector.py` now routes between
execution-chain projection and a focused direct/fallback step projection path.
Direct tool, terminal, access, approval, queue, and LLM fallback step assembly
live in dedicated helpers, keeping the projector itself as the read-model route
coordinator.

Workbench execution/LLM follow-up note: execution-chain helpers are split into
bundle reads, status/timestamp projection, summary payload extraction, and
owner-reference projection. LLM step projection now delegates assistant
progress and continuation-decision step assembly to focused helpers, leaving
the main LLM step view module responsible for the core LLM step only.

Workbench action follow-up note: action projection is split into trace/entity
link construction, approval action construction, and run/step action
composition. The public action projection module now only coordinates
Workbench action groups.

Workbench inspector follow-up note: inspector loop-health calculation and
linked-asset projection are split into focused helpers. `inspector_projector.py`
now assembles Inspector sections and quick actions without owning diagnostic
baseline building or owner-asset traversal.

Workbench run-summary follow-up note: the former mixed run-summary aggregate has
been retired. Run identity, time, status/approval state, display key-values,
instruction/output text, LLM summary, and metrics now live in focused projection
modules, and Workbench callers import the narrow concern they need instead of a
catch-all summary module.

Workbench HTTP follow-up note: the Workbench interface root has been split into
catalog, context tree/snapshot, linked-entity, trace, and core run/turn route
modules. The root router now composes route groups and keeps only Workbench
run/turn and request-preview endpoints.

Context Workspace integration follow-up note: session context tree evidence
normalization, tool interaction lifecycle classification, block/content
formatting, tool-result content normalization, execution-step node projection,
segment seed/range/value helpers, session message node projection, item/tool-call
pairing, consumed tool-history folding, tool-interaction node projection, and
tool-interaction summary formatting are split out of the large app-integration
session adapter. Execution-summary consumption boundary and tool-lifecycle fact
projection now live in `context_workspace_session_execution_facts.py`. The adapter
still maps Session owner facts to Context Tree child resolution, while pure projection
rules live in focused helpers. Active segment current-item range seed construction now
lives beside message/item projection in `context_workspace_session_item_nodes.py`.
Session segments root seed construction now lives with segment seed projection in
`context_workspace_session_segments.py`. Current-turn steps root seed construction now
lives with execution step projection in `context_workspace_session_execution.py`.
Historical segment range paging, range-limit notices, range-item budget checks, and
current item/tool-history message projection now live in segment/item projection
helpers instead of the session adapter. Session owner reads, instance lookup, and
transcript window queries now live in `context_workspace_session_reader.py`, leaving
the adapter as the Context Tree child-routing coordinator.
The orchestration-side tool-schema bootstrap integration has also been split:
the public bootstrap entry coordinates draft/default metadata only, while
catalog-backed default selection, Context Tree fallback projection, Context Tree
node expansion, and tool-schema group-ref parsing live in focused helpers. This
keeps tool visibility selection generic and rooted in Context Workspace state,
without creating task-specific evidence gates or provider-specific runtime
branches.
Request snapshot metadata and tool-schema mirror integration are now split by
projection concern as well: provider attachments, session node refs, draft
transcript/protocol-required refs, metadata normalization, Context Slice schema
projection, request schema selection, and Context Tree node synchronization are
separate helpers behind stable adapter/facade entrypoints.
The follow-up split keeps this boundary sharper: individual Context Slice input
payload construction, requested tool-schema parent-node expansion, run
runtime-context text projection, tool-schema snapshot metadata, and artifact
snapshot metadata now live in focused helpers behind the same public integration
entrypoints.
Current inbound input detection/projection, projected input item merge/dedupe,
tool schema node identity/source-id derivation, and request-render timing/cost
attachment have also been split out of the hot path coordinators. The remaining
large `request_render_snapshot_pipeline.py` is intentionally kept as the visible
phase coordinator rather than split into an opaque facade chain.
The request-render pipeline has since been narrowed further by moving draft input
selection, requested/visible tool-schema selection, control/context slice
build-input construction, and slice projection bundling into focused helpers.
The pipeline still owns the observable phase sequence and persistence handoff.
Metadata bundle assembly, final request-render record DTO assembly,
request-render tool-schema metadata, and context snapshot persistence payload
construction are now separated as well. This keeps request rendering explicit
without making the pipeline own every DTO field.
Request-render workspace binding, persisted request-render snapshot recorder
payloads, and full context-snapshot draft-input metadata have also been split
out. The current request-render pipeline remains the observable coordinator,
while stable request input, slice, tool-schema, workspace, metadata, record, and
persistence payload concerns live in dedicated helpers.
Session adapter execution-facts verification:
`PYTHONPATH=src ruff check src/crxzipple/app/integration/context_workspace_session.py src/crxzipple/app/integration/context_workspace_session_execution_facts.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_request_render_input_projection.py --ignore F403,F405`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/app/integration/context_workspace_session.py src/crxzipple/app/integration/context_workspace_session_execution_facts.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_request_render_input_projection.py --tb=short --maxfail=1`
-> 79 passed.
Session range/item projection verification:
`PYTHONPATH=src ruff check src/crxzipple/app/integration/context_workspace_session.py src/crxzipple/app/integration/context_workspace_session_item_nodes.py src/crxzipple/app/integration/context_workspace_session_segment_ranges.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_request_render_input_projection.py --ignore F403,F405`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/app/integration/context_workspace_session.py src/crxzipple/app/integration/context_workspace_session_item_nodes.py src/crxzipple/app/integration/context_workspace_session_segment_ranges.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_request_render_input_projection.py --tb=short --maxfail=1`
-> 79 passed.
Session current-steps root verification:
`PYTHONPATH=src ruff check src/crxzipple/app/integration/context_workspace_session.py src/crxzipple/app/integration/context_workspace_session_execution.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_request_render_input_projection.py --ignore F403,F405`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/app/integration/context_workspace_session.py src/crxzipple/app/integration/context_workspace_session_execution.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_request_render_input_projection.py --tb=short --maxfail=1`
-> 79 passed.
Session segment-root seed verification:
`PYTHONPATH=src ruff check src/crxzipple/app/integration/context_workspace_session.py src/crxzipple/app/integration/context_workspace_session_segments.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_request_render_input_projection.py --ignore F403,F405`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/app/integration/context_workspace_session.py src/crxzipple/app/integration/context_workspace_session_segments.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_request_render_input_projection.py --tb=short --maxfail=1`
-> 79 passed.
Active item-range seed verification:
`PYTHONPATH=src ruff check src/crxzipple/app/integration/context_workspace_session.py src/crxzipple/app/integration/context_workspace_session_item_nodes.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_request_render_input_projection.py --ignore F403,F405`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/app/integration/context_workspace_session.py src/crxzipple/app/integration/context_workspace_session_item_nodes.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_request_render_input_projection.py --tb=short --maxfail=1`
-> 79 passed.
Session owner reader split verification:
`PYTHONPATH=src ruff check src/crxzipple/app/integration/context_workspace_session.py src/crxzipple/app/integration/context_workspace_session_reader.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/app/integration/context_workspace_session.py src/crxzipple/app/integration/context_workspace_session_reader.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_request_render_input_projection.py --tb=short --maxfail=1`
-> 79 passed.
Run workspace metadata, Context Slice projection, and request-render metadata
have been split by the same rule. Workspace metadata now separates entry
assembly, run node payloads, continuation state, and value formatting; Context
Slice projection separates report/ref extraction from provider input projection;
request-render metadata separates visible-input summary and cost/budget
calculation from the metadata builder DTO. The request-render pipeline remains
the explicit phase coordinator.

Operations hotspot split notes:

- Tool complete: shared presenter/route helpers, query/filter/pagination,
  health/metrics, projection diagnostics, execution-item context lookup,
  overview projection, worker sections, scheduling diagnostics, scheduling
  capacity, scheduling row/blocker/run-projection/section projection, provider history, provider limiter
  projection, worker registration/runtime/capability projection, readiness
  sections/risk source selection and payload normalization, shared provider
  identity, lifecycle events, worker detail summary/capability/runtime sections,
  run table facts/rows/labels, overview actions/risk/rows/type chart/execution mix,
  run details, run detail summary/source/trace projection, error diagnostics,
  artifact/result projection, source owner reads, source/function catalog
  tables, source catalog rows/tone/endpoint/runtime labels, CLI process health
  rows, provider backend
  health rows and backend credential/readiness/runtime/tone labels, page section wiring, page
  DTO/payload helpers,
  provider-local page wrappers, page tabs, overview/page/fact collection,
  artifact/result reference parsing and artifact ref projection/enrichment,
  and golden contract/cost coverage are split into focused modules/tests.
- LLM complete: invocation filters, projection diagnostics, lifecycle/resolver
  event tables, runtime limiter metrics, response events, resolver sections,
  invocation facts, overview rows, provider sections, rate limiter sections,
  usage/error/stream sections, invocation tables, provider/request diagnostics,
  provider request labels, provider access readiness labels, provider warmup
  event projection, provider access/auth-blocked/model-availability row
  projection, detail
  tables, view models, invocation detail projection, invocation
  summary/request-context items, page overview/DTO assembly, page tab
  projection, page owner-fact collection, detail runtime
  observations, detail replay/tool-result labels, detail result payload preview,
  detail response item tables, detail response/observed event tables, detail
  policy trace tables, bounded detail payload helpers, invocation table rows,
  invocation summary/request-context items, lifecycle event
  collection, lifecycle bus topic/read/record projection, lifecycle row label/payload projection, and run-context
  projection are split into focused modules/tests.
- Orchestration complete: projection diagnostics, overview rows, detailed run
  queue, lane/executor sections, event log, backpressure/stuck-run diagnostics,
  ingress/dispatch, execution chain, scheduler status, policy limits,
  repeated-probe/recent-failure sections, health/latency/failure/observer
  metrics, action definitions, runtime fact helpers, and execution-chain
  section/query/diagnostic/row projection, scheduler/policy status helper
  projection, summary metric/tab projection, observed-facts metric projection,
  and page owner-fact collection are
  split into focused modules/tests. Ingress queue projection is also split:
  pending ingress state selection lives in `orchestration_ingress_state.py`,
  row assembly lives in `orchestration_ingress_rows.py`, source/status/
  dispatch/trace/action/age projection lives in
  `orchestration_ingress_projection.py`, and `orchestration_ingress_sections.py`
  keeps only table assembly. Ops event log
  projection is split the same way: event time/row projection lives in
  `orchestration_event_log_rows.py`, event source/summary/detail/tone/trace
  label rules live in `orchestration_event_log_projection.py`, and
  `orchestration_event_log_sections.py` keeps only table assembly.
  Worker/lane/executor projection is split as well: run type/progress labels,
  lane-lock TTL/expiry/renewal labels, executor status tone, trace/workbench
  routes, age labels, and duration labels live in
  `orchestration_worker_projection.py`, while
  lane-lock/executor row assembly lives in `orchestration_worker_rows.py`.
  `orchestration_worker_sections.py` keeps table shells, columns, and routes.
  Run queue row assembly lives in `orchestration_queue_rows.py`, while queue
  priority/wait/lease/tone/trace/age value rules live in
  `orchestration_queue_row_values.py`.
- Events state cleanup is complete for the current scope: the aggregate
  `events_state.py` file has been retired; recent event source selection and
  dead-letter filtering live in `events_recent_state.py`, record/observed-event
  summary projection lives in `events_recent_projection.py`, and
  subscription/topic state, observer runtime state, and shared
  cursor/display/json helpers live in focused state modules. Dead-letter table
  projection now lives in `events_dead_letters.py`; `events.py` is a facade over
  overview/page builders, while observer/subscription sections are split across
  focused consumer/subscription, observer runtime/lag, and coverage modules.
- Events page builder cleanup is complete for the current scope:
  `events_page_builder.py` keeps page DTO assembly, while
  `events_page_facts.py` owns page fact assembly. Source reads live in
  `events_page_sources.py`; topic/cursor/subscription/observer runtime state
  lives in `events_page_runtime_facts.py`; recent-event source selection,
  filtering, and pagination live in `events_page_recent_facts.py`; source-topic
  selection, recent-event read limits, uncovered-event filtering, state flag
  counts, health-count aggregation, and health projection live in
  `events_page_projection.py`.
  Recent-event table projection remains in
  `events_event_details.py`; single-event detail/contract/subscription projection
  lives in `events_event_detail_sections.py`; shared display/tone helpers live in
  `events_event_common.py`.
- Events contract cleanup is complete for the current scope:
  `events_contract_sections.py` keeps topic/contract/route table assembly,
  while topic/route matching, contract labels/statuses, and contract payload
  extraction live in `events_contract_matching.py`.
- Events overview cleanup is complete for the current hotspot scope:
  `events_overview_sections.py` keeps metric card projection only, while
  tab/action projection lives in `events_navigation_sections.py`, contract
  compatibility key-value projection lives in `events_contract_compatibility.py`,
  chart projection lives in `events_overview_charts.py`, owner volume projection
  lives in `events_owner_sections.py`, and overview labels/tones live in
  `events_overview_helpers.py`.
- Memory cleanup is complete for the current hotspot scope: event/context/source
  tables, source files/search trace/source scan tables, health/page summary/chart
  projection, detail projection, scalar value helpers, and file id/indexed/size/
  search/latest-update helpers now live in focused modules; `memory_common.py`
  keeps only Memory overview, record/index status, watcher, backend, and health
  semantics.
- Events, Daemon, Channels, Skills, Browser, Memory, and Access current hotspot
  scopes are split into page view models, shared display/status helpers, event
  projection, table/detail sections, Channels table row/chart projection,
  Channels overview/page builders and page filters, Skills overview/page
  builders and page facts, Daemon table row/chart/drain projection, Daemon
  instance/lease/process detail builders, Access target/requirement/usage
  tables, fallback inventory/target-row projection, and health/action helpers with
  focused regression coverage.
- Browser common helper cleanup is complete for the current scope: the retired
  `browser_common.py` file has been deleted; runtime/proxy/daemon-instance fact
  projection lives in `browser_runtime_facts.py`, status/health tone rules live
  in `browser_tones.py`, generic value/time/byte/filter/label helpers live
  in `browser_values.py`, and profile/page row projection lives in
  `browser_profile_rows.py`.
- Skills table cleanup is complete for the current hotspot scope: the aggregate
  `skills_tables.py` file has been retired; installed/source/conflict catalog
  tables live in `skills_catalog_tables.py`; profile usage lives in
  `skills_profile_usage_table.py`; missing capability tables live in
  `skills_missing_tables.py`; access/capability requirement tables live in
  `skills_requirement_tables.py`; resolver detail tables live in
  `skills_resolver_tables.py`.
- Skills page-fact cleanup is complete for the current hotspot scope:
  `skills_page_builder.py` now keeps page DTO/table/chart/detail assembly, while
  query normalization, safe skill/tool/access reads, readiness projection,
  event buckets, filtering, and health live in `skills_page_facts.py`.
  Skills runtime actions now live in `skills_actions.py`, and package/source
  chart projection lives in `skills_charts.py`; `skills_health.py` keeps health,
  metric, and tab summaries only.
- Skills detail cleanup is complete for the current hotspot scope:
  `skills_details.py` now keeps `SkillDetailModel` assembly only, while detail
  requirement/resource/event table projection and raw skill payload projection
  live in `skills_detail_sections.py`.
- Skills event cleanup is complete for the current hotspot scope:
  observation/bus event source reads, skill-event filtering, source dedupe, and
  latest-readiness mapping live in `skills_event_sources.py`; authoring/read
  labels, event details, and tone projection remain in `skills_events.py`.
- Tool runtime metric cleanup is complete for the current hotspot scope:
  runtime bootstrap policy metric card projection and runtime config parsing
  live in `tool_runtime_metrics.py`; terminal duration, run-window,
  percentile, throughput, and duration label values live in
  `tool_metric_values.py`; `tool_metrics.py` is focused on Tool health and
  metric-card composition.
- Tool readiness cleanup is complete for the current hotspot scope:
  `tool_readiness_sections.py` keeps risk table assembly,
  `tool_readiness_risk.py` keeps readiness service selection and access
  fallback, and `tool_readiness_payloads.py` owns combined/access payload
  normalization, requirement labels, and action route projection.
- Tool Run filtering cleanup is complete for the current hotspot scope:
  `tool_run_filters.py` keeps only run filtering predicates, search matching,
  status matching, and run dedupe; `tool_run_query.py` owns query DTO,
  normalization, pagination, and empty-state projection; `tool_run_time.py`
  owns run time and duration semantics shared by table/detail/provider sections.
- Tool lifecycle event cleanup is complete for the current hotspot scope:
  `tool_lifecycle_event_rows.py` keeps run/worker lifecycle event table sections
  and row assembly; `tool_lifecycle_event_projection.py` owns event priority,
  tone, detail text, tool labels, source labels/routes, trace derivation, and
  shared table column/display helpers used by lifecycle overview/detail views.
- Memory table cleanup is complete for the current hotspot scope: event-backed
  context/index/write/retrieval tables live in `memory_event_tables.py`, while
  source file/search trace/source scan tables live in `memory_source_tables.py`.
  `memory_tables.py` keeps store/index/usage tables.
- Memory page cleanup is complete for the current hotspot scope:
  `memory_page_facts.py` owns query normalization, owner-safe profile/memory/
  watch/event reads, selected agent resolution, file filtering, search-hit
  collection, and health calculation; `memory.py` keeps provider facade and
  page/overview DTO assembly.
- Daemon read-model facade cleanup is complete for the current scope:
  owner-safe runtime fact reads, process row synthesis/currentness, query
  filtering, and page action/link helpers live in focused helper modules;
  `daemon.py` is now a provider facade, page assembly lives in
  `daemon_page_builder.py`, and page owner-read/fact collection lives in
  `daemon_page_facts.py`. Daemon Process Sessions table projection now lives
  in `daemon_process_tables.py`; Process output reads/payloads/tables
  live in `daemon_process_output_details.py`; service-set/service/dependency row
  synthesis lives in `daemon_service_rows.py`, while instance/lease/runtime row
  synthesis lives in `daemon_table_rows.py`;
  observation/Event-bus source collection lives in `daemon_event_sources.py`,
  while daemon/process topic matching, owner/module filtering, and dedupe live
  in `daemon_event_filters.py`;
  process/state/lease chart projection lives in `daemon_charts.py`, lease/drain
  key-value overview lives in `daemon_drain.py`, and metric-card/tab projection
  lives in `daemon_metrics.py`; `daemon_tables.py` keeps table section assembly
  and `daemon_health.py` keeps health and desired-service rules. Daemon
  shared helper semantics are now split: scalar/time/filter normalization stays
  in `daemon_common.py`, status projection lives in `daemon_status_helpers.py`,
  process binding/currentness/output marker rules live in
  `daemon_process_helpers.py`, browser host labels live in
  `daemon_browser_helpers.py`, and Browser Host instance summary projection
  lives in `daemon_browser_instance_summary.py`.
- Channels read-model formatting cleanup is complete for the current scope:
  pure display/time/status helpers live in `channels_formatting.py`; JSON
  excerpt and payload display helpers live in `channels_payload_formatting.py`;
  safe owner/event calls live in `channels_safe_access.py`; topic parsing lives
  in `channels_topic_helpers.py`; connection topic/runtime matching lives in
  `channels_connection_helpers.py`; event routing, trace routing, event search,
  and dedupe live in `channels_event_helpers.py`; table/key-value/capability builders live in
  `channels_sections.py`; message-flow/delivery-trend/top-channel/failure
  chart projection lives in `channels_charts.py`; runtime record projection
  lives in `channels_runtime_records.py`; page query normalization and
  runtime/event/interaction filters live in `channels_page_filters.py`;
  runtime details live in `channels_details.py`; record details live in
  `channels_record_details.py`; interaction details live in
  `channels_interaction_details.py`; `channels_common.py` keeps safe channel
  record extraction helpers.
- Operations observer runtime cleanup is complete for the current scope:
  observer event-name catalog rules live in `observer_event_names.py`, callback
  contracts and subscription records live in `observer_subscriptions.py`,
  cursor cache/wait-watch state lives in `observer_cursor_state.py`,
  subscription batch processing and cursor persistence live in
  `observer_subscription_processor.py`, heartbeat/maintenance callbacks live in
  `observer_runtime_callbacks.py`, scan/wait processing lives in
  `observer_runtime_processing.py`, and the run loop lives in
  `observer_runtime_loop.py`. `observer_runtime_service.py` remains the durable
  event-pump facade. The aggregate `application/runtime.py` has been retired;
  callers import the focused modules directly.
- Operations source read-model factory cleanup is complete for the current
  scope: `factory.py` keeps provider construction; `factory_context.py` owns the
  explicit typed context DTO and observer-runtime attachment hook.
- Module fallback overview cleanup is complete: `modules.py` is a thin
  provider/router, shared overview/table helpers live in `modules_helpers.py`,
  and fallback overview projections live in focused `modules_*` files.
- Context Workspace Operations cleanup is complete for the current hotspot
  scope: `context_workspace.py` keeps provider/overview/page assembly;
  safe owner reads, slice collection, page health, and derived page facts live
  in `context_workspace_page_facts.py`; workspace/node/diagnostic rows live in
  `context_workspace_rows.py`; metric card projection lives in
  `context_workspace_metrics.py`; generic table/metadata/time/token helpers live
  in `context_workspace_row_helpers.py`; snapshot and context-budget rows live
  in `context_workspace_snapshot_rows.py`.
- Loop-regression diagnostics cleanup is complete for the current hotspot scope:
  `diagnostics.py` keeps the baseline builder; common value helpers, LLM
  response/request metrics, tool-only loop health, run-signal, final-answer,
  and missing-metric projection live in focused diagnostics helper modules,
  including `diagnostics_loop_health.py`.
- Operations persistence cleanup is complete for the current hotspot scope:
  projection store, observation store, and action-audit store are split into
  focused repository modules; the retired aggregate `repositories.py` file is
  deleted instead of retained as a compatibility shim. Observation store mapper
  and recording/update mechanics are also split out of
  `observation_repository.py`. The file-backed lightweight observation store is
  now a 141-line path/locking facade; file lock/atomic-write mechanics live in
  `observation_store_io.py`, event bucket aggregation lives in
  `observation_store_buckets.py`, and snapshot parsing, event recording, and
  heartbeat recording live in `observation_store_records.py`.
- Operations observation model cleanup is complete for the current scope:
  `observation_models.py` is a 23-line public model export surface, while
  observed-event/module observation DTOs, observer heartbeat DTOs, projection
  DTOs, and snapshot DTOs live in focused application model modules.
- Operations projection materializer cleanup is complete for the current
  hotspot scope: `application/projections.py` keeps materialize/write/publish
  flow only, module routing lives in `projection_modules.py`, page loading
  lives in `projection_materializer_pages.py`, table/detail extraction lives in
  `projection_materializer_details.py`, Memory space detail projection lives in
  `projection_memory_details.py`, and JSON-safe normalization lives in
  `projection_materializer_json.py`.
  Materialization and invalidation-publish exception paths now use safe
  structured logging fields instead of LogRecord-reserved names, with regression
  coverage so projection failures are not masked by logging itself.
  Public projection constants/functions remain importable from the materializer
  module because they are part of the projection application API, not a retired
  compatibility facade.
- Operations projection read-payload cleanup is complete for the current scope:
  `read_models/projection_payloads.py` keeps public `/operations` projection
  response assembly, while detail payload deferral lives in
  `projection_detail_payloads.py` and table/related filter rules live in
  `projection_table_filters.py`.
- Tool page section cleanup is complete for the current scope:
  `tool_page_sections.py` is a section group composition entrypoint, while
  execution/queue/scheduling sections, catalog/source/readiness sections, and
  worker/run detail sections live in focused group modules. Tool page source/
  provider owner reads live in `tool_page_source_facts.py`, run-derived buckets/
  detail contexts live in `tool_page_run_facts.py`, run query/filter/pagination
  selection lives in `tool_page_run_selection.py`, and `tool_page_facts.py`
  keeps final fact assembly.
- Operations DTO and HTTP interface cleanup is complete for the current scope:
  `http_models.py` is a thin export module and `http.py` is a runtime/SSE plus
  sub-router composition layer. Runtime status checks live in
  `http_runtime.py`; projection-refresh SSE payload normalization and frame
  formatting live in `http_stream_payloads.py`.
- Operations controlled-action routes are split by action owner: channel
  runtime/dead-letter controls live in `http_action_routes_channels.py`, while
  event subscription and observer cursor controls remain in
  `http_action_routes_events.py`.
- Access Operations cleanup is complete for the current provider hotspot:
  `access.py` is a dependency/query facade and page assembly lives in
  `access_page_builder.py`.
- Operations action-flow cleanup is complete for the current scope:
  `actions.py` keeps the action facade and receives an explicit
  `OperationsActionDependencies` bundle from HTTP composition; runtime controls,
  resource controls, orchestration controls, dependency validation, result DTOs,
  event subscription advancement, and stale Channel runtime pruning live in
  focused action modules.

## Wave 3. Capability Runtime Hardening

Purpose: make powerful local capabilities safe and generic.

| Task | Modules | Acceptance |
| --- | --- | --- |
| Split browser application/runtime engines | browser | Profile admin, pool allocation, execution coordination, action engine, snapshot, error mapping are distinct |
| Split Tool worker/source runtime services | tool | Complete: Tool worker artifact externalization moved to `tool_result_artifacts.py`, result validation to `tool_result_validation.py`, runtime execution to `worker_runtime_execution.py`, failure normalization to `worker_errors.py`, background tracking to `worker_tracking.py`, capability payloads to `worker_capabilities.py`, execution context decoration to `worker_execution_context.py`, result completion/failure application to `worker_completion.py`, recovered dispatch handling to `worker_recovery.py`, registration/stale/prune helpers to `worker_registration.py`, assignment concurrency selection to `worker_assignment_selection.py`, wakeup waiting to `worker_wakeup.py`, processing heartbeat threading to `worker_processing_heartbeat.py`, run/assignment/worker/dispatch heartbeat persistence to `worker_run_heartbeat.py`, worker run-loop control to `worker_run_loop.py`, run function/source resolution to `worker_run_resolution.py`, and run preparation/completion/failure persistence to `worker_run_persistence.py`; source runtime request bundle DTO/building moved to `source_runtime_bundles.py`, credential/runtime requirement parsing to `source_requirements.py`, entity/record mapping to `source_record_mapping.py`, merge/change state to `source_state.py`, event payloads to `source_events.py`, write validation to `source_validation.py`, command DTOs to `source_command_models.py`, UoW protocol to `source_unit_of_work.py`, function commands to `source_function_commands.py`, and source commands/sync use cases to `source_commands.py`; CLI source safety/runtime concerns are split into focused `cli_source_*` modules for config parsing, discovery/spec construction, process execution, process-output observation, credential injection, envelopes, redaction, and path validation |
| Add browser lease/cleanup/timeout tests | browser | CDP/session/action cleanup is deterministic |
| Split channel runtime by transport path | channels | Done: Web, Webhook, and Lark runtime services are isolated in transport-specific files, while `application/runtime.py` keeps shared bootstrap only. Transport-neutral observe cursor/status/settled-state helpers are shared; Lark session-message observation projection, outbound observe delivery, identity lookup/cache, long-connection ingress, and message-to-run submission are isolated behind focused helpers/services. Webhook inbound message-to-run submission and idempotency lookup now live behind a focused submission runtime. Channel profile, interaction, and runtime registry management now live in `profile_service.py`, `interaction_service.py`, and `runtime_manager.py`; `services.py` is a thin export surface |
| Add channel idempotency tests | channels | Complete for current channel lifecycle: Lark observe delivery has regression coverage for duplicate successful message skips; webhook inbound supports an explicit idempotency key that reuses the original run on duplicate submission; webhook automatic outbound retry/dead-letter loops are covered against duplicate delivery/dead-letter emission. Explicit dead-letter replay is documented as deliberate resend, not hidden idempotency |
| Add channel payload redaction tests | channels | Complete for current observation exits: dead-letter HTTP listing and Operations channels projection redact callback URLs, webhook callback URLs, tokens, secrets, authorization, and cookies without mutating owner event truth |
| Split mobile engine concerns | mobile | Done for this pass: control command execution moved to `mobile_control_engine.py`; snapshot, OCR fallback, vision-layout augmentation, screenshot artifact creation, and generation-scoped ref persistence moved behind `mobile_snapshot_actions.py`; tap/type/swipe/press/wait primitives moved to `mobile_interaction_actions.py`; ref/selector target resolution moved to `mobile_action_targets.py`; `engines.py` is now a thin action dispatcher |
| Add OCR timeout/error tests | ocr | Complete for current OCR runtime: adapter request/invalid-payload/HTTP/provider errors, result-size budgets, application/host capacity metadata, capacity exhaustion domain mapping, and HTTP 503 surfacing are covered |

Mobile engine follow-up note: screenshot-oriented action behavior is now separated from
the ADB-backed action dispatcher. `infrastructure/mobile_snapshot_actions.py` owns UI
snapshot capture, OCR fallback, vision layout candidate merging, screenshot artifact
payload construction, and generation-scoped ref persistence.
`infrastructure/mobile_control_engine.py` owns list/launch/activate/terminate control
commands. `infrastructure/mobile_action_targets.py` owns ref/selector target
resolution, `infrastructure/mobile_interaction_actions.py` owns tap/type/swipe/
press/wait primitives, and `infrastructure/engines.py` remains the public action
dispatcher without changing the mobile engine API.
Current verification:
`PYTHONPATH=src ruff check src/crxzipple/modules/mobile/infrastructure/engines.py src/crxzipple/modules/mobile/infrastructure/mobile_snapshot_actions.py tests/unit/test_mobile_domain.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/mobile/infrastructure/engines.py src/crxzipple/modules/mobile/infrastructure/mobile_snapshot_actions.py tests/unit/test_mobile_domain.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_mobile_domain.py tests/unit/test_mobile_http.py tests/unit/test_mobile_tool_http.py tests/unit/test_mobile_device_leases.py tests/unit/test_mobile_cli.py --tb=short --maxfail=1`
-> 51 passed.
Control engine split verification:
`PYTHONPATH=src ruff check src/crxzipple/modules/mobile/infrastructure/engines.py src/crxzipple/modules/mobile/infrastructure/mobile_control_engine.py src/crxzipple/modules/mobile/infrastructure/__init__.py tests/unit/test_mobile_domain.py tests/unit/test_mobile_device_leases.py tests/unit/test_mobile_cli.py tests/unit/test_mobile_http.py tests/unit/test_mobile_tool_http.py --ignore F403,F405`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/mobile/infrastructure/engines.py src/crxzipple/modules/mobile/infrastructure/mobile_control_engine.py src/crxzipple/modules/mobile/infrastructure/__init__.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_mobile_domain.py tests/unit/test_mobile_device_leases.py tests/unit/test_mobile_cli.py tests/unit/test_mobile_http.py tests/unit/test_mobile_tool_http.py --tb=short --maxfail=1`
-> 51 passed.
Interaction action split verification:
`PYTHONPATH=src ruff check src/crxzipple/modules/mobile/infrastructure/engines.py src/crxzipple/modules/mobile/infrastructure/mobile_action_targets.py src/crxzipple/modules/mobile/infrastructure/mobile_interaction_actions.py tests/unit/test_mobile_domain.py --ignore F403,F405`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/mobile/infrastructure/engines.py src/crxzipple/modules/mobile/infrastructure/mobile_action_targets.py src/crxzipple/modules/mobile/infrastructure/mobile_interaction_actions.py src/crxzipple/modules/mobile/infrastructure/mobile_control_engine.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_mobile_domain.py tests/unit/test_mobile_device_leases.py tests/unit/test_mobile_cli.py tests/unit/test_mobile_http.py tests/unit/test_mobile_tool_http.py --tb=short --maxfail=1`
-> 51 passed.

Tool package follow-up note: OpenAPI provider manifest parsing and Access credential
requirement parsing now live in `tool_package_access.py`; runtime request metadata,
dependency requirements, capability ids, common string/enum/mapping payload parsing,
and runtime requirement set derivation live in `tool_package_manifest_values.py`;
local tool domain declaration construction and parameter parsing live in
`tool_package_tool_declarations.py`; provider backend plan parsing lives in
`tool_package_provider_backends.py`; handler/runtime entrypoint resolution, typed
dependency injection, and activation construction live in `tool_package_activation.py`.
`tool_packages.py` stays as the package-load facade for namespace/package orchestration
and activation. Current verification:
`python -m ruff check src/crxzipple/modules/tool/infrastructure/tool_packages.py src/crxzipple/modules/tool/infrastructure/tool_package_activation.py src/crxzipple/modules/tool/infrastructure/tool_package_access.py src/crxzipple/modules/tool/infrastructure/tool_package_manifest_values.py src/crxzipple/modules/tool/infrastructure/tool_package_provider_backends.py src/crxzipple/modules/tool/infrastructure/tool_package_tool_declarations.py tests/unit/test_tool_providers.py tests/unit/test_tool_source_service.py tests/unit/test_tool_access_architecture.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_tool_access_architecture.py --tb=short --maxfail=1`
-> 7 passed;
`PYTHONPATH=src pytest -q tests/unit/test_tool_providers.py -k 'not discovers_and_executes_openapi_remote_tools' --tb=short --maxfail=1`
-> 21 passed, 1 deselected;
`PYTHONPATH=src pytest -q tests/unit/test_tool_source_service.py -k 'credential or openapi or provider_backend' --tb=short --maxfail=1`
-> 5 passed, 15 deselected.

Tool persistence follow-up note: generic persistence payload coercion now lives in
`persistence/repository_payloads.py`; Tool Surface payload restoration now lives in
`persistence/repository_surface_payloads.py`; Tool Surface persistence now lives in
`persistence/surface_repository.py`; source and discovery-run persistence now lives in
`persistence/source_repositories.py`; function and catalog persistence now lives in
`persistence/function_repositories.py`; provider backend persistence now lives in
`persistence/provider_backend_repository.py`; Tool run, assignment, and worker
SQLAlchemy repositories now live in `persistence/runtime_repositories.py`.
`persistence/repositories.py` remains the public import surface, reduced from the
1553-line audit baseline to a 33-line export module. Current
verification:
`python -m ruff check src/crxzipple/modules/tool/infrastructure/persistence/repositories.py src/crxzipple/modules/tool/infrastructure/persistence/source_repositories.py src/crxzipple/modules/tool/infrastructure/persistence/function_repositories.py src/crxzipple/modules/tool/infrastructure/persistence/provider_backend_repository.py src/crxzipple/modules/tool/infrastructure/persistence/runtime_repositories.py src/crxzipple/modules/tool/infrastructure/persistence/surface_repository.py src/crxzipple/modules/tool/infrastructure/persistence/repository_payloads.py src/crxzipple/modules/tool/infrastructure/persistence/repository_surface_payloads.py src/crxzipple/modules/tool/infrastructure/persistence/__init__.py src/crxzipple/shared/infrastructure/sqlalchemy_uow.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_tool_source_catalog_persistence.py --tb=short --maxfail=1`
-> 3 passed;
`PYTHONPATH=src pytest -q tests/unit/test_tool_background.py -k 'not local_background_process' --tb=short --maxfail=1`
-> 23 passed, 1 deselected;
`PYTHONPATH=src pytest -q tests/unit/test_tool_execution.py -k 'not process_tool' --tb=short --maxfail=1`
-> 20 passed, 1 deselected. The deselected local process strategy tests require
`ProcessPoolExecutor(spawn)` and fail in the current sandbox with
`[Errno 1] Operation not permitted`, matching the known process capability
restriction rather than persistence behavior.

Tool HTTP follow-up note: Pydantic HTTP request/response models now live in
`interfaces/http_models.py`; route payload/request projection and provider backend
readiness payload shaping live in `interfaces/http_payloads.py`; `interfaces/http.py`
is now a route surface for parsing, authorization handoff, owner service lookup, and
HTTP exception mapping. Current verification:
`python -m ruff check src/crxzipple/modules/tool/interfaces/http.py src/crxzipple/modules/tool/interfaces/http_models.py src/crxzipple/modules/tool/interfaces/http_payloads.py`
-> passed;
`python -m compileall -q src/crxzipple/modules/tool/interfaces/http.py src/crxzipple/modules/tool/interfaces/http_models.py src/crxzipple/modules/tool/interfaces/http_payloads.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_tool_http.py -k 'not openapi_provider_endpoints_discover_and_execute_remote_tools' --tb=short --maxfail=1`
-> 24 passed, 1 deselected. The deselected OpenAPI provider HTTP test requires
binding a local `ThreadingHTTPServer`, which the current sandbox denies with
`PermissionError`.

Tool domain follow-up note: the former 1147-line `domain/entities.py` is now a
61-line public domain export surface. Catalog/source/function/provider/tool
definition aggregates live in `domain/catalog_entities.py`; run/assignment/worker
lifecycle aggregates live in `domain/runtime_entities.py`; shared validation and
normalization live in `domain/entity_normalization.py`. Current verification:
`python -m ruff check src/crxzipple/modules/tool/domain`
-> passed;
`python -m compileall -q src/crxzipple/modules/tool/domain`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_tool_http.py tests/unit/test_tool_provider_backend_service.py --tb=short --maxfail=1 -k 'not openapi_provider_endpoints_discover_and_execute_remote_tools'`
-> 28 passed, 1 deselected;
`PYTHONPATH=src pytest -q tests/unit/test_tool_background.py --tb=short --maxfail=1 -k 'not executes_local_background_process_tool_and_updates_lifecycle'`
-> 23 passed, 1 deselected;
`PYTHONPATH=src pytest -q tests/unit/test_operations_tool_metrics.py tests/unit/test_operations_tool_run_filters.py tests/unit/test_operations_tool_run_error_diagnostics.py tests/unit/test_operations_tool_scheduling_sections.py --tb=short --maxfail=1`
-> 10 passed;
`PYTHONPATH=src pytest -q tests/unit/test_tool_execution.py tests/unit/test_tool_source_service.py tests/unit/test_tool_catalog_reconcile.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_context_tree_tool.py tests/unit/test_module_architecture_guards.py --tb=short --maxfail=1 -k 'not executes_local_inline_process_tool_and_reports_process_context'`
-> 95 passed, 1 deselected.

Tool catalog-model follow-up note: the former 943-line
`application/catalog_models.py` is now a 37-line application export surface.
Catalog enums/requirement types live in `catalog_model_types.py`; stable payload,
schema, and hashing helpers live in `catalog_model_helpers.py`; function candidate,
provider backend candidate, and function record models live in
`catalog_function_models.py`; source and discovery records live in
`catalog_source_models.py`. Current verification:
`python -m ruff check src/crxzipple/modules/tool/application/catalog_models.py src/crxzipple/modules/tool/application/catalog_model_types.py src/crxzipple/modules/tool/application/catalog_model_helpers.py src/crxzipple/modules/tool/application/catalog_function_models.py src/crxzipple/modules/tool/application/catalog_source_models.py`
-> passed;
`python -m compileall -q src/crxzipple/modules/tool/application/catalog_models.py src/crxzipple/modules/tool/application/catalog_model_types.py src/crxzipple/modules/tool/application/catalog_model_helpers.py src/crxzipple/modules/tool/application/catalog_function_models.py src/crxzipple/modules/tool/application/catalog_source_models.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_tool_catalog_reconcile.py tests/unit/test_tool_source_service.py tests/unit/test_tool_source_catalog_persistence.py tests/unit/test_tool_providers.py tests/unit/test_openapi_access.py tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_access_http.py --tb=short --maxfail=1 -k 'not discovers_and_executes_openapi_remote_tools and not openapi_provider_endpoints_discover_and_execute_remote_tools'`
-> 73 passed, 1 deselected.

Tool worker follow-up note: `application/worker_service.py` is now a 624-line worker
coordinator after moving ToolRun UoW preparation, completion, and failure persistence
to `worker_run_persistence.py`, and run/assignment/worker/dispatch heartbeat
persistence to `worker_run_heartbeat.py`. Long-running worker loop control lives in
`worker_run_loop.py`, function/source catalog resolution for worker concurrency and
execution lives in `worker_run_resolution.py`, and runtime invocation/result
validation remains in `worker_runtime_execution.py`. Runnable assignment selection
now resolves ToolFunction/catalog metadata inside the same UoW that loaded the
candidate assignments and runs, avoiding a closed-UoW lookup during worker capacity
selection. Current verification:
`PYTHONPATH=src ruff check src/crxzipple/modules/tool/application/worker_service.py src/crxzipple/modules/tool/application/worker_run_persistence.py tests/unit/test_tool_background.py tests/unit/test_tool_execution.py --ignore F403,F405`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/tool/application/worker_service.py src/crxzipple/modules/tool/application/worker_run_persistence.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_tool_background.py -k 'not executes_local_background_process_tool_and_updates_lifecycle' --tb=short --maxfail=1`
-> 23 passed, 1 deselected;
`PYTHONPATH=src pytest -q tests/unit/test_tool_execution.py -k 'not executes_local_inline_process_tool_and_reports_process_context' --tb=short --maxfail=1`
-> 20 passed, 1 deselected;
`PYTHONPATH=src pytest -q tests/unit/test_tool_execution.py::ToolExecutionTestCase::test_execute_many_batches_inline_run_creation_and_runs_concurrently tests/unit/test_tool_background.py::ToolBackgroundTestCase::test_executes_local_background_thread_tool_and_updates_lifecycle tests/unit/test_tool_background.py::ToolBackgroundTestCase::test_executes_remote_background_async_tool_and_updates_lifecycle --tb=short --maxfail=1`
-> 3 passed. The deselected local process strategy tests require
`ProcessPoolExecutor(spawn)` and fail in the current sandbox with
`[Errno 1] Operation not permitted`, which is an execution-environment capability
restriction rather than ToolRun persistence behavior.
Follow-up UoW-boundary verification:
`PYTHONPATH=src ruff check src/crxzipple/modules/tool/application/worker_service.py src/crxzipple/modules/tool/application/worker_assignment_selection.py tests/unit/test_tool_background.py tests/unit/test_tool_execution.py tests/unit/test_dispatch.py --ignore F403,F405`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_tool_background.py tests/unit/test_tool_execution.py tests/unit/test_dispatch.py -k 'not process_tool and not inline_process_tool and not background_process_tool' --tb=short --maxfail=1`
-> 51 passed, 2 deselected.
Heartbeat persistence split verification:
`PYTHONPATH=src ruff check src/crxzipple/modules/tool/application/worker_service.py src/crxzipple/modules/tool/application/worker_run_heartbeat.py tests/unit/test_tool_background.py tests/unit/test_tool_execution.py tests/unit/test_dispatch.py --ignore F403,F405`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/tool/application/worker_service.py src/crxzipple/modules/tool/application/worker_run_heartbeat.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_tool_background.py tests/unit/test_tool_execution.py tests/unit/test_dispatch.py -k 'not process_tool and not inline_process_tool and not background_process_tool' --tb=short --maxfail=1`
-> 51 passed, 2 deselected.

Tool app assembly follow-up note: `app/assembly/tool.py` is now a 536-line
composition surface after moving Tool query/control/orchestration/worker adapters and
service-graph construction to `app/assembly/tool_service_graph.py`. The package-level
lazy export for `build_tool_execution_services` now points directly at the focused
service-graph helper, while `tool.py` still re-exports the public name for direct
module imports. Current verification:
`PYTHONPATH=src ruff check src/crxzipple/app/assembly/tool.py src/crxzipple/app/assembly/tool_service_graph.py src/crxzipple/app/assembly/__init__.py tests/unit/test_module_lifecycle_architecture.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/app/assembly/tool.py src/crxzipple/app/assembly/tool_service_graph.py src/crxzipple/app/assembly/__init__.py tests/unit/test_module_lifecycle_architecture.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_module_lifecycle_architecture.py --tb=short --maxfail=1`
-> 21 passed.

## Wave 4. Governance, Credentials, And Extensibility

Purpose: keep external integration and configuration clean under growth.

| Task | Modules | Acceptance |
| --- | --- | --- |
| Split Access OAuth/query/action/settings flows | access | Done for this audit wave: OAuth repository/token-store contracts and OAuth result DTOs moved to `oauth_contracts.py`; OAuth payload redaction moved to `oauth_redaction.py` and is covered by a no-raw-secret setup payload test; token endpoint HTTP behavior, retryable provider HTTP/network failure handling, and redacted endpoint exceptions moved to `oauth_token_client.py` with refresh/revoke lifecycle and retry coverage; file-backed token storage now exposes a storage-key lock used by auto-refresh and revoke coordination; local Codex callback/browser opener logic moved to `oauth_callback_listener.py`; setup-session record/result and authorization/device-code payload shaping moved to `oauth_setup_flows.py`; Codex provider constants and identity extraction moved to `oauth_codex.py`; token payload expiry/scope/subject extraction, token masking, default account id, PKCE challenge, scope diff payload, and small text normalization moved to `oauth_token_payloads.py`; OAuth provider/account record construction, token document construction, account status replacement, refresh account shaping, and Settings credential-binding request construction moved to `oauth_account_records.py`; query result DTOs moved to `query_results.py`; synthetic asset compatibility projection moved to `query_assets.py`; overview counts, empty overview, asset-list projection, and readiness lookup moved to `query_overview_assets.py`; read-model record shaping and consumer merge rules moved to `query_record_models.py`; Settings/Access record collection and setup/OAuth/readiness conversion moved to `query_records.py`; Access/Settings audit pagination, merge, and sorting moved to `query_audits.py`; credential requirement projection moved to `query_requirements.py`; read model timestamp, normalization, setup hint, source masking, masked preview, and sensitive-key redaction helpers moved to `read_model_payloads.py`; inventory requirement check-spec construction, credential binding labels, requirement masking, credential asset kind calculation, and metadata redaction moved to focused `inventory_*` modules; migration legacy value extraction and migration requirement/credential payload rules moved to focused `migration_*` modules; persistence SQLAlchemy model/application record mapping moved to `repository_mappers.py`; action contracts/change parsing/redaction/payload/readiness helpers moved to focused `action_*` modules; setup/verify and OAuth action handlers moved to focused handler modules; Settings action contracts, payload parsing, Access record mapping, credential binding conversion, consumer binding conversion, and materialized config view/provider moved to focused `settings_*` modules; requirement parsing/canonical binding/compatibility rules moved to `credential_requirement_rules.py`; env/file/literal credential resolution moved to `credential_resolver.py`; credential resolution audit context, event payloads, safe source refs, trace redaction, consumer audit payloads, and audit text truncation moved to `credential_resolution_audit.py`; setup-flow object construction moved to `credential_setup_flows.py`; configured credential record lookup, source derivation, OAuth provider lookup, and configured credential resolution moved to `configured_credentials.py`; current Access checklist is complete, with deeper audit persistence hardening tracked as a cross-module follow-up |
| Add no-raw-secret tests | access, settings, operations | Done: Access credential resolution/action and Settings read-model/action redaction coverage already guards raw secret inputs; Operations observed-event projection, SQL observation persistence, and SQL projection persistence now redact sensitive keys, database URL passwords, and inline secret assignments while preserving safe token counts |
| Split Settings HTTP governance surface | settings | Done: HTTP routes, action policy, redaction, runtime defaults, and Settings page presenters are separated; Settings page overview counts/homepage sections/resource inventory shaping live in `read_models/pages_overview.py`, common validation/impact/section helpers live in `read_models/pages_common.py`, and audit page/payload projection lives in `read_models/pages_audits.py`; Settings HTTP action request DTOs, response projection, request/helper/error-audit logic, execution gate, create/update mutations, and dry-run/validation handling are split to `http_action_models.py`, `http_action_responses.py`, `http_action_helpers.py`, `http_action_execution.py`, `http_action_mutations.py`, and `http_action_validation.py`; Settings setup resource collection/import/seed/result/payload helpers are split to `setup_resources.py`, `setup_importer.py`, `setup_seeder.py`, `setup_results.py`, and `setup_payloads.py`; Settings setup database URL summary/redaction is split to `setup_database.py`; Access bootstrap resource declarations are split to `setup_access_resources.py`; core bootstrap resource collectors are split to `setup_core_resources.py`; in-memory service bundle assembly is split to `service_bundle.py`; Settings action result payload construction is split to `action_results.py`; resource action facade is split to `resource_actions.py`; resource create/update lifecycle is split to `resource_definition_actions.py`; resource publish/rollback lifecycle is split to `resource_publication_actions.py`; override action lifecycle is split to `override_actions.py`; Settings action-attempt audit construction is split to `action_audit.py`; resource-version construction/publish mechanics are split to `resource_versioning.py`; effective resolution, query/read operations, and shared service helpers are split to `resolution_service.py`, `query_service.py`, and `service_common.py`; Settings domain aggregates are split to focused resource/version/override/snapshot/audit modules behind an 18-line `domain/entities.py` export surface; Settings materialization warning DTO and payload/profile/tool/access normalization are split from the materializer; Settings persistence record DTOs, SQLAlchemy model/record mappers, domain/repository mappers, and resource/version/override/snapshot/audit repository families are split from repository query classes; Settings action service audit metadata now reuses the shared redaction helper instead of carrying a private redaction copy |
| Add Settings owner metadata invariant | settings | Done: `test_every_supported_kind_declares_write_path_and_apply_behavior` locks every Settings kind to explicit owner/truth source, owner API write path, apply mode, hot-apply flag, and owner-API requirement semantics without pushing observation policy into resource metadata |
| Split Skills filesystem package repository | skills | Done for this audit wave: path safety moved to `path_safety.py`; SKILL.md frontmatter, legacy manifest parsing, requirement normalization, and markdown rendering moved to `manifest_parser.py`; bounded file reads, legacy manifest file reads, resource discovery, and fingerprinting moved to `package_files.py`; directory discovery/loading moved to `package_loader.py`; `repository.py` now keeps root selection and public mutation/read orchestration; support-file write/delete traversal tests prevent `..` paths from modifying `SKILL.md`; targeted Skills tests pass |
| Split Skills interfaces/authoring/owner state | skills | Done for this audit wave: authoring payload projection moved to `authoring_payloads.py`, draft/package/request conversion and requirement merge moved to `authoring_conversions.py`, validation/readiness projection moved to `authoring_validation.py` and `authoring_readiness.py`, draft diff building moved to `authoring_diff.py`, apply lifecycle rules moved to `authoring_apply.py`, and audit/event observation moved to `authoring_observation.py`; owner package/source index helpers moved to `owner_package_index.py`; owner readiness snapshot/check/event payload projection moved to `owner_readiness_projection.py`; persistence model/application mapper helpers moved to `repository_mappers.py`; HTTP request/response DTOs moved to `http_models.py`; CLI option parsing and payload projection moved to `cli_options.py` and `cli_payloads.py`; Source and Draft CLI command groups moved to `cli_source_commands.py` and `cli_draft_commands.py`; source/skill runtime visibility, Context Workspace runtime-resolution golden coverage, and install/create race normalization are covered; remaining Skills hardening is trusted source/provenance policy |
| Add trusted source and path isolation tests | skills | Done: source/skill runtime visibility policy, readonly system-source rejection, nested resource reads, symlink escape filtering, read traversal rejection, and support-file write/delete traversal guards cover trusted source and path isolation boundaries |
| Add Authorization grant state-machine tests | authorization | Complete for current authorization surface: run/session temporary grants cannot leak across run/session/agent scope; agent-managed tool/effect allow/revoke, dry-run/impact preview, Access boundary, audit redaction, HTTP DTO/payload/service/agent-grant/policy-handler/decision-route split, agent-managed policy construction helper split, tool execution authorization helper split, policy impact helper split, temporary grant helper/use-case split, decision use-case split, audit record helper split, audit redaction helper split, policy lifecycle helper split, public service facade split, agent grant/revoke coordinator split, and persistence mapper split are covered |

Operations no-raw-secret follow-up note: Operations now treats redaction as an
observation/projection boundary concern. `application/observation_payloads.py`
redacts sensitive keys, database URL passwords, and inline `token=...` /
`secret=...` assignments while keeping safe numeric token-count metrics. The same
helper is used by observed-event projection, SQL observed-event persistence, and SQL
projection persistence so raw owner/event payloads cannot leak through Operations UI
or materialized read models.
Current verification:
`PYTHONPATH=src ruff check src/crxzipple/modules/operations/application/observation_payloads.py src/crxzipple/modules/operations/infrastructure/persistence/observation_repository_mappers.py src/crxzipple/modules/operations/infrastructure/persistence/projection_repository.py tests/unit/test_operations_observation.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/operations/application/observation_payloads.py src/crxzipple/modules/operations/infrastructure/persistence/observation_repository_mappers.py src/crxzipple/modules/operations/infrastructure/persistence/projection_repository.py tests/unit/test_operations_observation.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k 'sensitive or redacts or sqlalchemy_store_records_operations_projection' --tb=short --maxfail=1`
-> 4 passed, 50 deselected.

Settings application follow-up note: bootstrap setup now delegates core
Tool/Memory/runtime-default/environment resource seed construction to
`application/setup_core_resources.py`, Access seed declarations to
`application/setup_access_resources.py`, database URL redaction to
`application/setup_database.py`, and in-memory service bundle construction to
`application/service_bundle.py`. Bootstrap resource collection, explicit import,
startup seed, bootstrap result DTOs, and seed payload comparison now live in
`application/setup_resources.py`, `application/setup_importer.py`,
`application/setup_seeder.py`, `application/setup_results.py`, and
`application/setup_payloads.py`; `application/setup.py` is now the public setup
entrypoint instead of owning every seed payload and service assembly rule.
Override create/update/enable/disable lifecycle now lives in
`application/override_actions.py`, and action-attempt audit construction now lives in
`application/action_audit.py`, leaving `SettingsActionService` as the public use-case
coordinator for resource/version actions plus delegation to focused sub-lifecycles.
Resource-version construction, publish/supersede sequencing, resource publish state
mutation, snapshot creation, and snapshot persistence now live in
`application/resource_versioning.py`. Resource create/update orchestration now lives
in `application/resource_definition_actions.py`, publish/rollback orchestration now
lives in `application/resource_publication_actions.py`, and resource enable/disable
delegation lives in `application/resource_actions.py`, reducing
`application/services.py` to a stable public facade over resource actions, override
actions, and operator audit helpers. Settings HTTP action request models, response
projection, request/helper/error-audit logic, execution gate, create/update mutations,
and dry-run/validation handling now live in focused interface helper modules,
reducing `interfaces/http_actions.py` to a thin HTTP boundary and error mapper.
Settings page read-model projection now delegates overview counts/homepage sections
and resource inventory shaping to `application/read_models/pages_overview.py`,
common validation/impact/section helpers to
`application/read_models/pages_common.py`, and audit page/payload projection to
`application/read_models/pages_audits.py`, leaving `pages.py` focused on
kind/resource detail and summary aggregation.
Settings domain aggregates are split out of the former 425-line `domain/entities.py`
into focused resource, resource-version, override, effective-snapshot, action-audit,
and shared entity-normalization modules. `domain/entities.py` remains only the stable
export surface so existing application and infrastructure imports do not become a
second behavior track.
Materialization warning DTOs and payload normalization helpers are split out of
`application/materialization.py`, reducing the materializer to query/cache/warning
coordination plus typed config parser dispatch.
Settings persistence record DTOs now live in
`infrastructure/persistence/records.py`; SQLAlchemy model/record mapping and
timestamp/text normalization live in
`infrastructure/persistence/repository_mappers.py`; domain aggregate conversion and
domain-repository model copy helpers live in
`infrastructure/persistence/domain_repository_mappers.py`. The governance repository
module now owns query/transaction behavior only, while `domain_repositories.py` imports
the shared mapper modules instead of reaching into repository-private helpers. Domain
repository implementations are split by resource/version/override/snapshot/action-audit
family, leaving `domain_repositories.py` as the 74-line service assembly surface.
Current verification:
`PYTHONPATH=src ruff check src/crxzipple/modules/settings/domain src/crxzipple/modules/settings/application src/crxzipple/modules/settings/infrastructure/persistence src/crxzipple/modules/settings/interfaces tests/unit/test_settings_module.py tests/unit/test_settings_http.py tests/unit/test_settings_application_read_models.py tests/unit/test_settings_persistence.py tests/unit/test_settings_environment_setup.py tests/unit/test_settings_materialization.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/settings/domain src/crxzipple/modules/settings/application src/crxzipple/modules/settings/infrastructure/persistence src/crxzipple/modules/settings/interfaces`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_settings_module.py tests/unit/test_settings_http.py tests/unit/test_settings_application_read_models.py tests/unit/test_settings_persistence.py tests/unit/test_settings_environment_setup.py tests/unit/test_settings_materialization.py --tb=short --maxfail=1`
-> 44 passed.
`PYTHONPATH=src ruff check src/crxzipple/modules/settings/application/read_models/pages.py src/crxzipple/modules/settings/application/read_models/pages_overview.py src/crxzipple/modules/settings/application/read_models/pages_common.py src/crxzipple/modules/settings/application/read_models/pages_audits.py src/crxzipple/modules/settings/application/read_models/__init__.py tests/unit/test_settings_application_read_models.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/settings/application/read_models/pages.py src/crxzipple/modules/settings/application/read_models/pages_overview.py src/crxzipple/modules/settings/application/read_models/pages_common.py src/crxzipple/modules/settings/application/read_models/pages_audits.py src/crxzipple/modules/settings/application/read_models/__init__.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_settings_application_read_models.py tests/unit/test_settings_http.py tests/unit/test_settings_materialization.py --tb=short --maxfail=1`
-> 35 passed.

Authorization application follow-up note: tool execution authorization branching now
lives in `application/tool_execution_authorization.py`; `application/services.py`
delegates the decision flow after collecting temporary run/session authorization and
keeps repository access, evaluator access, public facade methods, and audit entrypoint
coordination.
Impact preview DTO/projection logic now lives in `application/policy_impact.py`; the
decision dry-run and impact-preview use cases now live in
`application/decision_use_cases.py`, including audit writes around request/decision
payloads.
Temporary run/session grant construction and scoped temporary authorization aggregation
now live in `application/temporary_grants.py`; temporary run/session grant
creation/storage/audit coordination now lives in `application/temporary_grant_service.py`.
Audit record id/timestamp construction, text normalization, and payload redaction now
live in `application/audit_records.py`; the service decides when to emit audit records.
Policy create/update/enable/delete/import coordination now lives in
`application/policy_lifecycle.py`; agent-managed grant/revoke coordination now lives in
`application/agent_grants.py`.
Authorization HTTP request/domain/response mapping remains in `interfaces/http_payloads.py`;
service lookup lives in `interfaces/http_services.py`; agent-grant response/status
handling lives in `interfaces/http_agent_grants.py`; policy CRUD/import/export
handlers live in `interfaces/http_policy_handlers.py`; dry-run, impact-preview, audit,
and check routes live in `interfaces/http_decision_routes.py`; `interfaces/http.py` is a
policy/grant route composition surface.
Authorization persistence repositories now delegate SQLAlchemy/domain mapping to
`infrastructure/persistence/repository_mappers.py`; repository classes retain query,
commit, bootstrap import, and audit pagination behavior.
Current verification:
`PYTHONPATH=src ruff check src/crxzipple/modules/authorization/application src/crxzipple/modules/authorization/interfaces tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/authorization/application src/crxzipple/modules/authorization/interfaces`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py tests/unit/test_module_architecture_guards.py::test_access_and_authorization_do_not_cross_own_truth_boundaries --tb=short --maxfail=1`
-> 29 passed.
`PYTHONPATH=src ruff check src/crxzipple/modules/authorization/interfaces/http.py src/crxzipple/modules/authorization/interfaces/http_decision_routes.py src/crxzipple/modules/authorization/interfaces/http_models.py src/crxzipple/modules/authorization/interfaces/http_payloads.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/authorization/interfaces/http.py src/crxzipple/modules/authorization/interfaces/http_decision_routes.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_auth_http.py tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py tests/unit/test_module_architecture_guards.py::test_access_and_authorization_do_not_cross_own_truth_boundaries --tb=short --maxfail=1`
-> 33 passed.
`PYTHONPATH=src ruff check src/crxzipple/modules/authorization/application src/crxzipple/modules/authorization/infrastructure src/crxzipple/modules/authorization/interfaces tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/authorization/application src/crxzipple/modules/authorization/infrastructure src/crxzipple/modules/authorization/interfaces`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py tests/unit/test_module_architecture_guards.py::test_access_and_authorization_do_not_cross_own_truth_boundaries --tb=short --maxfail=1`
-> 29 passed.
`PYTHONPATH=src ruff check src/crxzipple/modules/authorization/application src/crxzipple/modules/authorization/interfaces tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/authorization/application src/crxzipple/modules/authorization/interfaces`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py tests/unit/test_module_architecture_guards.py::test_access_and_authorization_do_not_cross_own_truth_boundaries --tb=short --maxfail=1`
-> 29 passed.

Agent HTTP follow-up note: request DTOs now live in
`interfaces/http_request_models.py`; request-to-application input conversion lives in
`interfaces/http_requests.py` with shared private value mappers for register/update
paths; response presenters remain in `interfaces/http_models.py`; resolution endpoint
response DTOs and presenter functions live in `interfaces/http_resolution_models.py`;
Agent service lookup, resolution service construction, and Agent error-to-HTTP mapping
live in `interfaces/http_services.py`. Home migration/config response projection and
profile-list projection live in `interfaces/http_models.py`; `interfaces/http.py` keeps
profile route parsing and owner service calls, while `interfaces/http_home_routes.py`
owns profile-home migration/sync/export/inspect/update endpoints. Current verification:
`python -m ruff check src/crxzipple/modules/agent/interfaces/http.py src/crxzipple/modules/agent/interfaces/http_models.py src/crxzipple/modules/agent/interfaces/http_requests.py`
-> passed;
`PYTHONPATH=src ruff check src/crxzipple/modules/agent/application src/crxzipple/modules/agent/interfaces`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/application src/crxzipple/modules/agent/interfaces`
-> passed;
`PYTHONPATH=src ruff check src/crxzipple/modules/agent/application/resolution.py src/crxzipple/modules/agent/application/resolution_models.py src/crxzipple/modules/agent/application/resolution_values.py src/crxzipple/modules/agent/application/resolution_authorization.py src/crxzipple/modules/agent/application/services.py src/crxzipple/modules/agent/application/home_runtime.py src/crxzipple/modules/agent/application/models.py src/crxzipple/modules/agent/application/event_payloads.py src/crxzipple/modules/agent/interfaces/http.py src/crxzipple/modules/agent/interfaces/http_models.py src/crxzipple/modules/agent/interfaces/http_resolution_models.py src/crxzipple/modules/agent/interfaces/http_requests.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/application/resolution.py src/crxzipple/modules/agent/application/resolution_models.py src/crxzipple/modules/agent/application/resolution_values.py src/crxzipple/modules/agent/application/resolution_authorization.py src/crxzipple/modules/agent/application/services.py src/crxzipple/modules/agent/application/home_runtime.py src/crxzipple/modules/agent/application/models.py src/crxzipple/modules/agent/application/event_payloads.py src/crxzipple/modules/agent/interfaces/http.py src/crxzipple/modules/agent/interfaces/http_models.py src/crxzipple/modules/agent/interfaces/http_resolution_models.py src/crxzipple/modules/agent/interfaces/http_requests.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_agent_http.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1`
-> 23 passed.
`PYTHONPATH=src ruff check src/crxzipple/modules/agent/interfaces/http.py src/crxzipple/modules/agent/interfaces/http_models.py src/crxzipple/modules/agent/interfaces/http_services.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/interfaces/http.py src/crxzipple/modules/agent/interfaces/http_models.py src/crxzipple/modules/agent/interfaces/http_services.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_agent_cli.py tests/unit/test_agent_http.py tests/unit/test_agent_settings_integration.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1`
-> 35 passed.
`PYTHONPATH=src ruff check src/crxzipple/modules/agent/interfaces/http.py src/crxzipple/modules/agent/interfaces/http_home_routes.py src/crxzipple/modules/agent/interfaces/http_models.py src/crxzipple/modules/agent/interfaces/http_requests.py src/crxzipple/modules/agent/interfaces/http_services.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/interfaces/http.py src/crxzipple/modules/agent/interfaces/http_home_routes.py src/crxzipple/modules/agent/interfaces/http_models.py src/crxzipple/modules/agent/interfaces/http_requests.py src/crxzipple/modules/agent/interfaces/http_services.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_agent_cli.py tests/unit/test_agent_http.py tests/unit/test_agent_settings_integration.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1`
-> 35 passed.

Agent CLI follow-up note: register/update payload construction and profile-settings
sync conversion now live in `interfaces/cli_payloads.py`; `interfaces/cli.py` keeps
Typer app composition only. Profile command registration lives in
`interfaces/cli_profile_commands.py`; home command registration lives in
`interfaces/cli_home_commands.py`. Profile sync command registration lives in
`interfaces/cli_profile_sync_commands.py`; enable/disable/delete command registration
lives in `interfaces/cli_profile_state_commands.py`. CLI and HTTP profile sync now
both delegate Settings profile import to
`application/settings_integration.py` instead of carrying duplicate conversion logic.
Current verification:
`PYTHONPATH=src ruff check src/crxzipple/modules/agent/application src/crxzipple/modules/agent/interfaces`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/application src/crxzipple/modules/agent/interfaces`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_agent_cli.py tests/unit/test_agent_http.py tests/unit/test_agent_settings_integration.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1`
-> 35 passed.
`PYTHONPATH=src ruff check src/crxzipple/modules/agent/interfaces/cli_profile_commands.py src/crxzipple/modules/agent/interfaces/cli_profile_sync_commands.py src/crxzipple/modules/agent/interfaces/cli_profile_state_commands.py src/crxzipple/modules/agent/interfaces/cli.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/interfaces/cli_profile_commands.py src/crxzipple/modules/agent/interfaces/cli_profile_sync_commands.py src/crxzipple/modules/agent/interfaces/cli_profile_state_commands.py src/crxzipple/modules/agent/interfaces/cli.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_agent_cli.py tests/unit/test_agent_http.py tests/unit/test_agent_settings_integration.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1`
-> 35 passed.

Agent application follow-up note: application DTOs are split by lifecycle:
profile command/action DTOs live in `application/profile_models.py`, home
migrate/sync/export/snapshot DTOs live in `application/home_models.py`, and
`application/models.py` remains the public export surface. Profile event
payload/action coercion helpers live in `application/event_payloads.py`, and
pure home root/default directory plus runtime preference normalization rules
live in `application/home_runtime.py`.
Home registry lookup/write, home config load/write/apply, scaffold/migration hooks,
runtime preference normalization, and home file read/write snapshot projection now
live in `application/home_operations.py`. Profile lifecycle orchestration now lives in
`application/profile_use_cases.py`, home migrate/sync/export/inspect/file-update
orchestration now lives in `application/home_use_cases.py`, and the shared Agent Unit
of Work protocol lives in `application/unit_of_work.py`. `AgentApplicationService` is
now a public facade and dependency composition point rather than the owner of every
profile/home branch.
Agent home config infrastructure is split behind the stable
`infrastructure/home_config.py` entrypoint: JSON load/atomic write lives in
`home_config_io.py`, profile payload projection lives in `home_config_payloads.py`,
and migration-aware payload helpers plus timestamp/runtime merge helpers live in
`home_config_payload_helpers.py`. The runtime preference compatibility alias and
legacy-shaped helper name have been retired; callers use `resolved_workdir` and
`runtime_payload_from_config_payload` directly.
Registration input to `AgentProfile` construction now lives in
`application/profile_factory.py`, keeping register/sync profile construction,
created-at preservation, and runtime preference normalization in one application helper.
Update input to domain update kwargs conversion now lives in
`application/profile_updates.py`, keeping `UNSET_FIELD` field-presence semantics out of
the service coordinator.
Agent profile resolution DTOs now live in `application/resolution_models.py`,
resolution value coercion helpers live in `application/resolution_values.py`, and
authorization policy-to-agent/tool grant projection rules live in
`application/resolution_authorization.py`. LLM route resolution, Tool catalog
resolution, Access readiness resolution, and Authorization policy query coordination
now live in focused `resolution_llm.py`, `resolution_tools.py`,
`resolution_access.py`, and `resolution_authorization_query.py` helpers.
Agent domain value objects are split behind the stable `domain/value_objects.py`
export surface: identity/instruction values, LLM policy values, execution policy,
memory binding, runtime preferences, and shared value helpers now live in focused
domain modules.
`AgentProfileResolutionQueryService` remains the resolution orchestration point instead
of being the DTO, source-specific projection, and helper owner. Current verification:
`python -m ruff check src/crxzipple/modules/agent/application src/crxzipple/modules/agent/interfaces/http.py src/crxzipple/modules/agent/interfaces/http_models.py src/crxzipple/modules/agent/interfaces/http_requests.py src/crxzipple/modules/agent/__init__.py`
-> passed;
`PYTHONPATH=src ruff check src/crxzipple/modules/agent/application/services.py src/crxzipple/modules/agent/application/home_runtime.py src/crxzipple/modules/agent/application/models.py src/crxzipple/modules/agent/application/event_payloads.py src/crxzipple/modules/agent/interfaces/http.py src/crxzipple/modules/agent/interfaces/http_models.py src/crxzipple/modules/agent/interfaces/http_requests.py`
-> passed;
`PYTHONPATH=src ruff check src/crxzipple/modules/agent/application/resolution.py src/crxzipple/modules/agent/application/resolution_models.py src/crxzipple/modules/agent/application/resolution_values.py src/crxzipple/modules/agent/application/resolution_authorization.py src/crxzipple/modules/agent/application/services.py src/crxzipple/modules/agent/application/home_runtime.py src/crxzipple/modules/agent/application/models.py src/crxzipple/modules/agent/application/event_payloads.py src/crxzipple/modules/agent/interfaces/http.py src/crxzipple/modules/agent/interfaces/http_models.py src/crxzipple/modules/agent/interfaces/http_requests.py`
-> passed;
`python -m ruff check tests/unit/test_agent_http.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --ignore F403,F405`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/application/services.py src/crxzipple/modules/agent/application/home_runtime.py src/crxzipple/modules/agent/application/models.py src/crxzipple/modules/agent/application/event_payloads.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/application/resolution.py src/crxzipple/modules/agent/application/resolution_models.py src/crxzipple/modules/agent/application/resolution_values.py src/crxzipple/modules/agent/application/resolution_authorization.py src/crxzipple/modules/agent/application/services.py src/crxzipple/modules/agent/application/home_runtime.py src/crxzipple/modules/agent/application/models.py src/crxzipple/modules/agent/application/event_payloads.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_agent_http.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1`
-> 23 passed.
`PYTHONPATH=src ruff check src/crxzipple/modules/agent/application src/crxzipple/modules/agent/interfaces`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/application src/crxzipple/modules/agent/interfaces`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_agent_cli.py tests/unit/test_agent_http.py tests/unit/test_agent_settings_integration.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1`
-> 35 passed.
`PYTHONPATH=src ruff check src/crxzipple/modules/agent/domain/runtime_preferences.py src/crxzipple/modules/agent/interfaces/dto.py src/crxzipple/modules/agent/infrastructure/home_config_payload_helpers.py src/crxzipple/modules/agent/infrastructure/home_config_payloads.py`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/domain/runtime_preferences.py src/crxzipple/modules/agent/interfaces/dto.py src/crxzipple/modules/agent/infrastructure/home_config_payload_helpers.py src/crxzipple/modules/agent/infrastructure/home_config_payloads.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_agent_cli.py tests/unit/test_agent_http.py tests/unit/test_agent_settings_integration.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1`
-> 35 passed.
`PYTHONPATH=src ruff check src/crxzipple/modules/agent/domain src/crxzipple/modules/agent/application src/crxzipple/modules/agent/interfaces`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/domain src/crxzipple/modules/agent/application src/crxzipple/modules/agent/interfaces`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_agent_cli.py tests/unit/test_agent_http.py tests/unit/test_agent_settings_integration.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1`
-> 35 passed;
`PYTHONPATH=src ruff check src/crxzipple/modules/agent/domain src/crxzipple/modules/agent/application src/crxzipple/modules/agent/infrastructure src/crxzipple/modules/agent/interfaces`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/domain src/crxzipple/modules/agent/application src/crxzipple/modules/agent/infrastructure src/crxzipple/modules/agent/interfaces`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_agent_cli.py tests/unit/test_agent_http.py tests/unit/test_agent_settings_integration.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1`
-> 35 passed;
`PYTHONPATH=src pytest -q tests/unit/test_module_architecture_guards.py --tb=short --maxfail=1`
-> 18 passed.
`PYTHONPATH=src ruff check src/crxzipple/modules/agent/domain src/crxzipple/modules/agent/application src/crxzipple/modules/agent/infrastructure src/crxzipple/modules/agent/interfaces`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/domain src/crxzipple/modules/agent/application src/crxzipple/modules/agent/infrastructure src/crxzipple/modules/agent/interfaces`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_agent_cli.py tests/unit/test_agent_http.py tests/unit/test_agent_settings_integration.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1`
-> 35 passed.
`PYTHONPATH=src ruff check src/crxzipple/modules/agent/application src/crxzipple/modules/agent/interfaces`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/application src/crxzipple/modules/agent/interfaces`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_agent_cli.py tests/unit/test_agent_http.py tests/unit/test_agent_settings_integration.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1`
-> 35 passed.
`PYTHONPATH=src ruff check tests/unit/test_agent_cli.py tests/unit/test_agent_http.py tests/unit/test_agent_settings_integration.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --ignore F403,F405`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/application src/crxzipple/modules/agent/interfaces`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_agent_cli.py tests/unit/test_agent_http.py tests/unit/test_agent_settings_integration.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1`
-> 35 passed.
`PYTHONPATH=src ruff check src/crxzipple/modules/agent/application src/crxzipple/modules/agent/interfaces`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/application src/crxzipple/modules/agent/interfaces`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_agent_cli.py tests/unit/test_agent_http.py tests/unit/test_agent_settings_integration.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1`
-> 35 passed.

## Wave 5. Support Module Hardening

Purpose: remove small but sharp operational risks.

| Task | Modules | Acceptance |
| --- | --- | --- |
| Add Dispatch concurrent claim tests | dispatch | Done: SQL repository concurrent `claim_next_queued_task` does not duplicate tasks across competing workers, and stale recovery only requeues expired leased claimed tasks without touching live, unleased, or queued tasks |
| Add Daemon lifecycle smoke tests | daemon | Done: fake-process manager smoke covers ensure/start, status refresh, failed-process healthcheck detection, reconcile recovery to desired replicas, and stop behavior without launching real processes |
| Decide Event Relay ownership | event_relay, operations | Done: retained as narrow event-to-Workbench bridge, with Events subscription cursors as progress truth and Operations remaining the durable projection owner |
| Add artifact retention/quota/download authorization | artifacts | Done: service tests cover retention cutoff cleanup, quota pruning, missing underlying files, negative quota rejection, and artifact-root containment; HTTP tests cover metadata/preview/download authorization, missing-file 404s, traversal 404s, and subject-header scoped artifact reads |
| Add Process cleanup/output caps | process | Done: bounded output windows, traversal rejection, stale process refresh, termination CLI cleanup, and terminal-session retention/quota cleanup are tested; cleanup never deletes running sessions |
| Decide Delivery placeholder | delivery, channels, events | Done: empty placeholder retired; future generic Delivery requires a fresh bounded-context design before code appears |

Wave 5 verification:
`PYTHONPATH=src ruff check tests/unit/test_daemon_manager.py`
-> passed;
`PYTHONPATH=src python -m compileall -q tests/unit/test_daemon_manager.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_daemon_manager.py --tb=short --maxfail=1`
-> 25 passed;
`PYTHONPATH=src ruff check src/crxzipple/core src/crxzipple/modules/mobile/infrastructure src/crxzipple/modules/operations src/crxzipple/modules/settings/application/read_models src/crxzipple/modules/tool/application tests/unit/test_config.py tests/unit/test_mobile_domain.py tests/unit/test_operations_observation.py tests/unit/test_settings_application_read_models.py tests/unit/test_tool_cli.py tests/unit/test_tool_background.py tests/unit/test_tool_execution.py tests/unit/test_dispatch.py tests/unit/test_artifacts_http.py tests/unit/test_daemon_manager.py --ignore F403,F405`
-> passed;
`PYTHONPATH=src python -m compileall -q src/crxzipple/core src/crxzipple/modules/mobile/infrastructure src/crxzipple/modules/operations src/crxzipple/modules/settings/application/read_models src/crxzipple/modules/tool/application tests/unit/test_config.py tests/unit/test_mobile_domain.py tests/unit/test_operations_observation.py tests/unit/test_settings_application_read_models.py tests/unit/test_tool_cli.py tests/unit/test_tool_background.py tests/unit/test_tool_execution.py tests/unit/test_dispatch.py tests/unit/test_artifacts_http.py tests/unit/test_daemon_manager.py`
-> passed;
`PYTHONPATH=src pytest -q tests/unit/test_config.py tests/unit/test_mobile_domain.py tests/unit/test_operations_observation.py tests/unit/test_settings_application_read_models.py tests/unit/test_tool_background.py tests/unit/test_tool_execution.py tests/unit/test_dispatch.py tests/unit/test_artifacts_http.py tests/unit/test_daemon_manager.py -k 'not executes_local_background_process_tool_and_updates_lifecycle and not executes_local_inline_process_tool_and_reports_process_context' --tb=short --maxfail=1`
-> 210 passed, 2 deselected;
`PYTHONPATH=src pytest -q tests/unit/test_tool_cli.py -k 'not process and not openapi_provider_commands' --tb=short --maxfail=1`
-> 14 passed, 4 deselected. The deselected Tool CLI/OpenAPI/process cases require
local process-pool or socket-bind capabilities denied by the current sandbox.

## Suggested Verification Commands

Run targeted tests as each wave lands:

```bash
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py tests/unit/test_orchestration_context_workspace_snapshot.py
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py
PYTHONPATH=src pytest -q tests/unit/test_tool_background.py
PYTHONPATH=src pytest -q tests/unit
cd frontend && npm run typecheck && npm run build && npm run audit:operations-layout
```

For long-chain runtime checks:

```bash
make dev-up
source scripts/dev/infra-env.sh
python -m crxzipple.main db upgrade head
python -m crxzipple.main daemon status
```

## Done Definition

A wave is done only when:

- checklist items are implemented without compatibility double-track behavior
- module docs are updated with the new boundary
- relevant tests pass
- Workbench/Operations behavior is verified for at least one active run
- LLM request preview confirms only selected provider input is sent
- no task-specific core logic was introduced
