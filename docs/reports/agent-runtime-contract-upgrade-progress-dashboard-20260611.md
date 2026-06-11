# Agent Runtime Contract Upgrade Progress Dashboard 2026-06-11

本文用于展示 LLM 能力释放 / Codex parity baseline 升级的整体重构进度。它是汇报看板，不替代各模块开发文档。

## 总体决策

| 项 | 决策 |
| --- | --- |
| 升级基线 | 先按 Codex parity baseline 对齐能力 |
| 数据兼容 | 开发前清库重建，不做历史兼容 |
| Runtime 主契约 | `LlmResponseItem` + `LlmResponseEvent` + `LlmContinuationSignal` |
| Request 主契约 | `LlmRequestEnvelope` |
| UI 数据源 | Workbench 只消费 Operations/UI read model |
| Tool 策略 | ToolSurface source-first/group-first；不恢复 keyword router |
| Hosted provider item | 进入 response history/model replay；绝不创建 CRXZipple ToolRun |
| Raw reasoning | 默认不展示；仅受控 Trace/UI |

## 模块进度总览

| 模块 / 主题 | 目标产物 | 文档状态 | 施工状态 | 风险 | 依赖 | 主文档 |
| --- | --- | --- | --- | --- | --- | --- |
| LLM Contract | response items/events/continuation | 已完成 | 未开始 | 高 | provider adapter | [provider-neutral-llm-response-stream-contract-plan-20260611.md](provider-neutral-llm-response-stream-contract-plan-20260611.md) |
| Provider Adapters | OpenAI Responses/Codex item stream mapping | 已完成 | 未开始 | 高 | LLM contract, policy | [llm-provider-adapter-response-item-implementation-plan-20260611.md](llm-provider-adapter-response-item-implementation-plan-20260611.md) |
| Model / Agent Policy | effective request policy | 已完成 | 未开始 | 中 | settings, agent, llm | [model-agent-policy-llm-request-options-plan-20260611.md](model-agent-policy-llm-request-options-plan-20260611.md) |
| Orchestration | request envelope + item/continuation loop | 已完成 | 未开始 | 高 | LLM, Session, Tool, Context Workspace | [orchestration-llm-contract-driven-runtime-plan-20260611.md](orchestration-llm-contract-driven-runtime-plan-20260611.md) |
| Session | `SessionItem` 会话事实流 | 已完成 | 未开始 | 高 | LLM response item, Orchestration | [session-module-response-item-migration-plan-20260611.md](session-module-response-item-migration-plan-20260611.md) |
| Context Workspace | `ContextSurface` / structured prompt surface | 已完成 | 未开始 | 高 | Session replay, ToolSurface | [context-workspace-llm-request-surface-plan-20260611.md](context-workspace-llm-request-surface-plan-20260611.md) |
| Tool | `ToolSurface` / `ToolResultEnvelope` | 已完成 | 未开始 | 中高 | Tool catalog, Orchestration | [tool-surface-llm-request-contract-plan-20260611.md](tool-surface-llm-request-contract-plan-20260611.md) |
| Operations Projection | Workbench/Trace/LLM projections | 已完成 | 未开始 | 高 | LLM, Session, Orchestration, Tool | [operations-agent-runtime-projection-plan-20260611.md](operations-agent-runtime-projection-plan-20260611.md) |
| Workbench UI | agent timeline read model/renderers | 已完成 | 未开始 | 中高 | Operations projection | [workbench-agent-timeline-read-model-plan-20260611.md](workbench-agent-timeline-read-model-plan-20260611.md) |
| DB Reset | reset / bootstrap playbook | 已完成 | 未执行 | 中 | migrations | [runtime-database-reset-playbook-20260611.md](runtime-database-reset-playbook-20260611.md) |
| Testing Strategy | golden path / negative cases | 已完成 | 未开始 | 中高 | all runtime modules | [agent-runtime-contract-upgrade-testing-strategy-20260611.md](agent-runtime-contract-upgrade-testing-strategy-20260611.md) |
| Assistant Progress Legacy Investigation | 历史调查，非主方案 | 已降级 | 不施工 | 低 | none | [assistant-progress-session-context-convergence-plan-20260611.md](assistant-progress-session-context-convergence-plan-20260611.md) |

## 施工顺序建议

| 阶段 | 范围 | 完成标志 |
| --- | --- | --- |
| Phase 0 | 清库重建准备 / migration 策略确认 | 空库可 upgrade head，reset playbook 可执行 |
| Phase 1 | LLM domain contract / persistence | response items/events/continuation 可 roundtrip |
| Phase 2 | OpenAI Responses/Codex adapter | stream fixture 能生成 items/events/continuation |
| Phase 3 | Model/Agent policy effective resolution | request options 有 resolution trace |
| Phase 4 | SessionItem schema/service | model-visible replay view 可用 |
| Phase 5 | ToolSurface / ToolResultEnvelope | tool_call -> ToolRun -> tool_result call_id 贯通 |
| Phase 6 | ContextSurface | render snapshot 记录 included/protocol refs |
| Phase 7 | Orchestration loop integration | 不再依赖 `LlmResult.tool_calls` 推进 |
| Phase 8 | Operations projections | Workbench/Trace 能看到 response item 级事实 |
| Phase 9 | Workbench frontend | timeline 展示 commentary/reasoning/tool/provider external |
| Phase 10 | Golden path / regression | 长链 agent 任务通过，低效探索可诊断 |

## 定期纠偏推进原则

本升级不采用“一次设计、长线盲做”的推进方式。每个 Phase 结束必须做一次 drift check；跨模块集成点发生变化时，也必须即时纠偏。

纠偏不是重开设计会，而是回答四个问题：

| 问题 | 目标 |
| --- | --- |
| 是否仍对齐 Codex parity baseline？ | 用户可见、隐形 history、model replay、stream/debug 分层没有偏移 |
| 是否仍保持 DDD owner 边界？ | LLM/Tool/Session/Orchestration/Context Workspace/Operations 没有互相吞真相 |
| 是否又退回旧主路径？ | 没有重新依赖 `LlmResult.text/tool_calls`、旧 session message、旧 projection 或 keyword router |
| 是否仍可解释？ | request、response、loop decision、context snapshot、timeline 都能通过 source refs 追溯 |

### Drift Check 触发点

| 触发点 | 必查内容 |
| --- | --- |
| 每个 Phase 完成 | 对照本看板更新施工状态、风险和下一步 |
| 新增 schema / migration | 确认没有为了旧库兼容引入 dual-read / dual-write |
| Adapter 行为变化 | 确认 message/reasoning/tool/provider external item 没被压扁 |
| Orchestration loop 变化 | 确认没有恢复 `tool_calls empty => finish` |
| Session replay 变化 | 确认 model-visible / user-visible / chat-visible / trace-visible 分层仍清晰 |
| Workbench/Operations 变化 | 确认前端没有绕过 Operations 多路拼数据 |
| 真实长链任务失败 | 先看 response items/events/continuation 和 context surface，再改 prompt |

### 纠偏输出

每次纠偏至少更新一个地方：

- 本看板的模块施工状态 / 风险 / 下一步。
- 对应模块开发文档的 checklist。
- 如发现设计冲突，先修文档，再继续施工。
- 如发现 Codex parity 不适合多 provider，记录 provider-specific deviation，不把 deviation 写成全局规则。

### 变更请求门禁

施工时如果发现实现必须偏离当前设计，必须先提出变更请求，不能直接在代码里静默改方向。

变更请求至少包含：

| 字段 | 内容 |
| --- | --- |
| `change_id` | 稳定编号，例如 `runtime-contract-cr-001` |
| `trigger` | 触发原因：代码约束、provider 行为、测试失败、真实任务偏差等 |
| `current_design` | 当前文档要求 |
| `proposed_change` | 建议偏移方案 |
| `affected_modules` | 受影响模块 |
| `contract_impact` | request/response/session/tool/workbench/schema 哪些 contract 变化 |
| `risk` | 风险与回滚成本 |
| `decision` | accepted / rejected / deferred |
| `doc_updates` | 需要同步更新的文档 |

变更请求处理原则：

- accepted 前不得把偏移实现合入主施工路径。
- accepted 后必须先更新设计文档和本看板，再继续代码施工。
- rejected 的偏移不得以 fallback、compat shim 或隐藏分支形式留下。
- deferred 的偏移必须有隔离范围，不能污染全局 contract。

### 一票否决信号

出现以下信号时，当前 Phase 不能视为完成：

- runtime 主路径仍从 `LlmResult.tool_calls` 推进。
- Workbench 又出现无真实内容的 progress fallback。
- provider external item 被创建为 CRXZipple ToolRun。
- reasoning summary/raw reasoning 可见性没有 policy/source ref。
- Context render snapshot 不能说明模型实际看到哪些 facts。
- 前端直接拼 `/sessions`、`/llms`、`/tools`、`/orchestration`。

## 关键验收指标

| 指标 | 目标 |
| --- | --- |
| LLM invocation 可解释性 | 每轮 invocation 可列出 response items/events/continuation |
| Loop 决策可解释性 | 每次继续/等待/完成都有 continuation decision |
| Model replay 完整性 | Responses/Codex family 的 reasoning/provider external/tool protocol items 可 replay |
| Tool call 连续性 | `call_id` 贯通 response item、ToolRun、Session tool_result |
| Workbench 真实性 | 没有真实文本时不展示假 progress |
| Provider external 边界 | provider hosted item 不创建 ToolRun |
| Raw reasoning 安全 | 默认不展示 raw reasoning |
| Context 可追溯 | render snapshot 能说明模型看到哪些 facts |
| 前端数据源 | Workbench 不跨模块直接拼数据 |

## 当前待决 / 待细化

| 项 | 状态 | 影响 |
| --- | --- | --- |
| provider external item artifact/link 规范 | 待设计 | 影响 Workbench/Trace 展示和复用 |
| response events 长期保留窗口 | 待设计 | 影响存储体积和调试能力 |
| ToolSurface 常驻工具首批清单 | 待确认 | 影响模型默认行动能力 |
| raw reasoning 受控开关入口 | 待确认 | 影响 Trace/UI 权限设计 |
| phase unknown final-answer policy 细节 | 已有原则，待落字段 | 影响 Orchestration completion |

## 汇报口径

当前状态：

```text
架构决策完成。
模块开发文档完成。
历史兼容策略已统一为清库重建。
尚未进入代码施工。
下一步建议从 LLM contract/persistence 与 OpenAI Responses/Codex adapter 开始。
```
