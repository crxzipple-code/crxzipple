# PR-Level Remediation Plan Pass 3

Date: 2026-06-21

This plan converts the audit findings into PR-sized work packages. It is designed for iterative cleanup without compatibility double tracks. Each PR should leave the codebase in one coherent structure.

## Sequencing Principles

- Add guard tests before moving side-effect-heavy runtime code.
- Start with pure projection/presenter extraction where behavior can be preserved mechanically.
- Split by stable responsibility, not by arbitrary file length.
- Keep owner modules as data truth. Do not create new projection owners while splitting.
- Do not introduce task-specific logic or migration shims for old internal structures.
- Delete old paths in the same PR once the new path is wired.

## PR 0. Architecture Guard Baseline

Purpose: establish fail-fast rules before structural movement.

Status: in progress. The first executable guard set has landed in `tests/unit/test_module_architecture_guards.py`.

Scope:

- Add module import boundary tests.
- Add tests for forbidden dependencies in the boundary matrix.
- Add minimal smoke fixtures for long-chain owner fact flow.

Files likely touched:

- `tests/unit/`
- `tests/unit/README.md`
- no production code unless small test seams are required

Acceptance:

- [x] Domain packages cannot import FastAPI, SQLAlchemy, Redis, Playwright, infrastructure, or other module domain packages directly.
- [x] Access cannot import Authorization.
- [x] Authorization cannot import Access credential/token infrastructure.
- [x] Orchestration cannot import provider-specific adapter internals.
- [x] Workbench/Operations projector modules are read-only in tests.
- [x] LLM request builders cannot read Session repositories directly.
- [x] Minimal smoke fixture for long-chain owner fact flow.

Current smoke fixture: `tests/unit/test_orchestration_tools.py::OrchestrationToolsTestCase::test_response_items_tool_calls_drive_inline_tool_loop` verifies that LLM invocation, tool run, session tool result, request render snapshot, and follow-up provider input remain connected through owner references.

Suggested command:

```bash
PYTHONPATH=src pytest -q tests/unit
```

Risk:

- Low. This is mostly tests and should be first.

## PR 1. Operations Projection Cost And Owner Fact Declaration

Purpose: make Operations projection behavior measurable before splitting large files.

Status: in progress. Tool, LLM, and Orchestration Operations pages now expose `projection_diagnostics` with owner source declarations, owner call counts, processed item counts, freshness, and elapsed time.

Scope:

- Add lightweight projection cost metadata to Operations read model output or internal diagnostics.
- Add a small declaration/helper for owner fact sources consumed by Tool/LLM/Orchestration Operations projections.
- Do not split the large files yet.

Files likely touched:

- `src/crxzipple/modules/operations/application/read_models/*.py`
- `src/crxzipple/modules/operations/application/read_models/models.py` or equivalent shared model file
- tests for operations read models

Acceptance:

- [x] Tool/LLM/Orchestration Operations pages expose or record projection elapsed time, owner calls/items processed, and projection freshness.
- [x] Each of the three projections declares consumed owner modules.
- [x] No owner module mutation occurs during read model build.

Current verification:

```bash
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py tests/unit/test_operations_llm_read_model.py tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_operations_orchestration_http.py
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py -k 'not trace'
cd frontend && npm run typecheck
```

Suggested command:

```bash
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py
```

Risk:

- Low-medium. It changes read model payload shape only if exposed publicly; prefer additive internal diagnostics unless UI contract intentionally updates.

## PR 2. Split Operations Shared Presenter Utilities

Purpose: reduce duplication and risk in the biggest files with pure helper extraction.

Status: in progress. Shared presenter and route helpers have landed for common health, display, status tone, truncation, and Workbench trace route formatting. Tool, LLM, and Orchestration read models now delegate the equivalent pure helpers while retaining module-specific labels and truncation behavior where semantics differ.

Scope:

- Extract shared display/tone/truncation/date/route helpers from Operations read models.
- Keep behavior identical.
- Do not change owner query logic yet.

Target modules:

- `operations/application/read_models/presenters.py`
- `operations/application/read_models/routes.py`
- optional `operations/application/read_models/table_helpers.py`

Source files:

- `operations/application/read_models/tool.py`
- `operations/application/read_models/llm.py`
- `operations/application/read_models/orchestration.py`

Acceptance:

- [x] Existing operations tests pass for the touched Tool/LLM/Orchestration and HTTP read-model surfaces.
- [x] No endpoint payload changes were introduced by the helper extraction.
- [x] Extracted helpers have focused unit tests for edge cases.

Current verification:

```bash
PYTHONPATH=src pytest -q tests/unit/test_operations_presenters.py
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_read_model.py tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_operations_orchestration_http.py
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py tests/unit/test_ui_operations_http.py -k 'not trace'
PYTHONPATH=src pytest -q tests/unit/test_module_architecture_guards.py
```

Suggested command:

```bash
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py
cd frontend && npm run audit:operations-layout
```

Risk:

- Low. Mostly pure function moves.

## PR 3. Split Operations Tool Read Model

Purpose: break the largest hotspot first.

Status: complete for Tool Operations. Tool run query/filter/pagination rules have moved into `operations/application/read_models/tool_run_filters.py`; tool health/metric cards have moved into `operations/application/read_models/tool_metrics.py`; shared worker online checks have moved into `operations/application/read_models/tool_worker_runtime.py`; projection diagnostics have moved into `operations/application/read_models/tool_projection_diagnostics.py`; orchestration execution-item context lookup has moved into `operations/application/read_models/tool_run_contexts.py`; overview action/queue/risk/worker/type/inline/strategy projection has moved into `operations/application/read_models/tool_overview_sections.py`; worker pool/table projection and worker runtime summary helpers have moved into `operations/application/read_models/tool_worker_sections.py`; worker detail projection has moved into `operations/application/read_models/tool_worker_details.py`; queue/waiting-IO/capability/run-blocker scheduling projection has moved into `operations/application/read_models/tool_scheduling_sections.py`; provider limit/history projection and worker provider limit projection have moved into `operations/application/read_models/tool_provider_sections.py`; tool readiness/access/runtime risk projection has moved into `operations/application/read_models/tool_readiness_sections.py`; lifecycle event collection and event section rendering have moved into `operations/application/read_models/tool_lifecycle_events.py`; tool run table facts, source/trace/progress shaping, and row projection have moved into `operations/application/read_models/tool_run_tables.py`; source/provider/CLI catalog health sections have moved into `operations/application/read_models/tool_source_sections.py`; tool run detail projection, browser-profile detail summary, assignment history, invocation context, and JSON-safe payload shaping have moved into `operations/application/read_models/tool_run_details.py`; error diagnostics have moved into `operations/application/read_models/tool_run_error_diagnostics.py`; artifact/result projection has moved into `operations/application/read_models/tool_run_artifacts.py`. `tool.py` now prepares owner-derived filter inputs, provider labels, and trace context, then delegates pure filtering, health/metric cards, projection diagnostics, orchestration context lookup, overview sections, worker pool/table/detail shaping, scheduling diagnostics, provider limit/history projection, readiness risk projection, lifecycle event projection, source health, provider backend health, tool run table/detail shaping, error facts, result summaries, artifact refs, and artifact sections. `tests/unit/test_operations_tool_read_model.py` now includes a page-contract golden fixture that locks metric ids, tab ids, section ids/counts, tool-run drill-down section ids, and projection cost counters. This keeps owner fact reading in the Tool Operations provider while giving the extracted rules focused unit coverage.

Scope:

- Split `operations/application/read_models/tool.py` by responsibility:
  - query/filter/pagination (done)
  - health/metrics (done)
  - overview actions/types/strategy/risk (done)
  - projection diagnostics (done)
  - orchestration execution-item context lookup (done)
  - tool run tables (done)
  - source/provider backend sections (done)
  - provider limit/history sections (done)
  - worker/queue/capability sections (done: worker pool/table/detail projection and scheduling diagnostics)
  - lifecycle events (done: event collection and section row rendering)
  - detail payloads (done: model, detail projection, browser summary, assignment history, invocation context, JSON-safe payload, artifact/result sections)
  - error/readiness diagnostics (done: tool run error facts and access/runtime readiness risk)
- Preserve public `ToolOperationsReadModelProvider` facade.

Acceptance:

- [x] Tool Operations page renders the same covered core sections after query/filter and table split.
- [x] Golden fixture compares section ids, row counts, metric card ids, and drill-down payload ids.
- [x] Projection cost stays equal or lower than baseline.

Current cost guard: `tests/unit/test_operations_tool_read_model.py::test_tool_operations_source_health_exposes_single_browser_source`
locks the Tool Operations page-level `owner_call_count` and `processed_item_count`;
`tests/unit/test_operations_tool_projection_diagnostics.py` locks the extracted
diagnostics calculator.

Current verification:

```bash
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_run_filters.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_metrics.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_run_tables.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_run_details.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_run_error_diagnostics.py tests/unit/test_operations_tool_run_artifacts.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_source_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_worker_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_worker_details.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_scheduling_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_provider_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_readiness_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_lifecycle_events.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_overview_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_projection_diagnostics.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_run_contexts.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_read_model.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_operations_http.py -k 'tool and not trace'
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py tests/unit/test_operations_tool_read_model.py tests/unit/test_operations_tool_metrics.py tests/unit/test_operations_tool_run_filters.py tests/unit/test_operations_tool_run_tables.py tests/unit/test_operations_tool_run_details.py tests/unit/test_operations_tool_run_error_diagnostics.py tests/unit/test_operations_tool_run_artifacts.py tests/unit/test_operations_tool_source_sections.py tests/unit/test_operations_tool_worker_sections.py tests/unit/test_operations_tool_worker_details.py tests/unit/test_operations_tool_scheduling_sections.py tests/unit/test_operations_tool_provider_sections.py tests/unit/test_operations_tool_readiness_sections.py tests/unit/test_operations_tool_lifecycle_events.py tests/unit/test_operations_tool_overview_sections.py tests/unit/test_operations_tool_projection_diagnostics.py tests/unit/test_operations_tool_run_contexts.py tests/unit/test_operations_presenters.py tests/unit/test_ui_operations_http.py -k 'tool and not trace' tests/unit/test_module_architecture_guards.py
PYTHONPATH=src pytest -q tests/unit/test_module_architecture_guards.py
```

Suggested command:

```bash
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py
cd frontend && npm run audit:operations-layout
```

Risk:

- Medium. Large mechanical split, but mostly projection-only.

## PR 4. Split Operations LLM And Orchestration Read Models

Purpose: finish P1 Operations page projection cleanup.

Status: complete. LLM invocation query/filter/pagination/streaming selection has moved into
`operations/application/read_models/llm_invocation_filters.py`; LLM projection owner-source
and cost diagnostics have moved into `operations/application/read_models/llm_projection_diagnostics.py`;
LLM lifecycle/resolver event source collection has moved into
`operations/application/read_models/llm_lifecycle_events.py`; LLM runtime limiter metric
snapshot and aggregation helpers have moved into
`operations/application/read_models/llm_runtime_metrics.py`; response event grouping/query
helpers have moved into `operations/application/read_models/llm_response_events.py`;
resolver bucket/fallback/facts projection has moved into
`operations/application/read_models/llm_resolver_sections.py`; invocation token,
duration, age, and request-metadata fact helpers have moved into
`operations/application/read_models/llm_invocation_facts.py`; LLM health, overview
metric cards, actions, queue/profile rows, max context label, and invocation reason
display rules have moved into `operations/application/read_models/llm_overview_sections.py`.
Provider access health, auth blockers, model availability, blocked-profile detection,
warmup event selection, and access-readiness display rules have moved into
`operations/application/read_models/llm_provider_sections.py`. Rate limiter summary,
limiter queue, and execution blocking risk projection have moved into
`operations/application/read_models/llm_rate_limiter_sections.py`. Latency, token
usage, invocation rate, and context pressure chart projection have moved into
`operations/application/read_models/llm_usage_sections.py`. Error summary and shared
LLM error classification/retryability rules have moved into
`operations/application/read_models/llm_error_sections.py`. LLM lifecycle event table
projection and event transport/continuation/input-delta labels have moved into
`operations/application/read_models/llm_lifecycle_events.py`. Stream health summary
projection has moved into `operations/application/read_models/llm_stream_sections.py`.
Shared invocation labels/provider render-report access rules have moved into
`operations/application/read_models/llm_invocation_labels.py`; streaming, recent,
and failed invocation table projection has moved into
`operations/application/read_models/llm_invocation_tables.py`. Provider/request
payload preview, runtime request summary, provider context mapping, provider wire
preview, and provider request label projection have moved into
`operations/application/read_models/llm_provider_request_diagnostics.py`. Detail
response item, response-runtime mapping, policy trace, provider response event, and
observed event tables have moved into
`operations/application/read_models/llm_detail_tables.py`. Detail error facts have
been folded into `operations/application/read_models/llm_error_sections.py` so list
and detail error diagnostics share classification and retryability rules.
Orchestration projection owner-source and cost diagnostics have moved into
`operations/application/read_models/orchestration_projection_diagnostics.py`.
Orchestration overview queue, lane-lock, executor rows, and executor capability
labels have moved into
`operations/application/read_models/orchestration_overview_rows.py`.
Orchestration detailed lane-lock and executor sections have moved into
`operations/application/read_models/orchestration_worker_sections.py`.
Orchestration detailed run queue projection has moved into
`operations/application/read_models/orchestration_queue_sections.py`.
Orchestration event log section and event row labels have moved into
`operations/application/read_models/orchestration_event_log_sections.py`.
Orchestration backpressure and stuck-run diagnostics have moved into
`operations/application/read_models/orchestration_backpressure_sections.py`.
Orchestration ingress queue projection and pending-ingress filtering have moved
into `operations/application/read_models/orchestration_ingress_sections.py`.
Orchestration execution chain projection, continuation-decision labels, and
tool-only streak diagnostics have moved into
`operations/application/read_models/orchestration_execution_chain_sections.py`.
Orchestration scheduler status and policy-limit sections have moved into
`operations/application/read_models/orchestration_status_sections.py`, and
repeated-probe/recent-failure sections have moved into
`operations/application/read_models/orchestration_failure_sections.py`.
Orchestration health, failure, ingress-rate, latency, recent-failure, and observer
metric projection has moved into
`operations/application/read_models/orchestration_metrics.py`.
Orchestration Operations action definitions have moved into
`operations/application/read_models/orchestration_actions.py`, and owner runtime fact
reads plus dispatch-task/run grouping helpers have moved into
`operations/application/read_models/orchestration_runtime_facts.py`.
`llm.py` and `orchestration.py` keep the public read-model provider facades
and delegate those pure rules.

Scope:

- Split LLM read model into:
  - invocation query/filter/pagination (done)
  - projection diagnostics (done)
  - lifecycle/resolver event source collection (done)
  - runtime limiter metrics snapshot/aggregation (done)
  - response event grouping/query/retention helpers (done)
  - resolver chart/fallback/facts projection (done)
  - invocation token/duration/request-metadata facts (done)
  - overview health/metrics/actions/queue/profile rows (done)
  - provider access/auth/model availability sections (done)
  - rate limiter and execution blocking risk sections (done)
  - latency/token/invocation-rate/context-pressure chart sections (done)
  - error summary and error classification rules (done)
  - lifecycle event table projection (done)
  - stream health summary section (done)
  - invocation label/provider render-report helpers (done)
  - invocation tables (done)
  - provider/request diagnostics (done)
  - detail response/runtime mapping/event tables (done)
  - detail error facts (done)
- Split Orchestration read model into:
  - projection diagnostics (done)
  - overview queues/lanes/executors rows (done)
  - detailed lane/executor sections (done)
  - detailed run queue section (done)
  - execution chain projection (done)
  - ingress/dispatch projection (done)
  - event log sections (done)
  - backpressure/stuck-run diagnostics (done)
  - scheduler status and policy-limit sections (done)
  - repeated-probe and recent-failure sections (done)
  - health/latency/failure/observer metric projection (done)
  - action definitions and runtime fact helpers (done)

Acceptance:

- LLM and Orchestration pages retain current sections and drill-down payloads.
- Provider diagnostics remain Operations-visible only and do not feed LLM input.
- Projection cost/freshness visible.

Suggested command:

```bash
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_invocation_filters.py tests/unit/test_operations_llm_projection_diagnostics.py tests/unit/test_operations_llm_read_model.py
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_lifecycle_events.py
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_runtime_metrics.py
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_response_events.py tests/unit/test_operations_llm_resolver_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_invocation_facts.py
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_overview_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_provider_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_rate_limiter_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_usage_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_error_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_lifecycle_events.py
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_stream_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_invocation_tables.py
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_provider_request_diagnostics.py
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_detail_tables.py
PYTHONPATH=src pytest -q tests/unit/test_operations_orchestration_execution_chain_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_orchestration_backpressure_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_orchestration_event_log_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_orchestration_ingress_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_orchestration_queue_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_orchestration_worker_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_orchestration_overview_rows.py tests/unit/test_operations_orchestration_projection_diagnostics.py tests/unit/test_ui_operations_orchestration_http.py
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k orchestration --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py
cd frontend && npm run audit:operations-layout
```

Risk:

- Medium. Still projection-only, but many helpers.

## PR 5. Workbench Timeline Golden Fixtures

Purpose: protect user-visible timeline behavior before splitting projectors.

Status: complete. `tests/unit/test_workbench_read_model.py` now includes a
long-chain timeline golden fixture that drives the real
`WorkbenchRunTimelineProjector` through execution steps, LLM response items,
session progress fallback, tool lifecycle items, and final response materialization.
The fixture locks user-visible item order/kinds/titles, turn id stability,
response item source refs, request render snapshot refs, tool interaction source
refs, sanitized tool execution plan content, read handles, hidden reasoning
policy placeholders, suppression of debug-only continuation text, suppression of
raw tool arguments, and de-duplication of session fallback progress when a
provider response item already carries the same assistant progress text.

Scope:

- Add recorded fixture(s) for long-chain run timeline projection. (done)
- Assert stable item ordering, item kinds, titles, source refs, and debug suppression. (done)
- Assert missing owner facts do not create generic progress items. (covered by existing
  empty-progress/helper tests and the new golden fixture's duplicate suppression)

Files likely touched:

- `tests/unit/test_workbench_*`
- fixture files under tests
- minimal Workbench test helper code

Acceptance:

- [x] Golden tests fail if timeline jumps to wrong turn/step.
- [x] Debug-only continuation/control items are not primary timeline items.
- [x] Missing facts are explicit empty/error states.

Current verification:

```bash
PYTHONPATH=src pytest -q tests/unit/test_workbench_read_model.py
```

Risk:

- Low-medium. Test fixtures may need careful stabilization.

## PR 6. Split Workbench Projectors

Purpose: separate timeline/step projection families without behavior change.

Status: complete for the Workbench timeline/step projector split. The public
`WorkbenchRunTimelineProjector` and `WorkbenchRunStepProjector` facades remain
stable, while pure projection families now live in focused modules:

- `timeline_refs.py`: timeline refs, sort keys, timestamp helpers.
- `timeline_visibility.py`: visibility, debug suppression, duplicate suppression.
- `timeline_response_items.py`: LLM response item to timeline item projection.
- `timeline_tool_lifecycle.py`: execution tool lifecycle and tool interaction merge.
- `step_llm_views.py`: assistant progress, continuation, and LLM step views.
- `step_tool_views.py`: tool execution step views.
- `step_support_views.py`: approval, missing-access, and generic fallback views.

Scope:

- Extract from `timeline_projector.py`:
  - response item projection (done)
  - tool interaction projection (done)
  - execution step projection (kept in `timeline_projector.py` as the small
    facade-local step-to-timeline mapper)
  - visibility policy (done)
  - lifecycle merge (done)
  - sorting (done)
- Extract from `step_projector.py`:
  - LLM (done)
  - tool (done)
  - approval (done)
  - continuation (done)
  - missing access (done)
  - generic fallback (done)

Acceptance:

- [x] PR 5 golden tests pass.
- [x] Workbench active run page remains stable under covered HTTP/unit surfaces.
- [x] No Workbench projector writes owner state.

Current verification:

```bash
PYTHONPATH=src pytest -q tests/unit/test_workbench_read_model.py
PYTHONPATH=src pytest -q tests/unit/test_ui_http.py tests/unit/test_workbench_read_model.py tests/unit/test_module_architecture_guards.py
```

Suggested command:

```bash
PYTHONPATH=src pytest -q tests/unit
cd frontend && npm run typecheck
```

Risk:

- Medium. User-visible behavior.

## PR 7. Settings HTTP Presenter And Action Policy Split

Purpose: move governance read model/policy code out of the HTTP router.

Status: completed in this pass.

Scope:

- Extract:
  - overview/detail presenters
  - audit presenters
  - runtime defaults read model and validation
  - action policy/rejection helpers
  - redaction helpers
- Keep HTTP routes as parse/call/serialize.

Files likely touched:

- `settings/interfaces/http.py`
- `settings/application/read_models/pages.py`
- `settings/application/read_models/runtime_defaults.py`
- `settings/application/action_policy.py`
- `settings/application/redaction.py`
- `tests/unit/test_settings_application_read_models.py`

Implemented split:

- `settings/interfaces/http.py`: routes, request DTO, dependency lookup, action execution glue, and HTTP exception mapping.
- `settings/application/read_models/pages.py`: overview, kind/detail, audit page presenters, audit payloads, resolution/impact/validation sections.
- `settings/application/read_models/runtime_defaults.py`: runtime defaults schema, field read model, validation, and apply requirements.
- `settings/application/action_policy.py`: kind aliases, ownership metadata, allowed/blocked actions, owner API/apply policy, action button models.
- `settings/application/redaction.py`: Settings-safe payload conversion plus secret/database URL redaction.

Acceptance:

- [x] Every Settings resource still declares owner, truth source, write path, and runtime apply behavior.
- [x] Module-owned actions remain blocked in Settings and point to owner APIs.
- [x] Redaction tests cover nested secrets, token query strings, database URLs, and token-count exceptions.
- [x] Runtime defaults validation lives outside HTTP and still audits failures through the route glue.
- [x] Settings HTTP output remains covered by existing public/UI prefix tests.

Current verification:

```bash
PYTHONPATH=src pytest -q tests/unit/test_settings_application_read_models.py tests/unit/test_settings_http.py tests/unit/test_settings_materialization.py tests/unit/test_settings_module.py tests/unit/test_settings_persistence.py tests/unit/test_settings_contracts.py tests/unit/test_settings_environment_setup.py
PYTHONPATH=src pytest -q tests/unit/test_ui_http.py tests/unit/test_module_architecture_guards.py
```

Current result:

- Settings targeted suite: 42 passed.
- UI HTTP and architecture guard suite: 34 passed.

Suggested command:

```bash
PYTHONPATH=src pytest -q tests/unit
```

Risk:

- Medium. Governance UI behavior and config safety.

## PR 8. Session Service Split With Replay Tests

Purpose: make Session ledger behavior auditable.

Status: in progress. Session append construction, lifecycle/query DTOs, UoW port, metadata merge, reset policy, item event payload, replay/window slices, and segment compaction rules have moved out of the public application service while keeping a single coherent service surface.

Scope:

- Add replay/compaction tests first if not already present.
- Split `SessionApplicationService` into smaller services while preserving public assembly surface where appropriate:
  - command/query
  - item append
  - replay window
  - compaction
  - metadata
  - routing/reset policy
- Avoid old/new service double track.

Acceptance:

- [x] Reset policy evaluation moved out of `SessionApplicationService`.
- [x] Append item DTO and `SessionItem` construction moved out of `SessionApplicationService`.
- [x] Lifecycle/routing DTOs moved out of `SessionApplicationService`.
- [x] Query/window DTOs moved out of `SessionApplicationService`.
- [x] Session Unit of Work port moved out of `SessionApplicationService`.
- [x] Metadata merge DTO and item metadata merge helper moved out of `SessionApplicationService`.
- [x] Session item appended event payload construction moved out of `SessionApplicationService`.
- [x] Replay window, item range, context frontier, and segment handle read-slice construction moved out of `SessionApplicationService`.
- [x] Segment compaction input/result DTO, normalization, archive metadata, segment metadata, and result projection moved out of `SessionApplicationService`.
- [x] Existing replay/compaction/session HTTP tests still pass after the first split.
- [x] Session item and session instance sequence uniqueness is enforced at the persistence schema boundary.
- [x] Stale concurrent append sequence races are rejected by the persistence schema.
- [x] Append sequence conflicts can be retried through an application-level detector port without leaking SQLAlchemy into Session application logic.
- [x] Session append rejects stale writes into closed or historical segments.
- [x] Segment compaction rejects stale/closed active instances before mutating the ledger.
- [x] Stale concurrent segment rotation sequence races are rejected by the persistence schema.
- [x] Concurrent append/replay/compaction boundary tests pass.
- [x] Replay preserves provider protocol-required items.

Current files:

- `session/application/services.py`: still owns the public application service and UoW transaction flow.
- `session/application/item_append.py`: append DTOs and `SessionItem` construction.
- `session/application/session_lifecycle.py`: ensure/reset/routed-session DTOs and routed-session result objects.
- `session/application/session_queries.py`: list/build/get query DTOs for session items, ranges, segment handles, context frontier, and instances.
- `session/application/unit_of_work.py`: Session repository Unit of Work application port.
- `session/application/session_metadata.py`: metadata merge DTOs and item metadata merge helper.
- `session/application/reset_policy.py`: idle/daily reset decision policy.
- `session/application/item_events.py`: `session.item.appended` fact payload projection.
- `session/application/session_windows.py`: replay window, item range, context frontier, and segment handle read-slice construction.
- `session/application/segment_compaction.py`: segment compaction DTOs, normalization, archive metadata, segment metadata, and result projection.
- `app/assembly/session.py`: wires SQLAlchemy unique-conflict detection into the Session append retry port.
- `session/infrastructure/persistence/models.py`: unique hot-path sequence indexes for session items and instances.
- `alembic/versions/0016_session_hot_path_indexes.py`: session instance sequence index is unique in rebuilt schema.
- `alembic/versions/0073_session_items.py`: session item segment sequence index is unique in rebuilt schema.
- `tests/unit/test_session_reset_policy.py`: reset policy boundary tests.
- `tests/unit/test_session_persistence_contracts.py`: persistence sequence uniqueness contract tests.

Current verification:

```bash
PYTHONPATH=src pytest -q tests/unit/test_session_reset_policy.py tests/unit/test_session.py tests/unit/test_session_segment_compaction.py tests/unit/test_session_http.py
PYTHONPATH=src pytest -q tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_module_architecture_guards.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_compaction_segment_rotation.py tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_module_architecture_guards.py
PYTHONPATH=src pytest -q tests/unit/test_session_segment_compaction.py tests/unit/test_session.py tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_orchestration_compaction_segment_rotation.py tests/unit/test_module_architecture_guards.py
PYTHONPATH=src pytest -q tests/unit/test_session_persistence_contracts.py tests/unit/test_session_http.py tests/unit/test_session_segment_compaction.py tests/unit/test_session.py
PYTHONPATH=src pytest -q tests/unit/test_db_cli.py -k 'db_commands_apply_and_report_revisions'
PYTHONPATH=src pytest -q tests/unit/test_session.py tests/unit/test_session_segment_compaction.py tests/unit/test_session_persistence_contracts.py tests/unit/test_session_http.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_compaction_segment_rotation.py tests/unit/test_sessions_tool_http.py tests/unit/test_context_workspace_session_adapter.py -k 'merge_item_metadata or compaction or historical_range_uses_session_items'
PYTHONPATH=src pytest -q tests/unit/test_module_architecture_guards.py
PYTHONPATH=src pytest -q tests/unit/test_session_reset_policy.py tests/unit/test_session.py tests/unit/test_session_segment_compaction.py tests/unit/test_session_persistence_contracts.py tests/unit/test_session_http.py
PYTHONPATH=src pytest -q tests/unit/test_sessions_tool_http.py -k 'history'
PYTHONPATH=src pytest -q tests/unit/test_orchestration_compaction_segment_rotation.py tests/unit/test_sessions_tool_http.py tests/unit/test_context_workspace_session_adapter.py -k 'merge_item_metadata or compaction or historical_range_uses_session_items'
PYTHONPATH=src pytest -q tests/unit/test_session_cli.py
PYTHONPATH=src pytest -q tests/unit/test_ui_http.py -k 'session'
PYTHONPATH=src pytest -q tests/unit/test_session_segment_compaction.py
PYTHONPATH=src pytest -q tests/unit/test_session_persistence_contracts.py
PYTHONPATH=src pytest -q tests/unit/test_runtime_llm_request_draft_collector.py -k 'active_session_only or protocol_call_ids or replay'
```

Current result:

- Session targeted suite: 32 passed.
- Runtime request draft collector and architecture guard suite: 18 passed.
- Orchestration compaction, runtime request draft collector, and architecture guard suite: 20 passed.
- Session compaction/session, runtime request draft, orchestration compaction, and architecture guard suite: 43 passed.
- Session persistence/session HTTP/compaction/session suite: 32 passed.
- Session/session compaction/persistence/session HTTP suite: 35 passed.
- Session/session compaction/persistence/session HTTP suite after append retry: 36 passed.
- Session reset/session/session compaction/persistence/session HTTP suite after append retry: 39 passed.
- Session reset/session/session compaction/persistence/session HTTP suite after stale historical append guard: 40 passed.
- Sessions tool history regression after stale historical append guard: 2 passed, 10 deselected.
- Session DTO split regression: session reset/session/session compaction/persistence/session HTTP suite 40 passed; orchestration/session-tool/context targeted suite 4 passed, 48 deselected; architecture guard suite 5 passed.
- Session UoW port split regression: session reset/session/session compaction/persistence/session HTTP suite 40 passed; orchestration/session-tool/context targeted suite 4 passed, 48 deselected; architecture guard suite 5 passed.
- Session CLI regression after DTO/UoW split: 5 passed.
- UI HTTP session regression after DTO/UoW split: 3 passed, 26 deselected.
- Session compaction stale active-instance guard: 5 passed.
- Session persistence sequence contracts after segment rotation race coverage: 6 passed.
- Session replay active-segment boundary after compaction: 6 passed in `test_session_segment_compaction.py`.
- PR8 regression bundle after concurrent append/replay/compaction boundary coverage: session reset/session/session compaction/persistence/session HTTP/session CLI suite 48 passed; orchestration/session-tool/context targeted suite 13 passed, 39 deselected; runtime request draft replay-targeted suite 3 passed, 10 deselected; architecture guard suite 5 passed.
- Orchestration compaction, sessions tool HTTP, and Context Workspace session adapter targeted metadata/compaction suite: 4 passed, 48 deselected.
- Architecture guard suite: 5 passed.
- DB migration smoke for current Alembic head: 1 passed, 5 deselected.
- LLM request builders use replay service, not repositories.
- Workbench/Operations still see required session facts after compaction.

Suggested command:

```bash
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit
```

Risk:

- High. Central runtime ledger.

## PR 9. Context Workspace Root Node Split

Purpose: reduce bootstrap/root-node maintenance cost.

Status: complete for the root-node bootstrap split. `root_nodes.py` now keeps
only default ordering, public constant re-exports, and parent lookup. Static
section roots, instruction/agent guidance, run/execution nodes, planning nodes,
resource roots, constants, and shared estimate/payload helpers live in focused
`root_node_*` modules.

Scope:

- Split `context_workspace/application/root_nodes.py` by root family:
  - instructions (done: `root_node_instructions.py`)
  - agent (done: agent identity/home nodes live with instruction seeds)
  - run (done: flow/environment/permission/provider/budget/constraint seeds)
  - execution (done: current execution and continuation seeds)
  - planning (done: goal and working-plan seeds)
  - estimates (done: shared `text_estimate` / runtime-contract estimate helper)
  - resources (done: session/tools/skills/memory/artifact/workspace roots)
- Preserve root ids and parent ids.

Acceptance:

- [x] Root node ids, parent ids, order, metadata, and runtime contract hash/version remain stable.
- [x] LLM provider input receives selected slices only.
- [x] `root_nodes.py` no longer owns per-family seed bodies.
- [x] Historical public constants exported from `root_nodes` remain available for callers/tests.

Current verification:

```bash
python -m py_compile src/crxzipple/modules/context_workspace/application/root_nodes.py src/crxzipple/modules/context_workspace/application/root_node_common.py src/crxzipple/modules/context_workspace/application/root_node_constants.py src/crxzipple/modules/context_workspace/application/root_node_sections.py src/crxzipple/modules/context_workspace/application/root_node_instructions.py src/crxzipple/modules/context_workspace/application/root_node_execution.py src/crxzipple/modules/context_workspace/application/root_node_task.py src/crxzipple/modules/context_workspace/application/root_node_resources.py
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py tests/unit/test_orchestration_context_workspace_snapshot.py
```

Suggested command:

```bash
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py tests/unit/test_orchestration_context_workspace_snapshot.py
```

Risk:

- Low-medium. Bootstrap-heavy, not side-effect-heavy.

## PR 10. Tool Worker Lifecycle Invariant Tests

Purpose: protect side-effect-heavy Tool worker code before extraction.

Status: complete for the first worker lifecycle guard set. Background worker
tests now lock registration/staleness, assignment heartbeat, recovered dispatch
handling, retry exhaustion, background large-result artifact externalization,
result envelope persistence, worker slot release, and dispatch terminal state.
Architecture guards also prevent Tool application code from importing
Orchestration runtime owner layers.

Scope:

- Add tests for:
  - worker registration/staleness (done)
  - assignment heartbeat (done)
  - recovered dispatch task handling (done)
  - failure/retry exhaustion (done)
  - large output artifact externalization (done for background worker path)
  - result envelope merge behavior (done for artifact envelope persistence)

Acceptance:

- [x] Tests cover current `ToolWorkerService` behavior.
- [x] Artifact refs are used for large payloads.
- [x] Failures do not complete orchestration run directly.

Current verification:

```bash
PYTHONPATH=src pytest -q tests/unit/test_tool_background.py
PYTHONPATH=src pytest -q tests/unit/test_module_architecture_guards.py
PYTHONPATH=src pytest -q tests/unit/test_tool_background.py tests/unit/test_tool_execution.py -k 'background or large_text or externalizes'
```

Suggested command:

```bash
PYTHONPATH=src pytest -q tests/unit/test_tool_background.py tests/unit
```

Risk:

- Low-medium as tests; required before runtime split.

## PR 11. Split Tool Worker And Source Services

Purpose: decompose Tool runtime without changing lifecycle semantics.

Status: complete. The worker/source application split is complete for the
current remediation pass: inline attachment,
large-text result, raw-output artifact externalization, and artifact result
envelope merge logic moved from `worker_service.py` into
`tool_result_artifacts.py`. `ToolWorkerService` now delegates result artifact
externalization before detail validation and keeps the execution lifecycle flow.
The first source split is also complete: runtime request bundle DTOs and pure
bundle construction moved from `source_service.py` into
`source_runtime_bundles.py`, while `ToolSourceQueryService` remains responsible
only for loading active source/function records and preserving requested order.
Source requirement payload parsing moved into `source_requirements.py`, so
`source_service.py` no longer owns Access credential/runtime requirement parser
details while still projecting persisted function records into catalog DTOs.
Source entity/record/provider-backend mapping moved into
`source_record_mapping.py`, source merge/change detection moved into
`source_state.py`, source/function event payload formatting moved into
`source_events.py`, and configured source write validation moved into
`source_validation.py`. Worker failure normalization moved into
`worker_errors.py`, and background assignment/worker slot completion moved into
`worker_tracking.py`; worker capability/registry snapshot payload construction
moved into `worker_capabilities.py`, and prepared execution context decoration
moved into `worker_execution_context.py`. Worker result completion/failure
application moved into `worker_completion.py`, and recovered dispatch task
handling moved into `worker_recovery.py`. `ToolWorkerService` still owns the
lifecycle flow and dispatch decisions. Worker registration/stale/prune helpers
moved into `worker_registration.py`, and assignment concurrency selection moved
into `worker_assignment_selection.py`. Worker wakeup waiting moved into
`worker_wakeup.py`, and processing heartbeat threading moved into
`worker_processing_heartbeat.py`. Tool runtime execution, artifact
externalization, and result detail validation moved into
`worker_runtime_execution.py`, with detail validation centralized in
`tool_result_validation.py`. Source command DTOs moved into `source_command_models.py`,
the source UoW protocol moved into `source_unit_of_work.py`, function commands
moved into `source_function_commands.py`, and source command/sync use cases
moved into `source_commands.py`. `source_service.py` is now the source query
service and package-level exports are wired directly to the new owner modules.

Scope:

- Split `ToolWorkerService` into registration (done), assignment loop selection (done), run executor (done), result completion (done), artifact externalization (done), result validation (done), failure normalization (done), background tracking (done), capability payloads (done), execution context decoration (done), recovery (done).
- Split `source_service.py` into source query (done), source commands (done), function commands (done), runtime request bundle builder (done), requirements parser (done), entity/record mapping (done), merge/change state helpers (done), event payload helpers (done), validation helpers (done), UoW protocol (done), command DTOs (done).
- Preserve owner event emission.

Acceptance:

- PR 10 tests pass.
- Source/function command idempotency tests pass.
- Runtime request bundle golden tests pass.

Current verification:

```bash
PYTHONPATH=src pytest -q tests/unit/test_tool_background.py tests/unit/test_tool_execution.py tests/unit/test_tool_workspace.py::ToolWorkspaceTestCase::test_workspace_exec_tool_honors_output_token_budget tests/unit/test_module_architecture_guards.py
PYTHONPATH=src pytest -q tests/unit/test_tool_source_service.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_context_tree_tool.py
PYTHONPATH=src pytest -q tests/unit/test_tool_background.py tests/unit/test_tool_execution.py tests/unit/test_tool_source_service.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_context_tree_tool.py tests/unit/test_module_architecture_guards.py
PYTHONPATH=src pytest -q tests/unit/test_tool_background.py tests/unit/test_tool_execution.py tests/unit/test_tool_source_service.py tests/unit/test_tool_catalog_reconcile.py tests/unit/test_operations_tool_readiness_sections.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_context_tree_tool.py tests/unit/test_module_architecture_guards.py
```

Final verification:

```bash
PYTHONPATH=src pytest -q tests/unit/test_tool_background.py tests/unit/test_tool_execution.py tests/unit/test_tool_source_service.py tests/unit/test_tool_catalog_reconcile.py tests/unit/test_operations_tool_readiness_sections.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_context_tree_tool.py tests/unit/test_module_architecture_guards.py
# 106 passed
```

Residual note:

- `ToolWorkerService` intentionally retains the outer run-loop shell and
  transaction entrypoints; the volatile details now live in focused helpers.

## PR 12. Split CLI Tool Source

Purpose: isolate CLI source safety concerns.

Status: complete. The previous 2100+ line `cli_source.py` is now a thin
facade for source discovery and runtime handler registration. CLI source
configuration and promoted-function parsing live in `cli_source_config.py`;
common scalar/list/numeric parsing lives in `cli_source_config_values.py`;
path and executable validation lives in `cli_source_paths.py`; discovery and
ToolSpec/candidate construction lives in `cli_source_discovery.py`; runtime
help/execute/read/cancel process handling lives in `cli_source_runtime.py`;
process-output observation/event publication lives in
`cli_source_process_observer.py`; credential resolution/temp-file injection
lives in `cli_source_credentials.py`; result/help envelopes live in
`cli_source_envelopes.py`; output redaction lives in
`cli_source_redaction.py`.

Scope:

- Extract:
  - config parsing (done)
  - discovery (done)
  - runtime process execution (done)
  - result/help envelopes (done)
  - redaction (done)
  - credential injection (done)
  - path/executable validation (done)

Acceptance:

- [x] Credential redaction tests pass.
- [x] Direct credential binding source rejection remains enforced.
- [x] Process envelopes remain stable.
- [x] Path validation prevents escaping allowed roots.

Current verification:

```bash
python -m py_compile src/crxzipple/modules/tool/infrastructure/cli_source.py src/crxzipple/modules/tool/infrastructure/cli_source_runtime.py src/crxzipple/modules/tool/infrastructure/cli_source_discovery.py src/crxzipple/modules/tool/infrastructure/cli_source_config.py src/crxzipple/modules/tool/infrastructure/cli_source_process_observer.py src/crxzipple/modules/tool/infrastructure/cli_source_credentials.py src/crxzipple/modules/tool/infrastructure/cli_source_config_values.py src/crxzipple/modules/tool/infrastructure/cli_source_envelopes.py src/crxzipple/modules/tool/infrastructure/cli_source_paths.py src/crxzipple/modules/tool/infrastructure/cli_source_redaction.py
PYTHONPATH=src pytest -q tests/unit/test_tool_source_service.py -k 'cli_source'
PYTHONPATH=src pytest -q tests/unit/test_tool_source_service.py tests/unit/test_tool_catalog_reconcile.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_context_tree_tool.py tests/unit/test_operations_tool_readiness_sections.py
PYTHONPATH=src pytest -q tests/unit/test_tool_background.py tests/unit/test_tool_execution.py tests/unit/test_tool_source_service.py tests/unit/test_tool_catalog_reconcile.py tests/unit/test_operations_tool_readiness_sections.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_context_tree_tool.py tests/unit/test_module_architecture_guards.py
# 106 passed
```

Risk:

- Medium-high. External process and credential handling.

## PR 13. Orchestration Chain Lifecycle State-Machine Tests

Status: complete.

Purpose: test before splitting execution chain state machine.

Scope:

- Added tests for:
  - chain bootstrap
  - LLM step start/complete/fail
  - tool batch materialization
  - late tool result target handling
  - approval step item terminal handling
  - continuation decision item creation
  - final response materialization

Acceptance:

- State transitions are explicit in assertions.
- Item ids/correlation keys remain stable.
- Tool result session item links are preserved.

Verification:

```bash
PYTHONPATH=src pytest -q tests/unit/test_orchestration_execution_chain.py
# 29 passed
PYTHONPATH=src pytest -q tests/unit/test_orchestration_execution_chain.py tests/unit/test_orchestration_approval.py tests/unit/test_orchestration_tools.py tests/unit/test_orchestration_tool_resource_policy.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_context.py tests/unit/test_orchestration_llm_invoker.py tests/unit/test_orchestration_llm_service_adapter.py tests/unit/test_orchestration_service_surface.py tests/unit/test_orchestration_queue.py tests/unit/test_orchestration_executor_leases.py
# 233 passed
```

Risk:

- Low-medium as tests; high value before extraction.

## PR 14. Split Orchestration Execution Chain And Worker CLI

Status: complete. Execution chain split, worker CLI split, lazy benchmark import
guard, and daemon-managed worker smoke verification are complete.

Purpose: make runtime state machine and CLI entrypoints maintainable.

Scope:

- Split `execution_chain_lifecycle.py` into bootstrap, LLM, tool, approval, session item, common state helper, terminal/final-response, contract, and id modules.
- Split `worker_cli.py` into executor commands, scheduler commands, shared runtime helpers, and benchmark/synthetic runtime support.
- Ensure production worker CLI does not import benchmark/synthetic adapters on normal path.

Acceptance:

- PR 13 tests pass.
- `execution_chain_lifecycle.py` is a thin public export layer; runtime behavior lives in focused modules.
- `worker_cli.py` is a thin Typer composition layer; worker command behavior lives in focused interface modules.
- Architecture guard confirms production worker CLI modules keep benchmark/synthetic runtime imports lazy.
- Daemon-managed worker smoke test passes.
- Benchmark code remains available but isolated.
- Daemon runtime benchmark uses scheduler target for scheduling and admin target for run query / daemon snapshots.

Suggested command:

```bash
python -m ruff check src/crxzipple/modules/orchestration/application/execution_chain_lifecycle.py src/crxzipple/modules/orchestration/application/execution_chain_bootstrap.py src/crxzipple/modules/orchestration/application/execution_chain_llm.py src/crxzipple/modules/orchestration/application/execution_chain_tool.py src/crxzipple/modules/orchestration/application/execution_chain_approval.py src/crxzipple/modules/orchestration/application/execution_chain_terminal.py src/crxzipple/modules/orchestration/application/execution_chain_session_items.py src/crxzipple/modules/orchestration/application/execution_chain_common.py src/crxzipple/modules/orchestration/application/execution_chain_contracts.py src/crxzipple/modules/orchestration/application/execution_chain_ids.py tests/unit/test_orchestration_execution_chain.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_execution_chain.py
PYTHONPATH=src pytest -q tests/unit
python -m crxzipple.main daemon status
```

Current verification:

```bash
python -m ruff check src/crxzipple/modules/orchestration/application/execution_chain_lifecycle.py src/crxzipple/modules/orchestration/application/execution_chain_bootstrap.py src/crxzipple/modules/orchestration/application/execution_chain_llm.py src/crxzipple/modules/orchestration/application/execution_chain_tool.py src/crxzipple/modules/orchestration/application/execution_chain_approval.py src/crxzipple/modules/orchestration/application/execution_chain_terminal.py src/crxzipple/modules/orchestration/application/execution_chain_session_items.py src/crxzipple/modules/orchestration/application/execution_chain_common.py src/crxzipple/modules/orchestration/application/execution_chain_contracts.py src/crxzipple/modules/orchestration/application/execution_chain_ids.py tests/unit/test_orchestration_execution_chain.py
# All checks passed
PYTHONPATH=src pytest -q tests/unit/test_orchestration_execution_chain.py
# 29 passed
python -m ruff check src/crxzipple/modules/orchestration/interfaces/worker_cli.py src/crxzipple/modules/orchestration/interfaces/worker_cli_common.py src/crxzipple/modules/orchestration/interfaces/worker_cli_executor.py src/crxzipple/modules/orchestration/interfaces/worker_cli_scheduler.py src/crxzipple/modules/orchestration/interfaces/worker_cli_benchmark.py tests/unit/test_app_assembly_architecture.py
# All checks passed
PYTHONPATH=src pytest -q tests/unit/test_orchestration_cli.py tests/unit/test_app_assembly_architecture.py
# 65 passed
python -m ruff check src/crxzipple/modules/orchestration/interfaces/worker_cli_benchmark.py
# All checks passed
PYTHONPATH=src pytest -q tests/unit/test_orchestration_cli.py -k 'benchmark_daemon_runtime or benchmark_runtime or benchmark_tool_io' --tb=short
# 6 passed, 26 deselected
PYTHONPATH=src pytest -q tests/unit/test_orchestration_execution_chain.py tests/unit/test_orchestration_approval.py tests/unit/test_orchestration_tools.py tests/unit/test_orchestration_tool_resource_policy.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_context.py tests/unit/test_orchestration_llm_invoker.py tests/unit/test_orchestration_llm_service_adapter.py tests/unit/test_orchestration_service_surface.py tests/unit/test_orchestration_queue.py tests/unit/test_orchestration_executor_leases.py tests/unit/test_orchestration_cli.py tests/unit/test_app_assembly_architecture.py
# 298 passed
source scripts/dev/infra-env.sh && PYTHONPATH=src python -m crxzipple.main orchestration-executor benchmark-daemon-runtime assistant openai.gpt-5.4-mini "Reply exactly: PR14_DAEMON_SMOKE_OK" --run-count 1 --run-id-prefix pr14-daemon-smoke-20260622b --main-key pr14-daemon-smoke --max-steps 2 --timeout-seconds 90 --poll-interval-seconds 1 --allow-shared-runtime
# completed_before_timeout=true, status_counts.completed=1, runtime_mode=daemon_scheduler_executor
```

Risk:

- High. Runtime coordinator paths.

## PR 15. Browser Lease And Engine Tests

Status: complete. Browser lease/action cleanup tests now lock allocation
isolation, heartbeat/expiry/release/fail behavior, CDP/session cleanup, action
failure cleanup, trace snapshot budget, and browser core task-specialization
guards.

Purpose: lock behavior before splitting browser runtime.

Scope:

- Add tests for:
  - profile allocation/lease isolation
  - allocation heartbeat/expiry/release/fail
  - action timeout/cancellation cleanup
  - CDP/session cleanup
  - trace/snapshot size budget
  - no site-specific logic in core engine fixtures

Acceptance:

- Tests fail on cross-profile state bleed.
- Action cleanup leaves no active session/target leak.
- Browser core production code remains free of site/task-specific flight logic.

Current verification:

```bash
python -m ruff check tests/unit/test_browser_cdp_sessions.py tests/unit/test_browser_profile_allocator.py tests/unit/test_browser_playwright_actions.py tests/unit/test_browser_playwright_runtime_actions.py tests/unit/test_app_assembly_architecture.py
# All checks passed
PYTHONPATH=src pytest -q tests/unit/test_browser_cdp_sessions.py tests/unit/test_browser_profile_allocator.py tests/unit/test_browser_playwright_actions.py tests/unit/test_browser_playwright_runtime_actions.py tests/unit/test_app_assembly_architecture.py --tb=short
# 102 passed
PYTHONPATH=src pytest -q tests/unit/test_browser_*.py tests/unit/test_operations_browser_read_model.py --tb=short
# 348 passed
```

Risk:

- Medium as tests, but may require fakes.

## PR 16. Split Browser Application Services And Action Engine

Status: complete. Browser application service split is complete:
`services.py` is now a thin export layer over execution planning, execution
coordinator, profile admin, profile pool, profile allocator, and shared
lifecycle helpers. Infrastructure action engine internals are now split across
focused modules for batch execution, raw CDP execution, action-trace
coordination, interaction primitives, ref/overlay handling, and wait actions.

Purpose: decompose Browser runtime after tests exist.

Scope:

- Split application services into profile admin, profile pool, allocator, execution coordinator, tab ops, selection ops.
- Split infrastructure engine into CDP session, locator resolution, action execution, overlay refs, snapshot capture, error mapping.

Acceptance:

- PR 15 tests pass.
- Browser core remains generic, no website/task-specific flows.
- Daemon/browser profile behavior remains compatible with Operations projections.

Current verification:

```bash
python -m ruff check src/crxzipple/modules/browser/application/services.py src/crxzipple/modules/browser/application/profile_lifecycle_common.py src/crxzipple/modules/browser/application/profile_admin_service.py src/crxzipple/modules/browser/application/profile_pool_service.py src/crxzipple/modules/browser/application/profile_allocator_service.py src/crxzipple/modules/browser/application/execution_coordinator.py src/crxzipple/modules/browser/application/execution_planning.py src/crxzipple/modules/browser/application/__init__.py
# All checks passed
PYTHONPATH=src pytest -q tests/unit/test_browser_profile_allocator.py tests/unit/test_browser_profile_pool.py tests/unit/test_browser_domain.py tests/unit/test_browser_http.py tests/unit/test_browser_cli.py tests/unit/test_browser_cdp_host_daemon.py --tb=short
# 79 passed
PYTHONPATH=src pytest -q tests/unit/test_browser_domain.py tests/unit/test_browser_cdp_control.py tests/unit/test_browser_interfaces.py tests/unit/test_browser_cdp_host_daemon.py tests/unit/test_browser_http.py tests/unit/test_browser_cli.py --tb=short
# 83 passed
python -m ruff check src/crxzipple/modules/browser/infrastructure/action_engines.py src/crxzipple/modules/browser/infrastructure/action_engine_batch.py src/crxzipple/modules/browser/infrastructure/action_engine_cdp.py src/crxzipple/modules/browser/infrastructure/action_engine_trace_runner.py src/crxzipple/modules/browser/infrastructure/action_engine_interactions.py src/crxzipple/modules/browser/infrastructure/action_engine_refs.py src/crxzipple/modules/browser/infrastructure/action_engine_wait.py
# All checks passed
PYTHONPATH=src pytest -q tests/unit/test_browser_playwright_actions.py -k 'action_trace or action-trace' --tb=short
# 12 passed, 2 deselected
PYTHONPATH=src pytest -q tests/unit/test_browser_playwright_actions.py tests/unit/test_browser_playwright_runtime_actions.py tests/unit/test_browser_playwright_snapshot_actions.py tests/unit/test_browser_playwright_locator_actions.py --tb=short
# 104 passed
PYTHONPATH=src pytest -q tests/unit/test_browser_*.py tests/unit/test_operations_browser_read_model.py --tb=short
# 348 passed
PYTHONPATH=src pytest -q tests/unit/test_app_assembly_architecture.py --tb=short
# 34 passed
```

Risk:

- High. Stateful external runtime.

## PR 17. Access OAuth/Query/Action/Settings Safety Split

Status: in progress. OAuth repository/token-store protocols and OAuth result
DTOs are now split into `oauth_contracts.py`; metadata redaction for OAuth
payloads is isolated in `oauth_redaction.py` and covered by a no-raw-secret
payload test. Token endpoint HTTP behavior is split into
`oauth_token_client.py`; refresh/revoke service paths are covered, including
OAuth `scope` to token `scopes` normalization. Local Codex callback listener
and browser opener logic are isolated in `oauth_callback_listener.py`.
Setup-session record/result construction and OAuth authorization URL/device-code
payload shaping are isolated in `oauth_setup_flows.py`. OpenAI Codex provider
constants and access-token identity extraction are isolated in `oauth_codex.py`.
Token payload expiry/scope/subject extraction, token masking, default account id,
PKCE challenge generation, scope diff payloads, and small text normalization are
isolated in `oauth_token_payloads.py`. OAuth provider/account record construction,
token document construction, account status replacement, refresh account shaping,
and Settings credential-binding request construction are isolated in
`oauth_account_records.py`. `oauth.py` remains the account lifecycle coordinator and
currently delegates the security-sensitive side effects to focused helpers. Access
query result/assets/overview-assets/record-model/requirements projection helpers
are split into focused query modules. Query record collection and audit-window
projection are split into `query_records.py` and `query_audits.py`. Access read model payload timestamp,
normalization, setup hint, source masking, masked preview, and sensitive-key
redaction helpers are split into `read_model_payloads.py`, leaving
`read_models.py` as DTOs plus `to_payload` methods. Inventory requirement
check-spec construction, credential binding labels, requirement masking, credential
asset kind calculation, and metadata redaction are split into focused
`inventory_*` modules. Migration legacy value extraction and migration
requirement/credential payload rules are split into focused `migration_*` modules.
Access persistence SQLAlchemy model/application record mapping is split into
`repository_mappers.py`, leaving repositories as transaction/query owners.
Access action contracts, change parsing, redaction/raw-secret rejection, audit/event
payload shaping, and credential requirement readiness are split into focused
`action_*` modules. Setup/verification handlers are split into
`action_setup_handlers.py`; OAuth provider/setup/account handlers are split into
`action_oauth_handlers.py`; `actions.py` remains the audit/event/routing coordinator.
Requirement parsing, credential binding canonicalization, expected-kind detection, and
binding/source compatibility rules are split into
`credential_requirement_rules.py`. Settings action contracts, payload parsing,
Settings payload to Access record mapping, credential binding conversion, and
consumer binding conversion, and materialized config view/provider are split into
focused `settings_*` modules;
`settings_integration.py` remains the Settings write adapter and resource upsert
coordinator. Credential resolution audit context, event payloads, safe source refs,
trace redaction, consumer audit payloads, and audit text truncation are split into
`credential_resolution_audit.py`; env/file/literal credential source IO is split
into `credential_resolver.py`; setup-flow object construction is split into
`credential_setup_flows.py`; configured credential record lookup, source derivation,
OAuth provider lookup, OAuth account token resolution, and configured credential
resolution are split into `configured_credentials.py`; `services.py` remains the
requirement readiness, setup routing, credential-resolution event, and public
application-service coordinator.
OAuth token endpoint failure handling is now centralized in
`oauth_token_client.py`: retryable HTTP/network failures are retried, endpoint
errors are normalized to Access-owned exceptions, and provider request exceptions
avoid echoing raw token material. File-backed OAuth token storage now exposes a
storage-key lock; auto-refresh and revoke coordination use that lock so concurrent
runtime consumers do not repeatedly refresh the same near-expired account token.

Purpose: isolate credential/token security concerns.

Scope:

- Split `access/application/oauth.py` into provider/accounts, setup sessions, browser flow, device flow, token client, callback listener, redaction, token payload normalization, and account record construction.
- Split `access/application/query.py` into result DTOs, synthetic asset projection,
  overview/assets projection, read-model record shaping, requirement projection,
  record collection, and audit-window projection.
- Split `access/application/read_models.py` payload construction, masking, and
  redaction helpers away from read-model DTOs.
- Split `access/application/inventory.py` requirement check-spec, masking, label,
  asset-kind, and metadata redaction helpers away from inventory grouping.
- Split `access/application/migration.py` legacy value extraction and migration
  requirement/credential payload rules away from plan builder coordination.
- Split `access/infrastructure/persistence/repositories.py` model/record mapping,
  timestamp coercion, and text validation away from repository transactions.
- Split `access/application/actions.py` into action contracts, change parsing,
  redaction, payload shaping, readiness helpers, and intent handlers.
- Split `access/application/settings_integration.py` into action contracts, payload
  parsing, Access record mapping, credential binding conversion, and consumer
  binding conversion, and config view/provider.
- Split `access/application/services.py` pure requirement/binding rules away from
  the requirement readiness/setup routing coordinator.
- Split credential resolution audit/event payload/redaction helpers away from
  `access/application/services.py`.
- Split env/file/literal credential source IO away from
  `access/application/services.py`.
- Split setup-flow object construction away from `access/application/services.py`.
- Split configured credential interpretation and OAuth provider lookup away from
  `access/application/services.py`.
- Add no-raw-secret tests first if missing.

Acceptance:

- OAuth refresh/revoke lifecycle and retry tests pass.
- OAuth auto-refresh second-read and storage-key lock tests pass.
- Callback listener cleanup is deterministic.
- Logs/events/projections/errors do not contain raw tokens/secrets.

Current verification:

```bash
python -m ruff check src/crxzipple/modules/access/application/oauth.py src/crxzipple/modules/access/application/oauth_codex.py src/crxzipple/modules/access/application/oauth_callback_listener.py src/crxzipple/modules/access/application/oauth_setup_flows.py src/crxzipple/modules/access/application/oauth_contracts.py src/crxzipple/modules/access/application/oauth_redaction.py src/crxzipple/modules/access/application/oauth_token_client.py src/crxzipple/modules/access/application/oauth_token_payloads.py src/crxzipple/modules/access/application/oauth_account_records.py tests/unit/test_access_oauth.py tests/unit/test_app_assembly_module_local.py
# All checks passed
PYTHONPATH=src pytest -q tests/unit/test_access_oauth.py --tb=short
# 10 passed
PYTHONPATH=src pytest -q tests/unit/test_access_oauth.py tests/unit/test_app_assembly_module_local.py --tb=short
# 33 passed
PYTHONPATH=src pytest -q tests/unit/test_access_oauth.py tests/unit/test_access_actions.py tests/unit/test_access_http.py tests/unit/test_access_llm_integration.py tests/unit/test_access.py tests/unit/test_authorization_access_boundary.py tests/unit/test_authorization.py tests/unit/test_access_governance_contracts.py tests/unit/test_app_assembly_module_local.py --tb=short
# 106 passed
python -m ruff check src/crxzipple/modules/access/application/actions.py src/crxzipple/modules/access/application/action_contracts.py src/crxzipple/modules/access/application/action_changes.py src/crxzipple/modules/access/application/action_redaction.py src/crxzipple/modules/access/application/action_payloads.py src/crxzipple/modules/access/application/action_readiness.py
# All checks passed
python -m ruff check src/crxzipple/modules/access/application/actions.py src/crxzipple/modules/access/application/action_setup_handlers.py src/crxzipple/modules/access/application/action_oauth_handlers.py
# All checks passed
PYTHONPATH=src pytest -q tests/unit/test_access_actions.py tests/unit/test_access_http.py tests/unit/test_access_policies.py --tb=short
# 32 passed
python -m ruff check src/crxzipple/modules/access/application/services.py src/crxzipple/modules/access/application/configured_credentials.py src/crxzipple/modules/access/application/credential_requirement_rules.py src/crxzipple/modules/access/application/credential_resolver.py src/crxzipple/modules/access/application/credential_resolution_audit.py src/crxzipple/modules/access/application/credential_setup_flows.py
# All checks passed
PYTHONPATH=src pytest -q tests/unit/test_access.py tests/unit/test_access_llm_integration.py tests/unit/test_access_tool_integration.py --tb=short
# 17 passed
python -m ruff check src/crxzipple/modules/access/application/settings_integration.py src/crxzipple/modules/access/application/settings_action_contracts.py src/crxzipple/modules/access/application/settings_payloads.py src/crxzipple/modules/access/application/settings_record_models.py src/crxzipple/modules/access/application/settings_credential_bindings.py src/crxzipple/modules/access/application/settings_consumer_bindings.py
# All checks passed
PYTHONPATH=src pytest -q tests/unit/test_access_oauth.py tests/unit/test_access_read_models.py tests/unit/test_access_actions.py tests/unit/test_access_http.py tests/unit/test_access_tool_integration.py tests/unit/test_access_llm_integration.py tests/unit/test_access.py tests/unit/test_authorization_access_boundary.py tests/unit/test_authorization.py tests/unit/test_access_governance_contracts.py tests/unit/test_app_assembly_module_local.py tests/unit/test_module_architecture_guards.py --tb=short
# 123 passed
python -m ruff check src/crxzipple/modules/access/application/settings_integration.py src/crxzipple/modules/access/application/settings_config_views.py src/crxzipple/app/assembly/access.py src/crxzipple/modules/access/interfaces/http.py src/crxzipple/modules/access/interfaces/inventory.py src/crxzipple/modules/access/interfaces/ui_http.py src/crxzipple/modules/operations/application/read_models/modules.py src/crxzipple/modules/access/application/query.py tests/unit/test_access_oauth.py tests/unit/test_access_actions.py
# All checks passed
PYTHONPATH=src pytest -q tests/unit/test_access_oauth.py tests/unit/test_access_actions.py tests/unit/test_access_read_models.py tests/unit/test_access_http.py tests/unit/test_operations_observation.py tests/unit/test_module_architecture_guards.py --tb=short
# 98 passed
PYTHONPATH=src pytest -q tests/unit/test_access_oauth.py tests/unit/test_access_read_models.py tests/unit/test_access_actions.py tests/unit/test_access_http.py tests/unit/test_access_tool_integration.py tests/unit/test_access_llm_integration.py tests/unit/test_access.py tests/unit/test_authorization_access_boundary.py tests/unit/test_authorization.py tests/unit/test_access_governance_contracts.py tests/unit/test_app_assembly_module_local.py tests/unit/test_module_architecture_guards.py --tb=short
# 123 passed
python -m ruff check src/crxzipple/modules/access/application/oauth.py src/crxzipple/modules/access/application/oauth_account_records.py src/crxzipple/modules/access/application/oauth_token_payloads.py
# All checks passed
PYTHONPATH=src pytest -q tests/unit/test_access_oauth.py tests/unit/test_access_actions.py tests/unit/test_access_http.py tests/unit/test_access.py --tb=short
# 53 passed
PYTHONPATH=src pytest -q tests/unit/test_access_oauth.py tests/unit/test_access_read_models.py tests/unit/test_access_actions.py tests/unit/test_access_http.py tests/unit/test_access_tool_integration.py tests/unit/test_access_llm_integration.py tests/unit/test_access.py tests/unit/test_authorization_access_boundary.py tests/unit/test_authorization.py tests/unit/test_access_governance_contracts.py tests/unit/test_app_assembly_module_local.py tests/unit/test_module_architecture_guards.py --tb=short
# 123 passed
python -m ruff check src/crxzipple/modules/access/application/query.py src/crxzipple/modules/access/application/query_overview_assets.py
# All checks passed
PYTHONPATH=src pytest -q tests/unit/test_access_read_models.py tests/unit/test_access_http.py tests/unit/test_access_actions.py tests/unit/test_access.py --tb=short
# 51 passed
PYTHONPATH=src pytest -q tests/unit/test_access_oauth.py tests/unit/test_access_read_models.py tests/unit/test_access_actions.py tests/unit/test_access_http.py tests/unit/test_access_tool_integration.py tests/unit/test_access_llm_integration.py tests/unit/test_access.py tests/unit/test_authorization_access_boundary.py tests/unit/test_authorization.py tests/unit/test_access_governance_contracts.py tests/unit/test_app_assembly_module_local.py tests/unit/test_module_architecture_guards.py --tb=short
# 123 passed
PYTHONPATH=src pytest -q tests/unit/test_access.py tests/unit/test_access_llm_integration.py tests/unit/test_access_tool_integration.py tests/unit/test_access_actions.py tests/unit/test_access_http.py --tb=short
# 48 passed
python -m ruff check src/crxzipple/modules/access/application/read_models.py src/crxzipple/modules/access/application/read_model_payloads.py src/crxzipple/modules/access/application/query.py src/crxzipple/modules/access/application/query_record_models.py src/crxzipple/modules/access/application/query_overview_assets.py
# All checks passed
PYTHONPATH=src pytest -q tests/unit/test_access_read_models.py tests/unit/test_access_http.py tests/unit/test_access_actions.py tests/unit/test_access_oauth.py tests/unit/test_access.py --tb=short
# 61 passed
PYTHONPATH=src pytest -q tests/unit/test_access_oauth.py tests/unit/test_access_read_models.py tests/unit/test_access_actions.py tests/unit/test_access_http.py tests/unit/test_access_tool_integration.py tests/unit/test_access_llm_integration.py tests/unit/test_access.py tests/unit/test_authorization_access_boundary.py tests/unit/test_authorization.py tests/unit/test_access_governance_contracts.py tests/unit/test_app_assembly_module_local.py tests/unit/test_module_architecture_guards.py --tb=short
# 123 passed
python -m ruff check src/crxzipple/modules/access/application/inventory.py src/crxzipple/modules/access/application/inventory_requirement_rules.py src/crxzipple/modules/access/application/inventory_redaction.py src/crxzipple/modules/access/application/migration.py
# All checks passed
PYTHONPATH=src pytest -q tests/unit/test_access_read_models.py tests/unit/test_access_tool_integration.py tests/unit/test_access.py --tb=short
# 23 passed
PYTHONPATH=src pytest -q tests/unit/test_access_oauth.py tests/unit/test_access_read_models.py tests/unit/test_access_actions.py tests/unit/test_access_http.py tests/unit/test_access_tool_integration.py tests/unit/test_access_llm_integration.py tests/unit/test_access.py tests/unit/test_authorization_access_boundary.py tests/unit/test_authorization.py tests/unit/test_access_governance_contracts.py tests/unit/test_app_assembly_module_local.py tests/unit/test_module_architecture_guards.py --tb=short
# 123 passed
python -m ruff check src/crxzipple/modules/access/application/migration.py src/crxzipple/modules/access/application/migration_requirement_payloads.py src/crxzipple/modules/access/application/migration_value_helpers.py src/crxzipple/modules/access/application/inventory_requirement_rules.py src/crxzipple/modules/access/application/inventory_redaction.py
# All checks passed
PYTHONPATH=src pytest -q tests/unit/test_access_migration.py tests/unit/test_access_tool_integration.py --tb=short
# 7 passed
PYTHONPATH=src pytest -q tests/unit/test_access_oauth.py tests/unit/test_access_read_models.py tests/unit/test_access_actions.py tests/unit/test_access_http.py tests/unit/test_access_tool_integration.py tests/unit/test_access_llm_integration.py tests/unit/test_access.py tests/unit/test_access_migration.py tests/unit/test_authorization_access_boundary.py tests/unit/test_authorization.py tests/unit/test_access_governance_contracts.py tests/unit/test_app_assembly_module_local.py tests/unit/test_module_architecture_guards.py --tb=short
# 127 passed
python -m ruff check src/crxzipple/modules/access/infrastructure/persistence/repositories.py src/crxzipple/modules/access/infrastructure/persistence/repository_mappers.py
# All checks passed
PYTHONPATH=src pytest -q tests/unit/test_access_persistence.py tests/unit/test_access_oauth.py tests/unit/test_access.py --tb=short
# 24 passed
PYTHONPATH=src pytest -q tests/unit/test_access_oauth.py tests/unit/test_access_read_models.py tests/unit/test_access_actions.py tests/unit/test_access_http.py tests/unit/test_access_tool_integration.py tests/unit/test_access_llm_integration.py tests/unit/test_access.py tests/unit/test_access_migration.py tests/unit/test_access_persistence.py tests/unit/test_authorization_access_boundary.py tests/unit/test_authorization.py tests/unit/test_access_governance_contracts.py tests/unit/test_app_assembly_module_local.py tests/unit/test_module_architecture_guards.py --tb=short
# 129 passed
python -m ruff check src/crxzipple/modules/access/application/query.py src/crxzipple/modules/access/application/query_records.py src/crxzipple/modules/access/application/query_audits.py src/crxzipple/modules/access/application/query_record_models.py src/crxzipple/modules/access/application/query_requirements.py
# All checks passed
PYTHONPATH=src pytest -q tests/unit/test_access_read_models.py tests/unit/test_access_http.py tests/unit/test_access_actions.py --tb=short
# 39 passed
PYTHONPATH=src pytest -q tests/unit/test_access_oauth.py tests/unit/test_access_read_models.py tests/unit/test_access_actions.py tests/unit/test_access_http.py tests/unit/test_access_tool_integration.py tests/unit/test_access_llm_integration.py tests/unit/test_access.py tests/unit/test_access_migration.py tests/unit/test_access_persistence.py tests/unit/test_authorization_access_boundary.py tests/unit/test_authorization.py tests/unit/test_access_governance_contracts.py tests/unit/test_app_assembly_module_local.py tests/unit/test_module_architecture_guards.py --tb=short
# 129 passed
python -m ruff check src/crxzipple/modules/access/application/oauth_token_client.py tests/unit/test_access_oauth.py
# All checks passed
PYTHONPATH=src pytest -q tests/unit/test_access_oauth.py --tb=short
# 12 passed
PYTHONPATH=src pytest -q tests/unit/test_access_oauth.py tests/unit/test_access_read_models.py tests/unit/test_access_actions.py tests/unit/test_access_http.py tests/unit/test_access_tool_integration.py tests/unit/test_access_llm_integration.py tests/unit/test_access.py tests/unit/test_access_migration.py tests/unit/test_access_persistence.py tests/unit/test_authorization_access_boundary.py tests/unit/test_authorization.py tests/unit/test_access_governance_contracts.py tests/unit/test_app_assembly_module_local.py tests/unit/test_module_architecture_guards.py --tb=short
# 131 passed
python -m ruff check src/crxzipple/modules/access/application/oauth.py src/crxzipple/modules/access/application/oauth_contracts.py src/crxzipple/modules/access/infrastructure/oauth_tokens.py tests/unit/test_access_oauth.py
# All checks passed
PYTHONPATH=src pytest -q tests/unit/test_access_oauth.py --tb=short
# 14 passed
PYTHONPATH=src pytest -q tests/unit/test_access_oauth.py tests/unit/test_access_read_models.py tests/unit/test_access_actions.py tests/unit/test_access_http.py tests/unit/test_access_tool_integration.py tests/unit/test_access_llm_integration.py tests/unit/test_access.py tests/unit/test_access_migration.py tests/unit/test_access_persistence.py tests/unit/test_authorization_access_boundary.py tests/unit/test_authorization.py tests/unit/test_access_governance_contracts.py tests/unit/test_app_assembly_module_local.py tests/unit/test_module_architecture_guards.py --tb=short
# 133 passed
PYTHONPATH=src pytest -q tests/unit/test_access_llm_integration.py tests/unit/test_access_tool_integration.py tests/unit/test_access_channel_requirements.py tests/unit/test_browser_access_requirements.py tests/unit/test_memory_access_requirements.py --tb=short
# 23 passed
PYTHONPATH=src pytest -q tests/unit/test_browser_cdp_control.py -k access_binding --tb=short
# 1 passed, 16 deselected
```

Risk:

- High security impact.

## PR 18. Skills Filesystem Repository Split

Purpose: isolate user-controlled filesystem operations.

Status: complete for the filesystem repository split wave. The public repository
port stayed stable, while internal path safety, parsing, package file helpers, and
directory loading moved into focused infrastructure modules.

Scope:

- Split filesystem repository into path safety, manifest parser, package file helpers, package loader, and public repository orchestration. Done:
  - `skills/infrastructure/filesystem/path_safety.py`
  - `skills/infrastructure/filesystem/manifest_parser.py`
  - `skills/infrastructure/filesystem/package_files.py`
  - `skills/infrastructure/filesystem/package_loader.py`
- Keep public repository port stable only if it is the intended owner module API; no compatibility wrapper for old internals.

Acceptance:

- Path traversal tests pass through existing read/resource tests plus explicit write/delete support-file traversal tests.
- Manifest/frontmatter read/write tests pass.
- Runtime skill resolution remains unchanged.
- Context Workspace skill adapter tests pass.

Verification:

```bash
python -m ruff check src/crxzipple/modules/skills/infrastructure/filesystem/repository.py src/crxzipple/modules/skills/infrastructure/filesystem/path_safety.py src/crxzipple/modules/skills/infrastructure/filesystem/manifest_parser.py src/crxzipple/modules/skills/infrastructure/filesystem/package_files.py src/crxzipple/modules/skills/infrastructure/filesystem/package_loader.py
PYTHONPATH=src pytest -q tests/unit/test_skills_cli.py tests/unit/test_skills_context.py tests/unit/test_skills_http.py tests/unit/test_skills_tool_authoring.py tests/unit/test_skills_authoring_http.py tests/unit/test_skills_owner_catalog_persistence.py tests/unit/test_context_workspace_skill_adapter.py --tb=short
# 52 passed
```

Risk:

- Medium-high. Filesystem mutation surface.

## PR 19. Capability And Support Hardening

Purpose: cover remaining P2 support risks after P1 cleanup starts.

Scope:

- Dispatch concurrent claim/lease tests.
- Daemon start/ensure/status/stop/recover smoke tests.
- Artifact retention/quota/download authorization.
- Process output cap/timeout cleanup.
- OCR host capacity/concurrency policy after timeout/error/result-size coverage.
- Mobile screenshot/artifact retention budget tests after ADB/device lease coverage.
- Decide Event Relay and Delivery ownership.

Acceptance:

- Support modules have explicit production/fallback behavior.
- Placeholder Delivery is retired or documented.
- Event Relay does not mutate owner lifecycle facts.

Risk:

- Medium. Broad but smaller modules.

## Preferred Execution Order

1. PR 0
2. PR 1
3. PR 2
4. PR 5
5. PR 7
6. PR 3
7. PR 4
8. PR 6
9. PR 8
10. PR 9
11. PR 10
12. PR 11
13. PR 12
14. PR 13
15. PR 14
16. PR 15
17. PR 16
18. PR 17
19. PR 18
20. PR 19

Rationale:

- Tests and measurement come first.
- Pure projection/UI splits precede side-effect runtime splits.
- Session and Context Workspace are split before Tool/Orchestration side-effect movement.
- Browser and Access are late because they are stateful/security-sensitive.

## PR Template

Each PR should include:

- Problem statement referencing the audit doc section.
- Owner module boundary statement.
- Files moved/created/deleted.
- Explicit statement that no compatibility double track remains.
- Tests run and result.
- If UI-facing, Workbench/Operations verification note.
- If LLM-facing, provider request preview note.
