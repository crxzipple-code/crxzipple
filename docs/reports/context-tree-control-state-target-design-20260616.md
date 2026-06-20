# Context Tree Control-State Target Design

日期：2026-06-16

## 结论

Context Tree 的目标形态不是 provider prompt body，也不是 owner 数据仓库。它是会话级上下文控制面：

```text
Owner modules own truth.
Context Tree owns selection/control state.
Slice Builder resolves owner refs live.
Provider Renderer emits provider-native input/tools.
Orchestration only advances the loop.
```

换句话说：**Tree owns selection, not truth.**

Tree 只保存 owner 引用、展开/折叠/pin/schema_enabled/summary_mode 等控制状态、预算估算和呈现策略。Session、Orchestration、Tool、LLM、Memory、Skills、Artifacts、Workspace 继续拥有各自事实。

## 当前问题

当前 Context Tree 已经有较完整的 owner node provider：

- Session：segment、item range、tool interaction。
- Tool：source、bundle、group、function。
- Skills：skill handles。
- Memory：memory scopes。
- Artifacts：session artifact handles。
- Agent：agent home。
- Workspace：workspace resource files。

但它还没有成为 LLM 上下文控制内核。当前主链路仍然近似为：

```text
orchestration -> session replay window -> transcript/messages/input_items -> provider input
context_workspace -> debug body / metadata / tool schema mirror -> request metadata/tools
```

也就是说，树能描述很多上下文状态，但 session history、skill catalog、tool result replay 等并不完全由树的选择状态决定。

目标链路应收敛为：

```text
owner facts
  -> Context Tree refs + control state
  -> Context Slice
  -> Provider Renderer
  -> LLM request
```

## 树的完整目标形态

顶层结构：

```text
context.root
├─ runtime
├─ task
├─ session
├─ capabilities
├─ knowledge
└─ render
```

### runtime

```text
runtime
├─ runtime.contract
├─ runtime.agent
│  ├─ runtime.agent.identity
│  └─ runtime.agent.home
├─ runtime.environment
├─ runtime.permissions
├─ runtime.provider
│  ├─ runtime.provider.profile
│  ├─ runtime.provider.transport
│  └─ runtime.provider.capabilities
└─ runtime.budget
```

用途：

- 表达本轮运行环境、权限、provider/model/transport 能力和预算。
- 默认进入 LLM 的应该是短 runtime slice，不是完整树正文。

事实来源：

- Agent module。
- LLM module。
- Access / Authorization / Daemon / Runtime metadata。

### task

```text
task
├─ task.current_goal
├─ task.user_request
├─ task.plan
├─ task.progress
├─ task.blockers
├─ task.waiting
└─ task.next_action
```

用途：

- 表达当前用户目标、运行进度、阻塞点、等待状态和下一步。
- 默认进入 LLM slice，要求短、确定、无猜测。

事实来源：

- Orchestration run。
- Session current user item。
- Assistant progress / final / blocked facts。

### session

Session 子树必须表达轮转。目标层级是：

```text
Session -> Instance -> Segments -> Segment -> Turn -> Step -> Item
```

目标树形：

```text
session
├─ session.frontier
│  ├─ session.frontier.active_instance
│  ├─ session.frontier.current_turn
│  ├─ session.frontier.model_visible_sequence
│  └─ session.frontier.user_visible_sequence
│
├─ session.instances
│  ├─ session.instance.active
│  │  └─ session.segments
│  │     ├─ session.segment.active
│  │     │  └─ session.turns
│  │     │     ├─ session.turn.current
│  │     │     │  └─ session.steps
│  │     │     │     ├─ session.step.intake
│  │     │     │     ├─ session.step.llm
│  │     │     │     ├─ session.step.tool_batch
│  │     │     │     ├─ session.step.approval
│  │     │     │     └─ session.step.final
│  │     │     ├─ session.turn.previous.1
│  │     │     └─ session.turn.previous.2
│  │     │
│  │     ├─ session.segment.compacted.1
│  │     │  ├─ session.segment.summary
│  │     │  └─ session.segment.ranges
│  │     │     ├─ session.range.1-40
│  │     │     └─ session.range.41-80
│  │     │
│  │     └─ session.segment.archived.1
│  │        ├─ session.segment.summary
│  │        └─ session.segment.ranges
│  │
│  ├─ session.instance.previous.1
│  │  └─ session.segments
│  │     ├─ session.segment.summary
│  │     └─ session.segment.ranges
│  │
│  └─ session.instance.previous.2
│
├─ session.pinned
│  ├─ session.item.pin_1
│  └─ tool.result.pin_2
│
└─ session.index
   ├─ session.index.by_turn
   ├─ session.index.by_tool_call
   ├─ session.index.by_artifact
   └─ session.index.by_topic
```

`session.step.*` 下挂 runtime-level 引用节点。注意：这里不直接挂 provider
raw response item。Provider 原始响应先由 LLM module normalize 为
`LlmResponseItem` / `LlmInvocation` 真相，再由 runtime response projector 映射为
assistant progress、assistant message、assistant tool call 等 runtime 语义节点。Tree
保存这些 runtime 语义节点的 owner refs 和呈现状态。

```text
session.step.llm
├─ runtime.llm_invocation.{id}
├─ runtime.assistant_progress.{id}
├─ runtime.assistant_message.{id}
└─ runtime.assistant_tool_call.{call_id}

session.step.tool_batch
├─ tool.call.{call_id}
├─ tool.run.{tool_run_id}
└─ tool.result.{call_id}

session.step.final
└─ session.item.final_answer
```

这让树能回答：

- 当前 active instance 是哪个？
- instance 下有哪些 segment？
- 哪个 segment 是 active / compacted / archived？
- 当前 turn 进行到哪个 step？
- 哪些 step 已呈现给模型？
- 哪些 tool call/result 完成、失败、等待、被折叠或被 pin？
- 当前 model-visible frontier 到哪里？

当前代码中的 `SessionInstance` 不应继续被伪装为 `session_segment`。Context Workspace 可以先用 owner_ref 指向现有 `SessionInstance`，但目标节点 kind 应区分 `session_instance` 和 `session_segment`。

LLM response item 也不应直接成为树节点 kind。树上应挂统一 runtime
semantics，例如：

```text
runtime.assistant_progress
runtime.assistant_message
runtime.assistant_tool_call
runtime.final_answer
runtime.blocked_state
```

这些节点的 `owner_ref` 可以追溯到底层事实：

```json
{
  "llm_invocation_id": "llminv_123",
  "llm_response_item_id": "respitem_456",
  "session_item_id": "sessitem_789",
  "execution_step_item_id": "execitem_abc",
  "tool_call_id": "call_abc"
}
```

Provider-specific raw payload、原始 response item、provider request/response preview
仍归 LLM module 和 Operations/Trace 观察面；Context Tree 只保存 runtime 语义投影和上下文呈现状态。

### capabilities

```text
capabilities
├─ tools
│  ├─ tools.active_surface
│  │  ├─ tools.function.exec
│  │  ├─ tools.function.web.fetch_text
│  │  └─ tools.function.context.read
│  │
│  ├─ tools.sources
│  │  ├─ tools.source.command
│  │  │  ├─ tools.group.process
│  │  │  └─ tools.group.shell
│  │  │     └─ tools.function.exec
│  │  │
│  │  ├─ tools.source.open_meteo
│  │  │  ├─ tools.group.geocoding
│  │  │  │  ├─ tools.function.open_meteo_geocoding.search_locations
│  │  │  │  └─ tools.function.open_meteo_geocoding.get_location
│  │  │  └─ tools.group.forecast
│  │  │     └─ tools.function.open_meteo_weather.forecast_weather
│  │  │
│  │  └─ tools.source.browser
│  │
│  ├─ tools.deferred
│  │  ├─ tools.source.github
│  │  └─ tools.source.slack
│  │
│  └─ tools.blocked
│     ├─ tools.blocked.auth_required
│     └─ tools.blocked.runtime_unavailable
│
├─ skills
│  ├─ skills.available
│  │  ├─ skill.browser
│  │  ├─ skill.openai-docs
│  │  └─ skill.github
│  ├─ skills.loaded
│  │  └─ skill.browser.SKILL.md
│  └─ skills.blocked
│
└─ model
   ├─ model.capability.vision
   ├─ model.capability.files
   ├─ model.capability.reasoning
   └─ model.capability.provider_native_continuation
```

规则：

- `tools.source` / `tools.group` 是发现入口。
- `tools.function` 才能进入 provider tool schema。
- `schema_enabled=true` 的 function 进入 `tools.active_surface`。
- `expand source/group` 必须能改变下一轮 active tool surface；否则只是展示，不是能力发现。
- Tool schema 和 execution binding 必须同源，避免模型看见的工具无法执行。

### knowledge

```text
knowledge
├─ memory
│  ├─ memory.scopes
│  │  ├─ memory.scope.session
│  │  ├─ memory.scope.agent
│  │  └─ memory.scope.workspace
│  └─ memory.recalled
│     ├─ memory.item.1
│     └─ memory.item.2
│
├─ workspace
│  ├─ workspace.root
│  ├─ workspace.files
│  │  ├─ workspace.file.AGENTS.md
│  │  ├─ workspace.file.runtime_contract.md
│  │  └─ workspace.file.current
│  └─ workspace.search_results
│
└─ artifacts
   ├─ artifacts.session
   ├─ artifact.image.{id}
   ├─ artifact.file.{id}
   └─ artifact.generated.{id}
```

规则：

- 默认只呈现 handle/summary。
- `opened=true` 或 `pinned=true` 的资源才进入 slice。
- 大文件、图片和 artifact 由 provider renderer 根据 provider 能力渲染成正文、file ref、image block 或 omitted report。

### render

```text
render
├─ render.current_slice
│  ├─ render.slice.instructions
│  ├─ render.slice.task
│  ├─ render.slice.history
│  ├─ render.slice.tool_results
│  ├─ render.slice.skills
│  ├─ render.slice.memory
│  ├─ render.slice.artifacts
│  └─ render.slice.tools
│
├─ render.active_tool_surface
│  ├─ render.tool_schema.exec
│  ├─ render.tool_schema.context.read
│  └─ render.tool_schema.open_meteo_weather.forecast_weather
│
├─ render.omitted
│  ├─ render.omitted.old_history
│  ├─ render.omitted.large_tool_output
│  └─ render.omitted.unavailable_refs
│
├─ render.budget
│  ├─ render.budget.text
│  ├─ render.budget.tool_schema
│  ├─ render.budget.image
│  └─ render.budget.file
│
└─ render.loss_report
   ├─ render.loss.provider_limits
   ├─ render.loss.budget_limits
   └─ render.loss.unresolved_refs
```

`render` 分支是 request-time decision report，不是 owner truth。它回答：

- 本轮发给 LLM 的 input slice 是什么？
- 哪些 nodes 被压缩、折叠、省略？
- 哪些 tools 进入 provider schema？
- token / tool schema / image / file 预算如何分布？
- provider 限制造成哪些 loss？

## 节点通用字段

节点保存控制信息，不保存事实正文：

```json
{
  "node_id": "session.turn.current",
  "owner": "session",
  "kind": "session_turn",
  "owner_ref": {
    "session_key": "...",
    "session_id": "...",
    "turn_id": "run_123",
    "sequence_range": [120, 138]
  },
  "state": {
    "visible": true,
    "expanded": true,
    "pinned": false,
    "opened": true,
    "schema_enabled": false,
    "summary_mode": "compact",
    "included_in_next_slice": true
  },
  "estimate": {
    "summary_tokens": 80,
    "expanded_tokens": 2600,
    "selected_tokens": 320
  },
  "render_policy": {
    "reason": "current_turn",
    "priority": 10
  }
}
```

Tool function 节点示例：

```json
{
  "node_id": "tools.function.open_meteo_weather.forecast_weather",
  "owner": "tool",
  "kind": "tool_function",
  "owner_ref": {
    "tool_id": "open_meteo_weather.forecast_weather",
    "source_id": "bundled.openapi.open_meteo_weather"
  },
  "state": {
    "visible": true,
    "expanded": true,
    "schema_enabled": true,
    "included_in_next_tool_surface": true
  },
  "estimate": {
    "tool_schema_tokens": 420
  }
}
```

Tool result 节点示例：

```json
{
  "node_id": "tool.result.call_abc",
  "owner": "tool",
  "kind": "tool_result",
  "owner_ref": {
    "tool_run_id": "toolrun_123",
    "tool_call_id": "call_abc",
    "turn_id": "run_123",
    "step_id": "step_tool_batch"
  },
  "state": {
    "status": "completed",
    "visible": true,
    "expanded": false,
    "summary_mode": "compact",
    "included_in_next_slice": true,
    "pinned": false
  },
  "estimate": {
    "summary_tokens": 40,
    "expanded_tokens": 1800,
    "selected_tokens": 40
  }
}
```

## LLM 默认看到的是 slice

LLM 默认不看完整 Context Tree。它只看 renderer 生成的上下文切片：

```text
Current task:
- ...

Progress:
- ...

Visible history:
- Current turn, steps intake -> llm -> tool_batch.
- Previous 2 turns compact summaries.
- One pinned tool result.

Active tools:
- exec
- context.read
- context.expand
- open_meteo_weather.forecast_weather

Expandable:
- previous instance summary/ranges
- browser skill
- workspace files

Omitted:
- 4 old segments compacted
- 2 large tool outputs folded
```

模型通过 context tools 改变 Tree 状态：

```text
context.expand(capability/tool source/session range/skill)
context.read(owner ref or node handle)
context.pin(node)
context.collapse(node)
context.enable_tool_schema(tool function)
context.diff()
```

这些工具返回的是动作结果和可用 handle，不返回整棵树正文。完整 debug tree 只用于 debug/Operations/显式 inspect。

## 施工原则

- 不复制 owner 数据正文到 Context Tree。
- 不把完整 `<context_tree>` 默认注入 provider input。
- 不保留 orchestration 直接拼 session transcript 的长期主路径。
- 不做任务特化判断，不维护 keyword router。
- 不做新旧双轨兼容；数据库可重建时按目标结构迁移。
- 不把无法形成准确结论的内容发送给 LLM。
- Provider-specific render 只发生在 LLM renderer / provider adapter 边界；renderer 消费的是 Context Slice 派生的中立 input items、active Tool Surface、provider attachments 和 provider profile，不从 tree metadata 额外生成 system prompt。
- Context Tree 操作影响下一轮 Context Slice 和 Tool Surface，不能只是 UI 展示。

## 迁移 Checklist

- [x] 定义 `ContextSlice` DTO：task/history/tool_results/skills/memory/artifacts/tools/render_report。
- [x] 定义 `ContextSliceBuilder`：按 tree state live resolve owner refs。
- [x] 将 orchestration 的 session replay 主路径替换为 `ContextWorkspace.build_slice(...)`。
- [x] 重构 session tree adapter：区分 `session_instance`、`session_segments_root`、`session_segment`、`session_turn`、`session_step`、`session_item`。
- [x] 将 orchestration execution chain/step/item 以 refs 挂到 `session.turn.*` 下。
- [x] 将 tool call/result 的 status、included_in_next_slice、summary_mode 写成树控制状态。
- [x] 将 tool source/group expand 与 function schema activation 闭合到 active tool surface。
- [ ] 将 skills catalog direct injection 收敛为 skills slice。
- [ ] 将 memory/artifact/workspace direct materialization 收敛为 knowledge slice。
- [x] Provider renderer 只消费 Context Slice 派生的中立 input items、active Tool Surface、provider attachments 和 provider profile。
- [ ] Operations 展示 Tree control state、current slice、omitted、budget、loss report。
- [x] 单测覆盖：展开 tool source 后下一轮 provider tool schema 增加对应 function。
- [x] 单测覆盖：session history 是否进入 provider input 由 tree state 决定。
- [x] 单测覆盖：旧 instance/segment 默认 summary，可按 range 展开。
- [x] 单测覆盖：tool result 完成但未 included 时不进入下一轮 LLM input。
