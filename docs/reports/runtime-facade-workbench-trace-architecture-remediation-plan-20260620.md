# Runtime Facade / Workbench / Trace Architecture Remediation Plan

Date: 2026-06-20

## Background

This document records the current architecture review decision after the runtime
request, Context Tree, Workbench, Trace, Operations, and provider rendering
alignment work.

The current runtime has mostly converged on the right direction:

- owner modules keep their own facts;
- orchestration coordinates run execution;
- Context Workspace owns context control and slice production;
- LLM owns provider-neutral request objects and provider-specific rendering;
- Operations observes events and materializes projection/read models;
- frontend is the single UI surface.

However, several responsibilities are still in transitional locations. The most
important cleanup is to remove orchestration from UI/debug/request-bridge
responsibilities and introduce a stable product-facing Workbench facade.

## Decisions

### 1. Context Tree Produces Slice, Not Provider/UI Shape

Context Workspace must expose context as `slice`.

Allowed:

```text
Context Tree
  -> Context Slice
```

Consumer-specific conversion is `render` or `projection`:

```text
Context Slice -> provider wire render
Context Slice -> Workbench/Trace UI projection
Context Slice -> debug render
```

Context Workspace must not become a provider prompt renderer. Full tree/debug
body is not the default LLM input. Debug render is observation-only.

### 2. Orchestration Must Not Own UI / Debug / Trace Assembly

Orchestration owns:

- run lifecycle;
- scheduling and executor advancement;
- wait/approval/resume;
- coordination of LLM and tool steps;
- run-level observation events.

Orchestration must not own:

- Workbench timeline view models;
- Trace UI;
- debug panels;
- provider request rendering;
- Context Tree rendering;
- frontend-friendly linked-entity detail assembly.

### 3. Workbench Becomes Product-Facing Facade Module

Introduce a stable Workbench module:

```text
src/crxzipple/modules/workbench/
  application/
    service.py
    read_models.py
    ports.py
    timeline.py
    linked_entities.py
    trace.py
    commands.py
  interfaces/
    http.py
```

Workbench is not a business truth owner. It is a product-facing facade over:

- orchestration;
- session;
- tool;
- llm;
- context_workspace;
- artifacts;
- agent;
- events;
- operations projections where useful.

Workbench owns only Workbench-facing read models, UI command coordination, and
runtime-console view composition.

### 4. Trace UI Is Useful, But Not a Top-Level Product Page

Trace functionality stays, but the independent top-level Trace page should be
retired.

Current Trace is mostly a Workbench deep-inspection surface:

- event timeline;
- selected event detail;
- linked entities;
- Context Snapshot;
- Runtime LLM request preview;
- provider request preview;
- step/run/LLM/tool correlation.

Target UI:

```text
Workbench Run Detail
  -> Trace Inspector / Trace Tab / Trace Drawer
```

Operations may still expose "Open Trace", but should route to Workbench
inspection:

```text
/workbench/runs/{run_id}?panel=trace&step_id=...
```

Only if Trace later becomes a cross-run platform tracing product should it be
promoted to a standalone `trace` module and top-level page.

### 5. Operations Is a Projection Layer

Operations is a module by code organization, but its nature is projection/read
model ownership, not business truth ownership.

Operations owns:

- operations observer runtime;
- observer heartbeat;
- operations projections;
- projection invalidation;
- operations read models;
- operations action facade that delegates to owner commands.

Operations does not own:

- run progression;
- session mutation;
- tool lifecycle truth;
- LLM invocation truth;
- Context Tree truth;
- provider request construction.

### 6. Diagnostics Are Not Runtime Core

`loop_regression_baseline.py` is useful for long-chain quality inspection, but
it is not orchestration runtime logic.

Move it out of the orchestration application root:

Because Workbench inspector debug consumes this baseline, it is productized as
an Operations diagnostic read model:

```text
src/crxzipple/modules/operations/application/read_models/diagnostics.py
```

## Current Problems

### Problem A: Orchestration Still Carries Workbench Read Model

Current file:

```text
src/crxzipple/modules/orchestration/application/read_models/workbench.py
```

This file assembles UI timeline, linked entities, inspector/debug panels, trace
routes, tool/LLM/session/artifact detail, and Workbench-facing state. This makes
orchestration responsible for UI projection.

Target:

```text
src/crxzipple/modules/workbench/application/*
```

### Problem B: Global UI Router Aggregates Too Much

Current file:

```text
src/crxzipple/interfaces/http/ui.py
```

It currently wires Workbench and Trace by directly constructing read model
providers and pulling services from the container.

Target:

```text
src/crxzipple/modules/workbench/interfaces/http.py
```

The controller should be thin and delegate to `WorkbenchApplicationService`.

### Problem C: Runtime LLM Request Bridge Lives in Orchestration

Previous file:

```text
src/crxzipple/modules/orchestration/application/runtime_llm_request.py
```

This exists as a transitional bridge from request render snapshot to
`RuntimeLlmRequest`. If it remains, orchestration keeps knowing too much about
LLM request construction.

Target:

```text
src/crxzipple/modules/llm/application/runtime_request_factory.py
```

Current implementation:

```text
src/crxzipple/modules/llm/application/runtime_request_factory.py
```

The factory is imported by orchestration as an LLM application service. It keeps
orchestration-specific draft/report types out of module import time to avoid
LLM/orchestration initialization cycles.

Orchestration should call the LLM factory with:

- context slice snapshot;
- selected tool surface;
- model/profile policy;
- run/session identifiers.

### Problem D: Context Workspace Service Is Too Large

Current file:

```text
src/crxzipple/modules/context_workspace/application/services.py
```

It mixes workspace lifecycle, tree actions, owner child refresh, snapshot
recording, request rendering, orphan pruning, and debug behavior.

Target split:

```text
workspace_service.py
tree_control_service.py
slice_builder.py
slice_snapshot_service.py
owner_child_refresh.py
debug_render_service.py
```

### Problem E: LLM Adapter Shared Layer Needed Explicit Boundaries

Retired file:

```text
src/crxzipple/modules/llm/infrastructure/adapters/common.py
```

The former `adapters/common.py` mixed content block conversion, tool schema
conversion, OpenAI item projection, fingerprints, preview payloads, and loss
reports. It has been deleted; architecture tests now guard against reintroducing
imports from `adapters.common`.

Current split:

```text
src/crxzipple/modules/llm/infrastructure/adapters/
  adapter_utils.py
  http_helpers.py
  openai_response_projection.py
  provider_message_projection.py
  provider_request_preview.py
  tool_schemas.py
src/crxzipple/modules/llm/infrastructure/rendering/input_projection.py
```

Provider-specific renderers remain in `adapters` and consume the narrowly named
helpers. `provider_message_projection.py` is the shared provider-message/content
projection layer; it preserves provider wire semantics such as tool-call replay,
tool-result attachments, reasoning replay, and text-only fallback for artifact
references.

### Problem F: Frontend Workbench / Trace Still Touch Owner APIs

Current Workbench uses:

```text
/ui/workbench/*
/turns
/tools
/agents
/llms
/context-workspaces/*
/llms/calls/*
/artifacts
```

Current Trace uses:

```text
/ui/trace/*
/context-workspaces/*
/turns/*/llm-request-preview
/llms/calls/*
/ui/workbench/linked-entities/*
```

Target:

```text
Workbench UI -> /workbench/*
Trace inspector -> /workbench/runs/{run_id}/trace or /workbench/traces/{trace_id}
Operations UI -> /operations/*
Settings UI -> owner module APIs are allowed for configuration writes
```

## Target Architecture

```text
frontend
  -> workbench interfaces
  -> operations interfaces
  -> settings interfaces

modules/workbench
  product-facing runtime console facade
  read models, trace inspector, linked entities, UI commands

modules/orchestration
  run execution coordination only

modules/context_workspace
  context tree control and context slice production

modules/llm
  provider-neutral runtime request and provider wire rendering

modules/operations
  observer, projections, operations read models

owner modules
  session / tool / browser / artifacts / memory / skills / access / agent
```

## Migration Plan

### Phase 1: Workbench Facade Extraction

- [x] Create `src/crxzipple/modules/workbench`.
- [x] Move Workbench DTO/read model types out of orchestration.
- [x] Move `WorkbenchReadModelProvider` to Workbench application layer.
- [x] Add Workbench ports for orchestration, session, tool, llm, agent,
      artifacts, events, and context workspace.
- [x] Add `modules/workbench/interfaces/http.py`.
- [x] Move `/ui/workbench/*` routes into Workbench interfaces.
- [x] Keep `/ui/workbench/*` as the Workbench facade API path; do not keep a
      second owner implementation behind the same route.

Current implementation note:

- Workbench read model code now lives in `modules/workbench/application`.
- `/ui/bootstrap` reports the Workbench section owner as `workbench`.
- Route paths remain unchanged, but route ownership moved from
  `interfaces/http/ui.py` to `modules/workbench/interfaces/http.py`.
- Linked-entity LLM/tool/session payload shaping moved into
  `modules/workbench/application/entity_details.py`.
- Trace summary/event filtering moved into
  `modules/workbench/application/trace.py`; `/ui/trace/*` remains mounted for
  API route continuity but is backed by `modules/workbench/interfaces/http.py`.
- Frontend top navigation no longer exposes Trace as a top-level product page;
  the trace inspector component now lives under
  `frontend/src/pages/workbench/trace`, and product-facing links use
  `/workbench/traces/:traceId?`.
- The old frontend `/trace/:traceId?` alias has been removed; Trace has one
  product-facing route: `/workbench/traces/:traceId?`.
- Operations `trace_route` cells now point to `/workbench/traces/*`; `/ui/trace/*`
  is reserved for the Workbench-backed trace API.
- Frontend Operations data loading remains on `/operations/*`; Workbench links
  from Operations are navigation targets only, not Operations data sources.
- Long-chain loop regression baseline now lives in
  `modules/operations/application/read_models/diagnostics.py`; orchestration CLI
  and Workbench debug consume that diagnostics helper instead of importing an
  orchestration application implementation.
- Context Workspace application models now document the boundary explicitly:
  `ContextSlice` / `RecordRequestRenderSnapshotInput` are provider-request
  inputs, while `ContextObservationRenderResult` / `RecordContextSnapshotInput`
  are observation/debug surfaces.
- Architecture tests now assert that the LLM request path does not consume
  Context Workspace `debug_body`.
- Architecture tests now also forbid provider request paths from importing
  Context Workspace observation/debug renderers or observation snapshot services.
- Architecture tests now assert that orchestration read models cannot own
  UI/Trace projections; `orchestration/application/read_models` is a tombstone
  package only.
- Context Workspace application services are already split along control, debug
  snapshot, provider request snapshot, and slice construction responsibilities:
  `ContextTreeService`, `ContextObservationSnapshotService`,
  `RequestRenderSnapshotService`, `ContextSliceBuilderService`, and
  `ContextControlSliceService`.
- Verification:
  `PYTHONPATH=src pytest -q tests/unit/test_ui_http.py tests/unit/test_ui_operations_http.py tests/unit/test_workbench_read_model.py tests/unit/test_app_assembly_architecture.py`
  passes with 90 tests.
  `cd frontend && npm run typecheck && npm run build` passes.
  Runtime request relocation checks:
  `PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_llm_runtime_request_factory.py tests/unit/test_llm_runtime_request_factory_builder.py tests/unit/test_context_workspace_snapshot_boundary.py tests/unit/test_runtime_llm_request.py`
  passes with 99 tests.
  Architecture surface checks:
  `PYTHONPATH=src pytest -q tests/unit/test_app_assembly_architecture.py tests/unit/test_orchestration_service_surface.py`
  passes with 42 tests.
  Context slice/debug boundary checks:
  `PYTHONPATH=src pytest -q tests/unit/test_app_assembly_architecture.py tests/unit/test_runtime_llm_request.py tests/unit/test_context_workspace_tree_service.py`
  passes with 81 tests.
  Workbench/Operations projection boundary checks:
  `PYTHONPATH=src pytest -q tests/unit/test_app_assembly_architecture.py tests/unit/test_workbench_read_model.py tests/unit/test_operations_observation.py`
  passes with 82 tests.
  LLM adapter split checks:
  `PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py tests/unit/test_provider_request_renderer_protocol.py tests/unit/test_provider_request_trace_fixtures.py tests/unit/test_openai_codex_renderer.py tests/unit/test_anthropic_renderer.py tests/unit/test_provider_protocol_render_router.py`
  passes with 114 tests.
- LLM adapter HTTP/credential/retry helpers now live in
  `llm/infrastructure/adapters/http_helpers.py`; provider adapters and renderers
  import those helpers directly instead of using `adapters/common.py` as a
  catch-all toolbox.
- Provider tool-name normalization and provider-specific tool schema builders
  now live in `llm/infrastructure/adapters/tool_schemas.py`; provider renderers
  import schema builders directly instead of using `adapters/common.py`.
- Shared provider input projection helpers now live in
  `llm/infrastructure/rendering/input_projection.py`; provider adapters and
  renderers import canonical-input-to-message helpers from the rendering layer.
- OpenAI response absorption now lives in
  `llm/infrastructure/adapters/openai_response_projection.py`; OpenAI
  Responses, Codex Responses, and OpenAI-compatible chat adapters import
  response item, continuation, stream-event, and tool-call intent projection
  from that module instead of mixing provider output parsing into
  `adapters/common.py`.
- Cross-provider adapter basics now live in
  `llm/infrastructure/adapters/adapter_utils.py`; adapters and renderers import
  text coercion, JSON argument parsing, base URL resolution, and image-input
  capability checks from that module instead of routing those utilities through
  `adapters/common.py`.
- Provider request preview/report helpers now live in
  `llm/infrastructure/adapters/provider_request_preview.py`; provider renderers
  import preview shaping, tool render reports, protocol render reports, and
  OpenAI request/input fingerprints from that module instead of mixing request
  observability into `adapters/common.py`.
- Provider message/content conversion now lives in
  `llm/infrastructure/adapters/provider_message_projection.py`. It owns the
  remaining cross-provider transcript projection rules: tool call/result
  conversion, provider-specific content block lowering, reasoning-summary replay,
  and artifact ref text fallback. `adapters/common.py` has been deleted, and
  `test_llm_adapter_common_module_is_retired` guards against reviving it or
  importing it from production adapter code.
- LLM adapter split verification:
  `PYTHONPATH=src pytest -q tests/unit/test_app_assembly_architecture.py::test_llm_adapter_common_module_is_retired tests/unit/test_llm_adapters.py tests/unit/test_anthropic_renderer.py tests/unit/test_openai_codex_renderer.py tests/unit/test_openai_codex_transport_wire_contract.py tests/unit/test_provider_request_renderer_protocol.py tests/unit/test_provider_protocol_render_router.py tests/unit/test_provider_request_trace_fixtures.py`
  passes with 117 tests.
- Workbench runtime selector data now goes through Workbench facade endpoints:
  `/ui/workbench/tools`, `/ui/workbench/agents`, and `/ui/workbench/models`.
  Runtime console loading no longer reads `/tools`, `/agents`, or `/llms`
  directly for these read models.
- Workbench runtime inspection data now also goes through Workbench facade
  endpoints for context snapshots and LLM request previews:
  `/ui/workbench/context-snapshots/*`,
  `/ui/workbench/runs/{run_id}/llm-request-preview`, and
  `/ui/workbench/llm-invocations/{invocation_id}/llm-request-preview`.
  Workbench and Trace frontend code no longer calls the owner read APIs
  `/context-workspaces/runs/*`, `/context-workspaces/snapshots/*`,
  `/turns/{run_id}/llm-request-preview`, or `/llms/calls/*/llm-request-preview`
  for these read models.
- Workbench command/control data now also goes through Workbench facade
  endpoints:
  `/ui/workbench/turns`,
  `/ui/workbench/turns/{run_id}/cancel`,
  `/ui/workbench/turns/{run_id}/approvals/{request_id}`,
  `/ui/workbench/context-tree/by-session/{session_key}`, and
  `/ui/workbench/context-tree/by-session/{session_key}/nodes/{node_id}/actions/{action}`.
  The Workbench frontend no longer calls `/turns`, `/turns/*`,
  or `/context-workspaces/by-session/*` directly. The owner endpoints can
  remain as generic module APIs, but Workbench uses only its product-facing
  facade.
- Additional facade verification:
  `PYTHONPATH=src pytest -q tests/unit/test_app_assembly_architecture.py::test_workbench_runtime_selectors_use_workbench_facade_endpoints tests/unit/test_ui_http.py tests/unit/test_workbench_read_model.py`
  passes with 40 tests, including backend coverage for Workbench selector,
  trace route, context snapshot, LLM request-preview, turn command route list,
  and Context Tree facade endpoints.
  `PYTHONPATH=src python -m ruff check src/crxzipple/modules/workbench/interfaces/http.py src/crxzipple/interfaces/http/ui.py tests/unit/test_app_assembly_architecture.py`
  passes.
  `cd frontend && npm run typecheck` passes.
- Trace route cleanup verification:
  `PYTHONPATH=src pytest -q tests/unit/test_ui_http.py tests/unit/test_ui_operations_http.py::UiOperationsHttpTestCase::test_ui_operations_tool_page_uses_tool_runtime_state tests/unit/test_ui_operations_http.py::UiOperationsHttpTestCase::test_ui_operations_llm_page_uses_runtime_state_and_events tests/unit/test_events.py::EventsModuleTestCase::test_trace_read_model_reads_source_events_not_relay_or_channel_topics`
  passes with 32 tests.
  `PYTHONPATH=src pytest -q tests/unit/test_app_assembly_architecture.py::test_frontend_trace_has_only_workbench_product_route tests/unit/test_app_assembly_architecture.py::test_workbench_runtime_selectors_use_workbench_facade_endpoints tests/unit/test_app_assembly_architecture.py::test_orchestration_read_models_do_not_own_ui_or_trace_projection`
  passes with 3 tests and guards against reintroducing the old frontend
  `/trace/:traceId?` product route.
  `cd frontend && npm run typecheck` passes after removing the old frontend
  `/trace/:traceId?` alias.
- OpenAI response projection split verification:
  `PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py tests/unit/test_openai_codex_transport_wire_contract.py tests/unit/test_openai_codex_renderer.py tests/unit/test_provider_request_trace_fixtures.py`
  passes with 91 tests.
  `PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py tests/unit/test_anthropic_renderer.py tests/unit/test_openai_codex_renderer.py tests/unit/test_provider_request_renderer_protocol.py tests/unit/test_provider_protocol_render_router.py tests/unit/test_provider_request_trace_fixtures.py`
  passes with 114 tests after extracting `adapter_utils.py`.
  `PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py tests/unit/test_openai_codex_renderer.py tests/unit/test_openai_codex_transport_wire_contract.py tests/unit/test_provider_request_trace_fixtures.py tests/unit/test_provider_request_renderer_protocol.py tests/unit/test_provider_protocol_render_router.py`
  passes with 112 tests after extracting `provider_request_preview.py`.
- Provider preview continuation checks:
  `PYTHONPATH=src pytest -q tests/unit/test_provider_request_trace_fixtures.py::test_codex_websocket_trace_fixture tests/unit/test_openai_codex_renderer.py::test_openai_codex_renderer_websocket_uses_provider_native_delta tests/unit/test_openai_codex_renderer.py::test_openai_codex_renderer_websocket_allows_additive_tool_surface_delta`
  passes with 3 tests.
- Context slice/debug isolation checks:
  `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_snapshot_boundary.py tests/unit/test_runtime_llm_request.py tests/unit/test_app_assembly_architecture.py::test_llm_request_path_does_not_consume_context_debug_body tests/unit/test_app_assembly_architecture.py::test_provider_request_path_does_not_import_context_observation_rendering`
  passes with 25 tests.
- Operations observer/projection checks:
  `PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py`
  passes with 43 tests.
- Runtime request factory test ownership checks:
  `PYTHONPATH=src pytest -q tests/unit/test_llm_runtime_request_factory.py tests/unit/test_llm_runtime_request_factory_builder.py tests/unit/test_runtime_llm_request.py`
  passes with 61 tests.

### Phase 2: Trace UI Into Workbench Inspector

- [x] Move trace data service from global `interfaces/http/ui.py` into
      `modules/workbench/application/trace.py`.
- [x] Move `/ui/trace/*` routes into Workbench interfaces or replace with
      `/workbench/traces/*`.
- [x] Remove Trace from top-level frontend navigation.
- [x] Refactor `frontend/src/pages/trace/TracePage.vue` into a Workbench
      `TraceInspector` component.
- [x] Update direct Operations "Open Trace" links to Workbench trace inspector.
- [x] Keep event trace read model in `events`; Workbench only aggregates it.

### Phase 3: Runtime Request Factory Relocation

- [x] Add `llm/application/runtime_request_factory.py`.
- [x] Move request construction logic out of
      `orchestration/application/runtime_llm_request.py`.
- [x] Make orchestration call LLM factory with Context Slice/Snapshot refs.
- [x] Delete the orchestration runtime request bridge once tests pass.
- [x] Ensure provider-specific rendering remains in LLM adapters only.

### Phase 4: Context Workspace Slice Cleanup

- [x] Rename main-path concepts to `ContextSlice` / `ContextSliceSnapshot`
      where they are not already canonical.
- [x] Ensure `render` only means consumer-specific conversion.
- [x] Split Context Workspace services into smaller application services.
- [x] Keep debug render explicitly observation-only.
- [x] Ensure LLM request path never consumes debug body by default.

### Phase 5: Operations and Diagnostics Cleanup

- [x] Confirm Operations pages only consume `/operations/*`.
- [x] Move long-chain regression baseline out of orchestration core.
- [x] If baseline is productized, expose it as Operations diagnostics.
- [x] Remove trace/debug UI projection logic from orchestration read models.

### Phase 6: LLM Rendering Common Split

- [x] Split `llm/infrastructure/adapters/common.py`.
- [x] Keep provider renderers small and provider-specific.
- [x] Keep shared rendering helpers under `llm/infrastructure/rendering`.
- [x] Preserve existing provider request trace fixture tests.

## Non-Goals

- Do not make Operations the business truth owner.
- Do not move owner module facts into Workbench.
- Do not keep old and new Workbench read model implementations in parallel.
- Do not create task-specific evidence/probe modules.
- Do not expose full Context Tree to LLM by default.
- Do not make orchestration render provider requests.
- Do not use debug/trace metadata as model-visible context unless explicitly
  requested through a proper slice.

## Acceptance Criteria

### Architecture

- [x] `orchestration/application/read_models/workbench.py` is gone or reduced to
      a compatibility-free import-less tombstone during the same cleanup commit.
- [x] `interfaces/http/ui.py` no longer owns Workbench or Trace business
      assembly.
- [x] Workbench routes are backed by `modules/workbench`.
- [x] Trace is available as Workbench inspector, not top-level nav.
- [x] LLM request construction is owned by `llm/application`.
- [x] Context Workspace produces slice; provider/UI/debug conversions happen
      downstream.

### Frontend

- [x] Workbench API client calls Workbench facade endpoints for runtime console
      read models.
- [x] Trace component no longer directly calls owner APIs.
- [x] Operations continues to call `/operations/*`.
- [x] Settings may continue direct owner API calls for configuration writes.

### Runtime

- [x] Long-chain run still completes.
- [x] Provider request preview still shows Codex-style continuation when
      applicable.
- [x] Context Slice used for LLM request contains no debug-only body.
- [x] Operations observer still materializes projections and emits invalidation.

### Tests

- [x] Workbench read model tests moved from orchestration to workbench.
- [x] UI HTTP tests updated for new Workbench facade.
- [x] Runtime LLM request factory tests live under LLM/application tests.
- [x] Provider renderer tests remain provider-specific.
- [x] Long-chain smoke test covers Workbench trace inspector links.

Verification notes:

- Long-chain smoke run `29ba571018a042b49b74a1165c057a87` completed through
  OpenAI Responses HTTP continuation, used local command tools, and retained
  `provider_continuation_state.previous_response_id`.
- Workbench current-turn steps endpoint returns 11 focused steps for
  `turn_id=29ba571018a042b49b74a1165c057a87`, instead of the historical
  unfiltered long-session list.
- Workbench Trace links now use `focus_id` derived from real runtime/source
  entity ids. LLM/tool focus links returned non-empty trace events in
  approximately 0.6-0.9 seconds; unfocused final response opens run-level
  trace.
- `focus_id` is intentionally not a display step id. It is a trace filter over
  source/runtime entity references such as `llm_invocation_id`, `tool_run_id`,
  `session_item_id`, `request_render_snapshot_id`, artifact id, approval id, or
  source event id.
- Event Trace read model reads `events.named.*` source event topics only and no
  longer scans `event_relay.*` / `channel.*` observation topics.

## Recommended First PR

Keep the first implementation PR boring:

1. Add `modules/workbench`.
2. Move Workbench read model code from orchestration without behavior change.
3. Move `/ui/workbench/*` routes behind Workbench interfaces.
4. Update imports and tests.
5. Do not touch provider rendering or Context Workspace in the same PR.

This gives orchestration immediate relief from UI read model ownership while
keeping runtime behavior stable.
