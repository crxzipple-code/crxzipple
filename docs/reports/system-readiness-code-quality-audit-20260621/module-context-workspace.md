# Module Audit: context_workspace

## Verdict

High importance, medium risk. Context Workspace is the correct owner of context tree, render snapshots, node state, and tool surface mirror. Root-node bootstrap and projection/service seams have been split, but the module remains a central control plane and still needs strict runtime budget, mirror consistency, and provider-input invariants.

## Evidence

- 42 Python files, about 8891 lines.
- Large files include `application/rendering/xml_renderer.py` (884), `application/rendering/provider_mirror.py` (758), `infrastructure/persistence/repositories.py` (741), `application/services.py` (735), `application/models.py` (458), `application/context_slice_item_projection.py` (429), `application/context_tree_maintenance.py` (396), and `interfaces/http.py` (320).

## Findings

- The module is correctly positioned as context control plane rather than owner of Session/Tool/Memory/Artifact data truth.
- The split into root node families, selection, control projection, item projection, tool surface projection, maintenance, actions, and refs is positive.
- The app integration session tree adapter is now a route coordinator over
  focused projection helpers: block/content formatting, tool-result content
  normalization, evidence facts, tool lifecycle classification, execution-step
  node projection, segment seed projection, segment range projection, segment
  id/scope values, session message node projection, item/tool-call pairing,
  consumed tool-history folding, tool-interaction node projection, and
  tool-interaction summary formatting live outside the provider. The provider
  still maps Session owner facts to Context Tree children, but it no longer owns
  those pure formatting and projection rules.
- The app integration orchestration tool-schema bootstrap has been split into
  focused units: the public bootstrap entry now coordinates draft metadata,
  catalog-backed defaults, and tree fallback; catalog lookup, tree fallback
  projection, tree node expansion, and group-ref parsing live in separate
  helpers. This keeps provider tool-schema defaults tied to selected Context
  Workspace state without making orchestration/provider code parse tree internals
  directly.
- Request snapshot metadata and tool-schema mirror integration are now split
  by projection concern. Provider attachment/tool schema conversion, session
  node refs, draft transcript budget/protocol-required refs, and small metadata
  normalization helpers live outside `snapshot_metadata.py`; `tool_schema_mirror.py`
  is now a thin adapter over context-slice schema projection, request schema
  selection, and Context Tree node synchronization.
- Run workspace metadata and Context Slice projection have also been split by
  concern. The run workspace metadata entry now only assembles the metadata
  payload; run node payloads, continuation payloads, and formatting helpers live
  in focused modules. Context Slice projection now separates report/ref
  extraction from provider input item projection, keeping selected-slice
  accounting apart from model-visible input construction.
- The Context Workspace orchestration integration split has been deepened
  without adding compatibility shims. Provider input payload construction for
  individual context-slice items now lives outside the projected-input iterator;
  Context Tree parent-node expansion for requested tool schemas now lives outside
  schema enablement; run runtime-context text projection is isolated from run
  node payload assembly; and snapshot metadata delegates tool-schema mirror and
  artifact attachment metadata to focused group builders.
- The request-render hot path has been further narrowed. Current inbound input
  detection/projection and projected input merge/dedupe rules now live outside
  the public draft-input projection entry. Tool schema node identity/source-id
  derivation lives outside tree expansion, and request-render timing/cost
  attachment lives in the timing helper instead of the pipeline coordinator.
- Request-render pipeline responsibilities are now split by stable phase without
  hiding the phase order. Draft/report input ref selection, requested/visible
  tool schema selection, control/context slice build-input construction, and
  slice projection bundling live in focused helpers. The pipeline remains the
  visible coordinator for workspace binding, slice construction, metadata
  building, snapshot persistence, and return-record assembly.
- Request-render DTO assembly has also been separated from the phase coordinator:
  metadata bundle construction, final `RequestRenderSnapshotRecord` construction,
  request-render tool-schema metadata, and `RecordContextSnapshotInput`
  persistence payload construction now live in focused helpers. The pipeline
  still owns phase timing and the decision of which persistence steps run.
- Request-render workspace binding, request-render snapshot-recorder payload
  persistence, and full context-snapshot draft-input metadata are now separated
  from the phase coordinators as well. This keeps provider-visible request
  construction, persistence payload construction, and diagnostic metadata
  grouping explicit while avoiding a second source of owner facts.
- Request render snapshot metadata keeps DTOs and the builder entry while
  visible-input summary and cost/budget calculations live in focused helper
  modules. `request_render_snapshot_pipeline.py` is intentionally left as the
  phase coordinator rather than split into hidden micro-facades.
- Request render snapshots now record `request_render_cost` with selected node count,
  selected session item count, provider-visible tool count, projected input item count,
  rendered input character count, and elapsed milliseconds. The same cost payload is
  mirrored into `request_render_snapshot.cost` and persisted render reports.
- Long-session request-render coverage now verifies that many large historical session
  nodes do not expand the provider-visible input when the current draft frontier selects
  a single session item; owner resolution and rendered input size stay bounded.
- Risk remains around render snapshot hot path cost and accidental reintroduction of full tree debug body into LLM input.
- Root-node family split is complete; service/model/rendering files should continue to be watched by runtime surface.

## Launch Risks

- Slow context snapshot/render can make Workbench appear stuck and delay LLM invocation.
- If debug-only tree state leaks into provider input, model judgment can be degraded.
- Hidden inconsistencies between tree references and owner facts can cause misleading UI or prompt context.

## Recommendations

- Keep full tree debug body outside LLM hot path.
- Add tests verifying provider input includes only selected slices and protocol-required items.
- Add snapshot cost metrics: selected nodes, rendered chars, provider-visible tools, session items included, elapsed time.
- Treat tree as control plane of refs/state, not duplicate storage of owner facts.
- Continue splitting app integration adapters by pure projection concern first
  before touching owner session lifecycle behavior. The current session adapter
  split should remain a control-plane mapping layer, not a second source of
  Session truth.

## Detailed Pass 1

### Files Reviewed

- `application/root_nodes.py`
- `application/services.py`
- `application/context_slice_item_projection.py`
- `application/context_tree_maintenance.py`
- `application/context_control_slice_builder.py`
- `application/context_tool_surface_projection.py`
- `application/rendering/pipeline.py`
- `application/rendering/xml_renderer.py`
- `infrastructure/persistence/repositories.py`
- `interfaces/http.py`

### File-Level Assessment

`application/root_nodes.py` was 921 lines and is now 123 lines after moving static
section roots, instruction/agent guidance, run/execution nodes, planning nodes,
resource roots, constants, and shared estimate/payload helpers into focused
`root_node_*` modules. It now keeps ordering, public constant re-exports, and parent
lookup.

`application/services.py` has already been reduced to distinct services: `ContextWorkspaceService`, `ContextTreeService`, `ContextObservationSnapshotService`, `RequestRenderSnapshotService`, `ContextSliceBuilderService`, and `ContextControlSliceService`. This is a good direction.

`context_slice_item_projection.py`, `context_control_slice_builder.py`, and `context_tool_surface_projection.py` show the intended control-plane/projection split.

### Boundary Cleanliness

The key rule is correct: Context Workspace owns context tree state, render snapshot, and provider attachment mirror; it does not own Session/Tool/Memory/Artifact truth.

Risk pattern:

- Root node payloads can duplicate runtime contract or owner facts if not constrained.
- Render snapshots can accidentally become large debug snapshots in the LLM hot path.
- Tool surface projection can drift from Tool owner catalog if mirror metadata is treated as truth.

### Lifecycle Clarity

Context lifecycle should be:

1. owner module facts exist elsewhere
2. context tree stores refs/control state
3. render snapshot selects a bounded slice
4. provider renderer translates selected slice
5. observation/debug can inspect full tree separately

Current implementation is close to this, but root and render layers need explicit tests.

### Persistence And Efficiency

Context persistence is appropriate for tree nodes/snapshots/mirrors. The efficiency risk is full tree rebuild or snapshot rendering in hot path. This has been a prior issue and should remain guarded.

### Concurrency And Multi-User Readiness

Context nodes must be scoped by session/run/workspace/agent. Multi-user readiness depends on not mixing tree refs or provider attachment mirrors across sessions.

### Remediation Checklist

- [x] Split `root_nodes.py` by instruction roots, execution roots, agent roots, run roots, planning roots, resources, constants, and shared helpers.
- [x] Add render snapshot budget tests for long sessions and large tool surfaces.
- [x] Add selected-slice coverage that guards LLM provider input from full debug tree/root body replay in covered paths.
- [x] Add mirror consistency tests against Tool owner catalog and Session item refs.
- [x] Track render elapsed time, selected node count, selected session item count, provider-visible tool count, and rendered char count in request render snapshots.

### Remediation Verification

Command passed after the current Context Workspace split wave:

```bash
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py tests/unit/test_orchestration_context_workspace_snapshot.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py::test_preview_request_render_snapshot_does_not_mutate_existing_workspace tests/unit/test_orchestration_context_workspace_snapshot.py::test_context_workspace_snapshot_projects_context_slice_session_input_items --tb=short
PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py::test_request_render_budget_stays_bounded_for_long_session_tree --tb=short
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tool_adapter.py::test_tool_schema_mirror_drops_stale_function_removed_from_owner_catalog tests/unit/test_context_workspace_tree_service.py::test_context_slice_builder_resolves_session_item_text_from_owner tests/unit/test_context_workspace_tree_service.py::test_context_slice_builder_reports_unresolved_session_item_refs_only --tb=short
```

Result:

- Context Workspace tree/tool/snapshot targeted suite: 80 passed
- Request render cost metadata focus tests: 2 passed
- Long-session request-render budget focus test: 1 passed
- Mirror consistency focus tests: 3 passed
- 2026-06-25 session adapter evidence split:
  `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py --tb=short --maxfail=1`
  -> 38 passed.
- 2026-06-25 session adapter projection split:
  `python -m ruff check src/crxzipple/app/integration/context_workspace_session*.py tests/unit/test_context_workspace_session_adapter.py`
  -> passed.
  `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py tests/unit/test_orchestration_context_workspace_snapshot.py --tb=short --maxfail=1`
  -> 122 passed.
- 2026-06-25 tool-schema bootstrap split:
  `python -m ruff check src/crxzipple/app/integration/context_workspace_orchestration/tool_schema_bootstrap.py src/crxzipple/app/integration/context_workspace_orchestration/tool_schema_catalog_bootstrap.py src/crxzipple/app/integration/context_workspace_orchestration/tool_schema_tree_bootstrap.py src/crxzipple/app/integration/context_workspace_orchestration/tool_schema_tree_nodes.py src/crxzipple/app/integration/context_workspace_orchestration/tool_schema_group_refs.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_orchestration_context_workspace_snapshot.py`
  -> passed.
  `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_request_render_input_projection.py tests/unit/test_runtime_tool_schema_policy.py --tb=short --maxfail=1`
  -> 65 passed.
- 2026-06-25 snapshot/tool-schema mirror split:
  `python -m ruff check src/crxzipple/app/integration/context_workspace_orchestration/snapshot_metadata.py src/crxzipple/app/integration/context_workspace_orchestration/snapshot_provider_attachments.py src/crxzipple/app/integration/context_workspace_orchestration/snapshot_node_refs.py src/crxzipple/app/integration/context_workspace_orchestration/snapshot_draft_budget.py src/crxzipple/app/integration/context_workspace_orchestration/snapshot_metadata_values.py src/crxzipple/app/integration/context_workspace_orchestration/tool_schema_mirror.py src/crxzipple/app/integration/context_workspace_orchestration/tool_schema_context_slice_projection.py src/crxzipple/app/integration/context_workspace_orchestration/tool_schema_request_selection.py src/crxzipple/app/integration/context_workspace_orchestration/tool_schema_node_sync.py src/crxzipple/app/integration/context_workspace_orchestration/request_render_snapshot_pipeline.py`
  -> passed.
  `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_request_render_input_projection.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_runtime_tool_schema_policy.py --tb=short --maxfail=1`
  -> 149 passed.
- 2026-06-25 run workspace / context slice / request-render metadata split:
  `python -m ruff check src/crxzipple/app/integration/context_workspace_orchestration tests/unit/test_context_workspace_tree_service.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_request_render_input_projection.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_runtime_tool_schema_policy.py`
  -> passed.
  `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_request_render_input_projection.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_runtime_tool_schema_policy.py tests/unit/test_llm_runtime_request_factory.py tests/unit/test_provider_request_renderer_protocol.py --tb=short --maxfail=1`
  -> 164 passed.
- 2026-06-25 provider input payload / tool expansion / grouped snapshot metadata
  split:
  `python -m ruff check src/crxzipple/app/integration/context_workspace_orchestration`
  -> passed.
  `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_request_render_input_projection.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_runtime_tool_schema_policy.py tests/unit/test_llm_runtime_request_factory.py tests/unit/test_provider_request_renderer_protocol.py --tb=short --maxfail=1`
  -> 164 passed.
- 2026-06-25 draft input / tool node values / request-render timing split:
  `python -m ruff check src/crxzipple/app/integration/context_workspace_orchestration`
  -> passed.
  `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_request_render_input_projection.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_runtime_tool_schema_policy.py tests/unit/test_llm_runtime_request_factory.py tests/unit/test_provider_request_renderer_protocol.py --tb=short --maxfail=1`
  -> 164 passed.
- 2026-06-25 request-render pipeline phase split:
  `python -m ruff check src/crxzipple/app/integration/context_workspace_orchestration`
  -> passed.
  `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_request_render_input_projection.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_runtime_tool_schema_policy.py tests/unit/test_llm_runtime_request_factory.py tests/unit/test_provider_request_renderer_protocol.py --tb=short --maxfail=1`
  -> 164 passed.
- 2026-06-25 request-render DTO/persistence helper split:
  `python -m ruff check src/crxzipple/app/integration/context_workspace_orchestration`
  -> passed.
  `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_request_render_input_projection.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_runtime_tool_schema_policy.py tests/unit/test_llm_runtime_request_factory.py tests/unit/test_provider_request_renderer_protocol.py --tb=short --maxfail=1`
  -> 164 passed.
- 2026-06-25 request-render workspace / snapshot persistence / draft metadata
  split:
  `python -m ruff check src/crxzipple/app/integration/context_workspace_orchestration`
  -> passed.
  `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_request_render_input_projection.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_runtime_tool_schema_policy.py tests/unit/test_llm_runtime_request_factory.py tests/unit/test_provider_request_renderer_protocol.py tests/unit/test_context_snapshot_metadata.py --tb=short --maxfail=1`
  -> 169 passed.
