# Workbench Agent Timeline Read Model Plan 2026-06-11

本文记录 LLM response item contract 升级后 Workbench 的目标数据路径：Workbench 不直接多路读取 Session / LLM / Tool / Orchestration，而是继续消费 Operations 聚合 read model。

关联文档：

- [provider-neutral-llm-response-stream-contract-plan-20260611.md](provider-neutral-llm-response-stream-contract-plan-20260611.md)
- [orchestration-llm-contract-driven-runtime-plan-20260611.md](orchestration-llm-contract-driven-runtime-plan-20260611.md)
- [session-module-response-item-migration-plan-20260611.md](session-module-response-item-migration-plan-20260611.md)
- [context-workspace-llm-request-surface-plan-20260611.md](context-workspace-llm-request-surface-plan-20260611.md)
- [tool-surface-llm-request-contract-plan-20260611.md](tool-surface-llm-request-contract-plan-20260611.md)
- [operations-agent-runtime-projection-plan-20260611.md](operations-agent-runtime-projection-plan-20260611.md)
- [assistant-progress-session-context-convergence-plan-20260611.md](assistant-progress-session-context-convergence-plan-20260611.md)
- [../ui/runtime-ui-read-model-contracts.md](../ui/runtime-ui-read-model-contracts.md)
- [../operations-data-truth-audit.md](../operations-data-truth-audit.md)

## Cutover Assumption

开发前会清除并重建数据库。本计划不考虑旧 Operations projection、旧 Workbench fixture、旧 `LlmResult.text/tool_calls` timeline 或旧 fallback 文案兼容。

如果旧 read model 不能表达新的 agent loop，应直接替换 read model contract。

## 施工进展 2026-06-12

- Workbench/Trace/UI HTTP 测试已切到 `session_item_id` / `llm_response_item_id` / execution item refs，不再期待 `session_message_id` 或 `*_message_ids` 字段。
- Daemon Operations 测试已对齐 read model 边界：页面 GET 不驱动 runtime refresh，缺失 process session 通过 materialized process row 表达。
- Tool Operations 测试已对齐 projection/observation 边界：页面展示已物化 lifecycle，不从 UI 测试直接依赖裸 event bus 即时读取。
- Workbench 主时间线隐藏无动作 continuation 决策，例如 `reason=none` 且 `follow_up=false`；这类事实仍保留在 steps/trace，用于调试，不作为用户可见进展。

## 定位

Workbench 是 agent runtime 的操作台，不是 owner module raw entity viewer。它展示的是“当前 turn/run 如何推进”，而不是某一张业务表。

目标数据流：

```text
LLM module truth
Tool module truth
Session module truth
Orchestration execution truth
Events
        -> Operations observer / query aggregation
        -> WorkbenchRunReadModel
        -> frontend Workbench
```

前端 Workbench 不允许直接绕过 Operations 去拼：

```text
/sessions
/llms
/tools
/orchestration
```

这些模块可以提供 query service，但页面级组合由 Operations / UI read model 层完成。

## 当前问题

### 1. Timeline 过度依赖旧 summary

旧 Workbench 容易从以下字段生成 timeline：

```text
llm.result_payload.text
llm.result_payload.tool_calls
execution_item.summary_payload
session_item.content_payload
```

这些字段无法表达 reasoning summary、assistant phase、provider external item、tool argument delta、end_turn 等现代 response 能力。

### 2. 兜底文案掩盖真实缺口

类似：

```text
Assistant progress message recorded.
```

这种文案会让 UI 看起来有进展，但没有展示模型真实输出。新方案中没有真实 content 就不展示自然语言 progress。

### 3. Session 和 Workbench 时间线不能一一镜像

Session item 是会话事实流。Workbench timeline 是 agent execution projection。

例如：

- `tool_call` 是 model-visible，但不应作为聊天气泡展示。
- `assistant commentary` 用户可见，但应展示在 agent progress，不一定进入 chat area。
- `reasoning summary` 可用于 trace/progress，但通常不作为聊天消息。

### 4. 多 owner 事实需要单 read model 聚合

LLM、Tool、Session、Orchestration 各自拥有 truth 是正确的。问题不在多 owner，而在 Workbench 不能直接消费多个 owner API 自己拼 truth。

## 目标

### 必须达成

1. Workbench 只消费 Operations/UI 层 Workbench read model。
2. Workbench timeline item 从 LLM response items、Session items、ToolRuns、ExecutionChain 统一投影。
3. `assistant_message(phase=commentary)` 展示为 Agent progress。
4. `assistant_message(phase=final_answer)` 展示为最终回复/回答区域。
5. `reasoning` 展示为可折叠 reasoning summary / trace clue，不冒充 assistant text。
6. `tool_call` 和 ToolRun/result 成对展示，保留 call_id/tool_name。
7. provider external item 单独展示，不创建 ToolRun。
8. 没有真实文本时不显示自然语言兜底。
9. 清库重建后不保旧 projection 结构。

### 非目标

- 不让前端直接读取模块 API 拼 timeline。
- 不把 Session item 流直接当 Workbench timeline。
- 不展示 raw reasoning，除非未来有明确权限和 policy。
- 不为旧 execution item summary 保留兼容渲染。
- 不把 provider-hosted web/image item 当 CRXZipple local tool run。

## Workbench Timeline Contract

建议新增统一 timeline item：

```text
WorkbenchTimelineItem
  id
  run_id
  turn_id
  step_id
  sequence_no
  kind
  title
  status
  content
  phase
  visibility
  source_refs
  trace
  timestamps
  children
```

### Kind

```text
user_input
assistant_commentary
assistant_final_answer
reasoning_summary
llm_invocation
tool_call
tool_run
tool_result
provider_external_item
continuation
approval
wait_state
error
system_event
```

### Source Refs

每个 timeline item 必须可追溯来源：

```text
source_refs:
  llm_invocation_id
  llm_response_item_id
  session_item_id
  tool_run_id
  orchestration_run_id
  execution_step_id
  event_id
  call_id
```

Workbench 可以点击跳转 Trace/Inspector，但不直接拿这些 id 再请求 owner module raw API 拼页面。

## 投影规则

### User Input

来源：

```text
SessionItem(kind=user_message)
Orchestration turn intake
```

展示：

```text
kind=user_input
chat_visible=true
```

### Assistant Commentary

来源：

```text
LlmResponseItem(kind=assistant_message, phase=commentary|unknown)
SessionItem(kind=assistant_message, phase=commentary|unknown)
```

展示：

```text
kind=assistant_commentary
title=Agent progress
content=<真实模型文本>
```

规则：

- content 为空则不展示。
- 不显示兜底自然语言。
- phase unknown 但同轮有 tool_call 时，Workbench 可展示为 `assistant_commentary`，但不得改写原始 response item / session item 的 `phase=unknown`。

### Assistant Final Answer

来源：

```text
LlmResponseItem(kind=assistant_message, phase=final_answer)
SessionItem(kind=assistant_message, phase=final_answer)
```

展示：

```text
kind=assistant_final_answer
```

规则：

- final answer 是用户答复区域的主内容。
- 不由“没有 tool_call”自动推断，必须结合 LLM phase / Orchestration finalization。

### Reasoning Summary

来源：

```text
LlmResponseItem(kind=reasoning)
LlmResponseEvent(type=reasoning_summary_delta)
```

展示：

```text
kind=reasoning_summary
collapsed=true
```

规则：

- 只展示 summary，不展示 raw reasoning。
- 对齐 Codex parity：reasoning summary 默认用户可见并折叠展示。
- raw reasoning 默认不展示；只有显式 debug/raw reasoning policy 允许时才进入受控 Trace/UI。

### Tool Call / Tool Run / Tool Result

来源：

```text
LlmResponseItem(kind=tool_call)
Orchestration execution plan
ToolRun
SessionItem(kind=tool_result)
```

展示：

```text
tool_call
  -> tool_run
  -> tool_result
```

规则：

- call_id 是关联主键之一。
- tool_name 必须显示。
- arguments/result 可折叠。
- tool_result 优先使用 `result_session_item_id` / `session_item` owner 作为 source ref；`result_message_id` 只作为辅助追溯字段。
- ToolRun status 以 Tool module truth 为准。

### Provider External Item

来源：

```text
LlmResponseItem(kind=provider_external_item)
```

展示：

```text
kind=provider_external_item
title=<provider item type>
```

规则：

- 不创建 ToolRun。
- 不混入 local tool timeline。
- 可进入 Trace/Inspector。

### Continuation

来源：

```text
LlmContinuationSignal
Orchestration loop decision
```

展示：

```text
kind=continuation
status=continued|ended|waiting
```

规则：

- `end_turn=false`、`needs_follow_up`、pending tool、approval wait 都要可诊断。
- 不再用 `tool_calls empty` 作为 UI 上的终止解释。

## Operations 聚合职责

Operations read model builder 负责：

- 读取 Orchestration execution chain。
- 关联 LLM invocation 和 response items。
- 关联 Session items。
- 关联 ToolRuns。
- 关联 Events trace。
- 生成 Workbench timeline。
- 对缺失 source ref 给出结构化 diagnostic，而不是编造 progress 文案。

建议 read model：

```text
WorkbenchRunReadModel
  run
  turns
  current_turn_id
  timeline
  steps
  status_strip
  inspector
  linked_entities
  actions
```

`steps` 可以保留给结构化执行链；`timeline` 专门服务用户阅读 agent 进展。
timeline 投影诊断进入 `inspector.debug.timeline_diagnostics`，不另开顶层数据源。

## 前端调整

### 需要删除/退化

- 删除 `Assistant progress message recorded.` 兜底。
- 删除从 function_call payload 生成自然语言 progress。
- 删除对旧 `llm.result_payload.text/tool_calls` 的主路径依赖。
- 删除前端跨模块拼 timeline 的尝试。

### 需要新增

- Timeline item renderer。
- Assistant commentary renderer。
- Final answer renderer。
- Reasoning summary collapsed renderer。
- Tool call/run/result grouped renderer。
- Provider external item renderer。
- Continuation diagnostic renderer。

所有固定文案进入 i18n。

## API Contract 草案

```json
{
  "run": {},
  "turns": [],
  "current_turn_id": "turn_...",
  "timeline": [
    {
      "id": "timeline_...",
      "kind": "assistant_commentary",
      "title": "Agent progress",
      "status": "completed",
      "content": {
        "text": "我先检查页面状态。"
      },
      "phase": "commentary",
      "source_refs": {
        "llm_invocation_id": "...",
        "llm_response_item_id": "...",
        "session_item_id": "..."
      },
      "trace": {}
    }
  ],
  "diagnostics": []
}
```

diagnostic 示例：

```json
{
  "code": "missing_session_projection",
  "severity": "warning",
  "message": "LLM assistant_message item has no linked session item",
  "source_refs": {
    "llm_response_item_id": "..."
  }
}
```

## 退场项

必须退场或降级：

- 不得让 Workbench 直接消费 owner module raw API。
- 不得让 `LlmResult.text` 作为 timeline 主来源。
- 不得让 `LlmResult.tool_calls` 作为 tool timeline 主来源。
- 不得保留 execution item fallback text。
- 不得假设 session item == timeline item。
- 不得让 function_call message 伪装成 assistant progress。
- 不得让 provider external item 伪装成 local ToolRun。
- 不得保留旧 Operations projection schema。

## Checklist

### Operations Read Model

- [x] 定义 `WorkbenchTimelineItem`。
- [x] 定义 timeline `kind` 枚举。
- [x] 定义 `source_refs`。
- [x] 聚合 LLM response items。
- [x] 聚合 SessionItem source refs。
- [x] 聚合 ToolRuns。
- [x] 聚合 tool execution plan summary。
- [x] 聚合 context render snapshot source refs。
- [x] 聚合 Orchestration continuation decision。
- [x] 输出 diagnostics。

### Backend API

- [x] 更新 Workbench run DTO，补充 `continuation_decision` step type。
- [x] 现有 Workbench run API 返回 timeline。
- [x] Trace inspector 支持 response item/source refs linked entities。
- [x] Workbench linked entity detail API 支持 `session_item` / `llm_response_item`，旧 `session_message` detail surface 已退场。
- [x] Trace link 可打开 `llm_response_item_id` detail。

### Frontend

- [x] 更新 runtime contracts/types，补充 `continuation_decision`。
- [x] 更新 Workbench API client，补充 linked entity detail loader。
- [x] 更新 Workbench step renderer，展示 continuation decision。
- [x] Workbench Step inspector 支持 `session_item` / `llm_response_item_id` linked entity 内联详情。
- [x] Trace inspector 支持 `session_item` / `llm_response_item_id` linked entity 内联详情。
- [x] Workbench timeline renderer 消费后端 `run.timeline`。
- [x] 实现 assistant commentary 基础展示。
- [x] 实现 final answer 基础展示。
- [x] 实现 reasoning summary 基础折叠展示。
- [x] 实现 tool call/run/result 基础展示。
- [x] 实现 provider external item 基础展示。
- [x] 移除 progress 兜底文案。
- [x] i18n 补齐 timeline 基础文案。

### Verification

- [x] 用户输入单轮最终答复可展示。
- [x] commentary + tool_call + tool_result + final_answer 链路可展示。
- [x] reasoning summary 进入 timeline 基础展示。
- [x] reasoning summary 存在时默认折叠展示。
- [x] explicit policy 禁止 reasoning 正文时隐藏正文并展示 presence/count。
- [x] provider external item 不生成 ToolRun。
- [x] tool_call 和 tool_result 通过 call_id 正确分组。
- [x] tool_result timeline 优先暴露 `session_item_id` source ref。
- [x] tool_run/tool_result timeline 暴露 `tool_execution_plan` summary。
- [x] timeline trace/source refs 暴露 `context_render_snapshot_id`。
- [x] source_refs 可进入 Trace linked entities。
- [x] LLM step 可展示 terminal loop diagnostic badge 和 summary。
- [x] 没有真实 content 时不展示假 progress。
- [x] 清库重建后 Workbench / Operations UI HTTP fixture 通过：`test_ui_http.py`、`test_ui_operations_orchestration_http.py`、`test_operations_llm_read_model.py`、`test_operations_observation.py` 共 93 个测试通过。
- [x] Workbench frontend build 通过。
- [x] Workbench typecheck 通过。

## 施工状态 2026-06-11

- Workbench 现有 step view 已能从 execution chain item 投影 `continuation_decision`。
- Workbench LLM step view 已能从失败 LLM execution item summary 投影 `llm_loop_diagnostic`，展示 `Loop diagnostic` badge 和诊断摘要。
- `WorkbenchRunView` 已新增 `timeline`，HTTP DTO 和前端 runtime type 已同步。
- 初始 timeline item 包含 `id/kind/status/title/content/phase/source_refs/trace`，并由 Workbench read model 从可信 execution projection 生成。
- LLM invocation 存在 `response_items` 时，timeline 会优先展开 provider item stream，输出 assistant commentary、tool call、reasoning、provider external、final answer 等 item kind；没有 response items 时才退回 LLM step 摘要。单测已覆盖 provider external item 不生成 ToolRun timeline。
- Workbench final-only 单测已覆盖 `user_input -> final_answer` 最小闭环，最终答复来自 LLM response item，不依赖旧 final step fallback。
- 空 assistant response item 不再生成 `Agent Progress` 假内容；Workbench 只展示有真实文本、payload 或结构意义的 response item。
- Assistant progress timeline 已使用 `session_item_id` source ref 和 TraceContext，不再暴露旧 `session_message_id` fallback。
- Assistant progress step view 没有真实 `assistant_progress_text` 或 SessionItem 文本时不生成 timeline 行。
- Workbench timeline read model 已修复 response item 显示污染：空 `reasoning` item 不再生成可见 timeline 行；LLM response item 已提供 `final_answer` 时，不再追加 legacy `final_response` step 造成重复回复；LLM step diagnostics 只统计 `message_kind=assistant_progress` 的 SessionItem，不再把 reasoning/final answer item 误报为 progress。
- continuation decision step 展示 reason、end_turn、follow_up，并保留 `llm_invocation_id` / `trace_step_id` 追溯信息。
- ToolRun timeline 已从 execution tool item / step view 投影，保留 `tool_run_id`、`execution_step_id` 和 `execution_item_id` source refs。
- Tool lifecycle timeline 已从 execution `TOOL_CALL` / `TOOL_RUN` / `TOOL_RESULT` items 拆成三段，分别保留 `tool_call_id`、`tool_run_id`、`session_item_id` 等 source refs；tool result 已优先消费显式 `result_session_item_id`，不再从旧 message ref 推断主定位。
- Tool run/result timeline content 已暴露 `tool_execution_plan` summary，用于解释 tool call 的 mode/strategy/environment/resource policy 和 arguments digest。
- Timeline trace/source refs 已透出 `context_render_snapshot_id`，可以追溯本轮模型实际使用的 Context Snapshot。
- Trace read model 已识别 timeline 使用的主要 source refs，并在 Trace linked entities 中输出。
- 前端 Workbench 已补充 `continuation_decision` 类型、图标和视觉 tone。
- 前端 Workbench 时间线已开始优先消费后端 `run.timeline`，并把 assistant commentary、final answer、tool lifecycle、reasoning/provider external 等 timeline item 映射到现有 step card 视觉层；缺少 timeline 时才退回旧 steps。
- Reasoning summary timeline item 已标记 `Reasoning Summary` badge，默认只展示摘要文本，response/provider/session refs 进入折叠详情面板；provider external item 已标记 `Provider Item` badge。
- `user_visible=false` 的 reasoning item 会保留 timeline presence/count，但不会把正文或原始 payload 暴露给 Workbench。
- Frontend `npm run build` 已通过；清库重建后 Workbench / Operations UI HTTP fixture 已通过。
- Workbench/Trace Context snapshot 卡片已展示 render snapshot 一等 refs 的 included/collapsed/protocol 计数和 protocol refs 预览。
- `session_item_id` 已进入 `TraceContext`、Trace linked entities 和 Workbench timeline `source_refs`，owner detail drilldown 具备稳定定位字段。
- Workbench linked entity detail API 已支持 `session_item` / `llm_response_item`，旧 `session_message` detail surface 已从当前主路径退场；Workbench Step inspector 和 Trace inspector 内联详情已接入。
- 当前落地范围完成了 timeline contract 外壳、LLM response item 聚合、SessionItem source refs、SessionItem replay 可见性、Tool call/run/result 三段生命周期、Trace source refs、continuation 基础投影、Context snapshot refs 观察入口，以及 Session/LLM owner detail 读取/展示入口。
