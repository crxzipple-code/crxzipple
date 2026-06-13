# Operations Agent Runtime Projection Plan 2026-06-11

本文记录 LLM contract 升级后 Operations module 的投影目标：把 LLM response items/events、Session items、Orchestration execution refs、ToolRuns 和 Events trace 聚合为 Workbench / Trace / LLM Operations 的单一 read model。

关联文档：

- [provider-neutral-llm-response-stream-contract-plan-20260611.md](provider-neutral-llm-response-stream-contract-plan-20260611.md)
- [orchestration-llm-contract-driven-runtime-plan-20260611.md](orchestration-llm-contract-driven-runtime-plan-20260611.md)
- [session-module-response-item-migration-plan-20260611.md](session-module-response-item-migration-plan-20260611.md)
- [workbench-agent-timeline-read-model-plan-20260611.md](workbench-agent-timeline-read-model-plan-20260611.md)
- [../operations-data-truth-audit.md](../operations-data-truth-audit.md)
- [../ui/runtime-ui-read-model-contracts.md](../ui/runtime-ui-read-model-contracts.md)

## Cutover Assumption

开发前会清除并重建数据库。本计划不考虑旧 `operations_projections`、旧 observed event payload、旧 Workbench fixture、旧 LLM read model 或旧 Trace inspector 兼容。

Operations projection schema 可以破坏式重建。HTTP/read model/前端类型应跟随新投影，而不是保留旧 projection 解释层。

## 定位

Operations 是观察和运维聚合面，不拥有业务真相。它通过 owner module query service、events 和 projection store 聚合页面级 read model。

新 runtime projection 目标：

```text
LLM response items/events/continuation
Session items
Orchestration execution chains/continuation decisions
ToolRuns/result envelopes
Events trace
        -> Operations observer/materializer
        -> WorkbenchRunReadModel / TraceTimelineReadModel / LlmOperationsReadModel
        -> frontend
```

前端仍只消费 `/operations/*` 或 `/ui/*` 页面 read model，不直接跨模块拼 truth。

## 必须达成

1. Operations 能读取并投影 LLM response items/events/continuation。
2. Workbench timeline 从 projection 生成，不从前端多路聚合。
3. Trace inspector 可定位 `llm_response_item_id`、`session_item_id`、`tool_run_id`、`continuation_decision_id`。
4. LLM Operations 页面可展示 response item lifecycle、reasoning summary presence、message phase、end_turn、tool argument delta 统计。
5. Orchestration projection 可解释 run 为什么继续、等待、完成或失败。
6. 缺失 source ref 时输出 diagnostic，不编造 fallback 文案。
7. 不保旧 projection 结构。

## Projection 输入

### LLM

```text
llm_invocation
llm_response_item
llm_response_event
llm_continuation_signal
```

### Session

```text
session
session_segment
session_item
visibility flags
source refs
```

### Orchestration

```text
run
turn
execution_chain
execution_step
execution_item_ref
continuation_decision
wait_state
```

### Tool

```text
tool_surface
tool_run
tool_result_envelope
worker/runtime state
```

### Events

```text
observed_event
trace_id
correlation_id
topic cursor
```

## Read Models

### WorkbenchRunReadModel

必须包含：

```text
run
turns
current_turn_id
timeline
steps
status_strip
inspector
linked_entities
diagnostics
actions
```

`timeline` 使用 [workbench-agent-timeline-read-model-plan-20260611.md](workbench-agent-timeline-read-model-plan-20260611.md) 中的 `WorkbenchTimelineItem`。

### LlmOperationsReadModel

新增或扩展：

```text
invocations
response_items
response_events_summary
reasoning_summary_stats
message_phase_stats
continuation_stats
tool_call_stats
provider_external_item_stats
diagnostics
```

### TraceInspectorReadModel

支持 source refs：

```text
llm_invocation_id
llm_response_item_id
llm_response_event_id
session_item_id
tool_run_id
execution_chain_id
continuation_decision_id
context_render_snapshot_id
tool_surface_id
```

## Diagnostics

Operations 不修复业务缺口，只暴露缺口：

```text
missing_session_projection
missing_llm_response_item
missing_tool_result_envelope
missing_continuation_decision
orphan_tool_result
unlinked_response_tool_call
```

diagnostic 必须带 source refs，便于跳转 Trace。

## 退场项

- 不得让前端多路读取 owner API 拼 Workbench。
- 不得让旧 `LlmResult.text/tool_calls` 作为 timeline 主来源。
- 不得保留 execution summary fallback 文案。
- 不得让 Trace 只展示 raw event payload 而不能跳 owner fact。
- 不得为旧 `operations_projections` 做兼容读取。

## Checklist

- [x] 定义 Workbench timeline projection builder。
- [x] 定义 LLM response item/event projection。
- [x] Workbench timeline 聚合 LLM response items。
- [x] Workbench timeline 聚合 SessionItem source refs。
- [x] Workbench timeline 聚合 ToolRuns。
- [x] Workbench timeline 拆分 Tool call/run/result lifecycle。
- [x] 定义 continuation decision execution item projection。
- [x] 定义 Trace inspector source refs。
- [x] Operations observer/materializer 消费新事件或 query facts。
- [x] `/operations/llm` 展示 response item stats。
- [x] `/operations/orchestration` 展示 continuation decisions。
- [x] Workbench step view 展示 continuation decision。
- [x] Workbench run read model 返回 timeline contract。
- [x] Workbench 无真实 content 时不展示假 progress。
- [x] 清库重建后 Operations projection 单测通过。

## 施工状态 2026-06-11

- LLM Operations recent invocation table 已展示 response item count、continuation reason、end_turn。
- LLM invocation detail 已展示 response item table 和 response event table。
- HTTP response DTO 和 frontend runtime contract 已同步 `response_items` / `response_events`。
- Frontend LLM Operations drawer 已展示 response items/events。
- Orchestration execution chain 已开始记录 `CONTINUATION_DECISION` item，可供 Operations/Workbench 后续投影。
- Orchestration Operations execution chains table 已展示 continuation decision count 和 latest decision。
- Workbench 现有 step view 已展示 continuation decision，可解释 run 因 provider continuation 继续或终止。
- Workbench run read model 已返回 timeline contract，初始 timeline 从可信 execution projection 生成。
- Workbench timeline 已优先展开 LLM invocation response items，并保留 `llm_response_item_id` source ref。
- Workbench timeline 已为 assistant progress 保留 `session_item_id` source ref，不再暴露旧 `session_message_id` surface。
- Workbench timeline 已过滤无真实内容的 assistant response item，不再展示假 progress。
- Workbench timeline diagnostics 已进入 inspector debug，可观察 timeline item、LLM response item、tool lifecycle、hidden reasoning 和 provider external item 计数。
- Workbench timeline 已聚合 ToolRun 基础项，并保留 `tool_run_id`、`execution_step_id`、`execution_item_id` source refs。
- Workbench timeline 已拆分 execution `TOOL_CALL` / `TOOL_RUN` / `TOOL_RESULT` lifecycle，并保留 `tool_call_id`、`tool_run_id`、`session_item_id` source refs。
- Trace event read model 已识别 `llm_response_item_id`、`execution_item_id`、`session_item_id`、`tool_call_id`、`continuation_decision_id` 等 source refs，并作为 linked entities 输出；Trace 前端优先展示 API linked entities，并可打开 `session_item` / `llm_response_item` detail。
- 当前完成范围包含 LLM Operations、Orchestration Operations、Workbench LLM response item timeline、Workbench SessionItem/source refs、Workbench Tool lifecycle timeline、Workbench continuation decision、Trace source refs、timeline contract 外壳，以及 Session/LLM owner detail drilldown；SessionItem 迁移主路径已收口，后续只保留测试 fixture bridge 清理和清库重建回归。
