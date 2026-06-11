# Context Workspace Tree Schema Convergence Plan 2026-06-07

本文是 Context Workspace / Prompt Tree 下一轮结构收口开发文档。上一轮已经把
prompt engine 主链路推进到 Context Workspace render snapshot、invocation-level
Actual Request 和 provider attachment mirror。本轮不再继续补提示词小片段，而是把
树本身的结构收成稳定 schema。

## 背景

当前系统已经达成：

- Context Workspace 拥有真实 Context Tree。
- Orchestration 只通过 `PromptInputCollector` 收集运行输入，再通过
  `ContextWorkspacePromptSnapshotAdapter` 请求 render snapshot。
- Workbench / Trace 可以查看真实 Context Tree XML、provider-native messages、
  mirrored tool schemas、provider attachments 和 request metadata。
- Normal turn 的历史对话已经从 provider-native 长 transcript 收回树上。
- Tool functions 已按 source-first bundle/group 渐进披露，不再把 100 多个 function
  直接平铺给模型。

本轮施工前，树结构仍保留了过渡形态：

- `runtime.contract`、agent identity、agent home、`run.flow`、runtime context、
  `work.plan`、`session.current` 等都是 sibling root。
- `<context_instructions>` 目前是 render 时额外写入的一段说明文本，不是真实可操作
  Context Tree 节点。
- `run.flow` / runtime context / `work.plan` 没有明确收进执行现场。
- `session.current` 已经主要承载会话事实，但树的顶层结构还不能一眼区分
  “总章”、“本次执行”、“当前会话”和“可用能力”。

这会让 agent 和人都难以判断某个信息属于哪一层，也会让后续 owner adapter 继续在
顶层加 root，树会再次变散。本文件保留这些差距作为审查背景；下方 checklist 记录
当前已经收口和仍需继续验收的项。

## 目标

1. 建立 Context Tree schema v2，清晰区分：
   - `context.instructions`：总章和长期规则。
   - `execution.current`：本次 turn/run 的执行现场。
   - `session.current`：当前会话事实、历史和 tool interaction。
   - capabilities/resources roots：tools、skills、memory、artifacts、workspace。
2. 让 `<context_instructions>` 从 render-only 文本升级为真实树节点。
3. 保持 runtime contract、agent home、project/workspace guidance 的优先级可见。
4. 保持 session 节点纯净，不再向 session 下塞 runtime contract、agent home 或通用规则。
5. 保持 execution 和 session 拆开：
   - execution 是这一次 run/turn 的流程、计划、continuation 状态。
   - session 是会话事实和历史回顾。
6. 继续保证 provider-specific tools、images、files 只是从树节点派生的 attachments，
   不反向污染 Context Tree 模型。
7. 每次 render snapshot 明确记录 tree schema version，便于 Actual Request 和测试定位。

## 非目标

- 不修改 turn / run / execution chain 状态机。
- 不把 Context Tree 变成资源 owner 或特殊资源读取系统。
- 不把 skill / memory / artifact 文件内容默认灌入树。
- 不引入关键词路由、人工联想规则或每 turn 强制规划 LLM。
- 不保留新旧树结构双轨兼容。历史 snapshot 可以原样展示，但新 render 必须走 v2。
- 不让前端绕过 `/context-workspaces/*` 或 `/turns/{run_id}/prompt-preview` 拼 prompt 真相。

## 目标树形

推荐 render 外层使用 `<context_tree>`，内部所有内容都来自真实节点，不再插入
render-only instruction block。

```xml
<context_tree schema_version="2026-06-07.context_tree.v2">
  <context_instructions
    id="context.instructions"
    kind="context_instructions"
    state="expanded">
    <node id="runtime.contract" kind="runtime_contract" />
    <node id="agent.identity" kind="agent_identity" />
    <node id="agent.home" kind="agent_home">
      <node id="agent.home.AGENT.md" kind="agent_home_file" />
      <node id="agent.home.USER.md" kind="agent_home_file" />
      <node id="agent.home.SOUL.md" kind="agent_home_file" />
      <node id="agent.home.IDENTITY.md" kind="agent_home_file" />
    </node>
    <node id="context.priority" kind="priority_guide" />
    <node id="context.tree_usage" kind="tree_usage_guide" />
  </context_instructions>

  <execution_current
    id="execution.current"
    kind="execution_context"
    state="expanded">
    <node id="run.flow" kind="run_flow" />
    <node id="run.runtime" kind="runtime_context" />
    <node id="work.plan" kind="work_plan" />
    <node id="execution.continuation" kind="continuation_state" />
  </execution_current>

  <session_current
    id="session.current"
    kind="session"
    state="expanded">
    <node id="session.instance.current" kind="session_segment" />
    <node id="session.message.current_inbound" kind="session_message_ref" />
    <node id="session.history.folded" kind="folded_history" />
    <node id="session.tool_interactions" kind="tool_interaction_group" />
  </session_current>

  <tools_available id="tools.available" kind="tool_bundle_root">
    <node id="tools.bundle.configured.browser" kind="tool_bundle" />
  </tools_available>

  <skills_available id="skills.available" kind="skill_group" />
  <memory_visible id="memory.visible" kind="memory_scope_group" />
  <artifacts_session id="artifacts.session" kind="artifact_group" />
  <workspace_resources id="workspace.resources" kind="workspace_resource_group" />
</context_tree>
```

说明：

- `context.instructions` 是最高优先级说明层，但它本身仍是 Context Tree 节点。
- `runtime.contract` 内容仍来自
  `src/crxzipple/modules/context_workspace/application/prompts/runtime_contract.md`。
- agent home 多文件是 agent 身份和持久工作规则，不是 session 历史。
- `context.priority` 和 `context.tree_usage` 只表达优先级、树操作和展开原则，不承载
  当前任务事实。
- `execution.current` 可以跨一次 run 的多次 LLM invocation 更新，但不应保存跨 session
  durable knowledge。
- `session.current` 只关心当前 session 事实、历史、folded summary 和 tool interaction。
- `workspace.resources` 只有 session/profile 明确绑定 workspace 时出现。

## 当前差距

### G1. Synthetic `<context_instructions>`

已收口。`_render_context_tree(...)` 不再直接拼接 render-only
`<context_instructions>` 文本；总章改为真实 `context.instructions` 节点，
可以被 `context_tree.list/expand/collapse/pin/estimate` 观察或治理。

### G2. Root siblings 过散

已收口。`_default_root_node_seeds(...)` 现在先声明 section roots，并把
instructions/execution/session/capability/resource 分层展示。

### G3. Execution 与 Session 边界不够直观

已收口。`run.flow`、`run.runtime`、`work.plan` 和 `execution.continuation`
统一挂在 `execution.current` 下，`session.current` 保持会话事实和历史。

### G4. Instructions 与 Agent Home 混在 render 文案里

已收口。runtime contract、agent identity、agent home、priority guide 和 tree usage
guide 都是 `context.instructions` 的真实 children，不再依赖 render-only 文案。

### G5. Render metadata 缺少 schema version

已收口。`context_render_snapshots.metadata`、orchestration snapshot record 和 LLM
invocation request metadata 都写入/镜像 `tree_schema_version`；snapshot metadata
同时记录 root node refs。

## 设计约束

- Node ID 尽量保持稳定，不用重复节点做兼容。比如 `runtime.contract` 仍叫
  `runtime.contract`，只是 parent 变成 `context.instructions`。
- 新 render 必须只有 v2 结构。旧 snapshot 作为历史事实原样展示，不为旧结构生成新兼容树。
- Owner adapters 只能挂到声明好的 section root：
  - session owner -> `session.current`
  - tool owner -> `tools.available`
  - skill owner -> `skills.available`
  - memory owner -> `memory.visible`
  - artifact owner -> `artifacts.session`
  - workspace owner -> `workspace.resources`
- Context Tree 只披露 handle、summary、估算和可见内容。真正读文件、读 skill、读 memory、
  打开 artifact 仍走 owner module 工具或 application service。
- Provider mirror 只读取可见并 schema-enabled 的 tool function 节点。

## 开发清单

### P0. Schema Freeze

- [x] 新增 `CONTEXT_TREE_SCHEMA_VERSION = "2026-06-07.context_tree.v2"`。
- [x] 在 `ContextRenderSnapshot.metadata` 中写入：
  - `tree_schema_version`
  - `root_node_ids`
  - `context_instructions_node_id`
  - `execution_current_node_id`
  - `session_current_node_id`
- [x] 在 LLM invocation `request_metadata` 中镜像 `tree_schema_version`。
- [x] 更新当前约束文档中 Context Tree v1/v2 的术语，Context Workspace 节点层停止扩散旧 `session.bulk.*` 说法并切到 `session.segment.*`。

### P1. Root Section Nodes

- [x] 在 `ContextWorkspaceService` 默认 seed 中新增：
  - `context.instructions`
  - `execution.current`
- [x] 将以下节点 reparent 到 `context.instructions`：
  - `runtime.contract`
  - agent identity
  - agent home
  - priority guide
  - tree usage guide
- [x] 将以下节点 reparent 到 `execution.current`：
  - `run.flow`
  - runtime context
  - `work.plan`
  - continuation state
- [x] 保持 `session.current` 作为 top-level section，不接收 execution/runtime children。
- [x] 保持 tools/skills/memory/artifacts/workspace section roots 为 top-level capability/resource roots。

### P2. Instructions Node Content

- [x] 删除 `_render_context_tree(...)` 中 render-only `<context_instructions>` 文本拼接。
- [x] 新增真实 guide nodes：
  - `context.priority`
  - `context.tree_usage`
- [x] 将优先级说明放入 `context.priority`：
  1. runtime contract
  2. explicit user instruction
  3. agent home
  4. current user input / session transcript
  5. visible context nodes
  6. tool results / owner facts
- [x] 将树使用说明放入 `context.tree_usage`：
  - collapsed handle 不等于不存在。
  - 能力不足前先展开相关 bundle/group。
  - 深入资源走 owner tools。
  - provider tool schemas 来自 visible function mirror。

### P3. Execution Section

- [x] 明确 `execution.current` 的 child schema：
  - `run.flow`
  - `run.runtime`
  - `work.plan`
  - `execution.continuation`
- [x] `run.flow` 内容只描述当前 prompt mode 和恢复语义。
- [x] `run.runtime` 只放本轮运行时上下文，例如 run id、agent id、workspace dir、llm id。
- [x] `work.plan` 保持公开计划，不包含 hidden chain-of-thought。
- [x] `execution.continuation` 汇总 approval/background/recovery 状态，只披露可公开状态。

### P4. Session Section

- [x] `SessionContextNodeProvider` 只向 `session.current` 写入 children。
- [x] normal turn 的旧历史继续通过 folded/range nodes 披露，不回到 provider-native
  transcript 长数组。
- [x] 当前 inbound user message 继续 provider-native 传递，同时在 session tree 中保留
  node ref 便于 Actual Request 对齐。
- [x] tool call/result 历史保持 `tool_interaction` 成对节点。
- [x] folded history summary 插入位置保持在 current active segment 之后，不挤掉
  runtime contract 或最新用户意图。

### P5. Capability Roots

- [x] `ToolContextNodeProvider` 继续 source-first：
  - `tools.available`
  - `tool_bundle`
  - optional `tool_bundle_group`
  - `tool_function`
- [x] 未显式分组的 source 展开后直接披露 function children，不再造无意义分类。
- [x] CLI source 不 mirror 为 provider function，只作为 guidance 节点指向 command/exec 能力。
- [x] Skill 节点保持 handle-first，不默认注入完整 `SKILL.md`。
- [x] Memory 节点只展示可见 scope/layer/recall handles，跨 session durable facts 由 memory owner 治理。
- [x] Artifact 节点只在 pin/open 后 mirror provider attachments。

### P6. Workspace Refresh And Migration

- [x] `ensure_workspace(...)` 对已有 workspace 执行结构收口：
  - 更新 section root。
  - reparent 稳定 node ids。
  - 删除或停用不再使用的过渡 guide 节点。
- [x] 不创建旧 root 和新 root 双份节点。
- [x] 旧 render snapshot 不迁移、不重写，只作为历史 Actual Request 展示。
- [x] 新 render snapshot 必须写入 schema v2。

### P7. Frontend Actual Request

- [x] Workbench / Trace XML 视图以真实 snapshot 为准，不根据旧 UI 卡片重排语义。
- [x] XML 代码折叠只是视觉折叠，不改变 Context Tree 业务折叠状态。
- [x] 右键菜单继续承载业务操作：expand、collapse、pin、unpin、enable schema。
- [x] 诊断区域展示：
  - tree schema version
  - context render snapshot id
  - runtime contract hash
  - mirrored tool schema count
  - prompt mode / prompt surface
- [x] 对旧 snapshot 只显示原始 XML，不做新结构伪装。

### P8. Tests

- [x] `test_context_workspace_tree_service.py`
  - 默认 workspace 生成 v2 section roots。
  - `runtime.contract` parent 是 `context.instructions`。
  - `work.plan` parent 是 `execution.current`。
  - `session.current` 不包含 runtime/agent/execution children。
- [x] `test_context_workspace_session_adapter.py`
  - session nodes 只挂到 `session.current`。
  - folded history / tool interaction 仍可展开。
- [x] `test_context_workspace_tool_adapter.py`
  - tools 仍按 source-first bundle/group/function 披露。
  - schema mirror 只读取 visible function nodes。
- [x] `test_orchestration_context_workspace_snapshot.py`
  - recorded snapshot metadata 包含 `tree_schema_version`。
  - LLM invocation request metadata 包含同一 schema version。
- [x] `test_turns_http.py`
  - prompt preview / Actual Request 返回 schema version 和真实 snapshot id。
- [x] 前端：
  - `cd frontend && npm run typecheck`
- [x] 涉及布局时运行 `npm run build` 和相关 layout audit。

## 验收标准

- 新 run 的 Context Tree render 只有 v2 section structure。
- Actual Request 中能清楚看见：
  - 总章 `context.instructions`
  - 执行现场 `execution.current`
  - 当前会话 `session.current`
  - 可用能力 roots
- `session.current` 不再混入 runtime contract、agent home、run flow 或 work plan。
- `context.instructions` 是可观察的真实节点，不是 render-only 说明文本。
- Provider 实际调用仍保留：
  - 当前用户输入 provider-native message。
  - 当前 tool loop provider-native tool protocol。
  - Context Tree XML system message。
  - mirrored tool schemas。
  - artifact provider attachments。
- 历史 session 不回到 provider-native 长 transcript。
- 新 snapshot metadata 和 invocation metadata 都能定位 tree schema version。

## 推荐施工顺序

1. 先加 schema version 和测试期望，确认当前失败点。
2. 增加 section root seeds 和 reparent 逻辑。
3. 把 render-only `<context_instructions>` 改成真实 node render。
4. 收 execution/current session/provider metadata。
5. 调整 owner adapters 挂载点。
6. 补 Workbench / Trace 诊断展示。
7. 跑 focused pytest 和 frontend typecheck。

## 风险

- 当前工具和测试可能直接依赖旧 root node ids 的同级关系。处理方式是保持 node id，
  只改变 parent，不复制一份兼容节点。
- 旧 snapshot 与新 snapshot 的 XML 结构会不同。处理方式是 snapshot immutable，
  前端展示原始 XML，不把旧 snapshot 改造成新结构。
- 如果 render instruction 文案一次性移除过多，agent 可能暂时不理解树操作。处理方式是把
  priority/tree usage 写成真实 guide nodes，并继续由 runtime contract 总述。
- 如果 section root 过度聚合 tools/skills/memory，会损失首屏可读性。本轮只把
  instructions 和 execution 收口，capability roots 保持清晰顶层。

## 当前状态

截至 2026-06-07：

- Prompt engine 主链路已经可用。
- Invocation-level Actual Request 已可观察。
- Tree schema v2 已进入生产代码：真实 `context.instructions` / `execution.current`
  section roots、schema version metadata、LLM request metadata、Workbench / Trace
  diagnostics 都已落地。
- 已验证：
  - `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py::test_context_tree_update_plan_records_visible_working_plan tests/unit/test_orchestration_context_workspace_snapshot.py::test_context_workspace_adapter_records_tree_snapshot_for_run_prompt tests/unit/test_orchestration_context_workspace_snapshot.py::test_engine_carries_context_contract_metadata_for_llm_invocation tests/unit/test_turns_http.py::TurnsHttpTestCase::test_turns_endpoint_submits_async_turn_without_exposing_orchestration`
  - `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_agent_adapter.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_context_tree_tool.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_http.py tests/unit/test_orchestration_context_workspace_snapshot.py::test_context_workspace_adapter_records_tree_snapshot_for_run_prompt tests/unit/test_turns_http.py::TurnsHttpTestCase::test_turns_endpoint_submits_async_turn_without_exposing_orchestration tests/unit/test_operations_context_workspace_read_model.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py tests/unit/test_context_workspace_agent_adapter.py tests/unit/test_context_workspace_tool_adapter.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_session_segment_compaction.py tests/unit/test_orchestration_compaction_segment_rotation.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_orchestration_memory.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_http.py tests/unit/test_orchestration_context_workspace_snapshot.py::test_context_workspace_adapter_records_tree_snapshot_for_run_prompt tests/unit/test_turns_http.py::TurnsHttpTestCase::test_turns_endpoint_submits_async_turn_without_exposing_orchestration tests/unit/test_operations_context_workspace_read_model.py`
  - `cd frontend && npm run typecheck`
  - `cd frontend && npm run build`
  - `cd frontend && npm run audit:operations-layout -- --base-url http://127.0.0.1:4173`
- Context Workspace 公开节点层已从旧 `session.bulk.*` 收口到
  `session.segment.*` / `session_segment`：
  - Workbench 的 Session Map、i18n、render snapshot metadata 使用 segment 口径。
  - `SessionInstance.metadata["segment"]`、`compact_active_segment()` 和
    `session.segment.compacted` 已成为 Session owner compaction API/event。
- 本轮交互收尾已完成：
  - Workbench Context XML viewer 已通过 Playwright 回归：原生 XML 样式、视觉折叠箭头、右键业务操作菜单均可用。
  - 布局相关变更已补 `cd frontend && npm run build` 和
    `cd frontend && npm run audit:operations-layout -- --base-url http://127.0.0.1:4173`。
