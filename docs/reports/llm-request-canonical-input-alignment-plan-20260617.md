# LLM Request Canonical Input Alignment Plan

Date: 2026-06-17

## Background

This document focuses on one narrow question: whether the final data sent to the LLM/provider matches the intended Codex-like request shape.

Recent inspection shows that CRXZipple's Codex provider wire shape is close to Codex at the top level:

```text
instructions + input + tools
```

For Codex WebSocket transport the final payload is:

```json
{
  "type": "response.create",
  "model": "...",
  "instructions": "...",
  "input": [],
  "tools": [],
  "tool_choice": "auto",
  "reasoning": {},
  "store": false,
  "stream": true
}
```

When provider-native continuation is valid, it should become:

```json
{
  "type": "response.create",
  "previous_response_id": "resp_xxx",
  "input": ["delta response items only"]
}
```

The current problem is not primarily the Codex renderer's wire schema. The problem is the canonical input handed to the renderer.

Latest inspected CRXZipple invocation:

```text
transport=websocket
message_type=response.create
input_items=156
messages=47
tool_schemas=24
provider_context_messages=0
has_previous_response_id=false
input_delta_mode=false
```

The provider input included many runtime/control/observation items as ordinary messages:

```text
runtime.contract
agent.home
run.flow
run.constraints
execution.continuation
session.turn.current
session.steps.current
session.step.*
runtime_llm_invocation
runtime_tool_run
runtime_session_message
assistant progress
empty assistant summaries
```

Codex uses the same broad provider shape, but its `input` is closer to clean response-item replay:

```text
user message
assistant message
reasoning summary
function_call
function_call_output
compact summary
```

Therefore the primary alignment target is:

```text
Context Tree / Session / Runtime facts
  -> canonical LlmInputItem[]
  -> provider renderer
  -> Codex wire payload
```

## Decisions

- Do not add compatibility shims for old request shapes.
- Do not keep dual prompt paths.
- Do not send uncertain diagnostics, trace reports, debug bodies, evidence verdicts, or task-specific next-step heuristics to the LLM.
- Do not create task-specific modules for flight search or browser behavior.
- Context Tree remains the control plane and slice owner.
- Provider renderers remain provider/transport/model translators.
- The Codex adapter must align to observed Codex source/trace behavior, not assumptions.

## Responsibility Split

### Context Tree / Slice Policy

Owns what is eligible for the `llm_request_slice`.

It must not include raw runtime/control/trace nodes as model-visible message content.

Allowed as control refs, but not as provider input text:

```text
session.turn.current
session.steps.current
session.step.*
runtime_llm_invocation
runtime_tool_run
execution.continuation
tool schema mirror reports
budget reports
debug tree bodies
```

If a node matters to the model, it must be projected into a canonical runtime transcript item first.

### Session / Runtime Projection

Owns conversion from owner facts to canonical `LlmInputItem`.

It should emit only model-semantic items:

```text
message(role=user)
message(role=assistant, phase=commentary|final)
reasoning(summary only when model-visible)
function_call
function_call_output
provider_external_item only when provider can replay it
compaction summary
```

It must not mechanically convert every SessionItem, step, run fact, progress record, or tool run fact into a provider message.

### Runtime Draft Assembly

Owns assembling one `LlmAdapterRequest`:

```text
provider_context_messages
input_items
tool_schemas
continuation
request_policy
overrides
```

It must treat `input_items` as the only provider input source when a context slice exists. Fallback session replay should be removed rather than retained as a hidden second path.

### Provider Renderer

Owns provider-specific translation:

```text
canonical LlmInputItem[] -> provider input[]
tool_schemas -> tools
provider_context_messages + system messages -> instructions
continuation state -> previous_response_id + delta input when valid
```

The renderer should not understand CRXZipple runtime node types. It should only enforce provider validity:

- drop empty messages;
- reject orphan tool outputs;
- preserve tool-call/tool-output pairing;
- downgrade unsupported item kinds with an explicit loss report;
- never place metadata/debug fields into provider wire payload.

### Tool Surface

Owns which tools are provider-visible.

Default LLM request should expose a small general-purpose tool surface, then allow model-driven expansion through `capability.search(enable=true)`.

Weather, browser, mobile, market, and other domain tools should not all be visible by default unless selected by current context/tool policy.

## Current Misalignment

### 1. Runtime/control nodes are rendered as ordinary messages

Observed provider input mapping includes `session.step.*`, `runtime_llm_invocation`, and `runtime_tool_run`.

These are not response items. They are runtime ledger/control facts. They should be visible to Workbench/Trace but not directly rendered as provider input text.

### 2. Assistant progress is replayed as assistant messages

Progress messages are useful for UI and live updates. They are not always useful as model-visible history.

Only provider/runtime items equivalent to Codex `AgentMessage` or `Reasoning` should be replayed.

### 3. Empty assistant summaries are sent

Observed content:

```json
{"summary": [], "text": null}
```

This must never reach provider input as an assistant message.

### 4. Duplicate assistant content appears

Repeated progress text appeared as separate assistant messages. This can anchor the model into a loop.

The request projection should dedupe identical adjacent assistant progress unless they represent distinct provider response items.

### 5. WebSocket continuation is not active

Observed:

```text
transport=websocket
has_previous_response_id=false
input_delta_mode=false
input_baseline_count=156
input_delta_count=0
```

This means the request is still full replay. Codex-like continuation requires valid provider response id plus stable input/tool/instructions fingerprints.

### 6. Tool surface is too broad

Observed tool schemas included browser, weather, capability search, and exec simultaneously.

For a generic agent, default tools should bias toward discovery and local execution, not pre-expanded domain tool groups.

## Target Request Shape

### Codex WebSocket first turn

```json
{
  "type": "response.create",
  "model": "gpt-5.4-mini",
  "instructions": "runtime contract + provider context",
  "input": [
    {
      "role": "user",
      "content": [
        {"type": "input_text", "text": "latest task"}
      ]
    }
  ],
  "tools": [
    {"type": "function", "name": "exec", "...": "..."},
    {"type": "function", "name": "process", "...": "..."},
    {"type": "function", "name": "capability_search", "...": "..."}
  ],
  "tool_choice": "auto",
  "store": false,
  "stream": true
}
```

### Codex WebSocket tool continuation

```json
{
  "type": "response.create",
  "previous_response_id": "resp_previous",
  "input": [
    {
      "type": "function_call_output",
      "call_id": "call_x",
      "output": "tool result"
    }
  ],
  "tools": ["same tool schema fingerprint"],
  "instructions": "same instructions fingerprint"
}
```

### Full replay fallback

When fingerprints do not match or provider state is missing, send full clean response-item replay:

```text
user message
assistant reasoning summary if needed
assistant function_call
function_call_output
assistant message
latest user/tool event
```

No runtime ledger nodes should appear as plain text messages.

### Normal turn protocol replay

Normal user follow-up turns must not directly replay all ordinary chat history.
However, model-issued tool protocol pairs remain provider-semantic history and
must be preserved as structured input items while the active session remains in
scope:

```text
function_call(call_id=x)
function_call_output(call_id=x)
latest user message
```

This prevents the next model turn from relying on an uncertain summary such as
`recent_tool_interactions` when an exact tool call id and output are available.
The Context Tree still controls ordinary history compression and visibility; the
runtime transcript preserves provider protocol continuity.

## Implementation Plan

## Phase 1: Audit Actual Provider Payload

- [x] Add a CLI/debug command that prints one invocation's final provider payload shape:
  - transport;
  - instructions token estimate;
  - provider input count;
  - provider input item type counts;
  - tool names;
  - continuation status.
- [x] Add a redacted payload dump mode for local debugging.
- [x] Add a comparison report for:
  - canonical input items;
  - provider input items;
  - dropped/loss items.
- [x] Ensure this audit command reads LLM invocation storage and does not alter runtime state.

## Phase 2: Clean `llm_request_slice`

- [x] Update Context Workspace slice policy so `llm_request_slice` excludes runtime ledger/control nodes as message content:
  - `session.turn.current`;
  - `session.steps.current`;
  - `session.step.*`;
  - `runtime_llm_invocation`;
  - `runtime_tool_run`;
  - raw run constraints if they are only bookkeeping.
- [x] Preserve those nodes for `trace_timeline_slice` and `debug_tree_slice`.
- [x] Keep references in slice reports, not provider input text.
- [x] Add tests proving these nodes do not become `LlmInputItem.message`.

## Phase 3: Formal Runtime Transcript Projection

- [x] Create or formalize a request-side projector:

```text
ContextObservationSlice + owner facts
  -> RuntimeTranscriptItem[]
  -> LlmInputItem[]
```

- [x] Allow only these model-visible transcript item kinds:
  - user message;
  - assistant final message;
  - assistant commentary when explicitly model-visible;
  - reasoning summary;
  - function call;
  - function call output;
  - compact summary.
- [x] Drop empty assistant messages.
- [x] Drop `{"summary": [], "text": null}`.
- [x] Dedupe identical adjacent assistant progress.
- [x] Preserve tool protocol ordering:

```text
function_call(call_id=x)
function_call_output(call_id=x)
```

- [x] Preserve prior active-session tool protocol pairs for normal follow-up turns while keeping ordinary chat history out of direct replay.
- [x] Emit a loss report for dropped unsupported items.

## Phase 4: Remove Hidden Fallback Replay

- [x] Remove fallback that bypasses Context Tree and directly replays session history when a context slice exists.
- [x] Make one path authoritative:

```text
Context Tree slice -> Runtime Transcript Projector -> LlmInputItem[]
```

- [x] Fail fast in tests if both slice input and legacy replay input contribute to the same request.
- [x] Update docs to state that Session is a ledger, not direct provider prompt input.

## Phase 5: Provider Context Messages

- [x] Move stable runtime/skill/capability context that belongs in instructions into `provider_context_messages`.
- [x] Keep actual user/task/tool history in provider `input`.
- [x] Stop rendering agent home placeholders with empty content into provider input.
- [x] Add tests that provider context is merged into Codex `instructions`.

## Phase 6: Tool Surface Narrowing

- [x] Define default always-visible tools:
  - `exec`;
  - `process`;
  - `capability.search`.
- [x] Move browser/weather/domain tool groups behind capability discovery unless pinned by Context Tree or current run policy.
- [x] Ensure `capability.search(enable=true)` both discovers and enables matching tools.
- [x] Add tests that weather/browser/web tools are not visible by default without explicit bootstrap.
- [x] Add tests that enabled tools appear in the next provider request.

## Phase 7: Codex WebSocket Continuation

- [x] Persist provider response id after each completed Codex response.
- [x] Persist input item fingerprints, instructions fingerprint, and tool fingerprints.
- [x] On the next request, send `previous_response_id + delta input` only when:
  - transport is WebSocket;
  - provider family supports continuation;
  - previous response id exists;
  - previous fingerprints exist;
  - current input has previous input as prefix;
  - instructions fingerprint matches;
  - tool fingerprints match.
- [x] Otherwise send full clean input without `previous_response_id`.
- [x] Add integration test that a second tool-result turn sends only `function_call_output` as delta.

## Phase 8: Provider Renderer Boundary Tests

- [x] Codex renderer:
  - renders canonical message to `role/content`;
  - renders function call to `function_call`;
  - renders tool result to `function_call_output`;
  - excludes metadata/debug fields;
  - excludes empty messages.
- [x] Anthropic/Gemini/OpenAI renderers:
  - document downgrade/loss behavior for unsupported response-item kinds.
- [x] Cross-provider tests use the same canonical `LlmInputItem[]`.

## Validation

Run focused tests:

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_openai_codex_renderer.py \
  tests/unit/test_openai_codex_transport_wire_contract.py \
  tests/unit/test_provider_renderer_canonical_request_integration.py \
  tests/unit/test_runtime_transcript.py \
  tests/unit/test_orchestration_runtime_llm_request.py
```

Run Workbench/LLM request inspection after a long-chain task:

```bash
source scripts/dev/infra-env.sh
python -m crxzipple.main orchestration runs inspect-latest --include-llm-request
```

Expected metrics:

```text
provider input item count: materially lower than current 156
runtime/control node messages: 0
empty assistant messages: 0
duplicate adjacent assistant progress: 0
tool schemas default count: small
Codex websocket second turn: previous_response_id=true when fingerprints match
```

## Acceptance Criteria

- [x] Final provider payload still uses Codex-native `instructions + input + tools`.
- [x] `context_slice_*` metadata does not appear in provider wire payload.
- [x] Runtime/control nodes do not become provider messages.
- [x] Empty assistant summary/null text is not sent.
- [x] Assistant progress is not replayed unless explicitly projected as model-visible commentary.
- [x] Prior active-session tool call/result pairs are replayed as exact structured input items for follow-up turns, not only as summaries.
- [x] Tool schemas are selected by tool visibility policy, not dumped wholesale.
- [x] Codex WebSocket continuation sends delta input when valid.
- [x] Full replay fallback remains possible but uses clean response-item replay only.
- [x] Operations/Trace can still inspect why an item was omitted through loss/report refs.

## Open Questions Before Construction

- Should assistant commentary always be model-visible for the next turn, or only when provider item phase says commentary?
- Should agent home files be instruction context only, or should empty/default files be omitted entirely?
- What is the minimum default tool surface after the current core default (`exec + process + capability.search`) proves too broad or too narrow?
- Should compact summary be produced by provider response item compaction, session segment compaction, or a separate summarizer invocation?
- Should failed tool results always replay to the model, or only failures that are paired with a model-issued call id?

## Construction Order

1. Add provider payload audit command.
2. Add failing tests for current bad input:
   - runtime node in provider input;
   - empty assistant item;
   - duplicate progress;
   - broad default tools.
3. Fix Context Workspace slice policy.
4. Fix request-side runtime transcript projection.
5. Remove fallback direct session replay.
6. Narrow default tool surface.
7. Fix continuation fingerprint/delta path.
8. Run long-chain Codex comparison again.
