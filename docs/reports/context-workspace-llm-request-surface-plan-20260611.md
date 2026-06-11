# Context Workspace LLM Request Surface Plan 2026-06-11

本文记录 LLM request / response contract 升级后 Context Workspace 的目标形态：从“树化 prompt 渲染器”升级为 agent-facing request context surface owner。它负责把 Session model-visible facts、Context Tree 节点状态、provider attachment mirror、tool schema mirror 渲染成可追溯的 `ContextSurface`，供 Orchestration 放入 `LlmRequestEnvelope`。

关联文档：

- [provider-neutral-llm-response-stream-contract-plan-20260611.md](provider-neutral-llm-response-stream-contract-plan-20260611.md)
- [orchestration-llm-contract-driven-runtime-plan-20260611.md](orchestration-llm-contract-driven-runtime-plan-20260611.md)
- [session-module-response-item-migration-plan-20260611.md](session-module-response-item-migration-plan-20260611.md)
- [tool-surface-llm-request-contract-plan-20260611.md](tool-surface-llm-request-contract-plan-20260611.md)
- [operations-agent-runtime-projection-plan-20260611.md](operations-agent-runtime-projection-plan-20260611.md)
- [agent-runtime-contract-upgrade-testing-strategy-20260611.md](agent-runtime-contract-upgrade-testing-strategy-20260611.md)
- [../context-workspace-prompt-tree-design.md](../context-workspace-prompt-tree-design.md)
- [../context-workspace-prompt-tree-development.md](../context-workspace-prompt-tree-development.md)

## Cutover Assumption

开发前会清除并重建数据库。本计划不考虑旧 context node、旧 render snapshot、旧 prompt preview、旧 session transcript delivery 或旧 tool schema mirror 的兼容。

如果旧 Context Workspace schema 或旧 prompt renderer 阻碍 agent 最佳效果，应直接迁到新结构。migration 只服务新库初始化，不设计历史升级路径。

## 定位

Context Workspace 拥有 Context Tree、节点状态、估算和 render snapshot。它不拥有 LLM provider 真相、Session item 真相、Tool Source 真相或 Orchestration run lifecycle。

LLM 能力升级后，它向 Orchestration 提供：

```text
ContextSurface
  context_render_snapshot_id
  rendered_context
  included_node_refs
  collapsed_node_refs
  model_visible_fact_refs
  provider_attachment_mirror
  tool_schema_mirror
  estimate
  diagnostics
```

Orchestration 把 `ContextSurface` 放入 `LlmRequestEnvelope`；LLM adapter 再按 provider family 映射。

## 当前问题

### 1. Prompt 仍容易退回文本拼接

树化 prompt 已经确立，但 request side 若仍然只传一段 rendered text，后续无法回答：

- 本轮模型看到了哪些 SessionItem？
- 哪些 response item 被折叠或保留？
- 哪些 tool schema 被镜像给 provider？
- 当前 turn 的 provider protocol items 有没有被预算破坏？

### 2. Session transcript 和 Context Tree 边界要重整

旧方式容易把 session 历史当 role/content transcript。新 Session module 会输出 `SessionReplayItem` / `SessionItem` 事实流。Context Workspace 应选择、折叠、渲染这些 facts，而不是重新读取旧 message 表。

### 3. 当前 turn protocol facts 不能被当普通历史压缩

当前 execution chain 中的 tool_call/tool_result/function protocol items 对 provider replay 是硬约束，不能被普通预算策略折叠成摘要。

### 4. Tool schema mirror 需要和 ToolSurface 对齐

Context Tree 展示 agent 可见的工具 source/group/schema 状态。Tool module 提供执行 truth 和 `ToolSurface`。Context Workspace 只能 mirror 可见 schema，不重新定义 tool source 或 runtime policy。

## 目标

### 必须达成

1. Context Workspace 提供 `ContextSurface` 给 Orchestration request builder。
2. render snapshot 记录 included/collapsed SessionItem、LlmResponseItem、ToolRun、ContextNode refs。
3. 当前 turn provider protocol items 标记为 `protocol_required`，不可被预算折叠破坏。
4. 历史 session facts 可被折叠、压缩、展开，但必须保留 source refs。
5. provider attachment mirror 和 tool schema mirror 都从 Context Tree 节点派生，并记录来源。
6. prompt preview 显示结构化 context surface，不再只显示最终文本。
7. Context Workspace 不解析 provider-native payload。
8. 支持数据库完全重建，不做旧 render snapshot 兼容。

### 非目标

- 不让 Context Workspace 拥有 SessionItem 真相。
- 不让 Context Workspace 拥有 Tool Source / ToolRun 真相。
- 不让 Context Workspace 直接决定 Orchestration loop。
- 不把 keyword router 放进 Context Tree。
- 不让 Context Workspace 生成 provider-native request。

## ContextSurface 草案

```text
ContextSurface
  id
  session_id
  run_id
  turn_id
  tree_revision
  render_snapshot_id
  rendered_context
  included_refs
  collapsed_refs
  protocol_required_refs
  provider_attachment_mirror
  tool_schema_mirror
  estimate
  diagnostics
  created_at
```

### Included Ref

```text
ContextIncludedRef
  owner_module
  owner_kind
  owner_id
  node_id
  visibility
  render_mode
  budget_class
  protocol_required
```

`owner_kind` 示例：

```text
session_item
llm_response_item
tool_run
memory_record
artifact
skill
workspace_file
context_node
```

### Render Mode

```text
full
summary
collapsed
reference_only
provider_attachment
tool_schema_mirror
```

## Context Tree 节点变化

新增或标准化节点族：

```text
session.active_segment
session.model_visible_items
session.tool_interactions
llm.response_items
tool.surface
tool.surface.<source>
tool.surface.<source>.<group>
runtime.protocol_required
```

说明：

- `session.model_visible_items` 展示可进入模型历史的 Session facts。
- `runtime.protocol_required` 展示当前 turn 不能被折叠的 provider protocol facts。
- `tool.surface` 是 ToolSurface 的 agent-facing mirror，不是 Tool Source truth。
- `llm.response_items` 只显示已被 Orchestration 引用进入当前 chain 的 response item refs，不读取 LLM raw events。

## Render Snapshot

允许破坏式调整 render snapshot schema。建议目标字段：

```text
context_render_snapshots
  id
  session_id
  run_id
  turn_id
  tree_revision
  rendered_context
  included_refs_payload
  collapsed_refs_payload
  protocol_required_refs_payload
  provider_attachment_mirror_payload
  tool_schema_mirror_payload
  estimate_payload
  diagnostics_payload
  created_at
```

snapshot 是事实：本轮 LLM request 到底看到了什么。它不应依赖事后从 prompt string 反推。

## Budget 策略

### 不能压缩

```text
current user input
current turn tool_call protocol item
current turn tool_result protocol item
current turn provider-required replay item
runtime contract
```

### 可压缩

```text
old assistant commentary
old reasoning summary
old tool interactions
old session segment exact messages
memory recall details
artifact previews
```

压缩后必须保留：

```text
source refs
summary text
expand action if available
budget reason
```

## Tool Schema Mirror

Tool schema mirror 从 ToolSurface 派生：

```text
tool_schema_mirror
  tool_surface_id
  source_refs
  group_refs
  enabled_function_refs
  schema_payload_refs
  estimate
```

规则：

- Context Workspace 可以控制 schema 是否在树中展开/折叠。
- Context Workspace 不改变 tool readiness、runtime requirements、authorization。
- provider function schema 最终由 LLM adapter 从 ToolSurface 映射，不由 Context Workspace 拼 provider-native schema。

## Prompt Preview

Prompt preview 应展示：

- rendered context tree。
- included refs。
- collapsed refs。
- protocol required refs。
- tool schema mirror。
- provider attachments。
- estimate。
- diagnostics。

不要只显示一段 prompt 文本。文本只是其中一个渲染结果。

## 与 Orchestration 配合

Orchestration 调用 Context Workspace：

```text
build_context_surface(session_id, run_id, turn_id, execution_chain_refs, tool_surface_id)
```

Context Workspace 返回 `ContextSurface`。Orchestration 只记录 snapshot id 和把 surface 放入 `LlmRequestEnvelope`。

## 退场项

必须退场或降级：

- Orchestration 内部拼历史 prompt。
- 只按 role/content transcript 渲染 session。
- 当前 turn protocol items 进入普通历史预算。
- Context Workspace 自行定义 tool source/runtime policy。
- Prompt preview 只显示 prompt string。
- 不得为旧 render snapshot/schema mirror 保留兼容 shim。

## Checklist

### Domain

- [ ] 定义 `ContextSurface`。
- [ ] 定义 `ContextIncludedRef`。
- [ ] 定义 render mode / budget class。
- [ ] 标记 `protocol_required` refs。

### Persistence

- [ ] 破坏式调整 render snapshot schema。
- [ ] 保存 included/collapsed/protocol refs。
- [ ] 保存 provider attachment mirror。
- [ ] 保存 tool schema mirror。
- [ ] 保存 diagnostics。

### Application

- [ ] 从 Session model-visible replay 构建 session nodes。
- [ ] 从 execution chain refs 构建 protocol required nodes。
- [ ] 从 ToolSurface 构建 tool surface mirror。
- [ ] 输出 `ContextSurface`。
- [ ] Prompt preview 展示 structured surface。

### Verification

- [ ] 当前 turn tool_call/tool_result 不被预算折叠。
- [ ] 历史 assistant commentary 可折叠但 source ref 保留。
- [ ] render snapshot 能回答本轮模型看到哪些 SessionItem。
- [ ] tool schema mirror 与 ToolSurface id 对齐。
- [ ] 清库重建后 context workspace 单测通过。
