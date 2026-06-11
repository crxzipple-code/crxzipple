# Context Workspace / Session Segment Compaction 开发方案

日期：2026-06-01

> Current naming note (2026-06-07): Session compaction has been renamed to
> segment vocabulary across the owner API and Context Workspace prompt tree:
> `CompactSessionSegmentInput`, `compact_active_segment()`,
> `SessionInstance.metadata["segment"]`, `session.segment.compacted`, and
> `session.segment.*` / `session_segment`.

## 背景

当前 Context Workspace 已经把 normal turn 的历史对话从 provider-native `messages/contents` 长数组里收出来，改由 Prompt Tree 交付。这个方向是正确的，但现有 compaction 仍然沿用旧机制：

- 维护 run 生成一条 assistant summary message。
- 同一个 active session instance 中 summary 之前的消息被标记为 archived。
- Context Workspace 再把 archived messages 投影成 `Folded History`。

这能工作，但它把“压缩”实现成消息归档，而不是 session 语义上的上下文段落轮转。后续应以 session module 的 `SessionInstance / active_session_id` 作为 segment 边界，让 Prompt Tree 只负责上下文披露和观察，不再承担 owner 资源治理。

## 本轮结论

1. Prompt Tree 是指导性的上下文交付层，不是特殊化资源工具系统。
2. 当前用户输入继续放 provider-native `user` content。
3. 当前 tool loop 继续使用 provider-native tool protocol。
4. 历史 session、tool interaction、skill 摘要、memory 摘要、artifact handle 进入 Prompt Tree。
5. Skill 只需要把 `skill.md` 的介绍和结构挂到树上；模型如果要深入阅读，调用普通文件、浏览器、workspace、web 等工具。
6. 工具结果已经会记录为 session message，后续可被 Context Workspace 投影成 `tool_interaction`。
7. 压缩边界应从“archive 一批消息”升级为“关闭当前 segment / session instance，打开新 segment”。

## 目标结构

理想 Prompt Tree 里的 session 部分：

```xml
<context_tree>
  <session>
    <segment id="current" state="expanded">
      <summary>Current active session segment.</summary>
      <recent_messages />
      <older_messages state="collapsed" />
      <tool_interactions />
    </segment>

    <segment id="previous" state="collapsed">
      <summary>Compacted summary of the previous session segment.</summary>
      <message_range state="folded" />
    </segment>
  </session>
</context_tree>
```

语义分工：

- `session` module 持有 session、session instance、message、segment 轮转事实。
- `orchestration` 触发 maintenance run，并请求 session 执行 segment compaction/rotation。
- `context_workspace` 读取 session query surface，把 current segment、previous segment、summary、folded message range 投影成 Prompt Tree。
- `tool`、`skill`、`memory`、`artifact` 等模块继续持有自己的资源真相；Context Workspace 只放可见摘要和 handle。

## 当前实现基线

已经存在：

- `Session.active_session_id` 和 `SessionInstance`。
- `SessionApplicationService.reset_session()` 可关闭当前 instance 并打开新 instance。
- `SessionApplicationService.archive_messages()` 可标记消息为 archived。
- `ContextWorkspace SessionContextNodeProvider` 已经按 active session 和 folded history 组织节点。
- `ContextRenderService` 只在节点展开时渲染内容，折叠节点只渲染 `title/summary`。
- `OrchestrationMaintenanceService.apply_compaction_summary()` 能在 compaction run 完成后归档旧消息并写 session metadata。

主要缺口：

- compaction 没有正式触发 session instance rotation。
- compaction summary 没有成为明确的 segment summary 事实。
- folded history 以 archived message 为主，不是以 closed segment 为主。
- 旧 `context_tree.read_skill/open_artifact` 方向容易把 Context Tree 做成特殊资源工具系统，需要收敛为普通工具读取资源、Prompt Tree 只披露结构。
- 展开旧 segment 缺少预算守卫，模型可以一次性把大量历史重新带入 prompt。

## 设计原则

### 1. Prompt Tree 不是资源 owner

Context Workspace 节点是上下文可见性 handle，不是资源副本。

禁止方向：

```text
Context Workspace 解析 skill.md 外链并替用户/模型穷举全部资源。
Context Workspace 自己实现通用文件读取、网页读取、artifact 内容读取。
Context Tree Tool 发展成另一套资源工具协议。
```

推荐方向：

```text
Prompt Tree 展示 skill.md 摘要、能力说明、入口路径。
模型通过普通 tool 阅读 skill.md、workspace 文件、网页或 artifact。
工具结果进入 session，并在下一轮作为 tool_interaction 被树化观察。
```

### 2. 历史压缩以 segment 为边界

`SessionInstance` 是 session 的上下文 segment。Compaction 应该对 segment 生效：

- 当前 segment 超出预算或命中维护策略。
- Orchestration 触发 compaction run。
- LLM 输出 compacted summary。
- Session module 关闭当前 segment，保存 segment summary。
- Session module 打开新 active segment。
- Context Workspace 默认只渲染旧 segment summary，不渲染旧 segment 原文。

### 3. Provider-native message 只保留当前交互语义

保留：

- 当前用户输入：provider-native `user`。
- 当前 assistant tool call：provider-native assistant function call。
- 当前 tool result：provider-native tool message。

转入 Prompt Tree：

- 旧用户/assistant 消息。
- 旧 tool interaction。
- closed segment summary。
- skill/memory/artifact/workspace 可见 handle。

### 4. 折叠有两层含义

UI/XML 显示折叠：

- 只是视觉层级，可展开查看已在 Prompt Tree 里的 XML。

业务语义折叠：

- 节点内容没有进入 prompt body，只保留 summary/handle。
- 展开需要改变 Context Workspace node state 或由普通工具读取资源后产生新的 session/tool result。

后续实现必须把这两层区分清楚。

## 目标数据模型

### SessionInstance 增强

建议给 `SessionInstance.metadata` 补充标准字段：

```json
{
  "bulk": {
    "kind": "active|compacted|reset",
    "summary_message_id": "msg_xxx",
    "summary_text": "...",
    "compaction_run_id": "run_xxx",
    "archived_message_count": 42,
    "archived_through_sequence_no": 128,
    "compacted_at": "2026-06-01T00:00:00Z"
  }
}
```

字段含义：

- `kind=active`：当前正在写入。
- `kind=compacted`：已关闭并有 summary。
- `summary_message_id`：summary 作为 session message 时的引用，可选。
- `summary_text`：segment summary 的读模型字段，便于 tree 快速投影。
- `archived_message_count`：压缩时归档的消息数量。
- `archived_through_sequence_no`：旧 segment 被摘要覆盖到的序号。

### Session API / Application 增强

新增应用用例：

```python
@dataclass(frozen=True, slots=True)
class CompactSessionSegmentInput:
    session_key: str
    session_id: str
    summary_message_id: str
    summary_text: str
    compaction_run_id: str
    archived_through_sequence_no: int | None = None
    reason: str | None = None

class SessionApplicationService:
    def compact_active_segment(self, data: CompactSessionSegmentInput) -> CompactSessionSegmentResult:
        ...
```

职责：

1. 校验 `session_id` 是当前 active instance。
2. 将 summary 写入当前 instance metadata。
3. 将旧消息归档或标记 folded。
4. 关闭当前 `SessionInstance`。
5. 打开新的 `SessionInstance`，更新 `active_session_id`。
6. 记录 `session.segment.compacted` / `session.reset` 或更明确事件。

注意：不要让 orchestration 直接操作 session internals。

### Context Workspace Session 投影

`SessionContextNodeProvider` 应改为按 instance 建树：

```text
session.current
  session.segment.current
    session.messages.current

  session.segment.compacted.<instance_id>
    session.segment.messages.<instance_id>.<from>.<to>
```

节点状态：

- current segment 默认 expanded。
- compacted segment 默认 collapsed。
- compacted segment summary 默认 visible。
- compacted raw message ranges 默认 collapsed，且不主动加载 children。

## Prompt Tree 与 Skill 的新边界

Skill 在 Prompt Tree 里只做指导性披露：

```xml
<skill id="skill.authoring" state="collapsed">
  <title>Skill Authoring</title>
  <summary>Use when creating or updating a skill package.</summary>
  <content>Optional short SKILL.md frontmatter/introduction excerpt.</content>
</skill>
```

不做：

- 自动解析所有 markdown links。
- 自动挂载外部网页。
- 自动把非 md 文件转成 tree resource。
- 为 skill 单独设计 `context_tree.read_skill` 的特殊路径。

模型要深入阅读时：

- 读 workspace/package 文件：用 workspace/file tool。
- 看网页：用 browser/web/search tool。
- 看 artifact：用 artifact/workspace/browser 等普通 tool。

这些工具结果会进入 session，再由 Context Workspace 投影成历史 tool interaction。

## 迁移计划

### Phase 1：Session segment 事实建模

- [x] 新增 `CompactSessionSegmentInput` / `CompactSessionSegmentResult`。
- [x] 在 Session application 中实现 `compact_active_segment()`。
- [x] 保证 compact 后旧 instance 关闭，新 instance 打开。
- [x] 给 `SessionInstance.metadata["segment"]` 写入 summary 和 compaction 元数据。
- [x] 发布明确事件，例如 `session.segment.compacted`。
- [x] 为 compact 后 message 归档策略补测试。

验收：

- compact 前后 `active_session_id` 变化。
- 旧 instance `status=closed`。
- 新 instance `status=active`。
- 旧消息不再进入 `active_session_only=True` 查询。
- summary 能从旧 instance metadata 或 summary message 查询到。

### Phase 2：Orchestration maintenance 接入 segment rotation

- [x] 改造 `apply_compaction_summary()`，不再只调用 `archive_messages()`。
- [x] compaction 成功后调用 `session_service.compact_active_segment()`。
- [x] 保留 summary message 作为事实，但 segment metadata 成为 tree 投影主入口。
- [x] 更新 preflight prompt budget 计算，把 Context Workspace session owner 估算纳入压缩压力。
- [x] 确保 compaction run 自身不污染新 active segment。

验收：

- 超预算 run 触发 maintenance 后，原 run 能在新 active segment 下继续。
- compaction summary 不作为普通 assistant 回复显示给用户。
- 旧 segment 不再出现在 normal turn provider-native transcript 中。

### Phase 3：Context Workspace session tree 改为 segment-first

- [x] `SessionContextNodeProvider` 先列 instances，再列消息。
- [x] current active instance 生成 `session.segment.current`。
- [x] current active instance 通过 `session.messages.current` 稳定暴露全部可见消息，不再做 recent / older 分页。
- [x] closed/compacted instance 生成 `session.segment.compacted.<id>` / `session.segment.closed.<id>`。
- [x] closed segment 默认只显示 summary。
- [x] 展开 closed segment 时分页加载 message ranges。
- [x] tool call/result 配对仍作为 `tool_interaction` 节点显示。
- [x] 修复当前 `compaction.summary` metadata 读取不一致问题，以 instance segment metadata 为主入口。

验收：

- Prompt XML 能看到 current segment 与 previous segment。
- previous segment collapsed 时只进入 summary。
- 展开 previous segment 后才进入 message/tool interaction 明细。
- Workbench Context 页显示的 XML 与 actual render snapshot 语义一致。

### Phase 4：预算与展开守卫

- [x] 给 Context Workspace render 增加 session owner 预算。
- [x] 展开 old segment 前估算 token，超预算时先拆分为更窄 range；单条仍超预算时只暴露 range notice。
- [x] 对 `Older Messages` 和 compacted/closed segment ranges 增加分页上限。
- [x] render snapshot metadata 记录 segment/session/tool interaction 相关计数与 session token/range 风险。
- [x] Operations Context Workspace 面板展示 segment 压缩和展开风险。

落地说明：

- `SessionContextNodeProvider` 为 closed/compacted segment 增加 `historical_range_limit`，range 过多时生成 `session_range_notice`，不一次性列出全部历史页。
- 每个 `session_message_range` 记录 `estimated_expanded_text_tokens`、`range_budget_soft_limit`、`range_budget_status`。
- 展开 range 前按真实消息估算；超过预算且包含多条消息时拆成更窄 range，拆到单条仍超限时生成 `Range Over Budget` notice。
- `ContextRenderService.estimate_breakdown["session"]` 记录 session owner 的节点数、segment 数、message/range/tool interaction 数和风险计数。
- render snapshot metadata 记录 `session_estimated_text_tokens`、`session_range_warning_count`、`session_range_blocked_count`、`session_range_limited_count`，Operations read model 已展示这些字段。

验收：

- 旧 segment 大量展开不会直接撑爆 context window。
- Prompt budget report 能分辨 current segment 与 folded segment。
- 触发 context limit 时维护逻辑能定位是哪类节点造成。

### Phase 5：收敛 context_tree 特殊工具语义

- [x] 审查 `tools/context_tree/tool.yaml` 中的动作。
- [x] 保留 tree 状态控制类动作：list / expand / collapse / pin / unpin / estimate / enable_tool_schema / disable_tool_schema。
- [x] 移除特殊资源读取动作：`read_skill`、`open_artifact`、`recall_memory` 的 owner-specific 语义。
- [x] 用普通 skill/workspace/browser/memory/tool 完成资源读取和检索。
- [x] 更新 prompt instructions：Context Tree 是上下文索引，不是资源读取工具集合。

落地说明：

- `context_tree` local package 不再依赖 memory runtime service 或 artifact service。
- skill node 展开只披露 `skill_read` handle，不把完整 SKILL.md 正文挂入树。
- memory scope node 只披露可见 scope，检索由 `memory_search` / `memory_read` 完成。
- artifact handle 进入 provider attachment mirror 改由通用 `pin` 状态触发；不再通过 `context_tree.open_artifact` 解析 owner variant。

验收：

- 模型要读 skill 深入内容时，走普通工具。
- 普通工具结果能进入 session，并在下一轮变成 `tool_interaction`。
- Context Tree tools 不再成为 owner service 的代理壳。

### Phase 6：前端观察和调试体验

- [x] Workbench Context 页面按 snapshot / live tree 区分观察入口。
- [x] XML 主视图优先展示 actual render snapshot。
- [x] 显示 current segment、previous compacted segment、summary、message range 的专门结构化导航。
- [x] 区分“XML 视觉折叠”和“业务语义折叠”。
- [x] 展开旧 segment 时显示 token estimate 和风险提示。

落地说明：

- Workbench Context 面板现在先展示 `Actual Prompt Snapshot`，再展示 `Live Tree Controls`。
- Snapshot 卡片增加 session budget / range warning / range blocked / range limited 风险条。
- Workbench 增加 `Session Segment Map`，从 live tree 聚合 `session_segment` 下的 range、notice、raw message/tool interaction 节点，显示 segment 状态、消息数、range/raw 加载数、估算 tokens、风险和展开/折叠动作。
- Workbench 增加 `Range Details`，逐 range 展示序号、消息数、估算 tokens、进入 actual prompt snapshot 的节点数、预算状态、原因和展开/折叠动作。
- `Session Segment Map` 增加 `Prompt` 列，用 actual render snapshot 的 `included_node_ids` 对齐每个 segment/range/raw 节点是否进入本次真实 prompt。
- `Session Segment Map`、`Range Details` 和 Live Tree XML 已联动选中态；点击 segment/range 或 XML 行会同步焦点并滚动到源码里的对应节点，精确节点强高亮、子节点弱高亮。
- range 节点和 range notice 已由 session adapter 输出标准 `range_reason_code`，Workbench 只翻译后端给出的原因码，不再只靠 `range_budget_status` / `notice_kind` 推断原因。
- `SessionContextNodeProvider` 已移除 active instance archived messages -> compacted segment 的 archive-only 观察路径；历史披露必须来自真实 closed/compacted `SessionInstance`。
- compacted segment 展开 raw range 时只读取 archived 原消息，compaction summary 保持为 Session owner metadata/summary，不再作为普通历史消息重复展开。
- Trace 详情页也展示同一组风险条，便于从链路调试里定位 prompt 体积风险。
- Live Tree 的源码折叠只作为视觉折叠；业务折叠仍由 Context Tree action 改变节点状态。
- Workbench 与 Trace 的 actual prompt snapshot 已改用共享 XML source viewer，
  直接展示记录下来的 `prompt_body`，带行号和视觉折叠，不再用裸 `<pre>` 预览真实
  prompt。

验收补充：

- `iab` in-app Browser 当前不可用；已使用本地 Playwright 打开 Workbench Context 页做截图级 QA，
  检查 actual prompt snapshot、源码折叠按钮、range detail 区域和首屏信息密度。

验收：

- 用户能看到发给 LLM 的真实 Prompt Tree。
- 用户能看出当前输入不在 tree 历史里重复出现。
- 用户能看到工具结果已经记录到 session 并树化。

## 测试计划

### Unit

- [x] `test_session_segment_compaction.py`
  - compact active segment opens new instance.
  - compact metadata is persisted on old instance.
  - active-only list excludes old segment messages.
  - closed segment messages remain queryable with instance id.

- [x] `test_orchestration_compaction_segment_rotation.py`
  - compaction run calls session compact use case.
  - normal run resumes with new active session id.
  - compaction summary is not delivered as user-facing final reply.

- [x] `test_context_workspace_session_adapter.py`
  - current segment node generated.
  - previous compacted segment node generated.
  - collapsed previous segment renders summary only.
  - expanded previous segment renders paged messages.

- [x] `test_orchestration_context_workspace_snapshot.py`
  - render snapshot includes segment metadata.
  - prompt body includes current segment and compacted summary.
  - provider-native transcript excludes old history.

### Integration

- [x] Start session, run several tool calls, trigger compaction, then continue task.
- [x] Verify tool results before compaction are visible as folded `tool_interaction`.
- [x] Verify new messages write to new active segment.
- [x] Verify rendered prompt XML matches recorded snapshot.
- [x] Verify Workbench / Trace actual prompt XML mounts from recorded snapshot with source lines and fold controls.
- [x] Verify Workbench actual prompt XML visually matches recorded snapshot with local Playwright screenshot QA.

## 兼容与清理原则

不保留长期双轨：

- 旧 `archive-only compaction` 观察路径已退场，不再从 active instance 的 archived messages 合成 compacted segment。
- 不新增旧 prompt assembler shim。
- 不让 Context Workspace 变成 resource owner service。
- 不让 frontend 绕过 `/context-workspaces` 或 Workbench read model 拼 prompt truth。

当前保留的历史读取规则：

- `compact_active_segment()` 关闭旧 `SessionInstance` 并写入 segment summary metadata。
- compacted segment 的 raw ranges 只读取 archived 原消息，避免 summary message 重复进入 prompt。
- manually reset 的 closed segment 仍可按 `message_visibility=all` 展开，用于普通 reset 历史追溯。

新增历史披露路径必须集中在 session/context workspace adapter 内，并以 owner query surface 为边界。

## 验收定义

本轮完成后，应满足：

1. Normal turn provider-native transcript 不回放旧历史长数组。
2. 历史按 session segment 出现在 Prompt Tree。
3. Compaction 会关闭当前 segment 并打开新 segment。
4. Previous segment 默认只暴露 summary。
5. 旧 segment 原始消息可按 range 展开，但受预算限制。
6. Skill 只作为 prompt guidance 节点；深入阅读走普通工具。
7. 工具结果进入 session，并可被树化成 tool interaction。
8. Workbench 能看到真实发给 LLM 的 Prompt Tree snapshot。

## 推荐施工顺序

1. 先做 Session segment compaction use case。
2. 再接 Orchestration maintenance。
3. 再改 Context Workspace session adapter。
4. 再补预算守卫。
5. 最后清理 context_tree owner-specific 特殊动作和前端展示。

不要先改 UI；UI 需要等 segment read model 稳定后再做，否则会继续围绕旧 archive 投影缝补。
