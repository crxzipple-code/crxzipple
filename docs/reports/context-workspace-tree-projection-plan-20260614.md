# Context Workspace Tree Projection Development Plan

Date: 2026-06-14

## 背景

CRXZipple 的 Context Workspace 拥有 Context Tree、节点状态、render snapshot、provider attachment mirror 和 agent-facing `context_tree.*` 工具。用户明确决策：

- 树是 agent 可见的运行面。
- 不新增概念替代树。
- 树后面的常驻和能力交付由 tool module / context workspace 控制。
- 不要让树每轮自动变成大段 prompt 底稿。

最新会话显示，默认把 `<context_tree>` / `<context_tree_delta>` 塞进 provider `system` message 会导致模型读到大量上下文但丢失任务状态。模型主动调用 `context_tree.render_current` 后也拿到截断树文本，仍没有稳定继承 KMG -> Shanghai 的查票任务。

本文件定义 Context Workspace 如何从“默认 prompt body 渲染器”迁移为“上下文真相 + agent 可操作对象 + provider input 投影来源”。

## 目标

1. Context Tree 仍由 Context Workspace 拥有。
2. 默认 LLM request 不再包含完整树 XML。
3. 树通过 `context_tree.*` 工具被模型主动查看和管理。
4. Context Workspace 为 provider request 提供 compact projection：
   - active task state
   - context hints
   - tool surface mirror
   - attachment mirror
   - render snapshot refs
5. 树的展开/折叠/pin/unpin 继续影响投影和工具可见性。

## 施工进度

- [x] Provider request 默认不再把完整 `<context_tree>` XML 注入为 `context_workspace` system message。
- [x] `include_context_messages=False` 时新增 `context_workspace_projection` compact message，包含 snapshot id、tree schema、节点/工具/附件计数、有限 node refs 和 `context_tree.*` read hints。
- [x] `context_workspace_delta` 默认 model-visible 路线已取消；有真实 `context_delta` 时仅保留在 Context Workspace snapshot/debug，不进入 provider messages 或 LLM request metadata。
- [x] 完整 tree render 仍保存在 request metadata `context_surface.rendered_context`，用于 Workbench/Operations/debug 审计，不作为默认 model-visible 底稿。
- [x] Orchestration preview 与实际 advance request 都已默认走 compact projection，不走 full tree / delta prompt。
- [x] Active task state 不从 evidence ledger 推断；当前任务事实由 provider transcript/session replay 承载，tree projection 只给 snapshot/refs/tool read hints。
- [x] Workbench/Operations 通过 LLM request preview、model-visible surface 和 context surface 区分 provider projection 与 debug-only rendered tree。

## 非目标

- 不把 Context Tree 从系统中移除。
- 不让 orchestration 直接拼树。
- 不把 Workbench 展示树作为 provider prompt 来源。
- 不要求所有 provider 支持树工具；工具不可用时使用 compact projection fallback。

## 目标形态

```text
Context Workspace
  owns:
    - Context Tree
    - node states
    - render snapshots
    - provider attachment mirror
    - context_tree.* tools

  exposes to orchestration:
    - stable instruction refs
    - active task state projection
    - context hint projection
    - tool mirror snapshot
    - provider attachment snapshot
    - tree snapshot id / revision

  does not expose by default:
    - full <context_tree> XML as system message
```

## Projection Types

### 1. Active Task State

Short model-visible block generated from tree/session/tool owner facts:

```text
Active task state:
- Goal: 查询东航官网昆明到上海机票
- Known slots:
  - date: 2026-06-15
  - origin: Kunming / KMG
  - destination: Shanghai
  - airport: SHA/PVG both acceptable
- Last status:
  - PC site blocked by WAF.
  - Mobile site bundle inspected.
  - Ticket price API not validated yet.
- Open uncertainty:
  - Ticket price API not validated yet.
```

This is not a new business truth owner and does not decide the next action. It is a projection from existing owner facts.

### 2. Context Hint Projection

Small hints that help the model decide whether to call tree tools:

```text
Context tree:
- Snapshot: ctxsnap_xxx revision 25
- Full tree is available through context_tree.render_current/read_snapshot/diff_since.
- Recent relevant nodes: active task, last tool interactions, continuation state.
```

### 3. Tool Surface Projection

The tree still controls tool mirror state, but provider request receives actual tool schemas through Tool Surface:

```text
tools = tool_surface.functions
metadata.context_render_snapshot_id = ctxsnap_xxx
```

### 4. Attachment Projection

Provider attachments are listed by reference:

```text
attachments:
- artifact: ...
- memory: ...
- file: ...
```

Large content is not inlined unless selected by budget/policy.

## Tree Tool Semantics

### `context_tree.render_current`

- Returns current tree render.
- Must support `max_chars`, `node_id`, and `include_state`.
- Tool output should state truncation clearly.
- Repeated render calls with truncation should suggest targeted `read_snapshot` / `list` / `diff_since`.

### `context_tree.read_snapshot`

- Reads a stable snapshot or node.
- Better than rendering whole tree for follow-up tasks.

### `context_tree.diff_since`

- Shows changes since a snapshot/revision.
- Default model path after the first tree read.

### `context_tree.list`

- Lightweight index of nodes.
- Preferred before large render.

## Request-Time Behavior

### First Turn

Default first turn should not necessarily send full tree XML. Instead:

```text
instructions = stable runtime contract
input = active_task_state + user message + replay items
tools = tool schemas including context_tree.*
metadata = context snapshot refs
```

If a mode explicitly requests “prompt preview / debug / full tree bootstrap”, full tree render may be included as a diagnostic input item, not normal default.

### Follow-Up Turn

```text
instructions = stable runtime contract
input = active_task_state delta + replay items + latest user
tools = current tool surface
metadata = tree snapshot refs
```

The model may call `context_tree.*` if it needs more.

### Tool-Driven Tree Read

When model calls `context_tree.render_current`, the output enters replay as `function_call_output`. That output is part of protocol chain and can be referenced in future turns.

## Evidence Boundary

Context tree tool success is not task evidence.

Separate:

- `context_observation`: tree was read, expanded, diffed, estimated.
- `task_evidence`: official website response, API output, command stdout proving a fact, validation result.

Context Workspace emits context observations. Orchestration does not maintain a generic evidence ledger for task completion; the LLM judges sufficiency from provider transcript and explicit owner facts. Business-grade validation belongs in explicit workflow / skill evaluators.

## Module Changes

## 1. Context Workspace Application

Add query:

```python
class ContextProjectionService:
    def projection_for_llm_request(
        self,
        session_key: str,
        *,
        snapshot_id: str | None,
        active_task_policy: dict[str, object],
    ) -> ContextRequestProjection: ...
```

Projection includes:

- `snapshot_id`
- `revision`
- `active_task_state`
- `context_hints`
- `tool_mirror`
- `attachment_refs`
- `budget_report`

## 2. Render Snapshot

Render snapshot should record:

- full tree content ref
- projection payload
- projection fingerprint
- whether full tree was provider-visible
- reason if full tree was included

## 3. Agent-Facing Tools

Update tool result envelope metadata:

- `context_observation=true`
- `task_evidence=false`
- `snapshot_id`
- `revision`
- `truncated`
- `suggested_follow_up_tool`

## 4. Prompt Surface Builder

Stop treating `render_snapshot.content` as the default system message. It should consume `ContextRequestProjection`.

## Test Plan

### Unit

- Projection omits full tree XML by default.
- Projection includes snapshot id/revision.
- Active task state extracts known slots from session/tree/evidence.
- Tree tool result is marked context observation, not task evidence.

### Integration

- LLM request preview has no `<context_tree` in system input by default.
- `context_tree.render_current` still works and enters replay as `function_call_output`.
- Tool schema mirror still reflects tree state.

### Regression

East China Airlines follow-up:

- Latest user: “下周一 那个机场都行”.
- Projection includes route/date/airport known slots.
- Model does not need to render full tree to know current task.

## Checklist

- [x] Add compact request projection payload.
- [x] Use projection in provider request builder.
- [x] Keep active task state in provider transcript/session replay instead of tree-derived evidence slots.
- [x] Generate context hint projection with snapshot id, counts, refs and `context_tree.*` read hints.
- [x] Mark tree tool outputs as context observations through ordinary function_call_output replay.
- [x] Stop default full tree system render.
- [x] Preserve full tree debug mode.
- [x] Update request builder to consume projection.
- [x] Update tests for request preview.
- [x] Update docs explaining tree as agent-managed object.

## Acceptance Criteria

- Normal LLM request contains no full tree XML.
- Model can explicitly call tree tools to inspect tree.
- Active task state appears as compact replay item.
- Evidence frontier no longer counts tree read/expand as task evidence.
- Workbench can still show tree operations in trace.
