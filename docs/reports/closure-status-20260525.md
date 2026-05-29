# Closure Status 2026-05-25

本文档是 2026-05-25 收口状态。它不是新的施工计划，而是给后续 agent 判断当前仓库边界、验证结果和剩余风险的入口。

## 已收口

- Active docs 入口保持在 `docs/README.md`；旧 `code-quality-audit-checklist.md` 模板已移到 `docs/archive/reports/code-quality-audit-checklist-template-20260506.md`。
- 生产代码静态检查已收口：`ruff check src/crxzipple` 通过。
- Python 编译检查已收口：`PYTHONPATH=src python -m compileall -q src tests alembic` 通过。
- Frontend 基础闸门已收口：`npm run typecheck`、`npm run build` 通过。
- Operations 布局审计已收口：`npm run audit:operations-layout` 在临时 `vite preview --port 4174` 下通过，报告写入被 `.gitignore` 排除的 `tmp/operations-layout-audit/`。
- Alembic 线性已确认：唯一 head 是 `0061_cleanup_legacy_browser_tool_sources (head)`。
- 当前运行主线默认使用 Docker Compose/Postgres/Redis；SQLite 只作为测试或显式 fallback。
- Settings / Access / Operations / Tool / Browser / Memory / Skill / Runtime assembly 当前目标边界已写入 `AGENTS.md` 与 `docs/agents/hosted-agent-operating-contract.md`，专项施工记录保留在 `docs/reports/*`。

## Unit 验证

2026-05-25 单进程全量 unit 已通过；pytest 分层闸门也已更新，详见
`docs/reports/pytest-runtime-governance-checklist-20260518.md`。

- `PYTHONPATH=src pytest --collect-only -q tests/unit`：1596 tests collected。
- `make test-unit-fast`：846 passed, 750 deselected, 64.15s。
- `make test-unit-runtime`：750 passed, 846 deselected, 246.96s。
- `make test-live`：5/1601 tests collected, 1596 deselected, 1.67s。
- `make test-unit`：1596 passed, 314.76s。

后续默认不要把 live/benchmark 测试混入日常 unit；涉及 daemon、browser、process、
orchestration worker、Postgres/Redis 并发语义时，应按风险选择 runtime 或 integration
层级。

## 版本控制边界

应纳入版本管理的主题分组：

- App assembly/runtime container：`src/crxzipple/app/**`、`src/crxzipple/interfaces/runtime_container.py`、HTTP/CLI dependency 接线和 assembly 架构测试。
- Settings governance：`src/crxzipple/modules/settings/**`、`src/crxzipple/shared/settings.py`、Settings HTTP/container/db 接线和 Settings tests。
- Access governance：`src/crxzipple/modules/access/**` application/infrastructure/read model/action/oauth/credential requirement 代码、`src/crxzipple/shared/access.py`、Access tests。
- Module Settings consumption：agent/llm/tool/channels/memory/runtime-defaults 的 owner API、settings UI 和相关 service/CLI/HTTP 调整。
- Operations projection/UI：`src/crxzipple/modules/operations/**`、`frontend/src/pages/operations/**`、Operations projection refresh helper、i18n。
- Tool / Browser / Skill / Memory 架构升级：对应模块代码、`tools/*/tool.yaml`、skill owner catalog、memory engine/space/policy、browser host/CDP/daemon MCP 接线、专项 tests 和 docs。
- Settings UI：`frontend/src/pages/settings/modules/AccessAssetsSettingsPage.vue` 与 Settings/Access i18n。
- Docs/agent constraints：`AGENTS.md`、`docs/README.md`、`docs/agents/hosted-agent-operating-contract.md`、本收口报告和仍有效的 reports。
- Migrations：`alembic/versions/0045_*` 到 `0061_cleanup_legacy_browser_tool_sources.py` 的当前线性迁移。
- Tests：所有新增/更新的 assembly、settings、access、operations、tool、browser、skill、memory、runtime 分层测试。

不得纳入版本管理：

- `tmp/operations-layout-audit/**`
- `frontend/dist/**`
- `.pytest_cache/**`
- `.ruff_cache/**`
- `.crxzipple/**`
- `*.db`, `*.sqlite*`, `*.log`, `*.pid`, `.env*` 真实环境文件

这些路径已由 `.gitignore` 覆盖。

## 剩余风险

- 本次收口跑过单元、静态、构建和 Operations 布局审计；未重新拉起完整 Postgres + Redis + API + daemon + frontend live stack 做端到端 smoke。代码和 migration 已具备条件，但真实进程联动仍建议单独验收。
- `ruff check tests` 仍会被历史测试星号导入和未用 import 噪音淹没；当前只保证生产代码 `ruff check src/crxzipple` 干净。
- Browser 默认能力已收口到单一 `configured.browser` Tool Source 和 `browser.*` functions；Browser profile 是运行上下文，daemon 只保留 `host:browser:{profile}`，后续不要恢复 per-profile Browser MCP source/service。
- `operations-observer rebuild` 是 projection rebuild，不再 reset observation 或全量重放事件；需要补历史观察时应走显式 observer 维护命令。
- Tool / Skill / Channel / Memory / Runtime Defaults 的 Settings 生效语义仍偏向 owner API / reconcile / restart。需要热应用时，应为对应模块补显式 reconcile/action，而不是由 UI 直接改模块私有状态。
- Authorization policy / temporary grant 仍是 Authorization runtime 状态，Access 负责外部凭证和 credential requirement governance。不要再把内部 ABAC 与外部 credential asset 混成同一套 Access 设置。
