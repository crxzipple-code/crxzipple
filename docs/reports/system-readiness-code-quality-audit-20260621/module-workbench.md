# Module Audit: workbench

## Verdict

Medium-high importance, medium-low risk after the current projector and HTTP split. Workbench is a projection module, not a truth owner. Timeline, step, run, action, execution, inspector, entity-detail, and interface routes now have focused helper modules and golden/HTTP tests. Remaining risk is concentrated in projection query budgets, long-session pagination, and continued guardrails against fallback/debug leakage.

## Evidence

- 62 Python files, about 7873 lines after focused split-out helpers.
- Workbench application files now top out at 240 lines. The Workbench HTTP root is now 178 lines after catalog, context-tree/snapshot, linked-entity, and trace routes moved into focused interface modules.

## Findings

- Workbench should remain a UI/read model projection over orchestration/session/llm/tool/context facts.
- Timeline and step projector families are now split into focused helper modules, reducing fallback/debug leakage risk.
- Recent split into run, step, timeline, action, execution, tool run, artifact, inspector, entity detail, and diagnostics projectors is positive.
- Trace timeline filtering now keeps run/session observation events when Context Workspace lacks precise object refs, while still filtering events that explicitly point at hidden session/tool/LLM objects.
- Workbench run responses now expose `projection_diagnostics` with owner method sources,
  owner call count, processed item count, timeline item count, and elapsed milliseconds.
  Owner sources are now structured fact declarations (`module`, `facts`, `read_path`);
  actual per-request owner method calls are reported separately as `owner_call_sources`.
- The UI should never display placeholder progress when owner facts are missing.

## Launch Risks

- Timeline may appear inconsistent with actual LLM/tool exchange if projectors use fallback inference.
- Loading current/long sessions can be slow if projection scans too much owner data.
- Linked entity details now have owner-specific payload helpers; remaining risk is pagination/budget controls for larger linked payloads.

## Recommendations

- Add projector-level golden tests from recorded execution chains.
- Track projection cost and owner calls per Workbench request.
- Keep all debug/trace-only fields out of model-visible request paths.
- Keep `read_models.py` as the provider coordination entrypoint; split further only when a new owner query family grows beyond route/projection coordination.

## Detailed Pass 1

### Files Reviewed

- `application/timeline_projector.py`
- `application/step_projector.py`
- `application/read_models.py`
- `application/projection_diagnostics.py`
- `application/entity_details.py`
- `application/inspector_projector.py`
- `application/tool_run_projection.py`
- `application/tool_artifact_projection.py`
- `interfaces/http.py`

### File-Level Assessment

`timeline_projector.py` was 1113 lines and is now 189 lines after moving timeline
refs/sort keys, visibility/debug/duplicate suppression, LLM response-item projection,
and tool lifecycle/interaction merge into focused modules. The public
`WorkbenchRunTimelineProjector` facade remains stable.

`step_projector.py` was 950 lines and is now 208 lines after moving LLM/assistant
progress/continuation views, tool step views, direct fallback views,
approval/missing-access/generic fallback views, and diagnostics into focused modules.

`entity_details.py` was 589 lines and is now a 113-line linked entity detail
facade over focused LLM/provider/replay/tool/value helpers.

`execution_projection.py` and `action_projection.py` have been replaced by focused
execution bundle/status/summary/ref helpers and action link/approval/composition
helpers.

`run_summary_projection.py` has been retired; run identity, time, status,
display key-values, instruction/output text, LLM summary, and metrics now live in
focused projection modules.

`interfaces/http.py` was 508 lines and is now a route composition layer for core
Workbench run/turn endpoints. Catalog, context tree/snapshot, linked entity, and
trace endpoints live in dedicated interface route modules.

`projection_diagnostics.py` owns the thin owner-call counter proxy and processed item
count helper used by run projection. This keeps diagnostics outside UI debug sections and
prevents Workbench from hiding projection cost inside incidental inspector data.

### Boundary Cleanliness

Workbench correctly owns UI read model projection, not runtime facts. It can depend on many owner query services, but it should never infer hidden truth when owner facts are missing.

Risk pattern:

- Timeline visibility logic can become a second runtime interpretation if it drifts
  from owner facts.
- Fallback timeline items can obscure missing owner facts; golden tests now reject
  empty/fallback progress leaks in covered paths.
- Debug/trace details can leak into user-visible primary timeline; visibility helpers
  now centralize suppression for covered paths.

### Lifecycle Clarity

Workbench must render:

- current run/thread summary
- execution steps/items
- LLM response items
- session items
- tool runs/results
- context snapshot refs
- diagnostics and debug panels

These should be projected with stable refs back to owner facts.

### Persistence And Efficiency

Workbench does not own persistence, but read model requests can become expensive if they repeatedly call owner services or scan long execution chains.

### Concurrency And Multi-User Readiness

Workbench must handle active run updates without jumping between turns or rendering stale timelines. Projection should be monotonic and keyed by run/turn/step refs.

### Remediation Checklist

- [x] Split `timeline_projector.py` into response item projector, tool interaction/lifecycle merger, refs/sorting, and visibility policy helpers.
- [x] Split `step_projector.py` by LLM/assistant progress/continuation, tool, approval, missing access, generic fallback, and diagnostics helpers.
- [x] Add golden tests from long-chain timeline runs.
- [x] Keep Trace timeline filtering precise: run/session observation events remain visible, hidden object-ref events are filtered by exact slice refs.
- [x] Add structured owner fact source declarations plus projection cost counters for owner calls and execution items processed.
- [x] Reject empty/fallback progress items in tests for covered timeline paths.
- [x] Split linked entity details by owner concern.
- [x] Split run summary projection into identity/time/status/text/LLM/metrics/display concerns and retire the catch-all module.
- [x] Split Workbench HTTP interface into catalog, context, linked-entity, trace, and root run/turn route modules.

### Remediation Verification

Command passed after the current Workbench split wave:

```bash
PYTHONPATH=src pytest -q tests/unit/test_ui_http.py tests/unit/test_workbench_read_model.py tests/unit/test_module_architecture_guards.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py::UiOperationsHttpTestCase::test_ui_trace_aliases_run_metadata_to_session_events tests/unit/test_ui_operations_http.py::UiOperationsHttpTestCase::test_ui_trace_summary_and_events_use_event_read_model tests/unit/test_ui_operations_http.py::UiOperationsHttpTestCase::test_ui_trace_events_are_gated_by_trace_timeline_slice_refs --tb=short
PYTHONPATH=src pytest -q tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_workbench_reads_llm_trace_from_execution_chain_without_run_metadata tests/unit/test_workbench_read_model.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_module_architecture_guards.py::test_workbench_and_operations_projectors_declare_owner_fact_sources tests/unit/test_workbench_projection_diagnostics.py --tb=short
```

Result:

- Workbench/UI/architecture targeted suite: 47 passed
- Trace timeline exact-ref filtering targeted suite: 3 passed
- Workbench projection diagnostics focus: 13 passed
- Owner fact declaration guard/focus tests: 2 passed
- 2026-06-25 Workbench split continuation:
  `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py tests/unit/test_ui_http.py tests/unit/test_workbench_read_model.py tests/unit/test_workbench_projection_diagnostics.py --tb=short --maxfail=1`
  -> 86 passed.
  `python -m ruff check src/crxzipple/modules/workbench/interfaces src/crxzipple/modules/workbench/application src/crxzipple/app/integration/context_workspace_session.py src/crxzipple/app/integration/context_workspace_session_evidence.py src/crxzipple/app/integration/context_workspace_session_tool_lifecycle.py tests/unit/test_context_workspace_session_adapter.py`
  -> passed.
