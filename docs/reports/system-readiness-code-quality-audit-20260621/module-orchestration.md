# Module Audit: orchestration

## Verdict

High importance, medium-high risk. The module is moving in the right direction as the runtime coordinator, but it remains one of the largest and most coupled modules. Execution chain lifecycle, worker CLI, benchmark runtime support, executor benchmark command registration, domain export surface, engine DTO/helper seams, engine outcome projection, execution-chain persistence repositories, coordinator execution-payload helpers, run queue/session/worker/terminal lifecycle methods, maintenance context-budget/compaction flows, runtime request draft models/session/payload helpers, waiting approval recovery, and session tool-result projection are now split into focused modules and guarded by regression coverage; remaining risk is concentrated in remaining tool-wait recovery breadth and long-chain performance/race invariants.

## Evidence

- 140 Python files, about 31602 lines.
- Cross-module import signal: very high.
- `application/engine.py` is now 747 lines after DTO/context, provider/request helper, and outcome projection extraction. `interfaces/worker_cli_executor.py` is now 425 lines after executor benchmark command extraction; `application/engine_session_recorder.py` is now 479 lines after tool-result session projection extraction; `application/coordinators/waiting.py` is now 424 lines after approval recovery extraction; `application/runtime_llm_request_draft.py` is now 511 lines after draft model, session replay, and payload helper extraction; `application/maintenance.py` is now 303 lines after context-budget, compaction-summary, auto-compaction, and run-classification extraction; `domain/run_entity.py` is now 475 lines; `domain/run_queue_lifecycle.py`, `domain/run_worker_lifecycle.py`, and `domain/run_terminal_lifecycle.py` now own queue/session binding, worker lease, and terminal state transitions; `application/coordinators/progress.py` is now 373 lines after shared execution-payload helper extraction; `infrastructure/persistence/repositories.py` is now 626 lines after execution-chain repository extraction; `interfaces/worker_cli_benchmark.py` is now 593 lines after common benchmark helpers and synthetic tool-IO runtime extraction; `domain/entities.py` is now a 17-line export surface.

## Findings

- Boundary direction is mostly correct: orchestration coordinates LLM, Tool, Session, Context Workspace, Dispatch, and Operations facts without owning all internal truths.
- Lifecycle is easier to audit after execution-chain state machine extraction, but run advancement still crosses engine, execution service, session recorder, LLM invoker, tool executor, and maintenance.
- The production worker CLI root and executor command module are now thinner; executor benchmark command registration is isolated in `worker_cli_executor_benchmarks.py`, while benchmark execution/synthetic support remains isolated in the benchmark helper modules.
- Domain aggregate exports are now thin; remaining aggregate review belongs in focused run/execution/ingress/executor-lease files rather than the export surface.
- Recent tool execution cleanup is positive: batch runner, records, grouping, dispatch guard, control decision, and result recorder are now separate.

## Launch Risks

- A long-chain failure can still be hard to localize because run, step, session item, LLM response item, tool run, and context snapshot references cross several paths.
- Multi-user concurrency depends on dispatch/lease/queue invariants; these need explicit tests and metrics.
- Worker CLI production entrypoints are thinner, but executor command and benchmark surfaces still need periodic checks so operator-only code does not leak into runtime ownership.

## Recommendations

- Add executable lifecycle invariant tests for every run step: LLM invocation, response items, session item writes, tool runs, execution chain items, context render snapshot refs.
- Continue reducing remaining tool-wait recovery breadth and add long-chain invariants around the newly split seams.
- Keep orchestration from reabsorbing Context Workspace render or provider-specific request logic.

## Detailed Pass 1

### Files Reviewed

- `application/engine.py`
- `application/execution_chain_lifecycle.py`
- `application/runtime_llm_request_draft.py`
- `application/engine_session_recorder.py`
- `application/engine_tool_executor.py`
- `application/tool_execution_batch_runner.py`
- `application/service_graph.py`
- `interfaces/worker_cli.py`
- `domain/entities.py`
- `infrastructure/persistence/repositories.py`

### File-Level Assessment

`application/engine.py` was 1113 lines and is now a 747-line advancement coordinator.
Engine DTO/context records live in `engine_models.py`; request option,
continuation, metadata, response-format, id-deduplication, and terminal diagnostic
helpers live in `engine_runtime_helpers.py`; and outcome projection, tool execution
context attributes, and background tool-call intent fallback live in
`engine_outcomes.py`. The file still owns the central advancement loop, but request
assembly and outcome shaping are no longer embedded in the coordinator.

`application/execution_chain_lifecycle.py` was 1552 lines and is now a 62-line export
layer after splitting bootstrap, LLM item lifecycle, tool item lifecycle, approval
lifecycle, session item materialization, common state helpers, terminal/final-response
policy, contracts, and id/correlation factories into focused modules.

`interfaces/worker_cli.py` was 2416 lines and is now a 37-line export/composition layer
after splitting executor commands, scheduler commands, shared runtime helpers, and
benchmark/synthetic runtime support. Benchmark code remains available but isolated from
the normal production worker path.

`interfaces/worker_cli_benchmark.py` was 1086 lines and is now a 593-line benchmark
command executor after extracting common benchmark run creation/status/daemon wait
helpers into `worker_cli_benchmark_common.py` and synthetic tool-IO LLM/tool runtime
support into `worker_cli_benchmark_synthetic.py`.

`interfaces/worker_cli_executor.py` was 813 lines and is now a 425-line production
executor command registration module after moving executor benchmark command
registration and lazy benchmark dispatch wrappers into
`worker_cli_executor_benchmarks.py`. The CLI surface is unchanged, but the
production executor commands no longer carry benchmark option declarations in the
same file. Architecture coverage now includes the new benchmark registration file
in the lazy-import guard.

Recent extraction of tool execution batch pieces is positive. `engine_tool_executor.py`
is small and delegates to `ToolExecutionBatchRunner`, while tool execution
records/grouping/guard/control/result recorder now hold formal responsibilities.

`infrastructure/persistence/repositories.py` was 1084 lines and is now a 626-line
run/wait/ingress/executor-lease repository module after moving execution-chain,
execution-step, and execution-step-item repositories to
`execution_chain_repositories.py`.

`domain/run_entity.py` was 933 lines and is now a 475-line run aggregate after moving
route/session binding/enqueue/resume into `domain/run_queue_lifecycle.py`, worker
claim/heartbeat/lease recovery into `domain/run_worker_lifecycle.py`, and
complete/fail/cancel terminal transitions into `domain/run_terminal_lifecycle.py`.
The aggregate keeps ownership of state fields, acceptance, and waiting/approval/tool
state transitions; the new mixins only group lifecycle methods around the same
aggregate state.

`application/coordinators/waiting.py` was 986 lines and is now 424 lines after
moving recovery-contract payload construction, terminal tool-run summary
projection, enum/text normalization, and resume-reason policy to
`waiting_recovery_payloads.py`. Shared LLM execution-step summary,
continuation-payload, tool-run-link, assistant-progress/session-item id, failed
LLM payload, and final-response summary helpers now live in
`coordinators/execution_payloads.py`; `progress.py` and `waiting.py` consume the
same helpers while preserving their previous differences around provider
continuation state and `llm_invocation_id` summary inclusion.
Approval replay, approval replay failure, replayed background-tool wait, replayed
tool-batch materialization, approval resume metadata, terminal tool-run marking,
and approval replay tool-result lookup now live in
`coordinators/waiting_approval_recovery.py`.

`application/maintenance.py` was 906 lines and is now a 303-line public
maintenance service facade. Preflight context-budget detection, context-window
threshold calculation, render-preview metrics, and session pressure helpers live
in `maintenance_context_budget.py`; compaction-summary session materialization
lives in `maintenance_compaction_summary.py`; and post-run/pre-compaction
follow-up scheduling lives in `maintenance_auto_compaction.py`. Run
classification and context-limit error recognition live in
`maintenance_run_classification.py`. The service keeps run lookup, refresh,
rewind, preflight attempt recording, and public composition dependencies.

`application/runtime_llm_request_draft.py` was 833 lines and is now a 511-line
collector focused on runtime request fact collection and LLM resolution.
`runtime_llm_request_draft_models.py` owns the draft DTO, session draft context,
and skill runtime request port. `runtime_llm_request_draft_session.py` owns
active-session replay-window selection and transcript construction.
`runtime_llm_request_draft_payloads.py` owns routing input and transcript-policy
payload projection.

`application/engine_session_recorder.py` was 805 lines and is now a 479-line
session-write coordinator. Tool result session item construction, tool-result
envelope projection, model-facing tool error guidance, metadata filtering, and
background tool execution-step reference resolution now live in
`engine_session_tool_results.py`. The recorder still decides when to append
inbound messages, LLM response items, tool-call records, and tool-result records,
but it no longer owns the tool-result payload format details.

### Boundary Cleanliness

The module is correctly positioned as coordinator. Current coupling is high because orchestration necessarily talks to LLM, Tool, Session, Context Workspace, Dispatch, Access/Authorization, and Operations. This coupling is acceptable only through ports/query services.

Risk pattern:

- `service_graph.py` imports many application services and may become a hidden facade if exposed outside the module.
- `runtime_llm_request_draft.py` and context integration must not turn orchestration into provider prompt assembler.
- Execution chain summary logic must not duplicate Workbench or Operations projection logic.

### Lifecycle Clarity

Lifecycle is the most important concern:

1. inbound request creates/continues run and turn
2. runtime request draft is built
3. LLM invocation happens in LLM owner
4. response items are recorded
5. tool calls become Tool owner runs
6. tool results become session/tool/execution chain facts
7. continuation decision advances or terminates run
8. Workbench/Operations observe through projections

This chain is architecturally sound, but the implementation spans enough files that invariant tests are mandatory before multi-user launch.

### Persistence And Efficiency

Repository files show substantial SQL usage, which is expected for durable run/turn/chain facts. Efficiency risk comes from lifecycle materialization repeatedly querying or reconstructing chain state.

Risk:

- Execution chain lifecycle may perform repeated active-step lookup/ensure operations.
- Long-chain runs can accumulate many items, and step materialization must avoid O(n²) behavior.

### Concurrency And Multi-User Readiness

Concurrency depends on scheduler, dispatch tasks, leases, lane locks, run assignment, and terminal status checks. The code has these concepts, but correctness must be proven by tests:

- duplicate worker claim
- run cancellation while tools are executing
- approval wait/resume races
- background tool completion after run terminal
- continuation after LLM/tool failure

### External Integration Readiness

External systems should integrate via orchestration submit/query/control APIs and events, not internal service graph or worker CLI. Worker CLI should remain operator/runtime only.

### Remediation Checklist

- [x] Split `worker_cli.py` into CLI parser/composition, worker runtime loop commands, scheduler commands, diagnostics/runtime helpers, and benchmark support.
- [x] Split `worker_cli_benchmark.py` into benchmark command flow, common run/status helpers, and synthetic tool-IO runtime support.
- [x] Split executor benchmark command registration out of the production executor CLI command module.
- [x] Split `execution_chain_lifecycle.py` into LLM item lifecycle, tool item lifecycle, approval lifecycle, session item materialization, step terminal/final-response policy, contracts, id/correlation factories, and common state helpers.
- [x] Split `engine.py` DTO/context records, provider/request helper logic, and outcome projection into focused engine modules.
- [x] Split execution-chain SQLAlchemy repositories out of the run/wait/ingress/executor-lease persistence module.
- [x] Split duplicated progress/waiting execution-payload helpers and waiting recovery-contract payload helpers.
- [x] Split waiting approval replay/recovery state-machine helpers out of the public wait coordinator.
- [x] Split run aggregate queue/session binding, worker lease, and terminal lifecycle methods into focused domain mixins.
- [x] Split maintenance context-budget, compaction-summary, auto-compaction follow-up, and run-classification logic out of the public maintenance service.
- [x] Split runtime request draft DTO, session replay/transcript construction, and routing/transcript-policy payload helpers out of the collector.
- [x] Split tool-result session item construction and envelope/background reference projection out of the engine session recorder.
- [x] Add invariant tests for execution-chain bootstrap, LLM step lifecycle, tool materialization, approval terminal handling, continuation decisions, and final response materialization.
- [x] Add race tests for cancellation, approval, background tool completion, and duplicate assignment.
- [x] Add query-count/performance tests for long execution chains.
- [x] Ensure `ServiceGraph` is never exported as a cross-module API.

### Remediation Verification

Additional engine model/runtime-helper split verification:

```bash
python -m ruff check src/crxzipple/modules/orchestration/application/engine.py src/crxzipple/modules/orchestration/application/engine_models.py src/crxzipple/modules/orchestration/application/engine_runtime_helpers.py tests/unit/test_llm_runtime_request_factory_builder.py tests/unit/test_orchestration_context_workspace_snapshot.py --ignore F403,F405
python -m compileall -q src/crxzipple/modules/orchestration/application/engine.py src/crxzipple/modules/orchestration/application/engine_models.py src/crxzipple/modules/orchestration/application/engine_runtime_helpers.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py::test_engine_carries_context_contract_metadata_for_llm_invocation tests/unit/test_llm_runtime_request_factory_builder.py --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_orchestration_tools.py tests/unit/test_orchestration_context.py tests/unit/test_orchestration_context_workspace_snapshot.py --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_orchestration_memory.py tests/unit/test_request_render_input_projection.py --tb=short --maxfail=1
```

Result:

- Orchestration engine ruff and compile checks: passed
- Request factory/context metadata focused suite: 37 passed
- Orchestration tools/context/context snapshot suite: 92 passed
- Orchestration memory/request render suite: 22 passed

Additional engine outcome projection split verification:

```bash
PYTHONPATH=src ruff check src/crxzipple/modules/orchestration/application/engine.py src/crxzipple/modules/orchestration/application/engine_outcomes.py
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/orchestration/application/engine.py src/crxzipple/modules/orchestration/application/engine_outcomes.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_execution_chain.py --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_orchestration_tools.py -k 'tool_call or tool_result or background or inline' --tb=short --maxfail=1
```

Result:

- Engine outcome ruff and compile checks: passed
- Orchestration execution-chain suite: 32 passed
- Orchestration context snapshot suite: 38 passed
- Orchestration tools outcome-focused subset: 16 passed, 21 deselected

Additional run aggregate lifecycle split verification:

```bash
PYTHONPATH=src ruff check src/crxzipple/modules/orchestration/domain/run_entity.py src/crxzipple/modules/orchestration/domain/run_queue_lifecycle.py src/crxzipple/modules/orchestration/domain/run_worker_lifecycle.py src/crxzipple/modules/orchestration/domain/run_terminal_lifecycle.py
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/orchestration/domain/run_entity.py src/crxzipple/modules/orchestration/domain/run_queue_lifecycle.py src/crxzipple/modules/orchestration/domain/run_worker_lifecycle.py src/crxzipple/modules/orchestration/domain/run_terminal_lifecycle.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_queue.py tests/unit/test_orchestration_execution_chain.py --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_orchestration_executor_leases.py tests/unit/test_workbench_read_model.py tests/unit/test_operations_orchestration_projection_diagnostics.py --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_orchestration_tools.py tests/unit/test_orchestration_context.py tests/unit/test_orchestration_context_workspace_snapshot.py --tb=short --maxfail=1
```

Result:

- Run aggregate lifecycle ruff and compile checks: passed
- Queue/execution-chain suite: 68 passed
- Executor lease/workbench/operations projection suite: 49 passed
- Orchestration tools/context/context snapshot suite: 92 passed

Additional worker CLI benchmark split verification:

```bash
python -m ruff check src/crxzipple/modules/orchestration/interfaces/worker_cli_benchmark.py src/crxzipple/modules/orchestration/interfaces/worker_cli_benchmark_common.py src/crxzipple/modules/orchestration/interfaces/worker_cli_benchmark_synthetic.py tests/unit/test_orchestration_cli.py --ignore F403,F405
python -m compileall -q src/crxzipple/modules/orchestration/interfaces/worker_cli_benchmark.py src/crxzipple/modules/orchestration/interfaces/worker_cli_benchmark_common.py src/crxzipple/modules/orchestration/interfaces/worker_cli_benchmark_synthetic.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_cli.py -k 'benchmark_runtime or benchmark_tool_io or benchmark_daemon_runtime' --tb=short --maxfail=1
```

Result:

- Worker CLI benchmark ruff and compile checks: passed
- Worker CLI benchmark focused suite: 6 passed, 26 deselected

Additional executor benchmark command registration split verification:

```bash
PYTHONPATH=src ruff check src/crxzipple/modules/orchestration/interfaces/worker_cli_executor.py src/crxzipple/modules/orchestration/interfaces/worker_cli_executor_benchmarks.py
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/orchestration/interfaces/worker_cli_executor.py src/crxzipple/modules/orchestration/interfaces/worker_cli_executor_benchmarks.py
PYTHONPATH=src pytest -q tests/unit/test_app_assembly_architecture.py::test_orchestration_worker_cli_keeps_benchmark_runtime_lazy --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_orchestration_cli.py -k 'benchmark_runtime or benchmark_tool_io or benchmark_daemon_runtime' --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_orchestration_cli.py -k 'heartbeat_executor or list_executor_leases or runtime_metrics or heartbeat_assignment or advance_assignment or wait_assignment_on_tool or complete_assignment or fail_assignment' --tb=short --maxfail=1
```

Result:

- Executor CLI ruff and compile checks: passed
- Benchmark lazy-import architecture guard: 1 passed
- CLI benchmark command subset: 6 passed, 26 deselected
- CLI executor command subset: 2 passed, 30 deselected
- Full `tests/unit/test_orchestration_cli.py` reached 18 passed and then stopped on
  `PermissionError: [Errno 1] Operation not permitted` while binding the local
  sample LLM HTTP server under this sandbox.

Additional execution-chain repository split verification:

```bash
python -m ruff check src/crxzipple/modules/orchestration/infrastructure/persistence/repositories.py src/crxzipple/modules/orchestration/infrastructure/persistence/execution_chain_repositories.py src/crxzipple/modules/orchestration/infrastructure/persistence/__init__.py src/crxzipple/shared/infrastructure/sqlalchemy_uow.py tests/unit/test_orchestration_execution_chain.py --ignore F403,F405
python -m compileall -q src/crxzipple/modules/orchestration/infrastructure/persistence/repositories.py src/crxzipple/modules/orchestration/infrastructure/persistence/execution_chain_repositories.py src/crxzipple/modules/orchestration/infrastructure/persistence/__init__.py src/crxzipple/shared/infrastructure/sqlalchemy_uow.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_execution_chain.py --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_orchestration_queue.py tests/unit/test_orchestration_executor_leases.py --tb=short --maxfail=1
```

Result:

- Orchestration persistence ruff and compile checks: passed
- Orchestration execution-chain persistence suite: 32 passed
- Orchestration queue/executor lease suite: 68 passed

Additional coordinator execution-payload helper split verification:

```bash
PYTHONPATH=src ruff check src/crxzipple/modules/orchestration/application/coordinators/progress.py src/crxzipple/modules/orchestration/application/coordinators/waiting.py src/crxzipple/modules/orchestration/application/coordinators/waiting_approval_recovery.py src/crxzipple/modules/orchestration/application/coordinators/execution_payloads.py src/crxzipple/modules/orchestration/application/coordinators/waiting_recovery_payloads.py
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/orchestration/application/coordinators/progress.py src/crxzipple/modules/orchestration/application/coordinators/waiting.py src/crxzipple/modules/orchestration/application/coordinators/waiting_approval_recovery.py src/crxzipple/modules/orchestration/application/coordinators/execution_payloads.py src/crxzipple/modules/orchestration/application/coordinators/waiting_recovery_payloads.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_execution_chain.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_tools.py tests/unit/test_orchestration_context.py tests/unit/test_orchestration_context_workspace_snapshot.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_memory.py tests/unit/test_request_render_input_projection.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_approval.py tests/unit/test_orchestration_tools.py tests/unit/test_orchestration_execution_chain.py --tb=short --maxfail=1
```

Result:

- Coordinator ruff and compile checks: passed
- Orchestration execution-chain suite: 32 passed
- Orchestration tools/context/context snapshot suite: 92 passed
- Orchestration memory/request render suite: 22 passed
- Approval/tools/execution-chain focused suite: 86 passed

Additional engine session recorder tool-result projection split verification:

```bash
PYTHONPATH=src ruff check src/crxzipple/modules/orchestration/application/engine_session_recorder.py src/crxzipple/modules/orchestration/application/engine_session_tool_results.py
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/orchestration/application/engine_session_recorder.py src/crxzipple/modules/orchestration/application/engine_session_tool_results.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_execution_chain.py::test_background_tool_result_message_uses_execution_item_reference --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py::test_session_adapter_renders_tool_result_envelope_refs --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_runtime_transcript.py -k tool_result_envelope --tb=short --maxfail=1
```

Result:

- Engine session recorder ruff and compile checks: passed
- Background tool-result execution reference test: 1 passed
- Context workspace tool-result envelope rendering test: 1 passed
- Runtime transcript tool-result envelope replay test: 1 passed, 15 deselected

Additional maintenance split verification:

```bash
PYTHONPATH=src ruff check src/crxzipple/modules/orchestration/application/maintenance.py src/crxzipple/modules/orchestration/application/maintenance_context_budget.py src/crxzipple/modules/orchestration/application/maintenance_compaction_summary.py src/crxzipple/modules/orchestration/application/maintenance_auto_compaction.py src/crxzipple/modules/orchestration/application/maintenance_run_classification.py
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/orchestration/application/maintenance.py src/crxzipple/modules/orchestration/application/maintenance_context_budget.py src/crxzipple/modules/orchestration/application/maintenance_compaction_summary.py src/crxzipple/modules/orchestration/application/maintenance_auto_compaction.py src/crxzipple/modules/orchestration/application/maintenance_run_classification.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_memory.py -k 'compaction or preflight or context_budget' --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_orchestration_context.py::OrchestrationContextTestCase::test_process_next_orchestration_assignment_scales_context_budget_to_llm_context_window --tb=short --maxfail=1
```

Result:

- Maintenance ruff and compile checks: passed
- Orchestration memory compaction/preflight focused suite: 6 passed, 13 deselected
- Context-budget scaling regression: 1 passed

Additional runtime request draft split verification:

```bash
PYTHONPATH=src ruff check src/crxzipple/modules/orchestration/application/runtime_llm_request_draft.py src/crxzipple/modules/orchestration/application/runtime_llm_request_draft_models.py src/crxzipple/modules/orchestration/application/runtime_llm_request_draft_session.py src/crxzipple/modules/orchestration/application/runtime_llm_request_draft_payloads.py
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/orchestration/application/runtime_llm_request_draft.py src/crxzipple/modules/orchestration/application/runtime_llm_request_draft_models.py src/crxzipple/modules/orchestration/application/runtime_llm_request_draft_session.py src/crxzipple/modules/orchestration/application/runtime_llm_request_draft_payloads.py
PYTHONPATH=src pytest -q tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_llm_runtime_request_factory_builder.py tests/unit/test_request_render_input_projection.py --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py::test_engine_carries_context_contract_metadata_for_llm_invocation --tb=short --maxfail=1
```

Result:

- Runtime request draft ruff and compile checks: passed
- Draft collector/request factory/request-render suite: 52 passed
- Context contract metadata regression: 1 passed

Historical broader split-wave verification:

Command passed after the current Orchestration split wave:

```bash
PYTHONPATH=src pytest -q tests/unit/test_orchestration_execution_chain.py tests/unit/test_orchestration_approval.py tests/unit/test_orchestration_tools.py tests/unit/test_orchestration_tool_resource_policy.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_context.py tests/unit/test_orchestration_llm_invoker.py tests/unit/test_orchestration_llm_service_adapter.py tests/unit/test_orchestration_service_surface.py tests/unit/test_orchestration_queue.py tests/unit/test_orchestration_executor_leases.py tests/unit/test_orchestration_cli.py tests/unit/test_app_assembly_architecture.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_module_architecture_guards.py::test_orchestration_service_graph_is_not_cross_module_api tests/unit/test_orchestration_service_surface.py::OrchestrationServiceSurfaceTests::test_service_graph_is_not_a_public_orchestration_surface tests/unit/test_orchestration_service_surface.py::OrchestrationServiceSurfaceTests::test_runtime_assembly_does_not_expose_service_graph --tb=short
```

Result:

- Orchestration targeted suite: 299 passed in 6:50
- ServiceGraph boundary focus tests: 3 passed

Command passed for focused race coverage:

```bash
PYTHONPATH=src pytest -q tests/unit/test_orchestration_queue.py::OrchestrationQueueTestCase::test_cancel_run_keeps_it_out_of_queue tests/unit/test_orchestration_queue.py::OrchestrationQueueTestCase::test_continuation_queue_is_idempotent_when_duplicate_insert_races tests/unit/test_orchestration_executor_leases.py::OrchestrationExecutorLeaseTestCase::test_executor_capacity_claim_is_atomic_guard tests/unit/test_orchestration_approval.py::OrchestrationApprovalTestCase::test_background_tool_call_can_wait_for_approval_then_transition_to_tool_wait --tb=short
```

Result:

- Orchestration race coverage suite: 4 passed

Command passed for long-chain query-count coverage:

```bash
PYTHONPATH=src pytest -q tests/unit/test_orchestration_execution_chain.py::test_execution_chain_snapshot_query_batches_items_for_long_chain tests/unit/test_orchestration_execution_chain.py::test_run_query_service_exposes_execution_chain_read_surface --tb=short
python -m ruff check src/crxzipple/modules/orchestration/application/query.py src/crxzipple/modules/orchestration/domain/repositories.py src/crxzipple/modules/orchestration/infrastructure/persistence/repositories.py tests/unit/test_orchestration_execution_chain.py --ignore F401,I001,E501
```

Result:

- Orchestration long-chain query-count suite: 2 passed
- Ruff focused check: passed
