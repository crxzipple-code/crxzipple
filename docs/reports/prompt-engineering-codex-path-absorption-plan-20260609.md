# Prompt Engineering Codex Path Absorption Plan 2026-06-09

本文是 2026-06-09 对照 Codex 源码后形成的 prompt engineering / Context Tree / browser
investigation 收口施工入口。目标不是继续追加提示词补丁，而是把 Codex 已验证的工程 agent
执行路径吸收到 CRXZipple 当前架构中，让模型默认沿“工程式事实探索”推进任务。

关联文档：

- [../reference/codex-prompt-engineering-reference.md](../reference/codex-prompt-engineering-reference.md)
- [../reference/claude-code-prompt-engineering-reference.md](../reference/claude-code-prompt-engineering-reference.md)
- [engineering-agent-runtime-upgrade-plan-20260607.md](engineering-agent-runtime-upgrade-plan-20260607.md)
- [prompt-engine-layered-refactor-plan-20260608.md](prompt-engine-layered-refactor-plan-20260608.md)
- [prompt-tree-budget-redundancy-remediation-plan-20260608.md](prompt-tree-budget-redundancy-remediation-plan-20260608.md)
- [../context-workspace-prompt-tree-design.md](../context-workspace-prompt-tree-design.md)
- [../session-semantics-design.md](../session-semantics-design.md)

## 背景

最近一次真实 browser 任务暴露出路线偏差：用户希望 agent 到东航官网核验机票价格，模型长时间困在
DOM / form / overlay 操作里，没有像 Codex 那样主动分析页面运行时、前端脚本和网络请求。

对照 Codex 源码后，结论是：

- 这不是模型基础能力差异。
- 也不是 CRXZipple 缺少 browser network / script / runtime 工具。
- 直接原因是模型默认看到的工作台不同。

Codex 默认给模型的是工程工作台：

- 稳定 base instructions：模型知道自己是 coding / engineering agent。
- 显式 environment context：cwd、shell、workspace、权限、网络、日期时区。
- 每 turn 构造 model-visible tools：shell / exec / plan / apply_patch / view_image / MCP / dynamic tools。
- 历史进入模型前做 normalize 和 tool output truncation。
- 每个工具有并发能力声明。
- plan mode 与普通 assistant text 分离，计划不是普通执行链上的高频工具消耗。

CRXZipple 当前给模型的是 Context Tree 工作台，但 browser 任务里默认暴露的是 DOM / form 工具面：

- `configured.browser` 已有 `network`、`code_insight`、`runtime` 能力组。
- 最新 run 的 `prompt_flow_hint` 为空。
- 最新 LLM invocation 的 provider tool schemas 只有 `context_tree.*`、`browser.navigate`、
  `browser.observe`、`browser.action.trace`、`browser.form.*`、`browser.overlay.*`。
- `browser.network.*`、`browser.script.*`、`browser.runtime.inspect` 没有进入模型可调用面。

因此本轮要收的是执行引导、工具面、历史与结果治理、browser resource policy，而不是单句提示词。

## 不可妥协约束

1. 不回退到 orchestration 内部拼 prompt。
   - Context Workspace 继续拥有 Context Tree、node state、render snapshot 和 provider attachment mirror。
   - Orchestration 只收集运行输入、记录 snapshot、推进 execution chain。

2. 不做关键词联想 router。
   - 不写“航班/价格/官网”等业务关键词规则。
   - 路线选择必须来自任务 surface、可见工具能力、run mode、Context Tree 状态或 agent 明确动作。

3. 不保留兼容双轨。
   - 不新增第二套 browser prompt path。
   - 不新增 provider adapter fallback 来绕过 Context Tree。
   - 不让前端或 orchestration 直接拼 tool/browser/network truth。

4. 不把长结果继续灌入 direct transcript。
   - 长 browser trace、DOM、network body、script source 必须落 owner fact / artifact / evidence handle。
   - Provider-native transcript 只保留 provider tool protocol 必需尾巴。

5. 不把 browser 做成特殊 module。
   - Browser 仍是 owner module + `configured.browser` tool source。
   - 本轮新增的是通用 tool capability policy、prompt flow policy 和 Context Tree 节点表达。

## 对照 Codex 可吸收路径

### 1. Base Instructions 总纲路径

Codex 源码参考：

- `/Users/crxzy/Documents/codex/codex-rs/core/gpt-5.2-codex_prompt.md`
- `/Users/crxzy/Documents/codex/codex-rs/core/templates/model_instructions/gpt-5.2-codex_instructions_template.md`

吸收目标：

- `context.instructions` 下新增或强化 `execution.guide`。
- 明确 CRXZipple agent 是工程式任务执行 agent，不是普通问答助手。
- 总纲描述通用执行路线：
  - 明确目标。
  - 建立环境和约束。
  - 选择事实源。
  - 使用最小动作探索。
  - 验证结论。
  - 失败后切换证据路径。

当前问题：

- `runtime.contract` 已有原则，但偏抽象。
- Browser “DOM 只是入口”已经写在 contract 中，但没有转化为默认工具面和执行节点。

落点：

- `src/crxzipple/modules/context_workspace/application/prompts/runtime_contract.md`
- `src/crxzipple/modules/context_workspace/application/root_nodes.py`

### 2. Environment Context 路径

Codex 源码参考：

- `/Users/crxzy/Documents/codex/codex-rs/core/src/context/environment_context.rs`

吸收目标：

- 把 `run.runtime` 从“运行上下文文本块”拆成更清晰的运行现场节点：
  - `run.environment`
  - `run.permissions`
  - `run.provider`
  - `run.context_budget`
  - `run.browser_context`（仅 browser capability 可见或使用时出现）

当前问题：

- `run.runtime` 目前存在，但信息密度和可读性不足。
- 模型很难一眼知道当前可用环境、权限边界、browser profile/pool、provider 能力和上下文预算。

落点：

- `src/crxzipple/app/integration/context_workspace_orchestration/run_workspace_metadata.py`
- `src/crxzipple/modules/context_workspace/application/root_nodes.py`
- `src/crxzipple/modules/context_workspace/application/rendering/xml_renderer.py`

### 3. Contextual Fragment 路径

Codex 源码参考：

- `/Users/crxzy/Documents/codex/codex-rs/core/src/context/contextual_user_message.rs`

吸收目标：

- Context Tree 中明确区分：
  - 用户本次输入。
  - runtime / environment / policy fragment。
  - agent home fragment。
  - tool result / evidence fragment。
  - owner facts。

当前问题：

- CRXZipple 已经有树状根节点，但 session / execution / instructions / evidence 的语义还可以更清楚。
- 模型有时把工具结果、环境说明、历史摘要混成同一类上下文。

落点：

- `session.current` 下强化当前 user intent / active segment / evidence frontier。
- `execution.current` 下强化当前 run 现场和约束。
- `context.instructions` 下只保留总纲、优先级、agent home、树使用规则。

### 4. Tool Router / 默认工作台路径

Codex 源码参考：

- `/Users/crxzy/Documents/codex/codex-rs/core/src/tools/spec_plan.rs`

吸收目标：

- 每次 provider request 都有清晰的 tool surface policy：
  - 哪些工具默认可见。
  - 哪些工具作为 Context Tree handle 可展开。
  - 哪些工具被 authorization/access/policy 屏蔽。
  - 哪些工具因为资源约束只能串行。

当前问题：

- CRXZipple 已有 Context Tree tool discovery 和 schema mirror。
- 但 browser 任务里关键能力组没有进入 provider tool schemas，导致模型看不见 network/code/runtime。

落点：

- `src/crxzipple/app/integration/context_workspace_orchestration/tool_schema_bootstrap.py`
- `src/crxzipple/app/assembly/tool_sources/browser.py`
- `src/crxzipple/modules/orchestration/application/prompt_input.py`
- `src/crxzipple/modules/orchestration/application/tool_resolver.py`

### 5. History Normalize 路径

Codex 源码参考：

- `/Users/crxzy/Documents/codex/codex-rs/core/src/context_manager/history.rs`

吸收目标：

- Provider request 前执行 hard normalize：
  - assistant tool call 必须有对应 tool result。
  - orphan tool result 不能进入 provider transcript。
  - 不支持图片的 provider 不收到图片 content。
  - 已消费的长工具结果折叠成 evidence handle。

当前问题：

- 当前已有 provider-message ordering contract，但 direct transcript 在长 browser run 中仍可能被大结果吞掉。
- Context Tree 和 provider-native transcript 会重复承载部分 tool result。

落点：

- `src/crxzipple/modules/orchestration/application/prompt_transcript.py`
- `src/crxzipple/modules/orchestration/application/provider_request.py`
- `src/crxzipple/app/integration/context_workspace_session.py`

2026-06-09 收口状态：

- Provider-native direct transcript 只保留当前用户输入和协议必需的 tool call/result 尾巴。
- 当前 session 的可见历史通过 `session.current -> session.segment.current -> session.messages.current`
  进入 Context Tree，而不是回退为 provider messages 数组链。
- 当前用户输入在 Context Tree 中只保留 “Delivered as provider user message for this turn.” 标记，
  避免同一用户消息在 direct transcript 和树内重复出现。
- 已完成的上一轮工具交互在下一轮作为 `session.tool_interaction` 可见；当前 run 内已经被模型消费的
  工具结果仍按 frontier / consumed 状态折叠，避免长工具结果膨胀 prompt。
- `session.tool_interaction` 的 frontier、opened_by_default、collapsed_by_default 属于 owner 派生状态；
  刷新时会随 session/run 阶段变化更新，只保留用户 pin 等控制态。

### 6. Tool Output Truncation 路径

Codex 源码参考：

- `/Users/crxzy/Documents/codex/codex-rs/core/src/tools/context.rs`
- `/Users/crxzy/Documents/codex/codex-rs/core/src/context_manager/history.rs`

吸收目标：

- Tool result 进入模型前必须有统一 envelope：
  - concise summary
  - key facts
  - status
  - evidence refs
  - omitted/truncated reason
  - owner read handle

当前问题：

- `browser.form.fill` / `browser.action.trace` 默认带 network/lifecycle/storage/snapshot diff，结果可能超过 100k chars。
- 这些大结果进入 direct transcript 后会严重污染下一轮注意力。

落点：

- `src/crxzipple/modules/tool/application/worker_service.py`
- `src/crxzipple/app/assembly/tool_handlers/browser.py`
- `src/crxzipple/modules/browser/*`
- `src/crxzipple/app/integration/context_workspace_session.py`

### 7. Parallel Capability 路径

Codex 源码参考：

- `/Users/crxzy/Documents/codex/codex-rs/core/src/tools/registry.rs`

吸收目标：

- Tool function 拥有 execution profile：
  - `read_only`
  - `mutates_resource`
  - `resource_scope`
  - `supports_parallel`
  - `serial_group_key`

当前问题：

- Orchestration 会把同一 LLM response 中多个 tool calls 组成 tool batch。
- Tool worker 对 inline runs 使用 `asyncio.gather` 并行执行。
- 对同一 browser target 的多个 `form.fill` / `click` / `type` 并行会造成页面状态串扰。

落点：

- `src/crxzipple/modules/tool/domain/value_objects.py`
- `src/crxzipple/modules/tool/domain/entities.py`
- `src/crxzipple/modules/tool/application/submission_service.py`
- `src/crxzipple/modules/tool/application/worker_service.py`
- `src/crxzipple/modules/orchestration/application/engine_tool_executor.py`

### 8. Plan Mode / Plan Stream 路径

Codex 源码参考：

- `/Users/crxzy/Documents/codex/codex-rs/core/src/tools/handlers/plan_spec.rs`
- `/Users/crxzy/Documents/codex/codex-rs/core/src/session/turn.rs`

吸收目标：

- 计划是执行辅助，不是每一步都调用的工具。
- `work.plan` 保留，但只在阶段变化时更新：
  - 新任务开始。
  - 进入新证据路径。
  - 关键事实确认。
  - 阻塞或恢复。
  - 收口完成。

当前问题：

- 最新长 browser run 中 `context_tree.update_plan` 调用了 31 次。
- 这消耗执行步数，也使模型更关注“维护计划”而不是推进事实探索。

落点：

- `src/crxzipple/modules/context_workspace/application/root_nodes.py`
- `tools/context_tree/tool.yaml`
- `src/crxzipple/modules/context_workspace/application/prompts/runtime_contract.md`

### 9. Prompt Debug / Final Request Inspectability 路径

Codex 源码参考：

- `/Users/crxzy/Documents/codex/codex-rs/core/src/prompt_debug.rs`

吸收目标：

- Operations / Trace 能直接看到某次 LLM invocation 的最终请求：
  - context tree XML snapshot
  - provider messages
  - provider tool schemas
  - attachments
  - request metadata
  - token budget breakdown
  - omitted/truncated nodes

当前问题：

- CRXZipple 已经能查 prompt preview / snapshot，但排障仍偏工程人员查库。
- 对路线偏差的判断应能在 UI 中直接完成：模型当时到底看见了哪些工具和上下文。

落点：

- `src/crxzipple/modules/orchestration/interfaces/http.py`
- `src/crxzipple/modules/llm/application/services.py`
- `frontend/src/pages/Trace*`
- `frontend/src/pages/Workbench*`

## 目标 Prompt Tree 结构

目标结构不是新增另一套 prompt，而是让现有树层级更明确：

```text
context.instructions
  runtime.contract
  execution.guide
  context.priority
  context.tree_usage
  agent.identity
  agent.home

execution.current
  run.goal
  run.flow
  run.environment
  run.permissions
  run.provider
  run.context_budget
  run.constraints
  work.plan
  evidence.frontier
  execution.continuation

session.current
  session.active_segment
  session.current_user_intent
  session.evidence_ledger
  session.folded_history

tools.available
  source-first capability bundles
  source prompt groups
  provider-mirrored tool schemas

skills.available
memory.visible
artifacts.session
workspace.resources
```

### 节点语义

- `execution.guide`：稳定工程执行路线，来自 runtime contract，但更面向行动。
- `run.goal`：本次 run 要完成的目标，不等同于 session 总标题。
- `run.environment`：cwd、runtime host、browser profile/pool、channel/source、daemon readiness。
- `run.permissions`：authorization/access/tool visibility/sandbox/network 等边界。
- `run.provider`：LLM profile、capability、image/file/tool support。
- `run.context_budget`：rendered tree、direct transcript、tool schemas、attachments 的预算状态。
- `run.constraints`：当前 run 的硬约束和调度约束，例如 browser mutating tool 串行。
- `evidence.frontier`：下一轮必须处理的最新事实尾巴，避免模型回到过期证据。
- `session.evidence_ledger`：已验证事实、失败路径、未解决缺口和 owner refs。

## Browser Investigation 目标路线

Browser 任务的默认路线应从“页面操作”升级为“浏览器工程调查”：

```text
1. Establish browser context
   - profile / pool / current target / URL / readiness

2. Observe first pass
   - interactive snapshot / visible form / tab state

3. Choose evidence path
   - if UI is enough: use form/overlay/DOM action
   - if data truth is behind frontend runtime: inspect runtime/scripts/network
   - if page is opaque: use storage/service worker/diagnostics

4. Execute smallest safe action
   - one mutating page action at a time per target

5. Verify
   - result visible in page, network response, app state, or replayed request

6. Extract and report
   - verified facts, assumptions, gaps, refs
```

### Browser tool bootstrap policy

当前 `configured.browser` 已有以下 groups：

- `navigation`
- `observation`
- `action_trace`
- `page_interaction`
- `forms_overlays`
- `dom_inspection`
- `network`
- `code_insight`
- `storage`
- `context_leases`
- `environment`
- `diagnostics`

本轮要调整默认暴露策略：

- Browser source 展开时，默认 starter schemas 应优先覆盖：
  - `browser.navigate`
  - `browser.observe`
  - `browser.network.inspect`
  - `browser.runtime.inspect`
  - `browser.script.find_request`
  - `browser.code.search`
  - `browser.evaluate`
- `browser.action.trace` 不再作为默认 starter schema；它保留在
  `action_trace` group 中，由模型在 runtime/code 或 network evidence
  已定位到具体状态变更后按需展开/使用。
- `browser.tabs.list` 不再作为默认 starter schema；它保留在
  `navigation` group 中，只用于恢复、多标签歧义或目标丢失。
- `forms_overlays` 不再作为 browser investigation 的唯一默认路线。
- `browser.form.fill` / `browser.overlay.select` 作为需要页面操作时再显式启用的 mutating tools。
- 如果 provider tool schema 预算不足，优先保留 route-changing / evidence-producing tools，延后低层点击和批量读工具。

## 开发任务清单

### P0. 文档和当前状态验收

- [x] 将本文加入 [../README.md](../README.md) 当前报告索引。
- [x] 记录最新长 browser run 的 route-deviation / route-recovery 证据：
  - stale run `396ba17e9f41462c893a394f0e6dd49e` 只暴露 `context_tree.*`，
    browser source catalog 仍是旧 prompt metadata，模型没有 network/code/runtime schema。
  - refreshed run `c0def1a8a720435997db20d8321eed2a` 暴露
    runtime/code + network starter schemas，route audit 为 `ok / runtime_network_visible`。
  - real external replay run `f5652335b8514545bc4df53e3cc7d983`
    已开始使用 `browser.observe`、`browser.runtime.inspect`、`browser.network.inspect`、
    `browser.code.search`、`browser.script.find_request`，说明路线从 DOM/Form 点击偏移回
    runtime/network/script 探索。
  - 同一 run 暴露新的硬阻断：旧 `browser.network.inspect` 将完整
    `Page.getResourceTree` 放入 tool details，真实东航页面触发
    `Tool run result details exceed the allowed size budget (131072 chars)`。
  - 修复后 API replay `2a0390f628ba4dc0acda8eb02d386238` 在东航页面返回
    compact CDP resource summary：108 resources / 3 frames / 14k details chars，
    top-level content 不再包含 base64 data URL 噪声。
- [x] 记录一次真实 prompt-surface 验收：
  - stale catalog run：`396ba17e9f41462c893a394f0e6dd49e`。
    当时 `configured.browser` source config hash 为 `sha256:096a...`，
    prompt keys 只有 `groups/summary/title`，provider schemas 只有 `context_tree.*`。
  - 刷新 source catalog 后：`configured.browser` config hash 更新为
    `sha256:35e88b89fb5a6007954c6154bed912f7455f32fcbaa040629e906f0b84fa7767`，
    prompt keys 包含 `default_tool_schema_group_refs/default_tool_schema_policy/evidence_path_ladder`。
  - passing run：`c0def1a8a720435997db20d8321eed2a`。
    provider schemas 包含 `browser.navigate`、`browser.observe`、`browser.action.trace`、
    `browser.network.inspect/start_capture/list_requests/get_response_body`、
    `browser.runtime.inspect`、`browser.script.find_request/inspect`、`browser.code.search`。
    route audit 为 `ok / runtime_network_visible`。
  - 2026-06-09 后续根因确认：validation run
    `7743b31e4e58468faab661bba4e418a5` 的 provider surface 已有
    runtime/network/code schema，但 `configured.browser` 仍把 `action_trace`
    作为 default starter，并且 `browser.observe` 在看到普通 form/ref 时把
    primary evidence path 排为 `stateful_interaction`。这会把模型重新拉回
    “点击表单”路线。
  - 本次修复后默认 starter 收敛为 `navigation`、`observation`、`network`、
    `code_insight`；`browser.observe` 在已有 runtime/script/API 信号时优先返回
    `runtime_and_code`，普通 form/ref 只作为后续 stateful path。
  - validation run `fe8b05c5cd224c608450cc6b6ccd3c82` 验证 provider surface
    已不再包含 `browser.action.trace`，但 6 步预算被计划更新、重复
    `browser.tabs.list` 和一次 `browser.code.search` 耗尽。
  - 后续修复将 `browser.tabs.list` 从默认 navigation schema 移除，保留为
    on-demand navigation group tool；`browser.navigate` 只要求 `url`，因此默认起步
    不再需要先列标签。
- [x] 补充一条 regression fixture，证明旧问题：provider schemas 缺少 network/code/runtime 时，
  provider-visible browser affordance 会退化为 `dom_form_only` / `dom_form_click_bias`。
  当前 request metadata 已记录 `browser_investigation_affordance_status`、`route_bias`、
  `present_paths`、`missing_paths` 和 schema 分组清单。
- [x] Workbench / Trace 路线诊断已显示 `browser_investigation_*` audit：
  - `ok` 表示 runtime/code + network 路线已进入模型可见工具面。
  - `dom_form_only` 标红，表示本轮仍会偏向 DOM/Form 点击路线。
  - 详情显示 present paths、missing paths 和可见 browser schema 数量。

### P1. Prompt Tree 执行节点重构

- [x] 新增 `execution.guide` 静态节点，内容来自 runtime contract 的工程执行路线，不复制整份 contract。
- [x] 新增 `run.goal` 节点，来自 inbound instruction / run metadata / session active intent。
- [x] 将 `run.runtime` 拆为 `run.environment`、`run.permissions`、`run.provider`、`run.context_budget`。
- [x] 新增 `run.constraints` 节点，显示当前 run 的 tool/resource/context 硬约束。
- [x] 新增 `evidence.frontier` 节点，展示下一轮模型必须优先处理的最新事实尾巴。
- [x] 保持 `execution.current` 作为聚合根，不把 instruction / session history 塞回 execution。
- [x] XML renderer 继续使用通用 node render；新增节点已通过 snapshot 覆盖。
- [ ] UI tree viewer 验收新增节点在前端原生 XML 视图里的层级和折叠表现。
  - 当前源码确认 Workbench / Trace 的 Actual Request XML tab 使用
    `XmlSourceViewer`，具备原生 XML 源码、行号、折叠三角和横向滚动。
  - `frontend` typecheck / build 已通过。
  - 本轮未勾掉该项：当前仓库没有 Playwright 依赖；尝试用系统 Edge headless
    独立临时 profile dump DOM 未能在限定时间内退出，已终止临时进程，未做截图验收。
- [x] 单测覆盖默认 root seeds、metadata 注入、render snapshot、估算和 XML 顺序。

### P2. Tool Surface Policy / Schema Bootstrap

- [x] 定义 `ToolSurfacePolicy`：
  - default mirrored schemas
  - expandable groups
  - provider schema budget
  - priority / eviction rule
  - reason metadata
- [x] `tool_schema_bootstrap.py` 支持 source/group priority，而不是只按 `prompt_flow_hint` 机械展开。
- [x] `tool_schema_bootstrap.py` 支持从 source prompt policy 读取默认 group refs；没有 `prompt_flow_hint` 时也能走 owner source metadata。
- [x] Browser source 默认 starter schemas 改为 navigation + observation + network + runtime/script/code + page-context evaluate。
  - `browser.action.trace` 和 `browser.tabs.list` 都不再默认镜像。
  - `browser.evaluate` 从 `page_interaction` 移到 `code_insight`，用于 deliberate
    page-context probes，帮助模型像工程 agent 一样枚举 runtime globals、
    frontend API client 和页面内请求构造。
- [x] `forms_overlays` 从默认 starter 中移出，作为页面操作路径按需启用。
- [x] provider request metadata 记录：
  - mirrored group refs
  - skipped schemas
  - bootstrap reasons
  - budget eviction result
- [x] provider mirror budget 记录默认 group refs / group ref count / reason，供 snapshot metadata 和 operations 调试读取。
- [x] 单测验证 browser run 的 provider schemas 包含 network/code/runtime starter。

### P3. Browser Investigation Guide 和结果路径

- [x] `runtime_contract.md` 中 browser 章节改为更短的总原则，具体路线放 `execution.guide` / browser source metadata。
- [x] Browser source metadata 增加“evidence path ladder”，强调 network/runtime/script 不是兜底，而是事实源之一。
- [x] `browser.observe` 结果中显式建议后续工具组：
  - form/overlay
  - network
  - runtime/script
  - storage/diagnostics
- [x] Browser evidence path ladder 收敛为 `modules/browser/application/evidence_paths.py`，`configured.browser` source metadata 与 `browser.observe` 输出共享同一份定义。
- [x] `browser.action.trace` 结果中只保留关键摘要和 refs，长 before/after snapshot 落 owner fact / artifact details。
- [x] `browser.network.inspect` 和 `browser.runtime.inspect` 结果结构化为 key facts + handles。
- [x] 单测覆盖 browser result envelope 的大小预算和 evidence refs。

### P4. Tool Execution Resource Policy

- [x] Tool function 增加 execution profile：
  - read-only / mutating
  - resource scope
  - serial group key
  - supports parallel
- [x] Browser mutating tools 标记为同一 target 串行：
  - navigate
  - click
  - type
  - form.fill
  - overlay.select
  - evaluate（默认视为 mutating，除非显式 read-only）
- [x] Browser read-only tools 可按 profile/target 限流并发：
  - observe
  - network inspect/list/get
  - script inspect/search
  - runtime inspect
  - storage list/query
- [x] Orchestration tool batch 按 resource policy 拆分：
  - 可并行的同时提交。
  - 同一 browser `profile/allocation + target_id` 的 mutating tool call 按顺序提交。
  - 缺失 `target_id` 时视为该 profile 的当前目标通配，避免 current-tab 操作并发串扰。
- [x] Tool run metadata 记录 resource policy decision：
  - `supports_parallel`
  - `mutates_state`
  - `execution_lane`
  - `resource_scope`
  - `resource_key`
  - `serial_group_key`
- [x] 单测覆盖同一 browser target 的 mutating tools 不会同批并发执行。
- [x] 单测覆盖同一 browser target 的 read-only tools 仍可同批提交。
- [x] Browser target/page generation 本轮明确延后，不在 orchestration metadata 里临时模拟：
  - 当前 Browser owner module 还没有稳定 generation fact。
  - 下一步如需要，应在 Browser owner 中新增 target revision/readiness fact，再由
    tool result/event 更新。
  - 本轮只保留 resource policy 串行治理，不把 generation 做成临时兼容字段。

### P5. Tool Result Normalize / Truncation

- [x] 定义通用 `ToolResultEnvelope`：
  - status
  - summary
  - key_facts
  - warnings
  - evidence_refs
  - omitted_count
  - truncated
  - read_handles
- [x] Tool Worker completion 前对外置大文本生成 model-visible result envelope。
- [x] 大文本结果不直接进入 session tool result content；完整正文进入 artifact，
  模型可见内容只保留短摘要、artifact refs 和 read handles。
- [x] Provider transcript builder 保留 assistant tool call 协议消息，并对 envelope/legacy artifact
  tool result 输出 compact provider transcript，不复制 raw 大结果。
- [x] Context Tree 的 `session.tool_interaction` 在展开/钉住时展示 envelope，不复制 raw result。
- [x] 单测覆盖大文本 tool result 外置成 artifact refs 和 envelope。
- [x] 单测覆盖 Context Tree 渲染 envelope refs，不把 preview/raw result 当正文塞回 prompt。
- [x] 单测覆盖长 browser tool chain 在 Context Tree 中按范围折叠，并保持 prompt budget。
- [x] 单测覆盖大 action trace 落 artifact refs，不把前后大 snapshot 直接塞回文本结果。
- [x] 单测覆盖 provider transcript 截断时仍保留 assistant tool call / tool result 配对。
- [x] Browser owner 大 payload / raw CDP 输出补 owner-level budget test：
  - 大 snapshot / observe 结果不能绕过 envelope 或 artifact refs 进入 prompt。
  - 网络正文、脚本源码、action trace 三类大 payload 均有稳定 read handle。
  - `browser.observe` 聚合入口只输出统计、bounded snapshot 和 evidence path，不把
    raw resource tree / raw response body / raw DOM 复制到顶层模型可见文本。

### P6. Plan 节点节流与语义调整

- [x] `work.plan` 文案改为阶段性计划，而不是每步都更新。
- [x] `context_tree.update_plan` tool description 增加使用约束：
  - 不用于普通思考。
  - 不用于每个工具调用前后。
  - 只在阶段变化或阻塞恢复时更新。
- [x] `context_tree.update_plan` 对相同 public plan payload 做 no-op，不刷新 Context Tree revision。
- [x] `context_tree.update_plan` 记录 `plan_phase`、`plan_phase_signature`、
  `previous_plan_phase_signature`、`phase_changed`、`plan_update_count`：
  - `phase` 由 `objective/status/current_step` 形成，是公开计划的阶段事实。
  - 同一 phase 下重复 `phase_update` / `phase_change` 直接 no-op，不刷新 Context Tree revision。
  - 同一 phase 下的 `verified_fact`、`blocker`、`recovery`、`final_summary` 仍允许写入，
    用于记录真实证据或状态变化。
- [x] Trace / Workbench 的 prompt request 路线诊断显示 `work_plan_update_count`
  和当前 `work_plan_phase`，作为计划工具噪音 / route 偏差诊断指标。
- [x] 单测覆盖重复 update plan 的压缩/去重行为。

### P7. Final Request Inspectability

- [x] Trace / Workbench 中对每个 LLM invocation 读取真实 invocation prompt preview，
  而不是在前端从 `/llms/calls/{id}` 临时拼装近似请求。
- [x] Trace / Workbench 中对每个 LLM invocation 显示：
  - provider messages
  - Context Tree XML snapshot
  - mirrored tool schemas
  - provider options
  - provider attachments
- [x] Trace / Workbench Context 面板增加“路线诊断”小节：
  - 当前模型看见了哪些 browser groups。
  - 当前模型 browser investigation affordance 是 `ok`、`partial` 还是 `dom_form_only`。
  - schema mirror 命中/跳过数量。
  - 可镜像工具、已启用候选、默认请求、重复 Schema 的能力可见性计数。
  - direct transcript / tree / tool schemas 各占多少。
  - provider transcript 中工具结果压缩/省略摘要。
- [x] Trace / Workbench 继续补齐更细的 request debug 明细：
  - hidden/available capability groups 的完整 group-level 清单。
  - schema bootstrap reasons 的可展开明细表。
- [x] LLM owner 增加 `/llms/calls/{invocation_id}/prompt-preview`：
  - 只读取已持久化 invocation messages / tool schemas / request metadata。
  - 从 `request_metadata.context_render_snapshot_id` 暴露真实 Context Workspace snapshot 引用。
  - 不调用 orchestration preview，不生成新的 `ctxpreview_*`。
- [x] Turn owner 的 `/turns/{run_id}/prompt-preview` 已改为执行事实优先：
  - 已执行 run 优先读取 Context Workspace recorded snapshot。
  - 未执行 run 才生成 live `ctxpreview_*`。
  - 实测旧慢 run `5eb562b796804f3eb2cd0144c68ce93f` 从 108s 降到约 1.85s，
    返回 `ctxsnap_e9c68d3bbfe849afbec7fbabf6d98b9a`。
  - 这确认慢点来自 live owner refresh / render rebuild，不是 prompt 内容尺寸。
- [x] Context Tree bootstrap / prompt preview 少做 owner refresh：
  - `ContextTreeService.list_tree(..., refresh=False)` 用于已经完成显式 expand 后的只读查看。
  - `ContextTreeService.get_node()` 用于 tool schema bootstrap 检查单个节点，不触发整树 owner refresh。
  - Tool source/function 查询增加 batch path，避免 default tool schema metadata 解析时逐工具 N+1 查询。
  - 这修复了 streaming/cancel 回归中 LLM adapter 尚未启动就被 Context Tree render 卡住的问题。
- [x] Workbench 选中 LLM step 时改用 invocation prompt preview DTO，
  不再在前端从 `/llms/calls/{id}` 临时拼装 preview。
- [x] Trace 选中 LLM event 时改用 invocation prompt preview DTO，
  不再在前端从 `/llms/calls/{id}` 临时拼装 preview。
- [x] 单测和前端类型检查覆盖 invocation prompt preview DTO。

### P8. Browser Route Regression 验收

- [x] 构造不访问外网的 browser investigation fixture，覆盖：
  - 动态表单。
  - 隐藏/自定义控件。
  - 前端请求方法。
  - 可 replay 的 API。
- [x] 单测覆盖 Browser tool 工程探索路径：
  - `browser.runtime.inspect` 发现运行时框架 / `$nuxt`。
  - `browser.script.find_request` 定位 `/portal/v3/shopping/briefInfo` 和 API client path。
  - `browser.network.replay_request` 使用 captured request + override json 复放并返回价格事实。
- [x] Browser tool result 在模型可见文本和 `browser_evidence` metadata 中暴露 evidence path：
  - runtime/script/code 工具标记为 `runtime_and_code`。
  - network/replay 工具标记为 `network_truth`。
  - stateful interaction / diagnostics / orient 工具按路径归类。
- [x] Prompt transcript 对大型 tool result 做压缩时保留 `browser_evidence.evidence_path_*`，
  避免 body/artifact externalization 后模型丢失验证路径。
- [x] Browser route fixture 验证 3 个工具步内发现：
  - 页面 runtime state。
  - endpoint/method/payload shape。
  - network response fact。
- [x] Provider request metadata / Workbench / Trace 可以直接看出本轮是否暴露了 runtime/code + network 路线。
- [x] 真实 agent run 回放验证模型能看见并描述 runtime/code + network 路线：
  - run `c0def1a8a720435997db20d8321eed2a` 在 1 step 内完成简短计划。
  - 回复明确优先使用 `browser.network.start_capture/list_requests/get_response_body`
    与 `browser.script.find_request/code.search/runtime.inspect`。
- [x] 真实外网页面 replay 验证 `browser.network.inspect` 不再因 CDP resource tree 过大失败：
  - 旧 run `f5652335b8514545bc4df53e3cc7d983` 在东航页面失败于 oversized details。
  - `BrowserNetworkInsightService` 现在返回 frame/resource count、type distribution、
    bounded frame/resource samples，并标记 `raw_omitted/truncated`。
  - data URL 资源压缩为 `data:*;base64,[omitted N chars]`，避免模型可见文本被 base64 淹没。
- [x] 真实外网页面 replay 验证 `browser.observe` 不再因 optional 子动作失败整体失败：
  - 旧 run `48385bd0b8d748d4b48e86a2ef688273` 在东航页面遇到
    `Expecting value: line 1 column 1` 裸异常。
  - `BrowserToolApplicationService` 现在把 adapter 未预期异常收敛为 display-safe
    `BrowserToolApplicationError`。
  - `browser.observe` 只把失败 optional sections 写入 `errors[]`，不污染正常 payload。
  - API replay `f0f6c17083c947d584fac31f4deff759` 已成功返回 runtime/framework/code facts。
- [ ] 真实外网页面任务回放验证模型在有限步数内主动执行上述路线，而不是退回重复 DOM/Form 点击。
  - validation run `7743b31e4e58468faab661bba4e418a5` 证明 prompt surface 已正确：
    provider schemas 包含 `browser.network.inspect`、`browser.runtime.inspect`、
    `browser.script.find_request`、`browser.code.search`，route audit 为
    `ok / runtime_network_visible`。
  - 同一 run 的实际路线仍偏慢：前两轮 LLM 各约 60s，先 list tabs / open 官网，
    第三轮才进入 `browser.observe`，随后仍有点击倾向。下一步应继续降低 LLM 回合数，
    让 observe 后的 evidence path 更强地引导 runtime/network/script 探索。
  - 2026-06-09 修复：`action_trace` 已从 browser 默认 starter 中移除；
    `browser.observe` 的 primary guidance 已改为在 runtime/script 信号存在时返回
    `inspect-runtime-or-scripts` / `runtime_and_code`，不再由普通 refs 优先触发
    `trace-meaningful-action`。
  - validation run `83857882c00742e28d6897d269a711d2` 验证路线继续改善：
    provider mirrored tools 中没有 `browser.tabs.list` / `browser.action.trace`；
    实际路线为 `browser.navigate` -> `browser.observe` ->
    `browser.network.start_capture` -> `browser.runtime.inspect` ->
    `browser.script.find_request` -> `browser.network.inspect` ->
    `browser.code.search`，并产生 `orient`、`network_truth`、
    `runtime_and_code` 证据路径。
  - 同一 run 暴露新的阻断：`network-start-capture` 结果只在嵌套
    `capture.capture_id` 中携带 id，模型可见文本没有明确 `capture_id`，
    导致模型把 `target_id` 当作 `capture_id` 调用
    `browser.network.list_requests`。已将 network action envelope 顶层补齐
    `capture_id/profile/target/status`，formatter 也显式输出
    `Use capture_id: ...` 和下一步 `browser.network.list_requests`。
  - 同一 run 还暴露默认能力缺口：模型可以搜索脚本，但缺少默认
    page-context JS probe；已把 `browser.evaluate` 纳入 `code_insight`
    默认 schema，让 agent 可在页面上下文中读取 `$nuxt`/client globals、
    枚举 API 方法或执行有证据约束的只读探针。
  - validation run `0118e4c453cc4455a192f013d61293fa` 验证
    `browser.evaluate` 已进入 provider mirrored tools，并在实际链路中被调用。
    但该 run 暴露新的 prompt 膨胀点：多轮 `browser.code.search` 把压缩 JS
    的长单行 snippet 放入 direct transcript，`session_message_range`
    膨胀到 117k chars，模型继续换关键词搜索而不是收敛到 script inspect /
    evaluate / replay。已将 code search 上游 snippet 降到 320 chars，并将
    `code.search` / `script.find_request` top-level formatter 收敛为短证据索引：
    script id、URL、位置、短 preview、details handle 和下一步 inspect/evaluate 指引。
  - validation run `be2d1b16de124b76a879d317a5642780` 验证
    capture id / evaluate / snippet 压缩后 prompt 不再被单个搜索结果撑爆，
    总估算约 13k tokens，并产生 `orient`、`network_truth`、`runtime_and_code`
    证据路径；但模型仍在 `runtime.inspect`、`network.inspect`、
    `script.find_request`、`code.search` 之间循环，没有稳定升阶到
    `script.inspect` / `evaluate`。
  - 随后修复将 `code.search` / `script.find_request` 视为索引工具：
    provider schema 增加 `limit/max_scripts/context_lines` 上限和默认值，
    执行层同步收紧默认扫描范围；runtime contract、execution guide、
    browser source summary 和 tool result formatter 都加入“候选出现后停止宽搜，
    转 inspect/evaluate/fetch/replay”的规则。
  - validation run `cb55c44d5ff04fd18af4cb67c49b10c3` 验证模型已开始使用
    `browser.script.inspect` 和 `browser.evaluate`，但暴露新的 browser 能力缺口：
    东航站点使用压缩单行 bundle，`code.search` 返回的是 `line=1, column=N`，
    旧 `script.inspect` 只能按行读取，模型会把 column 误当 line 或读不到
    关键片段。
  - 已为 `browser.script.inspect` 增加 column/window 预览：
    支持 `column`、`start_column`、`column_window`，修复超长单行导致
    `end_line=0` 的错误；formatter 改为 `line X, column Y` 和
    `script_id=...`，并在 `script_id` 误传 URL 时自动按 `url_contains`
    解析。
  - validation run `d04efa66c1fe4058980a92a9fd101d12` 验证 column inspect
    生效：模型成功用 `start_column` 读取到 `commonlib/js/index.js` 和
    `_nuxt/4f2a436.js` 的相关片段，prompt 估算降到约 11k tokens，top rendered
    nodes 不再由长 code search 结果占据。但 run 仍在 20 步内超限，调用分布中
    `browser.code.search` 仍有 15 次，说明下一步阻塞已经从“看不见工具/读不到
    bundle 片段”转为“缺少更高阶 request/client extraction 和执行链停机策略”。
  - 验收过程中发现 `/turns/{run_id}/cancel` 对长 reason 会因
    `dispatch_tasks.waiting_reason VARCHAR(100)` 触发 500；已将
    orchestration/dispatch domain 的 `waiting_reason` 收敛为短摘要，
    完整取消原因保留在 run metadata。
- [x] 验证 provider schemas 中包含 browser network/code/runtime。
- [x] 验证没有并行 mutating browser action。
- [x] 验证最终回答引用 verified evidence path 的工程约束：
  - `estimate_breakdown.evidence` 从可见 `session_evidence` 节点提取
    `verified_evidence_paths`、`browser_verified_evidence_paths` 和
    `final_response_requires_evidence_path`。
  - Context snapshot metadata 与 LLM request metadata 透传上述字段。
  - Workbench / Trace 路线诊断显示“最终证据”状态，便于确认本轮最终回答是否应引用
    `network_truth`、`runtime_and_code` 等证据路径。
  - 单测覆盖：无证据时字段稳定为空/false；存在 verified browser evidence path 时
    request metadata 标记最终回答必须引用该路径。

### P6. 当前状态：候选代码到可执行请求

- [x] Browser owner 新增 request extraction 工具，而不是继续让模型用
  `code.search` 人肉猜接口：
  - 从候选 script_id + column/window 中提取同作用域附近的函数名、对象链、
    URL/path、payload key、method 和调用关系。
  - 输出结构化候选：`endpoint_candidate`、`client_method_candidates`、
    `payload_key_candidates`、`confidence`、`evidence_preview`。
  - 保持 owner module 内实现，不把航空站点规则写进 prompt 或 orchestration。
  - 已落点：
    - `src/crxzipple/modules/browser/infrastructure/script_insight.py`
    - `tools/browser/local.py`
    - `src/crxzipple/app/assembly/tool_sources/browser.py`
    - `src/crxzipple/app/assembly/tool_handlers/browser.py`
  - `configured.browser` 的 `code_insight` 默认 schema 已包含
    `browser.script.extract_request`，并进入 evidence ladder、snapshot
    affordance metadata、observation suggested tools 和 runtime contract。
  - live validation `108854ef4dc8435a87eb5aca6c0fd97a`：
    - provider attachments 中包含 `browser.script.extract_request`。
    - Context Tree included nodes 中包含 `tools.tool.browser.script.extract_request`。
    - Evidence 中产生 `api_endpoint: browser.script.extract_request`。
    - 模型在 6 步内完成路线验证，确认 runtime/code/script path 可用。
    - 本轮只抽到 self-service/navigation 类候选，未最终定位航班查询 API；
      下一步应进入 client probe 或 network capture/replay 验证，而不是继续宽搜 bundle。
- [x] Browser owner 新增 page-context client probe 能力：
  - 输入 runtime global / object path / method name。
  - 在页面上下文中只读枚举对象 keys、方法列表、函数 arity 和 bounded source preview。
  - 失败时返回 missing segment / traversed path，指导模型先修正 client path，
    而不是继续宽搜。
  - 已落点：
    - `browser.runtime.probe_client`
    - owner action kind `runtime-probe-client`
    - `configured.browser` 的 `code_insight` 默认 schema
    - evidence ladder / snapshot affordance metadata / observation suggested tools /
      runtime contract
  - 保持 read-only；不自动调用 candidate endpoint，不写站点专用 dry-run。
	  - live validation `b68b251113ce431d807c30add99f17b5`：
	    - Context Tree included nodes 中包含 `tools.tool.browser.runtime.probe_client`
	      和 `tools.tool.browser.script.extract_request`。
	    - 模型实际调用了 `browser.script.extract_request` 与
	      `browser.runtime.probe_client`，验证 page-context probe 已进入执行链。
	    - 模型能沿 runtime/code/network 路径推进，但 run 在 14 步触发
	      `max_steps_exceeded`；直接失败点不是工具不可见，而是连续同类搜索和
	      request extraction 无 endpoint 后没有及时收口。
	  - live validation `8a67b1b5acf04c67b1fbc2623f340f21`：
	    - 新 network default surface 生效，provider mirror 中包含
	      `browser.network.get_response_body`、`browser.network.fetch_as_page`、
	      `browser.network.replay_request`。
	    - 模型实际完成 `extract_request -> start_capture -> runtime.probe_client ->
	      network.list_requests`，并产生 `orient`、`runtime_and_code`、
	      `network_truth` 证据路径。
	    - 仍在 10 步触发 `max_steps_exceeded`，说明 prompt-only stop rule 不足；
	      已转入 `evidence.frontier` 运行时诊断节点。
- [x] 让 `browser.network.start_capture` / `list_requests` 与 scripted probe 更紧密：
  - 当模型需要验证 API 路线时，优先 capture -> trigger/probe -> list -> get body。
  - `browser.observe(include_network_capture=true)` 不应成为唯一捕获入口。
  - 已落点：
    - `configured.browser` network group 的默认 schema 上限从 4 对齐到 6，
      保证 inspect/start/list/get_response_body/fetch_as_page/replay_request
      作为一条完整验证链进入默认工具面。
    - network group summary 明确 start capture -> trigger page action/runtime
      probe -> list filtered requests -> read body/replay。
    - `browser.network.start_capture` formatter 明确输出 capture id，并提示先触发
      page action/runtime probe，再调用 `browser.network.list_requests`。
- [x] Provider request / execution guide 增加停机策略：
  - 当已有 `network_truth` + `runtime_and_code` 且缺口明确时，模型应报告
    verified facts/gaps，而不是继续搜索同一 bundle。
  - 当连续 N 次 code/search/request-finder 返回同一 script_id/URL 时，下一步
    必须 inspect/evaluate/fetch/replay 或收口。
	  - 已落点：
	    - `runtime_contract.md` 明确 no-gain loop：连续两次 browser/code/network
	      probe 返回同一候选或同一缺口时，必须切换证据路径或报告 verified
	      facts/gaps。
	    - `execution.guide` 静态节点同步 no-gain loop 规则，并提升 guide revision。
	    - request extraction 无 endpoint 但返回 payload keys / client methods /
	      route hints 时，视为 partial evidence，下一步必须 client probe、
	      network capture/replay 或 final gap report，不能继续宽搜 bundle。
	    - `evidence.frontier` 下新增 Context Workspace 诊断节点：
	      `browser.network_capture_no_requests`、
	      `browser.endpoint_candidate_not_escalated`、
	      `browser.same_probe_repeated`。这些节点来自当前 session 的 browser
	      tool interaction 序列，用于下一轮 prompt surface 强制暴露空转风险。
- [ ] Operations/Trace 展示 browser evidence path ladder 和重复工具循环告警：
  - `same_tool_repetition`
  - `same_script_candidate_repetition`
  - `candidate_not_escalated`
  - `evidence_path_no_terminal_fact`

## 数据和事件

新增或强化事件：

```text
context_workspace.prompt_surface.built
context_workspace.tool_schema.bootstrap_applied
context_workspace.tool_schema.bootstrap_skipped
context_workspace.tool_result.envelope_created
orchestration.tool_batch.resource_policy_applied
browser.investigation.path_switched
browser.result.large_payload_folded
```

Operations read model 应支持：

- prompt surface budget。
- mirrored tool schema count / skipped count。
- tool result envelope / raw payload fold count。
- plan update count。
- browser route path：DOM / form / network / runtime / script / storage。
- browser serial group wait / execution time。

## 验证命令

按改动范围执行：

```bash
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_root_nodes.py tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tool_adapter.py::test_browser_source_prompt_groups_surface_in_context_tree
PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_prompt_transcript.py
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py tests/unit/test_orchestration_context.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py -k "preview or recorded_run_snapshot" tests/unit/test_turns_http.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_provider_request_builder.py::test_request_metadata_carries_budget_fields_from_snapshot_metadata tests/unit/test_orchestration_provider_request_builder.py::test_browser_investigation_affordance_flags_dom_form_only_schema_surface tests/unit/test_orchestration_provider_request_builder.py::test_browser_investigation_affordance_accepts_runtime_network_schema_surface
PYTHONPATH=src pytest -q tests/unit/test_browser_tool_http.py::BrowserToolHttpTestCase::test_browser_investigation_fixture_supports_runtime_script_network_route
PYTHONPATH=src pytest -q tests/unit/test_browser_playwright_runtime_actions.py::BrowserPlaywrightRuntimeActionsTestCase::test_network_inspect_returns_performance_entries_and_cdp_facts tests/unit/test_browser_playwright_runtime_actions.py::BrowserPlaywrightRuntimeActionsTestCase::test_network_inspect_summarizes_large_cdp_resource_tree
PYTHONPATH=src pytest -q tests/unit/test_browser_tool_application.py tests/unit/test_browser_observation.py
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py::test_session_adapter_projects_current_run_evidence_ledger_from_tool_results tests/unit/test_context_workspace_session_adapter.py::test_session_adapter_renders_tool_result_envelope_refs
PYTHONPATH=src pytest -q tests/unit/test_tool_background.py tests/unit/test_tool_submission_service.py
PYTHONPATH=src pytest -q tests/unit/test_operations_browser_read_model.py tests/unit/test_operations_tool_read_model.py
cd frontend && npm run typecheck && npm run build
```

新增验收测试建议：

```bash
PYTHONPATH=src pytest -q tests/unit/test_prompt_surface_tool_schema_policy.py
PYTHONPATH=src pytest -q tests/unit/test_tool_resource_policy.py
PYTHONPATH=src pytest -q tests/unit/test_browser_tool_http.py::BrowserToolHttpTestCase::test_browser_investigation_fixture_supports_runtime_script_network_route
PYTHONPATH=src pytest -q tests/integration/test_browser_investigation_route.py
```

2026-06-09 追加收口已执行：

```bash
PYTHONPATH=src pytest -q tests/unit/test_context_snapshot_metadata.py tests/unit/test_orchestration_provider_request_builder.py tests/unit/test_orchestration_context_workspace_snapshot.py::test_context_workspace_snapshot_metadata_locates_session_message_nodes tests/unit/test_orchestration_context_workspace_snapshot.py::test_context_workspace_adapter_records_tree_snapshot_for_run_prompt
PYTHONPATH=src pytest -q tests/unit/test_context_tree_tool.py tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_workspace_root_nodes.py tests/unit/test_context_snapshot_metadata.py tests/unit/test_orchestration_provider_request_builder.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_prompt_transcript.py tests/unit/test_context_workspace_session_adapter.py
PYTHONPATH=src pytest -q tests/unit/test_browser_observation.py tests/unit/test_app_assembly_targets.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_tool_providers.py
PYTHONPATH=src pytest -q tests/unit/test_browser_tool_http.py::BrowserToolHttpTestCase::test_browser_investigation_fixture_supports_runtime_script_network_route tests/unit/test_orchestration_provider_request_builder.py tests/unit/test_context_provider_mirror.py
PYTHONPATH=src pytest -q tests/unit/test_app_assembly_targets.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_browser_observation.py tests/unit/test_browser_tool_http.py tests/unit/test_tool_providers.py tests/unit/test_orchestration_provider_request_builder.py tests/unit/test_context_provider_mirror.py
PYTHONPATH=src pytest -q tests/unit/test_browser_playwright_runtime_actions.py tests/unit/test_browser_tool_http.py tests/unit/test_tool_providers.py tests/unit/test_context_workspace_root_nodes.py
PYTHONPATH=src pytest -q tests/unit/test_app_assembly_targets.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_browser_observation.py tests/unit/test_browser_tool_http.py tests/unit/test_browser_playwright_runtime_actions.py tests/unit/test_tool_providers.py tests/unit/test_orchestration_provider_request_builder.py tests/unit/test_context_provider_mirror.py tests/unit/test_context_workspace_root_nodes.py
PYTHONPATH=src pytest -q tests/unit/test_browser_playwright_runtime_actions.py tests/unit/test_browser_tool_http.py
PYTHONPATH=src pytest -q tests/unit/test_tool_providers.py tests/unit/test_app_assembly_targets.py tests/unit/test_context_workspace_tool_adapter.py
python -m py_compile src/crxzipple/modules/browser/infrastructure/script_insight.py tools/browser/local.py src/crxzipple/app/assembly/tool_sources/browser.py src/crxzipple/app/assembly/tool_handlers/browser.py
PYTHONPATH=src pytest -q tests/unit/test_context_provider_mirror.py tests/unit/test_orchestration_context_workspace_snapshot.py
PYTHONPATH=src pytest -q tests/unit/test_browser_observation.py tests/unit/test_app_assembly_targets.py tests/unit/test_context_workspace_tool_adapter.py
PYTHONPATH=src pytest -q tests/unit/test_browser_playwright_runtime_actions.py tests/unit/test_browser_tool_http.py tests/unit/test_tool_providers.py
python -m py_compile src/crxzipple/modules/browser/infrastructure/script_insight.py tools/browser/local.py src/crxzipple/app/assembly/tool_sources/browser.py src/crxzipple/app/assembly/tool_handlers/browser.py tests/unit/support.py
PYTHONPATH=src pytest -q tests/unit/test_browser_playwright_runtime_actions.py tests/unit/test_browser_tool_http.py
PYTHONPATH=src pytest -q tests/unit/test_tool_providers.py tests/unit/test_app_assembly_targets.py tests/unit/test_context_workspace_tool_adapter.py
PYTHONPATH=src pytest -q tests/unit/test_context_provider_mirror.py tests/unit/test_orchestration_context_workspace_snapshot.py
PYTHONPATH=src pytest -q tests/unit/test_browser_observation.py tests/unit/test_app_assembly_targets.py tests/unit/test_context_workspace_tool_adapter.py
cd frontend && npm run typecheck
cd frontend && npm run build
git diff --check
```

## 完成标准

- 最新 browser investigation run 的 provider tool schemas 默认包含 network/code/runtime starter。
- 同一 browser target 的 mutating tools 不会同批并发执行。
- `context_tree.update_plan` 不再在长链路中高频消耗执行步数。
- 大 browser result 不再以 100k+ chars 进入 direct transcript。
- Trace / Workbench 可直接看出模型当时看见了哪些工具、上下文和约束。
- Context Tree 中计划、环境、工具、执行约束、证据 frontier 都有显式节点。
- 不引入旧 prompt path、不新增 browser 专属 prompt 管线、不绕过 Context Workspace。

## 施工顺序

1. P1：先把 Prompt Tree 层级立住，尤其 `execution.guide`、`run.constraints`、`evidence.frontier`。
2. P2：接入 tool surface policy，让 browser network/code/runtime 进入默认 starter。
3. P4：加 tool resource policy，先解决 browser mutating 并行串扰。
4. P5：治理工具结果 envelope 和大结果折叠。
5. P6：降低 plan 工具高频消耗。
6. P7：补 UI / API 可观测性。
7. P8：用 browser route fixture 做回归验收。

这轮完成后，CRXZipple agent 不应再只像“网页点击操作员”，而应默认表现为能观察页面、分析运行时、
定位请求、验证事实并沉淀证据的工程执行 agent。
