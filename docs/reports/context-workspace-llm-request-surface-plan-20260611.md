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

## 当前施工状态

截至 2026-06-11，`ContextSurface` / `ToolSurface` request-side 结构已落地，Context Workspace render snapshot 已成为 Orchestration preview 和真实 invoke 的 structured surface 来源：

- `RunPromptInputCollector` 优先读取 Session module 的 model-visible `SessionItem` replay view。
- `tool_call` / `tool_result` SessionItem 会被转换为 provider-facing `LlmMessage`。
- LLM request metadata 已记录 `direct_session_item_refs`、`direct_session_item_frontier`、`direct_transcript_budget` 和对应 `direct_tool_protocol_call_ids`。
- Context render snapshot 已用一等字段记录 `included_refs`、`collapsed_refs`、`protocol_required_refs`，并在 metadata/provider attachments 保留观察镜像。
- current inbound user input 已通过 `current_inbound_session_item_id` 进入 render snapshot，并在 provider request metadata 中优先解析为 `current_inbound_ref.item_id`。
- Prompt transcript 已输出 SessionItem 级 budget/frontier 事实报告，能说明 included/collapsed/protocol_required item refs。
- Prompt input collector 已从 execution chain tool protocol items 生成 `execution_chain_protocol_required_refs`，并合并进入 render snapshot / ContextSurface 的 `protocol_required_refs`。
- SessionItem replay 已启用 item-level 字符预算，`tool_call` / `tool_result` / `provider_external_item` 即使超过普通预算也必须保留。
- Orchestration `ToolSurface.metadata` 已输出 function count、mirrored schema count 和 source/group refs；Context Workspace 继续只提供 tool schema mirror，不反向拥有 ToolSurface。
- Workbench/Trace 已展示 Context render snapshot 一等 refs 的计数和 protocol refs 预览。
- 默认 provider replay 和 `memory_flush` provider replay 已不再读取旧 `session_messages`；当前 session 尚无 model-visible SessionItem 时，normal turn 只从当前 inbound instruction 构造最小输入，其余历史必须通过 SessionItem 进入模型。
- follow-up normal turn 的 direct transcript 已收窄到当前 user item 与当前 turn protocol pair；上一轮 tool_call/tool_result 不再作为 direct protocol message replay，而是通过 Context Tree session history / `tool_interaction` 节点进入模型。
- maintenance compaction、正常 Orchestration inbound user input、Conversation `/messages`、Workbench progress、prompt input collector 和 agent-facing `tools/sessions` 已从旧 session message 主路径退场。
- Context Workspace artifact owner adapter 已从 SessionItem 扫描 artifact refs；session owner adapter 的 current segment、current range children、evidence ledger、browser investigation warning、consumed tool history 和 historical range 入口已优先读取 model-visible SessionItem。
- Session owner adapter 已从 tool_result SessionItem content blocks 提取 artifact content candidates；已渲染的 `tool_interaction` 节点可以通过 provider attachment mirror 把 image/file artifact refs 送入 request artifact block。
- Session item/item nodes 的 `owner_ref` 已保留 `session_item_id/source_module/source_kind/source_id`，历史 assistant commentary 折叠后仍可追溯来源。
- `context_workspace_session.py` 已删除旧 `list_messages` fallback；session owner adapter 只通过 `list_items` 读取 Session transcript facts。
- session owner adapter 已支持新 `SessionItemKind.TOOL_CALL` + `SessionItemKind.TOOL_RESULT` protocol pair 生成 `tool_interaction` 节点。
- Context Tree agent-facing session surface 已统一为 `session.items.current`、`session.item.*`、`session_item_range`、`session_item` 和 XML `<item role=...>`；render snapshot metadata 已统一为 `tree_session_item_count`、`session_item_node_refs`、`session_item_range_node_count`，Operations snapshot row 已使用 `tree_items`。
- Prompt preview HTTP/DTO 已一等返回 `context_surface` / `tool_surface`，不再只能通过 `provider_request_options.request_metadata` 反查 structured surface。
- Evidence/interaction adapter 已停止输出 `call_message_id/result_message_id` owner metadata，read hint 已指向 `/sessions/{key}/items`，XML renderer refs 已改为 `call_session_item_id/result_session_item_id`。

### Domain

- [x] 定义 `ContextSurface`。
- [x] 定义 included/collapsed/protocol refs payload。
- [x] 定义 render mode / budget class。
- [x] 标记 `protocol_required` refs。

### Persistence

- [x] `context_render_snapshots` 增加 `included_refs` / `collapsed_refs` / `protocol_required_refs` 一等字段。
- [x] SQLAlchemy repository roundtrip 保存 snapshot refs。
- [x] Orchestration Context Snapshot adapter 写入 direct session item refs 和 protocol required refs。

- [x] 破坏式调整 render snapshot schema。
- [x] 在 render snapshot metadata/provider attachments 中保存 direct SessionItem refs 和 protocol_required refs。
- [x] 破坏式 schema 字段保存 included/collapsed/protocol refs。
- [x] 保存 provider attachment mirror。
- [x] 保存 tool schema mirror。
- [x] 保存 diagnostics。

### Application

- [x] prompt input builder 从 Session model-visible replay 构建 provider request transcript。
- [x] 默认 provider replay 不再读取旧 `session_items`。
- [x] `memory_flush` provider replay 不再读取旧 `session_items`。
- [x] Prompt transcript 输出 SessionItem 级 budget/frontier 事实报告。
- [x] SessionItem replay 使用 item-level budget，并保留 protocol-required items。
- [x] render snapshot / provider request metadata 能回答当前 inbound user input 对应哪个 SessionItem。
- [x] current segment 入口优先从 Session model-visible replay 构建 session nodes。
- [x] current range 展开入口优先从 Session model-visible replay 构建 message/item nodes。
- [x] evidence ledger 和 browser investigation warning 入口优先从 Session model-visible replay 构建 evidence nodes。
- [x] consumed tool history 入口优先从 Session model-visible replay 构建 tool interaction nodes。
- [x] historical range/session node 入口优先从 Session model-visible replay 构建 range/item nodes。
- [x] session owner adapter 删除旧 `list_messages` fallback。
- [x] artifact session refs 从 SessionItem content blocks 构建 artifact nodes。
- [x] 从 execution chain refs 构建 protocol required refs，并进入 render snapshot / ContextSurface。
- [x] 从 ToolSurface 构建 request-side tool surface mirror metadata。
- [x] 输出 `ContextSurface`。
- [x] Prompt preview 展示 structured surface。
- [x] Evidence/interaction adapter 删除 `call_message/result_message` owner metadata，改为 `call_session_item/result_session_item`。
- [x] Evidence read hints 不再指向旧 `/sessions/{key}/messages`，改为 item surface 或 Operations/Trace source ref。

### Verification

- [x] 当前 turn tool_call/tool_result 通过 SessionItem replay 进入下一轮 request。
- [x] follow-up normal turn 历史 tool_call/tool_result 不再进入 direct transcript。
- [x] 新 `SessionItemKind.TOOL_CALL` + `SessionItemKind.TOOL_RESULT` protocol pair 可生成 `tool_interaction` 节点。
- [x] render snapshot 能回答本轮模型直接看到哪些 SessionItem。
- [x] render snapshot 能回答当前 inbound user input 对应哪个 SessionItem。
- [x] 当前 turn tool_call/tool_result 在 item-level budget report 中标记为 protocol_required 并确认 preserved。
- [x] 超预算时 protocol-required SessionItem 仍进入 provider transcript。
- [x] 历史 assistant commentary 可折叠但 source ref 保留。
- [x] render snapshot 能区分 included/collapsed/protocol_required 独立字段。
- [x] Workbench/Trace 能展示 snapshot 一等 refs 摘要和 protocol refs 预览。
- [x] Context Workspace HTTP 使用 `/sessions/{key}/items` 写入后，session owner tree 能看到 current segment 并展开到具体 item node。
- [x] Artifact owner adapter 从 SessionItem content blocks 展开 artifact nodes。
- [x] Context Workspace HTTP 使用 `/sessions/{key}/items` 写入 tool_call/tool_result 后，evidence ledger 和 browser investigation warning 能从 SessionItem 生成。
- [x] Context Workspace HTTP reset 后的 closed segment historical range 能从 SessionItem 展开。
- [x] Context Workspace session adapter 单测通过测试 fake 的 SessionItem mirror，不再依赖 adapter 双读。
- [x] tool schema mirror 与 ToolSurface id 对齐。
- [x] Evidence/interaction node 的 owner_ref/content/XML refs 不再出现 `result_message_id` / `call_message_id`。
- [x] 清库重建后 context workspace 单测通过：Context Workspace HTTP/session/artifact/tree/tool/context snapshot 组合共 91 个测试通过。
- [x] SessionItem context surface 纠偏后补跑 Context Workspace/Prompt 回归 104 passed。
- [x] 真实 `openai.gpt-5.4-mini` smoke 验证 snapshot prompt body：包含 `session.items.current` / `session.item.*` / `<item role=...>`，不包含旧 `session.messages.current` / `session.message.*` / `<message role=...>`。
