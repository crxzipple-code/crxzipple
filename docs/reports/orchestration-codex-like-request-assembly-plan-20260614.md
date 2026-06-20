# Orchestration Codex-Like Request Assembly Development Plan

Date: 2026-06-14

## 背景

Orchestration 是 CRXZipple 的 runtime coordinator。它不拥有 LLM、Tool、Session、Context Tree 的真相，但负责把这些 owner facts 组织成一次可执行的 agent turn。

最新会话显示：

- run 完成，但没有继续查票。
- LLM 调了 3 次 `context_tree.*`，没有调 `exec/web`。
- provider request `input` 中结构化回放的是当前 turn 的 tree call/output，而不是上一轮查票工程链。
- context tree 作为 system message 反复进入模型，掩盖了 active task。

本文件定义 Orchestration 如何组装 Codex-like request，并把纠偏/终止判断限定在 provider continuation、pending tool/approval 和 loop budget 内。

## 目标

1. 每轮 request 使用稳定 instructions + ResponseItem replay + compact context projection。
2. Context Tree 不再默认作为 system prompt body。
3. Tool call/result 驱动 continuation，按 response item 生命周期推进。
4. 明确区分 provider request input、tool schema、context projection、runtime debug metadata。
5. 不用通用 slot/evidence validator 替 LLM 判断 terminal response 是否足够；业务强验收由 workflow / skill evaluator 承担。
6. 不考虑历史数据兼容；允许清库重建。

## 非目标

- 不让 orchestration 拥有树化 Prompt 拼装。
- 不让 orchestration 拥有 tool/llm/session 原始事实。
- 不把所有 provider 都强制走 Codex WebSocket。
- 不把 browser/CDP 作为完成任务的硬编码路径。

## Request Assembly Pipeline

目标流水线：

```text
RunPromptInput
  |
  v
PromptSurfaceBuilder
  - latest user input
  - agent profile / runtime policy
  - context projection refs
  - resolved tool surface refs
  |
  v
SessionReplayQueryService
  -> LlmInputItem[] replay window
  |
  v
ContextProjectionService
  -> active_task_state + context_hints
  |
  v
ToolSurfaceSnapshot
  -> provider-visible tool schemas
  |
  v
LlmRequestEnvelope
  instructions
  input_items
  tools
  reasoning/provider options
  metadata/diagnostics
```

## Input Ordering

Default ordering:

1. Stable developer/system instructions.
2. Context projection item:
   - active task state.
   - context hints.
3. Replay window from Session:
   - recent user/assistant/reasoning/tool protocol chain.
4. Current turn latest user input.
5. Current tool result delta, if continuing after tool execution.

Important:

- `tools` stays separate from `input_items`.
- `context_tree.*` tool calls enter replay only if model actually called them.
- Full tree XML is debug-only or explicit tree tool output.

## Continuation Strategy

### Provider Native

For provider/transport combinations that support native continuation:

```text
previous_response_id + new input delta + tools
```

Codex WebSocket belongs here.

### Structured Replay

For HTTP Responses and provider-neutral default:

```text
instructions + normalized LlmInputItem[] + tools
```

Codex HTTP belongs here.

### Message Transcript Fallback

Only for providers without structured item support:

```text
messages[] with tool protocol downgraded
```

Fallback must be visible in diagnostics.

## Evidence Ledger Split

Orchestration should maintain two ledgers:

### Context Observations

Tree reads/expands/estimates:

- `context_tree.render_current`
- `context_tree.expand`
- `context_tree.diff_since`
- `context_tree.read_snapshot`

These are useful for trace but not task evidence.

### Task Evidence

Evidence that proves or disproves task facts:

- official website response
- HTTP/API result
- command stdout/stderr relevant to task
- CDP/network capture
- file/resource extraction
- validation step

Only owner/tool facts enter debug metadata. The generic agent loop does not derive
cross-task evidence verdicts before asking the model to continue or stop.

## Corrective Continuation

Do not add a generic post-response validator before marking turn completed. Provider
termination signals, pending tool calls, pending approvals, and loop budget remain
the default continuation criteria. Business-specific correction belongs to workflow
or skill evaluator code.

### Slot Regression Check

Slot regression may be computed as an Operations / baseline diagnostic. It is not
a default orchestration gate because generic slot extraction cannot be exhaustive.

Example:

```text
known:
  origin=KMG
  destination=Shanghai
  date=2026-06-15
  airport=SHA/PVG both OK

assistant:
  请把出发城市和到达城市再发我一下
```

Action:

1. Do not mark as plain completed.
2. Add loop correction input item:
   ```text
   Correction: You asked for origin/destination, but active task state already contains origin=KMG and destination=Shanghai. Continue from known slots or ask only for genuinely missing data.
   ```
3. Invoke one corrective continuation if budget/step policy allows.
4. If correction fails, complete with diagnostic state `needs_user_clarification_unresolved`.

### Tool-Only Context Loop Check

If a turn repeatedly calls only `context_tree.render_current` / `expand` and no task tool:

- inject correction:
  ```text
  You have read context tree N times. Use active task state and proceed, or call a task tool. Do not re-render the full tree unless a specific node is needed.
  ```

### Terminal Reasoning/Commentary Check

Existing commentary/reasoning-only diagnostics remain, but should understand response item replay mode.

## State Written to Run Metadata

Each LLM execution item summary should include:

- `input_mode`
- `structured_replay_item_count`
- `context_projection_id`
- `active_task_state_fingerprint`
- `tool_pair_count`
- `task_evidence_count`
- `context_observation_count`
- `provider_native_continuation_used`
- `message_transcript_fallback_used`
- `corrective_continuation_count`

## Module Changes

## 1. Prompt Surface / Request Builder

Replace default path:

```text
context_render_snapshot.content -> LlmMessage(system)
```

with:

```text
stable_runtime_contract -> instructions
context_projection -> LlmInputItem(message/developer or context item)
session replay -> LlmInputItem[]
```

## 2. Engine Loop

Engine loop consumes:

- `LlmContinuationSignal`
- completed response items
- tool execution plan
- corrective validators

It should not derive execution only from legacy `LlmResult.tool_calls`.

## 3. Execution Chain

Execution chain should record:

- request assembly diagnostics
- response item ids
- tool result ids
- evidence classification
- correction attempts

## 4. Baseline Builder

Update baseline metrics:

- Do not count context tree success as task evidence.
- Add active task state presence.
- Add optional slot regression diagnostic.
- Add structured replay counts.

## Test Plan

### Unit

- Request assembly orders items correctly.
- Full tree XML omitted by default.
- Tool schemas stay separate from input.
- Evidence split classifies context tree as context observation.
- Slot regression validator catches repeated known-slot questions.

### Integration

- Tool call -> ToolRun -> tool result -> next LLM request includes function_call_output.
- Follow-up turn inherits previous task state and previous protocol chain.
- Provider-native continuation path only enabled for supported transport.
- HTTP structured replay path does not send `previous_response_id`.

### Regression

Run East China Airlines chain:

1. Previous task established KMG -> Shanghai.
2. User says airport/date follow-up.
3. Request assembly includes active task state.
4. If model asks for origin/destination, corrective continuation triggers.
5. Final answer either continues task or asks only genuinely missing data.

## Checklist

- [x] Add request `input_mode` decision: request metadata now records `input_mode`, input item counts, kind counts, source counts, structured replay count, and projected message count.
- [x] Wire Session replay query into Orchestration.
- [x] Wire Context projection into Orchestration.
- [x] Remove default context tree system body.
- [x] Cancel default evidence ledger split for the generic agent loop; owner modules keep facts, and LLM judges sufficiency from transcript.
- [x] Cancel default slot regression validator; business-specific acceptance belongs to workflow / skill evaluator, not orchestration.
- [x] Cancel context-tree-only loop correction as model-visible guidance; tree state remains agent-managed/debug unless explicitly requested through tools.
- [x] Update execution item summaries: LLM execution step summary now includes `llm_request_input` with input mode and replay/projection item counts.
- [x] Update baseline metrics: baseline now reports LLM request input mode counts, structured replay steps, message projection steps, missing request-input summaries, and replay/projection item totals.
- [x] Add unit coverage for request input mode and Operations display.

## Acceptance Criteria

- Latest request preview shows structured replay, not tree-as-system.
- `context_tree.*` tool results are context observations, not task evidence.
- Known task slots survive follow-up turns.
- Orchestration does not complete a turn with an obviously regressive clarification without one correction attempt.
- Operations can explain whether the turn used native continuation, structured replay, or fallback transcript.
