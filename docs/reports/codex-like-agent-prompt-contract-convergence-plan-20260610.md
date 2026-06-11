# Codex-like Agent Prompt Contract Convergence Plan 2026-06-10

本文记录 2026-06-10 关于 “Codex-like” 能力吸收的最新决策，并作为后续 prompt engineering / runtime context / Context Tree 工具面收口施工入口。

目标不是把 CRXZipple 改成 Codex 的直接工具面，而是在保持 CRXZipple 当前 Context Tree / Tool Source Contract / render snapshot 设计的前提下，吸收 Codex 已验证的工程 agent 行为先验和运行环境表达。

关联文档：

- [prompt-engineering-codex-path-absorption-plan-20260609.md](prompt-engineering-codex-path-absorption-plan-20260609.md)
- [prompt-engine-layered-refactor-plan-20260608.md](prompt-engine-layered-refactor-plan-20260608.md)
- [prompt-tree-budget-redundancy-remediation-plan-20260608.md](prompt-tree-budget-redundancy-remediation-plan-20260608.md)
- [browser-tool-source-contract-convergence-plan-20260610.md](browser-tool-source-contract-convergence-plan-20260610.md)
- [../context-workspace-prompt-tree-design.md](../context-workspace-prompt-tree-design.md)
- [../context-workspace-prompt-tree-development.md](../context-workspace-prompt-tree-development.md)
- [../orchestration-design.md](../orchestration-design.md)
- [../../src/crxzipple/modules/tool/README.md](../../src/crxzipple/modules/tool/README.md)

## 背景

近期用 CRXZipple 执行“访问昆航/东航官网查询航班”任务时，模型路线和 Codex 差异明显：

- CRXZipple 模型更容易先使用 `web_search`、`fetch_text` 等公共网页工具。
- 即使屏蔽 search，模型也会转向 fetch，而不是主动进入本地 runtime / browser runtime / exec 路径。
- `exec` / `process` 已经具备 Tool Source 能力，但一度没有正确通过 Context Workspace mirror 进入 provider tool schema 面。
- browser 之前存在绕过 Tool Source Contract 的特殊路径嫌疑，已经明确要扶正为普通 tool source。

对照 Codex 后，结论是：

- 不应恢复关键词联想 route。
- 不应为了压制 search 去屏蔽合法的外部信息工具。
- 不应新增一条 “resident direct inject” 工具旁路。
- 需要让模型默认理解自己处在本地工程 runtime 中，并通过 Context Tree 使用可见能力。

因此本轮收口原则是：

```text
Codex 的工程行为和环境感知要吸收；
Codex 的直接工具面不要照搬。

CRXZipple 继续保持：
Tool Source -> Context Workspace mirror -> Context Tree -> Provider tool schemas
```

## 最新决策

### 对齐 Codex 的部分

1. 工程 agent 行为契约。
   - 先读代码、文件、runtime 状态，再做判断。
   - 搜索文件优先 `rg` / `rg --files`。
   - 用户要求改动时默认实施，不停在方案。
   - 做完要验证。
   - 不覆盖用户已有改动。
   - 长任务持续推进，遇到阻塞说明具体阻塞。
   - 回答时报告做了什么、检查了什么、哪些没验证。

2. Runtime context 信息密度。
   - 明确 cwd / workspace。
   - 明确 agent home。
   - 明确当前时间、时区。
   - 明确网络可用性。
   - 明确 sandbox / approval / permission 语义。
   - 明确 shell / exec / process / browser runtime 等本地能力是否可见。
   - 明确 daemon / dev stack 的运行入口和约束。

3. Web search 使用语义。
   - `web_search` 是外部信息能力，不是 workspace / local runtime 任务的默认探索入口。
   - 官网交互、前端调试、本地服务验证优先 browser runtime / exec / process。
   - 外部实时信息、公共事实、来源归因、未知公共 URL 才优先 search/fetch。

4. 工程核心能力默认可见。
   - `context_tree.*` 是基础上下文操作面。
   - `exec` / `process` 是工程 agent 的核心 runtime 能力，应由 Tool Source 默认策略进入 Context Workspace mirror。
   - workspace / artifact / memory / skill 能力按 owner module 和 Context Tree 状态披露。

### 保持 CRXZipple 设计的部分

1. Context Tree 是唯一 agent-visible prompt/workbench 面。
   - 不把工具、文件、memory、artifact 重新散塞成多套 prompt 文本。
   - 不因为 Codex-like 就把所有工具直接放进 system prompt。

2. Tool Source Contract 不绕过。
   - `exec`、`process`、`browser.*`、`web.fetch_*`、`brave_search.web_search` 都必须来自 tool module/source。
   - provider tool schemas 由 Context Workspace provider mirror 派生。
   - 不新增 orchestration 内部 direct tool injection。

3. Orchestration 不做关键词 route。
   - 不写 “航班/价格/官网 -> browser/search”。
   - 不写 “代码/项目 -> exec”。
   - 不按用户文本做业务联想。
   - route 只能来自 prompt mode、run policy、tool source visibility、Context Tree state、agent 显式动作。

4. Render snapshot 和 Operations 可观察性保留。
   - 每次 provider request 的 Context Tree render snapshot 必须可追踪。
   - mirrored tool schema count、default schema policy、预算、折叠状态必须进入 report/metadata。

## 当前已落地状态

### 1. Browser Tool Source 扶正

目标：

- browser 不再作为绕过 tool source 的特殊 runtime。
- browser capability 由 `configured.browser` / `browser.*` 通过 tool module/source 暴露。
- browser profile 是 runtime context，不是 tool source 维度。

相关文档：

- [browser-tool-source-contract-convergence-plan-20260610.md](browser-tool-source-contract-convergence-plan-20260610.md)

### 2. 内容联想 route 已移除

目标：

- 不再根据用户文本猜测 “该打开 search / browser / exec”。
- 保留 prompt mode。
- 工具可见性由 tool source policy + Context Workspace mirror + tree state 决定。

核心文件：

- `src/crxzipple/modules/orchestration/application/turn_submission.py`
- `tests/unit/test_turn_submission_prompt_bootstrap.py`

### 3. `exec` / `process` 默认 schema 展开修复

问题：

- 默认策略里配置了 `exec` / `process`。
- 但 `_default_schema_source_ids()` 只按 namespace 推导 source，导致无 namespace 的 direct command tool id 没有扩展到 `bundled.local_package.command`。
- provider tool schemas 只看到 `web.fetch_json`、`web.fetch_text`、`brave_search.web_search`，看不到 `exec` / `process`。

修复：

- `exec` / `process` 显式映射到 `bundled.local_package.command`。
- command bundle 默认展开后 provider schemas 可包含 `exec` / `process`。

核心文件：

- `src/crxzipple/app/integration/context_workspace_orchestration/tool_schema_bootstrap.py`
- `tests/unit/test_context_workspace_tool_adapter.py`

### 4. Brave Search 恢复

决策：

- Brave Search 不应因为模型偏好问题被屏蔽。
- search 使用偏差应由 prompt contract / runtime context / tree visibility 纠正，而不是删除合法外部信息工具。

当前启用集合应包含：

- `brave_search.web_search`
- `exec`
- `process`
- `web.fetch_json`
- `web.fetch_text`

### 5. 最小 Local Runtime Contract 先进入 `agent_instruction`

第一轮曾在 `build_agent_instruction_block()` 中追加固定契约：

- workspace/runtime 是项目、代码、本地应用、browser runtime、执行类任务的主操作面。
- workspace-bound 工作先看本地文件和 runtime 状态。
- `exec` / `process` 通过 Context Tree 可见或可启用时优先用于探索和验证。
- search/fetch 用于外部实时信息、来源归因、公共 URL。
- 重要结论要基于工具观察结果说明检查过什么。

核心文件：

- `src/crxzipple/modules/orchestration/application/prompting/producers.py`
- `tests/unit/test_prompting.py`

2026-06-10 继续施工后，该临时追加已撤回；工程契约迁入 Context Workspace 的
`runtime.contract` 静态节点，`agent_instruction` 重新只承载 agent profile system prompt。

### 6. 2026-06-10 第一轮施工进展

已完成：

- `agent_instruction` 中的最小 Local Runtime Contract 已升级为 `Engineering Runtime Contract`。
- 契约吸收 Codex 工程行为：
  - workspace/runtime 优先。
  - 文件发现优先 `rg` / `rg --files`。
  - 用户要求实现时直接施工并验证。
  - 不回滚或覆盖用户已有改动。
  - Context Tree 折叠节点是可操作 handle。
  - `exec` / `process` 通过 Context Tree schema enablement 使用。
  - search/fetch 只作为外部信息、来源归因或公共 URL 能力。
  - website/local app investigation 优先 browser/runtime observation。
- `runtime_context` 已补充：
  - timezone。
  - shell。
  - resolved tool set 中的 `exec` / `process` 可见事实。
  - network access 标记为 unknown until verified，避免编造权限事实。
  - long-running local services 走 daemon-managed services 的运行约束。
- `RunPromptInputCollector` 会把 resolved tool ids 传入 runtime context。

保持未改变：

- 没有新增 prompt block kind。
- 没有新增 provider direct tool injection。
- 没有恢复关键词 route。
- Context Tree / provider mirror 仍是 tool schema 进入 LLM 的唯一主路径。

验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_prompting.py tests/unit/test_prompt_input_collector.py tests/unit/test_turn_submission_prompt_bootstrap.py tests/unit/test_context_workspace_tool_adapter.py::test_default_direct_command_tool_schema_ids_expand_command_bundle
PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_context.py::OrchestrationContextTestCase::test_process_next_orchestration_assignment_uses_session_bound_workspace_context
```

### 7. 2026-06-10 第二轮施工进展

已完成：

- 工程契约从 `agent_instruction` 临时拼接迁移到 Context Workspace 的 `runtime.contract` 节点。
- `runtime_contract.md` 升级为 `2026-06-10`。
- `runtime.contract` 内容补充：
  - 本地文件发现优先 `rg` / `rg --files`。
  - `exec` / `process` 作为本地 discovery、verification、process inspection、repository work 的 command/runtime 工具。
  - search/fetch 只用于外部实时信息、来源归因、公共 URL，不替代 workspace/local app/browser runtime investigation。
  - website/local app investigation 优先 browser/runtime observation。
- `agent_instruction` 重新只保存 agent profile system prompt，避免固定工程契约在 orchestration 与 Context Tree 中重复出现。

保持未改变：

- 没有新增 prompt block kind。
- 没有新增 direct tool injection。
- 没有恢复关键词 route。
- `runtime.contract` 仍通过 Context Tree render snapshot 进入 LLM。

验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_prompting.py tests/unit/test_context_workspace_root_nodes.py tests/unit/test_context_workspace_tree_service.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_context_render_xml_renderer.py
```

### 8. 2026-06-10 第三轮施工进展

已完成：

- `exec` / `process` 默认可见策略下沉到 `tools/command/tool.yaml`。
  - `prompt.default_tool_schema_group_refs` 指向 `run_and_verify` 和 `background_processes`。
  - `run_and_verify` 默认 schema 为 `exec`。
  - `background_processes` 默认 schema 为 `process`。
- `web.fetch_json` / `web.fetch_text` 默认可见策略下沉到 `tools/web/tool.yaml`。
  - `prompt.default_tool_schema_group_refs` 指向 `public_fetch`。
  - `public_fetch` 默认 schema 为 `web.fetch_json` 和 `web.fetch_text`。
- `turn_submission.py` 不再默认注入 `resident_tool_schema_ids` 或 `default_tool_schema_ids`。
- 显式 `prompt_bootstrap_policy` / `runtime_task_policy.prompt_bootstrap` 仍保留，作为 prompt mode / runtime task 的显式策略入口。
- Context Workspace adapter 在 `prompt.flow_hint` 为空时，仍可通过 source prompt policy 自动解析默认 schema group refs。

保持未改变：

- 没有新增新的 default/resident 概念。
- 没有恢复关键词 route。
- 没有绕过 Tool Source Contract。
- Brave Search 保持可用，但不作为 source policy default schema。

验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_turn_submission_prompt_bootstrap.py tests/unit/test_context_workspace_tool_adapter.py::test_command_and_web_default_schemas_come_from_tool_source_prompt_policy tests/unit/test_context_workspace_tool_adapter.py::test_default_direct_command_tool_schema_ids_expand_command_bundle
```

### 9. 2026-06-10 第四轮施工进展

已完成：

- 删除 `turn_submission.py` 中已经空掉的 `RESIDENT_DEFAULT_TOOL_SCHEMA_IDS` 常量。
- 测试命名和断言去掉 resident default 语义，只保留“turn content 不做 route / 不注入默认工具面”的约束。
- provider mirror budget 增加 `default_group_matches` / `default_group_match_count`。
- snapshot metadata 增加：
  - `tool_schema_mirror_default_group_matches`
  - `tool_schema_mirror_default_group_match_count`
- LLM request metadata 透传上述字段。

意义：

- Trace / Operations 可以从现有 metadata 解释默认 schema 来自哪些 source prompt group。
- 没有引入新的 visibility mode。
- 没有新增 route 概念。
- 默认能力仍由 tool source prompt policy + Context Workspace mirror 决定。

验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_turn_submission_prompt_bootstrap.py tests/unit/test_context_workspace_tool_adapter.py::test_command_and_web_default_schemas_come_from_tool_source_prompt_policy tests/unit/test_orchestration_context_workspace_snapshot.py::test_context_workspace_adapter_bootstraps_browser_starter_schemas_from_source_policy tests/unit/test_orchestration_context_workspace_snapshot.py::test_engine_carries_context_contract_metadata_for_llm_invocation
```

### 10. 2026-06-11 Loop Governance 收口

关联开发文档：

- [codex-like-agent-loop-governance-development-plan-20260611.md](codex-like-agent-loop-governance-development-plan-20260611.md)

已完成：

- `runtime.contract` 保持能力中立，只保留通用工程行为、证据纪律和收敛纪律。
  - 不出现 Browser/CDP/Playwright/source-specific 操作策略。
  - 不出现 `script.extract_request` 等不可见能力名。
  - 不写任务专用 route。
- command/web 能力细节下沉到对应 Tool Source prompt group。
  - `tools/command/tool.yaml` 说明高信息密度命令、narrow verification、输出预算和长输出治理。
  - `tools/web/tool.yaml` 说明 public URL evidence、JSON/text fetch 边界、source URL 和 extracted field 报告规则。
- `exec` schema 增加：
  - `max_output_tokens`：控制 provider-facing stdout/stderr 输出预算。
  - `yield_time_ms`：同步命令的等待控制杆；命令仍运行时返回 background process handle。
- `exec` result 增加结构化状态和成本信息：
  - `exit_code`
  - `timed_out`
  - `wall_time_seconds`
  - output budget / estimated tokens / truncation flags
  - raw output artifact read handle
- tool result history hygiene 收口：
  - 长工具结果通过 envelope/read handle 呈现。
  - 历史 tool result 默认只给 bounded summary / digest / refs。
  - orphan tool result message 不再绕过工具结果治理。
  - 历史工具节点不再 prior-run 自动 opened。
- repeated probe 进入 observation：
  - run metadata 聚合 normalized target/count/first_seen/last_seen。
  - Operations Orchestration 页面展示 repeated probes。
  - Trace summary 展示 repeated probe 摘要。
- Phase 7 回归基线采集工具化：
  - `python -m crxzipple.main orchestration baseline <run_id> --task-label "..."`
  - 输出 orchestration steps、UI steps、LLM calls、tool calls、repeated target count、candidate discovery/validation step、terminal status、final facts/gaps 信号。
  - 无法可靠判断的指标进入 `metrics_missing`，不伪造真实任务结论。

保持未改变：

- 不恢复关键词 route。
- 不新增 resident/direct tool injection。
- Context Tree 仍是 agent-visible prompt/workbench 面。
- provider tool schemas 仍由 Tool Source prompt policy + Context Workspace provider mirror 派生。
- browser source 恢复后的 DOM/Playwright/network 指导只允许放在 browser source-local prompt 中。

验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_tool_workspace.py tests/unit/test_tool_catalog.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_context_workspace_root_nodes.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py tests/unit/test_context_render_xml_renderer.py tests/unit/test_prompt_transcript.py tests/unit/test_prompt_input_collector.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_tool_resource_policy.py tests/unit/test_tool_execution.py
```

## 目标形态

### Prompt Surface 总体结构

目标 provider request 仍然保持一条主路径：

```text
Agent Profile / Runtime Facts / Session / Tool Source / Owner Facts
        ↓
RunPromptInputCollector
        ↓
ContextWorkspacePromptSnapshotAdapter
        ↓
Context Workspace Render Pipeline
        ↓
Context Tree XML-like prompt body
        ↓
Provider Request Builder
        ↓
LLM Provider
```

其中：

- `agent_instruction` 承载稳定行为契约。
- `runtime_context` 承载本轮运行事实。
- Context Tree 承载实际 agent-visible 工作台。
- provider tool schemas 来自 Context Tree provider mirror。
- direct transcript 只服务 provider protocol 和当前用户消息，不作为历史治理主线。

### Context Tree 可见面

模型应优先看到：

```text
context.instructions
  runtime.contract
  engineering.agent_contract
  context.tree_usage

run.current
  environment
  permissions
  provider
  context_budget
  runtime_capabilities

session.current
  current user input marker
  active segment summary
  recent tool interaction handles

workspace.resources
  bound workspace handles
  AGENTS / BOOTSTRAP / TOOLS handles when available

tool.sources
  source-level groups
  function nodes
  schema_enabled state
```

说明：

- `engineering.agent_contract` 可以是节点，也可以先保留在 `agent_instruction`；最终建议归入 Context Workspace root node，让人类 UI 也能看到。
- `runtime_capabilities` 不应成为新的 tool route；它只是运行现场描述。
- tool function node 的 `schema_enabled=true` 仍是 provider schema mirror 的事实来源。

## 开发任务

### Phase 1：补厚 Agent Instruction Contract

目标：

- 从当前 5 条 Local Runtime Contract 扩展为完整工程 agent contract。
- 吸收 Codex 的工程行为，但保留 CRXZipple 术语。

建议内容：

- 身份：本地 Agent Runtime 中的工程执行 agent。
- 工作方式：
  - 先观察本地 workspace/runtime。
  - 文件搜索优先 `rg` / `rg --files`。
  - 改代码先读相关文件。
  - 用户要求实现时直接施工。
  - 小步改动，保持模块边界。
  - 不回滚用户改动。
  - 修改后按风险运行验证。
- 工具使用：
  - Context Tree 是可见工作台。
  - 折叠节点是可操作 handle。
  - 需要 schema 时通过 tree action 启用。
  - search/fetch 是外部信息能力。
- 汇报：
  - 简洁说明改动。
  - 说明测试/验证。
  - 说明未验证原因。

落点：

- 短期：`src/crxzipple/modules/orchestration/application/prompting/producers.py`
- 中期：`src/crxzipple/modules/context_workspace/application/prompts/runtime_contract.md`
- 中期：`src/crxzipple/modules/context_workspace/application/root_nodes.py`

验收：

- 单测断言 agent instruction 包含工程行为契约。
- prompt preview 中可看到契约。
- 不新增新的 prompt block kind。
- 不绕过 Context Tree 注入 provider tool schema。

### Phase 2：Runtime Context 增强

目标：

- 让模型清楚知道当前运行环境，而不是只知道 agent/model/time/workspace。

新增字段建议：

```text
# Runtime Context

- Agent: assistant
- Model: openai.gpt-...
- Current time: 2026-06-10T...
- Timezone: Asia/Shanghai
- Agent home: ...
- Workspace: ...
- Filesystem access: workspace/local runtime available
- Network access: available/unavailable/unknown
- Approval policy: ...
- Sandbox: ...
- Shell: zsh/bash/unknown
- Local command runtime: exec/process available via Context Tree when enabled
- Daemon-managed services: use daemon/make dev-up for long-running services
```

注意：

- 这些是事实，不是 route。
- 未知值要标为 unknown，不要编造。
- permission/sandbox 应从实际运行配置或 application config 注入，不能硬编码。

落点：

- `src/crxzipple/modules/orchestration/application/prompting/runtime_context.py`
- `src/crxzipple/modules/orchestration/application/prompting/producers.py`
- `src/crxzipple/modules/orchestration/application/prompt_input.py`
- 必要时扩展 `RunPromptInputCollector` 依赖的 runtime/config port。

验收：

- runtime context 单测覆盖 workspace/timezone/permission/capability。
- prompt preview 能看到新增字段。
- Context Workspace snapshot metadata 记录 runtime context version/hash。

### Phase 3：工程契约迁入 Context Workspace Root Node

目标：

- `agent_instruction` 不长期承载过多固定契约。
- 固定 runtime / engineering contract 成为 Context Tree 的可见节点，UI 和 snapshot 都能审计。

节点建议：

```text
context.instructions.runtime_contract
context.instructions.engineering_agent_contract
context.instructions.tool_surface_contract
context.instructions.web_search_policy
```

职责：

- Context Workspace 拥有这些 prompt contract 节点。
- Orchestration 只收集 agent profile system prompt 和 runtime facts。
- Provider request 只消费 Context Workspace render snapshot。

落点：

- `src/crxzipple/modules/context_workspace/application/prompts/`
- `src/crxzipple/modules/context_workspace/application/root_nodes.py`
- `src/crxzipple/modules/context_workspace/application/runtime_contract.py`
- `tests/unit/test_context_workspace_root_nodes.py`
- `tests/unit/test_context_render_xml_renderer.py`

验收：

- 新节点出现在 Context Tree XML render。
- prompt report included_node_ids 包含 contract 节点。
- agent instruction 中不重复大段固定 contract。
- budget 紧张时 contract 节点仍有高优先级。

### Phase 4：Tool Default Policy 固化到 Tool Module

目标：

- 常驻/默认能力由 tool module 或 tool package metadata 控制。
- Context Workspace mirror 根据 metadata 和 tree state 决定 provider schema。
- Orchestration 不持有工具 route 逻辑。

默认核心能力建议：

```text
context_tree.expand
context_tree.collapse
context_tree.enable_tool_schema
context_tree.disable_tool_schema
context_tree.pin
context_tree.unpin

exec
process
```

外部信息能力：

```text
brave_search.web_search
web.fetch_text
web.fetch_json
```

策略：

- `exec` / `process` 是工程 runtime 默认能力。
- search/fetch 默认可以启用，但 prompt policy 限定用途。
- browser 仍通过 `configured.browser` / `browser.*` 作为普通 tool source。
- 长 schema 工具默认可折叠，必要时由 tree action 启用。

落点：

- `tools/command/tool.yaml`
- `tools/web/tool.yaml`
- `tools/brave_search/tool.yaml`
- `src/crxzipple/modules/tool/application/source_service.py`
- `src/crxzipple/modules/tool/application/catalog_models.py`
- `src/crxzipple/app/integration/context_workspace_orchestration/tool_schema_bootstrap.py`
- `src/crxzipple/modules/context_workspace/application/rendering/provider_mirror.py`

验收：

- enabled sources 包含命令、web、brave search。
- provider schema mirror 能看到 `exec` / `process`。
- 没有 source 的 direct tool id 不会静默丢失。
- metadata/report 记录 default requested/candidate/mirrored count。

### Phase 5：Web Search Policy 从 Prompt 走向 Source Policy

目标：

- search/fetch 可用，但不会成为 workspace/local runtime 任务的默认起手。
- 不通过关键词 route 实现。

可选机制：

- source-level visibility mode：
  - `default_visible`
  - `collapsed_visible`
  - `enabled_by_policy`
  - `disabled_by_policy`
- prompt mode 对 visibility 有影响，但不看用户文本关键词。
- agent 可通过 Context Tree 显式启用 search/fetch。

禁止：

- “航班” -> search
- “官网” -> browser
- “代码” -> exec
- 任何业务关键词到 tool source 的硬编码联想。

落点：

- `src/crxzipple/modules/tool/domain/value_objects.py`
- `src/crxzipple/modules/tool/application/source_service.py`
- `src/crxzipple/modules/context_workspace/application/rendering/provider_mirror.py`
- `src/crxzipple/modules/orchestration/application/turn_submission.py`

验收：

- source policy 只依赖 source metadata、prompt mode、access policy、tree state。
- 单测覆盖 search/fetch source 不因用户文本变化而变化。
- prompt preview 能解释 search/fetch 当前可见原因。

### Phase 6：Operations / Trace 可观察性

目标：

- 能从 UI/metadata 看出模型为什么能看到某些工具。
- 能审计 prompt contract 是否进入本轮 render。

新增/强化字段：

```json
{
  "prompt_contract": {
    "version": "2026-06-10",
    "hash": "...",
    "included_node_ids": []
  },
  "tool_schema_mirror": {
    "default_requested_count": 0,
    "default_candidate_count": 0,
    "default_mirrored_count": 0,
    "mirrored_schema_names": []
  },
  "tool_source_policy": {
    "enabled_source_ids": [],
    "collapsed_source_ids": [],
    "disabled_source_ids": []
  }
}
```

落点：

- `src/crxzipple/app/integration/context_workspace_orchestration/snapshot_metadata.py`
- `src/crxzipple/modules/orchestration/application/provider_request.py`
- `src/crxzipple/modules/operations/application/read_models/orchestration.py`
- `frontend/src/pages/trace/TracePage.vue`
- `frontend/src/pages/workbench/WorkbenchPage.vue`

验收：

- Trace 能看到本轮 prompt contract version/hash。
- Trace 能看到 mirrored schema names。
- Workbench prompt preview 能看到 Context Tree 中的 contract/tool nodes。

## 禁止实现清单

以下实现会破坏本轮决策，不允许进入主线：

- 在 orchestration 中恢复关键词工具 router。
- 在 provider request builder 中直接塞 `exec` / `browser` schema，绕过 Context Workspace mirror。
- 为 browser 保留第二条 provider tool schema path。
- 按 browser profile 生成 tool source。
- 把 search/fetch 通过删除 source 的方式解决模型偏好。
- 在 prompt 文本里写业务关键词规则。
- 把 Context Tree 变成 owner module 的万能代理，绕过 owner application service。
- 把大量工具结果重新塞回 direct transcript。

## 测试计划

### 单元测试

必须覆盖：

- `build_agent_instruction_block()` 包含工程 agent contract。
- `build_runtime_context_message()` 输出新增 runtime facts。
- default schema metadata 能把 `exec` / `process` 展开到 command source。
- provider mirror 能镜像默认 command schemas。
- search/fetch/source visibility 不依赖用户文本关键词。
- Context Tree render 包含 contract nodes。
- prompt report/snapshot metadata 包含 contract/tool mirror 信息。

建议命令：

```bash
PYTHONPATH=src pytest -q tests/unit/test_prompting.py
PYTHONPATH=src pytest -q tests/unit/test_turn_submission_prompt_bootstrap.py
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tool_adapter.py
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_root_nodes.py
PYTHONPATH=src pytest -q tests/unit/test_context_render_xml_renderer.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py
```

### 集成/手工验证

1. 启动 dev stack。

```bash
make dev-up
make dev-status
```

2. 发起项目内任务。

期望：

- 模型优先使用 Context Tree / exec / process 观察本地项目。
- 不以 web search 作为默认起手。

3. 发起官网航班任务。

期望：

- Brave Search 可用。
- 模型不会用 search/fetch 替代需要交互的官网访问。
- 如 browser 工具可见，模型优先 browser runtime。
- 如需要公共事实归因，模型可以使用 search。

4. 查看 prompt preview / trace。

期望：

- 能看到 Local/Engineering Runtime Contract。
- 能看到 runtime context facts。
- 能看到 `exec` / `process` mirrored schemas。
- 能看到 search/fetch 可见原因。

## 迁移顺序

推荐顺序：

1. 保持当前最小 Local Runtime Contract，先验证模型路线是否明显改善。
2. 补厚 `agent_instruction` 工程行为契约。
3. 增强 `runtime_context`。
4. 把固定 contract 迁到 Context Workspace root nodes。
5. 将 default tool policy 进一步下沉到 tool package/source metadata。
6. 做 source-level visibility mode。
7. 补 Operations / Trace 展示。

每一步都要保持：

- 一条真实 provider request 路径。
- Context Tree 是唯一 agent-visible 面。
- Tool Source Contract 是唯一工具来源。
- 无关键词 route。

## 验收标准

本计划完成时，应满足：

- 新建 session 的 prompt preview 中可以清楚看到工程 agent contract 和 runtime context。
- `exec` / `process` 在工程任务中默认可通过 Context Tree mirror 进入 provider schemas。
- Brave Search 和 fetch 保持可用，但不作为 workspace/local runtime 任务的默认探索入口。
- browser 不再有特殊 provider schema 注入路径。
- `turn_submission.py` 不含业务关键词工具 route。
- provider request builder 不含绕过 Context Tree 的常驻工具注入。
- Trace/Operations 能解释本轮工具 schema 可见性来源。
- 相关单测和目标集成验证通过。

## 当前风险

1. Prompt contract 过长会挤压 Context Tree budget。
   - 应通过 contract version/hash、节点优先级和摘要化控制。

2. 模型仍可能偏好语义明显的 search/fetch。
   - 需要 runtime context + tool surface policy + tree usage guidance 共同作用，而不是继续堆提示词。

3. `exec` / `process` 默认可见可能扩大风险面。
   - 需要依赖现有 authorization/runtime permission，不在 prompt 层解决安全边界。

4. 过早引入 source visibility mode 可能变成新 router。
   - visibility 只能依赖 source metadata、prompt mode、access policy、tree state，不能依赖用户文本业务关键词。

## 结论

CRXZipple 要吸收 Codex 的不是 “直接把工具塞给模型”，而是工程 agent 的强先验：

- 我在本地 runtime 中工作。
- 我先观察 workspace 和运行状态。
- 我使用命令、进程、browser runtime 验证事实。
- 我把 search/fetch 当外部信息能力。
- 我做完要验证和报告。

与此同时，CRXZipple 的核心设计继续保持：

- Context Tree 是模型可见工作台。
- Tool Source Contract 是工具事实来源。
- Context Workspace provider mirror 是 schema 进入 LLM 的唯一通道。
- Orchestration 只推进 run，不做 prompt/tool route。
