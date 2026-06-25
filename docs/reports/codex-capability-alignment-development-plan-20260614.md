# Codex Capability Alignment Development Plan

Date: 2026-06-14

## 背景

本轮用 `/Users/crxzy/Documents/codex` 源码和一次强制 HTTP transport 的 Codex 实跑链路，对比了 CRXZipple agent 在“东航官网查询昆明到上海周日票价”任务中的表现。

实跑结论：

- Codex 源码 WebSocket path 支持 `previous_response_id + incremental input`。
- Codex HTTP path 没有 `previous_response_id`，会发送完整 `input`，长链下会明显触发 TPM 压力。
- CRXZipple 当前 runtime gate 明确禁用 Codex provider-native continuation；即便底层 WebSocket renderer/transport 能测 `previous_response_id + delta input`，orchestration 默认链路仍走 full clean input / no previous response id。
- 即使强制 HTTP，Codex 仍能走出较完整的工程探索链：
  - PC 官网被 WAF 拦截后转向移动站。
  - 抓取移动站前端 bundle。
  - 定位 `/m-base/sale/shoppingv2`。
  - 反解 `wbsk_Wbox.js` / `wbsk_skb.js` 加密函数。
  - 构造官方加密 `req` 请求。
  - 尝试 cookie 重放。
  - 最终因阿里云 WAF challenge 阻断而不给出伪造票价。
- Codex 没有拿到真实票价，但失败前的探索链路、阶段说明和证据归因明显强于 CRXZipple 当前 agent。

因此，能力差距不是单纯来自 WebSocket continuation，也不是 Codex 有神秘浏览器工具。差距来自多层叠加：

- 强模型。
- 清晰 shell runtime contract。
- 简洁直接的 exec 工具面。
- 原始 stdout/stderr/network response 反馈。
- 连续的 `agent_message` 阶段性自我整理。
- provider-native continuation 在 Codex WebSocket 源码路径中能降低长链回放成本；CRXZipple 当前不把它作为默认 runtime 能力启用。
- Workbench/Trace 对这些 item 的可见性。

本文件作为总纲开发文档，协调已有专项文档：

- [codex-websocket-continuation-transport-plan-20260614.md](codex-websocket-continuation-transport-plan-20260614.md)
- [provider-native-continuation-and-tree-replay-tool-plan-20260614.md](provider-native-continuation-and-tree-replay-tool-plan-20260614.md)
- [llm-session-response-item-replay-plan-20260614.md](llm-session-response-item-replay-plan-20260614.md)
- [context-workspace-tree-projection-plan-20260614.md](context-workspace-tree-projection-plan-20260614.md)
- [orchestration-codex-like-request-assembly-plan-20260614.md](orchestration-codex-like-request-assembly-plan-20260614.md)
- [workbench-operations-response-item-observability-plan-20260614.md](workbench-operations-response-item-observability-plan-20260614.md)
- [tool-surface-llm-request-contract-plan-20260611.md](tool-surface-llm-request-contract-plan-20260611.md)
- [workbench-agent-timeline-read-model-plan-20260611.md](workbench-agent-timeline-read-model-plan-20260611.md)
- [session-module-response-item-migration-plan-20260611.md](session-module-response-item-migration-plan-20260611.md)
- [orchestration-llm-contract-driven-runtime-plan-20260611.md](orchestration-llm-contract-driven-runtime-plan-20260611.md)

## 目标

让 CRXZipple 在不绑定单一 provider 的前提下，吸收 Codex agent loop 的有效能力：

1. 模型能把 shell/exec 当作可探索的本地运行时。
2. 模型能持续产生阶段性 progress / plan / evidence message。
3. 工具结果尽量原始、完整、结构化地反馈给模型。
4. LLM module 能无损承载 Responses item、reasoning summary、tool call、tool output、provider continuation。
5. Orchestration 能按 response item 生命周期推进，而不是只按“有没有 tool call”粗糙判断。
6. Context Tree 作为 agent 可主动查看/管理的运行面，默认 provider input 改为 Codex-like ResponseItem replay + compact context projection。
7. Workbench 能展示用户该看的内容，隐藏 provider/internal 细节，但不丢失可审计证据。
8. 长链任务在未来恢复 WebSocket continuation runtime gate 后避免全量回放和 token 膨胀；当前先保证 full clean input 语义正确、可观测、无协议孤儿。

## 非目标

- 不复制 Codex hosted `web_search` / `image_generation` 特权能力。
- 不把 CRXZipple 绑定为 OpenAI/Codex-only runtime。
- 不恢复旧 orchestration facade。
- 不让 orchestration 重新拥有 Prompt Tree 拼装。
- 不保留历史数据兼容；施工前允许清库重建。
- 不把 browser/CDP 作为本轮能力对齐的唯一前提。

## Codex 能力来源拆解

## 1. Shell Runtime Contract

Codex 对模型暴露的不只是“执行命令”，而是一种默认工作方式：

- 读代码先用 `rg`。
- 可以运行本地脚本验证假设。
- 可以检查环境里有哪些包和命令。
- 可以下载、保存、反解前端资源。
- 可以用 Node/Python 构造临时验证程序。
- 工具失败后基于 stdout/stderr 继续改脚本。

CRXZipple 当前差距：

- exec 工具虽然存在，但工具说明和 runtime prompt 没有稳定把它塑造成“工程探索运行时”。
- 模型容易把 exec 当作命令执行器，而不是环境探测、请求复现、证据采集面。
- 有时 prompt 过度细化具体路径，反而把模型诱导到固定模式。

对齐原则：

- 不写死“必须用 urllib / 必须抓 JS / 必须用 browser”。
- 明确 shell 可以用于环境探测和验证。
- 明确失败输出是下一步决策依据。
- 明确遇到 Web/WAF/JS 应用时，可以检查页面、资源、接口、依赖、cookies 和本地运行能力。

## 2. Direct Tool Surface

Codex 的 `exec_command` schema 简洁，模型容易理解：

- command。
- workdir。
- output。
- exit code。
- 可继续交互。

CRXZipple 当前差距：

- 工具 source / group / tree / router 设计较强，但容易让模型不确定真正可调用能力。
- 如果 tool description 太业务化，模型不会自然想到用 exec 探测本地 Node/Python/Playwright/CDP。
- 工具结果如果被过度摘要，模型拿不到原始错误信号。

对齐原则：

- 常驻工具说明保持短、直接、动作导向。
- exec 的能力说明要突出本地环境探测、脚本验证和长输出处理。
- 工具结果保留原始 stdout/stderr，同时提供短 summary 给 UI。
- 不因为 UI 好看而牺牲 model-visible 原始反馈。

## 3. Agent Message Lifecycle

Codex 在工具调用之间会产生 `agent_message`：

- 当前发现。
- 下一步计划。
- 路径切换原因。
- 失败证据。
- 最终不编造结果的依据。

这些 message 不是纯 UI 装饰。它们让用户可审计，也让后续模型回合拥有阶段性状态锚点。

CRXZipple 当前差距：

- 已开始记录 progress item，但出现过不显示、兜底、缺失、不可回灌等问题。
- 部分回合没有形成稳定的“发现 -> 下一步 -> 证据”的节奏。
- UI timeline、session history、operations projection 对 item 的语义还没有完全一致。

对齐原则：

- provider 返回的 assistant text / reasoning summary / progress item 必须先作为 response item 保存。
- 再由 Workbench 决定是否用户可见。
- 再由 Context Workspace / Orchestration 决定是否 model-visible。
- 不把所有 item 粗暴折成一条 assistant message。

## 4. Provider-Native Continuation

源码确认：

- Codex HTTP `ResponsesApiRequest` 没有 `previous_response_id`。
- Codex WebSocket `response.create` 有 `previous_response_id`。
- WebSocket path 会用 `last_response.response_id + incremental_items`。
- HTTP path 会全量 `input`，长链下成本很高。

CRXZipple 当前差距：

- 曾错误地把 Codex HTTP 当作支持 `previous_response_id`。
- 当前已止血；底层 Codex WebSocket renderer/transport 已有受测 delta 能力，但 LLM/orchestration runtime gate 暂时禁用 Codex provider-native continuation，真实运行仍回放 full clean input。
- Operations 对 normalized request 和 provider actual payload 的区分还需要继续强化。

对齐原则：

- HTTP 和 WebSocket schema 必须分离。
- continuation capability 必须绑定 provider + transport。
- 对 OpenAI Responses HTTP、Codex Responses WebSocket、非 Responses provider 分别建能力矩阵。
- Codex runtime gate 恢复前，Operations/Workbench 必须明确暴露当前是 full replay / no previous response id；未来 WebSocket delta 恢复必须走单独变更请求和 turn-scoped transport/fingerprint gate。

## 5. Context Tree Delivery

用户最新决策：

- 树是 agent 可见的运行面。
- 不新增额外概念替代树。
- 默认 provider request 不再把完整树 XML 当作 prompt 底稿。
- 树状态通过 compact projection 进入 request。
- 模型要重看树状态时，显式调用 tree replay/read 工具。

CRXZipple 当前差距：

- 树渲染、工具装配、session replay、provider input delta 的关系还容易混在一起。
- 把树作为 system message 会让动态上下文污染稳定 instructions。
- 完全不暴露树工具又会让模型丢失主动管理上下文的能力。

对齐原则：

- 默认：stable instructions + ResponseItem replay + compact context projection。
- 树不默认完整进入 provider input；full tree render 只用于 debug 或显式 tool output。
- 模型需要树：调用 `context_tree.render_current` / `context_tree.read_snapshot` / `context_tree.diff_since` 类工具。
- provider actual payload 仍由树状态渲染工具 schema 和 attachment mirror。

## 6. Failure Evidence Contract

Codex 失败得更干净，因为它把证据链讲清楚：

- 哪个入口能打开。
- 哪个资源被 WAF 拦。
- 哪个接口被定位。
- 哪个请求被复现。
- 哪个响应证明仍被阻断。
- 为什么不能给最终结果。

CRXZipple 当前差距：

- 失败原因有时散落在 tool output 中，最终回答没有聚合。
- Operations timeline 可能看到很多工具，但看不到“为什么换路径”。
- 后续回合不一定知道已经尝试过哪些路径。

对齐原则：

- Orchestration 不维护通用 evidence ledger；业务事实继续归属 Tool / Session / Context Workspace / Operations。
- agent progress item 作为阶段性模型输出保存和展示，不默认升级为任务证据。
- 最终回答应基于 transcript 中的关键事实和失败原因，但是否充分由 LLM 自己判断。
- model-visible context 默认回放 provider-native transcript；tree/evidence debug 通过工具或 Operations 查看，不自动形成行为建议。

## 总体架构

```text
User Task
  |
  v
Context Workspace
  - context tree surface
  - render snapshot
  - tool visibility state
  - tree replay/read tools
  |
  v
Orchestration
  - run loop owner
  - response item lifecycle
  - continuation state
  - provider transcript assembly
  - loop termination policy
  |
  v
LLM Module
  - provider-neutral request
  - response item stream
  - provider transport capability
  - provider actual payload preview
  |
  v
Provider Adapter
  - HTTP full request
  - WebSocket response.create + previous_response_id + delta (底层可测能力；当前 Codex runtime gate 关闭)
  - provider-specific item mapping
  |
  v
Tool Module
  - exec/process/web/context_tree tools
  - raw result + summary
  - tool lifecycle facts
  |
  v
Operations / Workbench
  - read model projection
  - user-visible timeline
  - provider/debug trace
  - failure guidance
```

## 模块改造方案

## 1. LLM Module

### 目标

让 LLM module 无损承载 provider response item 和 transport 能力，不再把强 provider 返回压扁为简化 assistant/tool_call 二元结构。

### 改造项

- 定义 provider-neutral `LlmResponseItem`：
  - `message`
  - `reasoning_summary`
  - `function_call`
  - `function_call_output`
  - `agent_progress`
  - `provider_error`
  - `transport_event`
  - `raw_provider_item`
- 定义 `LlmProviderTransport`：
  - `http`
  - `websocket`
  - `auto`
- 定义 `LlmContinuationState`：
  - `mode`
  - `transport`
  - `previous_response_id`
  - `previous_invocation_id`
  - `input_fingerprint`
  - `tool_schema_fingerprint`
  - `instructions_fingerprint`
- Adapter 输出：
  - normalized response items
  - provider response id
  - provider actual request preview
  - provider actual response metadata
  - continuation eligibility
- Codex HTTP adapter：
  - 禁止发送 `previous_response_id`。
  - 记录 `continuation_degraded_reason=http_transport_without_previous_response_id`。
- Codex WebSocket adapter：
  - 首轮发送 full `response.create`。
  - 后续 prefix/delta 校验通过时可发送 `previous_response_id + delta input`。
  - 当前 CRXZipple runtime gate 不向 Codex adapter 传入 provider-native continuation；该路径仅作为底层 adapter/transport 能力受测保留。
  - 校验失败时 full request fallback，并记录原因。

### 验收

- HTTP Codex 请求 payload preview 不含 `previous_response_id`。
- 底层 WebSocket Codex renderer/transport 第二轮 payload preview 可含：
  - `message_type=response.create`
  - `previous_response_id`
  - `input_mode=delta`
- 当前 orchestration 默认链路的 Codex invocation preview 应显示 `has_previous_response_id=false`、`input_delta_mode=false` 和 full clean input。
- Operations 能显示 transport、input item count、delta item count、fallback reason / runtime gate reason。

## 2. Orchestration Module

### 目标

从“LLM 返回 tool call -> 执行 tool -> 再调 LLM”升级为 response item stream loop。

### 改造项

- 保存每轮 response item：
  - provider item id
  - item type
  - user_visible
  - model_visible
  - operation_visible
  - related tool call id
  - source invocation id
- loop 判断：
  - provider end_turn / completed signal。
  - 是否存在 pending tool call。
  - 是否存在 pending approval。
  - 是否发生 recoverable provider transport fallback。
  - 是否达到 loop budget；不使用通用 evidence threshold 替模型判题。
- agent progress 处理：
  - 作为 run item 保存。
  - 投影到 Workbench timeline。
  - 后续 provider request 按 model-visible policy 回灌。
- continuation 处理：
  - 首轮绑定 context render snapshot。
  - 对支持且已打开 runtime gate 的 provider 后续优先 provider-native continuation。
  - Codex 当前 runtime gate 关闭，后续继续使用 full clean input replay。
  - 只有 fallback provider 才 transcript replay。
- evidence / failure facts:
  - 由 owner module 或工具结果显式提供。
  - 通用 orchestration loop 只保存、回放、展示，不跨任务分类裁判。

### 验收

- 一个长链 run 可展示所有 agent progress。
- 最终失败时有结构化 failure evidence。
- 没有 tool call 但 provider 未 end_turn 时不误判完成。
- provider fallback 到 HTTP full replay 时 run item 明确记录。

## 3. Context Workspace Module

### 目标

树继续作为 agent 可见运行面，但从“默认 prompt 注入”改为“compact projection + 显式 replay/read 工具”。

### 改造项

- 新增或扶正 agent-facing tree 工具：
  - `context_tree.render_current`
  - `context_tree.read_snapshot`
  - `context_tree.diff_since`
  - `context_tree.list_available_sources`
  - `context_tree.explain_tool_visibility`
- render snapshot 增加：
  - `surface_fingerprint`
  - `tool_schema_fingerprint`
  - `attachment_fingerprint`
  - `estimated_token_count`
- provider request surface builder：
  - 默认输出 active task state 和 context hints。
  - 不默认输出完整 tree render。
  - 树状态改变时更新 projection fingerprint / concise context hint。
- model-visible policy：
  - tree replay result 可进入 provider input。
  - UI timeline 不必把完整树 replay 当聊天消息展示。

### 验收

- provider request 有 context tree snapshot id/revision，但无完整树 XML。
- 普通工具轮不自动重放完整树。
- 模型调用 tree replay 工具后，下一轮可看到 replay output。
- Workbench 可解释“当前模型看到哪些工具/上下文”。

## 4. Tool Module

### 目标

让 exec/process/web/context_tree 工具既保持 DDD source 设计，又能给模型足够直接的操作感。

### 改造项

- exec tool description 改为短而明确：
  - 可运行 shell 命令。
  - 可检查本地环境和依赖。
  - 可写临时验证脚本。
  - 可抓取/解析网页资源。
  - stdout/stderr/exit code 会反馈。
- tool result contract：
  - `schema_version=2026-06-14.tool_result_envelope.v1`
  - `model_visible_payload`
  - `user_visible_payload`
  - `trace_payload`
  - `raw_output`
  - `stderr`
  - `exit_code`
  - `status`
  - `truncated`
  - `summary`
  - `artifact_refs`
- 长输出策略：
  - UI 默认折叠 raw output。
  - model-visible 输出不能只剩摘要；必须保留足够原始错误和关键命中行。
  - 截断 stdout/stderr 通过 raw output block 进入 artifact/read handle；普通大文本通过 artifact refs 外置。
- 默认常驻工具：
  - `exec`
  - `process`
  - `context_tree.list`
  - `context_tree.estimate`
  - `context_tree.render_current`
  - `context_tree.read_snapshot`
  - `context_tree.diff_since`
  - 必要 web fetch/search 工具
  - 不恢复 browser 作为默认，除非 profile 明确开启。
  - 常驻清单由各 tool source 的 `prompt.default_tool_schema_group_refs` 声明并由 Context Workspace mirror 进 provider request；不要在 orchestration 增加联想 route。

### 验收

- 模型能从 tool schema 看出 exec 可做环境探测。
- exec 失败时 stderr 原文进入 model-visible output。
- 长输出被截断时有 `truncated=true` 和 artifact/ref 可追溯。

## 5. Prompt / Runtime Contract

### 目标

减少方向干涉，强化运行原则。

### 改造项

runtime contract 保留原则：

- 先理解任务，再选择工具。
- 遇到动态网站，可以使用可用工具检查页面、脚本、网络、环境。
- shell 可用于验证假设，不确定时可以先小步探测。
- 工具失败后根据错误调整路径。
- 不伪造实时数据。
- 阶段性说明发现和下一步。

runtime contract 移除或避免：

- 固定指向 urllib。
- 固定指向某种 browser/CDP。
- 固定要求抓 JS。
- 过度任务特化的 endpoint 探测模板。

### 验收

- Prompt 不再诱导模型只走某一种 Web 探索路线。
- 长链任务中每 3-5 个工具调用至少出现一次有效 progress message，除非 provider 不返回。
- 最终回答包含证据链。

## 6. Workbench / Operations

### 目标

用户看到 Codex-like 的执行过程，但 provider/internal 噪声保持可折叠。

### 改造项

Timeline item types：

- user message
- agent progress
- tool call
- tool result
- approval required
- provider warning
- transport fallback
- evidence checkpoint
- final answer

显示策略：

- `agent_progress`: 默认显示。
- `reasoning_summary`: 默认可折叠显示，按 provider policy。
- `function_call`: 显示工具名、参数摘要、状态。
- `function_call_output`: 默认摘要，raw output 可展开。
- `provider_error`: 显示用户可操作提示。
- `transport_event`: debug 区展示，关键 fallback 可在 timeline 展示。

Operations 增加：

- LLM invocation actual payload preview。
- transport distribution。
- continuation hit/miss。
- input item count / delta count。
- token/request growth curve。
- tool/result fact visibility and debug metadata。

### 验收

- 用户能看到“我发现了什么，下一步做什么”。
- 用户能看到失败原因和处理建议。
- Debug 视图能确认本轮是否 WebSocket/delta。
- Timeline 不再出现裸 `none; end_turn=-; follow_up=false` 这类内部字段。

## 7. Session Module

### 目标

Session 不再是单一聊天 message 镜像，而是 response item history 和 model-visible replay policy 的持久化基础。

### 改造项

- session item schema：
  - `item_type`
  - `role`
  - `content`
  - `provider_item_id`
  - `source_module`
  - `source_invocation_id`
  - `user_visible`
  - `model_visible`
  - `timeline_visible`
  - `raw_payload_ref`
- model-visible replay policy：
  - 默认包含用户任务 + active task state + structured ResponseItem replay。
  - provider-native continuation 只发送 delta input；当前 Codex runtime gate 关闭时不走该分支。
  - HTTP structured replay 时按 policy 选择 replay items，不把树当 transcript。
  - provider fallback transcript replay 时，按 policy 降级为 compacted messages。
- user-visible policy：
  - Workbench timeline 从 operations/session projection 读。
  - 不要求 session 与 UI 一一镜像。

### 验收

- agent progress 可保存但不必作为普通 assistant chat message。
- provider-native continuation 启用时不会把所有历史 message 再塞给 provider；当前 Codex runtime gate 关闭时应明确显示 full replay。
- HTTP fallback 时可以生成 compact replay，而不是全量无限增长。

## 8. Testing And Audit

### 单元测试

- LLM adapter:
  - Codex HTTP 不发送 `previous_response_id`。
  - Codex WebSocket 底层 renderer/transport 后续轮可发送 `previous_response_id + delta input`。
  - Codex orchestration/runtime 默认链路在 gate 关闭时不传 provider-native continuation。
  - WebSocket prefix mismatch fallback full request。
- Orchestration:
  - response item stream 保存。
  - agent progress projection。
  - provider end_turn 与 no tool call 的组合判断。
  - runtime debug metadata 不进入 provider messages。
- Context Workspace:
  - 默认 compact projection。
  - 默认不输出 full tree XML。
  - tree replay tool output 可 model-visible。
- Tool:
  - exec raw output / stderr / exit code contract。
  - truncation + artifact ref。
- Workbench:
  - timeline item rendering。
  - internal provider fields 不裸露。

### 集成测试

- 一个 mock provider run：
  - 首轮返回 agent progress + tool call。
  - tool result 后返回 agent progress + tool call。
  - 最终返回 WAF blocked final。
  - 验证 timeline、session、operations、continuation state。
- 一个 real provider smoke：
  - 简单 shell 探测任务。
  - 验证模型会使用 exec 并产生 progress。
  - 不依赖真实航司网站成功。

### 回归基线

记录以下指标：

- LLM invocation count。
- tool call count。
- agent progress count。
- average input item count。
- provider transport。
- continuation hit rate。
- token/request growth。
- final evidence completeness。

## 施工顺序

## Phase 0: 决策冻结

- [x] 确认不做历史兼容，允许清库重建。
- [x] 确认 Codex HTTP 不再尝试 `previous_response_id`。
- [x] 确认 browser 不是本轮 P0。
- [x] 确认 tree replay 是 tool，不是每轮自动全量注入。

## Phase 1: LLM Response Item Contract

- [x] 定义 provider-neutral response item：`LlmResponseItem` 已覆盖 assistant message、reasoning、tool call、tool result、provider external、compaction、unknown，并带 `model_visible` / `user_visible` / provider item refs。
- [x] 定义 provider-neutral request input item：新增 `LlmInputItem(kind, payload, source, metadata)` 和 `LlmInputItemKind`，用于承载 Codex-like `input` replay，不再只能把历史压成 `LlmMessage`。
- [x] LLM invocation/request 管道承载 input item：`InvokeLlmInput`、`StreamLlmInput`、`LlmInvocation`、`LlmAdapterRequest`、`llm_invocations.input_items`、HTTP DTO 均已接入。
- [x] OpenAI Responses / Codex Responses adapter 优先使用 projected input item：当 `request.input_items` 非空时，provider `input` 从 projected items 生成；`messages` 保留为兼容和非 Responses provider fallback。
- [x] Adapter 输出完整 item stream：OpenAI/Codex 主路径与 Chat-compatible/Anthropic/Gemini 最小路径已通过 `LlmAdapterResponse.response_items` 进入 owner module。
- [x] 持久化 provider response id 和 request preview：`LlmInvocation.provider_request_id`、`provider_request_payload_preview`、`response_items` 已进入 domain/repository/HTTP DTO/Operations detail。
- [x] Operations 能查询 item stream：LLM invocation list/detail 已返回 `response_items`，Operations LLM detail 已有 Response Items table。
- [x] Response event 保留窗口策略显式化：LLM owner module 已暴露 `LlmResponseEventRetentionPolicy`，默认完整短期窗口为 24h、detail limit 为 100、长期 durable fact 为 completed response items；Operations LLM detail 已展示该策略。后续 prune/采样任务可在此 contract 上继续扩展。

## Phase 2: Agent Progress Lifecycle

- [x] 识别 provider text/progress item：orchestration 已按 `LlmResponseItem.phase/kind` 区分 commentary、final answer、reasoning summary、tool call、provider external。
- [x] 保存为 run/session item：`EngineSessionRecorder.append_llm_response_items()` 已把可记录 response item 写入 `SessionItem`，并保留 source refs、call id、provider item id/type、可见性。
- [x] Workbench timeline 默认展示：Workbench run read model 已投影 `assistant_commentary`、`reasoning_summary`、`agent_progress`、`tool_call`、`provider_external_item`、`final_answer`；hidden reasoning 仅展示 presence/count。
- [x] model-visible policy 回灌必要 progress/evidence。
- [x] 空 progress / 兜底 progress 禁止进入 UI。

## Phase 3: Tool Surface Alignment

- [x] 重写 exec tool description。
- [x] 标准化 raw tool result contract：`ToolResultEnvelope` 已带 `schema_version=2026-06-14.tool_result_envelope.v1`，并分层输出 model/user/trace payload、read handles、artifact refs、truncation facts。
- [x] 长输出 raw/artifact 双轨：`exec` 截断 stdout/stderr 使用 raw output blocks，Tool worker 外置 raw output / large text 为 artifact refs 并合并回 envelope。
- [x] 默认常驻工具清单收敛：`command`、`web`、`context_tree` source prompt policy 已覆盖 `exec/process`、public fetch、Context Tree read/replay/diff。

## Phase 4: Context Tree Replay Tool

- [x] 新增 read/replay current surface 工具：现有 `context_tree.render_current`、`context_tree.read_snapshot`、`context_tree.diff_since` 覆盖当前 surface、snapshot replay 和 diff。
- [x] 默认 compact projection，完整树只通过显式工具/调试进入模型：实际 provider request 只默认注入 `context_workspace_projection`，不注入 `context_workspace_delta` / full tree XML，也不在 LLM request metadata 携带 `context_delta` 原文；完整 tree XML 保留在 `context_surface.rendered_context` 供审计/调试和显式 `context_tree.*` 工具读取。
- [x] tree surface fingerprint 进入 request preview。
- [x] Workbench 展示当前 model-visible surface：LLM linked entity detail 已返回并可读展示 `model_visible_surface` 摘要。

## Phase 5: Codex WebSocket Transport

- [x] 新增 Codex WebSocket adapter。
- [x] 实现 `response.create`。
- [x] 底层 renderer/transport 实现 `previous_response_id + delta input`。
- [x] 底层 renderer/transport 实现 fallback full request。
- [x] Codex runtime gate 当前关闭 provider-native continuation，真实 orchestration 链路回放 full clean input。
- [x] Operations / Workbench 显示 transport/fallback。

## Phase 6: Orchestration Loop Governance

- [x] 从 tool-call 二元 loop 升级为 response-item loop：ToolRun 创建已从 `LlmResponseItem(kind=tool_call)` 派生，response item id 进入 execution chain/session refs，legacy `LlmResult.tool_calls` 仅保留兼容 fallback。
- [x] Orchestration request envelope 生成 provider-neutral input item：`PromptTranscript` 已从 `SessionItem` 直出 `LlmInputItem`，`ProviderPromptRequestBuilder` 优先保留 session item 的 `reasoning` / `function_call` / `function_call_output` / `provider_external_item` 语义，并把 context projection 等新增 prompt message 按 message item 补入；最终通过 `OrchestrationEngineLlmInvoker` 传入 LLM module。
- [x] 完成 end_turn / pending tool / pending approval / fallback 判断：`provider_end_turn_false` 无 tool call 时继续 follow-up；pending approval/tool wait 已进入 continuation state；Codex 当前不生成 provider-native continuation state，Workbench/Operations 应显示 full replay/no previous response id；未来恢复 WebSocket delta 需单独 gate。
- [x] evidence ledger 默认路线已取消：通用 agent loop 不再维护跨任务证据裁判账本；Context Tree 默认根已移除 `evidence.frontier`，Session segment 不再自动挂 `Current Evidence Ledger` / browser investigation warning；Context Workspace 不再从 run metadata 生成 `evidence_frontier_node`、snapshot `evidence_frontier` 或 `evidence_delta`；Tool / Session / Context Workspace / Operations 保持各自事实，provider transcript 负责把事实清楚交给模型。
- [x] loop budget 与纠偏策略已降级为 debug / Operations：`runtime_loop_correction` 不再作为 model-visible system hint 注入 provider input，避免用不可穷举阈值干扰 LLM 自主判断。
- [x] Context delta 已从 provider-facing request 收敛：默认请求不回放 full tree，不注入 `context_workspace_delta` message，也不在 LLM request metadata 携带 `context_delta` 原文；模型需要树状态时通过显式 `context_tree.*` 工具读取。
- [x] Codex transport 已修正 projection 归属：Context Slice 在 runtime request builder 中先转为中立 `LlmInputItem` / active Tool Surface；Codex renderer 只按 OpenAI Responses wire contract 渲染这些 items，不把 tree/slice metadata 合并进 `instructions`。

## Phase 7: Workbench / Operations Projection

- [x] Timeline item type 完整投影。
- [x] provider warning / transport fallback 可见。
- [x] raw tool output 可展开。
- [x] failure guidance 用户可见。

当前增量：

- Workbench tool lifecycle 已能在 `tool_result` 中展示 `result_summary`、`exit_code`、`truncated` 和 `read_handles`，避免工具结果只显示兜底文案。
- Workbench / Trace linked entity detail 已支持 `tool_run`，可展开查看 ToolRun payload、`result_envelope`、`read_handles`、`raw_output_blocks`、artifact/evidence refs。
- 非 access 类 failed run 已生成用户可见 `Failure guidance` markdown，并同步进入 Workbench steps 与 timeline content。
- Timeline kind 已收敛到目标集合：`approval_required -> approval`、`missing_access -> wait_state`、`agent_thinking -> reasoning_summary`、`evidence_frontier -> system_event(event_type=evidence_frontier)`；steps API 仍保留原交互 type。

## Phase 8: Smoke And Baseline

- [x] 跑 mock long-chain agent。
- [x] 跑 real exec exploration smoke。
- [x] 对比 Codex HTTP-only 东航链路指标：已完成路径级对照；Codex HTTP-only 未保存同口径 baseline JSON，因此不伪造 `llm_calls/tool_calls` 数字，数值化复跑作为后续可选采样。
- [x] 更新进度 dashboard。

当前增量：

- `loop_regression_baseline` 已补充 Codex-like 长链验收指标：
  - `llm_response_item_count`
  - `llm_reasoning_response_item_count`
  - `llm_reasoning_text_item_count`
  - `llm_assistant_message_response_item_count`
  - `llm_tool_call_response_item_count`
  - `llm_response_item_missing_count`
  - `llm_text_tool_call_steps`
  - `llm_tool_only_steps`
  - `loop_health`

### Codex HTTP-only vs CRXZipple 当前链路

| 维度 | Codex HTTP-only 观测 | CRXZipple 当前观测 |
| --- | --- | --- |
| Continuation | HTTP path 不携带 `previous_response_id`，全量 `input` 回放，长链会触发 TPM 压力；WebSocket 源码 path 支持 delta | 当前 CRXZipple Codex runtime gate 已禁用 provider-native continuation，真实 orchestration 链路应显示 full replay / no previous response id；底层 WebSocket renderer/transport delta 能力仅受测保留 |
| 探索路线 | PC 官网 WAF 后切移动站，抓 bundle，定位 `/m-base/sale/shoppingv2`，反解 `wbsk_*` 加密，尝试 cookie replay | 真实 run `8ab370783a34472a9414070aec200267` 已能用 `exec` 做动态站点探索并最终不伪造票价 |
| 最终结果 | 未拿到真实票价，因阿里云 WAF challenge 阻断而拒绝编造 | `status=completed`，final answer 含 verified/gap/unavailable evidence，不声称伪造票价 |
| 阶段总结 | 工具之间有清晰阶段说明和路径切换原因 | 后端 timeline 已投影 `reasoning_summary=16`、`agent_progress=2`，仍需降低空 reasoning/tool-only streak |
| Baseline 数字 | 本轮未保留与 CRXZipple 同 schema 的 Codex baseline JSON | `llm_calls=32`、`tool_calls=31`、`llm_response_item_count=64`、`evidence_frontier_item_count=29`、`first_endpoint_discovery_step=4`、`first_candidate_validation_step=60` |
| 当前差距 | Codex 的 HTTP-only 也不是高效 continuation，但阶段整理和证据归因更稳定 | 剩余差距集中在 tool result 事实可见性、失败原因归因和阶段性 progress 稳定性 |
  - `tool_only_streak_segments`
  - `validation_lag_suspected`
  - `tool_result_items`
  - `tool_result_summary_count`
  - `tool_result_exit_code_count`
  - `tool_result_read_handle_count`
  - `tool_result_truncated_count`
  - `evidence_frontier_item_count`
  - `verified_evidence_count`
  - `remaining_gap_count`
  - `failed_evidence_path_count`
- 已新增 mock 长链回归：模拟 agent progress -> exec endpoint discovery -> exec validation/WAF blocked -> final without fabricated fare data，验证 progress、tool result contract、evidence frontier、endpoint discovery/validation delta 和 final evidence completeness。
- 已新增 response-item aware 回归：通过 `llm_response_item_ids` 解引用真实 `LlmResponseItem`，把 `reasoning + tool_call` 区分于纯 tool-only invocation，避免把 provider 已生成的 reasoning summary 误判为无阶段性 progress。
- 已新增真实 exec runtime probe 回归：执行真实 Python 探测命令，验证 `summary`、`stdout`、`stderr`、`exit_code`、`cwd`、`shell` 等 facts 进入 model-visible envelope。
- 已修复 raw output 外置后的 envelope merge：当 raw output 被外置为 artifact 后，`read_handles` 以 artifact 为最终可读位置，不再保留已被搬移的 `raw_output_block` handle。
- 已修复 tree-backed protocol replay：execution chain 的 tool call/result protocol refs 统一指向 session item，Context Slice 对结构化 tool call/result 保留模型投影能力，防止下一轮 request 只剩孤儿 `function_call_output`。
- `orchestration baseline` CLI 已接入 LLM response item resolver；能从 LLM module 的 persisted response item truth 计算 reasoning/tool-call/assistant item 指标，summary payload 只作为 fallback。
- Workbench LLM step diagnostics 已改为 response item 优先：有 reasoning summary 文本的 LLM step 会显示 `progress recorded`，tool-only streak 不再被旧 summary 口径误放大。
- Workbench timeline 前端已把可见 `reasoning_summary` 映射为阶段总结进展项，并按 markdown 渲染正文；hidden reasoning 仍只展示 presence/count，不泄露 raw reasoning。
- SessionItem prompt replay 已保留当前 turn 内有正文的 `reasoning` / assistant commentary progress，即使在 protocol-only normal turn replay 中也不会丢失模型刚形成的阶段性发现；旧 turn progress 仍不随 protocol-only replay 全量回放。
- Workbench fallback step timeline 已增加真实内容门禁：旧 step 投影中的 `agent_progress` / `agent_thinking` 必须有 summary 或 markdown 才进入 timeline，避免空进展或兜底标题误导用户。
- `orchestration baseline` 已新增 `loop_health`：输出 tool-only streak 分段、当前/最大 streak、validation delta、warning threshold 和 `tool_only_streak` / `validation_lag` 告警，便于把“空 reasoning streak”从人工观察变成可治理指标。
- Workbench inspector debug 已新增 `Loop Health` 区块，直接复用 response-item aware baseline 的 `loop_health`，展示 warnings、最大/当前 tool-only streak、tool-only 分段数、validation delta 和 validation lag 状态；baseline 不可用时只显示 `unavailable`，不伪造健康状态。
- `runtime_loop_correction` 已按最新决策从 model-visible hint 降级为 request metadata / Operations debug；它可以帮助用户审计，但不再要求模型按固定阈值改变探索策略。
- Operations LLM invocation detail 已新增 `runtime_hints` section，把 request metadata 中的 `runtime_loop_correction` 和 `runtime_evidence_frontier` 投影为可读摘要；Workbench linked entity detail 已支持 `llm_invocation`，用户可从 timeline/inspector 链路查看该轮 runtime debug 记录的 loop correction warnings 与 evidence frontier 计数。
- Operations LLM lifecycle events 已新增 `Transport`、`Continuation`、`Input Delta` 列；当前 Codex orchestration 链路应显示 `has_previous_response_id=false`、`input_delta_mode=false`、full replay。底层 WebSocket incremental request 的 `previous_response_id=...` / `delta=...` 仅通过 adapter/transport 回归验收，恢复到 runtime 默认链路前必须先完成 turn-scoped gate 设计。
- LLM profile warmup 已从内部 service 扩展到 HTTP/CLI/Settings UI/Operations action：`POST /llms/{llm_id}/warmup`、`llm warmup <llm_id>`、LLM Profiles 页面 Warmup 按钮和 `POST /operations/llm/profiles/{llm_id}/warmup` 可在正式长链前验证 Codex WebSocket profile credential/transport/connection reuse。所有入口走 `llm.warmup` 授权动作，且不创建 invocation；Operations 入口额外写 action audit，warmup 成功/跳过/失败仍发布 LLM owner event，并进入 Operations lifecycle event、Provider Access 表和下一步处理建议。
- `runtime_evidence_frontier` 已按最新决策从 model-visible digest 降级为 request metadata / Operations debug；debug payload 使用 `observed_count / uncertain_count / failed_count`，不再输出 `verified/gap` 行为结论给模型。
- 已对真实东航长链 run `8ab370783a34472a9414070aec200267` 跑 baseline：
  - `status=completed`
  - `llm_calls=32`
  - `llm_response_item_count=64`
  - `llm_reasoning_response_item_count=32`
  - `llm_reasoning_text_item_count=14`
  - `llm_assistant_message_response_item_count=1`
  - `llm_tool_call_response_item_count=31`
  - `llm_response_item_missing_count=0`
  - `llm_text_tool_call_steps=14`
  - `llm_tool_only_steps=17`
  - `max_consecutive_llm_tool_only_steps=4`
  - `loop_health.warnings=["tool_only_streak", "validation_lag"]`
  - `tool_calls=31`
  - `tool_result_items=31`
  - `tool_result_summary_count=29`
  - `tool_result_read_handle_count=25`
  - `tool_result_truncated_count=15`
  - `evidence_frontier_item_count=29`
  - `first_endpoint_discovery_step=4`
  - `first_candidate_validation_step=60`
  - `candidate_discovery_to_validation_delta=56`
  - `final_answer_has_verified_facts=true`
  - `final_answer_has_gaps=true`
  - `final_answer_has_unavailable_evidence=true`
  - `metrics_missing=[]`

说明：本项已证明真实 agent 能使用 `exec` 做动态站点探索，并最终不伪造票价。response-item aware baseline 修正了旧口径误判：并非 31 轮全部 tool-only；真实情况是 14 轮存在 reasoning summary + tool call，17 轮为空 reasoning + tool call，最大空 reasoning/tool-only streak 为 4。Workbench run view 后端已能投影 reasoning summary 文本，真实 timeline 包含 `reasoning_summary=16`、`tool_call=31`、`agent_progress=2`、`final_answer=1`；前端已把可见 reasoning summary 从普通 LLM thinking 改为“阶段总结”进展项；SessionItem protocol-only replay 已保留当前 turn 有正文的 reasoning/progress；旧 fallback step timeline 已禁止空进展入 UI；Workbench inspector debug 已能直接展示 `loop_health`；`runtime_loop_correction` 和 `runtime_evidence_frontier` 已按最新决策降级为 request metadata / Operations / Workbench debug，不再注入 provider input。`loop_health` 已把剩余问题明确成两个 warning：`tool_only_streak` 与 `validation_lag`。后续治理重点从“模型完全没有阶段总结”收窄为：降低空 reasoning streak，并继续缩短 discovery -> validation delta。

## 关键验收场景

### 场景 A: Shell 探索能力

用户请求：检查一个本地项目如何启动。

期望：

- 模型先用 `rg/ls` 探测。
- 产生 progress：“我先看 package/Makefile/README”。
- 执行命令失败后根据 stderr 改路径。
- 最终给出可验证结论。

### 场景 B: 动态网站失败归因

用户请求：查询一个依赖 JS 的官网实时信息。

期望：

- 模型尝试官网入口。
- 遇到 JS/WAF 后切换到源码/接口/环境探测。
- 如果被 WAF 阻断，最终明确说明证据。
- 不编造实时结果。

### 场景 C: Provider Continuation

长链任务 10 轮以上。

期望：

- WebSocket provider 后续轮 request 为 delta。
- HTTP fallback 明确标记。
- token/request 不线性爆炸。
- Workbench 能看见 fallback 原因。

## 风险

- 过度强化 shell 可能让模型更爱写脚本而忽略已有高阶工具。
  - 缓解：工具说明强调“选择最合适工具”，不要强制 shell 优先。
- agent progress 过多会污染上下文。
  - 缓解：user-visible 与 model-visible 分离，回灌 evidence digest 而不是所有文本。
- WebSocket adapter 初期不稳定。
  - 缓解：fallback full request，但必须可观测。
- tree replay tool 被模型频繁调用。
  - 缓解：工具输出 concise surface + 可选 detail。

## 最终判定标准

完成后，CRXZipple 不必复制 Codex 的私有 hosted 工具，但应达到以下能力：

- 同一模型下，遇到复杂 Web/本地工程任务时，会主动探测环境和切换路径。
- 用户能看到稳定的阶段性说明。
- 失败结论有完整证据链。
- provider request 不再无脑全量膨胀。
- Context Tree 仍是唯一 agent-facing context surface。
- Operations 能解释一次 run 为什么成功、失败、退化或卡住。
