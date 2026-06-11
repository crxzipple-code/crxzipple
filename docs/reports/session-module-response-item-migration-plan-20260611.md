# Session Module Response Item Migration Plan 2026-06-11

本文记录 LLM 能力升级后 Session module 的目标形态：从“聊天消息记录”升级为“会话事实流”，承接 LLM response items、tool protocol facts、用户输入和 runtime 写入的可重放事实。

关联文档：

- [provider-neutral-llm-response-stream-contract-plan-20260611.md](provider-neutral-llm-response-stream-contract-plan-20260611.md)
- [orchestration-llm-contract-driven-runtime-plan-20260611.md](orchestration-llm-contract-driven-runtime-plan-20260611.md)
- [workbench-agent-timeline-read-model-plan-20260611.md](workbench-agent-timeline-read-model-plan-20260611.md)
- [context-workspace-llm-request-surface-plan-20260611.md](context-workspace-llm-request-surface-plan-20260611.md)
- [../session-semantics-design.md](../session-semantics-design.md)
- [../orchestration-design.md](../orchestration-design.md)
- [../context-workspace-prompt-tree-design.md](../context-workspace-prompt-tree-design.md)

## Cutover Assumption

开发前会清除并重建数据库。本计划不考虑历史数据兼容，不设计旧 `session_messages` backfill，不保留 dual-read / dual-write，不为了旧 UI projection 保留旧字段语义。

如果旧表、旧 DTO、旧 prompt transcript 或旧测试阻碍 agent 最佳效果，应直接迁到新结构。

## 定位

Session module 不拥有 LLM provider 真相，也不拥有 ToolRun 真相。Session 拥有的是“哪些事实进入这条会话，并且这些事实如何被用户、模型和运行时重放”。

目标边界：

```text
LLM response item truth        -> llm module
ToolRun truth                  -> tool module
Turn / execution chain truth   -> orchestration module
Conversation fact stream       -> session module
Prompt tree selection/render   -> context_workspace module
Operations / Workbench view    -> operations module
```

Session module 要做的是保存会话事实引用和可见性，不复制所有 owner module payload。

## 当前问题

### 1. Message 语义过窄

旧 session 以 `role + content_payload` 为中心，天然像聊天气泡。它难以表达：

- assistant commentary。
- assistant final answer。
- reasoning summary。
- model tool call。
- tool result。
- provider external item。
- compaction item。
- unknown provider item。

这些事实不一定都要作为聊天消息展示，但可能都需要进入下一轮 provider input。

### 2. 可见性混在一起

旧结构无法稳定区分：

```text
model_visible
user_visible
chat_visible
trace_visible
```

结果是：

- 用户可见内容不一定进入模型历史。
- 模型需要的 provider protocol item 可能被 UI 当聊天消息展示。
- trace/debug 需要的 reasoning 或 raw provider item 被压扁或丢失。

### 3. Prompt replay 过度依赖 role/content

现代 provider 不只需要普通 `role/content`。OpenAI Responses / Codex Responses 等 provider 可能需要 replay：

```text
message
reasoning
function_call
function_call_output
provider external item
```

Session 如果只提供扁平 text transcript，Context Workspace / Orchestration 只能重新猜测 provider protocol。

### 4. Tool call/result 连续性不足

provider replay 需要稳定保留：

```text
call_id
tool_name
provider_item_id
arguments
result mapping
```

这些字段不能藏在一段文本或 loose metadata 里。

## 目标

### 必须达成

1. Session 以 `SessionItem` 表达会话事实，而不是只表达聊天消息。
2. 每个 session item 显式记录 `kind`、`role`、`phase`、可见性和来源引用。
3. Session 可提供 provider-neutral 的 model-visible replay view。
4. Session 可提供 UI/Workbench 可消费的 user-visible/chat-visible view，但 Workbench 不直接绕过 Operations 聚合。
5. tool call / tool result item 必须保留 `call_id` 和 `tool_name`。
6. LLM response item 写入 Session 时必须保留 `source_module/source_kind/source_id/provider_item_id`。
7. Session 不判断 agent loop 是否继续；loop 决策仍由 Orchestration 综合 LLM continuation、tool state、approval、pending input。
8. 支持数据库完全重建，不做旧消息兼容。

### 非目标

- 不在 Session 保存完整 provider-native response event 流。
- 不让 Session 解析 provider payload。
- 不让 Session 直接执行 compaction 或 Context Tree 渲染。
- 不让 Session 替代 Orchestration execution chain。
- 不让 Workbench 直接消费 Session 表拼 timeline。

## 新领域模型

### SessionItemKind

```text
user_message
assistant_message
reasoning
tool_call
tool_result
provider_external_item
compaction
system_note
unknown
```

说明：

- `user_message`：用户或 channel 输入。
- `assistant_message`：模型输出的自然语言，可带 phase。
- `reasoning`：reasoning summary 或可公开 reasoning 片段；raw reasoning 不默认写入 Session。
- `tool_call`：模型请求本地/runtime tool 的 provider protocol fact。
- `tool_result`：tool result replay fact。
- `provider_external_item`：provider-hosted capability item，不创建 ToolRun。
- `compaction`：会话压缩或 segment summary fact。
- `system_note`：runtime 写入的会话级说明，例如 reset/segment rotation。
- `unknown`：保留结构化引用，避免未知 provider item 丢失。

### SessionItemPhase

```text
commentary
final_answer
unknown
```

phase 是 LLM response item 的能力投影，不是 prompt 文案规则。

### Visibility Flags

```text
model_visible
user_visible
chat_visible
trace_visible
```

默认建议：

| Kind | model_visible | user_visible | chat_visible | trace_visible |
| --- | --- | --- | --- | --- |
| user_message | true | true | true | true |
| assistant_message/commentary | true | true | false | true |
| assistant_message/final_answer | true | true | true | true |
| reasoning summary | provider-dependent; true for Responses/Codex parity | true | false | true |
| tool_call | true | false | false | true |
| tool_result | true | false | false | true |
| provider_external_item | provider-dependent; true for Responses/Codex parity | true | false | true |
| compaction | true | false | false | true |

可见性由 Orchestration 写入 Session 时确定；Session 只持久化，不自行推断业务语义。

## 目标 Schema

可以破坏式替换旧表。建议核心表：

```text
sessions
  id
  session_key
  agent_id
  active_segment_id
  metadata
  created_at
  updated_at

session_segments
  id
  session_id
  status
  opened_at
  closed_at
  summary_item_id
  metadata

session_items
  id
  session_id
  segment_id
  sequence_no
  role
  kind
  phase
  content_payload
  source_module
  source_kind
  source_id
  provider_family
  provider_item_id
  provider_item_type
  call_id
  tool_name
  model_visible
  user_visible
  chat_visible
  trace_visible
  created_at
```

索引建议：

```text
(session_id, sequence_no)
(segment_id, sequence_no)
(session_id, model_visible, sequence_no)
(source_module, source_kind, source_id)
(call_id)
```

## 写入规则

### User Input

用户输入写为：

```text
kind=user_message
role=user
model_visible=true
user_visible=true
chat_visible=true
trace_visible=true
source_module=orchestration|channel|http
```

### Assistant Message

LLM response item：

```text
kind=assistant_message
role=assistant
phase=commentary|final_answer|unknown
source_module=llm
source_kind=llm_response_item
source_id=<llm_response_item_id>
provider_item_id=<provider item id>
```

commentary 是否 `chat_visible` 默认为 false，由 Workbench 作为 agent progress 展示，不混入聊天气泡。

### Reasoning

reasoning summary 可以写入 Session item，但必须区分：

```text
content_payload.summary_text
content_payload.reasoning_type = summary|raw|encrypted_reference
```

raw reasoning 默认不进入 Session；如需要调试，应留在 LLM module raw payload / Operations trace 权限视图。

### Tool Call / Tool Result

tool call：

```text
kind=tool_call
role=assistant
call_id=<provider call id>
tool_name=<tool function name>
model_visible=true
trace_visible=true
source_module=llm
source_kind=llm_response_item
```

tool result：

```text
kind=tool_result
role=tool
call_id=<same call id>
tool_name=<tool function name>
model_visible=true
trace_visible=true
source_module=tool
source_kind=tool_run
source_id=<tool_run_id>
```

### Provider External Item

provider-hosted item 写成：

```text
kind=provider_external_item
source_module=llm
source_kind=llm_response_item
```

它可以进入 model-visible replay，但不创建 CRXZipple ToolRun。

## 读取接口

### Application Service

建议新增或调整：

```text
append_item(command)
append_items(commands)
list_items(session_id, segment_id=None, visibility=None, limit=None, cursor=None)
list_model_visible_items(session_id, budget=None, provider_family=None)
list_chat_items(session_id, limit=None, cursor=None)
list_trace_items(session_id, limit=None, cursor=None)
```

### Model Replay View

Session 输出 provider-neutral replay facts：

```text
SessionReplayItem
  id
  sequence_no
  role
  kind
  phase
  content_payload
  provider_item_id
  call_id
  tool_name
  source_ref
```

Context Workspace / prompt renderer 再把它们映射到目标 provider input。

## 与 Orchestration 配合

Orchestration 负责：

- 从 LLM response items 决定哪些 item 写入 Session。
- 从 ToolRun 结果决定哪些 tool result 写入 Session。
- 维护 turn / execution chain 与 session item 的引用关系。
- 决定 final answer 是否完成 turn。
- 决定 commentary/reasoning 是否用户可见。

Session 不负责：

- 判断 `end_turn=false`。
- 判断没有 tool call 是否终止。
- 重试 tool call。
- 推进 OrchestrationRun 状态。

## 与 Context Workspace 配合

Context Workspace 不直接读 provider payload。它通过 Session replay view 和 Orchestration run references 获取可选上下文：

```text
session.active_segment.*
session.compacted_segment.*
session.model_visible_items.*
session.tool_interactions.*
```

预算控制可以折叠或压缩 Session items，但不能破坏当前 turn 的 provider protocol 连续性。

## 退场项

必须退场或降级：

- `session_messages == chat timeline` 的假设。
- 只用 `role/content` 构建 provider input 的 prompt transcript。
- assistant progress 特殊消息概念。
- function_call message 被 Workbench 当自然语言 progress 展示。
- 通过 loose metadata 关联 tool call/result。
- 不得为旧 session message 结构保留长期兼容 shim。

## Checklist

### Domain

- [ ] 新增 `SessionItemKind`。
- [ ] 新增 `SessionItemPhase`。
- [ ] 新增 `SessionItem` entity/value object。
- [ ] 显式可见性字段进入领域模型。
- [ ] `SessionSegment` 与 `SessionItem` 关系明确。

### Persistence

- [ ] 破坏式调整 session schema。
- [ ] 建立 `session_items` 表。
- [ ] 建立 source reference 索引。
- [ ] 建立 call_id 索引。
- [ ] 删除或停止使用旧 `session_messages` 主路径。

### Application

- [ ] 实现 append item/items。
- [ ] 实现 model-visible replay query。
- [ ] 实现 chat-visible query。
- [ ] 实现 trace-visible query。
- [ ] 确保 Session 不解析 provider-native payload。

### Orchestration Integration

- [ ] LLM `assistant_message` item 写入 Session。
- [ ] LLM `reasoning` item 按策略写入 Session。
- [ ] LLM `tool_call` item 写入 Session。
- [ ] ToolRun result 写入 `tool_result` item。
- [ ] provider external item 写入 Session 或仅写 trace，根据 policy 决定。
- [ ] execution chain 记录相关 session item ids。

### Context Workspace Integration

- [ ] prompt input builder 使用 model-visible Session replay view。
- [ ] 当前 turn provider protocol items 不被预算压坏。
- [ ] 历史 session items 可折叠/压缩。

### Verification

- [ ] user -> assistant final answer 单轮可重放。
- [ ] assistant commentary + tool_call + tool_result + final answer 链路可重放。
- [ ] tool_call/tool_result call_id 完整。
- [ ] commentary 在 Workbench 可见但不作为普通聊天气泡。
- [ ] reasoning summary 的 model/user/trace 可见性符合 policy。
- [ ] 清库重建后所有 session 单测通过。
