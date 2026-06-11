# Browser Agent Lab / DevTools Upgrade Plan 2026-06-03

> Status: Superseded on 2026-06-04.
>
> 本文档剩余未闭合项不再继续施工。2026-06-03 这一轮的主要价值是确认
> Browser module 应面向 agent 暴露 DevTools 能力，而不是重造浏览器调试器；
> 但后续执行中发现它仍以“补能力清单”为主，无法充分解决 agent 在真实网页任务中
> 的工具可见性、动作反馈、prompt surface 和大文件治理问题。
>
> 后续以
> [browser-agent-workbench-upgrade-plan-20260604.md](browser-agent-workbench-upgrade-plan-20260604.md)
> 为当前施工入口。托管 agent 不应继续追本文尾项，也不应把本文中未完成的
> checklist 当作必须兼容的历史包袱。

本文档定义 Browser module 的下一轮升级方案。目标不是重新实现浏览器调试器，也不是把
CDP 原样暴露给 agent，而是把 Chromium / Chrome / Edge 已经提供的 DevTools 能力整理成
agent 可稳定使用、可审计、可沉淀经验的浏览器实验室。

本文接续：

- `browser-tool-source-profile-runtime-redesign-plan-20260525.md`
- `browser-profile-pool-multi-ip-collection-plan-20260526.md`
- `browser-agent-tooling-capability-upgrade-plan-20260528.md`
- `src/crxzipple/modules/browser/README.md`

后续施工以本文和 `AGENTS.md` 为准。旧 Browser MCP / per-profile source 路径不恢复。

## 设计结论

- 底层调试能力属于 Chromium 系浏览器，通过 Chrome DevTools Protocol 提供。
- Browser module 不发明调试器，只负责接入原生 DevTools 域，并提供 agent-friendly
  application surface。
- Agent 默认不直接使用 raw CDP；`cdp-raw` 继续只作为内部 debug/admin 逃生口。
- Tool module 不实现浏览器逻辑，只把 Browser application surface 暴露成 `browser.*`
  tool functions。
- Skill / Memory 不持有浏览器 runtime。Browser 探索 trace 可以生成 recipe draft，
  再由 Skills / Memory owner 决定是否沉淀。
- DOM/ref 不是最终目标。DOM 是人类 UI 的渲染结果；agent 更需要页面运行现场：
  interaction graph、network、script、runtime state、storage、console、trace。

## 当前审查结论

当前 Browser module 方向基本正确，但 agent 使用面仍不达标。

已经达标：

- Browser profile / pool / daemon / CDP 边界清晰。
- 默认 Browser Tool Source 只有 `configured.browser`。
- Browser MCP 不在默认路径。
- Tool 通过 Browser application port 调用，不直接拼 CDP endpoint。
- `cdp-raw` 已在 public facade 被阻断。
- Network、IndexedDB、CacheStorage、Performance、Page navigation history 等已经主要接
  原生 CDP 域。

尚未达标：

- 工具面仍是底层动作平铺，agent 要自己组合 snapshot、DOM、network、storage、trace。
- Interaction refs 仍偏 selector / text / role 包装，缺少 `backendNodeId`、bbox、
  hit-test、event listener、network trigger、confidence 等证据。
- DOM/交互识别主要依赖自写 JS + Playwright locator，未充分使用 `DOMSnapshot`、
  `DOMDebugger`、`DOM.getNodeForLocation`、`Accessibility`。
- Network capture/replay 和动作之间没有因果绑定，不能直接回答“点了这个按钮以后发生了
  什么”。
- 没有 script/code 分析面，agent 不能稳定搜索 bundle、接口字符串、handler、source map。
- Playwright trace 偏诊断资产，不是 agent 任务级 action trace。
- 没有 recipe draft / skill authoring 闭环。

## 目标

把 Browser 从“网页自动化工具集合”升级成“agent 浏览器实验室”：

```text
Agent
  -> browser.observe
  -> browser.interaction.inspect_ref
  -> browser.action.trace
  -> browser.network.inspect / replay
  -> browser.code.search / script.inspect
  -> browser.runtime.inspect
      -> Browser application services
          -> CDP domains / Playwright attach / daemon profile pool
              -> Chrome / Edge / Chromium
```

Agent 应能完成：

- 观察页面当前运行状态，而不是只读 DOM。
- 得到带证据的可交互 ref。
- 对一次动作获得 before/after 因果 trace。
- 分析网络请求、请求参数、响应摘要、initiator。
- 搜索页面脚本，找到接口、handler、route/store 线索。
- 用当前浏览器 session 做 page-context fetch 或 request replay。
- 将稳定探索路径整理成 recipe draft，并交给 Skill/Memory 沉淀。

## 非目标

- 不建设规避网站风控、验证码、限流或访问控制的系统。
- 不把 raw CDP 作为普通 agent 的主工具。
- 不为了某个 MCP browser server 恢复 per-profile tool source。
- 不让 Browser module 持有 Skill catalog 或 Memory truth。
- 不让 Tool module 实现 DOM、Network、Debugger、Storage 逻辑。
- 不把完整 DOM、完整 bundle、完整 response body 默认塞进 LLM prompt。

## 模块边界

### Browser Module

Browser module 负责：

- Browser profile / pool / allocation / runtime state。
- Daemon-managed CDP endpoint 的使用和 readiness。
- DevTools protocol adapter。
- Page observation、interaction graph、network insight、script insight、runtime inspect。
- Action trace 和 browser recipe draft。
- Browser-specific events、operations facts、安全脱敏。

Browser module 不负责：

- Tool source discovery / tool run lifecycle。
- Skill package 持久化。
- Memory 长期事实持久化。
- Orchestration run 推进。

### Tool Module

Tool module 负责：

- 注册 `configured.browser` source。
- 注册稳定的 `browser.*` function catalog。
- Tool run lifecycle、queue、worker、approval、artifact。
- 把 ToolExecutionContext 中的 profile/pool/session/run 信息传入 Browser application。

Tool module 不负责：

- 拼 CDP method。
- 读取 browser runtime 文件。
- 解析 browser profile/pool。
- 实现 network capture / script search / interaction graph。

### Skills / Memory

Skills 负责：

- 保存、校验、发布 agent 可复用的浏览器 recipe/skill。
- 提供 skill authoring 审批和 package truth。

Memory 负责：

- 保存跨会话事实性经验，例如某站点接口字段、页面结构注意事项。
- 不保存 browser runtime target、CDP endpoint、raw secret。

Browser recipe draft 只是一份候选经验，不自动成为 skill 或 memory。

### Operations

Operations 负责观察：

- Profile / pool / allocation readiness。
- 当前 target / page freshness。
- Recent observations。
- Action traces。
- Network captures。
- Failed browser actions。
- Ref confidence / evidence 分布。

Operations 不决策 browser runtime，不拼 owner module API，不绕过 `/operations/browser`。

## 原生 DevTools 能力接入

Browser module 应优先使用原生 DevTools 域，不自己造同等调试能力。

### DOM / Interaction

使用：

- `DOMSnapshot.captureSnapshot`
- `DOM.getDocument`
- `DOM.querySelector`
- `DOM.resolveNode`
- `DOM.describeNode`
- `DOM.getBoxModel`
- `DOM.getNodeForLocation`
- `DOMDebugger.getEventListeners`
- `Runtime.callFunctionOn`
- 可选 `Accessibility.getFullAXTree`

目标：

- 生成 interaction graph。
- 给 ref 建立证据链。
- 判断可见、遮挡、命中、disabled、readonly、editable。
- 找到事件监听和事件委托链。
- 对 SPA div/span/li 控件不再只靠 class 猜测。

### Network

使用：

- `Network.enable`
- `Network.requestWillBeSent`
- `Network.responseReceived`
- `Network.loadingFinished`
- `Network.loadingFailed`
- `Network.getResponseBody`
- `Network.getRequestPostData`

目标：

- 捕获请求和响应。
- 记录 initiator、frame、loader、timing。
- 读取 request / response body。
- 关联 action trace。
- 支持 page-context fetch 和 request replay。

### Runtime / Script

使用：

- `Runtime.evaluate`
- `Runtime.callFunctionOn`
- `Runtime.getProperties`
- `Debugger.enable`
- `Debugger.scriptParsed`
- `Debugger.getScriptSource`

目标：

- 搜索脚本中的接口字符串、route、关键函数、状态名。
- 读取脚本片段，不默认吐完整 bundle。
- 分析 event handler、initiator stack 和 source map 线索。
- 支持只读 runtime inspect。

### Storage / Worker

使用：

- `Storage.getCookies`
- `IndexedDB.requestDatabaseNames`
- `IndexedDB.requestDatabase`
- `IndexedDB.requestData`
- `CacheStorage.requestCacheNames`
- `CacheStorage.requestEntries`
- `CacheStorage.requestCachedResponse`
- `ServiceWorker.enable`

目标：

- 提供登录态和缓存状态摘要。
- 支持 IndexedDB / CacheStorage 查询。
- 识别 service worker 对请求的影响。
- 对 secret/cookie/token 默认脱敏。

### Page / Diagnostics

使用：

- `Page.getFrameTree`
- `Page.getNavigationHistory`
- `Page.lifecycleEvent`
- `Performance.getMetrics`
- `Tracing`

目标：

- 页面生命周期、frame 结构、导航历史、性能指标。
- 诊断型 trace 保留，任务级 action trace 单独建设。

## 新增 Application Services

建议新增到 `src/crxzipple/modules/browser/application`：

```text
BrowserDevtoolsAdapter
BrowserObservationService
BrowserInteractionGraphService
BrowserDomInspectionService
BrowserActionTraceService
BrowserNetworkInsightService
BrowserScriptInsightService
BrowserRuntimeInspectService
BrowserRecipeDraftService
```

### BrowserDevtoolsAdapter

职责：

- 统一封装 CDP session command / subscription。
- 提供小而稳定的 domain methods。
- 处理 target/frame/session 错误。
- 做 payload size limit 和 JSON-safe normalization。

规则：

- 不在 `action_engines.py` 继续堆大型 CDP 逻辑。
- Adapter 是 Browser infrastructure 能力，application service 通过 port 使用。
- raw CDP method 不进入普通 agent 工具面。

### BrowserObservationService

输入：

```python
BrowserObserveRequest(
    profile_name: str,
    target_id: str | None,
    scope: Literal["summary", "full"] = "summary",
    include_interactions: bool = True,
    include_network: bool = True,
    include_console: bool = True,
    include_storage: bool = False,
    include_scripts: bool = False,
)
```

输出：

```python
BrowserObservation(
    profile_name: str,
    target_id: str,
    page: BrowserPageState,
    frames: tuple[BrowserFrameState, ...],
    interactions: BrowserInteractionGraph | None,
    network: BrowserNetworkSummary | None,
    console: BrowserConsoleSummary | None,
    storage: BrowserStorageSummary | None,
    scripts: BrowserScriptSummary | None,
    errors: tuple[BrowserObservationError, ...],
)
```

输出原则：

- 默认 summary，不返回完整 DOM、完整 script、完整 body。
- 每个摘要都带 `truncated`、`limit`、`next_action`。
- 对 agent 使用 XML/structured payload 友好。

### BrowserInteractionGraphService

生成可交互图：

```python
BrowserInteractionNode(
    ref: str,
    kind: Literal[
        "button",
        "link",
        "input",
        "select",
        "date",
        "city",
        "option",
        "tab",
        "form",
        "overlay",
        "unknown",
    ],
    label: str | None,
    value: str | None,
    role: str | None,
    frame_id: str | None,
    backend_node_id: int | None,
    selector: str | None,
    bbox: BrowserBox | None,
    evidence: tuple[BrowserInteractionEvidence, ...],
    confidence: float,
    children: tuple["BrowserInteractionNode", ...],
)
```

证据类型：

```text
native-control
aria-role
visible-text
ax-node
self-listener
ancestor-listener
hit-test
box-visible
editable
form-associated
network-trigger
visual-fallback
```

排序原则：

- 原生控件、ARIA、event listener、hit-test 权重大于 class fallback。
- `visual-fallback` 只能作为低可信补充。
- 如果 text snapshot 可见表单，interaction graph 也必须解释为什么没有 ref 或产出 ref。

### BrowserDomInspectionService

承载 DOM 层诊断动作：

```text
dom-inspect
dom-clickability
dom-highlight
dom-mutation-wait
```

规则：

- DOM inspect/clickability/highlight/mutation wait 不继续堆在 action engine。
- 输出 layout/style/accessibility/clickability/event handler 摘要，帮助 agent 判断
  ref 面板是否漏掉真实可交互元素。
- highlight 和 mutation wait 仍然是 Browser runtime 调试能力，不变成 Tool 自己的 DOM 解析逻辑。

### BrowserActionTraceService

一次动作 trace：

```text
before observe
start network capture cursor
execute action
wait stabilize
after observe
compute diff
return trace
```

输出：

```python
BrowserActionTrace(
    trace_id: str,
    action: BrowserActionDescriptor,
    before: BrowserObservation,
    after: BrowserObservation,
    diff: BrowserActionDiff,
    network_delta: BrowserNetworkDelta,
    console_delta: BrowserConsoleDelta,
    storage_delta: BrowserStorageDelta,
    recommendations: tuple[BrowserTraceRecommendation, ...],
)
```

用途：

- 解释按钮点了是否有效。
- 识别点击产生的 XHR/fetch。
- 识别 overlay 出现/消失。
- 判断页面是否进入 loading、route change、结果页。
- 推荐下一步使用 DOM 操作、network replay 或 script inspect。

### BrowserNetworkInsightService

基于现有 network capture/replay 增强：

- request 与 action trace 关联。
- request 与 initiator / script / frame 关联。
- 请求参数 diff。
- 响应摘要。
- replay suitability：
  - same-origin
  - requires cookie/session
  - mutating method
  - sensitive body
  - cross-origin
  - likely idempotent

### BrowserScriptInsightService

能力：

```text
browser.code.search(query, scope)
browser.script.inspect(script_id, line_range)
browser.script.list
browser.script.find_request(request_id)
```

规则：

- 默认只返回命中片段和周边少量行。
- 大脚本内容写 artifact 或分页读取。
- source map 只做线索，不作为硬依赖。
- 不自动执行页面未知函数；执行类动作走 runtime inspect/evaluate 权限。

### BrowserRuntimeInspectService

能力：

- framework hint：React/Vue/Angular/Next/Nuxt/Vite 等。
- route / history / location state。
- focused element。
- event listener summary。
- selected node runtime properties。
- safe global keys。

Runtime inspect 默认只读。`Runtime.evaluate` 写入/执行类操作必须走高风险权限。

### BrowserRecipeDraftService

从 observation / action traces / network insight 生成 recipe draft：

```yaml
name: ceair_search_flight_price
site:
  host: m.ceair.com
inputs:
  - from_city
  - to_city
  - date
strategy:
  preferred:
    kind: network_replay_from_page_context
    request_pattern: ...
  fallback:
    kind: interaction_form_fill
validation:
  - response contains requested route
  - visible result matches date
risks:
  - price can differ by inventory and membership
```

Browser 只产出 draft。保存、审批、发布归 Skills。

## 新增 Tool Surface

新增高层工具：

```text
browser.observe
browser.interaction.snapshot
browser.interaction.inspect_ref
browser.action.trace
browser.network.inspect
browser.code.search
browser.script.inspect
browser.runtime.inspect
browser.recipe.draft
```

保留底层工具：

```text
browser.navigate
browser.tabs.*
browser.snapshot
browser.click
browser.type
browser.evaluate
browser.dom.*
browser.network.*
browser.storage.*
browser.service_worker.*
browser.trace.*
browser.performance.*
browser.context.*
browser.environment.*
```

Prompt tree / tool grouping 里默认优先展示高层工具。底层工具作为展开后的高级能力。

## Ref 存储升级

`BrowserStoredRef` 需要扩展为证据节点：

```python
BrowserStoredRef(
    ref: str,
    selector: str | None,
    uid: str | None,
    role: str | None,
    label: str | None,
    text: str | None,
    tag: str | None,
    frame_path: tuple[int, ...],
    frame_id: str | None,
    backend_node_id: int | None,
    bbox: BrowserBox | None,
    evidence: tuple[str, ...],
    confidence: float,
    snapshot_format: str | None,
    generation: int | None,
)
```

执行动作时：

1. 优先 `backend_node_id + frame_id` resolve。
2. 失败后使用 selector。
3. 再失败使用 role/text。
4. 最后才考虑 visual fallback / coordinate。

失败结果必须说明：

- node disappeared
- frame changed
- stale generation
- overlay blocked
- hit-test mismatch
- profile target drift

## 安全与权限

能力分级：

| 能力 | 权限建议 | 说明 |
| --- | --- | --- |
| `browser.observe` | `browser.profile_read`, `browser.page_action` | 默认脱敏摘要 |
| `interaction.inspect_ref` | `browser.page_action` | 可读 DOM/AX/layout/event 摘要 |
| `action.trace` | `browser.page_action`, `browser.network_read` | 可触发页面行为 |
| `network.get_response_body` | `browser.network_sensitive_read` | 响应 body 脱敏/截断 |
| `network.replay_request` | `browser.network_sensitive_read` | mutating/cross-origin 继续 gate |
| `browser.runtime.inspect` | `browser.code_read` | 固定只读 runtime 摘要 |
| `browser.script.list` | `browser.code_read` | 只读脚本目录 |
| `browser.script.find_request` | `browser.code_read` | request 到脚本候选引用 |
| `browser.code.search` | `browser.code_read` | 只读脚本片段 |
| `browser.script.inspect` | `browser.code_read` | bounded source preview |
| `evaluate` / raw runtime write | 高风险 | 不进入默认 agent prompt |

脱敏规则：

- cookie、authorization、token、secret、password、session 默认脱敏。
- request/response body 默认截断。
- 大 payload 写 artifact。
- cross-origin request replay 需要显式 `allow_cross_origin=true`。
- mutating method 需要显式 `allow_mutating=true`。

## Operations 观察

Browser Operations read model 增加：

- observation count / latest observe time。
- interaction ref count / confidence distribution。
- active action traces。
- action trace failures。
- network capture active/stopped count。
- recent request domains / failed requests。
- script inspection count / errors。
- profile target drift / stale ref warnings。

事件建议：

```text
browser.observation.captured
browser.interaction_graph.captured
browser.action_trace.started
browser.action_trace.completed
browser.action_trace.failed
browser.network_insight.generated
browser.script_insight.generated
browser.recipe_draft.generated
```

Operations 只物化摘要，不保存完整 body/script。

## 2026-06-03 Implementation Status

已落地：

- `BrowserDevToolsAdapter` 已接入 `Debugger.scriptParsed` / `Debugger.getScriptSource`。
- Browser action kind 已新增 `runtime-inspect`、`script-list`、`code-search`、`script-inspect`。
- `browser.runtime.inspect` 已接入固定只读 page-context probe，输出 page state、
  framework signals、selected globals、storage key counts 与 performance summary；不开放 raw CDP。
- `browser.script.list` 已作为轻量脚本目录入口暴露，返回 script id、URL、行数、
  execution context、module/source-map 等摘要，不读取完整源码。
- `browser.script.find_request` 已接入，可用 request URL/path/query fragment 定位 live
  scripts 中的候选引用位置，返回脚本、行号、term、snippet 与候选 score。
- `CdpBackedPlaywrightActionEngine` 已支持受控脚本搜索与脚本预览。
- `BrowserActionTraceService` 已支持 `action-trace`：执行一次真实页面动作，并返回 before/after snapshot、console/page error delta、network delta 与 next-action recommendation。
- Action trace 的 network delta 已提取 CDP request initiator，输出 `initiator_summary` / `causality`，可指向触发请求的 script/function/line。
- Action trace 已补 storage/lifecycle diff：storage 只输出 local/session key 增删和 count delta，
  不读取 value；lifecycle 输出 URL、title、ready/visibility/focus/history/online 字段变化，并参与 next-action recommendation。
- Action trace 已支持 JSON artifact：工具文本仍返回摘要，同时在 artifact service 可用时追加
  `application/json` file_ref，保存完整 trace payload 供 UI/agent 后续展开。
- `configured.browser` 已暴露 `browser.runtime.inspect`、`browser.script.list`、
  `browser.script.find_request`、`browser.code.search`、`browser.script.inspect`。
- `configured.browser` 已暴露 `browser.action.trace`。
- `configured.browser` 已暴露 `browser.network.inspect`，由 `BrowserNetworkInsightService`
  承载 performance/resource tree/CDP metrics inspection。
- `browser.network.replay_request` 已输出 replay suitability、request diff 与 response summary；
  摘要只暴露 gate、字段变化和大小/状态，不输出敏感 header/body value；如果源请求 URL、
  header 或 body 已脱敏，suitability 会降级为 warning，提醒 agent 补参数或改用其他路径。
- `browser.runtime.inspect` 已输出 route hints，覆盖 location、history state、
  Next.js data 与选定 runtime global 中常见 route/store 字段。
- DOM inspection 已输出 event handler summary，覆盖 inline handler、property handler 与
  已知 listener type 摘要，帮助 agent 判断可交互元素是否被 ref 面板漏掉。
- `BrowserDomInspectionService` 已拆出到 Browser infrastructure，承载 DOM inspect、
  clickability、highlight 与 mutation wait；Browser action engine 只保留 command 分发入口。
- `browser.observe` 已合入 `runtime-inspect` 的 page state、framework signals、
  route hints 与 runtime global 摘要；`network-inspect` 继续专注 resource tree 与
  performance，避免 observe 把不同运行事实揉成一个字段。
- `browser.observe` 已合入 script/code 摘要：默认返回 bounded `script-list`
  元数据；传入 `code_search_query` 或 request 线索时才执行 `code-search` /
  `script-find-request`，避免普通观察默认读取 bundle。
- `BrowserScriptInsightService` 已拆出到 Browser infrastructure，承载 runtime inspect、
  script catalog、request/code search 与 bounded source preview；Browser action engine
  只保留 command 分发入口。
- `BrowserActionTraceService` 已拆出到 Browser infrastructure，承载 before/after snapshot、
  network/console/page-error/storage/lifecycle delta、recommendation 与 trace payload 组装；
  Browser action engine 只提供 snapshot、network capture、inner action 和 message reader callback。
- `BrowserNetworkInsightService` 已拆出到 Browser infrastructure，承载 `network-inspect`
  的 Performance entries、CDP metrics 与 resource tree 读取；Browser action engine 只保留
  command 分发入口，network capture fallback 复用同一 Performance expression。
- `BrowserNetworkActionService` 已拆出到 Browser infrastructure，承载 network capture
  start/stop/list/get body/fetch-as-page/replay-request；Browser action engine 不再持有
  capture/replay 细节。
- `BrowserStorageInspectionService` 已接管 cookies、local/session storage、IndexedDB、
  Cache Storage 与 Service Worker inspection；Browser action engine 不再解析 storage/cookie
  payload，也清除了未调用的旧 browser storage/cookie 脚本块。
- `BrowserPeripheralActionService` 已拆出到 Browser infrastructure，承载 console buffer、
  dialog accept/dismiss、download / wait-download lifecycle、screenshot/PDF 输出序列化与
  page/locator evaluate；
  Browser action engine 只提供 locator click trigger。
- 旧的 page-injected console capture expression 已清理；console 读取统一走 session pool
  buffer。
- `cdp-raw` 明确保留为 debug/admin escape hatch，不进入默认 agent 工具面，不参与本轮
  action engine service 拆分。
- Tool prompt group 已新增 `action_trace`、`code_insight`，与低层 page action/network/diagnostics 分离。
- Tool capability catalog 已新增 `browser.code_read`。
- 结果默认只返回命中摘要、上下文行与 bounded source preview，不返回完整 bundle。

仍未落地：

- 深层 DOMDebugger listener chain、framework router state 解包仍未系统化，当前只提供
  route/event 的轻量可读摘要。

## 施工阶段

### Phase 1: DevTools Adapter and Ref Evidence

- [x] 新增 Browser DevTools adapter。
- [x] 接 `DOMSnapshot.captureSnapshot`。
- [x] 接 `DOM.getNodeForLocation`。
- [x] 接 `DOMDebugger.getEventListeners`。
- [x] 接 `DOM.resolveNode` + `Runtime.callFunctionOn` backend-node marker。
- [x] 扩展 `BrowserStoredRef`。
- [x] `browser.snapshot(format=interactive)` 输出 evidence/confidence。
- [x] `backend_node_id` 参与 ref 动作定位优先级。
- [x] 保留 visual class fallback，但降级为最后证据。
- [x] 拆出 `BrowserDomInspectionService`，让 DOM 诊断细节不再塞在 action engine。
- [ ] 测试东航移动页、日历、联想框、overlay。

### Phase 2: Browser Observe

- [x] 新增 `BrowserObservationService`。
- [x] 新增 `browser.observe` tool。
- [x] 聚合 page/tabs/frames/interactive refs/console。
- [x] 聚合 runtime/resource tree/performance 摘要。
- [x] 支持可选 existing network capture 请求摘要。
- [x] 聚合 runtime inspect 摘要。
- [x] 聚合 script/code insight 摘要。
- [x] 控制 payload size。
- [x] 失败时返回 explainable section errors。
- [x] 更新 tool catalog grouping，把 observe 作为 Browser 高层入口。

### Phase 3: Action Trace

- [x] 新增 `BrowserActionTraceService`。
- [x] 新增 `browser.action.trace` tool。
- [x] before/after snapshot。
- [x] 自动捕获 network delta。
- [x] 捕获 console/page error diff。
- [x] 捕获 storage/page lifecycle diff。
- [x] 生成 recommendation。
- [x] 支持 trace artifact。

### Phase 4: Network Insight

- [x] 增强 request initiator / script / action trace 关联。
- [x] 拆出 `BrowserNetworkInsightService`，让 action engine 只负责分发。
- [x] 拆出 `BrowserNetworkActionService`，让 capture/replay 不再塞在 action engine。
- [x] 新增 `browser.network.inspect`。
- [x] 增强 `replay_request` 输出 replay suitability。
- [x] 支持 request body diff / response summary。
- [x] 明确 mutating/cross-origin/sensitive body gate。

### Phase 5: Script and Runtime Insight

- [x] 拆出 `BrowserScriptInsightService`，让 action engine 只负责分发。
- [x] 接 `Debugger.scriptParsed`。
- [x] 接 `Debugger.getScriptSource`。
- [ ] 新增 script index。
- [x] 新增 `browser.script.list`。
- [x] 新增 `browser.script.find_request`。
- [x] 新增 `browser.code.search`。
- [x] 新增 `browser.script.inspect`。
- [x] 新增 `browser.runtime.inspect`。
- [x] 输出 framework summary。
- [x] 输出 route / event listener summary 第一版。

### Phase 5.5: Action Engine Boundary Cleanup

- [x] 拆出 `BrowserDomInspectionService`。
- [x] 拆出 `BrowserNetworkInsightService`。
- [x] 拆出 `BrowserNetworkActionService`。
- [x] 拆出 `BrowserScriptInsightService`。
- [x] 扩展 `BrowserStorageInspectionService` 接管 cookie/local/session storage。
- [x] 拆出 `BrowserPeripheralActionService` 接管 console/dialog/download。
- [x] 扩展 `BrowserPeripheralActionService` 接管 screenshot/pdf 输出序列化。
- [x] 扩展 `BrowserPeripheralActionService` 接管 page/locator evaluate。
- [x] 清理旧 page-injected console capture expression。
- [x] 明确保留 `cdp-raw` 作为 debug/admin escape hatch。

### Phase 6: Recipe Draft and Skill Handoff

- [ ] 新增 `BrowserRecipeDraftService`。
- [ ] 新增 `browser.recipe.draft`。
- [ ] 从 action traces / network insight 生成 recipe draft。
- [ ] 对接 Skills authoring surface，走 draft/validate/approve/apply。
- [ ] Memory 只接收用户或 agent 明确要求记住的事实。

### Phase 7: Operations and Docs

- [ ] Browser operations projection 增加 observation/action trace/network/script 摘要。
- [ ] Browser Operations 页面紧凑展示新增指标。
- [ ] 更新 `src/crxzipple/modules/browser/README.md`。
- [ ] 更新 `tools/README.md` Browser authoring section。
- [ ] 更新 tests/unit README 的 Browser 测试入口。

## 验收场景

### 东航移动页表单

输入：

```text
navigate https://m.ceair.com/
observe
```

期望：

- visible text 能看见预订机票表单。
- interaction graph 产生出发地、到达地、日期、搜索按钮 refs。
- refs 带 evidence 和 confidence。
- 如果 SPA hydration 未完成，observe 返回 `not_ready` 和建议 wait/stabilize。

### 日历控件

期望：

- 打开日期控件后，observe 能识别 overlay。
- 日期 option 有 refs。
- action trace 能说明点击日期后 overlay 消失、字段值变化。

### 搜索按钮网络因果

期望：

- `browser.action.trace(ref=search)` 返回新增 XHR/fetch。
- network delta 包含 method、url、request body summary、response summary。
- recommendation 可提示是否适合 page-context replay。

### JS 接口搜索

期望：

- `browser.code.search("flight")` 能返回脚本片段或 request initiator 线索。
- 大 bundle 不直接进入 tool result。
- script inspect 可按 script id + range 分页读取。

### 多 profile / pool

期望：

- observe/action trace 支持 `profile` 或 `profile_pool`。
- 同一 session/run 默认复用 allocation。
- 结果 metadata 记录 profile/pool/allocation/target_id。

## 验证命令

按改动范围运行：

```bash
PYTHONPATH=src pytest -q tests/unit/test_browser_playwright_actions.py
PYTHONPATH=src pytest -q tests/unit/test_browser_tool_http_runtime.py
PYTHONPATH=src pytest -q tests/unit/test_browser_network_capture.py
PYTHONPATH=src pytest -q tests/unit/test_browser_cdp_sessions.py
PYTHONPATH=src pytest -q tests/unit/test_operations_browser_read_model.py
```

前端或 tool catalog 改动时：

```bash
cd frontend
npm run typecheck
npm run build
```

运行栈验证：

```bash
make dev-up
bash scripts/dev/status-redis-stack.sh
```

## 收口标准

- Agent 默认能通过 `browser.observe` 理解浏览器现场，而不是先猜该调哪个底层工具。
- Ref 是证据节点，不只是 selector/text 包装。
- Action trace 能解释一次操作的因果。
- Network 和 script insight 能帮助 agent 找到更高效的请求路径。
- Raw CDP 不进入普通 agent tool surface。
- Browser module 不重复造 Chrome DevTools 已有能力。
- Tool module 不实现浏览器逻辑。
- Skill/Memory 沉淀通过 owner module，不与 Browser runtime 混在一起。
