# CRXZipple Docs Index

本目录只保留当前仍可作为施工依据的文档。历史评审、启动计划和外部参考已移到 `docs/archive/`，只能作为背景材料，不能作为当前实现约束。

## Agent 入口

- [../AGENTS.md](../AGENTS.md)：仓库级托管 agent 入口。
- [agents/hosted-agent-operating-contract.md](agents/hosted-agent-operating-contract.md)：完整托管 agent 开发约束。

## Reference

- [reference/codex-prompt-engineering-reference.md](reference/codex-prompt-engineering-reference.md)：Codex 最终 LLM 请求结构、prompt/context/tool 注入方式和工程行为偏置参考。
- [reference/claude-code-prompt-engineering-reference.md](reference/claude-code-prompt-engineering-reference.md)：Claude Code 最终 LLM 请求结构、system prompt、context/tool/compaction 工程参考。
- [reference/llm-provider-capability-matrix.md](reference/llm-provider-capability-matrix.md)：不同 provider/API family/model 的调用形态、response 能力和 CRXZipple 当前消化状态参考。

## 查验与报告

- [reports/closure-status-20260525.md](reports/closure-status-20260525.md)：当前收口状态、验证结果、版本控制边界和剩余风险。
- [reports/code-quality-followup-checklist-20260506.md](reports/code-quality-followup-checklist-20260506.md)：代码规范性问题收口记录和防回归验收入口；F1-F16 当前均已处理。
- [reports/access-module-stabilization-checklist-20260512.md](reports/access-module-stabilization-checklist-20260512.md)：Access 稳定化主清单；外部凭证、OAuth、app credential、LLM/Tool/Channel 接入、Settings/Operations 页面均以此为当前施工入口。
- [reports/app-assembly-container-target-checklist-20260514.md](reports/app-assembly-container-target-checklist-20260514.md)：App Assembly / Container Target 重构主清单；旧 `build_container` 手写装配已退役，后续 target container、tool capability 上限和旧路径删除验收以此为施工入口，不接受最小迁移或兼容双轨。
- [reports/port-usecase-boundary-remediation-checklist-20260516.md](reports/port-usecase-boundary-remediation-checklist-20260516.md)：App Assembly cutover 后的 Port / Use Case 边界整改清单；收口 Session tools 控制语义、Orchestration submit/process port、Tool queue/worker surface 和跨模块 concrete service 依赖。
- [reports/pytest-runtime-governance-checklist-20260518.md](reports/pytest-runtime-governance-checklist-20260518.md)：Pytest 全量运行变慢与卡住风险的治理记录；默认 unit 热路径不得真实跑 benchmark/live 多 worker 场景。
- [reports/runtime-defaults-governance-checklist-20260522.md](reports/runtime-defaults-governance-checklist-20260522.md)：Runtime Defaults 治理主清单；收口 Settings-owned runtime control defaults、env 首次 seed、typed materializer、assembly 注入和重启/生效语义。
- [reports/tool-engineering-architecture-upgrade-checklist-20260519.md](reports/tool-engineering-architecture-upgrade-checklist-20260519.md)：Tool Source / Tool Function Catalog / Tool Runtime 工程架构升级主清单；收口 `tool.yaml`、MCP、OpenAPI、CLI、provider backend 到 Tool-owned catalog，不接受长期双轨兼容。
- [reports/context-workspace-tool-bundle-grouping-upgrade-plan-20260531.md](reports/context-workspace-tool-bundle-grouping-upgrade-plan-20260531.md)：Context Workspace Tool Bundle 分组升级计划；把 `tools.available` 从关键词语义分组收敛为 Source-first 能力包，source 作为稳定边界，prompt metadata 作为 LLM-facing 标题和摘要。
- [reports/context-workspace-session-history-delivery-upgrade-plan-20260531.md](reports/context-workspace-session-history-delivery-upgrade-plan-20260531.md)：Context Workspace Session History Delivery 历史施工记录；把 normal turn 的历史对话从 direct transcript replay 收归 prompt tree，session 持有事实，Context Workspace 负责交付。当前节点命名以 `session.segment.*` 为准。
- [reports/context-workspace-session-segment-compaction-plan-20260601.md](reports/context-workspace-session-segment-compaction-plan-20260601.md)：Context Workspace / Session 历史压缩历史施工记录；把 prompt tree 压缩边界从 archived messages 收敛为 SessionInstance / SessionSegment 轮转，明确 skill 深入阅读走普通工具而不是特殊 context tree resource 工具。当前术语以 [session-semantics-design.md](session-semantics-design.md) 为准：SessionInstance 是 SessionSegment，Context Workspace 节点使用 `session.segment.*`。
- [reports/prompt-engineering-runtime-contract-upgrade-plan-20260605.md](reports/prompt-engineering-runtime-contract-upgrade-plan-20260605.md)：Prompt Engineering Runtime Contract 升级记录；文件化 runtime 总叙述，挂入 `context.instructions`，拆清 agent home 多文件与 project/workspace resources，不修改 turn / run 状态机。
- [reports/engineering-agent-runtime-upgrade-plan-20260607.md](reports/engineering-agent-runtime-upgrade-plan-20260607.md)：Engineering Agent Runtime 升级计划；吸收 Codex / Claude Code reference，把工程任务中的定位、实施、验证、工具结果 continuation、历史压缩和最终请求可观察性落成当前施工清单。
- [reports/context-workspace-tree-schema-convergence-plan-20260607.md](reports/context-workspace-tree-schema-convergence-plan-20260607.md)：Context Workspace Tree Schema 收口记录；`context.instructions` 已成为真实树节点，`execution.current` 已收出本次执行现场，并明确 session、execution、instructions 与能力 roots 的边界。
- [reports/prompt-engine-layered-refactor-plan-20260608.md](reports/prompt-engine-layered-refactor-plan-20260608.md)：Prompt Engine 分层重构施工入口；把 Run 输入收集、Context Workspace render、provider request 组装、LLM 调用拆成清晰层级，不接受兼容双轨和补丁式 helper 堆积。
- [reports/orchestration-execution-chain-dispatch-convergence-plan-20260601.md](reports/orchestration-execution-chain-dispatch-convergence-plan-20260601.md)：Orchestration Execution Chain / Dispatch 收口开发方案；把异步 LLM/tool/approval 归并从 run metadata 收成 Turn / ExecutionChain / ExecutionStep / StepItem，并让 `dispatch_tasks` 成为唯一 durable work queue。
- [reports/prompt-engineering-codex-path-absorption-plan-20260609.md](reports/prompt-engineering-codex-path-absorption-plan-20260609.md)：Codex 路径吸收施工入口；把模型执行引导、环境上下文、tool surface policy、tool result normalize、browser investigation route 和 final request inspectability 收成明确开发清单。
- [reports/browser-tool-source-contract-convergence-plan-20260610.md](reports/browser-tool-source-contract-convergence-plan-20260610.md)：Browser Tool Source 扶正施工入口；把 `configured.browser` 手写动态 source 干净收敛为标准 `tools/browser/tool.yaml` bundled local package，不保留 alias 或双路兼容。
- [reports/agent-runtime-contract-upgrade-progress-dashboard-20260611.md](reports/agent-runtime-contract-upgrade-progress-dashboard-20260611.md)：LLM 能力释放 / Codex parity baseline 整体升级进度看板；按 LLM、Orchestration、Session、Context Workspace、Tool、Operations、Workbench 等模块展示文档、施工、风险、依赖和下一步。
- [reports/llm-provider-protocol-rendering-boundary-refactor-plan-20260615.md](reports/llm-provider-protocol-rendering-boundary-refactor-plan-20260615.md)：LLM Provider Protocol Rendering 边界重构入口；把 provider/transport/model request rendering 与 response parsing 对称收归 LLM adapter / renderer，Context Tree 只作为 runtime canonical context，Orchestration 不再拼 provider prompt。施工硬约束：不兼容旧结构、不双轨并行、无法形成准确结论的内容不进入 LLM input、Codex 适配以抓包 trace 和源码事实为准、内核保持通用。
- [reports/session-runtime-projection-and-provider-request-renderer-plan-20260616.md](reports/session-runtime-projection-and-provider-request-renderer-plan-20260616.md)：Session Runtime Projection / Provider Request Renderer 详细开发方案；基于 Codex 源码确认 `ResponseItem -> TurnItem` 与 `Runtime transcript -> provider input` 的双向分层，定义 LLM response 保真、Session runtime transcript、tool result 入库、request renderer、Workbench/Operations 投影和 breaking migration 清单。
- [reports/runtime-request-render-snapshot-hot-path-refactor-plan-20260618.md](reports/runtime-request-render-snapshot-hot-path-refactor-plan-20260618.md)：Runtime Request Render Snapshot 热路径整改方案；把 LLM 调用前置链路从完整 Context Tree/debug snapshot 重建收敛为轻量 request render snapshot，完整树观察退出热路径，改由 Operations/Trace/Workbench 按需或异步生成。
- [reports/runtime-code-structure-convergence-plan-20260620.md](reports/runtime-code-structure-convergence-plan-20260620.md)：Runtime 代码结构治理方案；在已完成长链能力收口后，继续拆清 runtime request draft、LLM application service、tool execution observation、Context Workspace orchestration adapter 和 provider request preview 的职责边界，不引入兼容双轨或任务特化逻辑。
- [reports/runtime-code-quality-audit-20260621.md](reports/runtime-code-quality-audit-20260621.md)：Runtime 代码质量审查报告；基于当前大重构 diff 检查临时结构、边界漂移、大文件热点、provider/render/session/workbench 投影职责和下一轮收口优先级。
- [reports/system-readiness-code-quality-audit-20260621/README.md](reports/system-readiness-code-quality-audit-20260621/README.md)：上线前系统级代码质量审查；按模块分别评估边界清洁度、耦合、分层、生命周期、持久化、并发扩展和外部系统接入风险。
- [reports/provider-transcript-evidence-rendering-remediation-plan-20260615.md](reports/provider-transcript-evidence-rendering-remediation-plan-20260615.md)：Provider transcript / evidence rendering 历史整改记录；当前最新决策是不新增通用 EvidenceGate / EvidenceOutcomeClassifier，无法准确形成通用结论的证据裁判不进入 LLM input；browser path ladder / `evidence_path_*` 字段已退场，browser 只保留可验证 facts，是否完成由 LLM 基于 transcript 判断。
- [reports/browser-tool-source-profile-runtime-redesign-plan-20260525.md](reports/browser-tool-source-profile-runtime-redesign-plan-20260525.md)：Browser Tool Source / Profile Runtime 重构计划；退役 per-profile Browser MCP Source，把 browser capability 收成一个 Tool Source，profile 作为运行上下文。
- [reports/browser-profile-pool-multi-ip-collection-plan-20260526.md](reports/browser-profile-pool-multi-ip-collection-plan-20260526.md)：Browser Profile Pool / 多 IP 采集开发计划；补 Browser Profile CRUD、Access 代理凭证、Profile Pool、Allocator、Operations 观察和端到端验收。
- [reports/browser-agent-tooling-capability-upgrade-plan-20260528.md](reports/browser-agent-tooling-capability-upgrade-plan-20260528.md)：Browser agent-facing 工具能力升级方案；把 CDP 网络、DOM、Storage、Context Lease、Diagnostics 收成顺手的 `browser.*` 工具，而不是裸露 raw CDP。
- [reports/browser-agent-workbench-upgrade-plan-20260604.md](reports/browser-agent-workbench-upgrade-plan-20260604.md)：Browser Agent Workbench 历史施工入口；2026-06-10 后 Browser Tool Source 形态以 Browser Tool Source Contract Convergence Plan 为准，后续不再继续扩展 `configured.browser` catalog 路径。
- [reports/skill-governance-redesign-checklist-20260520.md](reports/skill-governance-redesign-checklist-20260520.md)：Skill 治理重构主清单；收口 Skills owner、Settings 操作面、Operations 观察面和 Orchestration 运行消费边界，不接受 Settings-owned enablement overlay 长期存在。
- [reports/skill-authoring-meta-skill-checklist-20260521.md](reports/skill-authoring-meta-skill-checklist-20260521.md)：Skill Authoring / Meta-Skill 施工清单；把“生成 skill 本身也是 skill”落成 agent-facing draft、validate、diff、approve、apply 链路。
- [reports/memory-engine-abstraction-upgrade-checklist-20260521.md](reports/memory-engine-abstraction-upgrade-checklist-20260521.md)：Memory Engine 抽象升级主清单；收口 Agent memory scope、Memory runtime surface、engine capability、Access credential、ToolExecutionContext 和 Operations/Settings 边界。
- [reports/memory-layered-access-upgrade-checklist-20260522.md](reports/memory-layered-access-upgrade-checklist-20260522.md)：Memory 分层访问升级清单；保持一个 agent 一个 identity scope，由 Memory runtime 生成 private/common/project/team/system layer access plan，支持受控公共记忆 recall/remember。
- [reports/module-lifecycle-tool-loading-checklist-20260513.md](reports/module-lifecycle-tool-loading-checklist-20260513.md)：Module 生命周期与 Tool 单次装载治理清单；收口 app assembly 装配顺序、Tool 二阶段装载、handler 跨模块依赖和 readiness。

已关闭的历史审计、Settings 过渡清单、Access/Tool/Channel 旧施工清单和
Browser MCP 旧路径清单放在
`docs/archive/reports/`，只作背景，不作为当前待办入口。

## 当前架构约束

- [orchestration-design.md](orchestration-design.md)：orchestration 模块边界、service graph、scheduler/executor/engine 分工。
- [operations-data-truth-audit.md](operations-data-truth-audit.md)：Operations 数据真相、observer、projection 和缺口。
- [dispatch-design.md](dispatch-design.md)：dispatch 调度域边界。
- [session-semantics-design.md](session-semantics-design.md)：session / segment / turn / execution chain / lane 语义和边界；memory 不参与当前 session 调度模型。
- [memory-space-design.md](memory-space-design.md)：memory space 和 durable knowledge 模型。
- [memory-rewrite-cutover.md](memory-rewrite-cutover.md)：memory 重构后的当前状态。
- [artifact-storage-policy.md](artifact-storage-policy.md)：Artifact 大 payload、下载、授权、保留期和 LLM raw request/response 外置策略。
- [ocr-capability-runtime-policy.md](ocr-capability-runtime-policy.md)：OCR engine capability metadata、capacity/concurrency owner 和大输出 artifact/ref 策略。
- [instruction-assets-memory-auth-design.md](instruction-assets-memory-auth-design.md)：skill、memory、access、authorization 的关系。
- [context-workspace-prompt-tree-design.md](context-workspace-prompt-tree-design.md)：树化 Prompt / Context Workspace 目标设计；把 tool、skill、memory、session、artifact、workspace 收成 agent 和本地 runtime 共治的上下文树。
- [context-workspace-prompt-tree-development.md](context-workspace-prompt-tree-development.md)：树化 Prompt / Context Workspace 详细开发文档；定义 domain、ports、storage、API、owner adapter、迁移阶段和验收清单。当前树结构以 2026-06-07 schema v2 为准；关于 session history 压缩与 skill 深入阅读边界，以 Session 历史压缩方案和 session 语义文档为准。
- [agent-workspace-bootstrap-design.md](agent-workspace-bootstrap-design.md)：agent workspace bootstrap 设计。
- [tool-credential-requirements-guide.md](tool-credential-requirements-guide.md)：Tool 外部凭证 requirement/slot 开发约束。
- [../tools/README.md](../tools/README.md)：内置 Tool source authoring contract。
- [channel-credential-requirements-guide.md](channel-credential-requirements-guide.md)：Channel 账号凭证 slot 与 Access binding 开发约束。
- [skill-source-trust-policy.md](skill-source-trust-policy.md)：Skill 外部 source、package provenance、signature 和 runtime visibility 信任边界。

## Channels

- [channels-events-blueprint.md](channels-events-blueprint.md)：channels + events 目标架构。
- [web-channel-guide.md](web-channel-guide.md)：web channel transport。
- [webhook-channel-guide.md](webhook-channel-guide.md)：webhook channel。
- [inbox-channel-guide.md](inbox-channel-guide.md)：inbox channel。
- [lark-channel-guide.md](lark-channel-guide.md)：Lark channel。

## UI

- [ui/current-ui-design-functional-spec.md](ui/current-ui-design-functional-spec.md)：当前 UI 设计稿功能规格。
- [ui/runtime-ui-read-model-contracts.md](ui/runtime-ui-read-model-contracts.md)：Workbench / Trace / Operations / Settings read model 契约。
- `ui/*.png`、`ui/operations/*.png`、`ui/settings/*.png`：当前设计稿图片。

## Archive

- [archive/README.md](archive/README.md)：归档文档清单。

归档文档不参与默认施工。若需要恢复其中的观点，必须先更新当前约束文档，再改代码。
