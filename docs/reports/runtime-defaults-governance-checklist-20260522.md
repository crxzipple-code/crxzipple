# Runtime Defaults Governance Checklist 2026-05-22

本文是 Runtime Defaults 治理收口文档。它用于明确 `runtime-defaults`
和 Settings module 的关系，并给后续托管 agent 提供施工边界。

## 结论

Runtime Defaults 不是独立业务模块，也不是 Operations read model。它是
Settings module 持有的一类 Settings-owned config resource，用来治理系统运行
控制面的全局默认值。

目标链路：

```text
bootstrap defaults / explicit import / Settings UI action
  -> SettingsResource(kind="runtime-defaults", id="defaults")
  -> SettingsResourceVersion / SettingsOverride / Settings audit
  -> SettingsEffectiveConfigMaterializer.runtime_defaults()
  -> RuntimeDefaultsConfig
  -> RuntimeControlDefaults / RuntimeSettingsBootstrapConfig
  -> app assembly injects typed config
  -> orchestration / tool worker / daemon consume typed values
```

模块不能直接读取这些 runtime default 的 env，也不能自己解析 Settings JSON。
模块只能消费 assembly 注入的 typed config。

## 当前状态

当前代码已经有基础结构：

- `src/crxzipple/core/config.py` 中 `Settings` 读取
  `APP_ORCHESTRATION_*`、`APP_TOOL_*` 环境变量。
- `src/crxzipple/modules/settings/application/setup.py` 会把 core settings seed 成
  `runtime-defaults/defaults`。
- `src/crxzipple/shared/settings.py` 定义 `RuntimeDefaultsConfig`。
- `src/crxzipple/modules/settings/application/materialization.py` 提供
  `runtime_defaults()` materializer。
- `src/crxzipple/modules/orchestration/application/settings_integration.py` 定义
  `RuntimeSettingsBootstrapConfig` 和 Settings -> runtime config 转换。
- `app/assembly/orchestration.py`、`app/assembly/tool.py`、`app/assembly/daemon.py`
  已经消费 runtime bootstrap config。

当前偏移点：

- env/core settings 仍像事实来源，启动 seed 会更新已有 Settings resource。
- runtime config 转换类放在 orchestration module 里，但 tool/daemon 也在用。
- `runtime-defaults` payload 已收敛到 nested schema；HTTP 写入口会拒绝未知 runtime 控制字段。
- UI 已改成 Runtime Defaults typed 控制页，不再作为 generic JSON/resource 浏览页呈现。
- `RuntimeDefaultsConfig.daemon` 曾经没有稳定语义，已在 2026-05-23 删除，避免
  runtime defaults 重新变成空壳配置桶。

## 治理边界

### Settings Owns

- `runtime-defaults/defaults` 的 resource、version、publish、rollback、override。
- payload schema validation。
- audit reason、actor、trace context。
- effective resolution 和 typed materialization。
- 显式 import/reseed 命令。

### App Assembly Owns

- 从 Settings materializer 读取 effective config。
- 转换成运行服务真正消费的 typed config。
- 把 config 注入 orchestration、tool worker、daemon spec builder。
- 标注哪些配置需要重启、daemon reload 或 hot apply。

### Runtime Modules Own

- 使用注入后的 typed config。
- 在自己的 application/service 中执行 lease、heartbeat、concurrency、retry 等运行逻辑。
- 通过 Operations 暴露运行事实。

Runtime modules 不拥有 runtime default 的配置真相。

### Operations Owns

- 展示实际运行状态和配置生效观察事实。
- 不能写 runtime defaults。
- 不能通过 Operations projection 反推 Settings 配置。

## 非目标

- 不新增 `modules/runtime_defaults`。
- 不把 Agent Profile、LLM Profile、Tool Catalog、Access Asset、Memory Space、
  Skill Catalog、Channel Profile 塞进 Runtime Defaults。
- 不让各模块继续直接读取 `APP_ORCHESTRATION_*`、`APP_TOOL_*` 决定运行行为。
- 不保留长期 flat key / nested key 双轨兼容。
- 不把 Runtime Defaults UI 做成 JSON 编辑器。
- 不展示 LLM defaults、security defaults、observability defaults 等未落地假面板。

## 目标资源模型

Runtime Defaults 的 Settings resource 统一使用嵌套 schema：

```json
{
  "config_id": "defaults",
  "enabled": true,
  "orchestration": {
    "run_lease_seconds": 30,
    "run_heartbeat_seconds": 5.0,
    "executor_max_concurrent_assignments": 4,
    "auto_compaction_enabled": true,
    "auto_compaction_reserve_tokens": 20000,
    "auto_compaction_soft_threshold_tokens": 4000
  },
  "tool_worker": {
    "run_max_attempts": 3,
    "run_lease_seconds": 30,
    "run_heartbeat_seconds": 5.0,
    "max_in_flight": 4,
    "default_run_concurrency": 4,
    "image_run_concurrency": 4,
    "shared_state_run_concurrency": 1,
    "remote_default_max_concurrency": 16
  },
  "metadata": {
    "schema_version": 1
  }
}
```

`daemon` 分类只有在出现稳定 daemon runtime defaults 时才加入。没有实际字段前不要在
schema、UI 或文档里保留空分类。

## Source Of Truth

目标规则：

1. 首次启动时，如果 `runtime-defaults/defaults` 不存在，可以由 built-in defaults
   和 env 生成初始 Settings resource。
2. 已存在 resource 时，启动 seed 不得自动覆盖用户发布的 Settings 配置。
3. 需要重新导入 env 或默认值时，必须提供显式 CLI/action，并写 Settings audit。
4. 环境差异走 Settings override；不要让业务模块各自读 env 形成旁路。
5. 数据库、Redis、state dir、日志、进程端口等 Settings 自己启动前需要的配置仍然属于
   core/bootstrap env，不归 Runtime Defaults。

## 生效语义

默认按保守规则处理：

- orchestration lease/heartbeat/compaction：API/daemon 重启或 executor 重启后生效。
- executor concurrency：daemon spec 更新后，executor 进程重启后生效。
- tool worker lease/heartbeat/retry/concurrency：tool worker 重启后生效。
- remote default concurrency：tool runtime/service 重新装配后生效。

在没有明确 apply hook 前，UI 必须标注 `restart required` 或 `daemon restart required`，
不能暗示保存后热生效。

未来如果要支持 hot apply，必须由对应 owner runtime 提供显式 apply/reconcile
application service，并有测试覆盖。

## Backend Checklist

### R1. Shared Runtime Config Contract

- [x] 把 `RuntimeSettingsBootstrapConfig` 从 orchestration module 迁出到
  `src/crxzipple/app/assembly/runtime_defaults.py` 或 shared runtime contract。
- [x] 把 `runtime_bootstrap_config_from_settings()` 一并迁出。
- [x] 保持 orchestration/tool/daemon 只依赖 typed runtime config，不依赖
  `RuntimeDefaultsConfig` payload 细节。
- [x] 新位置不 import 任何业务模块 domain/application。

### R2. Settings Bootstrap Truth

- [x] 修改 `seed_core_settings_resources()` 对 `runtime-defaults/defaults` 的行为：
  resource 不存在时创建，已存在时不自动覆盖。
- [x] 如果其他 Settings-owned bootstrap resource 仍需自动更新，要明确白名单，不能把
  runtime defaults 混在一起。
- [x] 增加显式 CLI/action：import/reseed runtime defaults from env/defaults。
  当前复用显式 `/settings/bootstrap-import` action；后续可补 runtime-specific action。
- [x] import/reseed 必须写 Settings action audit，并记录 source、reason、actor。

### R3. Schema Cleanup

- [x] `RuntimeDefaultsConfig` 只接受嵌套 schema。
- [x] 删除 flat key 读取兼容：
  `orchestration_run_lease_seconds`、`tool_worker_max_in_flight` 等顶层字段。
- [x] validation 拒绝未知顶层 runtime 控制字段，避免 JSON 成为杂物箱。
- [x] 如果要迁移旧数据，提供一次性 migration，把 flat payload 改成 nested payload；
  不在 runtime parser 中长期兼容。

### R4. Runtime Consumers

- [x] orchestration service graph 只从 typed config 获取 lease、heartbeat、compaction。
- [x] tool service graph 只从 typed config 获取 retry、lease、heartbeat、concurrency。
- [x] daemon spec builder 只从 typed config 获取 executor/worker 启动参数。
- [x] `rg "APP_ORCHESTRATION_|APP_TOOL_RUN_|APP_TOOL_WORKER_|APP_TOOL_REMOTE_DEFAULT"`
  只允许出现在 core bootstrap/config、migration/import、测试断言中。

### R5. Settings HTTP/API

- [x] 为 Runtime Defaults 提供 typed read model，包含 effective payload、source、
  validation、impact、restart requirement。
- [x] 写操作走 Settings action service，必须提供 reason。
- [x] action response 返回 version、audit ref、validation result、apply requirement。
- [x] 不返回 generic raw JSON 作为主要编辑面。

### R6. Tests

- [x] Settings bootstrap 首次创建 runtime defaults。
- [x] 已存在 runtime defaults 时 env 改变不会覆盖 Settings resource。
- [x] 显式 import/reseed 会创建新 version 和 audit。
- [x] nested schema materialization 到 typed runtime config。
- [x] flat payload migration 后 runtime parser 不再依赖 flat 兼容。
- [x] orchestration/tool/daemon assembly 使用 typed runtime config。

## Frontend Checklist

- [x] Runtime Defaults 页面改成全屏控制台布局，不是 generic JSON resource page。
- [x] 只展示已经接通的分区：
  - Orchestration Safety
  - Tool Worker Control
  - Compaction
  - Effective Preview
  - Impact / Restart Requirement
  - Version / Audit Summary
- [x] 移除未落地假面板：LLM Defaults、Security Defaults、Observability Defaults、
  Advanced generic JSON。
- [x] 每个字段显示单位、范围、默认值、当前 effective source。
- [x] 保存必须要求 reason。
- [x] 保存后显示 `restart required` / `daemon restart required`。
- [x] skeleton、empty、error 状态保持稳定布局。
- [x] 所有固定文案进入 i18n。

## Operations Checklist

- [x] Operations Orchestration 显示当前运行实际 lease/heartbeat/compaction 生效值。
- [x] Operations Tool 显示当前 worker 并发、lease、heartbeat、retry 生效值。
- [x] Operations Daemon 显示 executor/worker spec 参数和最近 worker 启动观测。
- [x] Operations 不提供 Runtime Defaults 写入口，仅展示只读生效观察值。

## Validation

建议验收命令：

```bash
PYTHONPATH=src pytest -q tests/unit/test_settings_materialization.py tests/unit/test_settings_http.py
PYTHONPATH=src pytest -q tests/unit/test_app_assembly_targets.py tests/unit/test_daemon_service.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_memory.py tests/unit/test_tool_execution.py

cd frontend
npm run typecheck
npm run build
```

静态查验：

```bash
rg "APP_ORCHESTRATION_|APP_TOOL_RUN_|APP_TOOL_WORKER_|APP_TOOL_REMOTE_DEFAULT" src tests
rg "orchestration_run_lease_seconds|tool_worker_max_in_flight" src/crxzipple/modules src/crxzipple/app
rg "RuntimeSettingsBootstrapConfig" src/crxzipple
```

## Agent Work Split

- Worker A：backend Settings bootstrap/source-of-truth/schema migration。
- Worker B：runtime config contract relocation and assembly consumers。
- Worker C：Runtime Defaults typed HTTP/API and tests。
- Worker D：frontend Runtime Defaults page and i18n。
- Worker E：Operations effective value display and docs/test validation。

所有 worker 必须遵守：不恢复旧 generic Settings overlay，不新增长期兼容 shim，不让业务模块直接读
runtime default env。

## Done Criteria

- `runtime-defaults/defaults` 是 Settings DB 中的配置真相。
- env 只负责首次 seed 或显式 import/reseed。
- runtime defaults 有 typed schema、typed materializer、typed assembly config。
- orchestration/tool/daemon 不解析 Settings JSON。
- flat key 兼容已迁移并删除。
- 2026-05-23 复核：`RuntimeDefaultsConfig` 已删除无稳定语义的 `daemon`
  空 bucket；HTTP 写入继续把 `daemon` 当作未知顶层字段拒绝。Daemon 运行参数只通过
  orchestration/tool_worker 中已经落地的 executor/worker 字段展示和生效。
- UI 可读、可改、可验证、可审计，并明确生效方式。
- Operations 只展示运行事实，不写配置。
