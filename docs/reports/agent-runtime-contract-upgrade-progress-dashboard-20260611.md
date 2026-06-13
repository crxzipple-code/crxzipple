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
| LLM Contract | response items/events/continuation | 已完成 | response items/events/continuation 主体完成，非流式 invocation 已在 LLM service 内把 adapter response items 归一化为 derived `LlmResult` summary；streaming completed event 带 `response_items` 时已持久化 item snapshot/continuation 并派生 summary，无 item snapshot 时仍是 legacy result fallback | 中高 | provider adapter | [provider-neutral-llm-response-stream-contract-plan-20260611.md](provider-neutral-llm-response-stream-contract-plan-20260611.md) |
| Provider Adapters | OpenAI Responses/Codex item stream mapping | 已完成 | OpenAI/Codex 主路径完成；OpenAI-compatible Chat Completions、Anthropic Messages、Gemini Generate Content 已输出最小 assistant/tool_call response items | 中高 | LLM contract, policy | [llm-provider-adapter-response-item-implementation-plan-20260611.md](llm-provider-adapter-response-item-implementation-plan-20260611.md) |
| Model / Agent Policy | effective request policy | 已完成 | 第一版 `EffectiveLlmRequestPolicy` 已落地；Engine preview/真实 invoke 已使用 Settings runtime defaults + model defaults/capabilities + Agent LLM policy + run override 合成 provider/reasoning/output options，并把 resolution trace 写入 request metadata。Agent Profile `llm_policy` 已进入 settings/home/http/CLI sync/DTO 和 prompt input；Settings `llm_request_defaults` 已进入 prompt input；LLM Operations invocation detail 已展示 policy trace。清库重建后 `llm list` 已可读取 6 个 imported profiles，model/agent/LLM 组合回归 99 passed | 低 | settings, agent, llm, orchestration | [model-agent-policy-llm-request-options-plan-20260611.md](model-agent-policy-llm-request-options-plan-20260611.md) |
| Orchestration | request envelope + item/continuation loop | 已完成 | request envelope snapshot 已定义，preview/真实 invoke 已统一消费 `LlmRequestEnvelope`，可携带 session replay refs、ContextSurface、ToolSurface、metadata、run-level reasoning/output/provider options；真实 invoke 已保存 Tool module request-time ToolSurface snapshot，并按 provider-visible tool ids 收敛；preview 只构造 envelope、不写 owner truth；tool_call response item 已受 request ToolSurface function refs 校验；ToolRun 创建已只从 `LlmResponseItem(kind=tool_call)` 派生，不再从 legacy `LlmResult.tool_calls` fallback 派生；ToolRun result 和 approval replay 已补齐 SessionItem protocol refs，ToolRun result envelope 已优先投影为 Session tool_result 的 model/user/trace 分层 payload，当前 turn tool_call/tool_result item ids 已进入 outcome 和 execution chain summary；`llm_response_item_ids` 与 `context_render_snapshot_id` 已进入 LLM execution item summary；execution chain schema 已收口为 chain/step/step_item + owner/payload_ref/summary_payload 通用引用模型；`ToolExecutionPlan` 已进入 ToolRun metadata、Engine outcome、tool_run_links 和 execution chain tool run/result summary；`ContinuationDecision` value object 已接入 execution chain；`ExecutionOwnerKind` / owner ref factories 已定义；Query service 已提供完整 chain snapshot；Workbench/Trace 已暴露 `execution_item_id` refs；provider external item 已验证不创建 ToolRun；final answer + end_turn + no pending work 已验证完成 run；commentary/reasoning-only terminal response 已失败为 `llm_incomplete_terminal_response`，并把 `llm_loop_diagnostic` 写入 execution payload 与失败 LLM execution item summary；approval recovery 生成侧已 item-only | 高 | LLM, Session, Tool, Context Workspace | [orchestration-llm-contract-driven-runtime-plan-20260611.md](orchestration-llm-contract-driven-runtime-plan-20260611.md) |
| Session | `SessionItem` 会话事实流 | 已完成 | 领域模型/application/SQL roundtrip 完成，Orchestration 已写入 LLM response items、legacy text-only assistant final fallback 和 ToolRun results，并把 tool_call/tool_result SessionItem refs 返回给 runtime outcome；默认 replay/recovery/maintenance 主路径已优先使用 SessionItem；Conversation history 已支持 compacted item 的 `visibility_state=archived|active` 投影；SessionItem prompt replay 已支持单条超长 item 裁剪；Orchestration runtime recorder 已停止为 assistant progress、tool_call fallback、inline/background tool_result 创建旧 `SessionMessage`，Tool execution link 使用 `result_session_item_id`；Orchestration recorder/maintenance ports 已 item-only，prompt input 已不再调用旧 SessionMessage transcript builder；PromptTranscript module 已删除旧 SessionMessage builder/filter/budget/truncate 路径；生产代码中的旧 `SessionMessage` domain object、repository、SQL model/table wiring、UOW `session_messages` 和 message append/list/archive/source surface 已删除；`0073_session_items` head migration 已删除旧 `session_messages` 表，新库目标 schema 只保留 `session_items`；`session.item.appended` 已由 Session module 声明为正式 event definition/surface；Orchestration outcome / LLM step event / execution chain summary / Operations LLM read model 已统一使用 `assistant_progress_item_ids`、`tool_call_session_item_ids`、`tool_result_session_item_ids`、`direct_session_item_count` | 中 | LLM response item, Orchestration | [session-module-response-item-migration-plan-20260611.md](session-module-response-item-migration-plan-20260611.md) |
| Context Workspace | `ContextSurface` / structured prompt surface | 已完成 | request side 已用 SessionItem replay，snapshot 已用一等字段记录 included/protocol/current inbound refs，Prompt transcript 已启用 SessionItem 级 budget/frontier 并保留 protocol-required items；follow-up normal turn direct transcript 已收窄到当前 user + 当前 turn protocol pair，历史 tool_call/tool_result 进入 Context Tree；execution chain tool protocol refs 已合并进入 render snapshot / ContextSurface 的 `protocol_required_refs`；`ToolSurface.metadata` 已输出 source/group refs mirror；prompt-preview HTTP/DTO 已一等返回 `context_surface` / `tool_surface`；默认 provider replay / memory_flush replay / maintenance compaction / inbound user input / Conversation `/messages` / Workbench progress 已使用 item-first surface，prompt input collector 已移除旧 message fallback；session evidence/interaction adapter 已支持 `SessionItemKind.TOOL_CALL` + `SessionItemKind.TOOL_RESULT` 生成 `<tool_interaction>`，并改用 `call_session_item_id/result_session_item_id` owner metadata；tool_result SessionItem content blocks 已可生成 artifact content candidates，已渲染节点可通过 provider attachment mirror 注入 image/file artifact blocks；evidence read hints、XML renderer refs、Context Tree node kind/id 和 snapshot metadata 已切换到 SessionItem 口径：真实 run snapshot 已验证只包含 `session.items.current` / `session.item.*` / `<item role=...>`，不再出现 `session.messages.current` / `session.message.*` / `<message role=...>` | 高 | Session replay, ToolSurface | [context-workspace-llm-request-surface-plan-20260611.md](context-workspace-llm-request-surface-plan-20260611.md) |
| Tool | `ToolSurface` / `ToolResultEnvelope` | 已完成 | Tool module provider-neutral `ToolSurface` / source / group / function application contract 已落地，`ToolSurfaceQueryService.build_surface()` 已可从 Tool catalog + runtime pool 生成 source-first/group-first request-time view，`ToolApplicationService.build_tool_surface()` 已作为只读出口；已验证未 ready/disabled tool 不进入 enabled functions 并进入 diagnostics。`ToolResultEnvelope` 已扩展为 artifact/model/user/trace 分层 payload，大结果外置路径已开始填充新字段。ToolRun 已新增 `call_id` / `tool_surface_id` / `result_envelope_payload` 一等字段和 0075 migration，Tool HTTP/DTO 与 Operations Tool read model 已投影 call/surface refs，Orchestration 发起 tool execution 时已显式传入 call_id。0076 migration 已新增 `tool_surfaces` snapshot 表，ToolSurface repository/UOW 已落地；`build_tool_surface(persist=True)` 已可保存 request-time snapshot，并按 provider-visible `tool_ids` 过滤；Orchestration 真实 request envelope 构造路径已保存 request-unique ToolSurface snapshot，base id 追溯到 context snapshot；LLM request metadata 已输出 `tool_surface_id`、mirrored schema names、function/source/group refs 和 always/context-selected counts；preview 只构造 envelope、不持久化；Operations Tool `auth_missing` 已优先展示近 24h 活跃/失败相关风险，避免 browser runtime 静态风险淹没当前任务工具 | 中高 | Tool catalog, Orchestration | [tool-surface-llm-request-contract-plan-20260611.md](tool-surface-llm-request-contract-plan-20260611.md) |
| Operations Projection | Workbench/Trace/LLM projections | 已完成 | LLM + Session refs + Orchestration + Workbench timeline + Trace refs 已落地；UI/HTTP 测试已按 Operations projection/read model 边界收敛，不再期待页面 GET 触发 daemon runtime refresh，也不再断言旧 `session_message_id` surface；Context Workspace snapshot row 已改用 `tree_items` / `session_item_node_refs` 口径 | 高 | LLM, Session, Orchestration, Tool | [operations-agent-runtime-projection-plan-20260611.md](operations-agent-runtime-projection-plan-20260611.md) |
| Workbench UI | agent timeline read model/renderers | 已完成 | timeline contract + LLM item/Session refs/Tool lifecycle/continuation/Trace refs 基础投影已落地，前端已优先消费 `run.timeline` 并映射到现有 step card；final-only、reasoning、provider external 基础投影已有验证，reasoning/provider item 基础 badge + 折叠详情已落，hidden reasoning 只展示 presence/count，provider external 不生成 ToolRun；tool run/result timeline content 已透出 `tool_execution_plan` 摘要；timeline trace/source refs 已透出 `context_render_snapshot_id`；timeline diagnostics 已进入 inspector debug；LLM step 已展示 terminal loop diagnostic badge/summary；Context snapshot 一等 refs 摘要/drilldown 已展示；`session_item_id` / `llm_response_item_id` 已进入 Trace/Workbench 定位字段；Session/LLM owner detail API/client/内联面板已落地；frontend typecheck/build 已通过；UI HTTP 回归已覆盖 item-only Trace/Operations 字段 | 中高 | Operations projection, Context Workspace | [workbench-agent-timeline-read-model-plan-20260611.md](workbench-agent-timeline-read-model-plan-20260611.md) |
| DB Reset | reset / bootstrap playbook | 已完成 | Docker Postgres/Redis 已按 playbook 清库重建；`db current` 为 `0076_tool_surface_snapshots (head)`；daemon running；`tool list` 可读取 catalog；`llm list` 可读取 6 个 imported profiles。首次 `make dev-up` 遇到 Postgres 冷启动连接竞态，等待 healthy 后重跑通过 | 低 | migrations | [runtime-database-reset-playbook-20260611.md](runtime-database-reset-playbook-20260611.md) |
| Testing Strategy | golden path / negative cases | 已完成 | 核心回归矩阵已跑通：LLM/adapters/HTTP/Operations LLM、Session/HTTP/CLI/compaction、Context Workspace HTTP/session/artifact/XML renderer、Tool catalog/execution/Operations Tool、Prompt input/transcript/provider request、Orchestration context/memory/approval/execution chain/tools/resource policy、Events/Observation、Auth/Authorization、UI HTTP/Operations orchestration HTTP、frontend typecheck/build/layout audit、compileall、临时空库 migration smoke、Docker reset bootstrap smoke；Docker reset 后已补跑 Session 30 passed、Context Workspace 91 passed、Tool/Orchestration 85 passed、Model/Agent/LLM 99 passed、UI/Operations 93 passed、Orchestration/Prompt 106 passed；本轮 SessionItem context surface 纠偏后补跑 Context Workspace/Prompt 104 passed、UI/Operations 95 passed、真实 `openai.gpt-5.4-mini` smoke completed；剩余真实长链任务 baseline | 中 | all runtime modules | [agent-runtime-contract-upgrade-testing-strategy-20260611.md](agent-runtime-contract-upgrade-testing-strategy-20260611.md) |
| Assistant Progress Legacy Investigation | 历史调查，非主方案 | 已降级 | 不施工 | 低 | none | [assistant-progress-session-context-convergence-plan-20260611.md](assistant-progress-session-context-convergence-plan-20260611.md) |

## 施工顺序建议

| 阶段 | 范围 | 完成标志 |
| --- | --- | --- |
| Phase 0 | 清库重建准备 / migration 策略确认 | 临时空库与 Docker Postgres reset 均可 upgrade 到 `0076_tool_surface_snapshots (head)`；bootstrap smoke 通过 |
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
已进入代码施工：LLM response item/event/continuation 的领域对象、SQLAlchemy 表、仓储 roundtrip 已落地。
OpenAI Responses/Codex `invoke()` 已输出 response items 和 continuation；provider native item lifecycle stream event 已持久化为 LLM response events。
Orchestration 已能从 `LlmResponseItem(kind=tool_call)` 驱动 inline tool loop，并能用 `continuation.needs_follow_up` 处理 `end_turn=false` 的无工具续跑；preview/真实 invoke 已统一消费 `LlmRequestEnvelope`，effective policy resolver 已合成 model defaults/capabilities + run override，并让 `llm_request_options` 贯通 reasoning/output/provider options；commentary/reasoning-only terminal response 已失败为 `llm_incomplete_terminal_response`，并把 `llm_loop_diagnostic` 写入 execution payload 与失败 LLM execution item summary；execution chain 已通过 `ContinuationDecision` value object 记录 continuation decision item；LLM response item refs 与 Context Snapshot refs 已可从 LLM execution summary 追溯；ToolExecutionPlan 已可从 tool run/result execution summary 追溯，并携带 `tool_surface_id`；ToolRun result envelope 已进入 Session tool_result replay payload。
LLM Operations 已展示 response item/event/continuation；Orchestration Operations 已展示 continuation decision；Workbench run read model 已返回 timeline contract，能展开 LLM response items、SessionItem refs、Tool call/run/result lifecycle，展示 continuation decision，并在 LLM step 中展示 terminal loop diagnostic；Trace read model 已识别 source refs linked entities。
SessionItem 领域模型、service、内存仓储、SQL 表/仓储和 source/call/provider refs roundtrip 已完成；Orchestration 已把 inbound user input、LLM response items、legacy text-only assistant final fallback、ToolRun results 和 approval resolution 写入 SessionItem model-visible view，其中 inbound user recorder 和 legacy assistant final fallback 已停止生成旧 `SessionMessage`，ToolRun 创建已不再从 legacy `LlmResult.tool_calls` fallback 派生，当前 turn response-item tool_call/tool_result 的 SessionItem refs 已进入 Engine outcome `session_item_ids`，execution chain tool result item 也已优先使用 `session_item` owner。Prompt input builder 已使用 model-visible SessionItem replay view；默认 provider replay 和 memory_flush replay 不再读取旧 session messages；当前 session 尚无 model-visible SessionItem 时，normal turn 只从当前 inbound instruction 构造最小输入。approval replay recovery 已记录 `tool_result_item_ids`，新 recovery contract 不再生成 `tool_result_message_ids`。Maintenance compaction 已优先从 run `session_item_ids` 选择 summary item，并用 SessionItem sequence 写入 item frontier；compaction 会把 compacted segment、summary item、compaction run 和 item frontier 写入被覆盖 item metadata，Session compact input/result 已删除 summary message 和 archived message frontier/count。preflight maintenance active history 检查也已改为读取 model-visible SessionItem。Session application public surface 已移除旧 message append/list/source/metadata/archive 用例，HTTP/CLI 已提供 `SessionItem` append/list surface；agent-facing `tools/sessions` 已改为读取/写入 SessionItem；Conversation `/messages` endpoint 和 conversation preview 已使用 chat-visible SessionItem，并把 compacted item metadata 投影成 `visibility_state=archived|active`。Request metadata 已记录 direct session item refs/frontier/budget，并只用 `current_inbound_session_item_id` 定位当前用户输入；已移除 direct transcript session message refs 和旧 tool protocol message fallback。SessionItem replay 已启用 item-level budget，超预算时仍保留 protocol-required items，并支持单条超长 item 的最近内容裁剪。Context render snapshot 已用一等字段记录 included/protocol/current inbound refs，并在 metadata/provider attachments 中保留观察镜像；Context Workspace artifact owner adapter 已从 SessionItem content blocks 扫描 artifact refs，session current segment/current range/evidence ledger/browser warning/consumed tool history/historical range 入口已切到 model-visible SessionItem，并删除旧 `list_messages` fallback；Context Tree agent-facing surface 已扶正为 `session.items.current` / `session.item.*` / `<item role=...>`，snapshot metadata 和 Operations projection 已使用 `tree_session_item_count` / `session_item_node_refs` / `tree_items`。Workbench/Trace 已展示 snapshot 一等 refs 摘要和 protocol refs 预览；`session_item_id` / `llm_response_item_id` 已进入 TraceContext、Trace linked entities 和 Workbench timeline source_refs；Workbench agent progress 已使用 SessionItem 内容和 trace refs，前端 Workbench 已开始优先消费后端 `run.timeline`；Workbench linked entity detail/API/client/Step inspector/Trace inspector 内联面板已支持 `session_item` / `llm_response_item`，`session_message_id` surface 已从 Runtime TraceContext、Events trace、Workbench source refs 和前端 runtime contract 移除。
本轮已补充多组迁移回归：LLM/adapter/Operations LLM、Session/HTTP/CLI/compaction、Context Workspace HTTP/session/artifact adapter、Tool catalog/execution/Operations Tool、Prompt input/transcript/provider request、Orchestration Context/Memory/Session tool HTTP、Approval/ExecutionChain/Compaction、UI HTTP、Turns/Conversations/Context snapshot、Orchestration tools/resource policy 均已通过。临时空库 migration smoke 与 Docker Postgres/Redis reset bootstrap smoke 均已可升到 `0076_tool_surface_snapshots (head)`，daemon、tool catalog、LLM profiles 可用；Docker reset 后又补跑 Session、Context Workspace、Tool/Orchestration、Model/Agent/LLM、UI/Operations、Orchestration/Prompt 回归，合计 504 个测试通过。SessionItem context surface 纠偏后又补跑 Context Workspace/Prompt 104 passed、UI/Operations 95 passed、`git diff --check` 通过，并完成真实 `openai.gpt-5.4-mini` smoke：run `b1f96e59bf6140588c8a8fb6b30aa1e2` completed，snapshot `ctxsnap_d86bd645542a489188d8c9f64e63b4b7` 的 prompt body 已验证不包含旧 `session.messages.current` / `session.message.*` / `<message role=...>`。下一步建议补一组真实长链任务 baseline，重点观察 response items、SessionItem replay、ContextSurface artifact mirror、ToolSurface snapshot 和 Operations timeline 是否一致。
```
