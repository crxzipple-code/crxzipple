# CRXZipple Docs Index

本目录只保留当前仍可作为施工依据的文档。历史评审、启动计划和外部参考已移到 `docs/archive/`，只能作为背景材料，不能作为当前实现约束。

## Agent 入口

- [../AGENTS.md](../AGENTS.md)：仓库级托管 agent 入口。
- [agents/hosted-agent-operating-contract.md](agents/hosted-agent-operating-contract.md)：完整托管 agent 开发约束。

## 查验与报告

- [reports/code-quality-followup-checklist-20260506.md](reports/code-quality-followup-checklist-20260506.md)：当前仍需处理的代码规范性问题清单。

已关闭的历史审计和整改报告放在 `docs/archive/reports/`，只作背景，不作为当前待办入口。

## 当前架构约束

- [orchestration-design.md](orchestration-design.md)：orchestration 模块边界、service graph、scheduler/executor/engine 分工。
- [operations-data-truth-audit.md](operations-data-truth-audit.md)：Operations 数据真相、observer、projection 和缺口。
- [dispatch-design.md](dispatch-design.md)：dispatch 调度域边界。
- [session-semantics-design.md](session-semantics-design.md)：session 语义和边界。
- [memory-space-design.md](memory-space-design.md)：memory space 和 durable knowledge 模型。
- [memory-rewrite-cutover.md](memory-rewrite-cutover.md)：memory 重构后的当前状态。
- [instruction-assets-memory-auth-design.md](instruction-assets-memory-auth-design.md)：skill、memory、access、authorization 的关系。
- [agent-workspace-bootstrap-design.md](agent-workspace-bootstrap-design.md)：agent workspace bootstrap 设计。

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
