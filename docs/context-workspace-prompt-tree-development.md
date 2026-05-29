# Context Workspace / 树化 Prompt 开发文档

本文是 [context-workspace-prompt-tree-design.md](context-workspace-prompt-tree-design.md) 的施工文档。设计文档说明目标和边界；本文说明模块如何落地、怎么拆任务、怎么迁移现有 prompt 代码、怎么验收。

## 施工目标

新增 `context_workspace` module，把当前散落在 orchestration prompt 里的上下文交付逻辑收成一棵真实 Context Tree。

最终形态：

```text
owner modules 持有业务真相
        ↓
context_workspace 维护真实 Context Tree
        ↓
agent / human / runtime 操作同一棵树
        ↓
Context Tree 作为 Prompt Body 交给 LLM
        ↓
provider adapter 从树节点镜像 tools / images / files 等特化附件
```

本轮不接受把旧 `PromptSurfaceBuilder` 外面包一层 facade 的最小迁移。需要分阶段替换旧装配点，最终让 orchestration 不再直接拼 tool、skill、memory、workspace、session bulk 文本。

## 旧基线

本轮重构前，prompt 主要由旧 `PromptAssembler.assemble()` 组装：

- agent system prompt：`profile.instruction_policy.system_prompt`
- runtime context：agent id、llm id、time、home/workspace
- flow prompt：session_start、approval、heartbeat、compaction、memory_flush
- active session transcript：只取 active session 未 archived 消息
- workspace bootstrap：`AGENT(S).md`、`SOUL.md`、`TOOLS.md`、`IDENTITY.md`、`USER.md`、`BOOTSTRAP.md`
- memory recall：仅 `SESSION_START` 自动 recall
- skills catalog：ready skills compact catalog
- available tools 文本：按 tool id 前缀硬编码 family
- tool schemas：surface 允许且 tool 可用时全部带
- artifact materialization：按 LLM capability 转 image/file 或 placeholder

主要问题：

- 可见能力和注入内容没有统一树状态。
- 展开、折叠、pin、启用 schema、回看历史图片等操作无统一协议。
- session bulk 和 compaction 是隐式机制。
- tool family 和 session tool guidance 有人工联想/手写说明。
- 估算只在 prompt 末端，不能按节点展示。
- 人类无法直观看到 agent 当前上下文工作台。

## 模块边界

新增目录：

```text
src/crxzipple/modules/context_workspace/
├─ domain/
├─ application/
├─ infrastructure/
└─ interfaces/
```

`context_workspace` 拥有：

- Context workspace 生命周期。
- Context node handle、状态、摘要、估算、owner ref。
- Agent/UI/runtime 对树的操作。
- 树渲染为 prompt body。
- Provider attachment mirror bundle。
- Run render snapshot。
- 操作事件和审计事实。

`context_workspace` 不拥有：

- session 消息真相。
- memory 内容真相。
- skill package 真相。
- tool schema 真相。
- artifact 原始文件真相。
- access credential 真相。
- authorization policy 真相。
- orchestration run 生命周期。

## Domain Model

### ContextWorkspace

绑定一个 session 的上下文工作台。

字段建议：

```python
@dataclass(kw_only=True)
class ContextWorkspace(AggregateRoot[str]):
    session_key: str
    agent_id: str
    status: str = "active"
    active_revision: int = 1
    metadata: dict[str, object] = field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
```

约束：

- `session_key` 必须唯一绑定一个 active workspace。
- 同一 session reset 后不新建 workspace，除非 reset policy 明确要求清空上下文树。
- `active_revision` 每次树状态变更递增。

### ContextNode

节点是 owner 资源在上下文树里的 handle，不是 owner 业务真相。

字段建议：

```python
@dataclass(frozen=True, slots=True)
class ContextNode:
    node_id: str
    workspace_id: str
    parent_id: str | None
    owner: str
    kind: str
    title: str
    summary: str
    content: str
    state: ContextNodeState
    actions: tuple[ContextAction, ...]
    owner_ref: dict[str, object]
    estimate: ContextEstimate
    revision: str | None = None
    freshness: str = "live"
    display_order: int = 0
    metadata: dict[str, object] = field(default_factory=dict)
```

`owner_ref` 示例：

```json
{
  "session_key": "web:abc",
  "session_id": "active-session-id",
  "range": {"from_sequence": 10, "to_sequence": 36}
}
```

节点默认避免保存完整 owner 内容。可保存摘要、caption、可见 metadata、估算和状态；由
`context_workspace` 自身生成的 prompt node（例如 `agent.identity`、`run.runtime`、
`run.flow`）可以保存本轮渲染所需的正文 `content`，并进入 render snapshot。

### ContextNodeState

建议用显式 flags，而不是一个超载 enum。

```python
@dataclass(frozen=True, slots=True)
class ContextNodeState:
    collapsed: bool = True
    loaded: bool = False
    pinned: bool = False
    prompt_visible: bool = True
    schema_enabled: bool = False
    consumed: bool = False
    archived: bool = False
```

说明：

- `collapsed`：节点子内容未披露。
- `loaded`：节点已从 owner 拉取过详情或 children。
- `pinned`：后续 render 时保持可见。
- `prompt_visible`：节点本身是否进入 prompt body。
- `schema_enabled`：tool node 的 schema 是否镜像到 provider tools。
- `consumed`：已使用，后续可降级摘要。
- `archived`：保留追溯，不主动出现。

### ContextAction

固定动作名，避免通用代理。

```text
expand
collapse
pin
unpin
recall_memory
read_skill
open_artifact
enable_tool_schema
disable_tool_schema
fold_session_range
estimate
```

不要提供：

```text
call(owner, action, payload)
```

### ContextEstimate

节点级估算。

```python
@dataclass(frozen=True, slots=True)
class ContextEstimate:
    text_chars: int = 0
    text_tokens: int = 0
    tool_schema_tokens: int = 0
    image_count: int = 0
    file_count: int = 0
    file_tokens: int = 0
    provider_attachment_count: int = 0
```

估算必须能聚合到 subtree 和 whole tree。

### ContextRenderSnapshot

每次 run 调用 LLM 前保存一次树渲染快照。

```python
@dataclass(kw_only=True)
class ContextRenderSnapshot(AggregateRoot[str]):
    workspace_id: str
    session_key: str
    run_id: str
    tree_revision: int
    prompt_body: str
    provider_attachments: dict[str, object]
    estimate: dict[str, object]
    included_node_ids: tuple[str, ...]
    mirrored_tool_node_ids: tuple[str, ...]
    mirrored_artifact_node_ids: tuple[str, ...]
    created_at: datetime
```

保存快照的目的：

- 后续复现 LLM 实际看到的 prompt body。
- 排查为什么某个 tool/image/memory 没出现。
- Operations 可以展示上下文压力来源。

## Application Services

### ContextWorkspaceService

职责：

- `ensure_workspace(session_key, agent_id)`
- `get_workspace(workspace_id | session_key)`
- `reset_workspace(session_key, policy)`
- `touch_revision(workspace_id)`

### ContextTreeService

职责：

- `list_tree(session_key, view)`
- `expand_node(workspace_id, node_id, actor)`
- `collapse_node(...)`
- `pin_node(...)`
- `unpin_node(...)`
- `enable_tool_schema(...)`
- `disable_tool_schema(...)`
- `open_artifact(...)`
- `read_skill(...)`
- `recall_memory(...)`
- `fold_session_range(...)`

所有操作：

- 先加载 workspace。
- 读取节点当前状态。
- 校验 actor 和 action 是否允许。
- 必要时调用 owner adapter。
- 写入 node state / loaded child nodes。
- 记录 operation。
- 发布事件。

### ContextRenderService

职责：

- `render_prompt_body(session_key, run_context)`
- `extract_provider_attachments(session_key, run_context, provider_capabilities)`
- `estimate_tree(session_key)`
- `record_render_snapshot(run_id, ...)`

注意：

- Render 不改变树结构，除非显式预算策略需要自动折叠，并记录 `context.budget.applied`。
- Render 输出必须保留树结构。
- Provider attachments 是节点镜像，不是 prompt 主体替代物。

### ContextOwnerRegistry

由 app assembly 装配，注册 owner adapters。

```python
@dataclass
class ContextOwnerRegistry:
    providers: Mapping[str, ContextNodeProvider]
    action_handlers: Mapping[str, ContextActionHandler]
```

`context_workspace` module 定义协议，具体 adapter 可以在 `app/integration/context_*` 或 owner module application 层实现。为避免 owner module 反向依赖，优先在 assembly/integration 层写适配器。

## Owner Adapter Contracts

### ContextNodeProvider

```python
class ContextNodeProvider(Protocol):
    owner: str

    def root_nodes(self, request: ContextNodeRequest) -> tuple[ContextNodeSeed, ...]:
        ...

    def children(self, request: ContextChildrenRequest) -> tuple[ContextNodeSeed, ...]:
        ...
```

Provider 必须只返回当前 agent/session 可见的节点。不可见资源不能以 disabled node 暴露给 agent。

### ContextActionHandler

```python
class ContextActionHandler(Protocol):
    owner: str

    def handle(self, request: ContextActionRequest) -> ContextActionResult:
        ...
```

只允许处理上下文动作，例如 read skill、recall memory、open artifact。禁止作为 owner module 的任意命令代理。

## Visibility Gate

Visibility 必须在节点进入 Agent view 前完成。

### Tool

Tool adapter 通过 Tool query/readiness/authorization surface 产出节点。

不可见条件：

- tool disabled。
- tool readiness 不满足且不允许 setup 提示。
- ABAC deny。
- required effect 不允许。
- access requirement 不 ready 且当前视图不允许 setup node。

可见但未启用 schema：

- tool group node。
- tool function summary node。
- `enable_tool_schema` action 可用。

### Skill

Skill adapter 通过 Skills owner catalog 和 readiness service 产出节点。

不可见条件：

- skill disabled。
- required tools 不可见。
- required access 不 ready。
- unsupported surface。
- authorization missing effects。

默认只显示 summary/catalog node。`read_skill` 后挂载 SKILL.md 或具体文件节点。

### Memory

Memory adapter 通过 Memory runtime access plan 产出 scope nodes。

可见范围：

- 当前 agent private scope。
- policy 允许的 shared/project/team/system scopes。

不可见的 memory scope 不显示。Recall 结果作为动态 child node 挂到对应 scope 下。

### Session

Session adapter 通过 session application/query service 产出：

- current instance。
- recent window。
- folded history。
- compaction summary。
- previous instances。
- message chunks。
- exact ranges。
- session artifacts index。

打开旧 session 只能逐级展开，不允许一次性加载完整历史。

### Artifact

Artifact adapter 产出：

- image/file metadata node。
- caption/observation node。
- thumbnail/preview node。
- full payload handle node。

Full payload 是否镜像到 provider image/file input，由 render 时 provider capability 和预算决定。

### Workspace

Workspace adapter 初期可以兼容现有 bootstrap 文件：

- `AGENT.md` / `AGENTS.md`
- `SOUL.md`
- `TOOLS.md`
- `IDENTITY.md`
- `USER.md`
- `BOOTSTRAP.md`

但长期应改成 workspace root node、bootstrap group node、file handle node。完整文件读取应走 expand/open，而不是 `PromptSurfaceBuilder` 直接扫文件。

## Storage

建议新增 Postgres 表：

### context_workspaces

- `workspace_id` primary key
- `session_key` unique index
- `agent_id`
- `status`
- `active_revision`
- `metadata`
- `created_at`
- `updated_at`

### context_node_states

- `workspace_id`
- `node_id`
- `parent_id`
- `owner`
- `kind`
- `state`
- `owner_ref`
- `summary`
- `estimate`
- `revision`
- `freshness`
- `display_order`
- `metadata`
- `created_at`
- `updated_at`

索引：

- `(workspace_id, node_id)` unique
- `(workspace_id, parent_id)`
- `(workspace_id, owner, kind)`

### context_operations

- `operation_id`
- `workspace_id`
- `session_key`
- `run_id`
- `actor_kind`
- `actor_id`
- `node_id`
- `action`
- `status`
- `reason`
- `payload`
- `created_at`

### context_render_snapshots

- `snapshot_id`
- `workspace_id`
- `session_key`
- `run_id` unique
- `tree_revision`
- `prompt_body`
- `provider_attachments`
- `estimate`
- `included_node_ids`
- `mirrored_node_ids`
- `created_at`

SQLite 只作为测试或显式 fallback，主开发路径按 Postgres 迁移。

## Interfaces

### Agent-facing Tool API

初期作为 Tool module 的 local functions 暴露：

```text
context_tree.list
context_tree.expand
context_tree.collapse
context_tree.pin
context_tree.unpin
context_tree.estimate
context_tree.read_skill
context_tree.recall_memory
context_tree.open_artifact
context_tree.enable_tool_schema
context_tree.disable_tool_schema
```

这些工具必须拿到 execution context：

- agent id
- session key
- active session id
- run id

如果缺 session/run context，应返回 setup_needed / invalid_context，而不是猜默认 session。

### HTTP API

给 UI/Human Control 用：

```text
GET    /context-workspaces/by-session/{session_key}/tree
GET    /context-workspaces/by-session/{session_key}/estimate
GET    /context-workspaces/runs/{run_id}/render-snapshot
POST   /context-workspaces/by-session/{session_key}/nodes/{node_id}/actions/expand
POST   /context-workspaces/by-session/{session_key}/nodes/{node_id}/actions/collapse
POST   /context-workspaces/by-session/{session_key}/nodes/{node_id}/actions/pin
POST   /context-workspaces/by-session/{session_key}/nodes/{node_id}/actions/unpin
POST   /context-workspaces/by-session/{session_key}/nodes/{node_id}/actions/enable-tool-schema
POST   /context-workspaces/by-session/{session_key}/nodes/{node_id}/actions/disable-tool-schema
```

HTTP 返回的是 Human/Runtime view，可包含不可见原因和审计信息；Agent-facing view 不能包含被策略挡掉的资源。

### CLI

```text
python -m crxzipple.main context tree SESSION_KEY
python -m crxzipple.main context estimate SESSION_KEY
python -m crxzipple.main context snapshot RUN_ID
python -m crxzipple.main context expand SESSION_KEY NODE_ID
```

CLI 用于调试和测试，不作为 agent 默认入口。

## Tree Rendering

Render 输出是 prompt body，必须是树结构。

建议根部包含少量固定说明：

```xml
<context_instructions>
  You are given a context tree.
  Nodes may be collapsed or expanded.
  Use context_tree tools to expand, collapse, recall, read, pin, open artifacts,
  or enable tool schemas when needed.
  Collapsed nodes are available handles, not full content.
  Do not assume unavailable nodes exist.
</context_instructions>
```

主体：

```xml
<context_tree session="..." revision="...">
  <node id="session.current" kind="session" state="expanded">
    <summary>Current active session.</summary>
  </node>
  <node id="tools.browser" kind="tool_group" state="collapsed" actions="expand enable_tool_schema">
    <summary>Browser automation capabilities are available.</summary>
  </node>
</context_tree>
```

规则：

- 不把完整 JSON 直接塞进 prompt body。
- XML-like 只用于稳定边界，不引入 HTML 特化语义。
- 节点 content 可包含 markdown/text，但必须包在节点边界内。
- 过大节点应渲染 summary + estimate + action hint。

## Provider Attachment Mirror

Provider attachment extractor 从树节点生成特化输入：

```python
@dataclass(frozen=True, slots=True)
class ProviderAttachmentBundle:
    tool_schemas: tuple[ToolSchema, ...]
    image_inputs: tuple[ProviderImageInput, ...]
    file_inputs: tuple[ProviderFileInput, ...]
    metadata: dict[str, object]
```

规则：

- tool schema 只来自 `schema_enabled=True` 的 tool function nodes。
- image/file input 只来自已打开且预算允许的 artifact nodes。
- provider 不支持时，不生成 attachment，prompt body 保留 caption/placeholder。
- adapter 只能镜像节点，不得重新发现工具或读取 owner 数据。

## Orchestration 迁移

### 当前保留

`PromptAssembler` 已退场，当前保留 `PromptSurfaceBuilder` 作为 Context Workspace
渲染前的 surface 输入收集器。

### 迁移目标

`PromptSurfaceBuilder` 只负责：

- 确认 run/session/agent 基本有效。
- 解析 LLM profile 和 provider capability。
- 构建 active session transcript message surface。
- 生成 `agent.identity` / `run.runtime` 等 context blocks。
- 解析 skill readiness metadata 和授权后的 tool candidate surface，供 Context Workspace
  生成 `tools.available` 节点。
- 生成 flow hint 供 Context Workspace 写入 `run.flow` node。

它不再渲染最终 prompt body，不再注入 tool/skill/memory/workspace/session bulk/flow 文本，
也不直接调用 LLM。

### 要迁出的旧逻辑

| 当前逻辑 | 迁入 |
|---|---|
| `build_available_tools_block` | Tool context nodes |
| `build_session_tools_block` | Session/tool context nodes |
| `build_skills_catalog_block` | Skill context nodes |
| `recall_prompt_memories` | Memory scope + recall action |
| `load_workspace_context_files` | 已删除；Workspace bootstrap nodes 由 Context Workspace owner adapter 负责 |
| transcript pruning | Session recent window / folded history nodes |
| artifact materialization | Artifact nodes + provider attachment mirror |
| prompt budget report | Context estimate + render snapshot |

### 不迁出的逻辑

Orchestration flow 仍属于 orchestration：

- approval resume / denied
- heartbeat
- compaction
- memory flush
- recovery resume

但这些 prompt 也应作为 flow nodes 渲染，而不是散落在字符串 blocks 中。

## Operations / UI

### Operations Read Model

新增 context module operations page 或合入 Workbench/Trace：

- workspace health
- active session tree revision
- node operation timeline
- largest nodes by estimate
- enabled schemas
- opened artifacts
- recent render snapshots
- budget pressure
- failed context actions

Operations 仍通过 `/operations/context_workspace` 的统一 operations projection 获取，不让前端绕过 read model 去拼 owner 数据。

当前已落地：

- `ContextWorkspaceService.list_workspaces()` 暴露最近 workspace 查询。
- `ContextRenderService.list_recent_snapshots()` 暴露最近 render snapshot 查询。
- `ContextWorkspaceOperationsReadModelProvider` 物化 workspaces、visible nodes、render snapshots、diagnostics 四个表格区。
- `context_workspace` 已加入 `OPERATIONS_PROJECTION_MODULES`，由 operations-observer 物化到 `/operations/context_workspace`。
- `frontend/src/pages/operations/modules/ContextWorkspaceOperationsPage.vue` 已接入统一 Operations 导航，消费 `/operations/context_workspace` projection。
- Workbench inspector 已新增 Context tab，读取 `/context-workspaces/by-session/{session_key}/tree` 和 `/context-workspaces/runs/{run_id}/render-snapshot`，支持节点 expand/collapse/pin/schema toggle 并展示 render snapshot 摘要。
- 运维表格默认不展开 node `content`，只暴露节点身份、owner/kind/state 与估算体积，避免把 prompt 正文泄漏成主表数据。

### Workbench

Workbench 可以展示当前 session 的 Context Tree：

- 左侧树。
- 中间节点详情。
- 右侧 estimate / render snapshot。
- 支持人类手动 pin/collapse/disable schema。

### Settings

Settings 不直接治理树状态。Settings 只治理默认策略：

- default auto collapse threshold
- max expanded history chunks
- default artifact preview mode
- default provider attachment budget

## Events

新增事件契约：

```text
context.workspace.created
context.node.expanded
context.node.collapsed
context.node.pinned
context.node.unpinned
context.node.schema_enabled
context.node.schema_disabled
context.memory.recalled
context.skill.read
context.artifact.opened
context.session.folded
context.prompt.rendered
context.budget.applied
context.action.failed
```

事件 payload 至少包含：

- workspace_id
- session_key
- run_id when available
- agent_id
- node_id
- owner
- kind
- action
- tree_revision
- actor_kind
- actor_id
- status
- reason

不要在事件里放完整 memory/skill/session/tool 内容。

## Testing Strategy

### Unit Tests

已落地：

```text
tests/unit/test_context_workspace_domain.py
tests/unit/test_context_workspace_tree_service.py
tests/unit/test_context_workspace_http.py
tests/unit/test_context_tree_tool.py
tests/unit/test_context_workspace_memory_adapter.py
tests/unit/test_context_workspace_session_adapter.py
tests/unit/test_context_workspace_workspace_adapter.py
tests/unit/test_context_workspace_artifact_adapter.py
tests/unit/test_context_workspace_skill_adapter.py
tests/unit/test_context_workspace_tool_adapter.py
tests/unit/test_orchestration_context_workspace_snapshot.py
tests/unit/test_operations_context_workspace_read_model.py
```

覆盖：

- workspace ensure idempotent。
- node expand/collapse/pin 状态迁移。
- action 不存在/不可用时报错。
- owner adapter 通过各自 adapter 单测覆盖可见节点生成和按需展开。
- render/estimate/provider attachment mirror 由 tree service、tool 和 orchestration snapshot tests 覆盖。
- provider attachments 只镜像 enabled nodes。
- run snapshot 保存后树变化不影响历史 snapshot。
- estimate 聚合正确。

### Integration / Flow Checks

当前未保留单独 integration test 文件；真实链路由 orchestration snapshot、turn/http、Operations projection
和 Workbench API 单测覆盖。后续如果需要更长链路验收，再新增：

```text
tests/integration/test_context_workspace_session_flow.py
tests/integration/test_context_workspace_prompt_render.py
```

覆盖：

- session 创建后自动 ensure context workspace。
- 普通 turn 能渲染 tree prompt body。
- tool schema enable 后 provider payload 出现 schema。
- skill read 后 skill content 成为节点。
- memory recall 后 recall result 成为节点。
- artifact open 后 image/file attachment mirror 按 provider capability 产生。

### Regression Tests

在旧测试上加断言：

- prompt 不再裸露 unavailable tools。
- ready skill 才能成为 skill node。
- memory scope 不可见时 recall action 不可用。
- compaction 后 folded history node 可见，旧消息不直接进入 prompt body。

## Migration Plan

### 当前施工状态（2026-05-30）

- 已新增 `modules/context_workspace` 第一阶段骨架。
- 已落地 workspace、node state、operation、render snapshot 的 domain model、repository protocol、SQLAlchemy repository、in-memory repository 和 Alembic 表。
- 已接入 app assembly：`CONTEXT_WORKSPACE_SERVICE`、`CONTEXT_TREE_SERVICE`、`CONTEXT_RENDER_SERVICE`。
- 已提供 `/context-workspaces/...` HTTP 调试面和 `python -m crxzipple.main context ...` CLI。
- 已实现默认 root handle nodes、expand/collapse/pin/unpin 等状态操作、XML-like tree render、render snapshot 记录。
- 已接入 owner provider registry 和 Session owner adapter：`session.current` 可生成 current instance、recent message range、older chunk、folded history / compaction summary handle；recent/older/archived range 都可按需展开成 message nodes。
- 已接入第一版 Skills owner adapter：`skills.available` 可按 resolved skill names 生成 skill nodes，展开单个 skill 可读取 Skills 模块返回的 `SKILL.md` instructions node。
- 已接入第一版 Tool owner adapter：`tools.available` 只根据当前 prompt surface 已解析的 `available_tool_names` 生成 tool function nodes，避免绕过 ABAC/access 暴露全量 tool catalog。
- 已接入第一版 provider attachment mirror：render 时会把 `schema_enabled` 的 tool nodes 镜像成 `provider_attachments.tool_schemas`，并记录 `mirrored_node_ids`，`disable_tool_schema` 后不会出现在 mirror bundle。
- Owner provider refresh 会保留已有 child node state，避免重新 ensure/refresh 时把 `schema_enabled=false`、pin/collapse 等用户/agent 操作冲回默认值。
- 已接入真实 orchestration run 的 Context render snapshot：真实 advance 会 ensure session workspace 并保存 tree snapshot；`preview_prompt` 不落快照。
- 真实 LLM 调用的 tool schema surface 只从 Context Tree mirror 读取：`tools.available` 会根据当前授权后的 prompt surface 预加载 tool function nodes，provider 只接收 `schema_enabled` 的 tool nodes；mirror 不可用时不再回退到 PromptSurfaceBuilder 初始 schema。
- 已接入 Memory / Artifact / Workspace owner adapters；Memory recall、artifact open、workspace bootstrap file expand 都走 Context Tree。
- Memory scope nodes 已带 governance metadata，Workbench Context 面板可按 private/shared/project/team/system 筛选。
- 已替换 PromptSurfaceBuilder 的主体 blocks；真实 provider prompt 由 Context Workspace render snapshot + transcript + provider attachment mirror 组成。
- 已接入 Operations `context_workspace` read model/projection 和 Workbench Context inspector。
- 旧 `PromptAssembler`、`memory_context.py`、`flow_prompts.py`、`workspace_context.py` 相关主路径已退场。

已验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_domain.py tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_workspace_http.py tests/unit/test_context_tree_tool.py
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_memory_adapter.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_workspace_adapter.py tests/unit/test_context_workspace_artifact_adapter.py tests/unit/test_context_workspace_skill_adapter.py tests/unit/test_context_workspace_tool_adapter.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_operations_context_workspace_read_model.py
PYTHONPATH=src pytest -q tests/unit/test_app_assembly_architecture.py tests/unit/test_app_assembly_registry.py tests/unit/test_app_assembly_targets.py tests/unit/test_app_assembly_module_local.py
make test-unit-fast
PYTHONPATH=src python -m crxzipple.main context --help
npm run typecheck
npm run build
```

### CW-0：准备

- [x] 分支策略确认：本轮在既有工作区继续施工，未新建开发分支。
- [x] 确认当前 `main` 基线和已有工作区改动。
- [x] 跑 context 相关 unit subset 和 app assembly suite。

### CW-1：Module 骨架

- [x] 新增 `modules/context_workspace`。
- [x] 定义 domain entities/value objects。
- [x] 定义 repository protocols。
- [x] 定义 application services / inputs / outputs。
- [x] 加入 app assembly keys / target wiring。
- [x] 添加 HTTP/CLI 调试 surface。
- [x] 添加 Alembic migration。
- [x] 添加基础单元测试。

验收：

- `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_domain.py`
- app assembly tests 通过。

### CW-2：Session Tree

- [x] 实现 session owner adapter。
- [x] ensure workspace on session-bound run。
- [x] 产出 current instance、recent window、folded history、compaction summary 节点。
- [x] 支持 expand recent message range 为 message nodes。
- [x] 支持 older chunks。
- [x] 支持 exact ranges / archived folded ranges：`session.history.folded` 可展开为 archived range，range 再精确展开消息节点。
- [x] 保存 render snapshot。

验收：

- session reset 后 tree 保留或清空行为符合 policy。
- compaction 后旧消息只通过 folded nodes 追溯。

### CW-3：Tree Render

- [x] 实现第一版 XML-like prompt body renderer。
- [x] 实现第一版 context instructions。
- [x] 实现 estimate aggregation。
- [x] 实现 render snapshot repository。
- [x] 在真实 orchestration advance 中引入 tree render，作为主 prompt body 注入并记录 snapshot。

验收：

- render snapshot 可通过 CLI/HTTP 查看。
- tree prompt body 可读且稳定。

### CW-4：Tool Nodes

- [x] Tool adapter 产出当前 prompt surface 已解析的 tool function nodes。
- [x] `enable_tool_schema` / `disable_tool_schema` 会影响 render mirror bundle。
- [x] Provider attachment bundle 生成 tool schemas。
- [x] 真实 LLM provider tool schemas 切换为 tree mirror bundle，mirror 未准备好时不再回退到旧 schema surface。
- [x] `context_tree.list/expand/collapse/pin/unpin/estimate/enable_tool_schema/disable_tool_schema` 作为 Tool local package 进入 catalog。
- [x] mirror 可用时真实 advance 移除 legacy `available_tools` system block。
- [x] 删除/停用 `build_available_tools_block` 的主路径，工具可调用面由 provider schema 承担，可见面由 `tools.available` 节点承担。

验收：

- 未 enable 的 tool schema 不进入 provider payload。
- enable 后只镜像指定 tool schema。
- ABAC deny 的 tool 不出现在 Agent view。

### CW-5：Skill Nodes

- [x] Skills adapter 产出 resolved/available skill nodes。
- [x] 展开 skill node 可通过 Skills application 读取 SKILL.md。
- [x] Skill content 挂为 child node。
- [x] `read_skill` action 语义化为一等 action，并通过 `context_tree.read_skill` 暴露。
- [x] 删除/停用 skills catalog prompt block 主路径；技能目录只保留为 context tree metadata 和 resolution event。

验收：

- not ready skill 不出现在 Agent view。
- read_skill 后 content node 有 estimate。

### CW-6：Memory Nodes

- [x] Memory adapter 产出当前可见 readable layer scope nodes。
- [x] `recall_memory` action 通过 `context_tree.recall_memory` 暴露。
- [x] recall result 挂到对应 memory node 下。
- [x] private/shared/project/team/system 的治理视图与 UI 筛选：Memory scope nodes 携带 governance metadata，Workbench Context 面板可按记忆层筛选。
- [x] 删除/停用 `recall_prompt_memories` 主路径；memory 内容只通过 `memory.visible` 和 `context_tree.recall_memory` 主动披露。

验收：

- agent 只能看到 policy 允许的 scopes。
- recall result 不跨 scope 泄露。

### CW-7：Artifact / Workspace Nodes

- [x] Artifact adapter 支持从 session `image_ref/file_ref` 发现 image/file handle，并保留 caption/preview/original/download 元数据。
- [x] `context_tree.open_artifact` 支持把 artifact node 解析到 owner artifact variant。
- [x] Provider attachment mirror 支持已打开 artifact 的 image/file content blocks。
- [x] Workspace adapter 接管 bootstrap files 的树节点展开。
- [x] 停用 `load_workspace_context_files` 主路径，PromptSurfaceBuilder 不再直接注入 workspace 文件内容。

验收：

- 历史图片可以展开查看。
- provider 不支持 vision 时保留 caption/placeholder。
- 大文件按节点 estimate 和预算降级。

### CW-8：PromptSurfaceBuilder 收口

- [x] 真实 advance prompt 插入 `<context_tree>` system message，并记录 snapshot id。
- [x] PromptSurfaceBuilder 不再把 agent/runtime 作为独立 system message 注入 LLM；它只生成树节点块给 Context Workspace。
- [x] `agent_instruction` 转为 `agent.identity` node 正文。
- [x] `runtime_context` 转为 `run.runtime` node 正文。
- [x] 移除 workspace bootstrap block 拼装主路径，workspace 文件只通过 context tree 展开。
- [x] 移除 skills catalog block 拼装主路径，技能内容改为 `skills.available` / `context_tree.read_skill` 渐进披露。
- [x] 移除 session tools guidance block 主路径，session 工具说明回到 tool function description/schema 与 `tools.available` 节点。
- [x] 移除 available tools inventory block 主路径，工具清单不再作为手写 system prompt。
- [x] 移除 recalled memory block 主路径，自动 recall 不再直接注入 system prompt。
- [x] Flow prompts 转为 `run.flow` node，由 orchestration 提供 mode/hint，context tree 负责渲染。
- [x] PromptSurfaceBuilder 退化为 run/profile/session/tool surface 输入收集器；真实 provider prompt 由 context render snapshot + transcript + attachment bundle 组成。
- [x] prompt report payload 改为 `context_blocks` / `context_budget` / `context`。
- [x] 删除旧 prompt block 主路径：available tools、session tools、skills catalog、recalled memory、flow prompts、workspace bootstrap。
- [x] orchestration run metadata 写入 `context_render_snapshot_id`，prompt report 内外部命名收成 context。
- [x] prompt report 写入 context render snapshot id、tree estimate、included/mirrored node ids；`estimated_total_tokens` 优先使用 render estimate。
- [x] prompt report 拆出 `ContextRenderReport` 值对象，减少 PromptSurfaceBuilder 与 render snapshot 字段耦合。

验收：

- 新 prompt body 主体是 `<context_tree>`。
- provider attachments 来自 tree nodes。
- 旧 block path 不再被 normal turn 使用。

### CW-9：Operations / UI

- [x] Operations 增加 context read model。
- [x] Operations projection 增加 `context_workspace` 模块入口。
- [x] Operations 展示 workspaces / visible nodes / render snapshots / diagnostics。
- [x] Operations 前端导航增加 Context Workspace 页面。
- [x] Workbench 展示 session context tree。
- [x] UI 支持 expand/collapse/pin/schema toggle/estimate。
- [x] render snapshot 可从 run detail 查看。
- [x] i18n 覆盖当前已落地页面固定文案。

验收：

- PC 端一屏可看关键上下文状态。
- loading/error/empty 不跳布局。
- Agent view 和 Human view 明确区分。

### CW-10：清理与文档

- [x] 删除旧 prompt-specific helper 主路径：`workspace_context.py`、`workspace_context_files` metadata、prompt preview context file DTO 已退场。
- [x] 更新 AGENTS.md。
- [x] 更新 docs/README.md。
- [x] 更新 tests/unit/README.md。
- [x] 更新 operations/ui contracts。
- [x] 跑验证套件。

## Validation Commands

按阶段选择：

```bash
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_domain.py
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py
PYTHONPATH=src pytest -q tests/unit/test_context_tree_tool.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_context.py tests/unit/test_prompt_transcript.py
PYTHONPATH=src pytest -q tests/unit/test_tool_access_architecture.py tests/unit/test_skills_context.py tests/unit/test_memory_runtime_service.py

cd frontend
npm run typecheck
npm run build
```

端到端本地验证：

```bash
make dev-up
python -m crxzipple.main db upgrade head
python -m crxzipple.main daemon status
```

## Backward Compatibility Policy

本轮迁移已经进入新主路径，不再保留旧 prompt 兼容面：

- 不保留旧 available tools block 作为 normal turn 主路径。
- 不保留 orchestration 直接 recall memory 的 normal turn 主路径。
- 不保留 skills catalog block 的 normal turn 主路径。
- 不保留 workspace bootstrap 直接扫文件的 normal turn 主路径。
- 不保留 context_workspace 的万能跨模块代理。

## Settled Decisions

1. Session reset 默认是否清空 context workspace？
   已按默认不清空落地：reset 后旧 instance 的消息会作为
   `session.history.folded` 下的 folded ranges 披露；显式清空策略后续再单独设计。

2. `pin` 是否跨 session？
   已按不跨 session 落地：pin/unpin 是 workspace-local node state，同一 node id
   在不同 session workspace 中互不影响。跨 session 偏好应进入 agent profile 或 settings policy。

3. Human force action 是否会进入 Agent view？
   已按 Agent view 过滤落地：Human/Runtime tree 可包含 `prompt_visible=false`
   的节点和原因，render snapshot / Agent prompt body 只包含 `prompt_visible=true`
   节点。被挡资源的审计原因不进入 Agent prompt。

4. Context tree 是否需要 daemon？
   已决策为当前不需要独立 daemon。它是应用服务 + persistence + events。
   只有出现自动折叠、自动摘要、过期归档等后台任务时，才接 daemon scheduler。

5. Tree render 使用 XML-like 是否固定？
   已固定为默认 prompt body 格式。内部 domain model 仍是 typed JSON；
   XML-like 只作为 LLM-facing render，不作为存储真相。

## 完成定义

本轮架构真正闭合时，应满足：

- Agent 看到的是 Context Tree prompt body。
- Agent 可以用 context_tree tools 操作真实树。
- Workbench/Operations 能观察同一棵树。
- 每个 run 有 render snapshot。
- Tool schemas/images/files 是从 tree nodes 镜像到 provider payload。
- 不可见资源不会进入 Agent view。
- Session bulk、history、artifact 回看不再靠隐式 prompt 拼接。
- PromptSurfaceBuilder 不再直接拼 tool/skill/memory/workspace/session bulk/flow 文本。
- 没有为了旧 prompt block 保留的大段兼容 shim。
