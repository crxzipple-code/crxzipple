# Browser Runtime, MCP, and CDP Upgrade Checklist 2026-05-24

> 2026-05-25 更新：本文档中关于 `mcp:browser:{profile}`、
> `configured.mcp.browser_{profile}` 和按 browser profile 生成 Tool MCP Source
> 的设计已被
> [../../reports/browser-tool-source-profile-runtime-redesign-plan-20260525.md](../../reports/browser-tool-source-profile-runtime-redesign-plan-20260525.md)
> 取代。本文只保留 browser host daemon、profile 字段、CDP runtime 和历史背景；
> 后续 Browser tool/source/profile 施工必须以新文档为准，不得继续扩展 per-profile
> Browser MCP Source。

本文档是 Browser runtime 重构的历史施工记录，不再是当前施工入口。当时目标不是
继续维护旧 browser MCP 特殊通道，而是把浏览器运行时收敛为：

```text
daemon host process
  -> browser CDP endpoint
  -> daemon-managed browser MCP endpoint
  -> Tool MCP Source discovery
  -> agent-facing browser tools

local CDP-backed browser tools
  -> Browser application port
  -> same daemon-managed browser CDP endpoint
```

## 冻结口径

- Browser MCP 是 Tool MCP Source 的一种输入，不再由 `modules/browser` 私有治理。
- `chrome-devtools-mcp` 不再作为 browser module 内部 client pool 或 action engine。
- CDP 是 browser runtime 的底层驱动协议，不是默认 agent tool source。
- Daemon 负责 browser host / browser MCP server 的进程生命周期，Browser module 负责
  profile、endpoint、tab/session、generation 和 CDP 语义。
- Tool module 负责 MCP source、tool discovery、tool function catalog 和 tool run lifecycle。
- Local browser tools 只补 MCP 覆盖不到的能力，必须通过 Browser application port 调用，
  不允许自己拼 CDP URL 或启动浏览器。
- Operations 只观察 daemon、browser、tool 事件与 read model，不直接控制 browser runtime。
- 不接受长期双轨兼容。旧 `ChromeMcpClientPool`、`McpControlEngine`、
  `McpBackedActionEngine` 和 browser domain 里的 MCP 配置必须在 cutover 后退场。

## 目标架构

```text
Browser Profile Config
  name
  executable_path
  user_data_dir
  profile_directory
  cdp_host / cdp_port / cdp_url
  proxy policy / proxy binding
  attach_only / autostart / headless

        |
        v

daemon service: host:browser:{profile}
  - start/adopt/stop browser host
  - launch Edge/Chrome/Chromium with CDP
  - healthcheck /json/version
  - write runtime manifest
  - publish daemon/browser host events

        |
        v

daemon service: mcp:browser:{profile}
  - requires host:browser:{profile} ready
  - launch mcp-proxy + chrome-devtools-mcp
  - pass --browserUrl=http://127.0.0.1:{cdp_port}
  - expose HTTP MCP endpoint
  - publish MCP endpoint readiness

        |
        v

Tool MCP Source
  - connect HTTP MCP endpoint
  - tools/list -> ToolFunction candidates
  - reconcile into Tool-owned catalog
  - agent normal browser operations use these tools

        |
        v

Browser Module CDP Surface
  - profile resolution
  - CDP endpoint and tab/session state
  - host_generation / page_generation
  - CDP-backed service methods for local tools
```

## 当前基线

- `daemon` 已有 `browser-stack` service set，且 `host:browser:{profile}` service spec
  已按 browser profile 生成。
- `daemon` 已有 `DaemonInstance` 和 file-backed instance store，可作为 runtime
  manifest 的落点。
- `modules/browser` 已收敛为 CDP-only 执行面：
  - `CdpControlEngine`
  - `CdpBackedPlaywrightActionEngine`
- `BrowserSystemConfig` 已移除 Browser 私有 MCP 配置。
- `existing-session` 已路由到 attach-only CDP。
- `CdpControlEngine` 不再 `Popen` 浏览器进程；managed host launch 已迁入
  daemon `browser host run` 使用的 `BrowserHostProcessRunner`。
- 当前 browser profile 支持 `user_data_dir`、`profile_directory`、proxy policy、
  autostart、host metadata、adopt/stale 判断和 launch fingerprint。
- Tool MCP source 已进入 Tool-owned source/function catalog；browser MCP 已从 Browser
  module 私有通道切到 daemon-managed MCP service + Tool MCP Source。

## 2026-05-24 施工进展

- 已把 browser profile 目标字段接入领域模型、core env 解析、state root、HTTP/CLI
  profile 管理、profile payload 和 daemon host spec metadata：
  - `profile_directory`
  - `autostart`
  - `proxy_mode`
  - `proxy_server`
  - `proxy_bypass_list`
  - `proxy_binding_id`
- 已补定向测试覆盖 state 持久化、env 解析、HTTP create/update 和 daemon spec metadata。
- 已让 daemon spec 为 managed profile 产出标准 `mcp:browser:{profile}` lazy 服务：
  - `host_service_key` / `requires_service_key` 指向 `host:browser:{profile}`
  - `command_argv` 使用 `mcp-proxy + chrome-devtools-mcp --browserUrl=<cdp>`
  - `server_url`、`mcp_endpoint`、`mcp_ping_url` 写入 metadata
- Tool MCP provider 已拆出 `stdio` / `http` transport：
  - `stdio` 继续使用 command。
  - `http` 使用 `endpoint_url`，可对接 daemon-managed browser MCP endpoint。
  - discovery/runtime 统一通过 `build_mcp_client` 获取 transport-specific client。
- 已让 managed browser profile 自动注册为 Tool MCP Source：
  - source id 使用 `configured.mcp.browser_{profile}`。
  - HTTP endpoint 指向 daemon `mcp:browser:{profile}` 暴露的 `/mcp`。
  - source config 带 browser profile 安全元数据：`profile_name`、`driver`、
    `host_service_key`、`mcp_service_key`、`mcp_endpoint`、`cdp_endpoint`。
  - 启动时只 upsert source，不强制 `tools/list`，避免 lazy MCP endpoint 未拉起时把
    source 标成 error。
  - 重启注册时保留已有 discovery 状态，不把已完成的 tools/list 结果清空。
  - discovered browser MCP function 继承 `daemon:mcp:browser:{profile}` runtime
    requirement。
- 已把 `existing-session` 从 browser 私有 MCP 生产路径切到 attach-only CDP：
  - profile 可保留 `cdp_url` / `cdp_port`。
  - capabilities 使用 `cdp-control` + `cdp-backed-playwright`。
  - daemon 不再生成旧 browser-private MCP service spec。
  - browser app assembly 不再实例化 `ChromeMcpClientPool` / `McpControlEngine` /
    `McpBackedActionEngine`。
  - browser profile diagnostics 和 local browser tool guidance 不再提示修复 Browser 私有 MCP。
  - browser CLI 移除了旧 `browser mcp run` 入口。
- Daemon manager 已执行 spec-level `requires_service_key`：
  - ensure/reconcile `mcp:browser:{profile}` 前会先 ensure `host:browser:{profile}`。
  - dependency cycle 会 fail fast。
- 旧 Browser 私有 MCP 特殊通道已从生产代码、公共导出和 dedicated test surface 删除。
- `mcp:browser:{profile}` 作为 daemon 托管的标准 MCP service，被 Tool MCP Source 消费。
- 已新增 `BrowserHostProcessRunner`：
  - `browser host run` 负责拉起并持有 managed browser process。
  - 支持 Chrome / Chromium / Edge / Brave executable path 查找。
  - 启动参数覆盖 CDP endpoint、`user_data_dir`、`profile_directory`、headless、
    static proxy server 和 bypass list。
  - 启动后轮询 `/json/version`，并把 `pid`、`endpoint`、profile、CDP、proxy
    metadata 写回 `DaemonInstance`。
  - `CdpControlEngine` 缺 host 时只报告 daemon failed/setup-needed，不再自行启动或杀进程。

## Browser Host Daemon

`host:browser:{profile}` 是浏览器本体的守护服务，职责只包括进程与 endpoint：

- 启动或接管 Edge/Chrome/Chromium。
- 注入启动参数：
  - `--remote-debugging-address`
  - `--remote-debugging-port`
  - `--remote-allow-origins`
  - `--user-data-dir`
  - `--profile-directory`
  - `--proxy-server`
  - `--proxy-bypass-list`
  - `--headless=new`
  - `--no-sandbox`
  - `--no-first-run`
  - `--no-default-browser-check`
- 探活 `/json/version`。
- 记录 `pid`、`endpoint`、profile、launch fingerprint、generation 和最近健康状态。
- 对 managed profile 执行 restart / stop。
- 对 attach-only profile 只探活和观察，不启动、不杀进程。

Browser Host Daemon 不做：

- 不执行 click、fill、snapshot。
- 不注册工具。
- 不解析页面。
- 不读取 cookie、token 或页面内容。
- 不保存 agent-facing observation。

## Browser MCP Daemon

`mcp:browser:{profile}` 是 browser MCP server/proxy 的守护服务，职责只包括 MCP
server 进程和 HTTP MCP endpoint：

```text
mcp-proxy --host 127.0.0.1 --port {mcp_port} --transport streamablehttp --stateless \
  -- npx -y chrome-devtools-mcp@latest \
       --browserUrl=http://127.0.0.1:{cdp_port} \
       --experimentalStructuredContent \
       --experimentalPageIdRouting
```

规则：

- `mcp:browser:{profile}` 必须依赖 `host:browser:{profile}` ready。
- MCP transport 面向 Tool Source 暴露 HTTP MCP endpoint。
- Tool module 负责 discovery 和 function catalog，daemon 不解释 MCP tool schema。
- Daemon MCP spec 和 Tool MCP source 共同消费 `BrowserMcpEndpointPlan`，避免
  `cdp_port`、`mcp_port`、endpoint 和 runtime requirement 双边重复推导。
- Browser MCP source 注册是 runtime integration activation，不属于 Tool module-local
  activation；单独装配 Tool module 时不能反向依赖 Browser infrastructure。
- MCP endpoint 默认 lazy，不随 daemon 启动全部拉起；只有 profile/source 明确开启时才
  autostart。

## CDP Browser Module

Browser module 保留 CDP runtime 语义：

- browser profile config 和 profile admin。
- CDP endpoint 解析与 health context。
- tab list、active target、page/session state。
- `host_generation`、`tab_generation`、`page_generation`、`snapshot_generation`。
- CDP-backed capabilities：
  - PDF / print
  - download behavior and wait
  - cookies / storage
  - network deep inspect
  - console / exception stream
  - frame / worker / target diagnostics
  - raw CDP debug escape hatch

Browser module 不再保留：

- `ChromeMcpClientPool`
- `McpControlEngine`
- `McpBackedActionEngine`
- domain-level `mcp_command`
- `existing-session -> mcp-control` routing

## Runtime Manifest

Manifest 是 daemon-owned runtime fact，建议落在 `DaemonInstance.metadata`，不新建一套
平行真相。

来源：

```text
browser profile config
+ daemon service spec
+ process start/adopt result
+ CDP healthcheck result
= daemon-owned runtime manifest
```

建议字段：

```json
{
  "service_key": "host:browser:work-edge",
  "profile_name": "work-edge",
  "managed_by": "crxzipple",
  "pid": 12345,
  "process_id": "process-session-id",
  "endpoint": "http://127.0.0.1:18800",
  "cdp_host": "127.0.0.1",
  "cdp_port": 18800,
  "executable_path": "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
  "user_data_dir": "/Users/me/.crxzipple/browser-profiles/work-edge",
  "profile_directory": "Default",
  "proxy_mode": "none",
  "proxy_binding_id": null,
  "launch_fingerprint": "sha256:...",
  "host_generation": "2026-05-24T12:00:00Z:...",
  "adopted": false,
  "last_healthcheck_at": "2026-05-24T12:00:01Z"
}
```

Manifest 不允许记录：

- Access secret。
- proxy 用户名/密码。
- cookie、localStorage、token。
- page snapshot、raw DOM、tool result。

## 拉起流程

```text
ensure host:browser:{profile}
  -> load desired service spec
  -> load last DaemonInstance manifest
  -> probe manifest pid and CDP endpoint
  -> scan matching process by cdp_port, user_data_dir, profile_directory
  -> if attach-only:
       endpoint ready -> ready/adopted
       endpoint unavailable -> disconnected/failed, do not launch
  -> if managed:
       valid existing process -> adopted/ready
       no valid process -> launch browser
  -> poll /json/version
  -> write DaemonInstance manifest
  -> publish daemon/browser events
  -> notify Browser module that host_generation changed
  -> Browser module clears stale refs/snapshots
```

默认启动策略：

- Default managed browser host: `autostart=true`。
- Additional managed browser hosts: profile-specific, default `autostart=false` unless configured.
- Attach-only profile: never autostart.
- Browser MCP daemon: default lazy, source/profile can opt into autostart.

## Adopt, Stale, and Conflict

Daemon refresh/reconcile 必须先 adopt，再 launch。

状态建议：

```text
unknown
-> discovering
-> adopted | starting
-> ready
-> degraded
-> stale
-> conflict
-> stopped
-> failed
```

规则：

- Manifest pid 存活、命令行匹配、CDP healthcheck 成功：`adopted/ready`。
- Manifest pid 不存在，CDP endpoint 不通：`stale`。
- Managed + autostart profile 遇到 stale：可以重新 launch。
- Lazy profile 遇到 stale：只记录，等 ensure 时 launch。
- Attach-only profile 遇到 stale/disconnected：不 launch。
- Port 被非本 profile 占用：`conflict`，不直接杀。
- 有 manifest 且 owner/fingerprint 能证明是 CRXZipple 旧实例：可 stop/restart。
- 陌生浏览器进程：只观察，不杀。

## Page State and Ref Staleness

Daemon 只保证 host ready，不保证页面事实连续。Browser module 必须管理 generation：

- `host_generation`: browser host process / endpoint generation。
- `tab_generation`: tab list generation。
- `page_generation`: navigation, reload, target replacement, user intervention。
- `snapshot_generation`: snapshot/ref generation。

旧 ref 失效条件：

- host generation 变化。
- endpoint 变化。
- tab closed/reopened。
- navigation/reload。
- user 手动操作导致 URL/title/frame tree 变化。
- 新 snapshot 覆盖旧 snapshot。

依赖 ref 的 local browser tools 必须校验 generation，不匹配时返回
`snapshot_stale`，不能盲目执行旧 ref。

MCP browser tools 的 `take_snapshot` 每次读取当前页面，但 CRXZipple 自己的 ref store
也必须绑定 generation。

## Proxy and Credentials

代理出口属于 browser host launch 配置，不属于 MCP Source。

推荐 profile proxy config：

```json
{
  "proxy": {
    "mode": "none | static | access_binding",
    "server": "socks5://127.0.0.1:7890",
    "bypass_list": ["127.0.0.1", "localhost", "<local>"],
    "credential_binding_id": "proxy-work-ip"
  }
}
```

规则：

- 无认证代理可以直接进入 `--proxy-server`。
- 有认证代理不能把 secret 写进命令行。
- Access module 持有代理凭证和 readiness。
- 需要认证时用本地 proxy adapter：
  - 浏览器只连 `127.0.0.1:{local_proxy_port}`。
  - adapter 从 Access 取凭证连真实代理。
- Operations 显示 proxy mode、readiness、出口检测结果，不显示 secret。

## Local Browser Tools

Local browser tools 是 MCP 覆盖缺口的 curated functions，不是第二套 browser
automation 主入口。

优先补这些能力：

- `browser_pdf`
- `browser_download`
- `browser_cookie`
- `browser_storage`
- `browser_network_inspect`
- `browser_console_events`
- `browser_cdp_raw`

规则：

- local browser tools 通过 Browser application port 调 CDP service。
- 不允许 handler 直接读取 `DaemonInstance` 或拼 endpoint。
- 不允许 handler 自己启动 browser host。
- raw CDP 默认禁用，需要独立 high-risk effect，例如 `browser.cdp.raw`。

## Operations Read Model

Operations 应分别观察：

- `host:browser:{profile}` daemon instance。
- `mcp:browser:{profile}` daemon instance。
- browser profile readiness 和 generation。
- tool MCP source discovery status。
- browser local tool run status。
- conflict/stale/adopted/restarted events。
- proxy readiness 和出口检测结果。

不要把 host、MCP source、tool run、browser page state 混成一个状态字段。

当前已落地：

- Daemon operations instance 表区分 Browser Host 和 Browser MCP runtime。
- Tool operations source health 表显示 Browser MCP Source 的 endpoint、host -> MCP
  dependency、`tools/list` 状态和 active/total function 数。

## Development Checklist

### P0 Inventory and Guards

- [x] 列出所有 `ChromeMcpClientPool`、`McpControlEngine`、`McpBackedActionEngine`
  引用点。
- [x] 列出 browser domain/config 中所有 MCP 字段和 `existing-session` 路由点。
- [x] 增加架构测试，禁止 `modules/browser` 引用 `chrome-devtools-mcp` 或 MCP client。
- [x] 增加架构测试，禁止 local browser tool handler 直接访问 container、daemon store 或 CDP URL。

### P1 Browser Profile Model

- [x] 给 browser profile 增加 `profile_directory`。
- [x] 给 browser profile 增加 proxy policy 和 `proxy_binding_id`。
- [x] 给 browser profile 增加 `autostart` / `keep_warm`。
- [x] 明确 attach-only profile 不可自动 launch。
- [x] 从 browser domain 移除 `mcp_command` / `mcp_timeout_seconds`。
- [x] 更新 Browser Profile HTTP / CLI create/update payload。

### P2 Daemon Service Specs

- [x] `host:browser:{profile}` spec 包含 profile launch metadata。
- [x] `mcp:browser:{profile}` spec 由 MCP source/profile 配置生成。
- [x] `mcp:browser:{profile}` 显式依赖 `host:browser:{profile}` ready。
- [x] daemon 已能为 managed profile 生成 profile-driven `mcp:browser:{profile}` lazy
  service skeleton。
- [x] `browser-stack` 默认只 include eager/ensure host services，不自动 include lazy MCP
  capability services。

### P3 Browser Host Runner

- [x] 把 browser launch 命令收进 daemon-managed host runner。
- [x] `CdpControlEngine` 不再 `Popen` browser。
- [x] host runner 支持 Edge/Chrome/Chromium executable path。
- [x] host runner 支持 `user_data_dir` 和 `profile_directory`。
- [x] host runner 支持 proxy server / bypass list。
- [x] host runner 启动后轮询 `/json/version`。
- [x] host runner 写入标准 DaemonInstance metadata。

### P4 Adopt and Manifest

- [x] Daemon refresh 先读旧 `DaemonInstance` manifest。
- [x] 按 pid/process session adopt 已存在 host。
- [x] host runner 按 cdp_port + user_data_dir + profile_directory 扫描匹配进程并 adopt。
- [x] host runner 写入 launch fingerprint，供后续 restart/adopt 判断。
- [x] stale manifest 不继续标 ready。
- [x] host runner 遇到 conflict 进程不直接杀，且不把完整 command 写入 manifest。
- [x] host runner manifest 不记录 secret、cookie、snapshot 或 raw DOM。

### P5 Browser MCP Source Cutover

- [x] 使用 daemon 托管 `mcp-proxy + chrome-devtools-mcp`。
- [x] Tool MCP Source 支持连接 HTTP MCP endpoint。
- [x] Browser managed profile 自动注册为 Tool MCP Source，但启动时不强制 discovery。
- [x] Browser MCP function 携带 daemon runtime requirement。
- [x] `existing-session` 生产路径切为 attach-only CDP，不再走 browser 私有 MCP engine。
- [x] daemon 不再生成旧 browser-private MCP service spec。
- [x] daemon ensure/reconcile 执行 `requires_service_key`，MCP service 会先拉 host。
- [x] 移除 browser CLI 旧 `browser mcp run` 入口。
- [x] Browser module 删除历史 MCP class/test surface。
- [x] Tool source discovery 将 browser MCP tools reconciled into `ToolFunction` catalog。
- [x] browser MCP source readiness 展示 host dependency、MCP endpoint、tools/list 状态。
- [x] Browser MCP source 注册从 Tool module-local activation 拆到 runtime integration
  activation，避免 tool-only 装配反向要求 Browser infrastructure。

### P6 Browser Module CDP-only Cleanup

- [x] 删除 `ChromeMcpClientPool` 生产路径。
- [x] 删除 `McpControlEngine` 生产路径。
- [x] 删除 `McpBackedActionEngine` 生产路径。
- [x] `existing-session` 不再表示 MCP；改成 attach-existing-CDP。
- [x] Browser facade 只暴露 profile/control/page action/CDP query service。
- [x] CDP service 统一通过 daemon host endpoint 获取当前 browser ref。

### P7 Generation and Stale Ref

- [x] 增加 `host_generation`。
- [x] 增加 `page_generation` 和 `snapshot_generation`。
- [x] ref store 绑定 generation。
- [x] host generation 变化时清空 profile refs/snapshots。
- [x] 依赖旧 ref 的 action 检测 generation；当前语义允许 anchored/semantic rebind，
  无法重绑时返回 stale error；Operations 通过 browser observation/read model 展示
  stale 状态，不在 tool/browser action 内做额外投影。
- [x] Browser profile/status payload 暴露脱敏的 host/page/snapshot generation summary。
- [x] Operations 展示 page observation 是否 stale。

### P8 Local Browser Tool Completion

- [x] 定义 local browser tool package manifest。
- [x] `browser_pdf` 通过 Browser CDP port 实现。
- [x] `browser_download` 通过 Browser CDP port 实现。
- [x] `browser_storage` / `browser_cookie` 通过 Browser CDP port 实现。
- [x] `browser_console_events` 通过 Browser CDP port 实现。
- [x] `browser_network_inspect` 通过 Browser CDP port 实现。
- [x] `browser_cdp_raw` 默认 disabled，并绑定 high-risk effect。

### P9 Access and Proxy Readiness

- [x] 定义 proxy credential requirement。
- [x] Access 提供 proxy credential readiness。
- [x] 有认证代理走本地 proxy adapter，不把 secret 写入 launch command。
- [x] Tool readiness 能解释 browser proxy setup_needed。
- [x] Operations 显示 proxy readiness。
- [x] Operations 显示出口 IP check。

Notes:

- Proxy credential requirement uses `browser_proxy:basic(proxy)` and is projected
  as an external Access consumer for `browser_profile_proxy`.
- Static proxy URLs with embedded credentials are rejected by browser profile
  validation. Authenticated proxy forwarding now runs through a browser-owned
  local HTTP proxy adapter, so Chrome only receives `127.0.0.1:{port}` in
  `--proxy-server`.
- Authenticated proxy adapter currently supports upstream `http://` /
  `https://` proxy endpoints with Basic credentials resolved through Access
  (`username:password`, `Basic ...`, or JSON username/password). SOCKS proxy
  auth is intentionally not represented as a credential-bearing browser launch
  flag.
- Browser host metadata records safe proxy facts only: binding id, local proxy
  URL, upstream endpoint, adapter kind, and optional egress check status/IP.
  Secret values are not written to daemon metadata or process argv.
- Egress IP is checked when `APP_BROWSER_PROXY_EGRESS_CHECK_URL` is configured;
  otherwise Operations reports the check as `not_configured`.

### P10 Operations and UI

- [x] Daemon operations 页面区分 host browser 与 MCP browser：
  - instances 表新增 `Runtime` 语义列。
  - instance detail 摘要展示 Browser Host 的 host runner PID、browser PID、
    manifest/adopted/stale、CDP endpoint、profile、proxy 与 launch fingerprint。
  - instance detail 摘要展示 Browser MCP 的 required host、MCP endpoint 与 CDP endpoint。
- [x] Browser operations 页面展示 profile、endpoint、generation、page observation、daemon runtime 与 stale 标记。
- [x] Tool operations 页面展示 browser MCP source discovery/run 状态。
- [x] 页面文案进入 i18n。
- [x] Skeleton/empty/error 保持布局稳定。

Notes:

- Browser operations page now keeps fallback metric cards and table schemas while
  data is loading or empty, so the first-screen grid does not collapse before
  the projection arrives.
- Browser table columns and dynamic deltas for proxy readiness / egress facts are
  covered by the shared table i18n map and browser-specific i18n keys.

### P11 Tests and Verification

- [x] Unit: profile config parse/create/update。
- [x] Unit: daemon host service spec generation。
- [x] Unit: stale daemon manifest does not become ready from endpoint probe.
- [x] Unit: CDP control detects conflicting/missing host without launching or killing process.
- [x] Unit: host runner startup failure does not overwrite daemon failed state as stopped.
- [x] Unit: daemon host runner conflict process does not get killed.
- [x] Unit: generation change invalidates refs.
- [x] Unit: local browser tools do not direct-read daemon/CDP URL.
- [x] Unit: Browser module does not import MCP client/runtime.
- [x] Unit: Tool operations source health exposes Browser MCP endpoint/dependency/tools-list.
- [x] Unit: Browser facade does not expose daemon/MCP/endpoint internals.
- [x] Unit: CDP control prefers daemon host endpoint over profile fallback URL.
- [x] Unit: browser runtime state records page/snapshot generations across open/navigate/restore.
- [x] Unit: stale refs are generation-checked and either safely rebound or rejected.
- [x] Unit: browser profile payload exposes host/page/snapshot generation summary.
- [x] Integration: managed Edge/Chrome host launch and `/json/version` ready.
- [x] Integration: mcp:browser HTTP endpoint initializes and lists tools.
- [x] Integration: MCP browser tool and local CDP tool share same profile endpoint safely.
- [x] Frontend: operations browser/tool/daemon panels show split statuses.

Notes:

- Live integration tests are intentionally opt-in. A default run of
  `PYTHONPATH=src pytest -q tests/integration/test_browser_live_mcp_smoke.py tests/integration/test_browser_live_remote_cdp_smoke.py tests/integration/test_browser_live_iframe_smoke.py`
  currently reports `4 skipped` until `APP_BROWSER_MCP_LIVE_SMOKE`,
  `APP_BROWSER_REMOTE_CDP_LIVE_SMOKE`, or `APP_BROWSER_LIVE_SMOKE` is enabled.
- Verified opt-in live smoke on 2026-05-25:
  - `APP_BROWSER_MCP_LIVE_SMOKE=1 PYTHONPATH=src pytest -q -rs tests/integration/test_browser_live_mcp_smoke.py`
  - `APP_BROWSER_LIVE_SMOKE=1 PYTHONPATH=src pytest -q -rs tests/integration/test_browser_live_iframe_smoke.py`
  - `APP_BROWSER_REMOTE_CDP_LIVE_SMOKE=1 PYTHONPATH=src pytest -q -rs tests/integration/test_browser_live_remote_cdp_smoke.py`

## Suggested Verification Commands

```bash
PYTHONPATH=src pytest -q tests/unit/test_browser_cdp_control.py
PYTHONPATH=src pytest -q tests/unit/test_browser_http.py tests/unit/test_browser_cli.py
PYTHONPATH=src pytest -q tests/unit/test_daemon_manager.py tests/unit/test_daemon_http.py
PYTHONPATH=src pytest -q tests/unit/test_tool_providers.py tests/unit/test_tool_http.py
PYTHONPATH=src pytest -q tests/unit/test_module_lifecycle_architecture.py

cd frontend
npm run typecheck
npm run build
```

Live smoke should be explicit and not part of default unit hot path:

```bash
make dev-up
python -m crxzipple.main daemon status
python -m crxzipple.main daemon ensure host:browser:crxzipple
python -m crxzipple.main daemon ensure mcp:browser:crxzipple
```

## Verification Log

2026-05-24 本轮已跑：

```bash
PYTHONPATH=src pytest -q tests/unit/test_app_assembly_targets.py
PYTHONPATH=src pytest -q tests/unit/test_browser_state.py tests/unit/test_config.py tests/unit/test_browser_http.py::BrowserHttpTestCase::test_browser_profile_management_endpoints_manage_state_root
PYTHONPATH=src pytest -q tests/unit/test_tool_mcp_client.py tests/unit/test_tool_settings_integration.py tests/unit/test_tool_providers.py::ToolProvidersTestCase::test_discovers_and_executes_mcp_remote_tools
PYTHONPATH=src pytest -q tests/unit/test_tool_http.py::ToolHttpTestCase::test_mcp_provider_endpoints_discover_and_execute_remote_tools tests/unit/test_tool_cli.py::ToolCliTestCase::test_tool_mcp_provider_commands_discover_and_execute_remote_tools
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/tool/infrastructure/mcp_client.py src/crxzipple/core/config.py src/crxzipple/app/assembly/daemon.py src/crxzipple/modules/browser/domain/value_objects.py
PYTHONPATH=src pytest -q tests/unit/test_app_assembly_targets.py tests/unit/test_config.py::ConfigTestCase::test_load_settings_reads_http_mcp_provider tests/unit/test_tool_settings_integration.py::ToolSettingsIntegrationTestCase::test_http_mcp_provider_mapping_converts_to_bootstrap_settings
PYTHONPATH=src pytest -q tests/unit/test_tool_mcp_client.py tests/unit/test_tool_providers.py::ToolProvidersTestCase::test_discovers_and_executes_mcp_remote_tools
PYTHONPATH=src python -m compileall -q src/crxzipple/app/assembly/tool.py src/crxzipple/app/assembly/daemon.py src/crxzipple/core/config.py src/crxzipple/modules/tool/application/settings_integration.py src/crxzipple/modules/tool/infrastructure/provider_catalog.py
PYTHONPATH=src pytest -q tests/unit/test_app_assembly_targets.py tests/unit/test_browser_state.py tests/unit/test_browser_http.py::BrowserHttpTestCase::test_browser_profile_management_endpoints_manage_state_root
PYTHONPATH=src pytest -q tests/unit/test_browser_domain.py tests/unit/test_app_assembly_targets.py
PYTHONPATH=src pytest -q tests/unit/test_daemon_manager.py::DaemonManagerTestCase::test_ensure_service_starts_required_service_first tests/unit/test_daemon_manager.py::DaemonManagerTestCase::test_ensure_process_backed_capability_can_use_raw_command_argv
PYTHONPATH=src pytest -q tests/unit/test_config.py::ConfigTestCase::test_load_settings_reads_browser_profile_runtime_fields tests/unit/test_tool_settings_integration.py::ToolSettingsIntegrationTestCase::test_http_mcp_provider_mapping_converts_to_bootstrap_settings
PYTHONPATH=src python -m compileall -q src/crxzipple/app/assembly/browser.py src/crxzipple/app/assembly/daemon.py src/crxzipple/app/assembly/tool.py src/crxzipple/modules/browser/application/services.py src/crxzipple/modules/browser/domain/value_objects.py src/crxzipple/modules/browser/infrastructure/profile_probe.py src/crxzipple/modules/browser/infrastructure/registry.py
PYTHONPATH=src pytest -q tests/unit/test_browser_domain.py tests/unit/test_browser_http.py::BrowserHttpTestCase::test_browser_profile_management_endpoints_manage_state_root
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/browser/interfaces/profile_payloads.py tools/browser/local.py
PYTHONPATH=src pytest -q tests/unit/test_browser_cli.py::BrowserCliTestCase::test_browser_mcp_run_is_not_a_browser_module_command
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/browser/interfaces/cli.py tests/unit/test_browser_cli.py
PYTHONPATH=src pytest -q tests/unit/test_browser_*.py
PYTHONPATH=src pytest -q tests/unit/test_daemon_manager.py tests/unit/test_daemon_cli.py tests/unit/test_daemon_domain.py tests/unit/test_app_assembly_targets.py tests/unit/test_tool_mcp_client.py tests/unit/test_tool_providers.py::ToolProvidersTestCase::test_discovers_and_executes_mcp_remote_tools tests/unit/test_tool_http.py::ToolHttpTestCase::test_mcp_provider_endpoints_discover_and_execute_remote_tools tests/unit/test_tool_cli.py::ToolCliTestCase::test_tool_mcp_provider_commands_discover_and_execute_remote_tools
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/browser src/crxzipple/app/assembly
python -m compileall -q src/crxzipple/modules/browser/infrastructure/host_runner.py src/crxzipple/modules/browser/infrastructure/engines.py src/crxzipple/modules/browser/interfaces/cli.py tests/unit/test_browser_cdp_control.py
PYTHONPATH=src pytest -q tests/unit/test_browser_cdp_control.py
PYTHONPATH=src pytest -q tests/unit/test_browser_cli.py::BrowserCliTestCase::test_browser_host_run_uses_host_loop tests/unit/test_browser_cdp_host_daemon.py
PYTHONPATH=src pytest -q tests/unit/test_browser_*.py
python -m compileall -q src/crxzipple/modules/browser/domain/entities.py src/crxzipple/modules/browser/infrastructure/engines.py src/crxzipple/modules/browser/infrastructure/host_runner.py src/crxzipple/modules/browser/application/services.py tests/unit/test_browser_cdp_control.py
PYTHONPATH=src pytest -q tests/unit/test_browser_cdp_control.py
PYTHONPATH=src pytest -q tests/unit/test_browser_domain.py tests/unit/test_browser_state.py
PYTHONPATH=src pytest -q tests/unit/test_browser_*.py
PYTHONPATH=src pytest -q tests/unit/test_daemon_manager.py tests/unit/test_daemon_cli.py tests/unit/test_daemon_domain.py tests/unit/test_app_assembly_targets.py
PYTHONPATH=src pytest -q tests/unit/test_tool_mcp_client.py tests/unit/test_tool_providers.py::ToolProvidersTestCase::test_discovers_and_executes_mcp_remote_tools tests/unit/test_tool_http.py::ToolHttpTestCase::test_mcp_provider_endpoints_discover_and_execute_remote_tools tests/unit/test_tool_cli.py::ToolCliTestCase::test_tool_mcp_provider_commands_discover_and_execute_remote_tools
python -m compileall -q src/crxzipple/modules/daemon/application/manager.py tests/unit/test_daemon_manager.py
PYTHONPATH=src pytest -q tests/unit/test_daemon_manager.py::DaemonManagerTestCase::test_missing_browser_host_runner_session_marks_manifest_stale_without_endpoint_probe tests/unit/test_daemon_manager.py::DaemonManagerTestCase::test_healthcheck_service_marks_browser_host_ready_via_cdp_probe
PYTHONPATH=src pytest -q tests/unit/test_daemon_manager.py tests/unit/test_daemon_cli.py tests/unit/test_daemon_domain.py tests/unit/test_app_assembly_targets.py
PYTHONPATH=src pytest -q tests/unit/test_browser_*.py
PYTHONPATH=src pytest -q tests/unit/test_tool_mcp_client.py tests/unit/test_tool_providers.py::ToolProvidersTestCase::test_discovers_and_executes_mcp_remote_tools tests/unit/test_tool_http.py::ToolHttpTestCase::test_mcp_provider_endpoints_discover_and_execute_remote_tools tests/unit/test_tool_cli.py::ToolCliTestCase::test_tool_mcp_provider_commands_discover_and_execute_remote_tools
python -m compileall -q src/crxzipple/modules/operations/application/read_models/daemon.py tests/unit/test_operations_daemon_read_model.py
PYTHONPATH=src pytest -q tests/unit/test_operations_daemon_read_model.py
PYTHONPATH=src pytest -q tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_operations_daemon_page_uses_refreshed_runtime_state
PYTHONPATH=src pytest -q tests/unit/test_daemon_manager.py::DaemonManagerTestCase::test_missing_browser_host_runner_session_marks_manifest_stale_without_endpoint_probe tests/unit/test_daemon_manager.py::DaemonManagerTestCase::test_healthcheck_service_marks_browser_host_ready_via_cdp_probe
python -m compileall -q tests/unit/test_module_lifecycle_architecture.py
PYTHONPATH=src pytest -q tests/unit/test_module_lifecycle_architecture.py::test_browser_module_does_not_reintroduce_private_mcp_runtime tests/unit/test_module_lifecycle_architecture.py::test_local_browser_tool_handlers_do_not_direct_read_daemon_or_cdp_runtime
python -m compileall -q tests/unit/test_tool_providers.py
PYTHONPATH=src pytest -q tests/unit/test_tool_providers.py::ToolProvidersTestCase::test_browser_mcp_source_sync_reconciles_remote_tools_into_catalog
python -m compileall -q src/crxzipple/app/assembly/tool.py src/crxzipple/modules/operations/application/read_models/tool.py tests/unit/test_tool_providers.py tests/unit/test_app_assembly_targets.py
PYTHONPATH=src pytest -q tests/unit/test_app_assembly_targets.py::test_browser_mcp_tool_source_registers_lazy_http_provider
PYTHONPATH=src pytest -q tests/unit/test_tool_providers.py::ToolProvidersTestCase::test_browser_mcp_source_sync_reconciles_remote_tools_into_catalog
python -m compileall -q tests/unit/test_operations_tool_read_model.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_read_model.py
PYTHONPATH=src pytest -q tests/unit/test_tool_providers.py::ToolProvidersTestCase::test_browser_mcp_source_sync_reconciles_remote_tools_into_catalog tests/unit/test_app_assembly_targets.py::test_browser_mcp_tool_source_registers_lazy_http_provider
PYTHONPATH=src pytest -q tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_operations_tool_page_uses_tool_runtime_state
python -m compileall -q tests/unit/test_module_lifecycle_architecture.py
PYTHONPATH=src pytest -q tests/unit/test_module_lifecycle_architecture.py::test_browser_interface_facade_stays_thin_application_surface tests/unit/test_module_lifecycle_architecture.py::test_browser_module_does_not_reintroduce_private_mcp_runtime
python -m compileall -q src/crxzipple/modules/browser/infrastructure/engines.py tests/unit/test_browser_cdp_control.py
PYTHONPATH=src pytest -q tests/unit/test_browser_cdp_control.py::BrowserCdpControlTestCase::test_cdp_control_engine_prefers_daemon_host_endpoint_over_profile_url tests/unit/test_browser_cdp_control.py::BrowserCdpControlTestCase::test_cdp_control_engine_requires_daemon_host_when_managed_cdp_missing
PYTHONPATH=src pytest -q tests/unit/test_browser_cdp_control.py
PYTHONPATH=src pytest -q tests/unit/test_browser_cdp_host_daemon.py
python -m compileall -q src/crxzipple/modules/browser/domain/entities.py src/crxzipple/modules/browser/application/services.py src/crxzipple/modules/browser/infrastructure/engines.py tests/unit/test_browser_domain.py tests/unit/test_browser_cdp_control.py
PYTHONPATH=src pytest -q tests/unit/test_browser_domain.py::BrowserDomainTestCase::test_execution_coordinator_navigate_clears_tab_refs tests/unit/test_browser_domain.py::BrowserDomainTestCase::test_runtime_state_can_restore_page_ref_session_from_stored_refs
PYTHONPATH=src pytest -q tests/unit/test_browser_domain.py
PYTHONPATH=src pytest -q tests/unit/test_browser_cdp_control.py tests/unit/test_browser_domain.py tests/unit/test_browser_state.py
PYTHONPATH=src pytest -q tests/unit/test_browser_playwright_actions.py::BrowserPlaywrightActionEngineTestCase::test_stale_ref_rebinds_to_semantic_role_locator tests/unit/test_browser_playwright_actions.py::BrowserPlaywrightActionEngineTestCase::test_click_rejects_stale_ref_after_new_snapshot_generation tests/unit/test_browser_playwright_actions.py::BrowserPlaywrightActionEngineTestCase::test_click_can_rebind_stale_ref_within_scoped_container
python -m compileall -q src/crxzipple/modules/browser/application/runtime_payloads.py src/crxzipple/modules/browser/application/services.py src/crxzipple/modules/browser/interfaces/profile_payloads.py tests/unit/test_browser_http.py
PYTHONPATH=src pytest -q tests/unit/test_browser_http.py::BrowserHttpTestCase::test_browser_snapshot_endpoint_exposes_frame_path
PYTHONPATH=src pytest -q tests/unit/test_browser_http.py
PYTHONPATH=src pytest -q tests/unit/test_browser_domain.py tests/unit/test_browser_state.py
python -m compileall -q src/crxzipple/app/keys.py src/crxzipple/app/assembly/browser.py src/crxzipple/app/assembly/operations.py src/crxzipple/interfaces/http/ui.py src/crxzipple/modules/browser/application/query.py src/crxzipple/modules/browser/application/__init__.py src/crxzipple/modules/operations/application/read_models/browser.py src/crxzipple/modules/operations/application/read_models/factory.py src/crxzipple/modules/operations/application/read_models/facade.py src/crxzipple/modules/operations/application/read_models/modules.py src/crxzipple/modules/operations/application/read_models/__init__.py src/crxzipple/modules/operations/application/projections.py src/crxzipple/modules/operations/interfaces/http.py src/crxzipple/modules/operations/interfaces/http_models.py tests/unit/test_operations_browser_read_model.py tests/unit/test_app_assembly_module_local.py
PYTHONPATH=src pytest -q tests/unit/test_operations_browser_read_model.py tests/unit/test_operations_read_model_boundaries.py
PYTHONPATH=src pytest -q tests/unit/test_app_assembly_module_local.py::test_browser_factory_builds_profile_runtime_infrastructure tests/unit/test_module_lifecycle_architecture.py::test_operations_source_read_model_context_is_explicitly_typed
cd frontend && npm run typecheck
cd frontend && npm run build
python -m compileall -q src/crxzipple/modules/tool/application/catalog_models.py src/crxzipple/modules/browser/domain/value_objects.py src/crxzipple/modules/browser/infrastructure/action_engines.py tools/browser/local.py tests/unit/test_browser_tool_http.py tests/unit/test_browser_playwright_actions.py tests/unit/test_tool_catalog.py
PYTHONPATH=src pytest -q tests/unit/test_browser_tool_http.py
PYTHONPATH=src pytest -q tests/unit/test_browser_playwright_actions.py
PYTHONPATH=src pytest -q tests/unit/test_tool_catalog.py::ToolCatalogTestCase::test_list_enabled_tools_respects_availability tests/unit/test_tool_catalog.py::ToolCatalogTestCase::test_browser_raw_cdp_tool_is_disabled_and_high_risk_by_default
PYTHONPATH=src python - <<'PY'
from pathlib import Path
from crxzipple.modules.tool.infrastructure.tool_packages import load_tool_package_plan
plan = load_tool_package_plan(Path("tools/browser/tool.yaml"))
ids = [handler.tool.id for handler in plan.local_handlers]
for required in ["browser_pdf", "browser_download", "browser_cookie", "browser_storage", "browser_console_events", "browser_cdp_raw"]:
    assert required in ids, required
raw = next(handler.tool for handler in plan.local_handlers if handler.tool.id == "browser_cdp_raw")
assert raw.enabled is False
assert raw.required_effect_ids == ("local_tool_access", "browser.cdp.raw")
PY
PYTHONPATH=src pytest -q tests/unit/test_browser_domain.py tests/unit/test_browser_state.py
PYTHONPATH=src pytest -q tests/unit/test_module_lifecycle_architecture.py::test_local_browser_tool_handlers_do_not_direct_read_daemon_or_cdp_runtime tests/unit/test_module_lifecycle_architecture.py::test_browser_module_does_not_reintroduce_private_mcp_runtime
PYTHONPATH=src pytest -q tests/unit/test_tool_catalog.py::ToolCatalogTestCase::test_browser_raw_cdp_tool_is_disabled_and_high_risk_by_default
python -m compileall -q src/crxzipple/modules/browser/domain/value_objects.py src/crxzipple/modules/browser/infrastructure/action_engines.py tools/browser/local.py tests/unit/support.py tests/unit/test_browser_tool_http.py tests/unit/test_browser_playwright_actions.py tests/unit/test_tool_catalog.py
PYTHONPATH=src pytest -q tests/unit/test_browser_tool_http.py::BrowserToolHttpTestCase::test_curated_browser_handlers_route_fixed_page_action_kinds tests/unit/test_browser_tool_http.py::BrowserToolHttpTestCase::test_browser_action_rejects_curated_diagnostic_escape_hatches
PYTHONPATH=src pytest -q tests/unit/test_browser_playwright_actions.py::BrowserPlaywrightActionEngineTestCase::test_network_inspect_returns_performance_entries_and_cdp_facts tests/unit/test_browser_playwright_actions.py::BrowserPlaywrightActionEngineTestCase::test_cdp_raw_sends_command_through_page_cdp_session
PYTHONPATH=src pytest -q tests/unit/test_tool_catalog.py::ToolCatalogTestCase::test_browser_network_inspect_tool_is_enabled_read_only_diagnostics tests/unit/test_tool_catalog.py::ToolCatalogTestCase::test_browser_raw_cdp_tool_is_disabled_and_high_risk_by_default
python -m compileall -q src/crxzipple/modules/access/interfaces/external_consumers.py src/crxzipple/modules/browser/domain/value_objects.py src/crxzipple/modules/operations/application/read_models/browser.py src/crxzipple/modules/operations/application/read_models/factory.py tests/unit/test_browser_access_requirements.py tests/unit/test_browser_domain.py tests/unit/test_operations_browser_read_model.py
PYTHONPATH=src pytest -q tests/unit/test_browser_access_requirements.py tests/unit/test_operations_browser_read_model.py::test_browser_operations_projects_proxy_access_binding_readiness tests/unit/test_browser_domain.py::BrowserDomainTestCase::test_static_proxy_rejects_credentials_in_proxy_server
PYTHONPATH=src pytest -q tests/unit/test_access_read_models.py tests/unit/test_browser_access_requirements.py
PYTHONPATH=src pytest -q tests/unit/test_operations_browser_read_model.py tests/unit/test_browser_domain.py tests/unit/test_browser_state.py
PYTHONPATH=src pytest -q tests/unit/test_browser_tool_http.py tests/unit/test_browser_playwright_actions.py tests/unit/test_tool_catalog.py::ToolCatalogTestCase::test_browser_network_inspect_tool_is_enabled_read_only_diagnostics tests/unit/test_tool_catalog.py::ToolCatalogTestCase::test_browser_raw_cdp_tool_is_disabled_and_high_risk_by_default
python -m compileall -q src/crxzipple/modules/tool/infrastructure/adapters/daemon.py src/crxzipple/app/assembly/tool.py tests/unit/test_tool_runtime_readiness.py
PYTHONPATH=src pytest -q tests/unit/test_tool_runtime_readiness.py tests/unit/test_tool_http.py::ToolHttpTestCase::test_tool_readiness_endpoint_blocks_missing_runtime_daemon_before_run_creation
python -m compileall -q src/crxzipple/core/config.py tests/unit/test_config.py src/crxzipple/modules/tool/infrastructure/adapters/daemon.py src/crxzipple/app/assembly/tool.py tests/unit/test_tool_runtime_readiness.py
PYTHONPATH=src pytest -q tests/unit/test_config.py::ConfigTestCase::test_load_settings_reads_browser_profile_runtime_fields tests/unit/test_config.py::ConfigTestCase::test_load_settings_rejects_static_browser_proxy_credentials tests/unit/test_tool_runtime_readiness.py tests/unit/test_tool_http.py::ToolHttpTestCase::test_tool_readiness_endpoint_blocks_missing_runtime_daemon_before_run_creation
```

2026-05-25 收口验证：

```bash
ruff check src/crxzipple
PYTHONPATH=src python -m compileall -q src/crxzipple
python -m compileall -q src/crxzipple/app/assembly/tool.py src/crxzipple/app/assembly/runtime.py tests/unit/test_app_assembly_module_local.py
PYTHONPATH=src pytest -q tests/unit/test_app_assembly_module_local.py::test_tool_activation_task_applies_manifest_packages_from_bindings
PYTHONPATH=src pytest -q tests/unit/test_module_lifecycle_architecture.py tests/unit/test_app_assembly_architecture.py tests/unit/test_app_assembly_module_local.py tests/unit/test_app_assembly_targets.py tests/unit/test_application_port_boundaries.py
PYTHONPATH=src pytest -q tests/unit/test_app_assembly_targets.py tests/unit/test_daemon_manager.py tests/unit/test_daemon_service.py tests/unit/test_tool_providers.py tests/unit/test_tool_mcp_client.py tests/unit/test_tool_runtime_readiness.py tests/unit/test_browser_cdp_control.py tests/unit/test_browser_playwright_actions.py tests/unit/test_browser_tool_http.py tests/unit/test_browser_proxy_adapter.py tests/unit/test_operations_browser_read_model.py
PYTHONPATH=src pytest -q tests/unit/test_browser_cdp_control.py tests/unit/test_browser_playwright_actions.py tests/unit/test_browser_tool_http.py
PYTHONPATH=src pytest -q tests/unit/test_browser_*.py
APP_BROWSER_MCP_LIVE_SMOKE=1 PYTHONPATH=src pytest -q -rs tests/integration/test_browser_live_mcp_smoke.py
ps -axo pid,ppid,pgid,stat,command | rg 'crxzipple-live-mcp|mcp-proxy|chrome-devtools-mcp|remote-debugging-port=.*tmp' || true
cd frontend && npm run typecheck
```

## Cutover Definition

本轮升级完成必须同时满足：

- Browser MCP 只能通过 Tool MCP Source 进入 tool catalog。
- Browser module 生产路径没有 MCP client pool/action engine。
- Browser host 只由 daemon launch/adopt/stop。
- CDP capabilities 通过 Browser application port 给 local tools 使用。
- host/MCP/tool/browser profile 四类状态在 Operations 中可分辨。
- host generation 变化后旧 refs/snapshots 不会被继续使用。
- 旧兼容路径删除或变成明确测试辅助，不能作为生产 fallback。
