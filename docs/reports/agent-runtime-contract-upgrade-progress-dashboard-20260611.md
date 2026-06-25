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

## 2026-06-14 纠偏补充

最新 Codex HTTP 源码审查和 CRXZipple 最新会话复盘后，升级基线进一步收敛：

- Codex HTTP 不使用 `previous_response_id`，而是发送 normalized `Vec<ResponseItem>` history。
- Codex 源码中的 WebSocket `response.create` 支持 `previous_response_id + delta input`；CRXZipple 当前运行时 gate 已关闭 Codex provider-native continuation，实际 orchestration 链路使用 full clean input，底层 WebSocket delta renderer/transport 仅作为受测能力保留。
- CRXZipple 默认 LLM request 不应再把完整 `<context_tree>` / `<context_tree_delta>` 当作 system prompt 底稿。
- Context Tree 继续作为 agent 可主动查看/管理的对象，默认进入 provider request 的是 compact projection。
- Provider input 主体应迁移为 Codex-like structured ResponseItem replay。
- Workbench/Operations 需要展示 input mode、replay item chain、context observation/task evidence 分层。

新增专项开发文档：

- [llm-session-response-item-replay-plan-20260614.md](llm-session-response-item-replay-plan-20260614.md)
- [context-workspace-tree-projection-plan-20260614.md](context-workspace-tree-projection-plan-20260614.md)
- [orchestration-codex-like-request-assembly-plan-20260614.md](orchestration-codex-like-request-assembly-plan-20260614.md)
- [workbench-operations-response-item-observability-plan-20260614.md](workbench-operations-response-item-observability-plan-20260614.md)

因此，下表中早期“已完成”的 ContextSurface / request replay 相关描述，只表示当时 item-first/tree-delta 中间态已落地；后续施工以本节四份新文档为准继续收敛。

## 2026-06-15 施工进展

- `SessionItem -> LlmInputItem` 直接 replay 已落地：`RuntimeTranscript` 输出 provider-neutral `input_items`，legacy `messages` 只作为兼容 provider 的降级投影。
- Orchestration request envelope 已不再只能从 message 反推 provider input：对能按 `session_item_id` 对上的历史项，优先使用 SessionItem 直出的 `reasoning`、`function_call`、`function_call_output`、`provider_external_item`。
- Context Tree 默认仍走 compact projection / delta；新增 projection message 会作为普通 `message` input item 补入，不把完整 `<context_tree>` 注入 provider prompt。
- Session replay budget 已输出 source/replay 双口径 tool protocol diagnostics，能定位 orphan output、missing output、duplicate call id；protocol-only 与 full-history replay 均已启用保守 tool protocol normalization，只保留第一组有效 `tool_call -> tool_result` pair，并通过 normalization delta 说明哪些源断点被过滤。中断 turn 的 `aborted` output 合成策略后续单独收敛。
- LLM request metadata 已提升 `direct_tool_protocol_health` 摘要，Operations/Workbench 后续可不展开完整 budget 就判断 replay 是否还有协议断点。
- Operations LLM detail Runtime Hints 已展示 tool protocol replay/source/filtered 摘要，能直接看出 provider replay 是否干净、源历史是否曾有断点、过滤了多少坏协议项。
- Workbench linked `llm_invocation` detail payload 已暴露 `runtime_hints.tool_protocol` 摘要，内联面板可复用同一健康事实。
- Workbench linked entity 详情卡已结构化展示 Runtime Hints / Tool protocol replay/source/filtered 摘要，用户不必展开 raw payload。
- Trace linked entity 详情卡已复用同一 Runtime Hints / Tool protocol replay/source/filtered 摘要。
- 本轮已补单测覆盖 SessionItem input item projection、context projection merge 和 provider envelope input item 顺序。
- Request envelope metadata 已新增 `input_mode`、input item kind/source counts、structured replay count 和 projected message count；Operations LLM detail 已展示 Replay Input Mode，能直接区分 structured replay、message projection 和 provider fallback。
- LLM execution step summary 已新增 `llm_request_input`，把 input mode 与 replay/projection item counts 写入 execution chain，Workbench/Trace 不展开 LLM owner detail 也能定位请求组装路径。
- Loop regression baseline 已新增 request input mode 指标，统计 structured replay/message projection step 数、缺失 request-input summary 数以及 replay/projection item totals。

## 2026-06-16 施工进展

- `PromptTranscript` 已迁移为 `RuntimeTranscript`，`build_model_visible_session_item_prompt_window(...)` 已迁移为 `build_model_visible_session_item_runtime_window(...)`，Orchestration 不再以 prompt transcript 命名维护 replay window。
- `prompt_input.py` / legacy prompting package 已退出主路径，runtime request draft/report/input item 由 Orchestration 协调，LLM provider renderer 负责 provider-specific wire rendering。
- Context Tree 已明确为 runtime context state，不再作为 provider prompt surface 发送；完整 tree debug body 只用于 debug 或显式 `context_tree.*` 工具读取。
- `prompt_visible` 已迁移为 `snapshot_visible`，`tree_prompt_visible_nodes(...)` 已迁移为 `tree_snapshot_visible_nodes(...)`。
- Context Workspace / Workbench / Trace / Operations 用户可见口径已从 `Prompt XML`、`Prompt Budget`、`Provider Prompt Tokens` 收敛到 `Context Debug XML`、`Context Budget`、`Provider Wire Tokens`。
- Orchestration maintenance 的 auto compaction 触发口径从 `prompt_budget` / `prompt_threshold` 收敛为 `context_budget` / `context_threshold`。
- Tool source runtime request bundle 已清掉 `ToolPromptBundle` / `list_prompt_bundles` 旧命名。
- Skills 模块已从 `SkillPromptResolution` / `prompt_catalog` 迁移为 `SkillRuntimeRequestResolution` / `runtime_request_catalog`，作为 runtime request 供料边界，不再暴露 prompt catalog API。
- `context_surface` / `ContextSurface` 旧字段已退场为 `context_snapshot`；LLM detail 中 `model_visible_surface` 已改为 `provider_input_summary`，provider preview 摘要字段统一为 `context_snapshot_*`。
- `runtime_loop_correction`、`runtime_evidence_frontier`、browser evidence path 等无法准确形成通用结论的内容已明确不作为默认 model-visible 输入；其中 browser evidence path ladder 已从生产代码与测试 fixture 退场，`browser_evidence` 只保留可验证事实字段，不保留 `evidence_path_*` 路径裁判元数据。
- 最新边界扫描已确认 `prompt_visible`、`prompt_budget`、`provider_prompt_tokens`、`ToolPromptBundle`、`SkillPromptResolution`、`prompt_catalog`、`context_surface`、`model_visible_surface` 等旧施工目标符号在 `src/`、`tests/unit/`、`frontend/src/`、`tools/` 主范围内无残留。
- Workbench request preview 已一等展示 Context Slice 摘要和 selected item/tool rows；HTTP/DTO/runtime preview metadata 与真实 request metadata 使用同一 `context_slice_summary` 来源。
- Workbench timeline 已从 execution step fallback 转为优先展示 LLM response item runtime semantic nodes，能直接看到 assistant commentary、reasoning summary、agent progress、tool call、provider external activity 和 final answer。
- Workbench linked entity drilldown 已收口到有 owner truth 的 refs：`llm_response_item_id`、`session_item_id`、`provider_item_id`、`tool_run_id` 等；不再把 run/turn/step/call 等控制面 ref 当作可展开 owner fact。
- Workspace bootstrap file nodes 已默认 handle-only：slice 中只给路径、大小、读取提示和 `content_available_via=workspace_read`，文件正文必须显式读取并经过预算后才可进入模型输入。
- Orchestration 内部 `ProviderTranscriptRenderer` 残留职责名已迁移为 `RuntimeReplayWindowBuilder`；collector 只构造 runtime replay window 和 protocol-required items，不承担 provider-specific rendering。
- Orchestration request envelope 已停止把 agent profile instruction 自动投影为 `provider_context_messages`；agent instruction 只通过 Context Snapshot / `agent.identity` 进入模型输入，避免 Context Slice 之外的重复 system/context 通道。
- Provider renderer 回归已锁住 `context_snapshot.debug_body` 不进入 OpenAI/Codex/Chat/Anthropic/Gemini wire payload；debug body 只作为 audit / explicit context_tree tool output。
- Runtime request builder 已补回归保护：Context Slice 中 handle-only workspace owner refs 只投影 bounded read hint，owner metadata/body 不进入 `LlmInputItem`。
- Workbench/Trace 的 Context Debug XML 面板已标注为 audit-only，不再用 `Debug Body Tokens` / `Provider Input Tokens` 这类容易混淆的旧文案；UI 口径改为 Context Debug Tokens / Provider Wire Tokens。
- Workbench/Trace request stats 已把旧 `Provider Messages` 文案收口为 `Runtime Replay Messages`，避免把 runtime replay / draft message count 误读为 provider wire payload message count。
- Orchestration execution step kind 已移除 `prompt_render`，当前上下文冻结阶段收口为 `context_snapshot`，UI 不再展示 “Prompt Render”。
- 当前 Context Tree 控制状态迁移 checklist 只剩 `runtime.blocked_state` 延期项；该项必须等待 provider/runtime 显式 blocked/refusal/needs-user item，不能从 assistant 文本推断。

## 2026-06-17 施工进展

- LLM request canonical input 已进一步收敛：普通会话历史不再作为 direct replay 重复发送，但 active session 内成对的 `tool_call -> tool_result` 会保留为精确 `function_call/function_call_output` input item，follow-up turn 不再只能依赖 `recent_tool_interactions` 摘要判断上一轮工具结果。
- Context Workspace provider attachment mirror 已成为 request-time tool schema 真相源；Orchestration 在 snapshot 后按最终 mirror schema 重新解析 executable ToolSurface，避免 provider 看见的 tool schema 与 runtime 可执行工具集合不一致。
- Runtime transcript 新增回归保护：follow-up 场景必须同时看到上一轮 `call_id` 和工具输出文本；相关 context workspace / runtime request / transcript / orchestration 回归 `116 passed`。
- `test_orchestration_tools.py` 已迁移到“默认只暴露 `capability.search`/`exec`/`process`，按 `capability.search(enable=true)` 一步发现并启用工具 schema”的新契约；旧 `context_tree.expand/enable_tool_schema` 默认流断言已清理，整文件回归 `36 passed`。
- LLM request canonical input / Context Slice ordering 收口后，Orchestration follow-up 已从 Context Snapshot `sequence_no` 排序生成 provider input items，并保持 `tool_call -> tool_output -> current_user` 协议顺序；`RuntimeLlmRequest.messages` 退化为从 input items 派生的兼容视图，不再与 draft/context slice 双轨分叉。
- Session item event relay 已把 `session.item.appended` 投影到 turn-session topic，Workbench/turn session 观察面能收到 session owner fact，不再依赖旧 `orchestration.run.message.appended`。
- 全量单测已重新闭合：第一次全量暴露 1 个顺序/压力敏感用例，已把多 skill read 场景的测试推进方式改为 worker 真实可重入推进，同时保留最终状态与两个 `skill_read` tool replay 断言；第二次全量 `2222 passed in 1598.38s`。
- 已收掉测试大文件预算质量债：`tests/unit/test_ui_http.py` 按 Workbench/Operations HTTP 拆分出 `tests/unit/test_ui_operations_http.py`，`tests/unit/test_browser_tool_http.py` 按基础 action/context 与 advanced network/runtime/snapshot 拆分出 `tests/unit/test_browser_tool_http_advanced.py`；`test_code_quality_budgets.py` 已恢复分文件预算，不再靠临时抬高阈值通过。
- Runtime request builder 已把 draft 中稳定 `system` 指令提升为 `provider_context_messages`，同时保持 Context Slice 生成的 user/tool/reasoning 输入只进入 `transcript.items` / provider `input`；`agent_instruction` 仍不走 provider context 旁路，避免重复注入。
- `llm-request-canonical-input-alignment-plan` checklist 已按已验证实现校准：context slice report refs、request-side projector、provider renderer boundary、provider context -> Codex instructions、loss report、Operations/Trace inspection 已闭合；Codex WebSocket continuation 仅底层 renderer/transport 回归保留，runtime 默认 gate 当前关闭，不再标记为 orchestration 持久化/回放闭环完成。
- Agent home context provider 已跳过存在但内容为空的 home files，避免空 `AGENT.md` / `USER.md` / `SOUL.md` / `IDENTITY.md` 占位节点进入 Context Slice 和 provider input；Context Workspace agent adapter 与 runtime request snapshot 回归通过。
- Codex WebSocket continuation 口径已纠偏：底层 renderer/wire tests 仍验证 WebSocket `previous_response_id + function_call_output` delta 能力，但 orchestration/LLM continuation state 对 Codex API family 返回空状态，实际运行回放 full clean input；后续恢复 runtime delta 必须先补 turn-scoped transport/指纹 gate 设计。

## 模块进度总览

| 模块 / 主题 | 目标产物 | 文档状态 | 施工状态 | 风险 | 依赖 | 主文档 |
| --- | --- | --- | --- | --- | --- | --- |
| LLM Contract | response items/events/continuation | 已完成 | response items/events/continuation 主体完成，非流式 invocation 已在 LLM service 内把 adapter response items 归一化为 derived `LlmResult` summary；streaming completed event 带 `response_items` 时已持久化 item snapshot/continuation 并派生 summary，无 item snapshot 时仍是 legacy result fallback；Response event retention policy 已由 LLM owner module 显式暴露，默认 24h 完整调试窗口、detail limit 100、长期事实为 completed response items，Operations detail 已展示该策略；Codex WebSocket profile warmup 已通过 HTTP/CLI/Settings UI/Operations action 暴露为 `llm.warmup` 授权动作，可在长链前验证 credential/transport/connection reuse 且不创建 invocation；Operations action 入口写 action audit 后委托 LLM owner service；warmup succeeded/skipped/failed 已作为 LLM profile owner event 发布；Codex provider-native continuation 当前在 runtime gate 层关闭，避免误把 WebSocket-only `previous_response_id` 用到不完整运行链 | 中高 | provider adapter | [provider-neutral-llm-response-stream-contract-plan-20260611.md](provider-neutral-llm-response-stream-contract-plan-20260611.md) |
| Provider Adapters | OpenAI Responses/Codex item stream mapping | 已完成 | OpenAI/Codex 主路径完成；OpenAI-compatible Chat Completions、Anthropic Messages、Gemini Generate Content 已输出最小 assistant/tool_call response items | 中高 | LLM contract, policy | [llm-provider-adapter-response-item-implementation-plan-20260611.md](llm-provider-adapter-response-item-implementation-plan-20260611.md) |
| Model / Agent Policy | effective request policy | 已完成 | 第一版 `EffectiveLlmRequestPolicy` 已落地；Engine preview/真实 invoke 已使用 Settings runtime defaults + model defaults/capabilities + Agent LLM policy + run override 合成 provider/reasoning/output options，并把 resolution trace 写入 request metadata。Agent Profile `llm_policy` 已进入 settings/home/http/CLI sync/DTO 和 runtime request；Settings `llm_request_defaults` 已进入 runtime request；LLM Operations invocation detail 已展示 policy trace。清库重建后 `llm list` 已可读取 6 个 imported profiles，model/agent/LLM 组合回归 99 passed | 低 | settings, agent, llm, orchestration | [model-agent-policy-llm-request-options-plan-20260611.md](model-agent-policy-llm-request-options-plan-20260611.md) |
| Orchestration | request envelope + item/continuation loop | 已完成 | request envelope snapshot 已定义，preview/真实 invoke 已统一消费 `LlmRequestEnvelope`，可携带 session replay refs、context snapshot、ToolSurface、metadata、run-level reasoning/output/provider options；真实 invoke 已保存 Tool module request-time ToolSurface snapshot，并按 provider-visible tool ids 收敛；preview 只构造 envelope、不写 owner truth；tool_call response item 已受 request ToolSurface function refs 校验；ToolRun 创建已只从 `LlmResponseItem(kind=tool_call)` 派生，不再从 legacy `LlmResult.tool_calls` fallback 派生；ToolRun result 和 approval replay 已补齐 SessionItem protocol refs，ToolRun result envelope 已优先投影为 Session tool_result 的 model/user/trace 分层 payload，当前 turn tool_call/tool_result item ids 已进入 outcome 和 execution chain summary；`llm_response_item_ids` 与 `context_snapshot_id` 已进入 LLM execution item summary；execution chain schema 已收口为 chain/step/step_item + owner/payload_ref/summary_payload 通用引用模型；`ToolExecutionPlan` 已进入 ToolRun metadata、Engine outcome、tool_run_links 和 execution chain tool run/result summary；`ContinuationDecision` value object 已接入 execution chain；`ExecutionOwnerKind` / owner ref factories 已定义；Query service 已提供完整 chain snapshot；Workbench/Trace 已暴露 `execution_item_id` refs；provider external item 已验证不创建 ToolRun；final answer + end_turn + no pending work 已验证完成 run；commentary/reasoning-only terminal response 已失败为 `llm_incomplete_terminal_response`，并把 `llm_loop_diagnostic` 写入 execution payload 与失败 LLM execution item summary；`runtime_loop_correction` 与 `runtime_evidence_frontier` 已降级为 request metadata / Operations / Workbench debug，不再作为 model-visible system message 注入 provider input；approval recovery 生成侧已 item-only | 高 | LLM, Session, Tool, Context Workspace | [orchestration-llm-contract-driven-runtime-plan-20260611.md](orchestration-llm-contract-driven-runtime-plan-20260611.md) |
| Session | `SessionItem` 会话事实流 | 已完成 | 领域模型/application/SQL roundtrip 完成，Orchestration 已写入 LLM response items、legacy text-only assistant final fallback 和 ToolRun results，并把 tool_call/tool_result SessionItem refs 返回给 runtime outcome；默认 replay/recovery/maintenance 主路径已优先使用 SessionItem；Session owner module 已提供 `SessionReplayWindow` / `build_replay_window()` 只读 surface，RuntimeTranscript 已通过该窗口读取 active-session model-visible items 并把 sequence/protocol 摘要写入 transcript budget；Conversation history 已支持 compacted item 的 `lifecycle_state=archived|active` 投影；SessionItem runtime replay 已支持单条超长 item 裁剪；Orchestration runtime recorder 已停止为 assistant progress、tool_call fallback、inline/background tool_result 创建旧 `SessionMessage`，Tool execution link 使用 `result_session_item_id`；Orchestration recorder/maintenance ports 已 item-only，runtime request 已不再调用旧 SessionMessage transcript builder；RuntimeTranscript module 已删除旧 SessionMessage builder/filter/budget/truncate 路径；生产代码中的旧 `SessionMessage` domain object、repository、SQL model/table wiring、UOW `session_messages` 和 message append/list/archive/source surface 已删除；`0073_session_items` head migration 已删除旧 `session_messages` 表，新库目标 schema 只保留 `session_items`；`session.item.appended` 已由 Session module 声明为正式 event definition/surface；Orchestration outcome / LLM step event / execution chain summary / Operations LLM read model 已统一使用 `assistant_progress_item_ids`、`tool_call_session_item_ids`、`tool_result_session_item_ids`、`direct_session_item_count` | 中 | LLM response item, Orchestration | [session-module-response-item-migration-plan-20260611.md](session-module-response-item-migration-plan-20260611.md) |
| Context Workspace | Context Snapshot / Context Tree debug body | 已完成 | request side 已用 SessionItem replay，snapshot 已用一等字段记录 included/protocol/current inbound refs，RuntimeTranscript 已启用 SessionItem 级 budget/frontier 并保留 protocol-required items；follow-up normal turn ordinary history 不直接 replay，但 active session 内成对 `tool_call/tool_result` 会作为结构化 provider replay item 精确保留，历史摘要仅作为辅助而非唯一证据；execution chain tool protocol refs 已合并进入 Context Snapshot 的 `protocol_required_refs`；默认 provider request 只发送 compact `context_workspace_projection`，不再发送 `context_workspace_delta` 或完整 `<context_tree>`；完整 debug body 保留在 Context Snapshot debug，模型需要树状态时通过显式能力/读取工具获取；`ToolSurface.metadata` 已输出 source/group refs mirror；runtime request preview HTTP/DTO 已一等返回 `context_snapshot` / `tool_surface`；默认 provider replay / memory_flush replay / maintenance compaction / inbound user input / Conversation `/messages` / Workbench progress 已使用 item-first surface，runtime request collector 已移除旧 message fallback；session evidence/interaction adapter 已支持 `SessionItemKind.TOOL_CALL` + `SessionItemKind.TOOL_RESULT` 生成 `<tool_interaction>`，并改用 `call_session_item_id/result_session_item_id` owner metadata；tool_result SessionItem content blocks 已可生成 artifact content candidates，已渲染节点可通过 provider attachment mirror 注入 image/file artifact blocks；evidence read hints、XML renderer refs、Context Tree node kind/id 和 snapshot metadata 已切换到 SessionItem 口径：真实 run snapshot 已验证只包含 `session.items.current` / `session.item.*` / `<item role=...>`，不再出现 `session.messages.current` / `session.message.*` / `<message role=...>` | 高 | Session replay, ToolSurface | [context-workspace-llm-request-surface-plan-20260611.md](context-workspace-llm-request-surface-plan-20260611.md) |
| Tool | `ToolSurface` / `ToolResultEnvelope` | 已完成 | Tool module provider-neutral `ToolSurface` / source / group / function application contract 已落地，`ToolSurfaceQueryService.build_surface()` 已可从 Tool catalog + runtime pool 生成 source-first/group-first request-time view，`ToolApplicationService.build_tool_surface()` 已作为只读出口；已验证未 ready/disabled tool 不进入 enabled functions 并进入 diagnostics。`ToolResultEnvelope` 已扩展为 artifact/model/user/trace 分层 payload，大结果外置路径已开始填充新字段。ToolRun 已新增 `call_id` / `tool_surface_id` / `result_envelope_payload` 一等字段和 0075 migration，Tool HTTP/DTO 与 Operations Tool read model 已投影 call/surface refs，Orchestration 发起 tool execution 时已显式传入 call_id。0076 migration 已新增 `tool_surfaces` snapshot 表，ToolSurface repository/UOW 已落地；`build_tool_surface(persist=True)` 已可保存 request-time snapshot，并按 provider-visible `tool_ids` 过滤；Orchestration 真实 request envelope 构造路径已保存 request-unique ToolSurface snapshot，base id 追溯到 context snapshot；LLM request metadata 已输出 `tool_surface_id`、mirrored schema names、function/source/group refs 和 always/context-selected counts；preview 只构造 envelope、不持久化；Operations Tool `auth_missing` 已优先展示近 24h 活跃/失败相关风险，避免 browser runtime 静态风险淹没当前任务工具 | 中高 | Tool catalog, Orchestration | [tool-surface-llm-request-contract-plan-20260611.md](tool-surface-llm-request-contract-plan-20260611.md) |
| Operations Projection | Workbench/Trace/LLM projections | 已完成 | LLM + Session refs + Orchestration + Workbench timeline + Trace refs 已落地；LLM invocation detail 已新增 `runtime_hints` section，可直接看到 `runtime_loop_correction` warnings、tool-only streak、`runtime_evidence_frontier` observed/uncertain/failed 调试计数；LLM lifecycle events 已显式展示 `Transport`、`Continuation`、`Input Delta`，无需展开 JSON 即可确认 provider replay mode；当前 Codex runtime gate 关闭时应显示 full replay / no previous response id，而不是 WebSocket delta；UI/HTTP 测试已按 Operations projection/read model 边界收敛，不再期待页面 GET 触发 daemon runtime refresh，也不再断言旧 `session_message_id` surface；Context Workspace snapshot row 已改用 `tree_items` / `session_item_node_refs` 口径 | 高 | LLM, Session, Orchestration, Tool | [operations-agent-runtime-projection-plan-20260611.md](operations-agent-runtime-projection-plan-20260611.md) |
| Workbench UI | agent timeline read model/renderers | 已完成 | timeline contract + LLM item/Session refs/Tool lifecycle/continuation/Trace refs 基础投影已落地，前端已优先消费 `run.timeline` 并映射到现有 step card；final-only、reasoning、provider external 基础投影已有验证，reasoning/provider item 基础 badge + 折叠详情已落，hidden reasoning 只展示 presence/count，provider external 不生成 ToolRun；可见 `reasoning_summary` 已按“阶段总结”进展项展示并使用 markdown 渲染；fallback step timeline 已禁止无 summary/markdown 的空 `agent_progress` / `agent_thinking` 入 UI；tool run/result timeline content 已透出 `tool_execution_plan` 摘要；timeline trace/source refs 已透出 `context_snapshot_id`；timeline diagnostics 与 `Loop Health` 已进入 inspector debug，能展示 `loop_health` warnings、tool-only streak、validation delta/lag；Workbench linked entity detail 已支持 `llm_invocation`，可查看该轮 request metadata 与 runtime hints 摘要；LLM step 已展示 terminal loop diagnostic badge/summary；Context snapshot 一等 refs 摘要/drilldown 已展示；`session_item_id` / `llm_response_item_id` 已进入 Trace/Workbench 定位字段；Session/LLM owner detail API/client/内联面板已落地；frontend typecheck/build 已通过；UI HTTP 回归已覆盖 item-only Trace/Operations 字段 | 中高 | Operations projection, Context Workspace | [workbench-agent-timeline-read-model-plan-20260611.md](workbench-agent-timeline-read-model-plan-20260611.md) |
| DB Reset | reset / bootstrap playbook | 已完成 | Docker Postgres/Redis 已按 playbook 清库重建；`db current` 为 `0076_tool_surface_snapshots (head)`；daemon running；`tool list` 可读取 catalog；`llm list` 可读取 6 个 imported profiles。首次 `make dev-up` 遇到 Postgres 冷启动连接竞态，等待 healthy 后重跑通过 | 低 | migrations | [runtime-database-reset-playbook-20260611.md](runtime-database-reset-playbook-20260611.md) |
| Testing Strategy | golden path / negative cases | 已完成 | 核心回归矩阵已跑通：LLM/adapters/HTTP/Operations LLM、Session/HTTP/CLI/compaction、Context Workspace HTTP/session/artifact/XML renderer、Tool catalog/execution/Operations Tool、Runtime request/transcript/provider request、Orchestration context/memory/approval/execution chain/tools/resource policy、Events/Observation、Auth/Authorization、UI HTTP/Operations orchestration HTTP、frontend typecheck/build/layout audit、compileall、临时空库 migration smoke、Docker reset bootstrap smoke；Docker reset 后已补跑 Session 30 passed、Context Workspace 91 passed、Tool/Orchestration 85 passed、Model/Agent/LLM 99 passed、UI/Operations 93 passed、Orchestration/Runtime Request 106 passed；本轮 SessionItem context snapshot 纠偏后补跑 Context Workspace/Runtime Request 104 passed、UI/Operations 95 passed、真实 `openai.gpt-5.4-mini` smoke completed；剩余真实长链任务 baseline | 中 | all runtime modules | [agent-runtime-contract-upgrade-testing-strategy-20260611.md](agent-runtime-contract-upgrade-testing-strategy-20260611.md) |
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
| Phase 6 | Context Snapshot | snapshot 记录 included/protocol refs |
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
| 真实长链任务失败 | 先看 response items/events/continuation 和 context snapshot 和 provider input，再改 runtime contract |

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
- Context Snapshot 不能说明 provider input 关联了哪些 runtime facts。
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
| Context 可追溯 | Context Snapshot 与 provider preview 能说明 provider input 关联了哪些 runtime facts |
| 前端数据源 | Workbench 不跨模块直接拼数据 |

## 当前待决 / 待细化

| 项 | 状态 | 影响 |
| --- | --- | --- |
| provider external item artifact/link 规范 | 待设计 | 影响 Workbench/Trace 展示和复用 |
| response events 长期保留窗口 | 待设计 | 影响存储体积和调试能力 |
| ToolSurface 常驻工具首批清单 | 已定首批：command/web/context_tree source policy | 影响模型默认行动能力；不通过 orchestration route 联想注入 |
| raw reasoning 受控开关入口 | 待确认 | 影响 Trace/UI 权限设计 |
| phase unknown final-answer policy 细节 | 已有原则，待落字段 | 影响 Orchestration completion |

## 2026-06-14 Codex 能力对齐推进

本轮基于 `/Users/crxzy/Documents/codex` 源码和一次强制 HTTP transport 的 Codex 东航任务实跑，补充了 Codex 能力来源总纲，并进入首批施工。

### 新增/更新文档

| 文档 | 状态 | 要点 |
| --- | --- | --- |
| [codex-capability-alignment-development-plan-20260614.md](codex-capability-alignment-development-plan-20260614.md) | 新增 | 把 Codex 能力来源拆成 shell runtime contract、direct tool surface、agent message lifecycle、provider-native continuation、context tree delivery、failure evidence contract |
| [codex-websocket-continuation-transport-plan-20260614.md](codex-websocket-continuation-transport-plan-20260614.md) | 新增/施工依据 | 明确 Codex HTTP 不支持 `previous_response_id`，WebSocket `response.create` 才支持 `previous_response_id + delta input` |

### 已落地施工

| 范围 | 状态 | 说明 |
| --- | --- | --- |
| Codex LLM profiles | 已更新 | `openai_codex.gpt-5.5`、`gpt-5.4`、`gpt-5.4-mini`、`gpt-5-codex` 已声明 `provider_websocket_transport` / `provider_incremental_input`，默认 `provider_transport=websocket` |
| Command tool surface | 已更新 | `exec` schema/README 已强化为 local workspace runtime，可用于环境探测、短脚本、资源检查、HTTP/API 复现，并强调 stdout/stderr/exit_code 是下一步证据 |
| Command runtime result contract | 已验证 | 真实 `exec` runtime probe 已验证 summary/stdout/stderr/exit_code/cwd/shell 进入 model-visible envelope；raw output 外置为 artifact 后 read handle 已收口为最终 artifact 位置 |
| Runtime contract | 已更新 | Tool discipline 增加 shell runtime 探测原则和动态站点/API-backed 应用的通用证据路径，不写死 urllib/browser/CDP/抓 JS 单一路线 |
| Workbench tool evidence timeline | 已更新 | tool lifecycle 的 `tool_result` 已展示 `result_summary`、`exit_code`、`truncated` 和 `read_handles`，避免用户只看到兜底工具结果 |
| Workbench/Trace tool run detail | 已更新 | linked entity detail 已支持 `tool_run`，可展开 ToolRun payload、`result_envelope`、`read_handles`、`raw_output_blocks` 与 artifact/evidence refs |
| Workbench failure guidance | 已更新 | failed run 自动生成用户可见 Failure guidance，包含错误码、错误消息和下一步处理建议，并同步进入 steps/timeline |
| Workbench timeline kind convergence | 已更新 | Timeline kind 收敛到目标集合，approval/wait/system evidence 等运行事实不再裸露内部 step type |
| Codex-like loop baseline | 已更新 | `orchestration baseline` 已补充 response item、tool result summary/exit/read handle/truncation、evidence frontier 与 `loop_health` 指标；CLI 已接入 LLM response item resolver，Workbench inspector debug 已复用 run 内 LLM response item resolver 展示 `Loop Health`；mock 长链回归覆盖 endpoint discovery、validation/WAF blocked、final evidence completeness；tool-only streak 与 validation lag 已有 warning 分段 |
| Runtime loop correction | 已降级 | `runtime_loop_correction` 不再作为 model-visible system message 注入 provider input；payload 只保留在 request metadata / Operations / Workbench debug，用于审计 tool-only streak、validation lag 等观测事实 |
| Runtime evidence frontier | 已降级 | `runtime_evidence_frontier` 不再作为 model-visible system digest 注入 provider input；`evidence_frontier` 只保留为 Orchestration/Operations debug 事实，Context Workspace 不再生成 evidence node / snapshot evidence / evidence delta |
| Runtime hints observability | 已更新 | Operations LLM invocation detail 已新增 `runtime_hints` section；Workbench linked entity detail 已支持 `llm_invocation`，能从 timeline/inspector 链接直接查看该轮 request metadata、loop correction warnings 和 evidence frontier 计数；LLM profile warmup succeeded/skipped/failed event 已进入 Operations lifecycle events，Provider Access 表已展示最近 warmup 状态和 next action；LLM Operations 页面已可从 Operations action 入口触发 saved profile warmup 并记录 action audit |
| Provider request preview | 已更新 | LLM adapter request 已携带 `request_metadata`；OpenAI Responses/Codex actual request preview 已投影 context snapshot id、tree schema、included node count、tool surface fingerprint、tool surface id、tool function count 与 tool surface fingerprint；Workbench LLM linked entity detail 已返回并可读展示 `provider_input_summary` 摘要；preview 只保留摘要和 sha256，不泄露完整 context tree rendered body |
| Provider-neutral input replay | 已更新 | 新增 `LlmInputItem` / `LlmInputItemKind`，`LlmInvocation` / `LlmAdapterRequest` / `InvokeLlmInput` / `StreamLlmInput` / HTTP DTO / SQL schema 已贯通 `input_items`；OpenAI Responses 与 Codex Responses adapter 在 `input_items` 非空时优先生成 provider `input`；OpenAI Chat Compatible / Anthropic Messages / Gemini Generate Content 已先从 `input_items` 派生 provider-native messages，再退回 legacy messages；Operations LLM detail 已拆分展示 provider-neutral Replay Input Items/Kinds/Sources/Protocol Items 与 provider request preview，Workbench/Trace linked `llm_invocation` detail 已展示同一 replay input 摘要；RuntimeTranscript budget 已输出 collapsed/shortened replay truncation diagnostics 和 omitted chars，避免把最终适配器预览误认为模型回放来源 |
| Session-backed protocol replay | 已更新 | Execution chain protocol refs 已统一指向真实 `session_item`，`execution_step_item_id` 仅作为追溯字段；Context Slice 对结构化 `tool_call` / `tool_result` 即使没有普通 text/content 也会保留为可投影输入，避免下一轮 provider input 只剩孤儿 `function_call_output` |
| Context Tree compact projection | 已更新 | 实际 provider request 与 preview 已默认只使用 `context_workspace_projection`；完整 `<context_tree>` 和 `context_workspace_delta` 不再作为默认 model-visible 底稿，完整 debug body 保留在 Context Snapshot debug 与显式 `context_tree.*` 工具输出中 |
| Real long-chain baseline | 已观测 | 东航真实 run `8ab370783a34472a9414070aec200267` completed：`llm_calls=32`、`llm_response_item_count=64`、`llm_reasoning_response_item_count=32`、`llm_reasoning_text_item_count=14`、`llm_tool_call_response_item_count=31`、`tool_calls=31`、`tool_result_items=31`、`evidence_frontier_item_count=29`、`first_endpoint_discovery_step=4`、`first_candidate_validation_step=60`、final answer 含 verified/gap/unavailable evidence |
| Real long-chain residual issue | 待治理 | response-item aware baseline 修正旧误判：同一 run 不是 31 连 tool-only，而是 `llm_text_tool_call_steps=14`、`llm_tool_only_steps=17`、`max_consecutive_llm_tool_only_steps=4`、`metrics_missing=[]`、discovery->validation delta 56；`loop_health.warnings=[tool_only_streak, validation_lag]`；Workbench 后端 timeline 已投影 `reasoning_summary=16`、`tool_call=31`、`agent_progress=2`、`final_answer=1`，前端已将可见 reasoning summary 作为阶段总结展示，inspector debug 已展示 `Loop Health`；SessionItem protocol-only replay 已保留当前 turn 有正文的 reasoning/progress；剩余问题是空 reasoning streak / validation 延迟治理 |
| LLM adapter regression | 已验证 | `tests/unit/test_llm_adapters.py tests/unit/test_llm.py` 通过，确认当前 WebSocket/HTTP continuation 半成品未破坏 adapter contract |
| Settings/Tool/Context regression | 已验证 | `tests/unit/test_llm_settings_integration.py tests/unit/test_llm.py tests/unit/test_orchestration_tools.py tests/unit/test_context_workspace_root_nodes.py` 通过，65 passed in 436.51s |
| Workbench/Operations UI regression | 已验证 | continuation fallback、LLM provider failure facts、tool result evidence timeline 相关 UI HTTP 单测通过 |
| Loop baseline regression | 已验证 | `tests/unit/test_orchestration_loop_regression_baseline.py tests/unit/test_orchestration_cli.py` 通过，覆盖 Codex-like mock 长链指标和 CLI 输出稳定性 |
| Command runtime regression | 已验证 | `tests/unit/test_command_tools.py tests/unit/test_command_exec.py tests/unit/test_tool_workspace.py::ToolWorkspaceTestCase::test_workspace_exec_tool_honors_output_token_budget` 通过 |
| Input replay / compact projection regression | 已验证 | `test_llm.py`、`test_llm_adapters.py`、`test_orchestration_runtime_llm_request_builder.py`、`test_orchestration_context_workspace_snapshot.py`、`test_prompt_transcript.py` 共 136 passed；`test_orchestration_tools.py` 37 passed |
| Phase 7 Codex parity fixture | 已更新 | Codex trace lifecycle 已固化为测试：本地抓包断言 `agent_message=23`、`command_execution=42`、`mcp_tool_call=4`、`web_search=2`；CRXZipple latest-run 等价输入 `reasoning=34/tool_call=42/assistant_message=1` 已回归为 `agent_progress=34` 投影；`context_tree.*` 控制面 tool call 已从 Workbench 主时间线隐藏，Operations LLM detail 保留 `provider_payload` 审计列；相关 38 个单测通过 |

### 当前判断

- Codex HTTP-only / 当前 CRXZipple Codex runtime gate 都走 full replay，长链会有 token/TPM 压力；WebSocket delta 是底层可测能力，但还不是当前 orchestration 默认运行能力。
- 当前优先级继续保持：
  - P0: Codex provider input 与 protocol replay 继续保持干净、可观测、无孤儿 tool output。
  - P0: agent progress/response item lifecycle 稳定投影到 Workbench 和 model-visible replay。
  - P1: exec/tool/runtime contract 让模型自然使用 shell 探测与验证。
  - P1: Codex WebSocket delta runtime gate 如需恢复，必须先补 turn-scoped transport/指纹校验设计和单独变更请求。

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
SessionItem 领域模型、service、内存仓储、SQL 表/仓储和 source/call/provider refs roundtrip 已完成；Orchestration 已把 inbound user input、LLM response items、legacy text-only assistant final fallback、ToolRun results 和 approval resolution 写入 SessionItem model-visible view，其中 inbound user recorder 和 legacy assistant final fallback 已停止生成旧 `SessionMessage`，ToolRun 创建已不再从 legacy `LlmResult.tool_calls` fallback 派生，当前 turn response-item tool_call/tool_result 的 SessionItem refs 已进入 Engine outcome `session_item_ids`，execution chain tool result item 也已优先使用 `session_item` owner。Runtime request builder 已使用 model-visible SessionItem replay view；默认 provider replay 和 memory_flush replay 不再读取旧 session messages；当前 session 尚无 model-visible SessionItem 时，normal turn 只从当前 inbound instruction 构造最小输入。approval replay recovery 已记录 `tool_result_item_ids`，新 recovery contract 不再生成 `tool_result_message_ids`。Maintenance compaction 已优先从 run `session_item_ids` 选择 summary item，并用 SessionItem sequence 写入 item frontier；compaction 会把 compacted segment、summary item、compaction run 和 item frontier 写入被覆盖 item metadata，Session compact input/result 已删除 summary message 和 archived message frontier/count。preflight maintenance active history 检查也已改为读取 model-visible SessionItem。Session application public surface 已移除旧 message append/list/source/metadata/archive 用例，HTTP/CLI 已提供 `SessionItem` append/list surface；agent-facing `tools/sessions` 已改为读取/写入 SessionItem；Conversation `/messages` endpoint 和 conversation preview 已使用 chat-visible SessionItem，并把 compacted item metadata 投影成 `lifecycle_state=archived|active`。Request metadata 已记录 direct session item refs/frontier/budget，并只用 `current_inbound_session_item_id` 定位当前用户输入；已移除 direct transcript session message refs 和旧 tool protocol message fallback。SessionItem replay 已启用 item-level budget，超预算时仍保留 protocol-required items，并支持单条超长 item 的最近内容裁剪。Context Snapshot 已用一等字段记录 included/protocol/current inbound refs，并在 metadata/provider attachments 中保留观察镜像；Context Workspace artifact owner adapter 已从 SessionItem content blocks 扫描 artifact refs，session current segment/current range/evidence ledger/browser warning/consumed tool history/historical range 入口已切到 model-visible SessionItem，并删除旧 `list_messages` fallback；Context Tree agent-facing surface 已扶正为 `session.items.current` / `session.item.*` / `<item role=...>`，snapshot metadata 和 Operations projection 已使用 `tree_session_item_count` / `session_item_node_refs` / `tree_items`。Workbench/Trace 已展示 snapshot 一等 refs 摘要和 protocol refs 预览；`session_item_id` / `llm_response_item_id` 已进入 TraceContext、Trace linked entities 和 Workbench timeline source_refs；Workbench agent progress 已使用 SessionItem 内容和 trace refs，前端 Workbench 已开始优先消费后端 `run.timeline`；Workbench linked entity detail/API/client/Step inspector/Trace inspector 内联面板已支持 `session_item` / `llm_response_item`，`session_message_id` surface 已从 Runtime TraceContext、Events trace、Workbench source refs 和前端 runtime contract 移除。
本轮已补充多组迁移回归：LLM/adapter/Operations LLM、Session/HTTP/CLI/compaction、Context Workspace HTTP/session/artifact adapter、Tool catalog/execution/Operations Tool、Runtime request/transcript/provider request、Orchestration Context/Memory/Session tool HTTP、Approval/ExecutionChain/Compaction、UI HTTP、Turns/Conversations/Context snapshot、Orchestration tools/resource policy 均已通过。临时空库 migration smoke 与 Docker Postgres/Redis reset bootstrap smoke 均已可升到 `0076_tool_surface_snapshots (head)`，daemon、tool catalog、LLM profiles 可用；Docker reset 后又补跑 Session、Context Workspace、Tool/Orchestration、Model/Agent/LLM、UI/Operations、Orchestration/Runtime Request 回归，合计 504 个测试通过。SessionItem context snapshot 纠偏后又补跑 Context Workspace/Runtime Request 104 passed、UI/Operations 95 passed、`git diff --check` 通过，并完成真实 `openai.gpt-5.4-mini` smoke：run `b1f96e59bf6140588c8a8fb6b30aa1e2` completed，snapshot `ctxsnap_d86bd645542a489188d8c9f64e63b4b7` 的 debug body 已验证不包含旧 `session.messages.current` / `session.message.*` / `<message role=...>`。下一步建议补一组真实长链任务 baseline，重点观察 response items、SessionItem replay、Context Snapshot artifact mirror、ToolSurface snapshot 和 Operations timeline 是否一致。
```
