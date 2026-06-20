# Session Runtime Projection and Provider Request Renderer Plan

Date: 2026-06-16

## 背景

本轮继续对照 `/Users/crxzy/Documents/codex` 源码和 CRXZipple 当前代码后，确认问题不只是某个字段丢失，而是运行时数据分层不够硬：

- Codex provider 原始响应是 `ResponseItem`，但它不会直接把 `ResponseItem::Message` 当成 UI / session timeline。
- Codex 会先把 provider `ResponseItem` 投影成 runtime `TurnItem`，例如 `AgentMessage`、`Reasoning`、`WebSearch`、`ImageGeneration`。
- Codex request 侧同样以 `Vec<ResponseItem>` 作为 provider input；工具结果通过 `function_call_output` / `custom_tool_call_output` 等 provider-native item 回放给模型。
- CRXZipple 当前已有 `LlmResponseItem`、`LlmInputItem`、provider renderer、`runtime_transcript` 等中间施工，但边界仍容易混乱：`LlmResponseItem` 被机械写入 `SessionItem`，`SessionItem` 又被直接渲染成 provider input。

用户最新决策：

- 不兼容旧结构，不双轨并行；数据库可清空重建。
- 运行时维护 Context Tree；渲染器按 provider / transport / model 把 runtime canonical context 渲染成 provider wire payload。
- 不把无法形成准确结论的诊断、证据裁判、路径偏置、任务特化判断发送给 LLM。
- Codex 适配以抓包 trace 和 Codex 源码事实为准。
- 不为某个任务特化内核；任务策略进入 skill / workflow / evaluator。

因此，本文件定义一套双向、对称、通用的开发方案：

```text
Response side:
Provider raw response
  -> LLM adapter parses LlmResponseItem
  -> Runtime Response Projector emits SessionRuntimeItem
  -> Session stores runtime transcript truth

Request side:
Context Tree + Session runtime transcript + Tool result facts
  -> Runtime Request Surface
  -> Provider Request Renderer
  -> Provider wire payload
```

## 源码事实

### Codex response side

Codex provider 原始响应类型定义在 `/Users/crxzy/Documents/codex/codex-rs/protocol/src/models.rs`：

- `ResponseItem::Message { role, content, phase }`
- `ResponseItem::Reasoning { summary, content, encrypted_content }`
- `ResponseItem::FunctionCall`
- `ResponseItem::FunctionCallOutput`
- `ResponseItem::WebSearchCall`
- `ResponseItem::ImageGenerationCall`

`MessagePhase` 明确区分：

- `commentary`：回合中阶段性 assistant text。
- `final_answer`：当前回合终态回答。

Codex runtime item 定义在 `/Users/crxzy/Documents/codex/codex-rs/protocol/src/items.rs`：

- `TurnItem::UserMessage`
- `TurnItem::AgentMessage`
- `TurnItem::Plan`
- `TurnItem::Reasoning`
- `TurnItem::WebSearch`
- `TurnItem::ImageGeneration`
- `TurnItem::McpToolCall`
- `TurnItem::ContextCompaction`

`AgentMessageItem` 字段包括：

- `id`
- `content`
- `phase`
- `memory_citation`

转换发生在 `/Users/crxzy/Documents/codex/codex-rs/core/src/event_mapping.rs`：

```text
ResponseItem::Message role=assistant -> TurnItem::AgentMessage
ResponseItem::Reasoning              -> TurnItem::Reasoning
ResponseItem::WebSearchCall          -> TurnItem::WebSearch
ResponseItem::ImageGenerationCall    -> TurnItem::ImageGeneration
ResponseItem::Message role=system    -> None
```

完成前还会进入 `/Users/crxzy/Documents/codex/codex-rs/core/src/stream_events_utils.rs` 的 `finalize_turn_item`：

- 组合 assistant text。
- 去除 hidden assistant markup。
- 解析 memory citation。
- 持久化 image generation 结果。
- 按 `phase=commentary` 区分是否触发 final-answer / mailbox deferral 语义。

结论：Codex 的 `agent_message` 是 runtime projection 结果，不是 provider 原始 item。

### Codex request side

Codex HTTP request 类型定义在 `/Users/crxzy/Documents/codex/codex-rs/codex-api/src/common.rs`：

```text
ResponsesApiRequest {
  model,
  instructions,
  input: Vec<ResponseItem>,
  tools,
  tool_choice,
  parallel_tool_calls,
  reasoning,
  store,
  stream,
  include,
  ...
}
```

WebSocket `response.create` 也包含：

```text
previous_response_id: Option<String>
input: Vec<ResponseItem>
tools
...
```

Codex provider input item 定义在 `/Users/crxzy/Documents/codex/codex-rs/protocol/src/models.rs`：

- `ResponseInputItem::Message`
- `ResponseInputItem::FunctionCallOutput`
- `ResponseInputItem::McpToolCallOutput`
- `ResponseInputItem::CustomToolCallOutput`
- `ResponseInputItem::ToolSearchOutput`

并通过 `impl From<ResponseInputItem> for ResponseItem` 进入 provider `input`。

工具结果不是随便拼成一段 assistant/user 文本，而是按 provider-native item 回放：

```text
function_call_output {
  call_id,
  output
}
```

`FunctionCallOutputPayload` 可以序列化为字符串或结构化 content items。

结论：Codex request side 也不是“session message 拼 prompt”，而是 runtime transcript 渲染为 provider-native `ResponseItem[]`。

### CRXZipple 当前状态

LLM response item 已存在于 `src/crxzipple/modules/llm/domain/value_objects.py`：

- `LlmResponseItemKind.ASSISTANT_MESSAGE`
- `REASONING`
- `TOOL_CALL`
- `TOOL_RESULT`
- `PROVIDER_EXTERNAL_ITEM`
- `COMPACTION`
- `UNKNOWN`

`LlmInputItem` 也已存在：

- `kind`
- `payload`
- `source`
- `metadata`

Session item 当前定义在 `src/crxzipple/modules/session/domain/value_objects.py`：

- `SessionItemKind.USER_MESSAGE`
- `ASSISTANT_MESSAGE`
- `REASONING`
- `TOOL_CALL`
- `TOOL_RESULT`
- `PROVIDER_EXTERNAL_ITEM`
- `COMPACTION`
- `SYSTEM_NOTE`
- `UNKNOWN`

当前主要问题：

1. `src/crxzipple/modules/llm/infrastructure/adapters/common.py` 的 `build_openai_response_items` 把所有 OpenAI/Codex `message` 默认标为 `final_answer`，未保留 raw `phase=commentary`。
2. `src/crxzipple/modules/orchestration/application/engine_session_recorder.py` 的 `append_llm_response_items` 机械地把 `LlmResponseItem` 映射为 `SessionItem`，缺少 Codex 那种 runtime projection / finalize 层。
3. `src/crxzipple/modules/orchestration/application/runtime_transcript.py` 已经承担 request side 渲染责任，但放在 orchestration 下，且含有 protocol replay、预算、诊断、过滤等混合职责，后续应迁移/收口为 request surface + provider renderer 的边界。
4. `src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_responses_renderer.py` 已经有 provider renderer 雏形，但它接收的是 `LlmAdapterRequest.input_items`，上游 input item 是否正确仍取决于 orchestration/session 投影。

## 一句话目标

**LLM module 无损接住 provider request/response；Session 保存 runtime transcript；Response Projector 负责 response item 到 runtime item；Request Renderer 负责 runtime item 到 provider wire item。**

## 不变原则

### 不兼容旧结构

- 不保留 legacy prompt transcript builder。
- 不保留 `LlmResponseItem -> SessionItem` 机械直写作为 fallback。
- 不保留 provider prompt body 与 context tree XML 双轨。
- 数据库迁移可以 breaking；开发前清库重建。

### 不发送不确定内容给 LLM

默认 model-visible request 不包含：

- evidence verdict。
- browser evidence path。
- runtime loop correction。
- heuristic next-step hint。
- 任务特化判定。
- 无法证明完整性的诊断总结。

这些只进入：

- Operations。
- Trace。
- Workbench debug。
- 测试 baseline。
- skill / workflow / evaluator。

### 不做任务特化

内核只处理：

- transcript item。
- context tree snapshot refs。
- tool call / result protocol。
- provider external item。
- continuation。
- visibility。
- rendering loss report。

不处理：

- 航班查询专用策略。
- 网站/WAF 专用判断。
- 某 provider 页面探索路线。
- 任务证据充分性。

## 目标架构

```text
modules/llm
  domain:
    LlmResponseItem
    LlmInputItem
    ProviderProtocolItem
    ProviderRenderReport

  infrastructure/adapters:
    provider-specific request renderer
    provider-specific response parser

modules/session
  domain:
    SessionRuntimeItem
    SessionItemKind
    visibility / replay policy / refs

  application:
    SessionRuntimeTranscriptService
    append runtime items
    query runtime items

modules/orchestration
  application:
    owns run loop
    calls LLM
    calls ResponseProjector
    creates ToolRun from runtime tool_call
    calls RequestSurfaceBuilder
    never renders provider payload

modules/context_workspace
  application:
    owns Context Tree
    owns render snapshot / tree state
    exposes tree read/replay tools
    does not produce provider prompt body

modules/tool
  application:
    owns ToolRun truth
    returns result envelope
    exposes model-visible result projection

modules/operations / frontend workbench
  read models:
    timeline projection
    raw provider trace
    renderer report
    user-visible guidance
```

## Data Model

## 1. LLM raw / canonical item

`LlmResponseItem` 是 provider-neutral raw-normalized response fact。它的职责是保真，不是 runtime transcript。

目标字段：

```text
LlmResponseItem
  id
  invocation_id
  sequence_no
  kind
  role?
  phase?
  content_payload
  provider_payload
  provider_item_id?
  provider_item_type?
  call_id?
  tool_name?
  model_visible_default
  user_visible_default
  created_at
  completed_at?
```

必须调整：

- OpenAI/Codex `message.phase` 必须从 raw item 读取：
  - `commentary` -> `LlmMessagePhase.COMMENTARY`
  - `final_answer` -> `LlmMessagePhase.FINAL_ANSWER`
  - absent -> `UNKNOWN`
- `reasoning` 默认不应直接等于 chat-visible；是否展示由 runtime projection / UI policy 决定。
- provider external item 保留 raw payload，不默认转成用户聊天消息。

## 2. Session runtime item

Session 是 runtime transcript truth，不是 provider response mirror。

目标 `SessionItemKind` 调整为：

```text
user_message
agent_message
reasoning
plan
tool_call
tool_result
provider_external_activity
context_compaction
runtime_notice
runtime_error
```

调整说明：

- `assistant_message` 改名为 `agent_message`，对齐 runtime 语义。
- `provider_external_item` 改为 `provider_external_activity`，避免被误解为 provider raw archive。
- `system_note` 拆成 `runtime_notice` / `runtime_error`，避免泛化成会被模型消费的提示。
- `unknown` 不进入 model-visible transcript；只可 trace-visible。

目标字段：

```text
SessionRuntimeItem
  id
  session_key
  session_id
  turn_id?
  sequence_no
  kind
  role?
  phase?
  content:
    text?
    blocks?
    summary?
    raw_content?
    model_visible_payload?
    user_visible_payload?
  refs:
    llm_invocation_id?
    llm_response_item_id?
    provider_item_id?
    provider_item_type?
    tool_run_id?
    tool_result_id?
    context_snapshot_id?
  protocol:
    call_id?
    tool_name?
    provider_replay_required
    provider_replay_kind?
  visibility:
    model_visible
    user_visible
    chat_visible
    trace_visible
  metadata:
    only exact owner facts
```

## 3. Provider request item

`LlmInputItem` 是 provider-neutral request-side canonical item，不等于 `SessionItem`。

目标字段：

```text
LlmInputItem
  kind:
    message
    reasoning
    function_call
    function_call_output
    provider_external_item
    compaction
  payload
  source:
    session_runtime_item
    context_snapshot
    tool_result
    user_input
  source_refs
  metadata
```

注意：

- `LlmInputItem` 不应携带 UI-only 字段。
- `LlmInputItem` 不应携带不确定 diagnostic judgement。
- provider renderer 负责把它变为 provider-specific item。

## Response Side: Runtime Response Projector

新增 application service，建议位置：

```text
src/crxzipple/modules/orchestration/application/runtime_response_projector.py
```

或者若 session owner 更合适：

```text
src/crxzipple/modules/session/application/runtime_projection.py
```

推荐归属：**Session module owns projection rules for runtime transcript shape; Orchestration calls it through a port.**

原因：

- LLM 不应该知道 session runtime semantics。
- Orchestration 不应该逐 provider 适配 response item。
- Session 才是 runtime transcript owner。

接口：

```python
class SessionRuntimeProjectionService:
    def project_llm_response_items(
        self,
        input: ProjectLlmResponseItemsInput,
    ) -> ProjectLlmResponseItemsResult:
        ...
```

输入：

```text
run_id
session_key
session_id
turn_id
invocation_id
response_items: tuple[LlmResponseItem, ...]
projection_context:
  provider_id
  transport
  model
  plan_mode?
```

输出：

```text
runtime_items: tuple[AppendSessionItemInput, ...]
tool_call_items: tuple[SessionRuntimeItemRef, ...]
final_answer_item_id?
last_agent_message?
projection_report:
  dropped_raw_item_refs
  unsupported_item_refs
  hidden_markup_stripped
  phase_unknown_count
```

映射规则：

| LlmResponseItem | Runtime Session Item |
| --- | --- |
| `assistant_message + commentary` | `agent_message + commentary` |
| `assistant_message + final_answer` | `agent_message + final_answer` |
| `assistant_message + unknown` | `agent_message + unknown`；不得冒充 final |
| `reasoning` | `reasoning` |
| `tool_call` | `tool_call` |
| `tool_result` | `tool_result`，仅当 provider 原生返回 tool output |
| `provider_external_item` | `provider_external_activity` |
| `compaction` | `context_compaction` |
| `unknown` | trace-only `runtime_notice` 或 projection report，不 model-visible |

Finalize 规则：

- agent text 可做 deterministic cleanup：
  - 去除 hidden assistant markup。
  - 解析 memory citation。
  - 保留 raw provider payload ref。
- 不做不可证明判断：
  - 不判断任务是否完成。
  - 不生成证据充分性。
  - 不生成下一步建议。
- `phase=commentary` 保留为 commentary，不得升级为 final。
- `phase=unknown` 保留 unknown，由 continuation / provider signal / tool calls 决定 loop。

Orchestration 调整：

- 删除或退役 `EngineSessionRecorder.append_llm_response_items` 的机械映射。
- Orchestration 调用 `SessionRuntimeProjectionService`。
- ToolRun 创建从 projected `tool_call` runtime item 派生，而不是直接从 raw `LlmResponseItem` 派生。
- continuation decision 使用：
  - provider continuation signal。
  - projected tool_call pending state。
  - final agent_message phase。
  - not raw item text heuristic。

## Tool Result Ingress

Tool result 会进入 Session，但 Session 不拥有 ToolRun 真相。

Tool module truth：

```text
ToolRun
ToolResult
stdout / stderr
artifact refs
approval state
runtime target
raw payload
```

Session runtime projection：

```text
tool_result
  call_id
  tool_name
  tool_run_id
  model_visible_payload
  user_visible_payload
  trace_ref
  provider_replay_required=true
```

必须保留：

- raw stdout/stderr 在 Tool owner / trace。
- model-visible payload 是确定的工具输出，不是猜测总结。
- UI summary 可压缩，但不影响 model-visible replay。

Session 侧只提供 runtime item query，例如
`SessionApplicationService.build_replay_window(model_visible=True)`；`SessionItem -> LlmInputItem`
属于 request projection / provider rendering 边界，不下沉到 Session owner。

不得做：

- 把完整 ToolRun truth 复制到 Session。
- 在 Session 中判断工具结果是否满足任务。
- 把 browser path / evidence verdict 合成到 tool_result model payload。

## Request Side: Runtime Request Surface + Provider Renderer

新增/收口两层：

```text
RuntimeRequestSurfaceBuilder
  -> provider-neutral runtime request

ProviderRequestRenderer
  -> provider wire payload
```

## 1. RuntimeRequestSurfaceBuilder

推荐归属：Orchestration application。

职责：

- 收集 run/session/context/tool refs。
- 请求 Session 返回 model-visible runtime transcript。
- 请求 Context Workspace 返回 context snapshot ref / compact projection。
- 请求 Tool Surface 返回 provider-visible tool schemas。
- 生成 provider-neutral `RuntimeLlmRequest`。

它不做：

- provider-specific JSON。
- prompt 拼接。
- task-specific guidance。
- evidence judgement。

输出：

```text
RuntimeLlmRequest
  run_id
  session_key
  turn_id
  user_input_ref
  instructions_refs
  context_snapshot_ref
  transcript_items: tuple[LlmInputItem, ...]
  tool_surface_snapshot_ref
  tool_schemas
  provider_policy
  options
```

## 2. SessionRuntimeTranscriptRenderer

推荐归属：Session application。

职责：

- 从 `SessionRuntimeItem` 选择 model-visible transcript。
- 保证 provider protocol required items 成对：
  - tool_call + tool_result。
  - provider external call + provider external result。
- 将 runtime item 转为 provider-neutral `LlmInputItem`。
- 不输出 provider-specific JSON。

规则：

- `user_message` -> `LlmInputItem(kind=message, role=user)`
- `agent_message` -> `LlmInputItem(kind=message, role=assistant, phase=...)`
- `reasoning` -> `LlmInputItem(kind=reasoning)`
- `tool_call` -> `LlmInputItem(kind=function_call)`
- `tool_result` -> `LlmInputItem(kind=function_call_output)`
- `provider_external_activity` -> `LlmInputItem(kind=provider_external_item)`
- `runtime_notice/runtime_error` 默认不 model-visible，除非明确属于 provider protocol recovery output。

预算/截断规则：

- 可截断普通历史 message。
- 不得截断当前 turn 的 protocol required pair。
- 不得保留 orphan tool_result。
- 不得保留 orphan tool_call 作为 replay item，除非它正等待执行且当前 request 是 tool execution 后续前的状态。
- 截断只进入 render report，不作为模型提示。

## 3. ProviderRequestRenderer

推荐归属：LLM infrastructure adapter。

职责：

- 把 `RuntimeLlmRequest` / `LlmAdapterRequest.input_items` 渲染为 provider wire payload。
- 按 provider / transport / model 能力处理：
  - OpenAI Responses HTTP。
  - Codex Responses WebSocket。
  - Anthropic Messages。
  - Gemini Generate Content。
  - Chat-compatible fallback。
- 生成 render report / wire preview。

OpenAI/Codex Responses 渲染：

```text
message                -> {"type":"message","role":...,"content":[...],"phase"?}
reasoning              -> {"type":"reasoning","summary":...,"content"?}
function_call          -> {"type":"function_call","call_id":...,"name":...,"arguments":...}
function_call_output   -> {"type":"function_call_output","call_id":...,"output":...}
provider_external_item -> provider raw-compatible item if supported; otherwise drop with report
```

Anthropic 渲染：

```text
agent tool_call        -> assistant content block tool_use
tool_result            -> user content block tool_result
agent_message          -> assistant message
user_message           -> user message
reasoning              -> not replayed unless provider supports equivalent; report drop/degrade
```

Gemini 渲染：

```text
tool_call              -> model part functionCall
tool_result            -> functionResponse
message                -> user/model parts
reasoning              -> not replayed unless supported; report drop/degrade
```

## LLM Module 调整

### Response parser

必须修改：

- `build_openai_response_items` 读取 raw `phase`。
- raw `message.role` 保留。
- `reasoning` 的 `summary/content/encrypted_content` 保留 provider payload。
- provider item id/call id 不丢。
- `user_visible` 默认值不等同于 chat-visible；chat-visible 由 session projection 决定。

新增测试：

- OpenAI/Codex `message phase=commentary` -> `LlmResponseItem.phase=COMMENTARY`。
- `message phase=final_answer` -> `FINAL_ANSWER`。
- no phase -> `UNKNOWN`。
- reasoning summary 不自动变 chat-visible final answer。

### Request renderer

必须收口：

- 保留 `openai_codex_responses_renderer.py` 的 provider renderer 方向。
- 但上游只能传 provider-neutral `LlmInputItem`。
- 删除 provider renderer 中对 runtime diagnostics 的依赖。
- render report 只记录：
  - rendered item count。
  - dropped item refs。
  - degraded item refs。
  - continuation strategy。
  - unsupported field omissions。

## Session Module 调整

### Schema breaking change

允许 breaking migration：

- rename / replace `assistant_message` -> `agent_message`。
- rename / replace `provider_external_item` -> `provider_external_activity`。
- replace `system_note` -> `runtime_notice` / `runtime_error`。
- 增加 protocol fields：
  - `turn_id`
  - `llm_invocation_id`
  - `llm_response_item_id`
  - `tool_run_id`
  - `tool_result_id`
  - `provider_replay_required`
  - `provider_replay_kind`

### Application service

新增：

- `SessionRuntimeProjectionService`
- `SessionRuntimeTranscriptService`

删除/退役：

- 面向 LLM response 的机械 append helper。
- 将 `SessionItemKind` 当 provider response item kind 的直映射函数。

## Orchestration 调整

Orchestration 只做协调：

```text
1. submit user input
2. append user_message runtime item
3. build RuntimeLlmRequest via RequestSurfaceBuilder
4. invoke LLM
5. project LLM response into Session runtime items
6. create ToolRun from projected tool_call items
7. append tool_result runtime items after tool completion
8. next LLM request renders session transcript through SessionRuntimeTranscriptService + LLM provider renderer
9. terminate based on provider signal + runtime item state
```

Orchestration 不再：

- 拼 provider input JSON。
- 把 context tree XML 当 prompt body。
- 生成 evidence frontier 给模型。
- 根据任务特化证据判定完成。

## Context Workspace 调整

Context Workspace 只维护：

- Context Tree。
- snapshot。
- node state。
- provider attachment mirror facts。
- context tree agent-facing tools。

它输出给 request builder 的是：

```text
ContextSnapshotRef
compact_projection
tree tool availability refs
provider attachment refs
```

它不输出：

- provider prompt body。
- browser path hint。
- evidence judgement。
- model next-step instruction。

完整树查看通过工具：

- `context_tree.render_current`
- `context_tree.read_snapshot`
- `context_tree.diff_since`

## Workbench / Operations 调整

Workbench timeline 消费 runtime session item，不消费 raw provider item。

UI 显示规则：

- `agent_message commentary`：进展消息。
- `agent_message final_answer`：最终回答。
- `reasoning`：折叠/可展开，根据策略展示 summary，不作为聊天正文。
- `tool_call`：工具调用。
- `tool_result`：工具结果摘要。
- `provider_external_activity`：provider 原生外部活动。
- `runtime_error`：明确错误和处理建议。

Operations / Trace 展示：

- raw LLM provider payload。
- `LlmResponseItem`。
- runtime projected SessionItem。
- provider request render preview。
- render loss report。

这四者不能混为同一条 UI timeline。

## Migration Plan

## Phase 1: Fix LLM Response Fidelity

- [x] 修改 OpenAI/Codex response parser，保留 raw `phase`。
- [x] 修正 reasoning / provider external item 的默认 visibility。
- [x] 增加 `LlmResponseItem` phase roundtrip 测试。
- [x] 增加 OpenAI/Codex SSE item parser 测试。

## Phase 2: Introduce Session Runtime Projection

- [x] 新增 runtime response projection service。
- [x] 新增 runtime item kind breaking migration。
- [x] 删除 `EngineSessionRecorder` 内部 `LlmResponseItem -> SessionItem` 机械映射，改由 projector 生成 session append input。
- [x] Orchestration 改为调用 projection service。
- [x] ToolRun 创建改从 projected `tool_call` runtime item 派生。
- [x] 增加 response projection 单测。

落地说明：

- `RuntimeResponseProjector` 已迁入 `modules/session/application/runtime_response_projection.py`，归 Session application owner。
- Orchestration 只调用 Session application 的 projection service，把 provider-neutral `LlmResponseItem` 投影为 runtime `SessionItem` append input。
- Orchestration 不再持有 `LlmResponseItem -> SessionItem` 的逐 provider / 逐 kind 映射规则；tool loop 只消费 projector 输出的 `ToolCallIntent`。
- Session item kind runtime contract 已破坏式收敛：`provider_external_item` -> `provider_external_activity`，`compaction` -> `context_compaction`，`system_note` -> `runtime_notice` / `runtime_error`。Session persistence 的 `kind` 是 string column，数据库重建即可承载新值，不需要保留旧 enum 兼容迁移。

## Phase 3: Introduce Session Transcript Renderer

- [x] Session 提供 model-visible runtime transcript query。
- [x] Session runtime item -> `LlmInputItem`。
- [x] 保证 tool_call/tool_result 成对。
- [x] 删除 orphan protocol item replay。
- [x] 截断和预算报告不进入 model input。
- [x] 增加 transcript renderer 单测。

## Phase 4: Move Provider Rendering to LLM Boundary

- [x] Orchestration 只构造 provider-neutral `RuntimeLlmRequest`。
- [x] LLM provider renderer 负责 provider wire payload。
- [x] OpenAI/Codex renderer 消费 `LlmInputItem`。
- [x] Anthropic/Gemini renderer 消费同一 canonical request。
- [x] 删除 orchestration 中 provider-specific request assembly。
- [x] 增加 provider renderer parity tests。

落地说明：

- `RuntimeLlmRequest.transcript.policy.require_tool_call` 是 provider-neutral request policy。
- Orchestration 不再按 `api_family` 生成 `tool_choice` / `toolConfig`。
- LLM provider renderer 负责把 `require_tool_call` 翻译为 OpenAI/Codex/OpenAI Chat 的 `tool_choice=required`、Anthropic 的 `tool_choice={"type":"any"}`、Gemini 的 `toolConfig.functionCallingConfig.mode=ANY`。
- `LlmInvocation.request_policy` 持久化该中立策略，保证 sync/async/stream/provider preview 入口看到同一份 runtime request policy。

## Phase 5: Context Workspace Boundary Cleanup

- [x] Context Workspace 不再产出 provider prompt body。
- [x] render snapshot 只作为 context fact / compact projection。
- [x] tree replay/read tool 作为模型主动查看树的唯一 full tree 通道。
- [x] 删除 model-visible evidence/frontier/browser path hints。
- [x] 增加 context snapshot boundary tests。

落地说明：

- Context Workspace 仍可生成 `debug_body` 作为 snapshot/debug fact，但该 body 不进入 `RuntimeLlmRequest.messages` / `RuntimeLlmRequest.transcript.items`。
- Provider renderer 只消费 runtime transcript items、tool schemas、provider attachments 和 request metadata preview；不会把完整 Context Tree debug body 渲染进 provider payload。
- `browser_evidence` / evidence path 类事实允许保留在 Tool/Context/Operations debug surface；runtime transcript 已验证不会把 `evidence_path` 作为 model-visible replay 指导发送给 LLM。
- `context_tree.render_current`、`context_tree.read_snapshot`、`context_tree.diff_since` 是模型主动读取 current/snapshot/delta tree debug body 的工具通道；默认 runtime request 只携带 snapshot refs / provider attachments / diagnostics，不把 full debug body塞进 provider wire input。

## Phase 6: Workbench / Operations Projection

- [x] Workbench timeline 改读 runtime session items。
- [x] Trace 展示 raw provider item / LLM item / runtime item / provider request preview 的关联。
- [x] Operations LLM 页面显示 renderer id、transport、render strategy、loss report。
- [x] 错误提示从 runtime_error / invocation failure facts 投影，不从兜底文案猜测。

### Phase 6 落地记录

- Workbench 主时间线不再从 `LlmInvocation.response_items` 直接展开用户可见进展；`_timeline_items_from_steps` 只投影 runtime step / SessionItem / Tool lifecycle / final response / continuation。
- 成功完成但无用户进展内容的 generic LLM step 不再污染 Workbench 主时间线；失败、运行中、等待态仍可作为 runtime 状态展示。
- LLM response item / provider item 保留为 owner/debug/detail 事实，由 Trace / linked entity / LLM Operations 展示，不再决定 Workbench timeline 的用户阅读结构。
- UI HTTP fixture 已补齐 FINAL_RESPONSE runtime step，不再依赖 raw final `LlmResponseItem` 回填最终答复。
- Trace read model / UI linked entities 已覆盖 `llm_response_item_id`、`session_item_id` 等 source refs，raw provider/LLM/runtime 事实通过详情关联观察。
- Operations LLM detail 已展示 provider renderer id、transport、render strategy、render report / loss report 和 wire preview，render report 不混入 Workbench 主 timeline。
- Workbench failed run guidance 来自 run error / invocation failure facts，用户可见错误提示不再靠 fallback 猜测生成。

## Phase 7: Regression and Codex Parity

- [x] 用抓包 Codex trace 固化 OpenAI/Codex request/response contract fixture。
- [x] 对比 CRXZipple provider wire payload。
- [x] 对比 projected runtime timeline。
- [ ] 验证无 browser 特权时 exec 工具探索链仍可自然进行。
- [ ] 验证失败时模型基于 transcript 说明失败原因，不由内核生成 evidence verdict。

### Phase 7 实测补充：Codex trace vs CRXZipple 最新会话

本补充只记录已经抓到的运行事实，不把推测写成结论。

Codex 抓包 trace：

- trace 目录：`.crxzipple/codex-flight-trace-20260615-084222/`
- 输入任务：东航官网，昆明到上海，周日票价查询。
- turn 状态：`turn.started=1`，`turn.completed=1`。
- completed item：
  - `agent_message=23`
  - `command_execution=42`
  - `mcp_tool_call=4`
  - `web_search=2`
- 可见行为：
  - browser 不可用时没有卡死，转向官网静态资源、JS 包、接口定位和 shell 请求。
  - `agent_message` 持续向用户说明当前判断和下一步动作。
  - 最终没有可靠拿到票价，但能说明官网接口、WAF/失败路径和证据来源。

CRXZipple 最新实测会话：

- run id：`e271dd1d2e784730a2c3b646498f9504`
- session id：`1eb9c5ca-528c-4aa8-a11c-87a348539d1b`
- run status：`completed`
- LLM：`openai_codex.gpt-5.5`
- execution chain：`chain:e271dd1d2e784730a2c3b646498f9504`，`step_count=85`
- session item count：`122`
  - `user_message=1`
  - `assistant_message=1`
  - `reasoning=34`
  - `tool_call=42`
  - `tool_result=44`
- tool call count：`42`
  - `exec=37`
  - `web.fetch_text=3`
  - `context_tree.update_plan=2`
- LLM response item count：`77`
  - `function_call=42`
  - `reasoning=34`
  - `message=1`
- provider request final invocation：
  - `transport=websocket`
  - `renderer_id=openai_codex_responses`
  - `render_strategy=provider_native_delta`
  - `previous_response_id` present
  - `input_delta_mode=true`
  - `input_item_count=2`
  - `input_item_types=["function_call","function_call_output"]`
  - `input_baseline_count=90`

当前差距判断：

1. **核心探索能力已经接近。**
   CRXZipple 也能自然使用 shell、Python、官网 JS、官网接口、网络请求继续探索；最新会话不是停在 browser 缺失或 DOM 不可用。
2. **最大差距是 runtime timeline projection。**
   Codex trace 有 23 条 `agent_message`；CRXZipple 最新 session 没有 `agent_message` kind，阶段性内容主要落在 `reasoning`，且 `user_visible=false`、`chat_visible=false`。
3. **provider wire continuation 已接近。**
   CRXZipple 最新 WebSocket 请求已经使用 `previous_response_id + delta input`，不是早期全量 prompt 回放。
4. **Workbench 用户感知仍弱。**
   用户看不到 Codex 那种“我观察到什么、下一步做什么”的阶段性叙事，即使模型内部已经产生了大量 reasoning summary / tool chain。
5. **不应把 `reasoning` 直接改成 chat 消息。**
   Codex 的 `agent_message` 是 runtime projection / event item；CRXZipple 应新增 trace-visible progress projection，而不是把 raw reasoning mirror 暴露给 chat 或重复喂回模型。

### Phase 7 新增施工项

- [x] 固化 Codex trace fixture：解析 `.crxzipple/codex-flight-trace-20260615-084222/codex-exec-events.jsonl`，断言 `agent_message=23`、`command_execution=42`、`mcp_tool_call=4`、`web_search=2`。
- [x] 固化 CRXZipple latest-run regression fixture：断言最新投影前存在 `reasoning=34`、`tool_call=42`、`assistant_message=1`、`agent_message=0` 的差距。
- [x] 新增 `agent_progress` / `agent_message(commentary)` runtime projection：来源必须是 provider 明确给出的 assistant commentary，或 LLM response 中可确认的 non-empty reasoning summary；不得由内核编造下一步建议。
- [x] `agent_progress` 默认 `user_visible=true`、`trace_visible=true`、`chat_visible=false`、`model_visible=false`，并记录 `source_llm_response_item_id`，避免重复写回模型。
- [x] Workbench 主时间线展示 `agent_progress`，但 chat 区只展示 user message 和 final answer。
- [x] Trace/detail 保留 raw reasoning、raw provider item、projection source refs，方便审计 projection 是否忠实。
- [x] 继续隐藏或分流 approval/context_tree/debug/runtime render report 等内部噪声；它们可在 Trace/Operations detail 中查看，不进入主叙事。
- [ ] 复跑东航任务，目标不是强求拿到票价，而是对比 timeline：CRXZipple 至少应能展示与 Codex 同等级别的阶段性观察和行动说明。

### Phase 7 施工记录：agent progress projection

- `SessionItemKind` 新增 `agent_progress`，作为用户可见、trace 可见、chat 不可见、model 不可见的 runtime projection item。
- `tests/unit/test_codex_trace_fixture.py` 固化 Codex trace lifecycle 计数；本地 trace 存在时断言真实抓包 `agent_message=23`、`command_execution=42`、`mcp_tool_call=4`、`web_search=2`。
- `tests/unit/test_runtime_response_projector.py` 固化 CRXZipple latest-run 等价输入形态：`reasoning=34`、`tool_call=42`、`assistant_message=1` 会投影出 `agent_progress=34`，避免阶段性进展继续只停留在 raw reasoning。
- `WorkbenchReadModel` 取消 `context_tree.update_plan` -> `Agent Progress` 的旧特判；`context_tree.*` 控制面 tool call 不再进入 Workbench 主时间线，避免把内部控制状态伪装成用户叙事。
- `Operations LLM Detail` 的 response items 表新增 `provider_payload` 审计列；raw provider payload 留在 Trace/Operations detail，Workbench 主时间线继续只消费筛过的用户叙事。
- `tests/unit/test_openai_codex_renderer.py` 和 `tests/unit/test_openai_codex_transport_wire_contract.py` 固化 Codex provider wire：HTTP 全量 replay 且不发送 `previous_response_id`；WebSocket 使用 `previous_response_id + delta input`。
- `RuntimeResponseProjector` 对 non-empty `reasoning.summary` 生成 `agent_progress`，同时保留原始 `reasoning` item 作为 model-visible protocol/history fact。
- assistant commentary 不再额外复制一条 progress；它本身作为 commentary item，由 recorder 归入 `assistant_progress_item_ids`。
- `OrchestrationSessionRecorder.append_llm_response_items` 会回传 `assistant_progress_item_ids`，来源包括：
  - `SessionItemKind.AGENT_PROGRESS`
  - user-visible assistant commentary
- `OrchestrationEngine` 会把 projector 产生的 progress ids 送入 `EngineAdvanceOutcome`，execution chain 因而能物化 `SESSION_MESSAGE/message_kind=assistant_progress`。
- Workbench read model 已经通过 `assistant_progress_item_ids` 和 session item fallback 显示 `agent_progress`，不会回退到 raw LLM response item 直接展示。
- 去重规则只去掉重复 session id，不改变 owner module truth。
- 已验证：
  - `PYTHONPATH=src pytest -q tests/unit/test_runtime_response_projector.py tests/unit/test_orchestration_execution_chain.py tests/unit/test_runtime_transcript.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_workbench_read_model.py`

## Acceptance Criteria

必须满足：

- [x] `LlmResponseItem` 不再直接等同 `SessionItem`。
- [x] Session 保存 runtime transcript，不保存 provider mirror 作为主 timeline。
- [x] Tool result 进入 Session runtime transcript，但 Tool module 仍拥有 ToolRun truth。
- [x] Provider request 只能由 LLM provider renderer 生成。
- [x] Context Tree 不默认完整塞入 provider input。
- [x] Codex HTTP 不发送 unsupported `previous_response_id`。
- [x] Codex WebSocket continuation 只在 trace/能力确认支持时启用。
- [x] `commentary` 不会被误标为 `final_answer`。
- [x] model input 不包含 evidence frontier / browser evidence path / loop correction。
- [x] Workbench timeline 与 provider raw trace 不混为一谈。

### Acceptance 落地记录

- Runtime response projector 已验证 assistant commentary 即使 `user_visible=true` 也保持 `SessionItemPhase.COMMENTARY` 且 `chat_visible=false`；只有 `FINAL_ANSWER` phase 进入 chat-final 视图。
- Provider external response item 投影为 `SessionItemKind.PROVIDER_EXTERNAL_ACTIVITY`，保留 `source_id/provider_item_id/provider_item_type` 作为 Trace/detail refs，不伪装成 assistant message 或 final answer。
- Runtime transcript 测试覆盖 SessionItem -> provider canonical input item 渲染，provider-specific payload 仍由 LLM provider renderer 生成。

## Validation Commands

按施工范围选择：

```bash
PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py
PYTHONPATH=src pytest -q tests/unit/test_openai_codex_renderer.py
PYTHONPATH=src pytest -q tests/unit/test_provider_protocol_render_router.py
PYTHONPATH=src pytest -q tests/unit/test_runtime_response_projector.py
PYTHONPATH=src pytest -q tests/unit/test_runtime_transcript.py
PYTHONPATH=src pytest -q tests/unit/test_session.py
PYTHONPATH=src pytest -q tests/unit/test_session_segment_compaction.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_runtime_llm_request.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_tools.py
PYTHONPATH=src pytest -q tests/unit/test_workbench_read_model.py
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_read_model.py

cd frontend
npm run typecheck
npm run build
```

## 执行决策

1. `SessionItemKind.ASSISTANT_MESSAGE` 暂不 rename 为 `AGENT_MESSAGE`。
   - 原因：当前 response projection 已用 `phase/visibility/chat_visible` 区分 commentary 与 final answer；继续 rename 会扩散到 channel/chat surface，收益低于风险。
2. Response projection service 归属 Session。
   - 已执行：`RuntimeResponseProjector` 在 `modules/session/application/runtime_response_projection.py`，Orchestration 只调用。
3. `runtime_transcript.py` 后续迁入 Session application。
   - 当前状态：仍在 Orchestration application 下，但已作为 provider-neutral renderer 使用；后续独立迁移，不阻塞本阶段验收。
4. `LlmInputItem` 继续由 LLM domain 持有。
   - 原因：它是 provider-neutral request canonical item，由 provider renderer 消费。
5. render loss report 不 model-visible。
   - 已执行：只进 Operations / Trace / Workbench debug/detail surface。

## 最终目标图

```text
LLM raw response
  -> LlmResponseItem
  -> SessionRuntimeProjectionService
  -> SessionRuntimeItem
  -> Workbench timeline / Orchestration runtime decisions

ToolRun result
  -> Tool owner truth
  -> Session tool_result runtime projection
  -> SessionRuntimeTranscriptRenderer
  -> LlmInputItem(function_call_output)
  -> ProviderRequestRenderer
  -> provider wire input

Context Tree
  -> ContextSnapshotRef / compact projection / tree tools
  -> RuntimeLlmRequest
  -> ProviderRequestRenderer
  -> provider wire input
```

这套结构把 Codex 已验证的有效分层吸收进 CRXZipple，但不把 CRXZipple 绑定到 Codex，也不把任务特化逻辑放进内核。
