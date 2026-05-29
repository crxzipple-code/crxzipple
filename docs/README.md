# CRXZipple Docs Index

本目录只保留当前仍可作为施工依据的文档。历史评审、启动计划和外部参考已移到 `docs/archive/`，只能作为背景材料，不能作为当前实现约束。

## Agent 入口

- [../AGENTS.md](../AGENTS.md)：仓库级托管 agent 入口。
- [agents/hosted-agent-operating-contract.md](agents/hosted-agent-operating-contract.md)：完整托管 agent 开发约束。

## 查验与报告

- [reports/closure-status-20260525.md](reports/closure-status-20260525.md)：当前收口状态、验证结果、版本控制边界和剩余风险。
- [reports/code-quality-followup-checklist-20260506.md](reports/code-quality-followup-checklist-20260506.md)：代码规范性问题收口记录和防回归验收入口；F1-F16 当前均已处理。
- [reports/access-module-stabilization-checklist-20260512.md](reports/access-module-stabilization-checklist-20260512.md)：Access 稳定化主清单；外部凭证、OAuth、app credential、LLM/Tool/Channel 接入、Settings/Operations 页面均以此为当前施工入口。
- [reports/app-assembly-container-target-checklist-20260514.md](reports/app-assembly-container-target-checklist-20260514.md)：App Assembly / Container Target 重构主清单；旧 `build_container` 手写装配已退役，后续 target container、tool capability 上限和旧路径删除验收以此为施工入口，不接受最小迁移或兼容双轨。
- [reports/port-usecase-boundary-remediation-checklist-20260516.md](reports/port-usecase-boundary-remediation-checklist-20260516.md)：App Assembly cutover 后的 Port / Use Case 边界整改清单；收口 Session tools 控制语义、Orchestration submit/process port、Tool queue/worker surface 和跨模块 concrete service 依赖。
- [reports/pytest-runtime-governance-checklist-20260518.md](reports/pytest-runtime-governance-checklist-20260518.md)：Pytest 全量运行变慢与卡住风险的治理记录；默认 unit 热路径不得真实跑 benchmark/live 多 worker 场景。
- [reports/runtime-defaults-governance-checklist-20260522.md](reports/runtime-defaults-governance-checklist-20260522.md)：Runtime Defaults 治理主清单；收口 Settings-owned runtime control defaults、env 首次 seed、typed materializer、assembly 注入和重启/生效语义。
- [reports/tool-engineering-architecture-upgrade-checklist-20260519.md](reports/tool-engineering-architecture-upgrade-checklist-20260519.md)：Tool Source / Tool Function Catalog / Tool Runtime 工程架构升级主清单；收口 `tool.yaml`、MCP、OpenAPI、CLI、provider backend 到 Tool-owned catalog，不接受长期双轨兼容。
- [reports/browser-tool-source-profile-runtime-redesign-plan-20260525.md](reports/browser-tool-source-profile-runtime-redesign-plan-20260525.md)：Browser Tool Source / Profile Runtime 重构计划；退役 per-profile Browser MCP Source，把 browser capability 收成一个 Tool Source，profile 作为运行上下文。
- [reports/browser-profile-pool-multi-ip-collection-plan-20260526.md](reports/browser-profile-pool-multi-ip-collection-plan-20260526.md)：Browser Profile Pool / 多 IP 采集开发计划；补 Browser Profile CRUD、Access 代理凭证、Profile Pool、Allocator、Operations 观察和端到端验收。
- [reports/browser-agent-tooling-capability-upgrade-plan-20260528.md](reports/browser-agent-tooling-capability-upgrade-plan-20260528.md)：Browser agent-facing 工具能力升级方案；把 CDP 网络、DOM、Storage、Context Lease、Diagnostics 收成顺手的 `browser.*` 工具，而不是裸露 raw CDP。
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
- [session-semantics-design.md](session-semantics-design.md)：session 语义和边界。
- [memory-space-design.md](memory-space-design.md)：memory space 和 durable knowledge 模型。
- [memory-rewrite-cutover.md](memory-rewrite-cutover.md)：memory 重构后的当前状态。
- [instruction-assets-memory-auth-design.md](instruction-assets-memory-auth-design.md)：skill、memory、access、authorization 的关系。
- [context-workspace-prompt-tree-design.md](context-workspace-prompt-tree-design.md)：树化 Prompt / Context Workspace 目标设计；把 tool、skill、memory、session、artifact、workspace 收成 agent 和本地 runtime 共治的上下文树。
- [agent-workspace-bootstrap-design.md](agent-workspace-bootstrap-design.md)：agent workspace bootstrap 设计。
- [tool-credential-requirements-guide.md](tool-credential-requirements-guide.md)：Tool 外部凭证 requirement/slot 开发约束。
- [../tools/README.md](../tools/README.md)：内置 Tool source authoring contract。
- [channel-credential-requirements-guide.md](channel-credential-requirements-guide.md)：Channel 账号凭证 slot 与 Access binding 开发约束。

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
