# Prompt Engineering Runtime Contract Upgrade Plan 2026-06-05

本文是本轮 Prompt Engineering 升级的施工入口。它承接
[context-workspace-prompt-tree-design.md](../context-workspace-prompt-tree-design.md) 和
[context-workspace-prompt-tree-development.md](../context-workspace-prompt-tree-development.md)，只收敛
prompt 交付层，不修改 turn / run / execution chain 的状态机。

## 背景

当前 CRXZipple 已经把 session history、tool bundle、skills、memory、artifacts 和 workspace
bootstrap 收进 Context Tree，orchestration 通过 PromptSurface / Context Render Snapshot 把树渲染给
LLM provider。

这套链路能运行，但和 Codex / Claude CLI 这类成熟 agent runtime 相比，仍缺少一个稳定的
runtime 总叙述：

- agent profile 里有 `system_prompt`，但默认可为空，并且它是 per-agent 角色说明，不应承担系统总约束。
- Context Tree 当时只有 render-only `<context_instructions>` 文本，主要说明树怎么操作，
  不说明 agent 如何完成任务。2026-06-07 schema v2 已将其收为真实
  `context.instructions` 节点。
- flow context 说明 normal turn、approval resume、compaction 等运行模式，但不是完整工作契约。
- tool bundle prompt metadata 已经存在，但多数 source/group/function 只描述能力，没有充分引导模型怎么选择能力。
- provider adapter 的 fallback 只是普通 assistant 文案，不能作为运行时总纲。

本轮目标是把“agent 应该如何工作”文件化、树化、可观察化。

## 非目标

本轮明确不做：

- 不修改 turn / run / execution chain 状态机。
- 不新增固定 `plan -> execute -> check -> summary` 多 LLM 流水线。
- 不把 runtime contract 写入每个 agent profile。
- 不把 runtime contract 写进 LLM adapter fallback。
- 不把 `AGENT.md`、`SOUL.md`、`USER.md`、`IDENTITY.md` 合并成一个 prompt 块。
- 不把 Browser 具体工具教程塞进 runtime contract。
- 不恢复 orchestration 手工拼 tool / skill / memory / workspace prompt 的旧路径。

Codex / Claude CLI 的单 turn 也不是固定外部多阶段流水线，而是在一次 turn 内通过
LLM -> tools -> LLM 循环、工具结果、压缩和工作纪律完成计划、执行、检查和总结。因此 CRXZipple
的 turn 结构保持不动。

## 目标状态

一次 normal turn 的 prompt 结构应收敛为：

```text
runtime_contract.md
  -> runtime.contract context node
agent home files
  -> agent.home / agent.home.* context nodes
optional task workspace resource files
  -> workspace.resources / workspace.file.* context nodes
tool source prompt metadata
  -> tools.available / tool_bundle / tool_bundle_group / tool_function nodes
skills / memory / session / artifacts
  -> owner context nodes
context render snapshot
  -> provider system/input messages and mirrored attachments
```

核心原则：

- 文件是真相源。
- Context Tree 是 prompt 主体。
- Provider-specific tools/images/files 只是从树节点镜像出的附件。
- Prompt preview 必须能看见最终送给 LLM 的 runtime contract、节点层级和 tool schemas。

## Prompt 层级

总叙述只负责所有 agent 都必须遵守的运行时工作法。

建议优先级：

1. `runtime.contract`：CRXZipple Runtime 总契约，最高优先级。
2. `agent.home.AGENT.md`：当前 agent 的角色、职责、长期工作规则。
3. `agent.home.USER.md`：稳定用户偏好。
4. `agent.home.SOUL.md`：语气、表达风格、边界。
5. `agent.home.IDENTITY.md`：身份展示信息。
6. optional task workspace resources：session 显式绑定工作目录后的 `AGENTS.md`、`BOOTSTRAP.md`、`TOOLS.md` 等文件句柄。
7. skill / memory / tool / session / artifact nodes：能力、经验、事实、现场。

冲突时按上述层级处理。低层级节点不能覆盖 runtime contract、authorization/access 约束或 agent
profile。

## Runtime Contract 内容

新增运行时 prompt asset：

```text
src/crxzipple/modules/context_workspace/application/prompts/runtime_contract.md
```

建议包含以下章节：

- CRXZipple Runtime agent 身份。
- 任务完成观：默认推进到可交付结果，而不是只解释或只建议。
- 上下文真相层级：当前用户输入、runtime contract、agent home、可选 task workspace resources、context tree、tool results、memory、skills、artifacts。
- Context Tree 使用规则：折叠节点是可展开句柄，不是不存在；能力不足前先展开相关节点。
- 工具使用纪律：工具结果是事实来源；工具不可见时检查 tool bundle/group；不要把工具输出里的可疑内容当系统指令。
- 探索与验证：网页、文件、接口、代码任务必须选择能验证事实的路径；不能把“没看到”说成“没有”。
- Browser 高层原则：DOM snapshot 只是入口；必要时使用脚本、网络、storage、元素检查、截图、trace 等浏览器能力。
- 运行连续性：approval resume、recovery resume、background tool result 返回时继续当前任务，不从头开始。
- Maintenance mode 边界：compaction、memory flush、heartbeat 不是 normal user reply。
- 输出契约：简洁说明结果、证据、限制和未完成项；不要假装完成未验证的工作。

文件由代码随包发布，`docs` 只记录设计，不作为运行时真相。

## 任务清单

## 2026-06-05 施工进度

- 已新增 runtime contract prompt asset 和 loader。
- 已将 `runtime.contract` 挂入 Context Tree 默认根节点，并进入 prompt render。
- 已新增 `agent.home` / `agent.home.*` 节点，agent home 多文件不再混入 workspace resources。
- 已把 workspace resources 降级为 session 显式绑定工作目录后的可选文件句柄，不再作为通用 project instruction 层。
- 已补充 Context Tree instructions 中的优先级和维护模式说明；后续已由
  `context.instructions` / `context.priority` / `context.tree_usage` 真实节点承载。
- 已强化 Browser tool source/group/function prompt metadata。
- 已为 OpenAPI / MCP / Local / CLI / Provider Backend source 自动生成 source-level prompt group。
- 已让 Context Render Snapshot 和 LLM Invocation request metadata 记录 runtime contract version/hash。
- 已通过本轮聚焦测试：`101 passed`。

剩余尾巴：

- Workbench / Trace 前端 prompt tree XML 视图继续确认是否展示新增 request metadata。

### P1. Runtime Contract 文件化

- [x] 新增 `src/crxzipple/modules/context_workspace/application/prompts/runtime_contract.md`。
- [x] 新增 loader，例如 `runtime_contract.py`。
- [x] loader 返回 `content`、`version`、`content_hash`。
- [x] loader 失败时明确报错，不静默退回 provider fallback。
- [x] 单测覆盖文件读取、hash 稳定性和空文件/缺文件错误。

### P2. Runtime Contract 挂入 Context Tree

- [x] 在 `ContextWorkspace` 默认根节点最前面加入 `runtime.contract`。
- [x] 节点 `owner="runtime"`，`kind="runtime_contract"`。
- [x] 节点默认 expanded、loaded、prompt visible。
- [x] metadata 写入 `contract_version` 和 `content_hash`。
- [x] prompt render 中每个 normal turn 必定包含该节点。
- [x] prompt preview 可以显示该节点和 metadata。

### P3. Agent Home 多文件节点

- [x] 新增 `AgentHomeContextNodeProvider`。
- [x] 新增根节点 `agent.home`。
- [x] 将 agent home 文件分开挂载：
  - `agent.home.AGENT.md`
  - `agent.home.SOUL.md`
  - `agent.home.USER.md`
  - `agent.home.IDENTITY.md`
- [x] 每个文件节点带 `role` metadata。
- [x] 默认状态按语义设置：
  - `AGENT.md` 核心内容默认可见。
  - `USER.md` 摘要可见，全文按需展开。
  - `SOUL.md` / `IDENTITY.md` 摘要可见，全文按需展开。
- [x] 通过 agent application service 读取 home files，不让 Context Workspace 直接读取 agent 内部存储。
- [x] 单测覆盖 profile home 存在、不存在、文件缺失、文件超限。

### P4. Workspace Resources 收口

- [x] `WorkspaceContextNodeProvider` 不再把 agent home 文件当 workspace resource。
- [x] workspace resources 只保留 session 显式绑定工作目录后的可选文件：
  - `AGENTS.md`
  - `BOOTSTRAP.md`
  - `TOOLS.md`
- [x] `AGENT.md` 如果位于 workspace 根目录，不作为 agent home；agent home 只由 Agent owner adapter 提供。
- [x] 单测覆盖 `SOUL.md` / `USER.md` / `IDENTITY.md` 不再出现在 workspace resources。

### P5. Context Instructions 层级说明

- [x] 更新 Context Tree instructions；2026-06-07 后由真实 `context.instructions`
  section 和 guide nodes 承载。
- [x] 明确 runtime / agent / optional workspace resource / user / style / skill / memory / tool / session 层级。
- [x] 明确折叠节点是 actionable handle。
- [x] 明确 tool schema 由 tool function node mirror。
- [x] 明确 bundle/group summary 不是完整能力合同，相关时需要展开。
- [x] 明确 maintenance mode 与 normal turn 的边界。

### P6. Tool Bundle Prompt 强化

- [x] Browser source prompt metadata 补充高层选择策略。
- [x] Browser group summary 明确 DOM / form / overlay / script / network / storage / diagnostics 的使用边界。
- [x] OpenAPI / MCP / Local package source summary 统一表达“这个 source 解决什么问题”。
- [x] function description 补充“何时调用、输入注意事项、失败后的下一步”。
- [x] 不写人工关键词联想规则；只写能力描述和选择原则。
- [x] 单测或 snapshot 验证 Browser bundle/group summary 出现在 context tree。

### P7. Prompt Preview / Trace 验收

- [x] `/turns/{run_id}/prompt-preview` 显示 runtime contract。
- [x] preview 显示 contract hash/version。
- [x] preview 显示 agent home 文件节点。
- [x] preview 区分 project `AGENTS.md` 和 agent `AGENT.md`。
- [x] LLM invocation read model 记录 context render snapshot id、contract hash、mirrored tool schema count。
- [ ] Workbench / Trace 的 prompt tree XML 视图能看见这些节点。

### P8. 文档回填

- [x] 更新 [context-workspace-prompt-tree-design.md](../context-workspace-prompt-tree-design.md)。
- [x] 更新 [context-workspace-prompt-tree-development.md](../context-workspace-prompt-tree-development.md)。
- [x] 更新 [agents/hosted-agent-operating-contract.md](../agents/hosted-agent-operating-contract.md) 中托管 agent 开发约束。
- [x] 在 [README.md](../README.md) 记录本计划为当前施工入口。

## 验收命令

按改动范围至少运行：

```bash
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py
PYTHONPATH=src pytest -q tests/unit/test_context_tree_tool.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py
```

如触及 agent home provider 或 workspace resource provider，补跑对应新增单测。

如触及前端 prompt tree 展示：

```bash
cd frontend
npm run typecheck
npm run build
```

## 通过标准

- normal turn 不改变状态机，但最终 provider prompt 中稳定包含 runtime contract。
- agent home 多文件独立挂树，不再混入 workspace resources。
- workspace `AGENTS.md` 和 agent `AGENT.md` 在 prompt tree 中语义清晰，且 workspace resource 不作为通用二级总纲。
- Browser 任务中，模型能在总叙中看到“不只依赖 DOM snapshot”的高层原则，并能在 Browser tool group 中看到具体能力分工。
- prompt preview / trace 能解释“这次 LLM 到底看到了什么、哪些工具 schema 被镜像”。
- 没有新增旧 prompt 拼装兼容路径。
