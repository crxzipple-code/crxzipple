# Browser Profile Pool / Multi-IP Collection Plan 2026-05-26

本文档定义“多个相互隔离的浏览器挂在不同 IP 访问同一网站采集信息”的完整开发方案。
它接续 `browser-tool-source-profile-runtime-redesign-plan-20260525.md`，不恢复 per-profile
Browser MCP Source，不把 profile 再膨胀成 Tool Source。后续施工以本文和
`AGENTS.md` 为准。

## 目标

支持用户创建一组浏览器运行身份，每个身份具备独立：

- browser profile 名称与运行策略。
- user-data-dir / profile directory / 登录态 / cookie / storage。
- CDP endpoint / daemon host。
- proxy / egress IP。
- 并发占用、冷却、失败隔离和运行审计。

典型场景：

```text
collection pool: ctrip-flight
  profile ctrip-a -> proxy A -> IP A -> ctrip.com
  profile ctrip-b -> proxy B -> IP B -> ctrip.com
  profile ctrip-c -> proxy C -> IP C -> ctrip.com

browser.navigate(profile_pool="ctrip-flight", url="https://flights.ctrip.com/...")
  -> Browser allocator 选定 ctrip-b
  -> Tool run metadata 记录 profile / pool / egress / target host
  -> 后续同一 run/session 默认继续使用 ctrip-b，直到显式释放或过期
```

## 非目标

- 不建设绕过网站限制的规避系统。
- 不内置代理供应商购买、换 IP 或账号养号逻辑。
- 不让 LLM 自己随意轮换 profile 来提高请求频率。
- 不让前端直接操作 `.crxzipple/browser/*` 文件或 daemon instance。
- 不恢复 `configured.mcp.browser_{profile}` / `mcp:browser:{profile}`。
- 不把 Browser Pool 做成 Tool Source。Tool Source 仍只有 `configured.browser`。

## 当前基础

已经具备：

- Browser profile 模型字段：
  - `name`
  - `driver`
  - `cdp_url`
  - `cdp_port`
  - `user_data_dir`
  - `profile_directory`
  - `attach_only`
  - `autostart`
  - `proxy_mode`
  - `proxy_server`
  - `proxy_bypass_list`
  - `proxy_binding_id`
  - `proxy_credential_kind`
- daemon service：`host:browser:{profile}`。
- Browser tool source：`configured.browser`。
- Browser functions：`browser.navigate`、`browser.snapshot`、`browser.click`、
  `browser.type`、`browser.evaluate`、`browser.screenshot`、`browser.tabs.*`。
- Tool input 支持显式 `profile`。
- Access 支持 credential binding、readiness、secret resolve、audit。
- Browser host 支持 `proxy_mode=static` 和 `proxy_mode=access_binding`。
- Operations Browser 页面已有 profile、daemon、proxy readiness、egress 字段基础。

立项时主要缺口，本轮已按下方任务清单收口：

- Settings Browser Profiles 完整 CRUD。
- 代理凭证一等 UI 操作流和 browser-oriented readiness/egress test。
- Browser Profile Pool。
- Browser Profile Allocator。
- Tool run 与 Browser profile/pool/egress 的关联事实。
- Operations 一屏监控采集池占用、冷却、失败隔离。

## 架构原则

### Browser owns profile and pool

Browser module 拥有 browser profile、pool、allocation、runtime state 的真相。Tool、
orchestration、agent、settings 只能通过 Browser application port/usecase 使用这些能力。

### Access owns external credential

代理账号密码是外部凭证，由 Access 管理。Browser profile 只保存 binding id，不保存 raw
secret。Browser host 启动时通过 Access port resolve credential，并把脱敏 readiness/egress
事实写回 runtime metadata / events。

### Tool owns tool run, not profile scheduling

Tool module 仍拥有 tool function 和 tool run lifecycle。Browser tool handler 可以接收
`profile` 或 `profile_pool`，但实际 profile 分配由 Browser allocator 完成。

### Operations observes, does not decide

Operations 只观察 Browser/Tool/Daemon/Access 事实并物化 read model。Operations 页面不得
直接调用 `/browser/profiles`、`/tools/runs`、`/access/*` 拼页面真相。

## 目标模型

### BrowserProfile

沿用当前 Browser profile，并补充 Settings/Operations 需要的治理字段。

```python
BrowserProfileConfig(
    name: str,
    driver: Literal["managed", "existing-session"],
    cdp_url: str | None,
    cdp_port: int | None,
    user_data_dir: str | None,
    profile_directory: str | None,
    attach_only: bool,
    autostart: bool,
    proxy_mode: Literal["none", "static", "access_binding"],
    proxy_server: str | None,
    proxy_bypass_list: tuple[str, ...],
    proxy_binding_id: str | None,
    proxy_credential_kind: Literal["basic", "bearer_token"] = "basic",
    color: str | None,
    enabled: bool = True,
    tags: tuple[str, ...] = (),
)
```

规则：

- `managed` profile 用于采集池，daemon 可启动/停止。
- `existing-session` profile 用于附着用户已打开浏览器，不进入自动采集池默认候选。
- `static` proxy 不允许包含用户名密码。
- `access_binding` proxy 必须有 `proxy_binding_id`。
- 修改 proxy / user-data-dir / cdp_port 后，必须标记 profile runtime 需要 restart/reconcile。

### BrowserProfilePool

新增 Browser-owned entity。

```python
BrowserProfilePool(
    pool_id: str,
    display_name: str,
    enabled: bool,
    profile_names: tuple[str, ...],
    target_hosts: tuple[str, ...],
    selection_strategy: Literal[
        "round_robin",
        "least_busy",
        "sticky_session",
        "manual_only",
    ],
    max_concurrency_per_profile: int,
    max_concurrency_total: int | None,
    allocation_ttl_seconds: int,
    cooldown_seconds: int,
    failure_cooldown_seconds: int,
    health_policy: dict[str, object],
    metadata: dict[str, object],
)
```

规则：

- pool membership 只引用 Browser profile name。
- disabled profile 不参与自动分配。
- `existing-session` 默认不允许加入自动分配，除非 pool 显式 `allow_attach_only=true`。
- target host 只用于路由和可观测，不用于绕过访问控制。
- pool 本身不保存 secret。

### BrowserProfileAllocation

新增 Browser-owned runtime entity，用于固定某个 run/session/tool run 对 profile 的占用。

```python
BrowserProfileAllocation(
    allocation_id: str,
    pool_id: str,
    profile_name: str,
    consumer_kind: Literal["tool_run", "orchestration_run", "session", "agent"],
    consumer_id: str,
    target_host: str | None,
    status: Literal["active", "released", "expired", "failed"],
    acquired_at: datetime,
    expires_at: datetime,
    released_at: datetime | None,
    release_reason: str | None,
    metadata: dict[str, object],
)
```

规则：

- 同一 `consumer_kind/consumer_id/pool_id/target_host` 优先复用 active allocation。
- Tool handler 完成短动作后不强制释放 session/run 级 allocation；由 TTL、run 完成事件或显式释放处理。
- profile 进入 failure cooldown 后，不再分配给新的 consumer。

## Access 代理凭证

新增或稳定以下 credential kind 使用约束：

| 用途 | Access kind | Browser 字段 |
| --- | --- | --- |
| HTTP basic proxy | `basic` | `proxy_binding_id` |
| HTTP(S) bearer proxy | `bearer_token` | `proxy_binding_id` |
| 静态无认证代理 | 无 | `proxy_mode=static` + `proxy_server` |

Browser profile 的 proxy source：

```json
{
  "proxy_mode": "access_binding",
  "proxy_server": "http://proxy.example:8080",
  "proxy_binding_id": "proxy-a-basic",
  "proxy_credential_kind": "basic"
}
```

Browser host 启动流程：

```text
BrowserHostProcessRunner
  -> if proxy_mode=access_binding
  -> AccessCredentialProvider.resolve_credential(proxy_binding_id, expected_kind=proxy_credential_kind)
  -> start local proxy adapter
  -> launch browser with --proxy-server=http://127.0.0.1:{local_adapter_port}
  -> egress check
  -> daemon metadata: proxy_binding_id, proxy_credential_kind, proxy_upstream, proxy_local_url, proxy_egress_ip
```

禁止：

- `proxy_server=http://user:password@host:port`。
- Browser profile 直接读取 env/file secret。
- Tool handler 自己解析 proxy secret。

## Browser Application Surface

新增/补齐 Browser application services。

### BrowserProfileAdminService

已有基础 CRUD，需补：

- enable / disable profile。
- validate proxy binding compatibility。
- restart-needed 标记。
- delete 前检查 active allocation / daemon host / default profile。
- set default profile。
- bulk import/export。

### BrowserProfilePoolService

新增：

- create pool。
- update pool。
- delete pool。
- enable / disable pool。
- add/remove profile。
- validate pool membership。
- list pools with profile readiness summary。

### BrowserProfileAllocator

新增：

- allocate profile by `profile_name` or `pool_id`。
- reuse sticky allocation。
- honor concurrency/cooldown/readiness。
- record allocation.
- release allocation.
- expire allocations.

返回 payload：

```json
{
  "profile_name": "ctrip-b",
  "pool_id": "ctrip-flight",
  "allocation_id": "browser_alloc_...",
  "selection_reason": "least_busy",
  "host_service_key": "host:browser:ctrip-b",
  "egress": {
    "status": "ready",
    "ip": "203.0.113.10"
  }
}
```

## Tool Integration

Browser tool functions 保持稳定 function id，不按 profile/pool 生成新函数。

### Input schema

所有 browser tools 支持：

```json
{
  "profile": "optional explicit profile",
  "profile_pool": "optional browser profile pool",
  "target_id": "optional tab id",
  "timeout_ms": "optional timeout"
}
```

解析顺序：

1. 显式 `profile`。
2. 显式 `profile_pool` 分配 profile。
3. ToolExecutionContext 中已有 browser allocation。
4. session / run sticky browser allocation。
5. agent profile default browser profile。
6. browser system default profile。

`profile` 和 `profile_pool` 同时出现时：

- 默认拒绝，除非 `profile` 属于该 pool 且 `selection_strategy=manual_only`。
- 错误码：`browser_profile_selection_conflict`。

### Tool run metadata

每次 browser tool run 必须记录：

```json
{
  "browser_profile": "ctrip-b",
  "browser_profile_source": "pool_allocation",
  "browser_profile_pool": "ctrip-flight",
  "browser_allocation_id": "browser_alloc_...",
  "browser_host_service_key": "host:browser:ctrip-b",
  "browser_host_generation": "...",
  "browser_page_generation": 3,
  "browser_snapshot_generation": 2,
  "browser_proxy_mode": "access_binding",
  "browser_proxy_binding_id": "proxy-b-basic",
  "browser_proxy_egress_ip": "203.0.113.10",
  "browser_target_host": "flights.ctrip.com"
}
```

Tool module 不自己计算 egress 或 readiness，只接收 Browser application 返回的脱敏事实。

## Daemon Lifecycle

每个 managed profile 对应一个 daemon service：

```text
host:browser:{profile}
```

补齐行为：

- profile create/update 后生成/更新 daemon service spec。
- profile disable 后停止或阻止 ensure。
- pool enable 不立即启动所有 profile，除非 profile `autostart=true` 或用户显式 warm up。
- allocation 前确保对应 host ready。
- host crash 后 Browser runtime 标记 profile degraded，allocator 暂停分配。
- proxy/user-data-dir/cdp_port 改动后，旧 host generation 失效。

## Settings UI

新增或重做 `/settings/browser-profiles`，按全屏应用布局，不做小卡片滚动。

### 页面结构

顶部：

- Browser Profiles 标题。
- 默认 profile。
- profile 数量、managed 数量、ready 数量、proxy ready 数量。
- 新建 profile、导入、刷新。

主区：

- 左侧 profile 表格：
  - name
  - driver
  - status
  - user-data-dir
  - proxy
  - egress
  - daemon
  - allocations
  - actions
- 右侧详情/编辑面板：
  - General
  - Runtime
  - Proxy
  - Readiness
  - Danger zone

下区：

- Browser Profile Pools 表格：
  - pool id
  - profiles
  - strategy
  - active allocations
  - cooldown
  - target hosts
  - status

Profile modal：

- Create / Edit。
- Proxy binding 选择器从 Access bindings 过滤 compatible kind。
- Test CDP。
- Test proxy egress。
- Save 后显示 restart-needed。

Pool modal：

- Create / Edit。
- 选择 profile。
- 选择 strategy。
- 设置 concurrency / TTL / cooldown。
- 设置 target hosts。

## Operations UI

Browser Operations 页面新增：

- Pool health strip：
  - active pools
  - ready profiles
  - active allocations
  - cooldown profiles
  - failed profiles
  - unique egress IPs
- Profile runtime table：
  - profile
  - pool
  - driver
  - status
  - endpoint
  - pid
  - pages
  - proxy
  - egress
  - active allocation
  - last error
- Pool allocation table：
  - allocation id
  - pool
  - profile
  - consumer
  - target host
  - age
  - ttl
  - status
  - release reason
- Proxy readiness panel：
  - binding id
  - expected kind
  - readiness
  - egress IP
  - last checked
- Events table：
  - profile created/updated/deleted
  - pool created/updated/deleted
  - allocation acquired/released/expired
  - host attached/degraded/failed
  - proxy egress checked

Tool Operations 补：

- Tool run table 增加 browser profile / pool / egress 可选列。
- Tool run detail drawer 展示 browser allocation metadata。

Daemon Operations 补：

- `host:browser:{profile}` service group 按 Browser profile 聚合。
- 显示 proxy egress、profile、generation。

## Events / Projection

Browser module 发布事件：

```text
browser.profile.created
browser.profile.updated
browser.profile.deleted
browser.profile.enabled
browser.profile.disabled
browser.pool.created
browser.pool.updated
browser.pool.deleted
browser.pool.enabled
browser.pool.disabled
browser.allocation.acquired
browser.allocation.released
browser.allocation.expired
browser.host.attached
browser.host.degraded
browser.host.failed
browser.proxy.egress_checked
```

Operations materializer 消费上述事件，并在 observer snapshot 中通过 Browser query service
补齐当前状态。

Projection store：

- `/operations/browser` 读取 `operations_projections`。
- 页面缺字段时补事件或 query service，不让前端绕路。

## HTTP/API Surface

Browser owner API：

```text
GET    /browser/profiles
POST   /browser/profiles
PUT    /browser/profiles/{profile_name}
DELETE /browser/profiles/{profile_name}
POST   /browser/profiles/{profile_name}/enable
POST   /browser/profiles/{profile_name}/disable
POST   /browser/profiles/{profile_name}/start
POST   /browser/profiles/{profile_name}/stop
POST   /browser/profiles/{profile_name}/restart
POST   /browser/profiles/{profile_name}/test-cdp
POST   /browser/profiles/{profile_name}/test-egress

GET    /browser/pools
POST   /browser/pools
PUT    /browser/pools/{pool_id}
DELETE /browser/pools/{pool_id}
POST   /browser/pools/{pool_id}/enable
POST   /browser/pools/{pool_id}/disable
POST   /browser/pools/{pool_id}/warm-up
POST   /browser/pools/{pool_id}/drain

GET    /browser/allocations
POST   /browser/allocations
POST   /browser/allocations/{allocation_id}/release
```

Settings API 可以通过 `/ui/settings/browser-profiles` 聚合 owner API，但写操作必须转发到
Browser owner application，不得另存 Settings-owned overlay。

## 数据持久化

优先使用 Browser module 自有 store/repository：

- `browser_profiles`
- `browser_profile_pools`
- `browser_profile_pool_members`
- `browser_profile_allocations`
- `browser_profile_runtime_states`

如果当前 Browser 仍以 file-backed store 为主，迁移策略：

1. 保留 file-backed store 作为 local runtime bootstrap。
2. 新增 SQL-backed repository。
3. 首次启动时从 `.crxzipple/browser/config/system.json` seed 到 DB。
4. 后续写操作进入 DB。
5. 不保留长期双写；迁移完成后 file 只作为 explicit export/import。

## 任务清单

### P0. 现状修复和守卫

- [x] 修复 Edge/Chrome renderer 子进程导致的 CDP port 归属误判。
- [x] control/action 路径统一使用解析后的 user-data-dir 作为 browser host lease owner。
- [x] 加测试覆盖 renderer 子进程误判 CDP port 冲突。
- [x] 加测试覆盖 action/control 使用同一 host lease owner。
- [x] 修复 Browser profile diagnostics 与 daemon readiness 延迟不一致。
- [x] existing-session 无显式 CDP endpoint 时，不要派生 managed port 造成误导。
- [x] Browser bootstrap 移除已删除 profile 对应的 stale `host:browser:*` spec/instance。
- [x] 加 architecture guard：Browser tool source 不得按 profile 生成。
- [x] 加 architecture guard：Browser runtime 不得读取 raw proxy secret。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_browser_cdp_control.py tests/unit/test_browser_playwright_actions.py
PYTHONPATH=src pytest -q tests/unit/test_browser_tool_http_runtime.py tests/unit/test_browser_tool_profile_http.py
PYTHONPATH=src pytest -q tests/unit/test_daemon_service.py tests/unit/test_browser_domain.py tests/unit/test_browser_cdp_urls.py tests/unit/test_app_assembly_targets.py tests/unit/test_operations_browser_read_model.py tests/unit/test_browser_http.py tests/unit/test_browser_cli.py tests/unit/test_browser_profile_probe.py tests/unit/test_module_lifecycle_architecture.py
ruff check src/crxzipple/modules/browser tests/unit/test_browser_*.py
```

### P1. Browser Profile CRUD

- [x] 后端补 profile enable/disable/start/stop/restart/test-cdp/test-egress。
- [x] 更新 profile 后发布 Browser profile events，并登记 browser.operations event surface。
- [x] delete profile 前检查 default、running runtime state / daemon host。
- [x] Settings Browser Profile 页面补 CRUD modal。
- [x] UI 支持 proxy binding 选择、CDP test、egress test。
- [x] Settings profile 表格和详情展示 runtime 中脱敏的 proxy egress 状态/IP。
- [x] Settings profile / pool 表格接入 active allocation 摘要，池详情可查看并释放单个活跃租约，避免池子运行后治理面看不到占用。
- [x] active allocation 删除/停用守卫已接入 profile 与 pool。
- [x] restart-needed 提示已接入 Settings owner API：profile payload 对比当前配置与 daemon host 启动 metadata，配置漂移时返回 `diagnostics.status=restart-needed` 和 `restart_fields`。
- [x] profile diagnostics 读取 daemon metadata 时优先选择 ready/current 实例，并按 proxy mode 比对配置漂移，避免 stale stopped instance 或未启用代理字段把可用 profile 误判为 restart-needed。
- [x] Test CDP / profile probe 会校验 local-managed CDP 端口上的进程是否匹配当前 profile 的 user-data-dir、headless、remote-allow-origins；端口可连但归属不符时返回 `cdp-profile-mismatch`，避免工具调用阶段才暴露 “CDP port is occupied by mismatched profile”。
- [x] Browser Settings 不直接展示后端英文 diagnostics message/summary_line，改由 `summary.code` / `probe.status` 映射 i18n 文案，覆盖 `profile-mismatch`、`restart-needed`、`bad-cdp-endpoint` 等状态。
- [x] Browser Settings / Operations 表格中的 pool strategy、profile status、page freshness 等枚举进入 i18n 映射，不再裸露 `least_busy`、`manual_only`、`fresh`、`cooling` 等内部值。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_browser_http.py tests/unit/test_browser_cli.py
cd frontend && npm run typecheck
```

### P2. Access Proxy Binding

- [x] Access credential requirement 增加 Browser proxy consumer。
- [x] Browser profile proxy binding readiness 进入 Access read model。
- [x] Browser egress check 不记录 secret。
- [x] Settings 代理选择器按 expected kind 过滤已接入。
- [x] Proxy kind compatibility：`basic` / `bearer_token` / no-auth static 已可用；Browser profile 显式声明 `proxy_credential_kind`，Access readiness/resolve 按该 kind 校验，local proxy adapter 注入对应 `Proxy-Authorization`。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_browser_access_requirements.py tests/unit/test_access_read_models.py
```

### P3. Browser Profile Pool

- [x] 新增 pool domain entity/value object。
- [x] 新增 file-backed pool repository，随 Browser state root 管理 `pools/`。
- [x] SQL repository / migration 决策：本升级不单独迁移 pool 表，避免 profile file + pool SQL 的分裂真相；后续 Browser persistence cutover 必须以 profile/pool/allocation/runtime/ref store 族为单位整体切换。
- [x] 新增 BrowserProfilePoolService。
- [x] 新增 Browser profile pool HTTP endpoints。
- [x] Browser CLI 增加 `browser pool` 管理命令。
- [x] Settings UI 增加 pool 表格和 modal。
- [x] Settings UI 接入 allocation release 与 pool drain owner action，用于释放单个或整池活跃租约。
- [x] Operations Browser 页面展示 pool readiness / allocation summary。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_browser_profile_pool.py tests/unit/test_browser_http.py tests/unit/test_browser_cli.py tests/unit/test_browser_state.py
cd frontend && npm run typecheck && npm run build
```

### P4. Browser Profile Allocator

- [x] 新增 allocation domain entity。
- [x] 新增 file-backed allocation repository，随 Browser state root 管理 `allocations/`。
- [x] 新增 allocator service：round_robin、least_busy、sticky_session 复用语义、manual_only。
- [x] 支持 max concurrency、TTL、cooldown、failure cooldown。
- [x] 支持 release/expire/drain。
- [x] 新增 allocation HTTP endpoints 和 `browser allocation` CLI。
- [x] Browser host ensure 与 allocation 串联：Browser tool handler 先通过 allocator 解析 profile，再进入 Browser tool application ensure/attach 路径。
- [x] 运行时新增/更新/删除 Browser profile 时，同步注册或移除对应 `host:browser:{profile}` daemon service spec，避免 profile CRUD 后必须重启 API 才能被 tool 使用。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_browser_profile_allocator.py tests/unit/test_browser_http.py tests/unit/test_browser_cli.py
```

### P5. Tool Integration

- [x] Browser tool schema 增加 `profile_pool`。
- [x] ToolExecutionContext 支持 browser allocation context。
- [x] Browser tool handler 调用 allocator。
- [x] Tool run metadata 记录 profile/pool/allocation；egress/proxy 字段已通过 Browser host/runtime metadata 透传。
- [x] Tool failure structured error：profile not found、pool not ready、concurrency exceeded。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_browser_tool_http.py tests/unit/test_browser_tool_application.py
PYTHONPATH=src pytest -q tests/unit/test_tool_access_architecture.py
```

### P6. Operations Projection

- [x] Browser profile/pool/allocation events 进入 operations projection。
- [x] Browser owner query service 暴露 pool/allocation 运维读模型。
- [x] `/operations/browser` 返回 pool、allocation、proxy readiness。
- [x] `/operations/tool` run detail 展示 browser profile/pool/allocation metadata。
- [x] Browser Operations 页面按全屏监控布局改造。
- [x] Tool Operations 增加 browser profile/pool/egress detail。

2026-05-26 进展：

- `/operations/browser` 新增 `profile_pools`、`profile_allocations` section，metrics/tabs 同步新增 `profile_pools`、`profile_allocations`。
- Browser 事件触发 Operations observer 时会重建 `browser`、`daemon`、`events` projections。
- Browser Operations 前端 tab 已能切换 profile pools / profile allocations；PC 指标区收为单行，页面接入 `operations-module-console` 审计根并通过 browser 单页布局审计。
- Tool run detail 已展示 `browser_profile_pool`、`browser_allocation_id`、`browser_target_host`。
- Tool run 列表新增紧凑 Browser 列，展示 profile / pool / allocation / target host 摘要。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_operations_browser_read_model.py tests/unit/test_operations_tool_read_model.py
cd frontend && npm run audit:operations-layout
```

### P7. End-to-End

- [x] 创建三个 managed profile。
- [x] 为每个 profile 配置不同 static proxy endpoint；带凭证 proxy 仍走 Access binding，避免 raw secret 进入 profile。
- [x] 创建 pool。
- [x] 对同一 URL 连续提交 browser.navigate，并执行 browser.snapshot 验证后续 browser tool 仍可使用已分配 profile。
- [x] 验证不同 tool run 分配到不同 profile；显式 profile 调用会记录为 `profile:{name}` allocation，不混入 pool allocation 统计。
- [x] 验证 Operations 显示 profile、pool、allocation，以及 Tool Operations 列表/详情显示 browser profile/pool/allocation/target host。
- [x] 验证 pool owner metadata 中的 secret marker 不出现在 Browser Operations、Tool Operations 或 tool run detail。
- [x] 验证 Browser Operations pool 行可见 available/cooling/failure cooldown/recent failure summary，allocation 表可见 failed/release reason。
- [x] `test-egress` 结果由 Browser profile admin service 脱敏写入 runtime state，并发布 `browser.profile.updated`；Operations 在 daemon metadata 缺失时使用 runtime egress fallback。
- [x] Tool runtime readiness 按 Browser host metadata 中的 `proxy_credential_kind` 向 Access 校验凭证类型，避免 bearer proxy 被固定按 basic 误判。
- [x] 真实代理 egress IP 验收归为环境门禁项：代码路径支持 static/basic/bearer egress test，当前自动化覆盖本地代理注入、secret 不泄露和 egress 结果落库；真实外部代理 IP 需在具备代理资产的环境执行 live-smoke。
- [x] 失败/冷却自动化验收已覆盖 query service 与 Operations read model；真实浏览器 live-smoke 保留到代理环境验收时一起跑。

验收：

```bash
make dev-up
PYTHONPATH=src pytest -q tests/integration/test_browser_profile_pool_e2e.py
cd frontend && npm run typecheck && npm run build
```

## 风险与决策点

- **代理 egress test 慢**：必须异步缓存 readiness，页面不阻塞全量加载。
- **同站采集并发风险**：默认 conservative strategy，必须有 cooldown 和 max concurrency。
- **existing-session 误用**：默认不进入 pool 自动分配，避免拿个人浏览器做采集身份。
- **user-data-dir 迁移**：修改目录后必须显式 restart，不热切。
- **Operations 数据延迟**：状态页用 projection 为主，必要时 observer sidecar 补 query service snapshot。
- **DB/file store 过渡**：本升级继续使用 Browser file-backed owner store；后续若切 DB，必须整体切换 profile/pool/allocation/runtime/ref store，不长期双写、不单独迁移 pool。

## 完成定义

本升级完成时，应满足：

- 用户可以在 Settings 中创建多个 Browser profile。
- 每个 profile 可以绑定不同代理凭证并测试出口 IP。
- 用户可以创建 Browser Profile Pool。
- 用户可以在 Settings 中看到 profile/pool 活跃租约数量，并释放单个租约或对 pool 执行 drain。
- Browser tool 可以通过 `profile_pool` 自动选择 profile。
- Tool run detail 可追溯 profile、pool、allocation、egress。
- Operations Browser 能一屏看到池、profile、allocation、daemon、proxy 健康。
- 没有 per-profile Browser Tool Source。
- 没有 raw proxy secret 泄露。
- 关键路径有单元测试、集成测试和前端 typecheck/build 验收。
