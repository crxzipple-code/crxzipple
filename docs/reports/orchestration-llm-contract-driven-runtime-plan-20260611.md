# Orchestration LLM Contract Driven Runtime Plan 2026-06-11

本文记录 LLM request / response contract 升级后 Orchestration module 的目标形态：从 `LlmResult(text + tool_calls)` 驱动的简单循环，升级为 `LlmRequestEnvelope + LlmResponseItem + LlmContinuationSignal` 驱动的 agent runtime coordinator。

关联文档：

- [provider-neutral-llm-response-stream-contract-plan-20260611.md](provider-neutral-llm-response-stream-contract-plan-20260611.md)
- [session-module-response-item-migration-plan-20260611.md](session-module-response-item-migration-plan-20260611.md)
- [workbench-agent-timeline-read-model-plan-20260611.md](workbench-agent-timeline-read-model-plan-20260611.md)
- [context-workspace-llm-request-surface-plan-20260611.md](context-workspace-llm-request-surface-plan-20260611.md)
- [tool-surface-llm-request-contract-plan-20260611.md](tool-surface-llm-request-contract-plan-20260611.md)
- [operations-agent-runtime-projection-plan-20260611.md](operations-agent-runtime-projection-plan-20260611.md)
- [model-agent-policy-llm-request-options-plan-20260611.md](model-agent-policy-llm-request-options-plan-20260611.md)
- [agent-runtime-contract-upgrade-testing-strategy-20260611.md](agent-runtime-contract-upgrade-testing-strategy-20260611.md)
- [codex-like-agent-loop-governance-development-plan-20260611.md](codex-like-agent-loop-governance-development-plan-20260611.md)
- [../orchestration-design.md](../orchestration-design.md)
- [../context-workspace-prompt-tree-design.md](../context-workspace-prompt-tree-design.md)
- [../session-semantics-design.md](../session-semantics-design.md)

## Cutover Assumption

开发前会清除并重建数据库。本计划不考虑历史 orchestration run、旧 execution item、旧 `LlmResult.tool_calls` 循环、旧 prompt transcript、旧 Operations projection 的兼容。

如果旧 run schema、旧 engine outcome、旧 DTO 或旧测试阻碍 agent 最佳效果，应直接迁到新结构。migration 只服务新库初始化，不设计历史升级路径。

## 施工进展 2026-06-12

- Engine outcome / LLM step event / run result payload / prompt metadata 已删除旧 `assistant_message_id(s)`、`user_message_id` 输出。
- Final response execution step materialization 已改用 `assistant_session_item_ids`，owner kind 使用 `session_item`。
- Progress/waiting coordinator summary 已使用 `session_item_ids`、`assistant_progress_item_ids`、`user_session_item_id`，不再写旧 assistant/user message id。
- Orchestration 已停止声明 `orchestration.session.message_observation` 和 `orchestration.run.message_appended` 观察契约；Session item append 作为 Session owner fact 直接进入事件契约。

## 定位

Orchestration 是综合 runtime 流程协调者。LLM 能力升级后，它仍不拥有 LLM、Tool、Session、Context Workspace 的内部真相，但必须消费这些模块暴露的新契约，完成：

- request side：收集 runtime 输入，构造 LLM request envelope。
- response side：消费 LLM response items / continuation signal。
- loop side：综合 tool execution、approval、wait state、pending input 决定下一步。
- projection side：记录 execution chain 因果关系，供 Operations/Workbench 投影。

目标边界：

```text
Session model-visible replay     -> session module
Context Tree render snapshot     -> context_workspace module
Tool surface / runtime policy    -> tool module
Provider request/response truth   -> llm module
Turn / execution chain decision   -> orchestration module
Workbench projection             -> operations module
```

## 当前问题

### 1. Request side 过薄

旧 Orchestration 容易把 LLM request 简化为：

```text
system prompt
session messages
tool schemas
```

这无法表达：

- provider-native input item replay。
- Context Workspace render snapshot 引用。
- tool surface metadata。
- reasoning config。
- output contract / response format。
- provider capability options。
- invocation metadata / cache key / service tier。

### 2. Response side 过薄

旧 engine 只看：

```text
LlmResult.text
LlmResult.tool_calls
```

这无法表达：

- assistant commentary vs final answer。
- reasoning summary。
- provider external item。
- tool argument delta。
- `end_turn=false`。
- continuation reason。

### 3. Loop 判断过度依赖 tool_calls

旧判断：

```text
if result.tool_calls:
    execute tools
else:
    finish
```

这会导致：

- 没有 tool call 但 provider 要求 follow-up 时过早结束。
- 只有 commentary 但没有 final answer 时误判完成。
- tool error / provider end_turn=false / pending external 无法被正确表达。

### 4. Execution chain 因果粒度不足

旧 execution chain 记录 invocation、tool run、session message，但不能稳定解释：

- 哪个 response item 触发了哪个 ToolRun。
- 哪个 assistant commentary 写入了哪个 SessionItem。
- 哪个 continuation signal 导致下一轮 LLM invocation。
- provider external item 为什么没有 ToolRun。

## 目标

### 必须达成

1. Orchestration request side 使用 `LlmRequestEnvelope`，不直接拼 provider-native request。
2. `LlmRequestEnvelope` 同时承载 base instructions、input items、context surface、tool surface、reasoning config、output contract、provider options、metadata。
3. Orchestration response side 使用 `LlmResponseItem` 和 `LlmContinuationSignal` 驱动 loop。
4. Tool execution plan 从 `LlmResponseItem(kind=tool_call)` 派生，不从 `LlmResult.tool_calls` 派生。
5. Session 写入从 response item 投影，不再围绕 `LlmResult.text + tool_calls` 特判。
6. Final answer 不再等于“没有 tool call”，必须结合 phase、continuation 和 orchestration pending state。
7. Execution chain 记录 response item、session item、tool run、continuation decision 的因果关系。
8. provider external item 不创建 ToolRun，只进入 LLM/Session/Trace/Workbench 投影。
9. 支持数据库完全重建，不做旧 run/execution 兼容。

### 非目标

- 不让 Orchestration 解析 provider-native payload。
- 不让 Orchestration 拥有 Context Tree 真相。
- 不让 Orchestration 拥有 Tool Source / ToolRun 生命周期。
- 不让 Orchestration 保存完整 LLM response event 流。
- 不恢复关键词联想 router。
- 不保留旧 `tool_calls empty => finish` 主路径。

## Request Side Contract

### LlmRequestEnvelope

Orchestration 向 LLM module 提交 provider-neutral request envelope：

```text
LlmRequestEnvelope
  invocation_id
  agent_id
  model_profile_id
  base_instructions
  input_items
  context_surface
  tool_surface
  reasoning_config
  output_contract
  provider_options
  metadata
```

说明：

- `base_instructions`：agent/runtime instructions，不直接混入历史消息。
- `input_items`：provider-neutral replay items，来自 Session model-visible view 和当前 execution chain protocol facts。
- `context_surface`：Context Workspace render snapshot 引用和渲染结果。
- `tool_surface`：Tool module 提供的可见工具集合、schema、runtime policy。
- `reasoning_config`：reasoning effort/summary/raw policy 等 provider capability 开关。
- `output_contract`：response format、structured output、final answer expectation。
- `provider_options`：parallel tool calls、tool choice、max output tokens、service tier、prompt cache key 等。
- `metadata`：run/turn/session/context/tool surface 关联信息。

### Input Items

Orchestration 不再只传 `role/content`，而是收集：

```text
SessionReplayItem[]
CurrentTurnProtocolItem[]
ContextAttachmentReference[]
```

由 LLM adapter 映射为目标 provider 的 request：

```text
OpenAI Responses    -> instructions + input ResponseItem[] + tools
Chat Compatible     -> messages + tools + response_format
Anthropic Messages  -> system + content blocks + tools
Gemini              -> contents + tools + generation config
```

### Context Surface

Context Workspace 提供：

```text
context_render_snapshot_id
rendered_context
included_node_ids
collapsed_node_ids
estimated_tokens
provider_attachment_mirror
tool_schema_mirror
```

Orchestration 只记录引用和交给 LLM module，不解析 Context Tree 内部状态。

### Tool Surface

Tool module 提供：

```text
tool_surface_id
tools
always_visible_tools
context_selected_tools
source_metadata
runtime_requirements
authorization_policy
parallel_tool_calls
tool_choice
```

Orchestration 可以根据 run policy 选择 surface，但不按关键词联想临时 route。

### Request Metadata

每次 invocation 必须携带：

```text
run_id
turn_id
execution_chain_id
llm_invocation_id
session_id
session_segment_id
context_render_snapshot_id
tool_surface_id
agent_id
model_profile_id
provider_family
```

metadata 主要服务 trace、cache、Operations、诊断，不是 prompt 正文。

## Response Side Contract

### Engine 消费内容

LLM invocation 完成后，Orchestration 消费：

```text
response_items
continuation_signal
derived_result_summary
```

`derived_result_summary` 只能用于摘要展示和 fallback diagnostics，不能作为 loop 主依据。

### Response Item 投影

Orchestration 写入 Session / execution chain：

| LLM response item | Orchestration action |
| --- | --- |
| `assistant_message(phase=commentary)` | 写 SessionItem commentary，记录 execution chain ref |
| `assistant_message(phase=final_answer)` | 写 SessionItem final_answer，候选完成输出 |
| `reasoning` | Responses/Codex parity 下写 SessionItem reasoning；其他 provider 按 policy 写 SessionItem 或仅记录 Trace/Operations ref |
| `tool_call` | 写 SessionItem tool_call，加入 tool execution plan |
| `tool_result` | 一般作为 provider replay fact 记录，不创建 ToolRun |
| `provider_external_item` | Responses/Codex parity 下写 SessionItem provider_external_item；其他 provider 按 policy 记录 Session/Trace/Operations ref；不创建 ToolRun |
| `unknown` | 保留 ref 和 diagnostic，不参与特殊 loop |

## Loop Decision

### 新决策输入

```text
local tool_call items
assistant final_answer items
assistant commentary items
reasoning items
provider external items
continuation_signal.end_turn
continuation_signal.needs_follow_up
continuation_signal.reason
pending tool runs
approval state
waiting state
pending user input
run cancellation
```

### 决策顺序

建议顺序：

1. 如果 run 已取消或失败，停止推进。
2. 如果存在需要 approval 的 tool call/action，进入 approval wait。
3. 如果存在 local tool_call items，创建 ToolRun 或 inline 执行。
4. 如果存在 background ToolRun pending，进入 tool wait。
5. 如果 continuation signal 明确要求 follow-up，按 reason 继续或等待。
6. 如果存在 final_answer 且无 pending work，完成 turn/run。
7. 如果只有 commentary/reasoning 且无 tool/final/continuation，按 policy 触发诊断失败或 request follow-up。

旧路径：

```text
tool_calls empty => finish
```

必须退场。

### Continuation Reason

Orchestration 至少识别：

```text
tool_call
provider_end_turn_false
tool_error_response
pending_external
approval_wait
tool_wait
user_input_required
none
unknown
```

LLM module 提供 provider-level continuation，Orchestration 叠加 runtime-level wait/recovery reason。

## Execution Chain Schema

允许破坏式调整 execution chain schema。当前落地方案不是再新增独立 `execution_item_refs` 表，而是把 execution chain 统一为：

- `orchestration_execution_chains`：turn/run 级外层链路状态。
- `orchestration_execution_steps`：LLM、tool batch、approval、continuation 等阶段。
- `orchestration_execution_step_items`：链路内最小可追溯事实，使用 `owner_kind/owner_id`、`payload_ref`、`summary_payload` 承载跨模块引用。

这样 `llm_response_item_id`、`session_item_id`、`tool_run_id`、`context_render_snapshot_id`、`continuation_decision`、`tool_execution_plan` 都进入同一条 execution item stream。Operations/Workbench 读取 execution item read model，而不是另开一套 refs 表再聚合。

```text
execution_chains
  id
  turn_id
  status
  active_step_id
  step_count
  error_payload
  created_at
  started_at
  completed_at
  updated_at

execution_steps
  id
  chain_id
  turn_id
  step_index
  kind
  status
  dispatch_task_id
  owner_kind
  owner_id
  correlation_key
  error_payload
  created_at
  started_at
  completed_at
  updated_at

execution_step_items
  id
  chain_id
  step_id
  turn_id
  item_index
  kind
  status
  owner_kind
  owner_id
  correlation_key
  source_event_id
  payload_ref
  summary_payload
  error_payload
  created_at
  completed_at
  updated_at
```

`execution_step_items` 用于连接：

```text
llm_response_item
session_item
tool_run
tool_result
context_render_snapshot
provider_external_item
```

### Continuation Decision

Continuation decision 不单独建表，作为 `ExecutionStepItem(kind=continuation_decision)` 记录：

```text
execution_step_items.summary_payload
  id
  chain_id
  step_id
  llm_invocation_id
  end_turn
  needs_follow_up
  provider_reason
  orchestration_reason
  decided_action
  pending_tool_run_ids
  final_answer_session_item_ids
  diagnostic_payload
  created_at
```

这能解释 Workbench 上“为什么继续/为什么停”。

## Session 写入策略

Orchestration 负责把 LLM response items 和 ToolRun 结果投影为 SessionItems：

```text
LLM assistant_message -> SessionItem assistant_message
LLM reasoning         -> SessionItem reasoning for Responses/Codex parity; otherwise policy/trace-only
LLM tool_call         -> SessionItem tool_call
ToolRun result        -> SessionItem tool_result
Provider external     -> SessionItem provider_external_item for Responses/Codex parity; otherwise policy/trace-only
```

写入时必须带：

```text
source_module
source_kind
source_id
provider_item_id
call_id
tool_name
visibility flags
```

## Tool Execution Plan

从 response item 派生：

```text
ToolExecutionPlan
  tool_call_id
  tool_name
  tool_id
  mode
  strategy
  environment
  resource_policy
  arguments_digest
```

Orchestration 只对 CRXZipple local/runtime tools 创建 ToolRun。provider-hosted item 只作为 LLM response fact。
Execution chain summary 只记录执行计划摘要和 `arguments_digest`，不复制 raw arguments；raw request/response 事实仍归 LLM/Session/Tool owner module。

## Operations / Workbench 配合

Orchestration 发布或提供 query facts：

- execution chain steps。
- llm invocation refs。
- llm response item refs。
- session item refs。
- tool run refs。
- continuation decisions。
- wait/recovery reasons。

Operations 聚合这些 facts，生成 Workbench timeline。Workbench 不直接访问 Orchestration 内部表拼接 owner module raw data。

## 退场项

必须退场或降级：

- `LlmResult.tool_calls` 作为 tool execution 主入口。
- `LlmResult.text` 作为 assistant progress/final answer 主入口。
- `tool_calls empty => finish`。
- Orchestration 直接拼 provider-native messages。
- 关键词联想 tool router。
- function_call session message 被当作 progress。
- provider external item 创建 ToolRun。
- 不得让旧 execution item summary 作为 Workbench 主来源。
- 不得为旧 run/execution/session 数据保留兼容 shim。

## Checklist

### Domain / Value Objects

- [x] 定义 `LlmRequestEnvelope` orchestration-facing DTO。
- [x] 定义 `ContextSurface`。
- [x] 定义 `ToolSurface`。
- [x] 定义 `ToolExecutionPlan`。
- [x] 定义 `ContinuationDecision`。
- [x] 定义 execution item owner refs。

### Request Builder

- [x] 从 Session 获取 model-visible replay items。
- [x] 从 Context Workspace 获取 render snapshot/context surface。
- [x] 从 Tool module resolved tools 构建 request-side ToolSurface。
- [x] 保存 request-time ToolSurface snapshot，并按 provider-visible tool ids 收敛。
- [x] 组装 run-level reasoning config。
- [x] 组装 run-level output contract。
- [x] 组装 run-level provider options。
- [x] 写入 request metadata。
- [x] Orchestration 不直接构造 provider-native request。

### Response Consumer

- [x] 读取 LLM response items。
- [x] 读取 LLM continuation signal。
- [x] 从 `tool_call` response item 派生 ToolExecutionPlan。
- [x] 从 `assistant_message` item 写 SessionItem。
- [x] 从 `reasoning` item 按 policy 写 Session/Trace。
- [x] 从 provider external item 写 ref，不创建 ToolRun。
- [x] Tool execution 不再从 no-response-item `LlmResult.tool_calls` fallback 派生，只从 `LlmResponseItem(kind=tool_call)` 派生。
- [x] inbound user input 由 session recorder 写入 `SessionItem(kind=user_message)`，不再生成旧 `user_message_id`。
- [x] 无 `LlmResponseItem` 的 assistant final fallback 写入 `SessionItem(kind=assistant_message)`，不再生成旧 assistant message。
- [x] tool_call/tool_result recorder 返回 SessionItem refs，并进入 Engine outcome `session_item_ids`。
- [x] LLM invocation 带 response items 时，`LlmResult` summary 已由 LLM module 从 response items 归一化派生。
- [x] `LlmResult` 在 Orchestration loop 内只作为 summary / legacy text-only final fallback，不再作为 tool execution 主入口。

### Loop Governance

- [x] 不再以 `tool_calls empty` 作为唯一终止依据。
- [x] 实现 continuation decision execution item。
- [x] 识别 `end_turn=false`。
- [x] 识别 pending tool wait。
- [x] 识别 approval wait。
- [x] Approval replay recovery 通过 SessionItem tool_result refs 恢复，新 recovery contract 不再生成 `tool_result_message_ids`。
- [x] Approval resolution side effect 写入 `SessionItem(kind=tool_result)`，不再写旧 `SessionMessage(kind=tool_result)`。
- [x] 识别 final answer + no pending work 完成。
- [x] 仅 commentary/reasoning 无 follow-up 时产生 diagnostic。
- [x] commentary/reasoning-only terminal diagnostic 进入失败 LLM execution item，供 Workbench/Trace 观测。

### Execution Chain

- [x] 破坏式调整 execution chain schema。
- [x] 记录 llm_response_item refs。
- [x] 记录 session_item refs。
- [x] 记录 tool_run refs。
- [x] 记录 tool_execution_plan summary。
- [x] 记录 context_render_snapshot refs。
- [x] 记录 continuation decision。
- [x] 记录 terminal loop diagnostic summary。
- [x] Query service 可按 run/turn 返回完整 chain。

### Operations Integration

- [x] 发布/暴露 execution item refs。
- [x] 发布/暴露 continuation decision execution item。
- [x] Execution chain summary 可解释 tool call 执行计划来源。
- [x] Workbench read model 可解释 tool call 执行计划来源。
- [x] Workbench read model 可解释 run 继续/终止原因。
- [x] Workbench step view 可展示 terminal loop diagnostic。

### Verification

- [x] request envelope 包含 session replay/context/tool surface/metadata。
- [x] assistant/tool_call -> ToolRun -> tool_result -> next invocation 正常推进。
- [x] final_answer + end_turn + no pending work 完成 run。
- [x] end_turn=false 且无 tool_call 时不会误完成。
- [x] provider external item 不创建 ToolRun。
- [x] tool_call/tool_result call_id 完整。
- [x] approval replay recovery 可通过 SessionItem call_id 找回 tool_result，旧 session message lookup 已退场。
- [x] approval resolution 可通过 SessionItem 记录 approval_request tool_result。
- [x] response item tool_call provider replay 保持 assistant/tool protocol pair。
- [x] response item tool_call 可驱动 inline tool loop。
- [x] current inbound user 的 `session_item_id` 进入 context render snapshot 和 provider request metadata。
- [x] 当前 turn response item tool_call/tool_result 的 `session_item_ids` 进入 outcome，可被 execution payload 和 downstream read model 追溯。
- [x] 清库重建后 orchestration 单测和关键集成测试通过：Orchestration context/memory/approval/execution chain/compaction/provider request + Prompt input/transcript 组合共 106 个测试通过。

## 施工状态 2026-06-11

- Engine 已优先读取 `invocation.response_items` 中的 `tool_call`，并转换为 `ToolCallIntent` 交给 Tool module 执行。
- Engine 已读取 `invocation.continuation`，当 `needs_follow_up=true` 时保持 loop 打开；`end_turn=false` 且无 tool call 不再误判为完成。
- Execution payload / result payload 已记录 `llm_continuation_reason`、`llm_continuation_end_turn` 和 follow-up 标记。
- Engine outcome / execution payload / event payload 已记录 `llm_response_item_ids`，progress/waiting coordinator 会把这些 refs 写入 LLM execution item summary。
- Engine execution payload / event payload 已记录 `context_render_snapshot_id`，execution chain summary 和 Workbench timeline trace/source refs 可追溯本轮 LLM 使用的 Context Snapshot。
- Execution chain 已新增 `CONTINUATION_DECISION` item，owner 为 `llm_continuation:{invocation_id}:continuation`，summary 记录 reason/end_turn/needs_follow_up。
- `ContinuationDecision` 已定义为 orchestration domain value object，execution chain continuation item summary 由该 value object 生成。
- `ExecutionOwnerKind` 与 `ExecutionOwnerReference` factory 已定义，后续新增 execution item owner refs 不再散落裸字符串。
- `OrchestrationRunQueryService.list_execution_chain_snapshots(turn_id)` 已提供 chain -> steps -> items 的完整 read snapshot。
- Engine preview 与真实 invoke 已统一从 `LlmRequestEnvelope` 读取 messages、tool schemas、request metadata、provider options 和 output contract；run metadata 的 `llm_request_options` 已可进入 `reasoning_config`、`output_contract` 和 `provider_options`。
- Auto LLM routing 已从 model-visible SessionItem content blocks 扫描 image/file refs；历史附件即使不再进入 direct transcript，也能触发 image/document routing 策略。
- Effective LLM request policy resolver 已接入 Engine preview/真实 invoke；request options 现在由 model defaults/capabilities + run override 合成，并把 `llm_request_policy.resolution_trace` 写入 request metadata。
- Engine 真实 invoke 已通过 Tool module `build_tool_surface(persist=True)` 保存 request-time ToolSurface snapshot；snapshot 使用 `tool_surface:{context_render_snapshot_id}:{unique}`，并在 metadata 保留 base id；同时按 Context Workspace 镜像后的 provider-visible tool ids 过滤，避免持久化全集与模型可见面不一致。Preview 仍只构造 envelope，不写 owner truth。
- Tool execution context 已携带 `tool_surface_id` / `tool_surface_snapshot_id` / `context_render_snapshot_id`，`ExecuteToolInput.tool_surface_id` 不再只依赖 metadata fallback；ToolRun 一等字段可关联回同一轮 request-time ToolSurface snapshot。
- Tool execution 已使用 request envelope 中的 ToolSurface function refs 校验 `tool_call` 可见性和 tool id 一致性；越界调用会失败为 `tool_surface_not_visible`，surface/ref 不一致会失败为 `tool_surface_mismatch`。
- Session recorder 已优先使用 `ToolRun.result_envelope_payload` 投影 `SessionItem(kind=tool_result)`；provider replay 内容来自 envelope 的 `model_visible_payload`，同时保留 user/trace payload、artifact/read handle refs 和完整 envelope metadata。
- LLM module 已在非流式 invoke/test/invoke_async 路径，以及 streaming completed event 带 `response_items` 的路径，把 response items 归一化为 derived `LlmResult` summary；Orchestration 读取到的 item-aware `invocation.result` 不再由 adapter 原始 `result.text/tool_calls` 覆盖。
- Workbench timeline source refs 和 Trace linked entities 已暴露 `execution_item_id`。
- Session recorder 已把 inbound user input 改为 item-only 写入，返回 `user_session_item_id`；provider request metadata 已优先用 `current_inbound_session_item_id` 定位当前用户输入。
- Legacy adapter 仅返回 `LlmResult.text/structured_output` 且没有 response items 时，Engine 现在把 assistant final fallback 记录为 SessionItem，并把 id 并入 outcome `session_item_ids`。
- Provider external response item 已验证只写入 LLM/Session fact，不创建 CRXZipple ToolRun。
- Final answer response item + `end_turn=true` + no pending work 已验证会完成 run，不进入工具循环。
- 明确 `assistant_message(commentary)` / `reasoning` only 且无 tool/final/provider external/follow-up continuation 的 terminal response 会失败为 `llm_incomplete_terminal_response`，并在 execution payload 与失败 LLM execution item summary 写入 `llm_loop_diagnostic`。
- Tool executor 已从 recorder 获取 tool_call/tool_result 的 `SessionItem` refs；Engine 会把这些 refs 合并到当前 advance outcome 的 `session_item_ids`。
- Tool executor 已定义 `ToolExecutionPlan`，并把 plan 摘要写入 ToolRun metadata、Engine outcome 和 `tool_run_links`；plan 摘要已携带 `tool_surface_id`，可从 execution chain 直接追溯本轮 request-time ToolSurface。
- Execution chain tool result item 已优先使用 `result_session_item_id` 作为 owner，并在 summary/payload ref 中保留 SessionItem refs。
- Execution chain tool run/result summary 已透传 `tool_execution_plan`，供 Operations/Workbench 后续解释 tool call 调度来源。
- Workbench 现有 step view 已投影 continuation decision，可展示 reason、end_turn、follow_up，并追溯到 LLM invocation。
- 旧 no-response-item `LlmResult.text/structured_output` 仅作为 assistant final summary fallback；`LlmResult.tool_calls` 已不再驱动 ToolRun 创建。
- SessionItem prompt replay 的 budget 已支持单个超长 item 裁剪，`memory_flush` 不会因为单条历史 assistant item 过长而把完整旧内容塞回模型。
- 已补充单测覆盖普通 inline tool loop、response item tool loop、provider continuation follow-up、continuation decision item 物化，以及 approval replay/resolution 的 SessionItem refs。
- `LlmRequestEnvelope` / `ContextSurface` / `ToolSurface` orchestration-facing snapshot 已定义并有单测覆盖；Engine preview/真实 invoke 已统一消费 request envelope，run-level `llm_request_options` 可贯通 reasoning/output/provider options；effective policy resolver 已合成 Settings runtime defaults + model defaults/capabilities + Agent LLM policy + run override，并写入 request metadata resolution trace；Settings `llm_request_defaults` 已由 assembly 注入 `RunPromptInput.runtime_llm_defaults`；Agent Profile `llm_policy` 已从 settings/home/http/CLI sync 进入 `RunPromptInput`，并可驱动 reasoning summary、final answer/tool use、parallel tool calls request options；LLM Operations invocation detail 已展示 policy resolution trace；request-time ToolSurface snapshot 已通过 Tool module 保存，并和 provider-visible tool ids 对齐；tool_call response item 已受 request ToolSurface function refs 校验；ToolRun result envelope 已投影为 Session tool_result；`ToolExecutionPlan` 已进入 tool outcome、execution chain summary 和 Workbench timeline content；`llm_response_item_ids` 与 `context_render_snapshot_id` 已进入 LLM execution item summary 和 Workbench trace/source refs；`ContinuationDecision` value object 已接入 execution chain；`ExecutionOwnerKind` / owner ref factories 已定义；Query service 已可按 turn 返回完整 chain snapshot；commentary/reasoning-only terminal response 已有 `llm_loop_diagnostic`、失败保护和 Workbench step 诊断展示。当前主要剩余是最终清库回归。
