# Closure Status 2026-05-07

本文档是 2026-05-07 收口状态。它不是新的施工计划，而是给后续 agent 判断当前仓库边界、验证结果和剩余风险的入口。

## 已收口

- Active docs 入口保持在 `docs/README.md`；旧 `code-quality-audit-checklist.md` 模板已移到 `docs/archive/reports/code-quality-audit-checklist-template-20260506.md`。
- 生产代码静态检查已收口：`ruff check src/crxzipple` 通过。
- Python 编译检查已收口：`PYTHONPATH=src python -m compileall -q src tests alembic` 通过。
- Frontend 基础闸门已收口：`npm run typecheck`、`npm run build` 通过。
- Operations 布局审计已收口：`npm run audit:operations-layout` 在临时 `vite preview --port 4174` 下通过，报告写入被 `.gitignore` 排除的 `tmp/operations-layout-audit/`。
- Alembic 线性已确认：唯一 head 是 `0043_settings_governance`，父链为 `0042_access_governance_persistence` -> `0041_create_operations_action_audits`。
- 临时 SQLite migration smoke 已通过：从 base 升级到 `0043_settings_governance (head)` 成功。SQLite 仍只作为测试或显式 fallback。
- Settings / Access / Operations 当前目标边界已写入 `AGENTS.md` 与 `docs/agents/hosted-agent-operating-contract.md`。

## Unit 验证

完整 `PYTHONPATH=src pytest -q tests/unit -x` 曾在 59% 后长时间无输出，被中断后改为按模块批次复跑。各批次均通过：

- Access / Agent / Authorization / Channel / Events：190 passed。
- Browser / Config / Daemon / DB / Event Relay / File-backed Memory：313 passed。
- LLM / Memory / Mobile / OCR / OpenAI Image / OpenAPI / Operations Observation：154 passed。
- Orchestration CLI：31 passed。
- Orchestration Context / Executor Leases / HTTP：55 passed。
- Orchestration Access / Approval / Queue / Service Surface / Tools：80 passed。
- Orchestration LLM Resolver / Memory：26 passed。
- Process / Prompt / Runtime / Serve：23 passed。
- Session：35 passed。
- Settings：18 passed。
- Shared / Skeleton / Skills / Test Layout / Text Encoding：35 passed。
- Tool：131 passed。
- Turns / UI / Worker Loops / Workspace Context：76 passed。
- Artifacts / Auth / CLI / Code Quality Budgets / Content / Conversations：35 passed。
- Dispatch / Events HTTP / Hidden Runtime / HTTP / Logger / Main CLI：24 passed。

`PYTHONPATH=src pytest --collect-only -q tests/unit` 当前收集 1214 tests。后续若需要“单进程全量 run”作为 CI 闸门，应单独定位 59% 后的长等待是否为顺序相关慢测；目前未发现失败断言。

## 版本控制边界

应纳入版本管理的主题分组：

- Settings governance：`src/crxzipple/modules/settings/**`、`src/crxzipple/shared/settings.py`、Settings HTTP/container/db 接线、Settings tests、`0043_settings_governance.py`。
- Access governance：`src/crxzipple/modules/access/**` 新 application/infrastructure/read model/action 代码、`src/crxzipple/shared/access.py`、Access tests、`0042_access_governance_persistence.py`。
- Module Settings consumption：agent/llm/tool/skills/channels/memory/orchestration 的 `settings_integration.py` 与相关 service/CLI/HTTP 调整。
- Operations projection/UI：`src/crxzipple/modules/operations/**`、`frontend/src/pages/operations/**`、Operations SSE refresh helper、i18n。
- Settings UI：`frontend/src/pages/settings/modules/AccessAssetsSettingsPage.vue` 与 Settings/Access i18n。
- Docs/agent constraints：`AGENTS.md`、`docs/README.md`、`docs/agents/hosted-agent-operating-contract.md`、本收口报告和仍有效的 reports。
- Tests：所有新增 `tests/unit/test_*settings*`、`test_access_*`、Settings/Access/Operations 相关更新。

不得纳入版本管理：

- `tmp/operations-layout-audit/**`
- `frontend/dist/**`
- `.pytest_cache/**`
- `.ruff_cache/**`
- `.crxzipple/**`
- `*.db`, `*.sqlite*`, `*.log`, `*.pid`, `.env*` 真实环境文件

这些路径已由 `.gitignore` 覆盖。

## 剩余风险

- 还未在本次收口中启动完整 Postgres + Redis + API + daemon + frontend live stack 做端到端 smoke。代码和 migration 已具备条件，但真实进程联动仍建议单独验收。
- `ruff check tests` 仍会被历史测试星号导入和未用 import 噪音淹没；当前只保证生产代码 `ruff check src/crxzipple` 干净。
- Tool / Skill / Channel / Memory / Runtime Defaults 的 Settings 生效语义仍偏向 container build / reconcile / restart。需要热应用时，应为对应模块补显式 reconcile/action，而不是由 UI 直接改模块私有状态。
- Authorization policy / temporary grant 仍是 Access/Authorization runtime 状态，Access config governance 则来自 Settings `access-assets`。如要把 policy governance 也完全配置化，需要另开明确任务。
