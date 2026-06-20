# Provider-Neutral LLM Response Stream Contract Plan 2026-06-11

本文记录 LLM module 的整改方向：把 CRXZipple 从 `LlmResult(text + tool_calls)` 的压扁输出，升级为 provider-neutral 的 response stream / response item contract。

关联文档：

- [../reference/llm-provider-capability-matrix.md](../reference/llm-provider-capability-matrix.md)
- [agent-runtime-contract-upgrade-progress-dashboard-20260611.md](agent-runtime-contract-upgrade-progress-dashboard-20260611.md)
- [assistant-progress-session-context-convergence-plan-20260611.md](assistant-progress-session-context-convergence-plan-20260611.md)
- [orchestration-llm-contract-driven-runtime-plan-20260611.md](orchestration-llm-contract-driven-runtime-plan-20260611.md)
- [session-module-response-item-migration-plan-20260611.md](session-module-response-item-migration-plan-20260611.md)
- [workbench-agent-timeline-read-model-plan-20260611.md](workbench-agent-timeline-read-model-plan-20260611.md)
- [context-workspace-llm-request-surface-plan-20260611.md](context-workspace-llm-request-surface-plan-20260611.md)
- [tool-surface-llm-request-contract-plan-20260611.md](tool-surface-llm-request-contract-plan-20260611.md)
- [llm-provider-adapter-response-item-implementation-plan-20260611.md](llm-provider-adapter-response-item-implementation-plan-20260611.md)
- [model-agent-policy-llm-request-options-plan-20260611.md](model-agent-policy-llm-request-options-plan-20260611.md)
- [operations-agent-runtime-projection-plan-20260611.md](operations-agent-runtime-projection-plan-20260611.md)
- [runtime-database-reset-playbook-20260611.md](runtime-database-reset-playbook-20260611.md)
- [agent-runtime-contract-upgrade-testing-strategy-20260611.md](agent-runtime-contract-upgrade-testing-strategy-20260611.md)
- [codex-like-agent-loop-governance-development-plan-20260611.md](codex-like-agent-loop-governance-development-plan-20260611.md)
- [../orchestration-design.md](../orchestration-design.md)
- [../session-semantics-design.md](../session-semantics-design.md)
- [../context-workspace-prompt-tree-design.md](../context-workspace-prompt-tree-design.md)

## 定位

这是统一 LLM module 设计，不是 Codex-like 专用设计。

Codex / OpenAI Responses 只是暴露问题的强样本：现代 provider 已经能返回 response item lifecycle、reasoning summary、message phase、tool argument delta、continuation signal 等结构化信息。CRXZipple 当前 LLM module 只向外释放 `text + tool_calls + usage`，导致后续 orchestration、session、Workbench、Context Workspace 都只能消费压扁后的能力。

目标不是照抄 Codex 的 hosted web search / image generation，也不是把所有 provider 都硬套 OpenAI `ResponseItem`。目标是建立 CRXZipple-native、provider-neutral 的消化层：

```text
provider-native response stream
  -> LLM adapter parses native events/items
  -> LlmResponseEvent / LlmResponseItem / LlmContinuationSignal
  -> derived LlmResult summary for read models
```

## Cutover Assumption

本轮整改以 agent 最佳效果为第一目标。开发、测试和本地运行环境允许完全重建数据库，因此旧表结构、旧 `result_payload`、旧 session message 形态和旧 Operations projection 都不能作为新 contract 的约束。

这意味着：

- 可以破坏式调整 LLM / Session / Orchestration / Operations 相关 schema。
- migration 只需要服务新结构落地和新库初始化，不需要为历史库做复杂升级路径。
- 不需要设计旧数据 backfill、dual-read、dual-write、legacy replay。
- 如果旧 DTO/read model 不能表达新能力，应改 DTO/read model，而不是把新能力压回旧字段。
- 验证重点从“旧数据还能不能显示”转为“新 agent loop 是否完整消化 provider 能力，并把必要事实交给后续轮次”。

## 当前问题

### 1. Adapter port 过窄

当前 adapter 只返回：

```text
LlmAdapterResponse
  result: LlmResult
  provider_request_id
```

`LlmResult` 只有：

```text
text
tool_calls
structured_output
usage
finish_reason
metadata
```

这无法表达：

- response item started/done。
- reasoning summary delta / completed item。
- raw/encrypted reasoning。
- assistant message phase：`commentary` / `final_answer` / `unknown`。
- provider `end_turn=false`。
- tool argument delta。
- provider item id/type。
- provider-hosted external items。

### 2. Streaming event 过窄

当前 `LlmStreamEvent` 是开放 string event，但实际使用集中在：

```text
invocation_started
text_delta
completed
failed
```

orchestration invoker 也只消费这些事件，导致 provider stream 中的 item lifecycle 无法被观察或持久化。

### 3. Persistence 只保存压扁结果

`llm_invocations` 当前保存：

```text
messages
tool_schemas
response_format
request_overrides
request_metadata
result_payload
error_payload
provider_request_id
```

没有 response item / response event 的 durable fact。Operations 只能观察最终 `result_payload`，不能解释“模型这一轮到底产出了哪些 item”。

### 4. Orchestration 只能用 tool_calls 推进

当前 engine 分叉：

```text
if invocation.result.tool_calls:
    execute tools
else:
    message only / finish
```

这无法消费 provider continuation signal，例如 `end_turn=false`，也无法区分 commentary、final answer、reasoning-only response、tool-call error response 等语义。

## 目标

### 必须达成

1. LLM module 能无损保存 provider response item/event 的关键结构。
2. LLM module 暴露 provider-neutral 的 `LlmResponseItem` 和 `LlmResponseEvent`。
3. `LlmResult` 保留为从 items 派生的摘要，服务 read model 和人工排查，不作为 runtime 主契约。
4. LLM module 提供 `LlmContinuationSignal`，让 orchestration 不再只依赖 `tool_calls` 判断循环终止。
5. OpenAI Responses / Codex Responses adapter 先实现 item lifecycle 映射。
6. OpenAI Chat Compatible / Anthropic / Gemini adapter 可以逐步映射到同一 contract，不要求一次性达到 OpenAI Responses 粒度。
7. Tool Source 仍归 Tool module 管理。provider-hosted items 不自动注册为 CRXZipple ToolRun。
8. 接受数据库完全重建和历史数据不兼容；新结构生效后不为旧 `llm_invocations.result_payload` 历史补兼容 shim。

### 非目标

- 不把 Codex hosted web search / image generation 作为 CRXZipple 标准能力路径。
- 不让 LLM module 执行本地工具。
- 不让 Session module 持有 LLM provider 真相。
- 不让 Context Workspace 直接解析 provider-native payload。
- 不要求所有 provider 都具备 reasoning summary / message phase / end_turn。
- 不保留旧 `LlmResult` 主路径。

## 新契约草案

### LlmResponseItemKind

```text
assistant_message
reasoning
tool_call
tool_result
structured_output
provider_external_item
compaction
unknown
```

说明：

- `assistant_message`：普通 assistant 输出，可带 phase。
- `reasoning`：reasoning summary / raw / encrypted reasoning 的归一化承载。
- `tool_call`：模型请求 CRXZipple Tool module 执行的本地/runtime tool。
- `tool_result`：provider-native history 或 tool result replay 中的结果项。
- `provider_external_item`：provider-hosted capability 结果，例如 OpenAI `web_search_call`、`image_generation_call`。它可进入 LLM history 和 UI，但不自动成为 ToolRun。
- `compaction`：provider 或 runtime 产生的压缩上下文项。
- `unknown`：保留 raw payload，但不参与特殊 loop 语义。

### LlmMessagePhase

```text
commentary
final_answer
unknown
```

phase 是 provider 能力，不是 prompt 规则。adapter 能识别就填，不能识别就用 `unknown`。

### LlmResponseItem

建议字段：

```text
id
invocation_id
sequence_no
kind
role
phase
content_payload
provider_payload
provider_item_id
provider_item_type
call_id
tool_name
model_visible
user_visible
created_at
completed_at
```

字段语义：

- `content_payload`：CRXZipple-native、可供 orchestration/session/workbench 消费的结构。
- `provider_payload`：provider 原始 item，供追溯和 adapter 修复。
- `provider_item_type`：如 `message`、`reasoning`、`function_call`、`web_search_call`。
- `model_visible`：可作为下一轮模型历史输入的事实。
- `user_visible`：可投影到 Workbench/Trace 的事实。
- `tool_name/call_id`：仅对 tool 相关 item 有意义。

### LlmResponseEventType

```text
invocation_started
item_started
text_delta
reasoning_summary_delta
reasoning_raw_delta
tool_argument_delta
item_completed
completed
failed
```

### LlmResponseEvent

建议字段：

```text
id
invocation_id
sequence_no
type
item_id
delta_payload
provider_payload
created_at
```

事件用于 streaming UI、Operations trace 和调试。完整历史事实以 completed `LlmResponseItem` 为准。

### LlmContinuationSignal

建议字段：

```text
end_turn: bool | None
needs_follow_up: bool
reason: none | tool_call | provider_end_turn_false | tool_error_response | pending_external
provider_payload
```

`needs_follow_up` 的计算属于 LLM module 的“provider response 解读”部分，但最终是否继续 turn 仍由 orchestration 综合判断：

```text
llm continuation
+ pending input
+ approval/waiting/hook
+ tool execution state
=> orchestration transition
```

## OpenAI Responses / Codex Responses 映射

先实现此 family，因为它能覆盖最完整能力面。

| Provider event/item | LLM contract |
| --- | --- |
| `response.created` | `LlmResponseEvent(invocation_started)` 或 metadata |
| `response.output_item.added` | `item_started` |
| `response.output_text.delta` | `text_delta` |
| `response.reasoning_summary_text.delta` | `reasoning_summary_delta` |
| `response.reasoning_summary_part.added` | `reasoning_summary_delta` section marker |
| `response.reasoning_text.delta` | `reasoning_raw_delta` |
| function/tool argument delta | `tool_argument_delta` |
| `response.output_item.done` message | `LlmResponseItem(assistant_message)` |
| `response.output_item.done` reasoning | `LlmResponseItem(reasoning)` |
| `response.output_item.done` function_call/custom_tool_call | `LlmResponseItem(tool_call)` |
| `response.output_item.done` function_call_output | `LlmResponseItem(tool_result)` |
| `response.output_item.done` web_search/image_generation | `LlmResponseItem(provider_external_item)` |
| `response.completed` | `completed` + `LlmContinuationSignal(end_turn=...)` |

`LlmResult` 派生规则：

```text
text = 合并 assistant_message 中可见 text
tool_calls = 从 kind=tool_call 且属于 CRXZipple Tool module 的 item 派生
usage = completed usage
finish_reason = provider status / end_turn 派生
metadata = response id, model, transport, item counts
```

## 其他 Provider 映射口径

### OpenAI Chat Compatible

支持能力通常较窄：

```text
message.content -> assistant_message
message.tool_calls[] -> tool_call
delta.content -> text_delta
delta.tool_calls[] -> tool_argument_delta 或内部合并后 item_completed
finish_reason -> completed metadata
```

若 provider 没有 reasoning summary / phase / end_turn，使用：

```text
phase = unknown
end_turn = None
needs_follow_up = tool_calls exists
```

### Anthropic Messages

待官方文档和实测补齐。预期映射：

```text
text block -> assistant_message / text_delta
tool_use block -> tool_call
tool_result block -> tool_result
thinking block -> reasoning
stop_reason -> completed metadata / continuation signal
```

不要把 Anthropic content block 直接伪装成 OpenAI ResponseItem。

### Gemini GenerateContent

待官方文档和实测补齐。预期映射：

```text
text part -> assistant_message
functionCall part -> tool_call
functionResponse part -> tool_result
thought/reasoning part -> reasoning if available
finishReason -> completed metadata
```

## 模块边界

### LLM module owns

- provider-native request/response 编解码。
- raw provider payload retention。
- normalized response item/event。
- invocation-level continuation signal。
- derived `LlmResult`。
- provider/model capability metadata。

### Orchestration owns

- agent runtime loop。
- 综合 LLM continuation、tool execution、approval、pending input、dispatch state。
- 调用 Tool module。
- 决定写入 Session 的内容和 source metadata。
- 发布 execution chain events。

### Tool module owns

- Tool Source / Tool Function Catalog / Tool Runtime。
- ToolRun 生命周期。
- tool result payload normalization。
- runtime/credential/readiness。

### Session module owns

- 会话事实。
- 可重放 history。
- user-visible / model-visible / chat-visible 的持久化标记。

Session 不需要保存 provider-native truth 的所有细节；但 orchestration 从 LLM item contract 写入 session 时，必须能保留足够语义用于下一轮 prompt replay。

### Context Workspace owns

- agent-facing context tree。
- render snapshot。
- provider tool schema mirror。
- 对 session/orchestration facts 的上下文选择和预算控制。

Context Workspace 不直接解析 provider-native payload。

### Operations owns

- LLM invocation / response item / response event 的观察投影。
- Workbench/Trace 可视化。
- 调试指标，例如 reasoning summary present、message phase、end_turn、tool argument delta count。

## 数据模型重建

本节不是“在旧生产库上平滑迁移”的计划，而是新 LLM contract 的目标 schema。当前项目允许重建数据库，所以可以直接让 schema 对齐最佳 runtime 形态。

### Phase 1: Domain value objects

- 新增 `LlmResponseItemKind`。
- 新增 `LlmMessagePhase`。
- 新增 `LlmResponseItem`。
- 新增 `LlmResponseEvent`。
- 新增 `LlmContinuationSignal`。
- `LlmInvocation` 增加：

```text
response_items: tuple[LlmResponseItem, ...]
continuation: LlmContinuationSignal | None
```

response events 可先不挂 entity 全量加载，避免大对象膨胀；通过 query service 分页读取。

施工状态 2026-06-11：

- 已落地 `LlmResponseItemKind`、`LlmMessagePhase`、`LlmResponseEventType`、`LlmContinuationReason`。
- 已落地 `LlmResponseItem`、`LlmResponseEvent`、`LlmContinuationSignal` payload roundtrip。
- 已让 `LlmInvocation` 持有 completed `response_items` 和 invocation-level `continuation`。

### Phase 2: Persistence

新增表：

```text
llm_invocation_response_items
  id
  invocation_id
  sequence_no
  kind
  role
  phase
  content_payload
  provider_payload
  provider_item_id
  provider_item_type
  call_id
  tool_name
  model_visible
  user_visible
  created_at
  completed_at

llm_invocation_response_events
  id
  invocation_id
  sequence_no
  type
  item_id
  delta_payload
  provider_payload
  created_at
```

`llm_invocations.result_payload` 若继续存在，只能作为 summary cache；也可以在施工时改名或拆分，只要 runtime 主路径不依赖压扁结果。

施工状态 2026-06-11：

- 已新增 Alembic `0072_llm_response_items`。
- 已新增 `llm_invocation_response_items`、`llm_invocation_response_events`。
- 已新增 `llm_invocations.continuation_payload`。
- 已实现 SQLAlchemy / in-memory repository 的 response item/event/continuation roundtrip。

### Phase 3: Application service

- `stream_invoke()` 持久化 normalized events/items。
- `completed` 时根据 response items 派生 `LlmResult`。
- 增加 query service：

```text
list_response_items(invocation_id)
list_response_events(invocation_id, limit, after_sequence)
get_continuation(invocation_id)
```

施工状态 2026-06-11：

- 已扩展 `LlmAdapterRequest.invocation_id`，让 adapter 可生成 invocation-scoped response items。
- 已扩展 `LlmAdapterResponse.response_items` / `continuation`。
- 已让同步/异步 `invoke()` 持久化 adapter 返回的 response items 和 continuation。
- 已让非流式 `invoke()` / `invoke_async()` / `test_profile()` 在 adapter 返回 response items 时，用 response items 重建 `LlmResult` summary；adapter 原始 `result.text/tool_calls` 不再覆盖 item-derived summary。
- 已增加 `list_response_events(invocation_id, limit, after_sequence)` query method。
- 已让 `stream_invoke()` / `stream_invoke_async()` 将 normalized stream events 持久化为 durable `LlmResponseEvent`。
- Streaming `completed` event 若带 `response_items`，LLM service 已持久化 response item snapshot、continuation，并用 response items 重建 `LlmResult` summary；无 `response_items` 的 completed event 仍作为 legacy result fallback。

### Phase 4: Adapter migration

优先顺序：

1. `openai_codex_responses.py`
2. `openai_responses.py`
3. `openai_chat_compatible.py`
4. `anthropic_messages.py`
5. `gemini_generate_content.py`

每个 adapter 必须能在“不支持 item stream”的 provider 上退化为最小 item：

```text
assistant_message
tool_call
completed
```

施工状态 2026-06-11：

- 已让 OpenAI Responses / Codex Responses `invoke()` 从 completed response output 映射 `response_items` 和 `continuation`。
- 已覆盖 `message`、`reasoning`、`function_call`、provider hosted item 和 `end_turn=false`。
- 已保持 provider hosted item 为 `provider_external_item`，不创建 CRXZipple ToolRun。
- streaming 对外事件序列暂不破坏；application service 已开始把 stream event 投影为 durable `LlmResponseEvent`。
- 已完成 provider native `response.output_item.added/done`、reasoning summary/raw delta、tool argument delta 到 `LlmResponseEvent` 的基础映射和持久化。
- LLM Operations read model / detail drawer 已能展示 response items、response events、continuation reason 和 end_turn。
- Workbench timeline 与 Trace inspector 已完成 response item/source refs 的基础展示和 linked entity drilldown；response event 长期保留窗口仍待单独设计。

### Phase 5: Orchestration integration

- `EngineLlmInvoker` 返回包含 response item summary 的 invocation。
- engine 从 response items 派生 tool call execution plan。
- engine 使用 `continuation` 替换单纯 `result.tool_calls` 判断：

```text
if local tool_call items:
    execute tools
elif continuation.needs_follow_up:
    continue / wait according to reason
else:
    message-only completion path
```

施工状态 2026-06-11：

- 已让 engine 优先从 `LlmResponseItem(kind=tool_call)` 派生本地 tool call execution。
- Orchestration 已不再用旧 `LlmResult.tool_calls` 作为 ToolRun 创建 fallback；inline tool loop 由 `LlmResponseItem(kind=tool_call)` 驱动。
- 已让 `continuation.needs_follow_up` 驱动无 tool call 的下一轮 LLM invocation。
- 已在 execution payload / result payload 中记录 `continuation_reason` 和 `continuation_end_turn`。
- 独立 `ContinuationDecision` value object、execution item response item refs 和 SessionItem 投影迁移已完成；剩余为真实长链 baseline 验证。

### Phase 6: Session integration

- 对 `assistant_message(phase=commentary)`、`assistant_message(phase=final_answer)` 投影为可区分 `SessionItem`。
- 对 `reasoning` 按 Codex parity 默认投影为 `SessionItem(kind=reasoning)`；非 Responses/Codex provider 可按 policy 仅保留在 LLM/Operations trace。
- 对 `tool_call` / `tool_result` 保留 provider item id、call id、tool name。
- 对 `provider_external_item` 按 Codex parity 默认投影到 Session/Trace/Operations；非 Responses/Codex provider 可按 policy 降级；绝不创建 ToolRun。

### Phase 7: Operations / Workbench

- LLM invocation detail 展示 response items。
- Workbench LLM step 展示：
  - reasoning summary present。
  - assistant commentary。
  - final answer phase。
  - end_turn。
  - local tool calls。
  - provider external items。
- Trace 支持按 invocation_id 查看 raw provider event。

## Cutover Policy

- 接受数据库完全重建和历史数据不兼容。
- 不做旧 invocation response item 回填。
- 不做双路：新 runtime 主路径必须读取 response items/events/continuation。
- `LlmResult` 可保留为派生 summary/read model，但不再作为 orchestration loop 的主判断依据。
- HTTP/DTO 的 `result` 字段只能作为摘要展示；runtime 读取面必须以 item/event/continuation 为准。
- 既有 `text_delta/completed` stream 事件若保留，只能由 `LlmResponseEvent` 投影产生，不能继续作为 adapter/application 内部主事件。
- migration/DDL 只负责建立新库结构和让新数据写入；旧数据不要求在 Operations/Workbench 继续可见。
- 删除或重命名旧字段、旧表、旧 projection 是允许的，只要模块边界和新 contract 更清晰。

## Verification Checklist

### Unit

- [x] `LlmResponseItem.to_payload/from_payload` roundtrip。
- [x] `LlmResponseEvent.to_payload/from_payload` roundtrip。
- [x] `LlmContinuationSignal` reason/end_turn roundtrip。
- [x] OpenAI Codex Responses SSE: message item 映射。
- [x] OpenAI Codex Responses SSE: reasoning summary delta/item 映射。
- [x] OpenAI Codex Responses SSE: function_call 映射。
- [x] OpenAI Codex Responses SSE: `end_turn=false` 映射。
- [x] `LlmResult` 从 response items 派生 text/tool_calls/usage。
- [x] persistence repository 保存/读取 response items。
- [x] query service 分页读取 response events。

### Integration

- [x] streaming invoke 能由 `LlmResponseEvent` 投影输出摘要 `text_delta/completed`。
- [x] streaming invoke 同时输出新 `item_started/item_completed/reasoning_summary_delta`。
- [x] orchestration 仍可执行普通 tool call。
- [x] orchestration 能从 `LlmResponseItem(kind=tool_call)` 驱动工具执行。
- [x] orchestration 对 `end_turn=false` 不误判完成。
- [x] Workbench 能展示 response item 列表。
- [x] Operations LLM read model 能显示 item/event counts。

### Regression

- [x] `PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py`
- [x] `PYTHONPATH=src pytest -q tests/unit/test_llm.py`
- [x] `PYTHONPATH=src pytest -q tests/unit/test_orchestration_context.py`
- [x] `PYTHONPATH=src pytest -q tests/unit/test_orchestration_execution_chain.py`
- [x] `PYTHONPATH=src pytest -q tests/unit/test_operations_llm_read_model.py`
- [x] `PYTHONPATH=src pytest -q tests/unit/test_orchestration_tools.py::OrchestrationToolsTestCase::test_process_next_orchestration_assignment_completes_inline_tool_loop tests/unit/test_orchestration_tools.py::OrchestrationToolsTestCase::test_response_items_tool_calls_drive_inline_tool_loop tests/unit/test_orchestration_tools.py::OrchestrationToolsTestCase::test_provider_continuation_without_tool_calls_keeps_loop_open`
- [x] `cd frontend && npm run typecheck`

## Codex Parity Baseline

第一版策略先对齐 Codex 的可见性和 replay 口径：

- Codex 展示给用户的 response item，CRXZipple 也投影给用户。
- Codex 只作为 history/API item 隐形处理的内容，CRXZipple 也不强行变成聊天气泡。
- Codex replay 给模型的 provider item，CRXZipple 在对应 provider family 上也进入 model-visible replay。
- Codex 作为 stream/debug 事件处理的 delta，CRXZipple 默认进入 response events / Trace，不进入主 timeline。

具体默认值：

- `assistant_message`：写入 SessionItem；commentary 作为 agent progress，final_answer 作为最终答复。
- `reasoning`：完整保存为 LLM response item；summary 用户可见并可折叠展示；Responses/Codex family 默认 model-visible replay；raw reasoning 默认不展示给用户。
- `provider_external_item`：保存为 LLM response item；按 Codex 口径进入 history/model replay；可投影到 Session/Trace/Operations；绝不创建 ToolRun。
- `tool_argument_delta`：保存在 response events / Trace；Workbench 主 timeline 默认只展示 completed tool_call arguments。
- `MessagePhase.unknown`：按 Codex fallback，可作为 final answer 候选；Orchestration 仍必须结合 continuation/pending work，不能退回 `tool_calls empty`。
- response events：默认保留完整短期调试流；completed `LlmResponseItem` 是长期 durable fact。当前 owner module 已显式暴露 `LlmResponseEventRetentionPolicy(full_event_window_seconds=86400, detail_event_limit=100, durable_fact=completed_response_items, overflow_action=prefer_response_items_and_request_preview)`，Operations LLM detail 会展示该策略。

仍待施工细化：

- `provider_external_item` 的 artifact/link 规范。
- response events 的长期压缩/采样后台任务。

## 定期纠偏原则

本升级必须持续校准，而不是一次设计后盲目施工。每个模块 Phase 完成后都要回看：

- 是否仍对齐 Codex parity baseline。
- 是否仍保持 provider-neutral contract，而不是硬编码某一家 hosted capability。
- 是否仍保持 owner module 真相边界。
- 是否又退回旧 `LlmResult(text + tool_calls)` 主路径。
- 是否能通过 source refs 解释 request、response、loop decision 和 Workbench timeline。

一旦发现文档、代码或真实运行行为冲突，先更新设计文档和进度看板，再继续施工。

如果施工需要偏离当前设计，必须提出变更请求并获得 accepted 决策后再实现。变更请求必须说明触发原因、当前设计、建议变更、影响模块、contract impact、风险、决策和需更新文档。不得通过隐藏 fallback、兼容 shim 或局部特殊分支绕过设计变更流程。

## 最终判定

LLM module 的整改方向不是“Codex-like”。它是 provider-neutral 的 response stream contract 升级。

Codex API 证明了上游 LLM 能力已经超过 `text + tool_calls`。CRXZipple 要吸收的是现代 LLM 的结构化 response 能力，而不是某一家 provider 的 hosted tool 生态。
