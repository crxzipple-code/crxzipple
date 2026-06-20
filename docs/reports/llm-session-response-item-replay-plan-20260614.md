# LLM / Session ResponseItem Replay Development Plan

Date: 2026-06-14

## 背景

Codex HTTP path 不依赖 `previous_response_id`。源码显示它在每次 Responses HTTP 请求中发送：

```text
instructions = stable base instructions
input        = ContextManager.for_prompt(...) -> Vec<ResponseItem>
tools        = model-visible tool specs
```

其中 `Vec<ResponseItem>` 是协议链，不是普通聊天文本。它包含 user/assistant message、reasoning、function_call、function_call_output、local shell call、web/image/custom tool item 等。工具 schema 在 `tools` 字段，历史 tool call/result 在 `input` 字段，并通过 `call_id` 关联。

CRXZipple 当前已经有 `LlmResponseItem`、`SessionItem`、`provider_item_type`、`call_id` 等字段，但最新会话证明 provider request 仍以 `context_tree` system message 为主，历史执行链只在当前 turn 内局部回放。结果是模型能读到很多上下文，却不能稳定继承“当前任务状态”和上一轮工程探索链。

本文件定义 Session / LLM module 如何把历史事实无损投影为 provider-neutral ResponseItem replay。

## 目标

1. 将 model-visible SessionItem 投影为 provider-neutral `LlmInputItem` / `ResponseInputItem`。
2. 默认 LLM request 的 `input` 主体改为结构化 item replay，而不是压扁后的 role/content transcript。
3. 保留 provider 原生 item 语义：reasoning、function_call、function_call_output、provider external item 不降级为普通 assistant 文本。
4. 工具调用和工具结果通过 `call_id` 保持协议配对。
5. 长输出按 model-visible replay policy 截断，但保留原始结果在 owner module / artifact。
6. 不考虑历史数据兼容；允许清库重建后使用新 schema。

## 非目标

- 不在 Session module 里拥有工具、LLM、Context Tree 的业务真相。
- 不把 Workbench timeline 当作模型 replay 来源。
- 不把所有 provider 都强行映射成 OpenAI Responses 原样字段；provider-neutral item 是主契约。
- 不恢复旧 transcript-only `messages` contract。

## 目标模型

## 施工进度

- [x] 新增 provider-neutral `LlmInputItem` / `LlmInputItemKind` 基础值对象。
- [x] `LlmInvocation`、`LlmAdapterRequest`、`InvokeLlmInput`、`StreamLlmInput` 已承载 `input_items`。
- [x] `llm_invocations.input_items` 已加入目标 schema migration `0079_llm_invocation_input_items`。
- [x] OpenAI Responses / OpenAI Codex Responses adapter 已在 `input_items` 非空时优先使用 projected input。
- [x] provider request preview fallback 已暴露 `input_item_count` / `input_item_kinds`。
- [x] `llm.invocation_started` event 已带 `input_item_count` / `input_item_kinds`。
- [x] Orchestration `LlmRequestEnvelope` 已生成 message-equivalent `input_items` 投影并传入 LLM invoker。
- [x] `PromptTranscript` 已从 `SessionItem` 直接生成 provider-neutral `input_items`，保留 `reasoning`、`function_call`、`function_call_output`、`provider_external_item` 语义。
- [x] `RunPromptInput` / `ProviderPromptRequestBuilder` 已优先使用 SessionItem 直出的 `input_items`，只把新增 context projection 等非 session 消息按 message 投影补入。
- [x] 默认真实 provider request 已使用 Context Tree compact projection，不再自动把完整 `<context_tree>` XML 当作 system prompt。
- [x] replay budget 已输出 source/replay 双口径 `tool_protocol_diagnostics`，能报告 orphan tool output、missing tool output、duplicate call id。
- [x] protocol-only replay 已输出 `tool_protocol_normalization` delta，能说明哪些源断点被规范化过滤，没有把 orphan/missing 协议项喂给 provider。
- [x] full-history replay 已启用保守 tool protocol normalization：只保留第一组有效 `tool_call -> tool_result` pair，过滤 orphan output、missing-output call 和重复 call/result。
- [x] LLM request metadata 已暴露 `direct_tool_protocol_health` 摘要，Operations/Workbench 可直接读取 replay 是否仍有协议断点以及过滤了多少源断点。
- [x] Operations LLM detail Runtime Hints 已展示 tool protocol replay/source/filtered 摘要。
- [x] Workbench linked `llm_invocation` detail payload 已暴露 `runtime_hints.tool_protocol` 摘要，可查看 replay 是否干净、源历史是否有断点、过滤总数。
- [x] Workbench linked entity 详情卡已结构化展示 Runtime Hints / Tool protocol replay 摘要，不必展开原始 JSON。
- [x] Trace linked entity 详情卡已结构化展示同一 Runtime Hints / Tool protocol replay 摘要。
- [x] Operations LLM detail Request Context 已区分 provider-neutral Replay Input Items / Kinds / Sources / Protocol Items 和 provider request preview。
- [x] Workbench / Trace linked `llm_invocation` detail 已展示 provider-neutral Replay Input count/kinds/sources/protocol counts。

当前第一版 `LlmInputItem` 采用瘦契约：

```python
@dataclass(frozen=True, slots=True)
class LlmInputItem:
    kind: LlmInputItemKind
    payload: dict[str, Any]
    source: str = "projection"
    metadata: dict[str, Any] = field(default_factory=dict)
```

这样做的原因是：provider-neutral 层先稳定承载 replay item，不把 role/call_id/tool_name 等字段过早固定成跨 provider 公共字段；OpenAI Responses adapter 在最终映射时负责把 `payload` 规范化为 `message` / `function_call` / `function_call_output`。

### Provider-Neutral Input Item

建议新增 value object：

```python
@dataclass(frozen=True, slots=True)
class LlmInputItem:
    kind: LlmInputItemKind
    role: str | None
    content: object
    call_id: str | None = None
    tool_name: str | None = None
    provider_item_id: str | None = None
    provider_item_type: str | None = None
    provider_payload: dict[str, object] = field(default_factory=dict)
    model_visible: bool = True
    user_visible: bool = False
    source_ref: dict[str, object] = field(default_factory=dict)
```

第一版 kind：

- `message`
- `reasoning`
- `function_call`
- `function_call_output`
- `provider_external_item`
- `compaction`
- `context_compaction`
- `other`

### SessionItem Projection

| SessionItem kind | LlmInputItem kind | Provider mapping |
| --- | --- | --- |
| `user_message` | `message(role=user)` | Responses `message` |
| `assistant_message` | `message(role=assistant)` | Responses `message` |
| `reasoning` | `reasoning` | Responses `reasoning` if supported |
| `tool_call` | `function_call` | Responses `function_call` |
| `tool_result` | `function_call_output` | Responses `function_call_output` |
| `provider_external_item` | `provider_external_item` | provider-specific |
| `compaction` | `compaction` | Responses `compaction` or summary message fallback |

## Replay Rules

### Visibility

- Only `model_visible=true` items are eligible for replay.
- `user_visible` / `chat_visible` only affect UI, not replay eligibility.
- Raw reasoning follows provider safety policy:
  - provider encrypted reasoning: keep as provider item when supported.
  - summary reasoning: replay as `reasoning.summary` when supported.
  - unsupported provider: downgrade to hidden assistant progress only if policy allows.

### Tool Pair Integrity

Before provider request:

1. Every replayed `function_call` must have matching `function_call_output`, unless it is the latest provider output waiting for execution.
2. Every `function_call_output` must have a preceding matching call in replay window.
3. Orphan outputs are dropped from replay and reported in request diagnostics.
4. Missing outputs can be synthesized as `aborted` only for interrupted turns, with explicit metadata.

### Truncation

- Tool result replay uses bounded text/content output.
- Original `ToolRun.result_envelope_payload` remains untouched in Tool module.
- If truncation occurs, replay item includes:
  - `truncated=true`
  - `raw_artifact_ref` or `read_handle` when available
  - visible first/last output slices when useful

### Compaction

When replay exceeds budget:

- Replace older item ranges with a `compaction` item.
- Compaction output should preserve:
  - active task state
  - known slots
  - confirmed evidence
  - failed paths
  - last actionable next step
- Keep recent tool call/output pairs intact.

## Module Changes

## 1. Session Module

### Add Replay Query

Add an application query surface:

```python
class SessionReplayQueryService:
    def replay_items_for_model(
        self,
        session_key: str,
        *,
        max_items: int | None,
        max_chars: int | None,
        since_sequence_no: int | None,
    ) -> SessionReplayWindow: ...
```

`SessionReplayWindow` contains:

- ordered `LlmInputItem`
- budget report
- orphan/missing pair diagnostics
- source SessionItem ids
- compaction refs

### Stop Flattening by Default

Existing `build_model_visible_session_item_prompt_window()` can remain as compatibility helper, but orchestration must stop using it as the default request input path.

New default:

```text
SessionItem[] -> LlmInputItem[] -> provider adapter
```

Old fallback:

```text
SessionItem[] -> LlmMessage[] -> provider adapter
```

Fallback should only be used for providers without structured item support.

## 2. LLM Module

### Request Contract

Extend `LlmAdapterRequest`:

```python
input_items: tuple[LlmInputItem, ...]
messages: tuple[LlmMessage, ...]  # legacy/fallback
input_mode: "response_item_replay" | "message_transcript"
```

Adapter behavior:

- `openai_responses` / `openai_codex_responses`: prefer `input_items`.
- chat-completions-like providers: convert `input_items` to messages with explicit tool protocol fallback.
- unsupported provider item kinds are dropped or downgraded with diagnostics, never silently flattened.

### Provider Preview

`provider_request_payload_preview` must show:

- `input_mode`
- `input_item_count`
- `input_item_types`
- `tool_pair_count`
- `orphan_tool_output_count`
- `compaction_item_count`
- `uses_message_transcript_fallback`

## 3. Orchestration Integration

Orchestration request builder obtains:

```text
stable instructions
+ active task state item
+ session replay window
+ current turn user input / tool output delta
+ tool schemas
```

It must not ask Context Workspace for full tree text by default.

## Test Plan

### Unit

- `SessionItem -> LlmInputItem` mapping for all item kinds.
- Tool call/output pair normalization.
- Missing output synthesizes `aborted` only for interrupted turn.
- Orphan output is excluded with diagnostics.
- Reasoning visibility policy.
- Tool result truncation keeps raw ref.

### Integration

- New turn after a tool-heavy run replays previous `exec -> output -> assistant progress` chain as structured input.
- Latest user follow-up such as “下周一 那个机场都行” inherits previous task slots from replay/active task state.
- OpenAI/Codex Responses adapter emits `function_call` and `function_call_output` in `input`, not role/tool messages.

### Regression Scenario

Use the East China Airlines task:

1. User asks for KMG -> Shanghai ticket.
2. Agent explores with `exec`.
3. User says “下周一 那个机场都行”.
4. Next request must include:
   - active task state with KMG / Shanghai / SHA/PVG / 2026-06-15.
   - previous `exec` call/output chain.
   - no full context tree as system text.
5. Model should continue task or report evidence, not ask for origin/destination again.

## Checklist

- [x] Define `LlmInputItem`.
- [x] Define dedicated `SessionReplayWindow` query DTO.
- [x] Add Session owner replay query surface via `SessionApplicationService.build_replay_window()`.
- [x] PromptInputCollector 已改用 Session replay window 读取 active-session model-visible items，并把窗口 sequence/protocol 摘要写入 transcript budget。
- [x] Implement first-pass SessionItem projection rules in `PromptTranscript`.
- [x] Implement first-pass tool pair diagnostics.
- [x] Implement protocol-only strict normalization observability / orphan output exclusion.
- [x] Implement strict normalization for full-history replay modes where policy allows.
- [x] Promote replay protocol health summary into request metadata.
- [x] Project replay protocol health into Operations LLM Runtime Hints.
- [x] Project replay protocol health into Workbench linked LLM invocation detail.
- [x] Render Workbench linked LLM invocation runtime hints in the inspector detail card.
- [x] Render Trace linked LLM invocation runtime hints in the detail card.
- [x] Implement interrupted-turn terminal output synthesis when owner state proves a call was interrupted: cancelled/timed-out ToolRun owner facts are recorded as model-visible `tool_result` SessionItems and replayed to the next LLM turn.
- [x] Implement replay truncation diagnostics beyond existing budget refs: budget now reports collapsed/shortened item counts, omitted chars, refs, and whitelisted `provider_replay_truncation` metadata.
- [x] Extend LLM adapter request with `input_items`.
- [x] Update OpenAI/Codex Responses adapter to consume `input_items`.
- [x] Add fallback conversion for non-Responses providers: OpenAI Chat Compatible / Anthropic Messages / Gemini Generate Content now derive provider messages from `input_items` before falling back to legacy messages.
- [x] Update provider request preview fields.
- [x] Switch orchestration default from message projection to SessionItem item replay when session item input is available.
- [x] Add focused unit tests for SessionItem input item projection and provider envelope merge.

## Acceptance Criteria

- Latest provider request preview shows `input_mode=response_item_replay`.
- Previous turn tool call/output items appear as structured input items.
- No context tree XML appears in default system/instructions payload.
- Tool schemas remain in `tools`, not in history text.
- Follow-up task state survives across turns without asking for already-known slots.
