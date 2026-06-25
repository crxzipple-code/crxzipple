# Runtime Code Structure Convergence Plan

Date: 2026-06-20

## Purpose

This document records the next structure-only cleanup pass for the CRXZipple
agent runtime. The runtime behavior is already on the right track after the
provider-renderer, Context Workspace request snapshot, and long-chain convergence
work. The remaining problem is code shape: several application services now
work, but carry too many responsibilities in one file or keep observation logic
inside execution hot paths.

This plan does not introduce task-specific logic. It does not add compatibility
shims or a second runtime path. It should make the current runtime easier to
reason about, test, and govern.

## Non-Negotiable Principles

- Keep the kernel generic. Do not add special handling for flight search, browser
  scraping, CEAir, or any benchmark task.
- Do not reintroduce dual tracks. New extracted services replace inline logic in
  the same change.
- Do not send uncertain debug/trace observations to the LLM as facts.
- Context Workspace owns context control state and request render snapshots.
- LLM adapters/renderers own provider-specific wire input and provider response
  normalization.
- Orchestration owns run progression, execution chains, approval/waiting, and
  scheduling decisions, but should not own UI/trace/debug projection logic.
- Tool and LLM modules own their own lifecycle facts; they do not complete
  orchestration runs.

## Current State

Recent validated behavior:

- Browser `evaluate` now accepts the provider-visible `script` argument across
  the tool entrypoint, batch payload normalization, and Playwright action layer.
- Failed tool results now include generic model-visible recovery guidance.
- Runtime step budget context now tells the model when to converge.
- Final-step budget is exposed as model-visible guidance, but tool schemas are
  not withheld purely because of the step counter; hiding tools at this layer
  weakened recovery/background flows.
- Long-chain CEAir smoke test completed at `23/24` after the final-step
  convergence change.
- LLM request slices now exclude stale visible session history by default. A
  live validation run `628f0dc55c994611af271395d864a89a` rendered one inbound
  input item, one snapshot node, and a 22-character snapshot for a one-turn
  smoke request.
- Current execution-chain replay remains protocol-complete: assistant progress,
  tool calls, and tool results from the active chain are preserved for the next
  provider request, while old unrelated assistant/user messages are not replayed.
- Runtime context delivery is now provider-renderer owned. The request factory
  keeps runtime step-budget facts in metadata; the Codex renderer appends a
  compact runtime-context input item to the provider wire request without adding
  it to the continuation baseline. This keeps `previous_response_id` usable
  while making `constrained` / `critical` / `finalize_now` visible to the model.

The runtime works, but the structure still has cleanup targets:

- `runtime_llm_request_draft.py` mixes request collection, routing, budget,
  transcript planning, tool schema policy, report building, and execution-chain
  replay references.
- `llm/application/services.py` mixes profile management, credential validation,
  invocation lifecycle, provider request preview recording, and streaming result
  persistence.
- repeated probe observation still projects into run metadata for existing
  Operations/Trace readers, but the execution hot path now depends on a formal
  observation port instead of the storage shape.
- `app/integration/context_workspace_orchestration/adapter.py` is a large
  integration adapter containing multiple conceptual adapters.
- Provider request preview/summary logic exists in both LLM application service
  and provider adapter preview helpers.

## Target Shape

### Runtime Request Collection

`RuntimeLlmRequestDraftCollector` should be a coordinator, not a policy bag.

Target collaborators:

- `RuntimeTranscriptPlanBuilder`
  - chooses current inbound vs replay window;
  - produces canonical transcript/input item plan;
  - attaches execution-chain protocol refs when needed.
- `RuntimeStepBudgetPolicy`
  - computes `remaining_steps` and `step_budget_status`;
  - produces model-facing budget guidance;
  - does not mutate provider-visible tool availability.
- `RuntimeToolSchemaPolicy`
  - decides whether tool schemas may be exposed for this request;
  - consumes resolved tools, surface policy, runtime mode, and step budget;
  - follows explicit surface policy and resolved request surface, not uncertain
    heuristic suppression.
- `RuntimeRequestReportBuilder`
  - builds `RuntimeRequestReport`;
  - computes context/transcript budget summaries;
  - does not affect provider-visible input.
- `runtime_request_bootstrap_hint`
  - extracts bootstrap tool-schema hint parsing from run metadata;
  - keeps metadata normalization out of the collector.

The collector should assemble these outputs into `RuntimeLlmRequestDraft`.

### LLM Application Service

`LlmApplicationService` should no longer own every LLM concern.

Target split:

- `LlmProfileService`
  - register/update/list profiles;
  - validate credential binding expectation.
- `LlmInvocationService`
  - create invocation;
  - persist started/succeeded/failed lifecycle;
  - persist response items and continuation.
- `ProviderRequestPreviewRecorder`
  - invoke adapter preview;
  - record provider request preview;
  - publish `llm.invocation_provider_request_prepared`.
- `LlmStreamingCompletionRecorder`
  - consume final streaming result;
  - persist response summary/items/continuation.
- `LlmAdapterRequestBuilder`
  - translates invocation/profile/runtime metadata into `LlmAdapterRequest`;
  - resolves adapter credentials;
  - derives provider transport, runtime route, and runtime policy.
- `llm_invocation_events`
  - owns LLM invocation started/prepared/succeeded/failed/warmup event payloads;
  - owns provider response item/continuation extraction from streaming completed
    payloads;
  - keeps event/read-model summaries out of `LlmApplicationService`.

The public application surface can remain stable, but implementation should be
delegated.

### Tool Execution Observation

Execution should not write analysis-oriented probe observations directly into
run metadata.

Decision:

- Current Operations/Trace readers materially consume
  `repeated_probe_observation`, so it is retained.
- Retained observation is behind `ToolProbeObservationPort`, and it is explicit
  that it is not provider-visible runtime evidence.
- The default implementation still projects to run metadata; moving that
  projection to an event-backed Operations read model is a future storage
  decision, not an execution concern.

Default recommendation: keep the port boundary and avoid further executor
changes unless Operations storage is migrated.

### Tool Resource Policy

`OrchestrationEngineToolExecutor` should not own resource-lane conflict rules.

Target:

- `tool_resource_policy.py` owns `ToolResourcePolicy`, serial/parallel lane
  resolution, generic resource keys, and browser-target resource conflict
  comparison.
- The executor asks for a policy and groups prepared executions; it does not
  implement provider/tool-family resource key parsing itself.
- Browser target resource handling remains generic resource-scope behavior, not
  benchmark/task-specific browser evidence logic.

### Tool Execution Records

`OrchestrationEngineToolExecutor` should not own record payload classes.

Target:

- `tool_execution_records.py` owns `ToolRunLink`,
  `ToolExecutionPlan`, `ToolExecutionBatchOutcome`, tool lifecycle extraction,
  and argument digesting.
- The executor produces and consumes these records, but does not implement their
  payload shape.

### Context Workspace Integration Adapter

`ContextWorkspaceRunSnapshotAdapter` should be decomposed into small integration
services:

- `RunWorkspaceBindingAdapter`
- `RuntimeContextNodeUpdater`
- `RequestRenderSnapshotRecorder`
- `ToolSchemaMirrorAdapter`
- `ArtifactMirrorAdapter`
- `ContextSliceProjection`
- `RecordedRequestRenderSnapshotLoader`
- `request_render_timing`
- `request_render_refs`

The current adapter can remain as a thin facade during the same refactor, but it
must not keep duplicate logic after extraction.

### Provider Request Preview

Provider request preview belongs at the provider adapter/renderer boundary.

Target:

- LLM application service calls a single preview recorder.
- Adapter preview builders own provider-specific preview details.
- Application-level fallback preview is minimal and generic.
- Request render snapshot metadata extraction is not duplicated in two modules.

## Implementation Plan

### Phase 1: Extract Runtime Policies

Files:

- `src/crxzipple/modules/orchestration/application/runtime_llm_request_draft.py`
- new `src/crxzipple/modules/orchestration/application/runtime_step_budget_policy.py`
- new `src/crxzipple/modules/orchestration/application/runtime_tool_schema_policy.py`

Tasks:

- Move `_step_budget_status` and related runtime context budget decisions into
  `RuntimeStepBudgetPolicy`.
- Move `_should_include_tool_schemas` into `RuntimeToolSchemaPolicy`.
- Preserve final-step guidance while keeping provider-visible tool schemas
  available unless the surface policy explicitly disables them.
- Add tests proving:
  - normal turn final step still exposes resolved tools;
  - memory flush still exposes required maintenance tools;
  - non-final normal turn still exposes resolved tools;
  - budget statuses are unchanged.

Acceptance:

```bash
PYTHONPATH=src pytest -q tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_runtime_context_message.py
```

### Phase 2: Retire Or Isolate Repeated Probe Observation

Files:

- `src/crxzipple/modules/orchestration/application/engine_tool_executor.py`
- possibly Operations observation if retained.

Tasks:

- Search for all consumers of `repeated_probe_observation`.
- If no active user-facing or runtime decision consumer exists, remove:
  - `_record_tool_probe_observation`
  - `_normalized_probe_target`
  - helper fingerprint functions used only by it
  - write to `run.metadata["repeated_probe_observation"]`
- If a consumer exists, introduce an observation port and keep execution unaware
  of probe aggregation details. The default implementation may still project to
  run metadata while Operations/Trace readers consume that field.

Acceptance:

- `OrchestrationEngineToolExecutor` depends on `ToolProbeObservationPort`, not
  on the metadata storage shape.
- Probe aggregation helpers stay outside `engine_tool_executor.py`.

```bash
PYTHONPATH=src pytest -q tests/unit/test_orchestration_tools.py tests/unit/test_tool_execution.py
```

### Phase 3: Extract Provider Request Preview Recorder

Files:

- `src/crxzipple/modules/llm/application/services.py`
- new `src/crxzipple/modules/llm/application/provider_request_preview_recorder.py`
- `src/crxzipple/modules/llm/infrastructure/adapters/provider_request_preview.py`

Tasks:

- Move `_provider_request_payload_preview` and
  `_record_provider_request_payload_preview` out of `services.py`.
- Keep provider-specific preview in adapter helpers.
- Remove duplicate request render snapshot metadata extraction from application
  fallback if adapter preview already supplies it.
- Application fallback preview should only include model, provider, message/item
  counts, tool count, and configured options.

Acceptance:

```bash
PYTHONPATH=src pytest -q tests/unit/test_llm.py tests/unit/test_llm_adapters.py tests/unit/test_llm_runtime_request_factory_builder.py
```

### Phase 4: Split LLM Service Internals

Files:

- `src/crxzipple/modules/llm/application/services.py`
- new profile/invocation/stream recorder modules.

Tasks:

- Extract profile registration and credential expectation validation.
- Extract invocation lifecycle persistence.
- Extract streaming completion persistence.
- Keep public imports stable through `llm/application/__init__.py` where needed.

Acceptance:

```bash
PYTHONPATH=src pytest -q tests/unit/test_llm.py tests/unit/test_llm_adapters.py tests/unit/test_operations_llm_read_model.py
```

### Phase 5: Split Context Workspace Orchestration Adapter

Files:

- `src/crxzipple/app/integration/context_workspace_orchestration/adapter.py`
- existing neighboring files in the same package.

Tasks:

- Extract request render snapshot recording.
- Extract runtime context message/node update.
- Extract tool schema mirror operations.
- Keep the public adapter as an assembly-facing facade only.

Acceptance:

```bash
PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_workspace_session_adapter.py
```

## Execution Checklist

### Phase 1: Runtime Request Policy Extraction

- [x] Add `runtime_step_budget_policy.py`.
- [x] Move step budget status calculation out of
  `runtime_llm_request_draft.py`.
- [x] Add `RuntimeStepBudgetPolicy` tests for `available`, `constrained`,
  `critical`, and `finalize_now`.
- [x] Add `runtime_tool_schema_policy.py`.
- [x] Move tool schema exposure decision into `RuntimeToolSchemaPolicy`.
- [x] Cover normal turn final-step tool schema exposure.
- [x] Cover normal turn non-final tool schema exposure.
- [x] Cover maintenance/memory flush tool schema exposure.
- [x] Add `runtime_request_report_builder.py`.
- [x] Move report construction, context-budget resolution, transcript budget
  refs, execution-chain protocol refs, and assistant-progress protocol refs out
  of `runtime_llm_request_draft.py`.
- [x] Add `runtime_request_bootstrap_hint.py`.
- [x] Move runtime request bootstrap hint metadata parsing out of
  `runtime_llm_request_draft.py`.
- [x] Reduce `runtime_llm_request_draft.py` to 833 lines.
- [x] Run focused draft/context tests after extraction.

### Phase 2: Tool Probe Observation Cleanup

- [x] Search all current readers of `repeated_probe_observation`.
- [x] Decide remove-first vs move-behind-observation-port.
- [x] Move aggregation details out of `engine_tool_executor.py`.
- [x] Keep fingerprint helpers only in `tool_probe_observation.py`.
- [x] Replace direct run metadata write in executor with a formal observation
  port.
- [x] Verify no probe observation is sent to LLM as provider-visible evidence.
- [x] Extract tool resource policy calculation and conflict helpers into
  `tool_resource_policy.py`.
- [x] Remove browser target resource key parsing from
  `engine_tool_executor.py`.
- [x] Extract tool execution records into `tool_execution_records.py`.
- [x] Move tool lifecycle extraction and argument digest calculation out of
  `engine_tool_executor.py`.
- [x] Export tool execution records and resource policy helpers from the
  orchestration application package surface.
- [x] Run Phase 2 acceptance tests.

### Phase 3: Provider Request Preview Ownership

- [x] Add `provider_request_preview_recorder.py`.
- [x] Add one shared `provider_request_input_preview.py` helper for
  request-metadata preview extraction.
- [x] Move adapter preview invocation out of `llm/application/services.py`.
- [x] Move provider request preview persistence out of
  `llm/application/services.py`.
- [x] Keep provider-specific preview formatting in adapter/renderer helpers.
- [x] Remove duplicated request render snapshot metadata extraction from the
  application fallback path.
- [x] Keep fallback preview minimal and generic.
- [x] Run Phase 3 acceptance tests.

### Phase 4: LLM Service Internal Split

- [x] Extract `LlmProfileService`.
- [x] Move credential expectation validation with profile registration.
- [x] Extract `LlmInvocationService`.
- [x] Extract invocation lifecycle persistence.
- [x] Extract response item / continuation persistence.
- [x] Extract `LlmStreamingCompletionRecorder`.
- [x] Extract `LlmAdapterRequestBuilder`.
- [x] Move adapter credential resolution and runtime route/policy/transport
  derivation out of `llm/application/services.py`.
- [x] Extract `llm_invocation_events.py`.
- [x] Move invocation event payload builders, runtime request summary helpers,
  and streaming completed-payload extraction out of
  `llm/application/services.py`.
- [x] Reduce `llm/application/services.py` to 1447 lines.
- [x] Export provider request preview recorder/input preview helpers from the
  LLM application package surface.
- [x] Keep public application imports stable.
- [x] Run Phase 4 acceptance tests.

### Phase 5: Context Workspace Orchestration Adapter Split

- [x] Extract `RunWorkspaceBindingAdapter`.
- [x] Do not introduce a standalone `RuntimeContextNodeUpdater`; the remaining
  node-state mutation is tool-schema enable/expand and belongs inside
  `ToolSchemaMirrorAdapter`.
- [x] Extract `RequestRenderSnapshotRecorder`.
- [x] Extract `ToolSchemaMirrorAdapter`.
- [x] Confirm existing `ArtifactMirrorAdapter` stays separate or is wired as a
  narrow collaborator.
- [x] Extract Context Slice projection helpers into a narrow projection module.
- [x] Extract recorded request-render snapshot loading into
  `RecordedRequestRenderSnapshotLoader`.
- [x] Extract request-render timing helpers into `request_render_timing.py`.
- [x] Extract request-render ref helpers into `request_render_refs.py`.
- [x] Remove duplicate metadata string extraction helper from
  `tool_schema_mirror.py`.
- [x] Reduce `ContextWorkspaceRunSnapshotAdapter` to an assembly-facing facade.
- [x] Remove duplicate tool schema mirror logic after extraction.
- [x] Run Phase 5 acceptance tests for the extracted adapter boundaries.

### Final Acceptance

- [x] Run the full verification matrix.
- [x] Run a bounded browser-heavy long-chain smoke test.
- [x] Confirm final-step LLM request keeps resolved tool schemas and relies on
  step-budget guidance instead of heuristic suppression.
- [x] Confirm normal LLM request slice excludes stale visible session history
  and keeps only current inbound input plus protocol-required replay refs.
- [x] Confirm current execution-chain assistant progress remains provider-visible
  on the following LLM request.
- [x] Confirm runtime context is provider-visible without breaking provider-native
  websocket continuation.
- [x] Confirm no `max_steps_exceeded` on the long-chain smoke.
- [x] Confirm Workbench timeline does not expose debug-only fields.
- [x] Update this checklist with completed items and any changed decisions.

## Verification Matrix

After each phase, run targeted tests. After the full plan:

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_runtime_llm_request_draft_collector.py \
  tests/unit/test_runtime_context_message.py \
  tests/unit/test_orchestration_context_workspace_snapshot.py \
  tests/unit/test_runtime_transcript.py \
  tests/unit/test_llm.py \
  tests/unit/test_llm_adapters.py \
  tests/unit/test_tool_providers.py \
  tests/unit/test_orchestration_tools.py
```

Latest result:

```text
233 passed in 220.47s
```

Focused live slice validation:

```text
run_id=628f0dc55c994611af271395d864a89a
provider_continuation_state.input_item_count=1
request_render_snapshot_id=ctxsnap_cab65ce6f0d6450eb075055bf0d70c4e
snapshot_included_node_count=1
snapshot_text_chars=22
```

Provider-native runtime context validation:

```text
run_id=c319ef8c79994d99af6ab1984284133b
status=completed
current_step=13
max_steps=14
latest_invocation=43c83e9a182c4126b132def97d9f9316
has_previous_response_id=true
input_delta_count=3
input_baseline_count=35
provider_input_count=3
step_budget_status=finalize_now
```

The run completed instead of failing with `max_steps_exceeded`. It did not obtain
official CEAir fare data; the final answer correctly reported the verified
official page path and stated that flight/price data was not confirmed. This is
recorded as a runtime-channel success and a capability/browser-state limitation,
not as task-specific success.

Workbench timeline validation for the same run after read-model cleanup:

```text
steps=40
timeline=40
continuation_count=0
debug_body=-1
payload_preview=-1
provider_request_payload_preview=-1
provider_wire_preview=-1
previous_response_id=-1
input_delta_count=-1
input_baseline_count=-1
render_report=-1
request_metadata=-1
runtime_request_summary=-1
<context_tree>=-1
```

The `/ui/workbench/runs/{run_id}/steps?turn_id={turn_id}` and embedded
`run.timeline` surfaces no longer expose provider continuation IDs, payload
previews, render reports, request metadata, or Context Tree debug bodies.

Focused renderer validation:

```text
133 passed in 1.33s
```

Focused runtime request collector validation after Phase 1 extraction:

```text
52 passed in 0.66s
runtime_llm_request_draft.py: 833 lines
```

Focused LLM service validation after adapter request builder extraction:

```text
161 passed in 17.01s
llm/application/services.py: 1755 lines
```

Focused LLM event payload validation after invocation event extraction:

```text
126 passed in 15.86s
llm/application/services.py: 1447 lines
```

Focused Context Workspace adapter validation after recorded snapshot loader and
timing extraction:

```text
36 passed in 0.76s
context_workspace_orchestration/adapter.py: 465 lines
```

Focused tool resource policy validation after extraction:

```text
46 passed in 197.17s
engine_tool_executor.py: 1035 lines
```

Focused tool execution record validation after extraction:

```text
66 passed in 224.45s
engine_tool_executor.py: 890 lines
```

Focused application surface validation after export cleanup:

```text
143 passed in 227.26s
```

Long-chain smoke:

- Submit a normal Workbench turn for a browser-heavy website task.
- Use a bounded `max_steps`.
- Verify:
  - model can discover and enable needed tools;
  - final-step LLM request keeps the resolved request surface and exposes
    `finalize_now` guidance;
  - run completes or provides a supported limitation instead of
    `max_steps_exceeded`;
  - Workbench timeline shows assistant progress, tool calls/results, and final
    answer without debug-only fields.

## Success Criteria

- Runtime request draft collector is below 900 lines or clearly delegates major
  policy sections.
- LLM application service is split so profile/invocation/preview/streaming can
  be tested independently.
- Tool execution hot path no longer owns repeated-probe observation aggregation.
- Provider request preview metadata has one owner.
- No new compatibility branch, no duplicate request path, no task-specific
  evidence gate.
- Long-chain browser task still passes after each phase.

## Open Decisions

- Whether `repeated_probe_observation` should move from run metadata to an
  event-backed Operations projection. Current status: active Operations/Trace
  consumers exist, so execution depends only on `ToolProbeObservationPort`; the
  default implementation still projects into run metadata for those readers.
- Whether `runtime_context_message.py` should remain in app integration or move
  beside runtime request policy. Current status: keep it in integration because
  the runtime request factory now passes pure runtime context metadata to the
  provider renderer, while Context Workspace still owns the debug/rendered
  context message for snapshots.
