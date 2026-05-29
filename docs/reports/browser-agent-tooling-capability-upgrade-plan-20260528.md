# Browser Agent Tooling Capability Upgrade Plan 2026-05-28

本文档定义 Browser 能力升级方案。目标不是把 CDP 原样暴露给 agent，而是把浏览器整理成
agent 顺手使用的工具箱：既能像人一样操作页面，也能像工程师一样观察网络、DOM、存储、
上下文和运行诊断。

本文接续：

- `browser-tool-source-profile-runtime-redesign-plan-20260525.md`
- `browser-profile-pool-multi-ip-collection-plan-20260526.md`
- `src/crxzipple/modules/browser/README.md`

后续施工仍遵守当前主线：

- Browser tool source 只有 `configured.browser`。
- Browser profile / pool 是运行上下文，不是 Tool Source。
- Browser MCP 不是默认路径，不恢复 `configured.mcp.browser_{profile}`。
- Tool module 拥有 tool catalog / tool run lifecycle；Browser module 拥有 profile、CDP、
  tab、page action、network、DOM、storage、diagnostics 的运行能力。
- `cdp-raw` 只能作为调试逃生口，不能替代 agent-facing 工具。

## 目标

给 agent 建立一套高可用、低歧义、可组合的浏览器工具：

```text
页面操作：打开、切 tab、点击、输入、选择、上传、下载、截图、PDF
页面理解：interactive snapshot、DOM inspect、box model、computed style、可点击性诊断
网络观察：抓包、筛选请求、看 headers/body/timing/initiator、复放请求
会话使用：读取 cookie/storage/indexedDB/cache/service worker、页面上下文 fetch
上下文治理：profile/pool 分配、tab/window lease、代理/IP、隔离与回收
调试诊断：console、JS exception、performance、trace、权限、页面生命周期
```

agent 使用时应能自然完成这些任务：

- “打开携程并查看昆明到上海机票”：先用页面操作进入页面，再用 network 找 XHR 返回。
- “为什么按钮点了没反应”：看 DOM 可点击性、console error、network failure。
- “这个页面真实提交了什么参数”：看 request payload、headers、cookies、initiator。
- “用当前登录态调用接口”：用 page-context fetch 或 replay request。
- “多个隔离身份挂不同代理采集同一站点”：用 browser profile pool acquire/release。

## 非目标

- 不建设绕过网站风控、限流或访问控制的规避系统。
- 不让 LLM 直接随意调用任意 CDP method。
- 不把 profile、pool、site、proxy 膨胀成多个 Tool Source。
- 不让 Tool module 直接读取 browser runtime 文件、daemon manifest 或 raw CDP endpoint。
- 不让 Operations 决策 browser 调度；Operations 只观察和物化 read model。

## 当前基础

已经具备：

- `configured.browser` 单一 Browser source。
- Browser profile 和 daemon host：`host:browser:{profile}`。
- Browser page action：
  - `navigate`
  - `open-tab`
  - `focus-tab`
  - `close-tab`
  - `snapshot`
  - `click`
  - `type`
  - `press`
  - `hover`
  - `drag`
  - `select`
  - `fill`
  - `upload`
  - `download`
  - `wait`
  - `screenshot`
  - `pdf`
  - `evaluate`
  - `console`
  - `cookies`
  - `storage`
  - `network-inspect`
  - `cdp-raw`
- Active overlay snapshot 已能对 autocomplete/calendar 生成 scoped refs。
- Browser profile pool / 多 IP 采集方案已有独立计划。

主要缺口：

- `network-inspect` 只读 performance/resource tree，不是完整 CDP network capture。
- `cdp-raw` 太底层，agent 不适合直接使用。
- DOM / Accessibility / box model / computed style 未产品化。
- IndexedDB / Cache Storage / Service Worker 未产品化。
- Page-context fetch、request replay、request interception 未产品化。
- tab/window lease、页面连续操作和回收语义仍需收口。
- Operations Browser 页面缺完整 network/storage/lease/diagnostics 观察。

## 目标工具面

### Core Navigation and Page Actions

保持当前能力，但收敛命名和语义：

```text
browser.tabs.list
browser.tabs.open
browser.tabs.focus
browser.tabs.close
browser.navigate
browser.snapshot
browser.click
browser.type
browser.press
browser.fill
browser.select
browser.upload
browser.download
browser.screenshot
browser.pdf
browser.wait
```

规则：

- 所有工具都接受 `profile` 或 `profile_pool`。
- 所有工具都返回 `profile`、`target_id`、`page_generation`、`snapshot_generation`。
- `click` 优先使用 `ref` / `selector`，允许坐标兜底，但坐标不是主要交互模型。
- `snapshot(active_overlay=true)` 应优先返回当前浮层 scope，避免全页噪音。

### DOM and Visual Inspection

新增：

```text
browser.dom.inspect
browser.dom.box_model
browser.dom.computed_style
browser.dom.highlight
browser.dom.clickability
browser.dom.mutation_wait
```

用途：

- 解释一个元素为什么不可点。
- 判断是否被遮挡、是否 disabled、是否 out of viewport。
- 读取 layout box、computed style、visible text、ARIA role、DOM path。
- 给 agent 一个更可靠的“页面结构理解”通道。

示例输出：

```json
{
  "target_id": "...",
  "ref": "r12",
  "selector": "...",
  "visible": true,
  "enabled": true,
  "clickable": false,
  "blocked_by": {
    "selector": ".modal-mask",
    "z_index": 2000
  },
  "box": {
    "x": 520,
    "y": 312,
    "width": 180,
    "height": 36
  },
  "computed_style": {
    "display": "block",
    "visibility": "visible",
    "pointer_events": "auto"
  }
}
```

### Network Capture

新增：

```text
browser.network.start_capture
browser.network.stop_capture
browser.network.list_requests
browser.network.get_request
browser.network.get_response_body
browser.network.get_request_body
browser.network.replay_request
browser.network.fetch_as_page
browser.network.clear_capture
```

能力来源：

- CDP `Network.enable`
- CDP `Network.requestWillBeSent`
- CDP `Network.responseReceived`
- CDP `Network.loadingFinished`
- CDP `Network.getResponseBody`
- CDP `Network.getRequestPostData`
- Runtime page-context `fetch`

目标行为：

- capture 按 `profile + target_id + capture_id` 管理。
- 默认只保留最近 N 条请求和受控大小的 body。
- 支持筛选：
  - resource type
  - domain / path / method / status
  - initiator
  - mime type
  - keyword
  - time range
- 响应 body 默认脱敏和截断。
- 大 body 写 artifact，不直接塞进 tool result。

请求记录模型：

```python
BrowserNetworkRequest(
    request_id: str,
    capture_id: str,
    profile_name: str,
    target_id: str,
    frame_id: str | None,
    loader_id: str | None,
    url: str,
    method: str,
    resource_type: str,
    request_headers: dict[str, str],
    request_post_data_preview: str | None,
    status: int | None,
    response_headers: dict[str, str],
    mime_type: str | None,
    timing: dict[str, object],
    initiator: dict[str, object],
    body_ref: str | None,
    created_at: datetime,
    completed_at: datetime | None,
)
```

### Request Interception

新增但默认受限：

```text
browser.network.intercept.start
browser.network.intercept.stop
browser.network.intercept.rules
```

能力来源：

- CDP `Fetch.enable`
- CDP `Fetch.continueRequest`
- CDP `Fetch.fulfillRequest`
- CDP `Fetch.failRequest`

使用边界：

- 默认只允许 block/mock 静态资源、测试域名或显式 allowlist。
- 修改 headers/body 需要更高权限。
- 所有 interception rule 必须进入 audit。
- 不允许 agent 静默篡改登录、支付、授权相关请求。

### Deep Storage

新增：

```text
browser.storage.cookies
browser.storage.local
browser.storage.session
browser.storage.indexeddb.list
browser.storage.indexeddb.get
browser.storage.indexeddb.query
browser.storage.cache.list
browser.storage.cache.get
browser.service_worker.list
browser.service_worker.inspect
```

能力来源：

- 当前 Playwright context cookies。
- Runtime `localStorage/sessionStorage`。
- CDP `IndexedDB.*`
- CDP `CacheStorage.*`
- CDP `ServiceWorker.*`

规则：

- cookie / token / authorization header 默认脱敏。
- 修改 storage 需要显式操作工具，不和读取工具混在一起。
- 读取 IndexedDB/Cache body 时受大小限制。

### Context, Lease, and Pool

新增/补齐：

```text
browser.context.acquire
browser.context.release
browser.context.current
browser.context.heartbeat
browser.context.reconcile
```

用途：

- 让一个任务连续操作同一个 profile/tab/window。
- 支撑 profile pool 分配。
- 避免多个任务抢同一个 tab。
- 处理浏览器被用户关闭、target 失效、服务重启后的恢复。

模型：

```python
BrowserContextLease(
    lease_id: str,
    profile_name: str,
    profile_pool_id: str | None,
    target_id: str | None,
    window_id: str | None,
    consumer_kind: str,
    consumer_id: str,
    status: Literal["active", "released", "expired", "lost"],
    acquired_at: datetime,
    expires_at: datetime,
    last_heartbeat_at: datetime | None,
)
```

规则：

- 同一 consumer 可复用 active lease。
- tab 关闭后 lease 标记 `lost`，下一次操作必须重新 snapshot 或重新 acquire。
- lease 过期后 tab 是否关闭由 profile/pool policy 决定。
- 用户手动切 tab 不影响机器通过 CDP 操作非前台 tab，但人机混用时要显示 warning。

### Emulation and Permissions

新增：

```text
browser.emulation.set
browser.emulation.reset
browser.permissions.grant
browser.permissions.clear
browser.geolocation.set
browser.network_conditions.set
```

能力：

- viewport / device scale。
- user agent。
- timezone / locale。
- geolocation。
- permissions。
- network throttling。

规则：

- 与 profile runtime policy 绑定，不能让 agent 任意伪装生产身份。
- 修改影响持久 profile 的设置时，需要记录 audit。

### Diagnostics and Tracing

新增：

```text
browser.diagnostics.collect
browser.performance.metrics
browser.trace.start
browser.trace.stop
browser.trace.export
browser.page.lifecycle
browser.page.errors
```

用途：

- 收集 console、JS exception、network failures、page lifecycle、performance metrics。
- 支持 Operations Browser 页面和 agent 自诊断。
- 复杂问题导出 trace artifact。

## 后端改造

### Browser Application

新增 application services：

- `BrowserNetworkCaptureService`
  - start / stop / list / get / body / replay / fetch_as_page。
- `BrowserDomInspectionService`
  - inspect / box_model / computed_style / highlight / clickability。
- `BrowserStorageInspectionService`
  - indexedDB / cache / service worker。
- `BrowserContextLeaseService`
  - acquire / release / heartbeat / expire / reconcile。
- `BrowserDiagnosticsService`
  - collect / metrics / trace。

现有 `BrowserToolApplicationService` 保持作为 Tool-facing facade，但不膨胀成所有逻辑的上帝类。
它只负责：

- 组装 display-safe error。
- 调用对应 Browser application service。
- 返回 tool run metadata。

### Browser Infrastructure

新增或拆分：

- `cdp_session_broker.py`
  - page-scoped CDP session 生命周期。
  - 长连接订阅 session 和短命 command session 分离。
- `network_capture.py`
  - Network/Fetch event subscription。
  - ring buffer / body store / request correlation。
- `dom_inspector.py`
  - DOM / CSS / Accessibility / Overlay helpers。
- `storage_inspector.py`
  - IndexedDB / CacheStorage / ServiceWorker adapters。
- `context_leases.py`
  - lease persistence and expiration。
- `diagnostics.py`
  - performance / trace / lifecycle / errors。

### Persistence

短期实现：

- in-process + runtime state store ring buffer。
- tool run metadata 记录 capture id / request ids。

稳定实现：

- Postgres 表：
  - `browser_context_leases`
  - `browser_network_captures`
  - `browser_network_requests`
  - `browser_network_bodies`
  - `browser_diagnostics_runs`
- 大 body、trace、screenshot、MHTML 写 artifact store，不直接进普通表。

### Events

Browser module 发布事实事件：

```text
browser.profile.ready
browser.profile.lost
browser.context.lease.acquired
browser.context.lease.released
browser.network.capture.started
browser.network.capture.stopped
browser.network.request.observed
browser.network.request.failed
browser.network.fetch.executed
browser.network.fetch.failed
browser.network.replay.executed
browser.network.replay.failed
browser.network.intercept.started
browser.network.intercept.stopped
browser.diagnostics.collected
browser.trace.exported
```

Events module 只承载事件，不理解 browser 业务。

## Tool Module 改造

Tool catalog 新增稳定函数，而不是暴露 raw CDP：

```text
browser.network.*
browser.dom.*
browser.storage.*
browser.context.*
browser.diagnostics.*
browser.emulation.*
```

规则：

- `browser.cdp-raw` 标记为 advanced/debug，默认不推荐给普通 agent。
- 每个新 function schema 必须有清晰输入示例和 display-safe error。
- Tool run metadata 必须记录：
  - `browser_profile`
  - `browser_profile_source`
  - `browser_profile_pool`
  - `browser_context_lease_id`
  - `browser_target_id`
  - `browser_capture_id`
  - `browser_page_generation`
  - `browser_snapshot_generation`

## Operations 改造

新增/补齐 `/operations/browser` projection：

- Profile readiness：
  - ready / lost / setup_needed / conflicted。
- Context leases：
  - active leases、consumer、TTL、target、lost count。
- Network captures：
  - active captures、request count、failed count、top domains、latest XHR。
- Storage health：
  - cookie count、storage usage、service worker status。
- Diagnostics：
  - console errors、network failures、JS exceptions、trace artifacts。
- Pool status：
  - profile allocation、proxy/egress、cooldown、failure quarantine。

Operations 只从 Browser/Tool/Daemon/Access 事实和 query service 聚合，不由前端绕路调用模块 API。

## Settings 改造

Browser Settings 应提供：

- Browser Profile CRUD。
- Profile Pool CRUD。
- Proxy credential binding 选择和 readiness。
- Profile runtime policy：
  - autostart
  - attach-only
  - tab limit
  - lease TTL
  - tab recycle policy
  - allowed emulation changes
- Browser tool exposure policy：
  - allow network capture
  - allow response body
  - allow request replay
  - allow interception
  - allow storage write
  - allow cdp-raw debug

Settings 不直接替 Browser 执行 CDP 操作，只调用 Browser application usecase。

## 安全和授权

Browser 工具要分级：

| 级别 | 工具 | 默认 |
| --- | --- | --- |
| safe-read | snapshot、tabs.list、dom.inspect、network.list、storage read with redaction | 可开放 |
| page-action | click、type、navigate、upload、download | 需按 agent policy |
| sensitive-read | cookies、headers、response body、IndexedDB body | 需授权 |
| mutation | storage set、permissions grant、emulation set | 需授权 |
| network-mutation | replay、fetch_as_page、intercept | 需授权 / audit |
| debug-admin | cdp-raw、trace full export | 默认关闭 |

脱敏规则：

- `Authorization`
- `Cookie`
- `Set-Cookie`
- `x-api-key`
- token-like query/body fields
- password / secret / credential 字段

所有 sensitive-read / mutation 都必须写 audit fact。

## Agent 使用体验

推荐 agent 工作流：

### 查页面数据

```text
browser.navigate
browser.network.start_capture
browser.click / browser.type
browser.network.list_requests(resource_type="xhr", keyword="flight")
browser.network.get_response_body(request_id)
```

### 调试点击失败

```text
browser.snapshot(active_overlay=true)
browser.dom.clickability(ref)
browser.console(level="error")
browser.network.list_requests(status_min=400)
```

### 使用登录态调用接口

```text
browser.network.list_requests(keyword="/api/")
browser.network.get_request(request_id)
browser.network.replay_request(request_id)
```

或：

```text
browser.network.fetch_as_page(url, method, headers, body)
```

### 多 profile 采集

```text
browser.context.acquire(profile_pool="ctrip-flight", target_host="ctrip.com")
browser.navigate(lease_id=...)
browser.network.start_capture(lease_id=...)
...
browser.context.release(lease_id=...)
```

## 开发 Checklist

### R1: CDP Session Broker

- [x] 新增 page-scoped CDP session broker。
- [x] 区分 command session 和 subscription session。
- [x] 支持 target detach / page close / browser restart 的统一错误。
- [x] 所有 CDP 错误转成 display-safe Browser error。
- [x] `cdp-raw` 迁到 debug/admin 分类。

当前 CDP 会话由 `BrowserCdpSessionBroker` 统一创建和回收。普通 CDP 调用拿
command lease，network capture 拿 subscription lease 并长期绑定事件监听；
target closed / detached / browser connection closed 等异常会归一成可展示、
可恢复的 Browser 错误。`cdp-raw` 已从普通 `configured.browser` function
catalog、`browser.action` agent-facing handler、公开 Browser HTTP/CLI facade
中移除，只保留内部调试逃生口。

同时清理 `Settings.browser_profile_runtime_settings` 以及
`APP_BROWSER_PROFILE_SPECS[*].runtime_mode/transport/executable_path/headless`
这类旧 Browser profile 运行层字段。当前 profile config 只表达
driver/CDP/proxy/autostart/attach-only 等 profile 事实；executable/headless
属于 Browser system config。

### R2: Network Capture

- [x] 新增 `BrowserNetworkCaptureService`。
- [x] 实现 `start_capture` / `stop_capture`。
- [x] 监听 request / response / loading / failure 事件。
- [x] 实现 request correlation。
- [x] 实现 body store 和 size limit。
- [x] 实现 `list_requests` 筛选。
- [x] 实现 `get_request`、`get_response_body`、`get_request_body`。
- [x] 实现 redaction。
- [x] 发布 browser network events。
- [x] 添加 unit tests 和 live-ish fake CDP tests。

当前已接通 `browser.network.start_capture` / `stop_capture` / `list_requests`
/ `get_request` / `get_request_body` / `get_response_body` / `fetch_as_page`
/ `replay_request` / `clear_capture`。
独立 network fetch/replay audit facts 已写入事件流；后续剩余是 Operations Browser
页面把这些事实投影成 network/diagnostics 面板。

### R3: Replay and Page Fetch

- [x] 实现 `replay_request`。
- [x] 实现 page-context `fetch_as_page`。
- [x] 限制跨域、敏感 method、认证 header 暴露。
- [x] 写独立 audit facts。
- [x] Tool schema 标明风险等级和授权需求。

当前实现通过当前页面 `fetch(..., credentials: "include")` 执行请求；默认只允许同源和
安全 HTTP method。跨域必须显式 `allow_cross_origin=true`，POST/PUT/PATCH/DELETE
必须显式 `allow_mutating=true`。认证类 header 不接受从 tool 参数透传，避免把凭证从
浏览器上下文泄露到工具入参。

### R4: DOM Inspection

- [x] 新增 DOM inspection action surface。
- [x] 实现 `dom.inspect`。
- [x] 实现 `box_model`。
- [x] 实现 `computed_style`。
- [x] 实现 `clickability`。
- [x] 实现 `highlight`。
- [x] 实现 `mutation_wait`。
- [x] 继续收敛 calendar/autocomplete duplicate refs。
- [x] 增加 overlay/root scoped snapshot 回归用例。

当前 DOM inspection 通过 `browser.dom.inspect` / `browser.dom.box_model`
/ `browser.dom.computed_style` / `browser.dom.clickability`
/ `browser.dom.highlight` / `browser.dom.mutation_wait` 暴露给 agent。
它复用现有 profile、target、ref/selector 解析，返回元素可见性、视口 box、computed
style、click point、blocked_by、不可点击原因、临时高亮状态和 DOM mutation 等待结果。
autocomplete/calendar overlay 已增加 scoped snapshot 和 descendant duplicate ref 回归；
后续若遇到站点特异 DOM，再按同一规则补局部 selector normalizer。

### R5: Deep Storage

- [x] 新增 `BrowserStorageInspectionService`。
- [x] 实现 IndexedDB list/get/query。
- [x] 实现 CacheStorage list/get。
- [x] 实现 ServiceWorker list/inspect。
- [x] 实现 storage read redaction。
- [x] storage write 单独授权，不混入 read 工具。

当前 deep storage 已作为正式 `browser.storage.*` / `browser.service_worker.*`
tool function 接入。IndexedDB / CacheStorage 走 CDP 只读命令，ServiceWorker
走页面标准 API 只读检查；结果默认脱敏 cookie、token、secret、authorization
等敏感字段。旧 `storage` action 仍只承担 local/session storage 的显式 set/get/clear，
deep storage 细节由 `BrowserStorageInspectionService` 承担，action engine 只做页面调度。

### R6: Context Lease

- [x] 将现有 `BrowserProfileAllocation` 正式升级为 context lease，避免新增并行 `BrowserContextLeaseService`。
- [x] 实现 acquire/release/heartbeat/expire。
- [x] Tool input 支持 `lease_id`。
- [x] Tool run metadata 记录 lease。
- [x] 处理 tab closed / target lost / browser restart 的 reconcile/lost 语义。
- [x] Operations 展示 active/lost/expired leases。

当前 context lease 不再单独建立第二套实体；`BrowserProfileAllocation`
就是 profile/pool 维度的浏览器上下文租约。`browser.context.*` 暴露
acquire/current/heartbeat/release/reconcile，普通 browser 工具也可用
`lease_id` 复用同一 profile/tab 连续操作。reconcile 会核对 live targets；
租约拥有的 target 全部消失时标记为 `lost`，并通过 browser allocation event
进入 Operations。

### R7: Emulation and Permissions

- [x] 实现 viewport/user-agent/timezone/locale/geolocation。
- [x] 实现 permissions grant/clear。
- [x] 实现 network conditions。
- [x] 与 profile runtime policy 绑定。
- [x] 修改型操作写 audit。

已新增 `BrowserEnvironmentControlService`，通过 `configured.browser` 暴露：

- `browser.emulation.set`
- `browser.emulation.reset`
- `browser.permissions.grant`
- `browser.permissions.clear`
- `browser.geolocation.set`
- `browser.network_conditions.set`

这组能力走 `BrowserPageActionKind` 和 cdp-backed action engine，不开放任意 CDP
method。影响范围按 target / browser_context 标注为 profile runtime scope；当前
CDP override、Playwright permission grant 均为运行时控制，不写入持久 profile
配置。修改型操作发布 `browser.environment.changed` 事件，供 Operations / audit
侧向观察。

### R8: Diagnostics and Trace

- [x] 实现 diagnostics.collect。
- [x] 收集 console errors、JS exceptions、network failures。
- [x] 实现 performance metrics。
- [x] 实现 trace start/stop/export。
- [x] trace 写 artifact。
- [x] Operations 展示 diagnostics summary。

已新增 `BrowserDiagnosticsService`，通过 `configured.browser` 暴露：

- `browser.diagnostics.collect`
- `browser.performance.metrics`
- `browser.trace.start`
- `browser.trace.stop`
- `browser.trace.export`
- `browser.page.lifecycle`
- `browser.page.errors`

当前诊断工具汇总 page lifecycle、console error/assert、Playwright pageerror、
CDP Performance metrics、可选 performance entries；trace 使用 Playwright browser
context tracing，`trace.stop/export` 以 zip artifact 形式返回。Operations Browser
页面已通过 observed browser diagnostics events 展示 diagnostics summary；
network failures 已在 R2/R3 的 network capture/event 中具备事实来源，R8 的
diagnostics.collect 读取当前页 console/pageerror/performance/lifecycle。

### R9: Tool Catalog and UX

- [x] 新增 `browser.network.*` function definitions。
- [x] 新增 `browser.dom.*` function definitions。
- [x] 新增 `browser.storage.*` deep functions。
- [x] 新增 `browser.context.*` functions。
- [x] 新增 `browser.diagnostics.*` functions。
- [x] 更新 tool schema examples。
- [x] 更新 result formatter，让 agent 读到紧凑摘要。
- [x] 保留完整 JSON payload 给详情，不把大 body 塞进一级结果。

当前 `configured.browser` catalog 已包含 tabs / DOM / deep storage /
environment / diagnostics / context / network functions。schema 提供 profile /
profile_pool 统一运行上下文入口，并为常用 browser 操作、context lease、
network capture、diagnostics 写入示例。工具返回对 agent 展示紧凑摘要；
截图、下载、trace 等大 payload 通过 artifact/content block 传递，普通 details
中只保留附件标记。

### R10: Operations and Settings

- [x] `/operations/browser` 增加 network capture projection。
- [x] `/operations/browser` 增加 context lease projection。
- [x] `/operations/browser` 增加 diagnostics projection。
- [x] Settings Browser profile/pool policy 接入新能力开关。
- [x] i18n 覆盖所有新 browser 文案。

`/operations/browser` 当前通过 Browser query service 展示 profile / pool /
allocation / page / daemon 事实，通过 Operations observed events 侧向展示
network activity 与 diagnostics。network/diagnostics 不读取 browser 进程内存，
因此 API、worker、daemon 分进程运行时仍以事件总线和 Operations observation 为真相。
Settings Browser Profiles 现在通过 Browser owner API 管理 profile / pool 的
租约 target 回收策略：`close_targets_on_release` 和
`close_targets_on_expire` 持久化在 Browser profile/pool 真相中，allocator
释放、drain 或过期租约时按 policy 决定是否关闭租约拥有的 tab。

### R11: Acceptance

- [x] Agent 能在航司/携程类页面中通过 network 找到 XHR 数据。
- [x] Agent 能解释一个元素为什么不可点击。
- [x] Agent 能用当前页面登录态 fetch 一个同源接口。
- [x] Agent 能读取 IndexedDB/Cache 中的可见状态。

验收覆盖：

- `tests/unit/test_browser_playwright_actions.py::test_network_capture_actions_record_and_list_requests`
  覆盖 XHR capture/list/get body、同源 `fetch_as_page`、request replay 和事件脱敏。
- `tests/unit/test_browser_playwright_actions.py::test_dom_inspection_actions_return_layout_style_and_clickability`
  覆盖 DOM inspect / clickability，能返回 blocked overlay 和不可点击原因。
- `tests/unit/test_browser_playwright_actions.py::test_deep_storage_read_tools_use_cdp_and_page_context`
  覆盖 cookies/local/session storage、IndexedDB、CacheStorage 和 ServiceWorker 只读状态。
- `tests/unit/test_browser_profile_allocator.py::test_allocator_honors_least_busy_concurrency_and_release`
  覆盖多 profile pool 下不同 consumer 不会抢同一个 active lease。
- `tests/unit/test_browser_profile_allocator.py::test_allocator_reconcile_marks_allocation_lost_when_targets_disappear`
  覆盖 target lost 后 lease 进入 lost 语义；`BrowserCdpSessionBroker`
  覆盖 CDP target/connection lost 的可恢复错误文案。
- `tests/unit/test_operations_browser_read_model.py::test_browser_operations_projects_network_and_diagnostic_events`
  覆盖 Operations Browser 对 network capture 与 diagnostics 的 read model 投影。
- `tests/unit/test_tool_providers.py::test_browser_source_activation_registers_profile_context_catalog`
  覆盖 `configured.browser` 只暴露稳定 browser function，不暴露 `cdp-raw` 或 per-profile MCP source。
- [x] 多 profile pool 下，两个任务不会抢同一个 lease。
- [x] 浏览器关闭/target lost 后，工具返回可恢复错误和 next action。
- [x] Sensitive headers/body 默认脱敏。
- [x] Operations Browser 页面能看到 capture/lease/diagnostics。
- [x] `cdp-raw` 不作为普通 agent 默认工具出现。

## 推荐施工顺序

1. CDP Session Broker。
2. Network Capture。
3. Network Body / Replay / Page Fetch。
4. DOM Inspect / Clickability。
5. Context Lease。
6. Deep Storage。
7. Diagnostics / Trace。
8. Emulation / Permissions。
9. Operations / Settings / i18n 收口。

优先级理由：

- Network 是 agent 真实理解页面数据的最大增益。
- DOM Inspect 解决“能看见但点不了”的高频失败。
- Context Lease 保证多任务和连续操作不互相打架。
- Storage / Diagnostics / Emulation 是能力补强，不应先于核心工作流。
