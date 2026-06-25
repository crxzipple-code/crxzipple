# Module Audit: orchestration

## Verdict

High importance, medium-high risk. The module is moving in the right direction as the runtime coordinator, but it remains one of the largest and most coupled modules. Execution chain lifecycle and worker CLI are now split into focused modules and guarded by a broad regression suite; remaining risk is concentrated in the central engine, domain aggregate breadth, persistence, runtime request draft, and long-chain performance/race invariants.

## Evidence

- 114 Python files, about 30953 lines.
- Cross-module import signal: very high.
- Large files include `domain/entities.py` (1804), `application/engine.py` (1113), `interfaces/worker_cli_benchmark.py` (1086), `infrastructure/persistence/repositories.py` (1048), `application/coordinators/waiting.py` (986), `application/maintenance.py` (877), `application/runtime_llm_request_draft.py` (833), `interfaces/worker_cli_executor.py` (813), and `application/engine_session_recorder.py` (805).

## Findings

- Boundary direction is mostly correct: orchestration coordinates LLM, Tool, Session, Context Workspace, Dispatch, and Operations facts without owning all internal truths.
- Lifecycle is easier to audit after execution-chain state machine extraction, but run advancement still crosses engine, execution service, session recorder, LLM invoker, tool executor, and maintenance.
- The production worker CLI root is now a thin export/composition layer; benchmark/synthetic support is isolated in `worker_cli_benchmark.py`.
- Domain entity file is large; it should be reviewed for aggregate boundaries and value-object extraction.
- Recent tool execution cleanup is positive: batch runner, records, grouping, dispatch guard, control decision, and result recorder are now separate.

## Launch Risks

- A long-chain failure can still be hard to localize because run, step, session item, LLM response item, tool run, and context snapshot references cross several paths.
- Multi-user concurrency depends on dispatch/lease/queue invariants; these need explicit tests and metrics.
- Very large worker CLI can become a hidden production operator surface with inconsistent behavior.

## Recommendations

- Add executable lifecycle invariant tests for every run step: LLM invocation, response items, session item writes, tool runs, execution chain items, context render snapshot refs.
- Continue reducing `engine.py`, domain entities, persistence, and runtime request draft by extracting small policies/value objects.
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

`application/engine.py` has been partially cleaned but still owns the central advancement loop and many helper functions: request metadata, response format, run-level LLM options, tool surface snapshot builder, response item id extraction, continuation state, and terminal diagnostics. This is acceptable only if the helpers remain pure and tested.

`application/execution_chain_lifecycle.py` was 1552 lines and is now a 62-line export
layer after splitting bootstrap, LLM item lifecycle, tool item lifecycle, approval
lifecycle, session item materialization, common state helpers, terminal/final-response
policy, contracts, and id/correlation factories into focused modules.

`interfaces/worker_cli.py` was 2416 lines and is now a 37-line export/composition layer
after splitting executor commands, scheduler commands, shared runtime helpers, and
benchmark/synthetic runtime support. Benchmark code remains available but isolated from
the normal production worker path.

Recent extraction of tool execution batch pieces is positive. `engine_tool_executor.py`
is small and delegates to `ToolExecutionBatchRunner`, while tool execution
records/grouping/guard/control/result recorder now hold formal responsibilities.

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
- [x] Split `execution_chain_lifecycle.py` into LLM item lifecycle, tool item lifecycle, approval lifecycle, session item materialization, step terminal/final-response policy, contracts, id/correlation factories, and common state helpers.
- [x] Add invariant tests for execution-chain bootstrap, LLM step lifecycle, tool materialization, approval terminal handling, continuation decisions, and final response materialization.
- [x] Add race tests for cancellation, approval, background tool completion, and duplicate assignment.
- [x] Add query-count/performance tests for long execution chains.
- [x] Ensure `ServiceGraph` is never exported as a cross-module API.

### Remediation Verification

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
