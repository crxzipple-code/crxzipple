# Context Workspace Session History Delivery Upgrade Plan 2026-05-31

> Current naming note (2026-06-07): this report predates Context Tree schema v2.
> Current Context Workspace session nodes use `session.segment.*` /
> `session_segment`. Session owner internals may still call compaction units
> `bulk`, but Prompt Tree public nodes must use `segment`.

## 背景

Context Workspace 已经把 tool、skill、memory、artifact、workspace 等上下文逐步收成一棵真实的 prompt tree。Agent 和 UI 可以围绕这棵树执行 `expand`、`collapse`、`pin`、`estimate`、`enable_tool_schema` 等操作，orchestration 会在 LLM 调用前记录 render snapshot，并把树渲染成 XML 风格 prompt body。

迁移前 session 历史对话处于双通道状态：

1. 旧 `PromptSurfaceBuilder` 直接读取 active session messages，经 `build_prompt_transcript()` 转成 provider-native `LlmMessage`。
2. `SessionContextNodeProvider` 也把 recent / older / folded history 暴露为 context tree 节点，并由 Context Workspace 渲染成 prompt body。

这会让 prompt engineering 的控制权分散：历史对话既绕过树直接进入 provider messages，又在树上作为可观察节点存在。长期保留这条双轨会导致预算估算、折叠、回看图片、工具历史披露和 UI 所见即所得都不稳定。

本计划的目标是把 normal turn 的历史对话交付收归 Context Workspace tree，session module 只持有历史事实，orchestration 不再直接 replay 整段 active transcript。

## 迁移前实现基线

### Session 写入

当前用户输入在 run 推进时写入 session transcript：

- `src/crxzipple/modules/orchestration/application/engine.py`
- `src/crxzipple/modules/orchestration/application/engine_session_recorder.py`

写入内容包括：

- inbound user message
- assistant final response
- assistant function_call message
- tool result message

这些消息的 owner 仍然是 `session` module。

### Direct transcript 读取（已退场）

迁移前旧 `PromptSurfaceBuilder.build()` 读取：

```python
session_service.get_session_with_messages(
    ListSessionMessagesInput(
        session_key=session_key,
        active_session_only=True,
    )
)
```

随后只保留：

```python
message.session_id == run.active_session_id
and message.visibility is not SessionMessageVisibility.ARCHIVED
```

并调用：

```python
build_prompt_transcript(filtered_session_messages, max_chars=...)
```

normal turn 下 `max_chars=None`，因此 active session 未归档历史基本会全部进入 provider-native messages。

### Transcript 清洗规则

迁移前 `build_prompt_transcript()` 做了三件事：

- 过滤没有对应 tool result 的孤立 assistant function_call。
- 把已经被旧 assistant message 处理过的历史图片/文件替换成占位文本。
- 在 `MEMORY_FLUSH` 模式下按字符预算保留最近消息。

这些规则是有价值的，但它们目前发生在 tree 之外。

### Context Workspace session tree

`SessionContextNodeProvider` 当前暴露：

- `session.current`
- `session.segment.current`
- `session.messages.current`
- `session.segment.compacted.*`
- `session.segment.closed.*`
- `session.segment.messages.*`

当前 active segment 的消息由 `session.messages.current` 稳定承载，不再用 recent / older 分页；历史 segment 主要提供 summary / handle / estimate，展开后才披露 message ranges。

### Context render 注入

Context Workspace render 会生成：

```xml
<context_instructions>
  ...
</context_instructions>
<context_tree session="..." revision="...">
  ...
</context_tree>
```

orchestration 会把这段 `prompt_body` 作为 system message 插入 LLM messages，并把 tool schema / artifact attachment mirror 到 provider 特化输入。

## 目标状态

normal turn 的历史传递应变成：

```text
session 持有历史事实
        ↓
context_workspace session adapter 生成 session history nodes
        ↓
tree state 控制哪些历史节点进入 prompt body
        ↓
context render 生成唯一历史上下文正文
        ↓
provider adapter 只做必要 mirror
        ↓
LLM invocation
```

最终 LLM 输入应满足：

- 当前用户输入仍以 provider-native `user` message 进入，保证本轮任务清晰。
- 当前 run 内新产生的 assistant tool_call / tool result 继续以 provider-native messages 进入，保证工具循环能看到刚返回的结果。
- 历史对话不再作为整段 active transcript 直接 replay。
- 历史对话通过 `<context_tree>` 中的 session nodes 进入 prompt body。
- tool call / tool result 历史以结构化 session nodes 呈现。
- 图片/文件历史以 artifact handles 或 opened artifact attachments 进入，而不是靠 transcript placeholder。
- folded / archived / inactive session history 默认不进入完整正文，只作为可展开 handle。
- render snapshot 能复现 LLM 实际看到的历史。

## 非目标

- 不把 session 历史真相迁移到 Context Workspace。
- 不让 Context Workspace 直接修改 session owner 数据。
- 不恢复旧 PromptAssembler 或旧 orchestration facade。
- 不通过前端拼接历史来解决 prompt 重复问题。
- 不为旧 direct transcript 行为保留长期兼容开关。
- 不把所有历史默认塞进 prompt tree 完整内容；树需要支持渐进披露。
- 不在本计划内重写 memory engine、tool source 或 skill authoring。

## 设计原则

### Session 是事实源，Context Workspace 是交付层

Session module 负责保存消息、归档、实例 reset、compaction metadata。Context Workspace 只保存：

- 节点 handle
- 披露状态
- 摘要
- 估算
- owner ref
- render snapshot

完整 session message 由 session application service 按需查询。

### 当前输入和历史要分离

当前 inbound message 是本轮任务触发源，应保留 provider-native user message。历史消息则进入 context tree。

原因：

- provider-native user message 对大多数 LLM adapter 是最高兼容形态。
- 当前输入通常需要保持最短路径，避免被树结构淹没。
- 历史由树治理，才具备折叠、回看、估算、pin 和 UI 可观察性。

### 树折叠是业务语义，XML 折叠只是 UI 显示

业务层 collapsed 节点在 prompt body 中只出现 handle / summary / estimate，不出现完整 children content。

前端 XML viewer 的代码折叠只是展示效果，不改变 Context Workspace 的业务节点状态。

### Provider mirror 不改变 prompt 主体

图片、文件、tool schema 等 provider 特化输入可以从 tree nodes mirror 到 adapter 要求的位置，但 prompt 主体仍以 Context Workspace XML 为准。

### 不能用预算不足作为隐藏双轨的理由

如果历史太大，应通过 node estimate、folded range、compaction summary、agent 主动 expand 来治理，而不是保留 direct transcript 作为隐形 fallback。

## 目标 Prompt Shape

normal turn 目标输入：

```text
system:
  agent system prompt

system:
  runtime context

system:
  <context_tree>
    <node id="session.current" kind="session">
      ...
      <node id="session.segment.current" kind="session_segment" state="expanded">
        <node id="session.messages.current" kind="session_message_range" state="expanded">
          <node id="session.message...1" kind="session_message">
            <role>user</role>
            <content>...</content>
          </node>
          <node id="session.message...2" kind="session_message">
            <role>assistant</role>
            <content>...</content>
          </node>
        </node>
      </node>
      <node id="session.segment.compacted.<id>" state="collapsed">
        <summary>Compacted prior segment summary...</summary>
      </node>
    </node>
  </context_tree>

user:
  current inbound instruction

assistant/tool:
  current run 内刚产生的 tool_call / tool_result，仅在同一 run 的工具循环中出现
```

注意：

- historical user / assistant / tool message 不再作为 provider messages 铺平。
- 当前 inbound instruction 在 session 中也会保存，但 tree 中只保留 handle，provider message 保留当前 run 的工作窗口。
- 如果当前输入已经出现在 recent message node 中，render 需要避免重复全文，或标记为 `current_inbound` 并在 tree 中只显示 handle。

## Session Node 设计

### 根节点

```xml
<node id="session.current" kind="session" owner="session">
  <title>Current Session</title>
  <summary>Active session instance ...</summary>
</node>
```

### Current Messages

默认展开当前 active segment 的全部可见消息，不再按最近 N 条分页；当前 inbound 在 tree 中只保留 handle，不重复完整正文。

建议 owner ref：

```json
{
  "session_key": "...",
  "session_id": "...",
  "from_sequence_no": 1,
  "to_sequence_no": 19,
  "message_count": 19
}
```

建议 content 渲染：

```xml
<message role="assistant" sequence="18" kind="message">
  <content>...</content>
</message>
```

### Current Inbound

当前输入可以在 tree 中出现 handle，用于 UI 所见即所得，但不应重复完整正文：

```xml
<node id="session.message.current" kind="session_message" state="current">
  <title>Current User Message</title>
  <summary>Delivered as provider user message for this turn.</summary>
</node>
```

如果后续决定让当前输入也完全树化，需要单独升级 provider adapter，此处不作为本计划第一阶段目标。

### Tool Call Pair

assistant function_call 和 tool result 应成对渲染，避免孤立 call 误导模型：

```xml
<node kind="tool_interaction" id="session.tool_call.call_x">
  <tool_name>browser.snapshot</tool_name>
  <arguments>{...}</arguments>
  <result status="failed">...</result>
</node>
```

规则：

- 有 tool result 的 function_call 才作为完整交互出现。
- 没有 result 的 pending/background call 默认只给 handle 和状态。
- failed tool result 保留错误摘要和可展开详情。

### Attachment History

历史图片/文件不再由 transcript placeholder 表达，应转成 artifact node 或 attachment handle：

```xml
<node kind="artifact_ref" owner="artifacts" state="collapsed">
  <title>Image attachment</title>
  <summary>Previously processed image. Open if visual detail is needed.</summary>
</node>
```

展开后可以 mirror 到 provider attachment。

### Historical Segment Handles

inactive session、archived messages、compacted ranges 默认按 segment 只出现 summary：

```xml
<node id="session.segment.compacted.<id>" kind="session_segment" state="collapsed">
  <summary>Compacted prior segment summary...</summary>
</node>
```

agent 需要时通过 context tree tool 展开 segment ranges，但 render 必须估算预算，不能一次性把超大历史塞回 prompt。

## Application Surface 变更

### PromptInputCollector

需要把 normal turn 的 transcript build 改为当前输入专用。

目标职责：

- 读取 agent profile、session binding、LLM routing、skills catalog、surface policy。
- 生成当前 inbound provider message。
- 不再 normal turn 下 replay active transcript。
- `MEMORY_FLUSH` 可以暂时保留 dedicated transcript builder，但必须标清为非 normal delivery。

建议新增内部结构：

```python
@dataclass(frozen=True, slots=True)
class CurrentPromptInput:
    message: LlmMessage
    session_message_id: str | None
```

### PromptTranscript

旧 `build_prompt_transcript()` 已退出；当前只保留两个显式入口：

- `build_current_run_prompt_window()`：只服务当前 run 内 provider-native 工作窗口。
- `build_memory_flush_prompt_transcript()`：只服务 memory flush 维护面。

normal turn 不允许调用全量 active session transcript builder。清洗、工具调用配对和附件降级逻辑仍保留在 shared helper 内，但必须通过上述明确入口进入，避免再出现“看起来像历史 replay”的泛名。

### ContextWorkspacePromptSnapshotAdapter

需要确保 render 前 session tree 已经同步到当前 run：

- `ensure_workspace()`
- sync root nodes
- sync session history nodes
- render prompt body
- record snapshot

`session.messages.current` 默认展开，需要在 adapter 或 Context Workspace activation 中确保状态初始化稳定；它必须随 active segment 刷新为完整可见消息，不允许因工具结果插入而移动分页窗口。

### SessionContextNodeProvider

需要从 summary provider 升级成 prompt delivery provider：

- message node 需要支持完整文本 content。
- tool interaction 需要结构化 content。
- attachment block 需要转 artifact handle。
- current inbound 需要特殊标记，避免重复全文。
- older/folded range 需要按 chunk 渐进展开。

### ContextRenderService

需要支持不同 node kind 的 XML 渲染，而不是所有节点统一 `<title>/<summary>/<content>`。

建议引入 renderer registry：

```python
class ContextNodePromptRenderer(Protocol):
    def render(self, node: ContextNode, children: tuple[ContextNode, ...]) -> str:
        ...
```

首批专用 renderer：

- `session_message`
- `session_message_range`
- `tool_interaction`
- `artifact_ref`
- `tool_bundle`
- `tool_function`
- default node renderer

## 数据与状态变更

### ContextNode metadata

session message node 建议 metadata：

```json
{
  "role": "user",
  "kind": "message",
  "sequence_no": 18,
  "source_kind": "orchestration_run",
  "source_id": "...",
  "visibility": "visible",
  "content_digest": "..."
}
```

### ContextNode content

对于短文本 message，可以把可渲染内容缓存到 `ContextNode.content`，但 owner ref 必须仍能定位 session message。

对于大内容、文件、图片，不缓存完整内容，只缓存摘要和 artifact refs。

### Render snapshot

snapshot metadata 需要补：

```json
{
  "history_delivery": "context_tree",
  "direct_transcript_message_count": 1,
  "tree_session_message_count": 8,
  "folded_history_count": 64,
  "current_inbound_message_id": "..."
}
```

Operations / Trace 后续可以据此展示 prompt 来源。

## 迁移阶段

### CW-H1: 文档与基线测试

- [x] 新增本开发文档并挂入 docs index。
- [x] 迁移前 direct transcript 红线已退役；现用 normal turn 不含完整历史 transcript 的目标态回归测试锁定。
- [x] 增加 snapshot 测试，确认 context prompt body 中已有 session nodes。

### CW-H2: Session node prompt content

- [x] `SessionContextNodeProvider` 为 `session_message` 生成可用于 prompt 的结构化 content。
- [x] 支持 role、sequence、kind、source、created_at、visibility metadata。
- [x] 对 assistant function_call + tool result 合并为 `tool_interaction` 或父子节点。
- [x] 对 image/file/history attachment 转 artifact handle 或 placeholder handle。
- [x] 补单元测试覆盖 recent / older / folded / tool result / attachment。

### CW-H3: Context render 专用 renderer

- [x] 为 `session_message` 增加 XML renderer。
- [x] 为 `tool_interaction` 增加 XML renderer。
- [x] folded / older collapsed range 只渲染 summary handle；展开 range 后才渲染完整消息。
- [x] collapsed 节点不输出完整 content。
- [x] render snapshot 记录 session history delivery metadata。

### CW-H4: Normal turn 收口

- [x] `PromptInputCollector` normal turn 不再调用 direct active transcript replay。
- [x] 当前 inbound instruction 保留为 provider-native user message。
- [x] 当前 run 内 tool_call / tool_result 保留为 provider-native 工作窗口，避免 inline tool loop 失明。
- [x] 历史消息只从 Context Workspace prompt body 进入。
- [x] `MEMORY_FLUSH` 路径继续隔离为明确非 normal transcript 路径。
- [x] 删除 normal turn 依赖 `build_prompt_transcript()` 全历史 replay 的测试假设。
- [x] 增加防回归测试：历史 assistant/user/tool 不在 provider messages 中重复出现。

### CW-H4.1: 当前落地补充

- [x] `SessionContextNodeProvider` 对当前 inbound message 只输出 `Delivered as provider user message for this turn.` 摘要，避免 tree 与 provider user message 重复全文。
- [x] Context Workspace owner children refresh 改为读取最新节点，避免旧 `owner_ref` 把新子树删回旧状态。
- [x] Context Workspace owner refresh 只作用于声明了动态加载动作的节点，避免 upsert 的静态 recall 子树被 owner provider 空结果误删。
- [x] Context render snapshot estimate 增加 owner/kind breakdown；preflight compaction 使用 session-owner 历史压力，而不是被固定 tool tree 开销误导。
- [x] 维护 surface（memory_flush / compaction / heartbeat）不使用 context tree provider mirror 替换自己的声明式工具协议。
- [x] Memory recall 由 memory owner 工具完成；工具结果写入 session 后，下一轮通过 `tool_interaction` 或 memory owner 节点进入 Context Tree，不再通过 `context_tree.recall_memory` 代理。
- [x] 配对成功的 assistant function_call / tool result 在 session tree 中合并为 `tool_interaction`，避免历史里裸露孤立 call。
- [x] 持久化 render snapshot metadata 记录 `history_delivery`、direct transcript 数量、tree session message 数量、tree tool interaction 数量、folded history node 数量和 current inbound message id。
- [x] 持久化 render snapshot metadata 记录 opened artifact materialize 后的 `artifact_content_block_count`，便于 Trace/Operations 判断是否真正送入 provider 输入。
- [x] session adapter 回归测试锁定 failed tool interaction 在 XML 中保留 status、error 与 result 摘要。
- [x] session adapter 回归测试锁定附件历史只以 `[image:name]` / `[file:name]` 句柄进入 prompt，不重新嵌入 artifact id 或原始内容。
- [x] session adapter 回归测试锁定 older / folded 历史默认只露 handle，只有执行 expand 后才进入 XML prompt 正文。
- [x] context snapshot adapter 回归测试锁定 opened artifact 的 provider mirror：vision model 得到 image block，非 vision model / 超预算 artifact 得到清晰文本说明，text-like 文件得到可读文本块。

### CW-H5: 附件与 provider mirror 收口

- [x] 历史图片/文件不再依赖 `_prune_processed_history_attachments()` 的 placeholder 作为主要机制；normal history 走 session handle / artifact node / opened artifact mirror。
- [x] artifact node 展开后可 mirror 成 provider attachment。
- [x] 非 vision model 下 artifact mirror 输出清晰文本说明。
- [x] 大文件/大图只给 handle 和预算提示。
- [x] text-like 文件 artifact mirror 为文本块并按预算截断，而不是作为 opaque base64 文件强塞。

### CW-H6: UI 与诊断

- [x] Workbench Context 面板显示完整 prompt body 原生 XML，不再只截断前 1800 字。
- [x] Trace 面板显示 prompt body 原生 XML。
- [x] 标出 direct provider messages 与 tree prompt body 的来源。
- [x] Workbench Context 面板显示 history delivery mode。
- [x] Workbench Context 面板显示 direct transcript count/roles、tree session message count、tool interaction count、folded count、provider message/schema count 和 artifact content block count。
- [x] Trace 面板显示 history delivery mode、direct transcript count/roles、tree session message count、tool interaction count、folded count、provider message/schema count 和 artifact content block count。
- [x] 支持从 render snapshot 定位到 session message node。

### CW-H7: 清理旧双轨

- [x] 清理 normal turn direct transcript fallback。
- [x] 清理长期兼容开关和旧命名。
- [x] `build_prompt_transcript()` 已拆成 `build_current_run_prompt_window()` 与 `build_memory_flush_prompt_transcript()`，调用点不再使用旧泛名。
- [x] 更新 `docs/context-workspace-prompt-tree-development.md` 的当前状态。
- [x] 当前 README / AGENTS 约束无需追加；本轮状态落在本开发文档与 `docs/context-workspace-prompt-tree-development.md`。

## 验收标准

### Prompt 行为

- [x] normal turn provider messages 中只有 system/context/current run 工作窗口等必要消息，不再包含完整历史 transcript replay。
- [x] 历史对话可在 `<context_tree>` 中看到。
- [x] recent history 默认可读，older/folded 默认只显示 handle。
- [x] 展开 older/folded 后，下一轮 render 能包含展开内容。
- [x] 当前 inbound 不在 provider user message 和 tree history 中重复全文。
- [x] tool call/result 历史结构清晰，不出现孤立 function_call。

### Snapshot 与可观测

- [x] 每次 run 的 context render snapshot 能复现本轮 prompt body。
- [x] snapshot metadata 能说明历史来源和数量。
- [x] Trace 能看到 prompt 估算、历史来源、折叠数量和可定位 session message node refs。
- [x] Operations 能看到 prompt 估算、历史来源、折叠数量和可定位 session message node refs。

### 边界

- [x] session module 不依赖 context_workspace。
- [x] context_workspace 不持有 session 完整真相。
- [x] orchestration 不直接拼 session 历史正文。
- [x] frontend 不直接绕过 `/context-workspace` 或 trace snapshot 拼 prompt。

### 回归

- [x] tool result 后续轮次仍能被 LLM 理解。
- [x] approval / background tool / failed tool / yielded run 的历史仍可追溯。
- [x] memory flush 仍能读取必要 transcript。
- [x] archived message 默认不进入 normal prompt，除非用户或 agent 明确展开对应 folded range。
- [x] inactive session 只通过 folded history handle 出现。

## 2026-05-31 当前实现摘记

- normal turn 的 provider transcript 现在是 current-run window：当前 inbound 加本 run 内刚产生的 tool_call / tool_result；历史 replay 不再走 provider message。
- session tree recent / older / folded children 会把已配对工具调用合成为 `tool_interaction`；未配对 call 保留为 `session_message` handle。
- `tool_interaction` prompt XML 直接输出工具名、call id、状态、参数、错误和结果摘要。
- Context Workspace render 使用可见节点树，collapsed 节点只输出 handle，opened/pinned descendant 可穿透折叠父节点进入 prompt。
- 维护 surface 不接受 context tool mirror 改写，避免 memory_flush / compaction 协议被交互式 tree 工具覆盖。
- 架构护栏已覆盖：session 不反向依赖 context_workspace，context_workspace 不依赖 session truth，orchestration 不直接 import context_workspace module，旧 `build_prompt_transcript()` 不可复活。
- 前端护栏已覆盖：`prompt_body` 只允许出现在 Workbench/Trace 的 Context Workspace snapshot surface，避免页面绕过 Context Workspace 拼 prompt。
- session adapter 回归测试覆盖 yielded、background、approval 与 failed tool 历史，确保这些异步/人工介入链路在 Context Tree XML 中仍可追溯。
- `test_orchestration_tools.py` 已迁移到 Context Tree 渐进披露流程：测试中的 LLM 先展开 tool / skill 节点，再通过可见 schema 调用工具，或用 skills owner 的 `skill_read` 读取 SKILL.md。
- follow-up turn 回归已覆盖 prior tool history：上一轮 tool call / result 不再作为 provider-native assistant/tool messages 注入下一轮，只通过 Context Tree `tool_interaction` 进入 prompt body。

## 推荐验证命令

按实际改动范围选择：

```bash
PYTHONPATH=src pytest -q tests/unit/test_prompt_transcript.py
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_context.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_tools.py
PYTHONPATH=src pytest -q tests/unit/test_app_assembly_architecture.py
```

前端涉及 Context / Trace 显示时：

```bash
cd frontend
npm run typecheck
npm run build
```

## 风险与处理

### 历史重复

风险：当前 inbound 或 current active messages 同时在 provider messages 和 tree 中出现。

处理：

- 当前 inbound provider-native 传递。
- tree 中当前 inbound 默认只出现 handle。
- snapshot metadata 记录 `current_inbound_message_id`。

### 工具历史丢失

风险：去掉 direct transcript 后，模型看不到上一轮 tool result。

处理：

- `tool_interaction` renderer 必须在 recent history 中显示工具名、参数摘要、状态、结果摘要。
- 大结果提供 collapsed detail handle。
- 防回归测试覆盖“工具结果后一轮继续推理”。

### 上下文过大

风险：recent history 完整展开导致 prompt 膨胀。

处理：

- recent 默认 N 条，N 由 runtime default 或 Context Workspace policy 控制。
- older/folded 默认 collapsed。
- `estimate` 必须按节点和整棵树聚合。

### Memory flush 破坏

风险：memory flush 仍需要较完整 transcript。

处理：

- memory flush 暂时保留 dedicated transcript builder。
- normal turn 不使用该 builder。
- 后续可把 memory flush 也迁移到 tree range selection。

### Provider adapter 兼容

风险：有些 provider 对 system message 顺序或 attachment mirror 敏感。

处理：

- 保持 context workspace body 插入在 system prefix 后。
- tool schema / image / file mirror 保持 provider adapter 特化。
- 所有 provider 特化输入必须能从 snapshot 回溯到 node id。

## 完成判定

本升级完成后，可以用一句话描述系统：

> Session 保存历史事实，Context Workspace 决定历史如何进入 prompt；orchestration 只交付当前输入、树渲染和 provider mirror，不再直接 replay 历史 transcript。

达到该状态后，prompt engineering 的主控点才真正从 orchestration 迁移到 Context Workspace，后续 memory、skill、tool、artifact、session segment 都能按同一棵树治理。
