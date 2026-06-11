# Browser Agent Workbench Upgrade Plan 2026-06-04

本文档是 Browser agent-facing 能力的新一轮施工入口。2026-06-03 的
Browser Agent Lab / DevTools 计划剩余未闭合项停止继续推进；本轮不再沿着旧清单补尾巴，
而是围绕最近真实会话暴露的问题重新收口：

- agent 想核验航司官网运价时，浏览器页面基础表单可见，但没有稳定完成搜索。
- `browser.type` / `browser.click` 返回成功，却没有证明页面业务状态已经改变。
- Browser module 已经具备部分 DevTools 能力，但最新会话实际可调用 schema 只有基础
  `navigate/tabs/click/type/snapshot/screenshot/evaluate`。
- `configured.browser` catalog / context tree / provider schema mirror 没把
  `browser.observe`、`browser.action.trace` 等高阶入口交付给 agent。
- Browser 相关大文件继续增长，后续迭代会越来越难由托管 agent 安全接手。

本轮目标不是“给模型加一段联想提示词”，而是把 Browser 从“能点网页的工具集合”升级为
“agent 可见、可调试、可验证、可沉淀的浏览器工作台”。

## 关系和取舍

当前施工依据：

- `AGENTS.md`
- `docs/README.md`
- `src/crxzipple/modules/browser/README.md`
- `docs/reports/browser-tool-source-profile-runtime-redesign-plan-20260525.md`
- `docs/reports/browser-profile-pool-multi-ip-collection-plan-20260526.md`
- `docs/reports/browser-agent-tooling-capability-upgrade-plan-20260528.md`
- 本文档

被本文 supersede：

- `docs/reports/browser-agent-lab-devtools-upgrade-plan-20260603.md`

2026-06-03 文档中已经落地并符合当前方向的代码可以保留；未闭合项不再逐项迁移。
如果某个旧项仍有价值，必须重新归入本文的目标结构、文件边界和验收标准后再施工。

## 设计结论

- Browser profile / pool / daemon / CDP endpoint 仍归 Browser module。
- Tool module 仍只拥有 Tool Source / Tool Function Catalog / Tool Run 生命周期。
- 默认 Browser Tool Source 仍只有 `configured.browser`；Browser profile 是运行上下文，
  不再生成 per-profile source。
- `cdp-raw` 保留为内部 debug/admin 逃生口，不进入普通 agent prompt surface。
- Agent 默认使用高阶工作台入口：`browser.observe` 和 `browser.action.trace`。
- DOM、Network、Runtime、Script、Storage 是可展开能力组，不是默认平铺给模型的全部工具。
- 工具执行成功不等于页面业务动作成功。Browser 工具返回必须区分 `tool_ok` 和
  `page_effect_ok`。
- 最终答复需要证据链：页面文本、URL、网络响应、表单状态、截图/trace artifact 或明确 blocker。

## 真实问题复盘

最近“核对昆航官网运价”会话暴露出三个层面的问题。

### 1. Browser 基础交互没有完全退化

最新 run 中，`browser.snapshot(format=interactive)` 已经给出表单 refs：

- 出发城市
- 到达城市
- 出发日期
- 搜索航班按钮

`browser.type` 和 `browser.click` 也返回成功。也就是说，底层并非完全看不到页面。

### 2. 页面业务状态没有被验证

昆航这类 SPA / 自定义控件页面，直接向可见输入框 `type` 不一定会写入内部状态。
城市可能必须从联想框选择，日期可能必须从日期控件选择。点击搜索后页面仍在首页，
说明“工具执行成功”没有转化成“搜索提交成功”。

当前工具返回过于贫瘠：

```text
Executed type via cdp-backed-playwright.
Executed click via cdp-backed-playwright.
```

它没有告诉 agent：

- 输入后的真实 DOM value 是什么。
- 内部 hidden state 是否变化。
- 点击后是否产生 XHR/fetch。
- URL / route / title 是否变化。
- 是否出现校验错误。
- 是否出现联想框或日期面板。
- 是否有 console/page error。

### 3. 高阶浏览器能力没有进入 prompt surface

代码里已经有 `browser.observe`、`browser.action.trace` 等入口声明和部分 handler，
但当前运行库中的 `tool_functions` 不包含这两个高阶入口。最新 LLM 调用只拿到 9 个基础
Browser schemas。DOM/Network 作为折叠 group 可见，但高阶诊断入口没有被自然交付。

因此 agent 没有展现“全面掌握浏览器状态后的能力增长”，不是因为这个方向不成立，
而是因为能力没有被稳定交付到它的工作台。

## 目标状态

```text
Agent
  -> context tree
      -> tools.bundle.configured.browser
          -> Browser Observation
              -> browser.observe
          -> Action Trace
              -> browser.action.trace
          -> Page Interaction
              -> browser.snapshot / click / type / evaluate / screenshot
          -> DOM Inspection
          -> Network Capture & Replay
          -> Code & Runtime Insight
          -> Storage & Workers
  -> browser tool run
      -> Tool module lifecycle
      -> Browser application service
      -> Browser infrastructure adapter
      -> Chromium / Chrome / Edge CDP + Playwright attach
```

Agent 执行网页核验任务时，理想路径是：

```text
open/list/select tab
observe page
trace one meaningful action
if effect missing:
  inspect form / DOM / overlay
  inspect network / script / runtime
  choose next interaction or page-context request
verify result against user goal
answer with evidence
```

## 非目标

- 不做航司或 OTA 专用 hard-coded 流程。
- 不建设规避验证码、风控、访问限制或付费墙的系统。
- 不把 raw CDP 作为普通 agent 主工具。
- 不让 Tool module 实现 Browser 业务逻辑。
- 不把完整 DOM、完整 bundle、完整 response body 默认塞进 prompt。
- 不为了旧 2026-06-03 文档未闭合项保留兼容 shim。

## Prompt Surface 与工具分层

默认 provider-callable schemas 应控制在低歧义、高收益入口。

默认启用：

- `browser.observe`
- `browser.action.trace`
- `browser.form.inspect`
- `browser.form.fill`
- `browser.overlay.observe`
- `browser.overlay.select`
- `browser.navigate`
- `browser.tabs.list`
- `browser.tabs.select`
- `browser.snapshot`
- `browser.click`
- `browser.type`
- `browser.evaluate`
- `browser.screenshot`

默认可见但折叠：

- `Navigation & Tabs`
- `Browser Observation`
- `Action Trace`
- `Page Interaction`
- `DOM Inspection`
- `Network Capture & Replay`
- `Code & Runtime Insight`
- `Storage & Workers`
- `Context Leases`
- `Environment Controls`

规则：

- `browser.observe` 是当前页总览入口。
- `browser.action.trace` 是关键页面动作入口，应优先替代裸 `click/type`。
- DOM / Network / Script / Runtime 只在需要时展开并 enable schema。
- 页面动作没有达到预期时，agent 不应直接总结失败，应先进入诊断路径。

## Tool Catalog 收口

### 当前问题

`src/crxzipple/app/assembly/tool.py` 同时承担：

- `configured.browser` source record。
- Browser prompt metadata。
- Browser function specs。
- Tool catalog reconcile。
- Browser runtime handler 注册。
- 其他 Tool assembly 逻辑。

这导致 catalog 漏项、prompt group 漏项、handler 漏项难以一起验收。

### 目标拆分

新增：

```text
src/crxzipple/app/assembly/tool_sources/
  __init__.py
  browser.py
  local_packages.py
  provider_backends.py

src/crxzipple/app/assembly/tool_handlers/
  __init__.py
  browser.py
  local_packages.py
  provider_backends.py
```

`tool_sources/browser.py` 负责：

- `_BROWSER_SOURCE_ID`
- Browser source record。
- Browser prompt metadata。
- Browser function catalog candidates。
- Browser source / function reconcile。
- Browser catalog migration helpers。

`tool_handlers/browser.py` 负责：

- Browser handler deps。
- `browser.observe` handler。
- `browser.action.trace` handler。
- DOM / Network / Storage / Script / Context handlers。
- handler map 注册。

`tool.py` 只保留组合根调用，不再内联 Browser catalog 和 40+ handler 声明。

### 验收

- `configured.browser` source config 包含所有目标 groups。
- `tool_functions` active/enabled 包含：
  - `browser.observe`
  - `browser.action.trace`
  - `browser.dom.inspect`
  - `browser.network.inspect`
  - `browser.network.start_capture`
  - `browser.network.list_requests`
  - `browser.network.get_request`
  - `browser.network.get_response_body`
  - `browser.network.get_request_body`
  - `browser.network.fetch_as_page`
  - `browser.network.replay_request`
  - `browser.runtime.inspect`
  - `browser.code.search`
  - `browser.script.list`
  - `browser.script.find_request`
  - `browser.script.inspect`
- Context tree 展开 `tools.bundle.configured.browser` 后显示目标 groups。
- 默认 prompt schema 包含高阶入口，不再只给 9 个基础工具。

## Browser Action Result 升级

### 当前问题

动作工具返回只说明 Playwright/CDP 动作执行成功，没有说明页面是否完成业务效果。

### 目标模型

所有状态动作返回统一结构：

```json
{
  "tool_ok": true,
  "page_effect_ok": false,
  "action": {
    "kind": "click",
    "target": {"ref": "r24", "selector": null}
  },
  "before": {
    "url": "...",
    "title": "...",
    "focused_element": "...",
    "visible_validation_text": []
  },
  "after": {
    "url": "...",
    "title": "...",
    "focused_element": "...",
    "visible_validation_text": ["出发城市不可以为空"]
  },
  "delta": {
    "url_changed": false,
    "title_changed": false,
    "dom_mutation_count": 3,
    "network_request_count": 0,
    "console_error_count": 0,
    "page_error_count": 0
  },
  "next_actions": [
    {
      "kind": "inspect_form",
      "reason": "visible text changed but no search request was emitted"
    }
  ]
}
```

### 必须区分

- `tool_ok=false`：工具本身失败，例如 target lost、ref stale、timeout。
- `tool_ok=true, page_effect_ok=false`：动作执行了，但页面没有达到可解释的业务效果。
- `tool_ok=true, page_effect_ok=unknown`：动作执行了，但未收集足够信号。
- `tool_ok=true, page_effect_ok=true`：动作执行且出现 URL/network/DOM/result 等正向证据。

## Browser Observe

`browser.observe` 是 agent 的默认观察入口。

输入：

- `target_id`
- `format`
- `active_overlay`
- `include_tabs`
- `include_console`
- `include_page_errors`
- `include_runtime`
- `include_resource_tree`
- `include_performance_metrics`
- `include_network_capture`
- `include_scripts`
- `limit`

输出：

- 当前 tab / title / url / readiness。
- Interactive refs。
- 当前 overlay refs。
- 表单摘要。
- 可见 validation / alert / toast。
- console 和 page error 摘要。
- runtime / resource tree 摘要。
- 最近 network capture 摘要。
- script/code hint 摘要。
- 推荐下一步诊断入口。

## Browser Action Trace

`browser.action.trace` 是关键交互入口。

流程：

```text
before observe
start bounded network capture
execute action
wait stabilization
after observe
compute effect delta
persist trace artifact when useful
return compact trace
```

支持 action：

- click
- type
- press
- fill
- select
- evaluate
- wait

返回：

- before / after observation。
- network delta。
- DOM mutation / URL / title delta。
- validation / toast / alert delta。
- console/page error delta。
- artifact link。
- next actions。

## Form / Overlay 能力

浏览器控件问题不应靠站点专用规则处理，而应建设通用能力。

新增或补齐：

- `browser.form.inspect`
- `browser.form.fill`
- `browser.overlay.observe`
- `browser.overlay.select`

`browser.form.inspect` 返回：

- field label。
- visible value。
- actual input value。
- hidden/state candidates。
- readonly/disabled/editable。
- associated overlay。
- event listeners。
- confidence。

`browser.form.fill` 策略：

- 普通 input：fill + input/change/blur。
- readonly/custom input：click -> overlay observe -> select candidate。
- 日期控件：优先选择可见日期项，失败再尝试 keyboard/input。

## DOM / Network / Script 能力

这些能力不默认平铺，但必须可展开且可用。

DOM：

- inspect ref/selector。
- box model。
- computed style。
- hit-test / clickability。
- event listener summary。
- mutation wait。

Network：

- start/stop/list capture。
- get request / request body / response body。
- fetch as page。
- replay request。
- action trace 关联 request delta。

Script / Runtime：

- runtime inspect。
- script list。
- code search。
- script inspect。
- find request。
- framework / route / location / store hint。

## 大文件理想拆分

### `src/crxzipple/app/assembly/tool.py`

当前约 3881 行。目标压到 800-1200 行以内。

拆分后：

```text
src/crxzipple/app/assembly/tool.py
  # Tool module assembly root only.

src/crxzipple/app/assembly/tool_sources/browser.py
  # configured.browser source + function specs + prompt metadata + reconcile.

src/crxzipple/app/assembly/tool_handlers/browser.py
  # Browser handler deps and handler registry.

src/crxzipple/app/assembly/tool_sources/local_packages.py
src/crxzipple/app/assembly/tool_handlers/local_packages.py

src/crxzipple/app/assembly/tool_sources/provider_backends.py
src/crxzipple/app/assembly/tool_handlers/provider_backends.py
```

规则：

- `tool.py` 不再保存 40+ browser spec。
- Browser source 和 handler 拆分后必须有单元测试锁边界。
- 不创建“legacy_browser.py”兼容层。

### `src/crxzipple/modules/browser/infrastructure/action_engines.py`

当前约 5932 行。目标压到 600-900 行。

拆分后：

```text
src/crxzipple/modules/browser/infrastructure/action_engine.py
  # CdpBackedPlaywrightActionEngine thin dispatcher.

src/crxzipple/modules/browser/infrastructure/action_dispatch.py
  # BrowserActionCommand kind -> service/action.

src/crxzipple/modules/browser/infrastructure/page_actions.py
  # click/type/press/fill/select/evaluate/screenshot.

src/crxzipple/modules/browser/infrastructure/snapshot_actions.py
  # text/interactive/role/accessibility snapshot.

src/crxzipple/modules/browser/infrastructure/snapshot_refs.py
  # ref generation, ref lookup, selector fallback, frame ref mapping.

src/crxzipple/modules/browser/infrastructure/frame_targets.py
  # target/page/frame resolution.

src/crxzipple/modules/browser/infrastructure/action_effects.py
  # before/after state, page_effect_ok, deltas, next_actions.

src/crxzipple/modules/browser/infrastructure/form_actions.py
  # form inspect/fill/submit and overlay selection.

src/crxzipple/modules/browser/infrastructure/result_payloads.py
  # normalized browser tool result envelopes.
```

保留并继续收口：

```text
src/crxzipple/modules/browser/infrastructure/dom_inspection.py
src/crxzipple/modules/browser/infrastructure/network_actions.py
src/crxzipple/modules/browser/infrastructure/network_insight.py
src/crxzipple/modules/browser/infrastructure/script_insight.py
src/crxzipple/modules/browser/infrastructure/storage_inspection.py
src/crxzipple/modules/browser/infrastructure/action_trace.py
```

规则：

- Engine 只调度，不内联复杂 JS 和 payload normalization。
- Snapshot/ref/form/action-effect 分别测试。
- 拆分过程中不保留旧 engine 双轨。

### 大测试拆分

当前大测试：

- `tests/unit/test_browser_playwright_actions.py`
- `tests/unit/test_browser_tool_http.py`
- `tests/unit/test_tool_providers.py`

目标拆分：

```text
tests/unit/test_browser_action_engine_dispatch.py
tests/unit/test_browser_page_actions.py
tests/unit/test_browser_snapshot_refs.py
tests/unit/test_browser_action_effects.py
tests/unit/test_browser_action_trace.py
tests/unit/test_browser_form_actions.py
tests/unit/test_browser_network_actions.py
tests/unit/test_browser_prompt_catalog.py
tests/unit/test_browser_context_tree_surface.py
```

## 施工阶段

### Phase 0: 关闭旧计划并建立入口

- [x] 标记 2026-06-03 文档为 superseded。
- [x] 新增本文档。
- [x] 更新 `docs/README.md`，把本文作为 active Browser 施工入口。
- [x] 后续任务不再引用 2026-06-03 未闭合 checklist。

### Phase 1: Catalog / Prompt Surface 修复

- [x] 拆出 `tool_sources/browser.py`。
- [x] 拆出 `tool_handlers/browser.py`。
- [x] 修复 Browser source reconcile 代码路径，确保高阶工具进入 candidates 并参与 source upsert。
- [x] 补 `configured.browser` prompt groups：`observation`、`action_trace`、`code_insight`。
- [x] 让 context tree 展开 Browser source 后显示完整 group。
  - 2026-06-04: `test_browser_source_prompt_groups_surface_in_context_tree` 使用真实 `configured.browser` catalog candidates 与 prompt groups 验证树上先显示 12 个 group，展开 group 后才显示 `browser.observe` / `browser.action.trace` 等 function。
  - 2026-06-05: context prompt render 改为只以 `_tree_prompt_visible_nodes` 作为裁剪口，避免 provider schema mirror 已包含 Browser function、但 XML 正文漏掉 Browser source/group 摘要的错位。
- [x] 默认 enable 高阶工具 schemas。
  - 2026-06-04: Browser observation/action_trace group 展开后，`browser.observe` 与 `browser.action.trace` function 节点默认 `schema_enabled=True`，render 后进入 provider `tool_schemas` attachments。
- [x] 写 catalog / prompt surface 回归测试。
- [x] 在本地 dev stack 运行 activation/reconcile，确认 Postgres `tool_functions` 已写入高阶工具。

### Phase 2: Action Result Envelope

- [x] 定义 Browser action result envelope。
- [x] `click/type/fill/select/press/evaluate` 返回轻量 `tool_ok` / `page_effect_ok`。
- [x] `navigate` 返回轻量 `tool_ok` / `page_effect_ok`。
- [x] `browser.action.trace` 返回统一 `action_envelope`，把 network / lifecycle /
      storage / snapshot / console / page-error 信号收敛为 `page_effect_ok` 和
      `next_action`。
- [x] 增加 before/after URL/title/focus/validation/network/console/page-error delta。
  - 2026-06-05: `browser.action.trace` 已输出 before/after snapshot diff、network capture delta、console/page-error delta、storage delta 和 lifecycle delta；lifecycle payload 覆盖 URL/title/ready_state/visibility/focus/history/online，formatter 已把这些信号合并进 agent-facing trace result。
- [x] 为普通 action / navigate envelope 做 HTTP/tool message serializer，让 agent 可见
      `tool_ok`、`page_effect_ok` 和下一步诊断建议。
- [x] 为 `browser.action.trace` formatter 显示 Page effect。
- [x] 补普通动作 action effect 单元测试。
- [x] 补 navigate / serializer 基础单元测试。
- [x] 补 `browser.action.trace` envelope 单元测试。
- [x] 补 deep delta 单元测试。
  - 2026-06-05: `test_action_trace_summarizes_script_initiated_network_delta`、`test_action_trace_summarizes_storage_and_lifecycle_delta`、`test_action_trace_reports_action_error_without_losing_after_state`、`test_action_trace_does_not_count_background_network_when_locator_is_ambiguous` 覆盖 network/script、storage/lifecycle、失败后 after state 和背景网络误判回归。

### Phase 3: Observe / Action Trace 产品化

- [x] `browser.observe` 输出 compact workbench guidance：根据 refs、network capture、
      code/runtime、errors 生成 `next_action` 和 `suggested_tools`。
- [x] 完成 `browser.observe` 更完整的 compact 输出分层。
  - 2026-06-04: `browser.observe` agent-facing formatter 已分层展示 page/tabs/frames/interaction/form/overlay/runtime/network/code/snapshot，并在 form/overlay/top guidance 中展示 suggested tools 与 evidence path。
- [x] 完成 `browser.action.trace` before/after + network delta + next_actions。
  - 2026-06-04: `browser.action.trace` agent-facing formatter 已展示 before/after snapshot、network/console/page-error/storage/lifecycle delta、Next、Suggested tools 与 Evidence path；缺顶层 recommendation 时可从 action envelope 兜底。
- [x] trace artifact 持久化。
  - 2026-06-04: `browser.action.trace` handler 注入 artifact service 时会生成 `application/json` file ref artifact，metadata 标注 `source=browser`、`attachment_kind=action-trace`、`trace_id`；`test_browser_action_trace_handler_normalizes_wrapped_action_payload` 已覆盖。
- [x] 工具说明和 context tree summary 中明确使用方式。
  - 2026-06-04: `configured.browser` prompt metadata 与 `browser.observe` / `browser.action.trace` function description 已明确 observe-first、trace-action、inspect-DOM/runtime/network/scripts 的 browser workbench 流程。
- [x] 补 observe/action trace guidance / envelope 回归测试。

### Phase 4: Form / Overlay 通用能力

- [x] 新增只读 `browser.form.inspect`，复用 Browser observation 并输出 fields/actions/candidates。
- [x] 新增 `browser.form.fill`，作为 action trace 的表单填充入口并返回页面效果证据。
- [x] 新增只读 `browser.overlay.observe`，复用 active overlay snapshot 并输出 candidates。
- [x] 新增 `browser.overlay.select`，作为 active overlay 候选选择入口并返回页面效果证据。
- [x] 初步支持 readonly/custom input：普通 fill 不可用时可触发控件并选择匹配 overlay 候选。
- [x] 初步支持 autocomplete / date picker / select-like overlay 的候选观察。
- [x] 补 form / overlay observation 与 handler 映射回归测试。
- [x] 补 readonly/custom input overlay fallback 与 action trace 回归测试。
- [x] 补更完整的 SPA 表单动作模拟页测试：readonly city controls -> overlay candidate selection -> search click network delta。

### Phase 5: DOM / Network / Script Deep Tools 收口

- [x] DOM inspection 使用 CDP/Playwright 能力返回 clickability/event listener evidence。
  - 2026-06-04: `browser.dom.*` inspection 在 ref 带 `backendNodeId` 时读取 `DOMDebugger.getEventListeners`，并把 bounded listener evidence 合并到 `event_summary`。
- [x] Network capture 与 action trace 关联。
  - 2026-06-04: `action-trace` 创建的 network capture 写入 `trace_id`、wrapped action kind 和 action target metadata；返回结构继续保留 request causality / script initiator summary。
- [x] `fetch_as_page` / `replay_request` 返回安全提示和 replay suitability。
  - 2026-06-04: `network-fetch-as-page` 返回 `fetch_safety` / `response_summary`；`network-replay-request` 已返回 `replay_suitability` / `request_diff` / `response_summary`，tool 文本摘要展示关键 gate。
- [x] Runtime/script insight 只返回 bounded snippets。
  - 2026-06-04: `runtime-inspect`、`code-search`、`script-find-request`、`script-inspect` 均保留数量/上下文/字符上限；长 `script-inspect.source_preview` 不进入 top-level content。
- [x] 大 body / 大 script 写 artifact，不默认塞 prompt。
  - 2026-06-04: `network-fetch-as-page` / `network-replay-request` 默认只返回 `body_preview`，完整 body 需显式 `include_body=true`；tool adapter 对大 network body 和大 script preview 生成 artifact，并从 details 移除大字段。

### Phase 6: 大文件拆分

- [x] 拆出 `app/assembly/tool.py` 中的 Browser source / handler assembly。
- [x] 继续拆 `app/assembly/tool.py` 中的 local package / provider backend assembly，使文件压到目标范围。
  - 2026-06-04: package activation 已拆到 `app/assembly/tool_packages.py`，configured provider source/runtime activation 已拆到 `app/assembly/tool_sources/configured_providers.py`，cleanup/runtime activator 已拆到 `app/assembly/tool_runtime.py`；`tool.py` 从 1431 行降到 722 行。
- [x] 拆 `browser/infrastructure/action_engines.py`。
  - 2026-06-04: Browser-side JS marker/expression 常量已拆到 `browser/infrastructure/action_engine_scripts.py`；payload/batch/action-result/CDP-session helper 已拆到 `browser/infrastructure/action_engine_payloads.py`；snapshot/frame/interactive-ref helper 已拆到 `browser/infrastructure/action_engine_snapshots.py`；locator/overlay payload helper 已拆到 `browser/infrastructure/action_engine_locators.py`；snapshot/ref 执行方法已拆到 `browser/infrastructure/action_engine_snapshot_runner.py`，并删除未引用 bulk-select helper；`action_engines.py` 从 6296 行降到 2656 行。
- [x] 拆 browser 大测试。
  - 2026-06-04: `test_browser_playwright_actions.py` 已拆为公共 `browser_playwright_action_support.py` 与 core/action-trace、runtime/devtools、locator/wait、snapshot/ref 四组测试；最大单文件从 5118 行降到 1732 行。
- [x] 删除旧 import 路径和无用 shim。
  - 2026-06-04: 定向扫描 browser/tool assembly 路径后未发现本轮拆分遗留 active shim；旧 browser MCP/profile 相关内容仅保留迁移测试、404 守卫和已退役状态提示。
- [x] Browser source / handler 拆分范围的 `ruff` / `py_compile` / focused pytest 通过。
- [x] Tool package/provider 拆分范围的 `ruff` / architecture pytest 通过。
- [x] Browser action script 拆分范围的 `ruff` / `py_compile` / focused pytest 通过。
- [x] Browser action payload/helper 拆分范围的 `ruff` / `py_compile` / focused pytest 通过。
- [x] Browser action snapshot/helper 拆分范围的 `ruff` / `py_compile` / focused pytest 通过。
- [x] Browser action locator/helper 拆分范围的 `ruff` / `py_compile` / focused pytest 通过。
- [x] Browser action snapshot runner 拆分范围的 `ruff` / `py_compile` / browser pytest 通过。
- [x] Browser action 大测试拆分范围的 `ruff` / `py_compile` / focused pytest 通过。

### Phase 7: 端到端验收

- [x] 本地 dev stack 能启动。
  - 2026-06-04: `bash scripts/dev/down-redis-stack.sh && make dev-up` 完成；API `http://127.0.0.1:8000/health` 返回 ok，Frontend `http://127.0.0.1:4173/` 返回 200，daemon supervisor 正常运行。
- [x] Browser operations 页面不回退。
  - 2026-06-04: `frontend/scripts/audit_operations_layout.py` 默认模块列表已纳入 `browser`；`npm run audit:operations-layout -- --base-url http://127.0.0.1:4173 --modules browser --warn-only` 通过，报告写入 `tmp/operations-layout-audit/report.json`。
- [x] Browser settings 页面不回退。
  - 2026-06-05: `http://127.0.0.1:4173/settings/browser-profiles` Playwright layout scan 通过，`bodyScrollX=0`、`bodyScrollY=0`；中文标题从“浏览器画像”收为“浏览器 Profile”；`cd frontend && npm run typecheck` 通过。
- [x] `configured.browser` 只有一个 source。
  - 2026-06-04: 直连 `GET /tools/sources` 返回 `configured_browser_count=1`；`GET /tools/functions?source_id=configured.browser` 返回 61 个 browser functions。
- [x] Agent 能通过 context tree 看见 Browser groups。
  - 2026-06-04: `tests/unit/test_context_workspace_tool_adapter.py` 已覆盖 `tools.bundle.configured.browser` 展开后的 Browser group 节点与高阶工具 schema。
  - 2026-06-05: 同一测试补充验证 workspace 初始 prompt 已包含 `configured.browser` source handle 摘要；展开 `Browser Observation` / `Action Trace` 后，group summary 会进入 prompt XML 正文，且 `browser.observe` / `browser.action.trace` 同步进入 provider `tool_schemas`。
- [x] Agent 能通过 Browser tools 完成基础真实网页任务。
  - 2026-06-05: 本地 dev stack 重启后，通过 `POST /turns` 提交 `https://example.com` 标题检查任务，run `f8e7d5fadca04ae3a6f01b78937c21d4` 在 5 步内完成：`context_tree.expand(configured.browser)` -> `context_tree.expand(navigation)` -> `browser.navigate` -> `browser.tabs.list` -> final answer。`context_tree.expand` 结果已提示当前 mirrored schema，避免了重复 `enable_tool_schema` 的预算浪费。
- [x] Agent 能用 `browser.observe` 开始真实网页任务。
  - 2026-06-05: LLM adapter 短暂断连后恢复；run `f73d95f383ab4cd7a6326e3c213a8769` 在 7 步内完成 `https://example.com` 交互链接读取任务，调用序列包含 `browser.navigate` -> `context_tree.expand(observation)` -> `browser.observe`，最终回答 `Learn more` / `https://www.iana.org/domains/example`。
- [x] `browser.observe` / `browser.action.trace` Tool API 能产出证据化页面状态。
  - 2026-06-05: 直连 Tool API 验证 `browser.observe` 返回 `r1: link "Learn more"`、recommended `browser.action.trace` / DOM inspection；`browser.action.trace` 点击该 ref 后返回 before/after snapshot、network/script initiator、lifecycle delta 与 suggested follow-up tools。
- [x] `browser.action.trace` 区分动作失败和页面效果。
  - 2026-06-05: 修复 `action-trace` envelope，不再用 `tool_ok` 遮蔽页面变化；当 click/navigation wait 报错但 URL/title/snapshot/network 已变化时，`page_effect_status=action_failed_with_observed_effect`，formatter 输出 `observed change (action reported failure)`，并建议从 after snapshot 继续。
- [x] `context_tree.expand` 直接披露加载出的子 handles。
  - 2026-06-05: `context_tree.expand` 结果增加 `loaded_child_handles` 与文本列表，展开 browser source 后可直接看到 `navigation` / `observation` / `action_trace` 等 group id，减少 agent 额外调用 `context_tree.list` 的概率。
- [x] Agent 能使用 `browser.action.trace` 完成证据化跳转判断。
  - 2026-06-05: run `e5e1920dc664448497b87db225f3f876` 先展开 `configured.browser`、`navigation`、`observation`、`action_trace`，随后执行 `browser.navigate` -> `browser.observe` -> `browser.action.trace`。最终答复引用 before/after snapshot、lifecycle delta 与 network 证据，判断 `Learn more` 从 `https://example.com/` 跳转到 `https://www.iana.org/help/example-domains`。
- [x] Browser function schema 不再诱导 agent 传入不存在的 `profile: default`。
  - 2026-06-05: `profile` 参数文案改为普通任务应省略，仅在用户明确要求时传具体已配置 profile，并明确 `'default' is not a profile name`。run `4bf69243f9c74692a975fa79d93bca99` 的 prompt preview 显示 agent 已不再传 `profile: default`，`browser.navigate` 与 `browser.observe` 成功走系统默认 profile。
- [x] 无效 Browser ref 错误不再被误判为 profile readiness 问题。
  - 2026-06-05: 直连 Tool API 对 `browser.action.trace(ref=r999)` 的错误从 `Next: use-profile with profile 'crxzipple'` 修正为 `run browser.observe ... retry ... fresh ref`，并提示 `browser.dom.clickability` / `browser.dom.inspect`。
- [x] Agent 在动作无效时使用 `browser.action.trace` 或 DOM/Network 继续调查。
  - 2026-06-05: 已两次提交 agent-level recovery run（`43de05f7471e4c3993fb9f4c8fefbb8f`、`4bf69243f9c74692a975fa79d93bca99`），均被外部 LLM provider `servers are currently overloaded` 打断；第二次已确认失败前完成 browser source/group 展开、navigate、observe，且不再出现 `profile: default`。
  - 2026-06-05: 第三次 run `6da1434620fe4bcfb5822864d241f5a8` 完整通过。执行链为 `browser.navigate` -> `browser.observe` -> `browser.action.trace(ref=r999)` -> `browser.action.trace(ref=r1)`；无效 ref 返回 `inspect-target`、fresh ref / clickability guidance，agent 未停止。随后正确 ref 的 click 出现 timeout，但 action trace 标记 `observed change (action reported failure)`，agent 根据 before/after snapshot、lifecycle 与 network 判断最终跳转成功。
- [x] 航司官网类任务能够给出证据化 blocker 或完成核价。
  - 2026-06-05: run `90016c59bf924d6294c4824c5d275506` 首次验证东航官网，完成 `browser.observe` 与 `browser.action.trace`，但暴露出 action trace 把 ref 失效后的背景埋点请求误判成页面效果的问题。
  - 2026-06-05: 修复 action trace observable-effect 判定：`Browser ref not found/stale/unsupported locator` 等“动作未落到页面”的错误不再把 network-only 背景请求算作页面效果。直连 Tool API 验证东航页 `r17` 失效时输出 `Page effect: no observable change`、`Next: inspect-target`，即使捕到 `tingyun` 埋点请求也不误判。
  - 2026-06-05: run `73b0005a72e84609a405db2b337da5d0` 重新验证航司官网类任务，agent 未完成核价，但给出合格 blocker：页面 `https://www.ceair.com/zh/cny/home` 已加载，observe 暴露 `r19/r20` 出发/到达输入框，但 action trace 点击 `r19` 时 ref 已失效；before/after snapshot 一致，`Snapshot changed: no`、`Lifecycle delta: 0`、`Network: 0 request(s)`、`Console/Page error delta: 0`，结论为表单 ref 生命周期不稳定，需要刷新 refs 或进入 DOM/clickability/selector 诊断。
  - 2026-06-05: 进一步定位 ref 失效根因：`action.trace` 在执行前会重新拍 before snapshot，并按 `snapshot_limit` 覆盖 tab refs；当 observe 暴露 `r19` 但 trace 传入 `snapshot_limit=12` 时，trace 自己把目标 ref 冲掉。已修复为 action trace 的目标 ref 序号高于显式 `snapshot_limit` 时自动提升 trace snapshot limit。单元测试 `test_action_trace_preserves_high_ref_when_snapshot_limit_is_smaller` 覆盖 `r19 + snapshot_limit 12` 仍可点击目标。
  - 2026-06-05: 继续修复 action trace 的 ref 状态链：内部 before/after snapshot 现在会同步 `runtime_state.current_ref_generation`，避免刚刷新的 refs 被误判为 stale；若 trace 前已有同 ref 的精确 selector/backend/uid，before snapshot 只生成 role-only ref 时会把精确 locator 合并回目标 ref。当前代 ref 也优先使用 selector/backend，再退回语义 role。单元测试 `test_action_trace_preserves_precise_ref_locator_when_before_snapshot_is_role_only` 覆盖同名输入框 strict-mode 场景。
  - 2026-06-05: 真实 Tool API 复测东航首页通过：`browser.observe(limit=80)` 暴露 27 refs，`browser.action.trace(action_ref=r19, snapshot_limit=12)` 自动提升 before snapshot 到 27 refs，resolved selector 为 `role=textbox[name="出发"][nth=0]`，动作成功并展开候选态，after snapshot 增至 31 refs。另补 `test_action_trace_does_not_count_background_network_when_locator_is_ambiguous`，strict-mode/ambiguous locator 失败时不再把 `tingyun` 等背景请求算作页面效果。

## 验收命令

按阶段选择：

```bash
PYTHONPATH=src pytest -q tests/unit/test_tool_providers.py
PYTHONPATH=src pytest -q tests/unit/test_app_assembly_targets.py::test_browser_function_catalog_uses_profile_context_not_profile_ids
PYTHONPATH=src pytest -q tests/unit/test_browser_observation.py
PYTHONPATH=src pytest -q tests/unit/test_browser_playwright_actions.py
PYTHONPATH=src pytest -q tests/unit/test_browser_tool_http.py
PYTHONPATH=src pytest -q tests/unit/test_browser_tool_http_runtime.py
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tool_adapter.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py
```

前端相关：

```bash
cd frontend
npm run typecheck
npm run build
```

运行态检查：

```bash
make dev-up
source scripts/dev/infra-env.sh
python -m crxzipple.main db upgrade head
python -m crxzipple.main daemon status
```

## 完成定义

本轮完成时应满足：

- 2026-06-03 Browser Agent Lab 尾项不再作为 active 待办。
- `configured.browser` catalog、prompt tree、provider schema 三层一致。
- 高阶 Browser tools 稳定进入 agent 工作台。
- 动作工具返回可解释的页面效果，而不是只返回“执行成功”。
- Browser 大文件完成实质拆分，后续 agent 能按文件边界安全施工。
- 真实网页任务失败时，agent 能说明失败原因和证据，而不是泛泛说“页面不可操作”。
