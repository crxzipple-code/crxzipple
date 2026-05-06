# Code Quality Audit 2026-05-06

本文档按 [code-quality-audit-checklist.md](code-quality-audit-checklist.md) 组织，由四条并行审计线汇总而成：

- 后端基础、架构边界、API、测试结构。
- Operations / Daemon / DB 链路。
- `frontend-v2` 构建、API、布局。
- 文档入口与旧文档清理。

## Summary

结论：未发现 P0 阻塞项；Postgres/Redis、Operations projection、核心 `/operations/*` API、`frontend-v2` typecheck/build/layout audit 当前可用。但存在多项 P1 架构收口问题，主要集中在旧 `orchestration-observation` 残留、Operations 前端旁路、tool/llm 事件定义缺口、默认 SQLite 风险和 active UI 文档口径冲突。

整改后状态：P1/P2/P3 主体修复已落到
[code-quality-remediation-tasks-20260506.md](code-quality-remediation-tasks-20260506.md)。
本文历史发现保留原始审计背景；已修复项在对应小节标注当前状态，避免后续 agent 把旧证据当成当前事实。

当前不建议继续扩大功能面。建议先按本文 P1 顺序收口，再进入下一轮功能开发。

## Findings

### P0

未发现。

### P1

#### P1-1. 旧 `orchestration-observation` 未完全退场

影响：旧 worker 已不在 daemon spec 中作为运行项，但 container 字段、builder、CLI、测试仍残留，导致相关单测失败，并持续制造“旧观察进程是否应保留”的架构歧义。

证据：

- [container.py](/Users/crxzy/Documents/crxzipple/src/crxzipple/bootstrap/container.py:383)
- [container.py](/Users/crxzy/Documents/crxzipple/src/crxzipple/bootstrap/container.py:1562)
- [container.py](/Users/crxzy/Documents/crxzipple/src/crxzipple/bootstrap/container.py:2003)
- [worker_cli.py](/Users/crxzy/Documents/crxzipple/src/crxzipple/modules/orchestration/interfaces/worker_cli.py:2335)
- [worker_cli.py](/Users/crxzy/Documents/crxzipple/src/crxzipple/modules/orchestration/interfaces/worker_cli.py:2366)
- [worker_cli.py](/Users/crxzy/Documents/crxzipple/src/crxzipple/modules/orchestration/interfaces/worker_cli.py:2427)
- [test_daemon_service.py](/Users/crxzy/Documents/crxzipple/tests/unit/test_daemon_service.py:123)
- [test_orchestration_cli.py](/Users/crxzy/Documents/crxzipple/tests/unit/test_orchestration_cli.py:680)
- [test_events.py](/Users/crxzy/Documents/crxzipple/tests/unit/test_events.py:1351)
- [test_cli.py](/Users/crxzy/Documents/crxzipple/tests/unit/test_cli.py:63)

验证结果：

- `tests/unit/test_daemon_service.py`：3 failed，均因旧 `worker:orchestration-observation` 预期。
- `tests/unit/test_orchestration_cli.py -k observation`：2 failed，仍测旧 observation CLI。

建议：

- 删除旧 orchestration observation runtime/builder/CLI 暴露。
- 更新 daemon/orchestration/events/CLI 测试，只认可 `worker:operations-observer`。
- 保留必要历史说明在 docs/archive，而不是代码兼容层。

#### P1-2. Operations 前端仍存在 owner module API 旁路

影响：Operations 页面主 read model 基本走 `/operations/*`，但 action/辅助读取仍直接调用 owner module API。严格按当前约束，前端不应绕过 Operations read/action surface 拼运维真相或执行运维动作，否则会重新形成 UI 层中间台。

证据：

- [api.ts](/Users/crxzy/Documents/crxzipple/frontend-v2/src/pages/operations/api.ts:377)
- [api.ts](/Users/crxzy/Documents/crxzipple/frontend-v2/src/pages/operations/api.ts:468)
- [api.ts](/Users/crxzy/Documents/crxzipple/frontend-v2/src/pages/operations/api.ts:527)
- [api.ts](/Users/crxzy/Documents/crxzipple/frontend-v2/src/pages/operations/api.ts:540)
- [api.ts](/Users/crxzy/Documents/crxzipple/frontend-v2/src/pages/operations/api.ts:563)
- [api.ts](/Users/crxzy/Documents/crxzipple/frontend-v2/src/pages/operations/api.ts:592)
- [api.ts](/Users/crxzy/Documents/crxzipple/frontend-v2/src/pages/operations/api.ts:843)

另一个直接风险：Daemon action 在 UI 中检查了 `reason_required`，但没有把 reason 传入实际调用。

- [DaemonOperationsPage.vue](/Users/crxzy/Documents/crxzipple/frontend-v2/src/pages/operations/modules/DaemonOperationsPage.vue:573)
- [api.ts](/Users/crxzy/Documents/crxzipple/frontend-v2/src/pages/operations/api.ts:592)

建议：

- 为 Operations 动作补统一 action dispatcher 或模块化 Operations action API。
- 前端 Operations 页面只调用 `/operations/{module}` 与 `/operations/{module}/actions/*`。
- 所有 action payload 带 `reason`、`risk`、`audit`、`permission` 语义。

#### P1-3. tool / llm 运行事实发布了事件，但缺 EventDefinition

影响：事件事实已经进入 events backend，但 `EventDefinitionRegistry` 未覆盖 tool/llm 事件，Trace/Operations 无法依赖稳定事件定义做展示、校验和语义映射。

证据：

- [tool entities.py](/Users/crxzy/Documents/crxzipple/src/crxzipple/modules/tool/domain/entities.py:252)
- [tool entities.py](/Users/crxzy/Documents/crxzipple/src/crxzipple/modules/tool/domain/entities.py:337)
- [llm services.py](/Users/crxzy/Documents/crxzipple/src/crxzipple/modules/llm/application/services.py:144)
- [llm services.py](/Users/crxzy/Documents/crxzipple/src/crxzipple/modules/llm/application/services.py:249)
- [container.py](/Users/crxzy/Documents/crxzipple/src/crxzipple/bootstrap/container.py:1760)

缺失事件包括：

- `tool.run.*`
- `tool.assignment.*`
- `tool.worker.*`
- `llm.invocation_*`
- `llm.profile_*`

建议：

- 为 tool/llm 补 EventDefinition / contract 注册。
- 同步 Trace/Operations 显示名、level、status、linked entity 字段。
- 加测试确保新增事件不会再次绕过 registry。

#### P1-4. 默认 DB 仍是 SQLite，worker/observer CLI 缺运行 guard

影响：`serve` 和 dev stack 有 SQLite guard，但 daemon/worker/operations-observer CLI 路径未见同类保护。手动启动 worker 或 observer 时可能写入 SQLite，而 API 读 Postgres projection，造成运行真相分裂。

证据：

- [config.py](/Users/crxzy/Documents/crxzipple/src/crxzipple/core/config.py:1815)
- [crxzipple.py](/Users/crxzy/Documents/crxzipple/src/crxzipple/interfaces/cli/crxzipple.py:37)
- [up-redis-stack.sh](/Users/crxzy/Documents/crxzipple/scripts/dev/up-redis-stack.sh:191)

建议：

- 对 daemon/worker/operations-observer/tool scheduler 等长运行入口加 SQLite guard。
- 或将本地 runtime 默认 DB 明确切到 Postgres env。
- SQLite 仅保留测试和显式 fallback。

#### P1-5. Active UI 文档仍有旧 `/ui/*` 和 owner provider 口径

状态：已由 R4 修正。active UI 文档现在将 Operations 读取入口描述为 `/operations/{module}` + `operations_projections`，并明确业务模块只提供通用 service/query/event 事实，不提供 Operations 专用页面聚合口径。

影响：`docs/ui/current-ui-design-functional-spec.md` 是 active UI 文档，但仍建议新增 `/ui/*` read surface，并出现 owner module provider 口径，和当前 `modules/operations` projection 决策冲突。后续 agent 可能按 active 文档把 Operations read model owner 放回业务模块。

证据：

- [current-ui-design-functional-spec.md](/Users/crxzy/Documents/crxzipple/docs/ui/current-ui-design-functional-spec.md:646)
- [current-ui-design-functional-spec.md](/Users/crxzy/Documents/crxzipple/docs/ui/current-ui-design-functional-spec.md:650)
- [current-ui-design-functional-spec.md](/Users/crxzy/Documents/crxzipple/docs/ui/current-ui-design-functional-spec.md:679)

建议：

- 将该段改为当前事实：Operations 页面由 `/operations/{module}` + `operations_projections` 提供。
- 明确 owner module 只提供通用 service/query，不提供 Operations 专用 provider。

#### P1-6. application 层直接依赖 infrastructure 具体实现

影响：部分 application service import 本模块 infrastructure 具体实现，削弱 port/adapter 边界，使组合根难以替换实现，也违背托管 agent 约束中的 DDD 分层。

证据：

- [memory services.py](/Users/crxzy/Documents/crxzipple/src/crxzipple/modules/memory/application/services.py:24)
- [skills manager.py](/Users/crxzy/Documents/crxzipple/src/crxzipple/modules/skills/application/manager.py:32)
- [artifacts services.py](/Users/crxzy/Documents/crxzipple/src/crxzipple/modules/artifacts/application/services.py:21)
- [process services.py](/Users/crxzy/Documents/crxzipple/src/crxzipple/modules/process/application/services.py:10)

建议：

- 补 application port/protocol。
- 由 container 注入 infrastructure 实现。
- 将已有 concrete import 收口为 adapter wiring。

### P2

#### P2-1. Operations API `limit/offset` 只裁剪主表，详情数组仍完整返回

影响：`/operations/llm?limit=1` 仍返回约 1.2MB 且含 `invocation_details=33`；`/operations/tool?limit=1` 仍返回约 193KB 且含 `tool_run_details=13`。这不符合“查询接口有分页/无运行态无限 list 返回”的质量要求。

证据：

- [http.py](/Users/crxzy/Documents/crxzipple/src/crxzipple/modules/operations/interfaces/http.py:88)
- [http.py](/Users/crxzy/Documents/crxzipple/src/crxzipple/modules/operations/interfaces/http.py:347)
- [projections.py](/Users/crxzy/Documents/crxzipple/src/crxzipple/modules/operations/application/projections.py:138)

建议：

- 将大详情拆成按需详情 endpoint 或 projection query key。
- 主列表只返回当前页 rows 和必要 summary。
- 右侧 drawer 打开时再按 id 拉详情。

#### P2-2. 未捕获 HTTP 500 返回 plain text

影响：未捕获异常返回 `500 text/plain; charset=utf-8`，body 为 `Internal Server Error`。这不满足 API 质量要求，也会触发前端 `Expected JSON` 类错误。

证据：

- [app.py](/Users/crxzy/Documents/crxzipple/src/crxzipple/interfaces/http/app.py:63)
- [app.py](/Users/crxzy/Documents/crxzipple/src/crxzipple/interfaces/http/app.py:81)

建议：

- 增加全局 exception handler，统一返回 JSON error envelope。
- 保持日志记录，但不要 re-raise 到默认 plain text handler。

#### P2-3. 多个状态变更 HTTP action 缺 reason/risk/audit/confirmation 语义

影响：daemon ensure/reconcile/stop、browser/mobile control/action、tool cancel/retry/prune 等危险或状态变更 endpoint 缺统一操作原因、风险和审计契约。

证据：

- [daemon http.py](/Users/crxzy/Documents/crxzipple/src/crxzipple/modules/daemon/interfaces/http.py:110)
- [daemon http.py](/Users/crxzy/Documents/crxzipple/src/crxzipple/modules/daemon/interfaces/http.py:146)
- [browser http.py](/Users/crxzy/Documents/crxzipple/src/crxzipple/modules/browser/interfaces/http.py:203)
- [mobile http.py](/Users/crxzy/Documents/crxzipple/src/crxzipple/modules/mobile/interfaces/http.py:38)
- [tool http.py](/Users/crxzy/Documents/crxzipple/src/crxzipple/modules/tool/interfaces/http.py:236)

建议：

- 统一 action request model。
- 对危险动作强制 confirmation/reason。
- 将审计事件纳入 access/authorization 或 operations action service。

#### P2-4. OperationsShell 订阅 raw event stream 并在前端推断模块刷新

影响：目前 raw event stream 仅用于刷新触发，不直接渲染完整真相，但 UI 仍依赖 event owner/topic 命名推断模块。这增加了前端对 raw event 语义的耦合。

证据：

- [OperationsShell.vue](/Users/crxzy/Documents/crxzipple/frontend-v2/src/pages/operations/OperationsShell.vue:198)
- [events.ts](/Users/crxzy/Documents/crxzipple/frontend-v2/src/shared/api/events.ts:41)

建议：

- 由 Operations runtime/status 或 projection update feed 提供模块刷新信号。
- 前端只理解 projection/module invalidation，不解析 raw owner/topic。

#### P2-5. Orchestration 页面裸露 raw event key

影响：运行事件直接显示 `executor.lease.heartbeated`、`engine_failed` 等 raw key，违反“不要裸露 i18n/event key 给用户”的 UI 约束。

证据：

- [OrchestrationOperationsPage.vue](/Users/crxzy/Documents/crxzipple/frontend-v2/src/pages/operations/modules/OrchestrationOperationsPage.vue:468)
- [OrchestrationOperationsPage.vue](/Users/crxzy/Documents/crxzipple/frontend-v2/src/pages/operations/modules/OrchestrationOperationsPage.vue:1381)

建议：

- 后端 projection 增加 display label/tone/summary。
- 前端展示 translated label，raw key 放详情/debug。

### P3

#### P3-1. `OperationsProjection` dataclass 重复定义

状态：已由 R11 修正。当前应用层只保留一个 `OperationsProjection` 定义，DB projection store 与 read model 共享该 entity。

影响：后一个定义覆盖前一个，导致前一个 `from_payload()` 实际不可用。当前未发现调用，但属于明显工程卫生问题。

证据：

- [observation.py](/Users/crxzy/Documents/crxzipple/src/crxzipple/modules/operations/application/observation.py:217)
- [observation.py](/Users/crxzy/Documents/crxzipple/src/crxzipple/modules/operations/application/observation.py:254)

建议：

- 保留一个定义。
- 如果 DB store 仍需要 `from_payload()`，补回测试覆盖。

#### P3-2. DB 测试常量未更新到 `0040`

状态：已由 R3 / R8.1 修正。当前 `HEAD_REVISION` 为 `0041_create_operations_action_audits`，对应 action audit migration head。

影响：`tests/unit/test_db_cli.py` 两个断言失败。

证据：

- [cli_test_support.py](/Users/crxzy/Documents/crxzipple/tests/unit/cli_test_support.py:37)

建议：

- 将 `HEAD_REVISION` 更新为当前 Alembic head。
- 增加 migration head 自动校验，减少人工同步。

#### P3-3. `tests/unit/test_cli.py` 超出 top-level smoke 范围

影响：`test_cli.py` 包含模块级 runtime ensure、完整 ask/chat 集成流和旧 worker 断言，违背 `tests/unit/README.md` 的测试布局规则，也放大旧 observation 残留造成的失败面。

证据：

- [tests/unit/README.md](/Users/crxzy/Documents/crxzipple/tests/unit/README.md:17)
- [test_cli.py](/Users/crxzy/Documents/crxzipple/tests/unit/test_cli.py:9)
- [test_cli.py](/Users/crxzy/Documents/crxzipple/tests/unit/test_cli.py:70)
- [test_cli.py](/Users/crxzy/Documents/crxzipple/tests/unit/test_cli.py:292)

建议：

- 将模块级 CLI 覆盖迁移到 `test_<module>_cli.py`。
- `test_cli.py` 只保留 root command smoke。

#### P3-4. README 项目简介仍是 skeleton

状态：已由 R4 修正。README 首段已更新为本地 Agent Runtime 控制台和运行时简介。

影响：入口第一印象仍是 “DDD-oriented Python project skeleton”，和当前 Agent Runtime 控制台方向不一致。

证据：

- [README.md](/Users/crxzy/Documents/crxzipple/README.md:3)
- [AGENTS.md](/Users/crxzy/Documents/crxzipple/AGENTS.md:7)

建议：

- 更新 README 简介为本地 Agent Runtime / Operations console。

#### P3-5. Checklist 旧路径扫描会误报设计稿路径

状态：已由 R4 修正。checklist 的旧 UI Operations route 扫描已改为 API route 语义，并排除 `docs/ui/operations/*.png` 设计稿路径。

影响：`/ui/operations` 扫描会命中 `docs/ui/operations/*.png`，但这不是旧 API route，引起 checklist A 项误报。

证据：

- [code-quality-audit-checklist.md](/Users/crxzy/Documents/crxzipple/docs/reports/code-quality-audit-checklist.md:32)
- [current-ui-design-functional-spec.md](/Users/crxzy/Documents/crxzipple/docs/ui/current-ui-design-functional-spec.md:12)

建议：

- 将扫描条件改为 API route 语义，例如 `'/ui/operations'` 或 `GET /ui/operations`。
- 或排除 `docs/ui/operations` 图片路径。

#### P3-6. Checklist 报告模板缺 per-finding 字段

状态：已由 R4 修正。checklist 已要求 `File:line` 和 `Evidence` 字段，并给出 per-finding 模板。

影响：Checklist 要求文件路径，但没有明确要求行号/证据摘述，报告可操作性不稳定。

证据：

- [code-quality-audit-checklist.md](/Users/crxzy/Documents/crxzipple/docs/reports/code-quality-audit-checklist.md:262)
- [code-quality-audit-checklist.md](/Users/crxzy/Documents/crxzipple/docs/reports/code-quality-audit-checklist.md:271)

建议：

- 增加 finding 模板：`Severity / File:line / Evidence / Impact / Recommendation / Blocks hosted agents?`。

#### P3-7. Tool 页动态 i18n key 有潜在裸露风险

影响：Tool 页面 metric/tab 动态拼 key；当前 API 返回的 id 已有翻译，但新增 id 时可能裸露 `operations.tool.metric.<id>` 或 `operations.tool.tab.<id>`。

证据：

- [ToolOperationsPage.vue](/Users/crxzy/Documents/crxzipple/frontend-v2/src/pages/operations/modules/ToolOperationsPage.vue:794)

建议：

- 后端 projection 提供 display label，或前端加 fallback map/unknown label。
- i18n scan 增加动态 id 覆盖测试。

#### P3-8. `frontend-v2` bundle 偏大

影响：`npm run build` 通过，但 Vite 警告主 JS chunk 约 `978.69 kB`，超过 500 kB。

证据：

- [vite.config.ts](/Users/crxzy/Documents/crxzipple/frontend-v2/vite.config.ts:35)

建议：

- 增加 route-level lazy loading。
- 为 vendor / markdown / chart / heavy UI 做 manual chunks。

## Verification

Started at: `2026-05-06 11:10:29 CST`

### Coordinator Commands

```bash
git status --short
sed -n '1,260p' docs/reports/code-quality-audit-checklist.md
date '+%Y-%m-%d %H:%M:%S %Z'
```

### Documentation Workstream

```bash
find docs/archive -maxdepth 3 -type f
rg -n 'review-feedback|new-frontend-development-plan|current-code-architecture-review|web-console-blueprint' docs AGENTS.md README.md -g '!docs/reports/**'
rg -n "GET /ui/operations|POST /ui/operations|PATCH /ui/operations|DELETE /ui/operations|[\`\"'=]/ui/operations" docs AGENTS.md README.md -g '!docs/reports/**' -g '!docs/ui/operations/*.png"
find docs -name .DS_Store -print
```

Result:

- No old UI documents remain in archive.
- R4 follow-up: old UI Operations route scanning now uses route syntax and excludes `docs/ui/operations/*.png`.
- No `.DS_Store` under docs.
- Markdown links checked for key entry docs; no missing links found.

### Backend Workstream

```bash
git diff --check
find docs -name .DS_Store
rg 'except:\s*$|/Users/crxzy/Documents/crxzipple' src tests docs
PYTHONPYCACHEPREFIX=/tmp/crxzipple-pycache-audit PYTHONPATH=src python -m compileall -q src tests alembic
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src pytest --collect-only -q -p no:cacheprovider tests/unit
PYTHONPATH=src pytest -q tests/unit/test_shared_http.py tests/unit/test_operations_observation.py tests/unit/test_tool_background.py tests/unit/test_orchestration_service_surface.py
```

Result:

- `compileall`: passed.
- collect-only: passed, collected 1086 tests.
- healthy subset: `41 passed`.
- selected broader backend group: `88 passed, 8 failed`; failures concentrated around old `orchestration-observation` expectations and one CLI patch target drift.

### Operations / Daemon / DB Workstream

```bash
docker compose ps
python -m crxzipple.main db current
python -m crxzipple.main db history
curl /operations/tool
curl /operations/llm
curl /operations/orchestration
curl /operations/runtime
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py
PYTHONPATH=src pytest -q tests/unit/test_daemon_cli.py tests/unit/test_daemon_http.py
PYTHONPATH=src pytest -q tests/unit/test_daemon_manager.py
PYTHONPATH=src pytest -q tests/unit/test_daemon_service.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_cli.py -k observation
PYTHONPATH=src pytest -q tests/unit/test_db_cli.py
```

Result:

- Docker Compose Postgres and Redis: healthy.
- DB current: `0041_create_operations_action_audits (head)`.
- Alembic: single head, linear to `0041`.
- `operations_projections`: 18 rows, 9 modules with `page` + `overview`.
- `/operations/tool`, `/operations/llm`, `/operations/orchestration`: `200` JSON.
- `/operations/runtime`: PostgreSQL connected, Redis connected, migration current.
- `test_operations_observation.py`: `4 passed`.
- daemon CLI/HTTP: `29 passed`.
- daemon manager: `19 passed`.
- daemon service: `3 failed`, old observation expectations.
- orchestration CLI observation subset: `2 failed`, old observation CLI.
- DB CLI: stale `HEAD_REVISION` 已修正，当前相关验证通过。

### Frontend-v2 Workstream

```bash
cd frontend-v2 && npm run typecheck
cd frontend-v2 && npm run build
cd frontend-v2 && npm run audit:operations-layout
VITE_DATA_MODE=fixture npm run dev -- --port 5184
npm run audit:operations-layout -- --base-url http://127.0.0.1:5184 --output-dir ../tmp/operations-layout-audit-fixture
curl http://127.0.0.1:4173/api/operations/runtime
```

Result:

- `npm run typecheck`: passed.
- `npm run build`: passed with Vite chunk-size warning, main JS about `978.69 kB`.
- API-mode layout audit: passed, report under `tmp/operations-layout-audit/report.json`.
- Fixture-mode layout audit: passed.
- `/api/operations/runtime`: `200 application/json`.

## Recommended Fix Order

1. Remove old `orchestration-observation` code/CLI/test expectations.
2. Add runtime DB guard for daemon/worker/operations-observer CLI paths.
3. Register tool/llm EventDefinition and contract coverage.
4. Move Operations frontend owner-module calls behind Operations action/read endpoints.
5. Split Operations large detail payloads into paged/on-demand detail surfaces.
6. Add JSON 500 handler and standard action reason/risk/audit contracts.
7. Clean DDD application -> infrastructure direct imports.
8. Repair remaining P3 test/frontend hygiene items.

## Residual Risk

- Full `tests/unit` was not run to completion because targeted groups already expose failures.
- No dangerous POST action was executed during audit.
- Mobile/tablet layout was not covered; layout audit used desktop `1440x900`.
- API response model vs frontend TypeScript was not checked field-by-field.
- Worktree remains heavily dirty, so future agent tasks must inspect `git status` carefully before editing.
