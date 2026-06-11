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

- [ ] 定义 Workbench timeline projection builder。
- [ ] 定义 LLM response item/event projection。
- [ ] 定义 continuation decision projection。
- [ ] 定义 Trace inspector source refs。
- [ ] Operations observer/materializer 消费新事件或 query facts。
- [ ] `/operations/llm` 展示 response item stats。
- [ ] `/operations/orchestration` 展示 continuation decisions。
- [ ] Workbench 无真实 content 时不展示假 progress。
- [ ] 清库重建后 Operations projection 单测通过。
