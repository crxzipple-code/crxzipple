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

允许破坏式调整 execution chain schema。建议新增：

```text
execution_chains
  id
  run_id
  turn_id
  status
  created_at
  completed_at

execution_steps
  id
  chain_id
  sequence_no
  kind
  status
  llm_invocation_id
  tool_run_id
  session_item_id
  continuation_decision_id
  metadata
  created_at
  completed_at

execution_item_refs
  id
  chain_id
  step_id
  sequence_no
  owner_module
  owner_kind
  owner_id
  role
  call_id
  tool_name
  metadata
```

`execution_item_refs` 用于连接：

```text
llm_response_item
session_item
tool_run
tool_result
context_render_snapshot
provider_external_item
```

### Continuation Decision

建议记录：

```text
continuation_decisions
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
  llm_response_item_id
  call_id
  tool_name
  arguments
  source_metadata
  runtime_requirements
  authorization_context
  execution_mode
```

Orchestration 只对 CRXZipple local/runtime tools 创建 ToolRun。provider-hosted item 只作为 LLM response fact。

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

- [ ] 定义 `LlmRequestEnvelope` orchestration-facing DTO。
- [ ] 定义 `ContextSurface`。
- [ ] 定义 `ToolSurface`。
- [ ] 定义 `ToolExecutionPlan`。
- [ ] 定义 `ContinuationDecision`。
- [ ] 定义 execution item owner refs。

### Request Builder

- [ ] 从 Session 获取 model-visible replay items。
- [ ] 从 Context Workspace 获取 render snapshot/context surface。
- [ ] 从 Tool module 获取 tool surface。
- [ ] 组装 reasoning config。
- [ ] 组装 output contract。
- [ ] 组装 provider options。
- [ ] 写入 request metadata。
- [ ] Orchestration 不直接构造 provider-native request。

### Response Consumer

- [ ] 读取 LLM response items。
- [ ] 读取 LLM continuation signal。
- [ ] 从 `tool_call` response item 派生 ToolExecutionPlan。
- [ ] 从 `assistant_message` item 写 SessionItem。
- [ ] 从 `reasoning` item 按 policy 写 Session/Trace。
- [ ] 从 provider external item 写 ref，不创建 ToolRun。
- [ ] `LlmResult` 只作为 summary。

### Loop Governance

- [ ] 移除 `tool_calls empty => finish` 主路径。
- [ ] 实现 continuation decision。
- [ ] 识别 `end_turn=false`。
- [ ] 识别 pending tool wait。
- [ ] 识别 approval wait。
- [ ] 识别 final answer + no pending work 完成。
- [ ] 仅 commentary/reasoning 无 follow-up 时产生 diagnostic。

### Execution Chain

- [ ] 破坏式调整 execution chain schema。
- [ ] 记录 llm_response_item refs。
- [ ] 记录 session_item refs。
- [ ] 记录 tool_run refs。
- [ ] 记录 context_render_snapshot refs。
- [ ] 记录 continuation decision。
- [ ] Query service 可按 run/turn 返回完整 chain。

### Operations Integration

- [ ] 发布/暴露 execution item refs。
- [ ] 发布/暴露 continuation decision。
- [ ] Workbench read model 可解释 tool call 来源。
- [ ] Workbench read model 可解释 run 继续/终止原因。

### Verification

- [ ] request envelope 包含 session replay/context/tool surface/metadata。
- [ ] assistant commentary + tool_call -> ToolRun -> tool_result -> next invocation 正常推进。
- [ ] final_answer + end_turn + no pending work 完成 run。
- [ ] end_turn=false 且无 tool_call 时不会误完成。
- [ ] provider external item 不创建 ToolRun。
- [ ] tool_call/tool_result call_id 完整。
- [ ] 清库重建后 orchestration 单测和关键集成测试通过。
