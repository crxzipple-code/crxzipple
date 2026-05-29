# Browser Tool Source and Profile Runtime Redesign Plan 2026-05-25

本文档是 Browser tool/source/profile runtime 的当前开发计划。它替代
`../archive/reports/browser-runtime-mcp-cdp-upgrade-checklist-20260524.md` 中关于
`configured.mcp.browser_{profile}`、`mcp:browser:{profile}`、按 profile 暴露
Browser MCP Source 的设计。旧文档只保留 browser host daemon、CDP runtime、
profile 字段和历史背景；后续施工以本文档为准。

## 决策结论

- Browser profile 是运行上下文，不是 Tool Source。
- Browser tool capability 只注册一次，不按 profile 膨胀。
- 退役 per-profile Browser MCP Source：
  - `configured.mcp.browser_user`
  - `configured.mcp.browser_crxzipple`
  - `configured.mcp.browser_{profile}`
- 退役 per-profile Browser MCP daemon：
  - `mcp:browser:user`
  - `mcp:browser:crxzipple`
  - `mcp:browser:{profile}`
- Browser 正常工具能力改为 CRXZipple-owned Browser Local/Provider Source：
  - source id: `configured.browser`
  - function prefix: `browser.*`
- 保留 `host:browser:{profile}`。浏览器进程、user-data-dir、profile directory、
  proxy、CDP endpoint 的隔离天然属于 Browser runtime。
- 不为了 `chrome-devtools-mcp` 的一个 `browserUrl` 边界牺牲 CRXZipple 的 profile
  建模。官方 Browser MCP 可作为未来实验 source，但不作为默认 browser 工具路径。
- 不保留长期兼容 alias。迁移时清理旧 source/function/run-time references，避免 UI 和
  authorization 出现双轨。

## 问题背景

当前实现把每个 browser profile 注册成一个 MCP source：

```text
profile user
  -> mcp:browser:user
  -> configured.mcp.browser_user
  -> mcp.browser_user.take_snapshot

profile crxzipple
  -> mcp:browser:crxzipple
  -> configured.mcp.browser_crxzipple
  -> mcp.browser_crxzipple.take_snapshot
```

这等价于“打开不同 Word 文件要安装多个 Office”。profile 是操作上下文，而不是能力
来源。继续按 profile 生成 source 会带来：

- Tool Source 列表重复。
- Tool Function catalog 重复。
- Tool authorization / trust / approval 重复。
- Operations Tool 页面误把 profile readiness 当 source readiness。
- 新增 profile 会放大 tool catalog。
- agent 在选工具时看到多套同构 browser 工具，增加误选概率。
- 后续想把 session/agent 默认 profile、proxy、user-data 隔离作为运行策略治理时，
  会被 source/function ID 绑死。

## 目标架构

```text
Tool Source
  configured.browser
    kind: browser_local
    owner: tool
    runtime requirement: browser-profile-runtime

        |
        v

Tool Function Catalog
  browser.snapshot
  browser.navigate
  browser.click
  browser.type
  browser.evaluate
  browser.screenshot
  browser.tabs.list
  browser.tabs.select
  browser.tabs.close

        |
        v

Tool Handler / Browser Tool Adapter
  - reads ToolExecutionContext
  - resolves browser profile
  - calls Browser application port
  - records tool run facts

        |
        v

Browser Application
  - profile resolution
  - host readiness
  - CDP endpoint lookup
  - page/tab generation
  - action/snapshot/screenshot/evaluate

        |
        v

Daemon Runtime
  host:browser:crxzipple
  host:browser:user
  host:browser:work
```

## 模块边界

### Tool Module

Tool module 负责：

- 注册 `configured.browser` source。
- 注册稳定的 `browser.*` tool functions。
- 执行 tool run lifecycle、queue、worker、retry、artifact、audit facts。
- 注入 `ToolExecutionContext`。
- 通过 browser application port 调用 Browser module。
- 在 function schema 中声明 `profile` 参数和 profile resolution 行为。

Tool module 不负责：

- 维护 browser profile 真相。
- 启动 Chrome/Edge/Chromium。
- 拼 CDP endpoint。
- 读取 `.crxzipple/browser/runtime/*.json`。
- 直接调用 daemon service 来解析 browser host。

### Browser Module

Browser module 负责：

- Browser profile config：
  - `name`
  - `driver`
  - `user_data_dir`
  - `profile_directory`
  - `cdp_url`
  - `cdp_port`
  - `attach_only`
  - `autostart`
  - `headless`
  - `proxy_mode`
  - `proxy_server`
  - `proxy_binding_id`
- Browser runtime state：
  - host generation
  - page generation
  - active target
  - snapshot generation
  - last action
  - last error
- Browser application ports for tools：
  - resolve profile
  - ensure/adopt host
  - list tabs
  - select tab
  - navigate
  - snapshot
  - screenshot
  - click/type/evaluate
- Browser-specific readiness and errors.

Browser module 不负责：

- 注册 Tool Source。
- 管理 Tool Function catalog。
- 管理 tool authorization/trust。
- 直接物化 Operations Tool projection。

### Daemon Module

Daemon module 负责：

- `host:browser:{profile}` lifecycle。
- 启动/停止/健康检查 browser host process。
- 记录 daemon instance、process metadata、endpoint readiness。
- 根据 Browser profile spec 生成 host daemon service specs。

Daemon module 不负责：

- Browser tool function discovery。
- Browser tool schema。
- Browser MCP source。
- 对 agent 暴露 browser tool。

### Operations Module

Operations module 负责侧向观察：

- Tool 页面显示一个 `Browser` source。
- Browser 页面显示多个 profile 的 runtime/readiness。
- Daemon 页面显示 `host:browser:{profile}`。
- Tool run detail 中显示本次使用的 profile。

Operations module 不应该：

- 前端绕过 `/operations/*` 直接拼 browser/tool 真相。
- 把 Browser profile 再展示成多个 Tool Source。
- 依赖旧 per-profile MCP source 作为当前事实。

## Browser Profile Resolution

每次 browser tool 调用都必须解析出一个 profile。解析顺序：

1. Tool input 显式 `profile`。
2. `ToolExecutionContext` 中的 session/browser context。
3. Agent profile 的 runtime default browser profile。
4. Browser system config 的 `default_profile`。

解析结果必须进入 tool run metadata：

```json
{
  "browser_profile": "crxzipple",
  "browser_profile_source": "input|session|agent_default|browser_default",
  "browser_host_service_key": "host:browser:crxzipple",
  "browser_host_generation": "...",
  "browser_page_generation": "..."
}
```

如果无法解析或 profile 不存在：

- tool run failed
- reason: `browser_profile_not_found`
- message 面向用户，不暴露内部 stack

如果 profile 存在但 host 不 ready：

- tool run failed 或 setup-needed，取决于该 tool 的语义
- reason: `browser_host_not_ready`
- Operations Browser 页面展示 host readiness
- Tool 页面展示 tool run failure，不新增 source failure

## Tool Source and Function Contract

### Source

唯一默认 Browser source：

```json
{
  "source_id": "configured.browser",
  "kind": "local",
  "display_name": "Browser",
  "status": "active",
  "config": {
    "provider": "crxzipple.browser",
    "profile_mode": "runtime_context",
    "default_profile_source": "browser_system_config"
  }
}
```

不再生成：

```text
configured.mcp.browser_user
configured.mcp.browser_crxzipple
configured.mcp.browser_{profile}
```

### Functions

初始函数集：

- `browser.snapshot`
- `browser.navigate`
- `browser.click`
- `browser.type`
- `browser.evaluate`
- `browser.screenshot`
- `browser.tabs.list`
- `browser.tabs.select`
- `browser.tabs.close`

所有函数共享：

```json
{
  "profile": {
    "type": "string",
    "required": false,
    "description": "Browser profile to use. Defaults to runtime/session/agent/browser default profile."
  }
}
```

Function ID 不得包含 profile：

```text
Allowed:
  browser.snapshot
  browser.navigate

Forbidden:
  mcp.browser_user.take_snapshot
  mcp.browser_crxzipple.take_snapshot
  browser.crxzipple.snapshot
```

## chrome-devtools-mcp 定位

默认路径不再依赖 `chrome-devtools-mcp`。

原因：

- `chrome-devtools-mcp` 的边界是一个 `browserUrl`。
- CRXZipple 的边界是一个 browser capability + profile runtime context。
- 为了复用原生 MCP 而按 profile 注册 source，会破坏 Tool/Operations/Authorization
  的治理模型。

允许未来新增实验 source：

```text
configured.mcp.chrome_devtools_experimental
```

但必须满足：

- 默认关闭。
- 不按 profile 自动注册。
- 不污染 Browser 默认 source。
- 不影响 `browser.*` functions。
- 不作为 Operations Browser/Tool 主路径。

## Data Migration and Cleanup

必须清理旧事实，不能只隐藏 UI。

### Tool Source Cleanup

删除或停用：

- `configured.mcp.browser_user`
- `configured.mcp.browser_crxzipple`
- `configured.mcp.browser_%`

建议方式：

- migration 清理 Tool source catalog 中匹配 `configured.mcp.browser_%` 的 source。
- 同步清理 source discovery state。
- 同步清理 source health projection。

### Tool Function Cleanup

删除：

- `mcp.browser_user.*`
- `mcp.browser_crxzipple.*`
- `mcp.browser_{profile}.*`

如果存在历史 tool runs 引用这些 function：

- 历史 run 保留 raw record。
- 新 catalog 不再提供这些 function。
- Operations 历史详情可以显示 legacy function id，但不能作为可调用 function。

### Daemon Cleanup

移除 daemon spec 生成：

- `mcp:browser:{profile}`

停止并清理已有 daemon instances：

- service key prefix `mcp:browser:`
- 但保留 `host:browser:{profile}`

### Operations Projection Cleanup

重建 projection：

```bash
source scripts/dev/infra-env.sh
python -m crxzipple.main operations-observer rebuild
```

验收：

- Tool operations source table 只出现一个 Browser source。
- Browser operations profiles table 仍出现多个 profile。
- Daemon operations 不再出现 `mcp:browser:{profile}`，只出现 `host:browser:{profile}`。

## Implementation Checklist

### P0 Documentation and Contract Freeze

- [x] 本文档进入 `docs/README.md` 当前施工入口。
- [x] 旧 Browser MCP checklist 顶部加 superseded 提示，并移入
  `docs/archive/reports/`，避免留在当前施工入口。
- [x] AGENTS/hosted-agent contract 如需补充，明确禁止 per-profile Browser MCP Source。
- [x] 新增 architecture guard test，禁止 production code 生成
      `configured.mcp.browser_{profile}`。
- [x] 新增 architecture guard test，禁止 daemon spec 生成 `mcp:browser:{profile}`。

### P1 Browser Application Port

- [x] 定义 Browser tool application port/service：
  - [x] `execute_control(profile, kind, target/context, payload)`
  - [x] `execute_page_action(profile, kind, target/ref/selector/context, payload)`
  - [x] 覆盖 `snapshot`、`navigate`、`click`、`type`、`evaluate`、
    `screenshot`、`list-tabs`、`focus-tab/select-tab`、`close-tab` 等
    browser tool 调用，不再要求 tool handler 直接拿 facade/serializer。
- [x] Port 返回 display-safe error model。
  - 已落地 `BrowserToolExecutionError` / `BrowserToolApplicationError`，Browser
    application port 将底层 `BrowserValidationError` 归一成
    `code/message/category/details/retryable/setup_required`。
  - Tool worker 识别带 `to_payload()` 的 display-safe exception，并按
    `ToolRunError` 结构落库，Operations/详情面可以读取错误码和安全 details。
- [x] Port 返回 browser runtime metadata：
  - [x] profile
  - [x] host service key
  - [x] host generation
  - [x] page generation
  - [x] active target id
  - 已落地 `BrowserToolApplicationService` / `BrowserToolExecutionResult`，
    runtime metadata 由 Browser application 从 runtime state 生成；`tools/browser/local.py`
    不再直接拼 `host:browser:*` 或读取 browser runtime state。

### P2 Browser Tool Source Registration

- [x] 移除 `_register_browser_mcp_tool_source_catalog` 的 per-profile source 注册。
- [x] 新增 `tool.register_browser_source_catalog` activation。
- [x] 注册唯一 source `configured.browser`。
- [x] 注册稳定 function catalog `browser.*`。
- [x] Function schema 全部包含 optional `profile`。
- [x] Function metadata 声明 Browser runtime requirement，而不是 daemon MCP requirement。
- [x] Source/function 更新不触发旧 MCP discovery。

### P3 Tool Handler Integration

- [x] 新增 Browser local/provider backend handler。
- [x] Handler 从 `ToolExecutionContext` 读取：
  - [x] agent id
  - [x] session id
  - [x] run id
  - [x] trace id
  - [x] optional default browser profile
  - 当前 metadata 明确写入 `browser_context_agent_id`、
    `browser_context_session_id`、`browser_context_run_id`、
    `browser_context_trace_id`、`browser_context_profile` 和
    `browser_context_profile_source`；orchestration 调用 tool 时同步注入
    `active_session_id` 与 `trace_id`。
- [x] Handler 调用 Browser application port。
- [x] Handler 把 profile resolution metadata 写入 tool run result。
- [x] Handler 生成 artifacts / content blocks：
  - [x] screenshot image
  - [x] snapshot JSON/text
  - [x] console/evaluate output
  - 已有 `test_browser_action_handler_persists_screenshot_as_artifact_ref`、
    `test_browser_snapshot_handler_surfaces_snapshot_body_in_content` 和
    `test_browser_action_handler_surfaces_evaluate_result_in_content` 覆盖核心路径。
- [x] Handler 不读取 daemon/process/browser runtime files。
- [x] Handler 不拼 CDP endpoint。

### P4 Daemon Spec Cleanup

- [x] 保留 `host:browser:{profile}` spec。
- [x] 删除 `mcp:browser:{profile}` spec 生成。
- [x] 删除 browser MCP endpoint plan 到 daemon MCP service 的生产路径。
- [x] 清理 daemon service set `browser-stack` 中的 MCP service entries。
- [x] 停止/清理旧 `mcp:browser:*` 实例的 dev/runtime cleanup。
  - 2026-05-26：清理从 daemon activation 常规路径移入
    `0062_drop_retired_browser_mcp_services` daemon state migration，带 marker，
    只负责 file-backed spec/instance/lease 退役。
- [x] Daemon Operations 更新 runtime kind：Browser Host 是唯一 browser daemon runtime。

### P5 Legacy Catalog Migration

- [x] Alembic/data migration 清理旧 browser MCP sources。
- [x] 删除旧 `tools/browser/tool.yaml` local package manifest，避免启动装配继续过滤旧包。
- [x] 旧 browser package source/functions 只由 migration 清理，不再挂在启动路径做兼容删除。
- [x] 清理旧 source discovery records。
- [x] 清理旧 source health records / stale Operations projections。
- [x] 对历史 tool run 只保留 legacy id 展示，不可再调用。
  - 旧 source/function catalog 被迁移和启动装配清理；历史 `tool_runs`
    保留 `function_id/source_id` 用于 Operations 详情展示，但重新执行会因 catalog
    缺失或 source deleted fail fast。
- [x] 更新 seed/bootstrap，避免重启后旧 source 被重新 upsert。

### P6 Settings UI

- [x] Tool Settings 不再显示 Browser MCP per-profile source。
  - `0061_cleanup_legacy_browser_tool_sources` 清理
    `configured.mcp.browser_*`、`mcp.browser_*` 和旧 bundled browser source；
    Tool Settings 只消费 Tool source/function catalog，不再硬编码 profile source。
- [x] Browser/Profile Settings 显示 profile 列表、默认 profile、user-data 隔离。
  - 新增 `/settings/browser-profiles`，直接消费 `/browser/profiles`；
    首屏展示默认 profile、managed/attach-only/isolated storage 统计、
    profile 表格和右侧详情。
  - 支持在 Browser/Profile Settings 中设置系统默认 browser profile。
- [x] Agent Settings 可设置默认 browser profile。
  - Agent Settings 在 Runtime 面板可从 `/browser/profiles` 选择默认 browser profile，
    写入 `runtime_preferences.attrs.default_browser_profile`。
  - Orchestration run context provider 读取 agent profile 后注入
    `agent_default_browser_profile`，browser tool 按 runtime context 解析 profile。
- [x] 不要求用户理解 MCP source/profile 的内部关系。
  - Browser profile 治理从 Tool MCP source 视角移到 Browser/Profile Settings；
    Agent Settings 只暴露 browser profile 选择，不暴露 MCP source/profile 关系。
- [x] `user` attach-only profile 未 ready 时，错误显示在 Browser/Profile 区域。
  - Browser/Profile Settings 使用 `/browser/profiles` 返回的 diagnostics/status/
    summary_line 展示 attach-only 或 existing-session profile 的未就绪原因。

### P7 Operations UI and Read Model

- [x] Backend read model: Tool Operations source table 只显示 `Browser` 一个 source。
- [x] Backend read model: Tool Operations function table 显示 `browser.*`。
- [x] Tool run detail 显示本次 profile 和 profile source。
- [x] Tool run detail 显示本次 host/page generation metadata。
- [x] Backend read model: Browser Operations profile table 显示多个 profile readiness。
- [x] Backend read model: Daemon Operations 不再展示 `mcp:browser:*`。
- [x] Browser readiness 不再污染 Tool source active status。
- [x] i18n 覆盖所有新增固定文案。

### P8 Authorization / Access / Audit

- [x] Browser capability trust 绑定到 `browser.*` function 或 `configured.browser` source。
  - `Tool` domain 现在保留 `source_id`，orchestration/http authorization resource
    attrs 同步暴露 `source_id` 和 `capability_ids`；browser function 由
    `configured.browser` source 产出，且 function id 稳定为 `browser.*`。
  - 默认 Authorization policy 已新增 `allow_browser_tool_execution` 和
    `allow_browser_local_tool_access_effect`，按 `resource.source_id=configured.browser`
    授权，不按 profile 复制。
- [x] 不按 profile 重复授权同一 browser capability。
  - 当前授权资源绑定到 function/source/capability，不再出现
    `configured.mcp.browser_{profile}` 或 `mcp.browser_{profile}.*` 维度。
- [x] 如需限制 profile，使用 authorization condition：
  - [x] allowed profiles
  - [x] user profile 是否允许
  - [x] managed profile 是否允许
  - 执行入口会把 browser tool input 中的 `profile` 注入 Authorization context：
    `browser_profile`、`requested_browser_profile`、
    `browser_profile_source=input.profile`。策略可以通过 `context_match` 或
    `condition` 限制某个 profile，而不需要按 profile 复制 Tool Source/Function。
- [x] Audit 记录：
  - [x] function id
  - [x] resolved profile
  - [x] profile resolution source
  - [x] target URL / origin where safe
  - [x] artifact ids
  - `ToolRun` 持久化 `function_id/source_id`；browser result metadata 写入
    `profile_name/profile_source`、runtime generation、safe target origin/url 和
    `browser_artifact_ids`。
- [x] Access module 不参与 browser profile 真相管理。
  - Browser profile 真相仍由 Browser module/system config 管理；Access 只通过
    external consumer binding 暴露 profile proxy credential readiness，不管理 profile
    列表、默认 profile 或 user-data 目录。

### P9 Tests

- [x] Unit: browser source registration only creates `configured.browser`.
- [x] Unit: no `configured.mcp.browser_%` source after activation.
- [x] Unit: no `mcp:browser:{profile}` daemon spec.
- [x] Unit: browser function IDs do not include profile.
- [x] Unit: Authorization context exposes explicit browser profile for policy
  restriction.
- [x] Unit: profile resolution order.
- [x] Unit: missing profile failure.
- [x] Unit: host not ready setup-needed/failure.
- [x] Unit: tool handler calls Browser application port, not daemon/process/browser files.
- [x] Unit: old source/function cleanup migration.
- [x] Unit: Operations Tool read model shows one Browser source.
- [x] Unit: Operations Tool run detail shows resolved Browser profile/source.
- [x] Unit: Operations Tool run detail shows Browser host/page generation metadata.
- [x] Unit: Browser runtime readiness does not downgrade Tool source health.
- [x] Unit: Operations Browser read model still shows multiple profiles.
- [x] HTTP/unit: run `browser.navigate` with default profile.
- [x] HTTP/unit: run `browser.navigate` with explicit `profile=user`.
- [x] HTTP/unit: run `browser.navigate` and verify tool run metadata.
- [x] HTTP/unit: run `browser.snapshot` and verify profile/target metadata.
- [x] Integration: run `browser.snapshot` with default profile.
  - 2026-05-25：`browser.snapshot` 对默认 `crxzipple` profile 成功，结果 metadata
    包含 `profile_name=crxzipple`、`profile_source=browser.default_profile`、
    `browser_host_generation`、`browser_target_id`、`browser_page_generation`、
    `browser_snapshot_generation` 和安全裁剪后的 `browser_target_origin/url`。
- [x] Integration: run `browser.snapshot` with explicit `profile=user`.
  - 2026-05-25：`profile=user` 进入同一个 `browser.snapshot` function，不再需要
    per-profile source；由于本机已有 Chrome 未暴露 18801 remote debugging，运行返回
    `browser_runtime_not_ready/setup_required`，这是 profile readiness 失败而不是 catalog
    或 authorization 失败。
- [x] Integration: run `browser.navigate` and verify tool run metadata.
  - 2026-05-25：`browser.navigate` 默认 profile 成功，`ToolRun` 持久化
    `function_id=browser.navigate`、`source_id=configured.browser`，result metadata
    记录 resolved profile、host generation、target id，并把
    `https://example.com/browser-integration?secret=...#...` 裁剪为
    `browser_target_origin=https://example.com` 和
    `browser_target_url=https://example.com/browser-integration`。
- [x] Frontend: Settings profile selector and Operations source table layout.
  - 2026-05-25：Playwright smoke 覆盖 `/settings/browser-profiles` 和
    `/operations/tool?tab=sources&provider=browser`，页面不再出现
    `configured.mcp.browser` / `mcp:browser`，Tool Operations 能看到单一 Browser source。

## 2026-05-25 Progress Snapshot

已完成默认后端路径收口：

- `configured.browser` 是唯一默认 Browser Tool Source。
- `browser.*` 是唯一默认 Browser Tool Function 前缀。
- daemon spec 只生成 `host:browser:{profile}`，不再生成 `mcp:browser:{profile}`。
- Operations Tool/Browser/Daemon read model 已移除 `mcp_endpoint`、`mcp_service_key` 和
  Browser MCP runtime kind 读取。
- 旧 `tools/browser/tool.yaml` local package manifest 已删除；Browser 工具由
  `configured.browser` 显式注册，不再靠启动 activation 过滤或删除旧
  `bundled.local_package.browser`。
- Alembic `0061_cleanup_legacy_browser_tool_sources` 会硬删除当前 catalog 中的旧
  `configured.mcp.browser_%`、`bundled.local_package.browser`、旧 browser function、
  discovery/provider backend 记录，并清掉含旧 marker 的 Operations projection。
- daemon state migration `0062_drop_retired_browser_mcp_services` 会 retire 旧
  `mcp:browser:*` service spec、instance、lease；daemon activation 常规路径不再识别
  Browser MCP。当前 dev registry 已验证只剩 `host:browser:crxzipple`、
  `host:browser:remote`、`host:browser:user`。
- `operations-observer rebuild` 已收口为有界的一次性 projection rebuild：只清理并
  重建 `operations_projections`，不再默认 reset observation store 或重放全量历史事件。
  历史事件增量观察仍由 `operations-observer run/process` 负责。
- Browser tool result metadata 已记录 `profile_name` 和 `profile_source`；Tool
  Operations 的 run detail 摘要会展示本次解析到的 Browser Profile 与来源。
- Tool Operations 的 Browser source row 只展示 `Browser profile context`，source active
  status 不查询 browser/tool readiness；具体 profile/daemon readiness 回到 Browser/Daemon
  运维面展示。
- Browser handler 已覆盖缺失 profile 失败路径；managed profile 缺少 ready host 时由 Browser
  control/Tool readiness 路径返回 `setup_needed` 或失败，不回退到 per-profile source。
- Browser tool result metadata 会在可用时记录 `browser_host_service_key`、
  `browser_host_generation`、`browser_target_id`、`browser_page_generation`、
  `browser_snapshot_generation` 和 `browser_current_ref_generation`；Tool Operations
  run detail 会展示这些运行证据。
- Browser tool result metadata 额外记录 display-safe audit facts：安全裁剪后的
  `browser_target_origin/browser_target_url` 和 `browser_artifact_ids`，避免把截图/PDF/
  下载产物只藏在 content block 里。
- Tool authorization resource attrs 现在暴露 `source_id` 和 `capability_ids`，授权
  策略可以按 `resource.id=browser.*`、`resource.source_id=configured.browser` 或
  `resource.capability_ids contains browser.page_action` 收口，不需要 profile 级重复授权。
- Browser tool 显式 `profile` 参数现在会进入 Authorization context，可按
  `context.browser_profile` 做 `allowed profiles`、`user profile 是否允许`、`managed
  profile 是否允许` 等条件控制；没有恢复 per-profile source/function。
- 默认 Authorization policy 已补齐 Browser source 运行策略；HTTP `/tools/browser.navigate/runs`
  不再因为缺少 allow policy 停在 authorization，orchestration/agent 路径也能通过
  `local_tool_access` effect 检查。
- Browser Operations 的 daemon runtime 表已修正同一 service 多条历史 instance 的选择逻辑：
  按 service 聚合后优先 ready/running instance，再看时间；避免历史 stopped instance 覆盖当前
  ready host，导致面板误报 `0 ready`。
- 新增 Tool Source / Browser run detail 固定文案已进入前端 i18n 映射，避免中文界面裸露
  backend label。
- Browser handler factory 已从旧 tool 名导出收敛为 `create_browser_*_handler`；
  生产装配只注册 `browser.*` function，`browser_pdf/browser_cdp_raw` 等旧 local package
  factory 不再作为模块导出形态存在。
- 旧 `browser.profile`、`browser.script` 和 fixed-kind local package factory 已移除；
  Browser profile 查询/治理只走 Browser module 的 HTTP/CLI surface，Tool module 只暴露
  当前 `configured.browser` source 下的公开 `browser.*` 可执行函数。
- Browser local handler 内部不再保留多步 script/final-observe 返回路径；公开 handler 统一走
  单步 browser operation 执行，`stabilize/observe_after` 只作为单步辅助参数存在。
- Browser local handler 内部命名已从 script 收敛为 operation；Playwright action engine 中
  未引用的 `_BROWSER_SCRIPT_*` 常量已删除，避免继续暗示有独立 Browser script tool。

仍需后续闭合：

- 无。

## Acceptance Criteria

The upgrade is complete only when all of the following are true:

- Tool Settings and Operations show one Browser source.
- Tool function catalog contains `browser.*`, not `mcp.browser_{profile}.*`.
- Adding a new browser profile does not create a new Tool Source.
- Adding a new browser profile only creates/updates `host:browser:{profile}` runtime.
- Browser tool calls can explicitly choose profile.
- Browser tool calls can use session/agent/default profile without explicit profile input.
- Tool run details show resolved profile.
- Browser Operations shows profile readiness separately from Tool Source readiness.
- No production code path registers `configured.mcp.browser_{profile}`.
- No production code path generates `mcp:browser:{profile}`.
- Old browser MCP sources/functions do not reappear after restart.
- Unit and targeted integration tests pass.

## Non-Goals

- 不在本轮实现完整 Playwright replacement。
- 不在本轮实现通用 MCP gateway。
- 不在本轮给 `chrome-devtools-mcp` 做 profile router。
- 不在本轮支持跨 profile 同一 tool call 并行操作。
- 不在本轮把 browser profile 迁出 Browser module。

## Rollout Order

建议按顺序施工：

1. Guard tests and docs freeze.
2. Browser application port shape.
3. Browser source/function catalog.
4. Tool handler.
5. Daemon MCP spec removal.
6. Migration cleanup.
7. Operations/Settings UI cleanup.
8. Integration verification.

不要先改 UI 隐藏旧 source。必须先让后端真相收口，否则 UI 会继续被旧 catalog 和 daemon spec
污染。

## Developer Notes

- 如果某个 browser action 当前只在旧 MCP backend 里有实现，优先在 Browser application/CDP
  surface 补能力，而不是保留 per-profile MCP source。
- 如果短期确实需要 `chrome-devtools-mcp` 的某个特殊能力，应作为内部实现细节封装在
  Browser module 或 experimental source，不能进入默认 Tool Source。
- Browser local tool handler 必须通过 app assembly 注入 Browser application port，不能
  在 handler 内创建 browser service/container。
- Operations projection 缺数据时补 Browser/Tool query service 或事件，不让前端绕路调用
  `/browser`、`/tools` 拼真相。
