# Context Workspace / 树化 Prompt 设计

本文记录当前对 Prompt Engineering 重构的目标设计。它是后续施工依据，不是历史讨论纪要。

## 背景

当前系统由 `PromptAssembler` 在 orchestration 内部运行时拼装 prompt，来源包括 agent instruction、runtime context、flow prompt、session transcript、workspace bootstrap、available tools、session tools、skills catalog、memory recall 和 artifact materialization。

这套实现能运行，但它仍然是“拼装器”：

- tool、skill、memory、session、workspace 的上下文装配逻辑散落在 orchestration prompt 代码里。
- tool schema 目前偏“可用就带”，缺少注意力治理。
- session bulk、compaction summary、archived messages 是隐式窗口逻辑，agent 不能直观看见或控制。
- 历史图片和文件为了压缩会被替换为占位，agent 很难主动回看。
- 人类和 Operations 面很难解释“这次 LLM 到底看到了什么、为什么没看到什么”。

我们要把 Prompt Engineering 从“拼一段 prompt”升级为：

**维护 agent 和本地 runtime 共治的 Context Tree。树本身就是 prompt 主体，provider-specific tools/images/files 只是从树节点派生出的额外附件。**

## 目标

1. **树化 prompt**
   LLM 看到的是一棵已授权的上下文树，而不是一坨临时拼接文本。Session、Memory、Skill、Tool、Workspace、Artifact 都是节点。

2. **agent 可操作**
   Agent 可以通过工具操作真实树：展开、折叠、pin、读取 skill、召回 memory、打开 artifact、启用 tool schema 等。

3. **本地可控制**
   Runtime 和 UI 可以基于同一棵树观察、估算、控制上下文，而不是从 prompt 字符串里反推。

4. **所见即所得估算**
   每个节点都能估算 text token、tool schema 成本、image/file payload 成本和 provider 附件成本。人和 agent 都能看见上下文压力来自哪里。

5. **吸收行业变化**
   新出现的概念不再迫使 orchestration prompt 重新设计。新的 MCP resource、browser DOM snapshot、computer-use scene、voice/video context、policy capsule 等都只是新增 node kind。

## 核心原则

### 树是真实状态，不是影子投影

Agent 和 UI 操作的是 `ContextTree` 本体：

- `expand`
- `collapse`
- `pin`
- `unpin`
- `recall_memory`
- `read_skill`
- `open_artifact`
- `enable_tool_schema`

不存在让 agent 操作一份 projection，再同步回真实状态的中间层。

### 树就是 prompt 主体

调用 LLM 时，prompt body 应保持树结构。Provider 不认识树时，由 adapter 做很薄的适配。

```text
Context Tree Prompt Body
  ├─ Agent / runtime instruction nodes
  ├─ Session nodes
  ├─ Memory nodes
  ├─ Skill nodes
  ├─ Tool nodes
  ├─ Artifact nodes
  └─ Workspace nodes

Provider Attachments
  ├─ selected tool schemas copied from tool nodes
  ├─ selected images copied from artifact nodes
  └─ selected files copied from artifact nodes
```

Provider attachments 是从节点派生出的额外输入，不改变树作为 prompt 主体的事实。

### 硬约束先于树可见性

ABAC、Access readiness、memory scope、skill readiness、tool readiness、surface policy 决定节点是否可见。不可见资源不能以“禁用节点”形式暴露给 agent。

Prompt Engineering 只处理已经可见的上下文如何展开、折叠、估算和交付。

### 不写人工联想规则

不要在系统里维护 keyword router 或 trigger synonym map。比如“用户说画图就强塞 image tool”这类规则不应出现。

系统提供已授权上下文树和操作能力。语义判断由 LLM 通过树操作完成；本地 runtime 只负责硬约束、状态、预算和安全。

### 不把 embedding 下沉到所有模块

Embedding 可以是某些 owner module 内部 engine 的实现，例如 memory 或 docs search，但不能成为所有模块的相关性契约。

模块边界上暴露结构化事实、查询能力、节点摘要和 owner handle。

## 新模块定位

建议新增 `context_workspace` module。它不是 orchestration 的子功能，而是 agent 和本地 runtime 的上下文工作台。

### 它拥有

- `ContextWorkspace`：绑定 session 的上下文工作区。
- `ContextNode`：树节点，保存 handle、summary、状态、估算和 owner ref。
- `ContextNodeState`：collapsed、expanded、pinned、loaded、schema_enabled、consumed、archived 等。
- `ContextTreeOperation`：agent/UI/runtime 对树的操作记录。
- `ContextEstimate`：节点级和整棵树的 prompt/provider 成本估算。
- `ContextRenderSnapshot`：某次 run 调用 LLM 时的树渲染快照和 provider attachment 快照。

### 它不拥有

| 真相 | Owner |
|---|---|
| run lifecycle | `orchestration` |
| session / messages / instances | `session` |
| memory scope / recall / remember | `memory` |
| skill package / SKILL.md / readiness | `skills` |
| tool source / function / schema / readiness | `tool` |
| artifact image / file | `artifacts` |
| credential / OAuth / readiness | `access` |
| ABAC policy | `authorization` |

`context_workspace` 保存上下文节点状态，不保存 owner module 的业务真相。

## Session 绑定方式

树的活状态绑定 `Session`，每个 `Run` 记录一次调用时快照。

```text
Session
└─ Context Workspace
   ├─ node states
   ├─ expanded / collapsed state
   ├─ pinned nodes
   ├─ loaded skill / memory / artifact handles
   ├─ folded history nodes
   └─ estimates

Run
└─ Context Render Snapshot
   ├─ tree revision
   ├─ rendered prompt body
   ├─ provider attachments
   ├─ enabled tool schemas
   ├─ loaded image/file payload refs
   ├─ estimate
   └─ operation trace reference
```

原因：

- Context Tree 是一个持续会话工作台，需要跨 turn 保留。
- Run 是短生命周期执行单元，只需要记录当时 LLM 实际看见的树快照。
- Agent 不应全局共享树状态，否则不同 session 会互相污染。

## 树节点模型

内部使用 typed JSON/domain model，给 LLM 的 prompt body 使用 XML-like 树结构渲染。XML-like 的目的不是做 AI HTML，而是提供可嵌套、可扩展、LLM 易读的边界。

节点最少需要：

```json
{
  "node_id": "memory.private.assistant",
  "owner": "memory",
  "kind": "memory_scope",
  "title": "Private Memory",
  "summary": "Private memory visible to the current agent.",
  "state": "collapsed",
  "actions": ["expand", "recall"],
  "owner_ref": {
    "scope_ref": "assistant"
  },
  "estimate": {
    "text_tokens": 42,
    "tool_schema_tokens": 0,
    "image_count": 0,
    "file_tokens": 0
  },
  "revision": "owner-specific-revision",
  "freshness": "live"
}
```

Prompt body 形态示例：

```xml
<context_tree session="session-key" revision="42">
  <node id="session.current" kind="session" state="expanded">
    <summary>Current active session.</summary>
  </node>

  <node id="memory.private.assistant" kind="memory_scope" state="collapsed" actions="expand recall">
    <summary>Private memory visible to this agent.</summary>
  </node>

  <node id="tools.browser" kind="tool_group" state="collapsed" actions="expand enable_schema">
    <summary>Browser automation capabilities are available.</summary>
  </node>
</context_tree>
```

## 操作协议

所有树化 prompt 操作都由 `context_workspace` module 提供。Owner modules 只提供资源查询和业务动作。

### Agent-facing actions

- `context_tree.list`
- `context_tree.expand(node_id)`
- `context_tree.collapse(node_id)`
- `context_tree.pin(node_id)`
- `context_tree.unpin(node_id)`
- `context_tree.estimate()`
- `context_tree.recall_memory(node_id, query)`
- `context_tree.read_skill(node_id)`
- `context_tree.open_artifact(node_id, mode)`
- `context_tree.enable_tool_schema(node_id)`
- `context_tree.disable_tool_schema(node_id)`

Agent-facing actions 必须是窄接口，不能提供 `call(owner, action, payload)` 这种万能代理。

### Runtime-facing actions

- `ensure_workspace(session_key, agent_id)`
- `render_prompt_body(session_key, run_context)`
- `extract_provider_attachments(session_key, run_context, provider_capabilities)`
- `record_render_snapshot(run_id, snapshot)`
- `fold_session_range(session_key, range, summary)`
- `apply_budget_policy(session_key, budget)`

### Human-facing actions

- `inspect_tree(session_key)`
- `inspect_node(node_id)`
- `force_pin(node_id)`
- `force_collapse(node_id)`
- `force_disable_schema(node_id)`
- `preview_estimate(session_key)`
- `inspect_render_snapshot(run_id)`

底层走同一套 application service，避免 agent、runtime、UI 三套逻辑分叉。

## Session Bulk 和历史折叠

当上下文超出 window 时，不应只靠隐式 archived messages。应该折叠成显式树节点。

```text
Session
├─ Current Instance
│  ├─ Recent Window
│  ├─ Pending Tool Results
│  └─ Artifacts
├─ Folded History
│  ├─ summary
│  ├─ decisions
│  ├─ open tasks
│  ├─ important tool results
│  ├─ artifacts index
│  └─ source ranges
└─ Previous Instances
   ├─ instance summary
   ├─ timeline
   ├─ message chunks
   └─ exact ranges
```

打开历史 session 是高风险操作，因为它可能立刻超过 window。因此历史必须分级披露：

1. summary 默认可见。
2. timeline 可展开。
3. message chunks 分页。
4. exact message range 按需读取。
5. artifact/image 作为 handle 按需打开。

展开历史不等于把历史全部塞进 LLM provider payload。它只是更新树状态。真正调用 LLM 时，runtime 根据树状态、预算和 provider 能力决定保留完整节点、摘要节点或附件镜像。

## Artifact / Image / File

历史图片和文件不应只有压缩占位。树节点应保留回看能力。

```text
Artifact Node
├─ metadata
├─ caption / observation
├─ thumbnail
├─ full payload handle
└─ provider attachment state
```

支持 vision 的 provider 可以从 image node 派生 image input。不支持 vision 的 provider 保留 caption 或 placeholder。图片被 LLM 看过后应优先生成短 observation node，后续默认用 observation，避免反复加载大 payload。

## Provider 适配

Provider adapter 必须保持薄。

- OpenAI 支持 native tools，则把已启用 tool node 的 schema 复制到 `tools`。
- 支持 image input，则把已打开 image node 的 payload 复制到 image input。
- 支持 file input，则把 file node 的 payload 复制到 file input。
- 不支持某类 native input，则保留树里的文本摘要或 placeholder。

Provider 特性不能反向污染 Context Tree 模型。

## Orchestration 边界

长期目标是 orchestration 不再直接拼 memory、skill、tool、workspace、session bulk 文本。

Orchestration 应继续负责：

- run lifecycle
- scheduler / executor / engine
- LLM invocation
- tool call 推进
- approval / denial / resume
- heartbeat / compaction / memory_flush 等 flow

Prompt 上下文交付应变成：

```text
orchestration run
  ↓
context_workspace.render_prompt_body(...)
context_workspace.extract_provider_attachments(...)
  ↓
LLM invocation
```

Flow prompt 可以作为树中的 runtime/flow 节点存在，而不是散落在字符串拼装里。

## Operations 和 UI

这棵树同时是 prompt 观察面和控制面。

Operations / Settings / Workbench 可以展示：

- agent 当前可见的上下文树。
- 节点展开、折叠、pin、schema enabled 状态。
- 每个节点的 token/image/file/schema 估算。
- 当前上下文压力。
- 上一次 run 的 render snapshot。
- 哪些节点被预算降级。
- 哪些操作由 agent 触发，哪些由人类触发。

被硬策略挡掉的资源可以在 Human/Runtime view 中以审计形式显示，但不能进入 Agent view。

## 事件与审计

Context Workspace 应发布事件，供 Operations observer 物化 read model。

建议事件：

- `context.workspace.created`
- `context.node.expanded`
- `context.node.collapsed`
- `context.node.pinned`
- `context.node.unpinned`
- `context.node.schema_enabled`
- `context.node.schema_disabled`
- `context.memory.recalled`
- `context.skill.read`
- `context.artifact.opened`
- `context.session.folded`
- `context.prompt.rendered`
- `context.budget.applied`

每次 run 必须保存当时 render snapshot，否则树后续变化后无法复现当时 LLM 看到的上下文。

## 分阶段施工

### Phase 1：Module 骨架和协议

- 新增 `modules/context_workspace`。
- 定义 domain model：workspace、node、node state、operation、estimate、render snapshot。
- 定义 application ports：session、memory、skills、tool、artifacts、authorization/access visibility。
- 提供最小 HTTP/CLI/query surface。
- 增加单元测试覆盖节点状态、操作权限、估算模型。

### Phase 2：Session Tree

- 为 session 创建默认 workspace。
- 将 active session、recent window、compaction summary、archived ranges、artifacts index 表达为节点。
- 保留现有 transcript 逻辑，但让它开始读取 session tree 的 rendered body。
- 建立 run snapshot 记录。

### Phase 3：Tool / Skill / Memory / Artifact 节点

- Tool 提供 visible tool nodes 和 schema attachment extraction。
- Skills 提供 ready skill nodes 和 read_skill action。
- Memory 提供 visible scope nodes 和 recall_memory action。
- Artifacts 提供 image/file nodes、caption、thumbnail、payload handle。

### Phase 4：PromptAssembler 收口

- 将当前 `available_tools` 文本、skills catalog、memory recall、workspace bootstrap、session bulk 逐步迁到 Context Tree。
- `PromptAssembler` 只保留 orchestration flow、LLM routing、provider call 所需薄逻辑。
- 删除长期双轨和大段兼容 shim。

### Phase 5：UI / Operations

- Settings/Workbench/Operations 增加 Context Tree 可视化和操作面。
- Operations read model 增加 context workspace health、node operations、run render snapshot、budget estimate。
- UI 显示每个节点的 prompt/provider 成本，支持人类 pin/collapse/disable schema。

### Phase 6：清理旧模式

- 清理 orchestration 里直接拼 tool/skill/memory/workspace/session bulk 的旧路径。
- 保留 owner module 的查询能力，不保留 prompt-specific 旧 facade。
- 更新 docs、AGENTS、测试 README。

## 不做什么

- 不做通用跨模块代理。
- 不统一 memory、skill、tool、session 的业务数据模型。
- 不把 ABAC 或 Access 移进 context workspace。
- 不为相关性写 keyword router。
- 不要求所有模块做 embedding。
- 不把树做成 AI HTML 或特化 XML 方言。
- 不让 provider payload 结构反向决定内部树模型。

## 当前结论

最终目标：

```text
Owner Modules 持有业务真相
        ↓
Context Workspace 维护真实上下文树
        ↓
Agent / Human / Runtime 共治树状态
        ↓
Context Tree 作为 Prompt Body 交给 LLM
        ↓
Provider Adapter 镜像部分节点到 tools/images/files
```

一句话：

**树不是 prompt 的素材，树就是 prompt。Provider 特化输入只是树节点的镜像附件。**
