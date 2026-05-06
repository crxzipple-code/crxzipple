# Code Quality Audit Checklist

本文档是接下来代码质量查验的执行清单。目标是给托管 agent 一个可逐项勾选的入口，用来查清当前代码质量、架构边界、运行链路、前端一致性和文档状态。

查验完成后，应输出正式报告：

- 建议路径：`docs/reports/code-quality-audit-YYYYMMDD.md`
- 报告必须列出问题、严重级别、涉及文件行号、证据摘述、影响、建议修复顺序和已执行验证命令。

## 严重级别

- `P0`：阻塞启动、迁移、发起 turn、worker 执行或核心 API。
- `P1`：架构越界、数据真相错误、假数据、兼容泥潭。
- `P2`：前端布局、可观测性、i18n、API 契约、分页、错误展示问题。
- `P3`：测试覆盖、文档同步、命名、清理、工程卫生问题。

## A. 文档与入口

- [ ] `AGENTS.md` 存在，并明确托管 agent 开发约束。
- [ ] `docs/README.md` 存在，并作为 active docs 入口。
- [ ] `docs/agents/hosted-agent-operating-contract.md` 存在，并覆盖模块边界和施工规则。
- [ ] `docs/archive/` 不包含旧 UI 施工文档。
- [ ] 主文档不再引用旧 UI 施工路径。
- [ ] 主文档不再引用旧 UI Operations API route；`docs/ui/operations/*.png` 设计稿路径不算旧 route。
- [ ] `README.md` 指向 `AGENTS.md` 和 `docs/README.md`。
- [ ] `docs/operations-data-truth-audit.md` 描述当前 `/operations/{module}` + projection 链路。
- [ ] `docs/ui/runtime-ui-read-model-contracts.md` 与当前 Operations 方案一致。

建议命令：

```bash
rg -n 'review-feedback|new-frontend-development-plan|current-code-architecture-review|web-console-blueprint' docs AGENTS.md README.md -g '!docs/reports/**' || true
rg -n "GET /ui/operations|POST /ui/operations|PATCH /ui/operations|DELETE /ui/operations|[\`\"'=]/ui/operations" docs AGENTS.md README.md -g '!docs/reports/**' -g '!docs/ui/operations/*.png' || true
find docs -name .DS_Store -print
```

## B. 工作树安全

- [ ] 已记录 `git status --short`。
- [ ] 区分本轮改动和用户/历史改动。
- [ ] 未回滚无关文件。
- [ ] 未删除仍被引用的文档或代码。
- [ ] 没有 `.DS_Store`、临时日志、构建产物误入主文档区。

建议命令：

```bash
git status --short
git diff --check
```

## C. Python 基础闸门

- [ ] `PYTHONPATH=src python -m compileall -q src tests alembic` 通过。
- [ ] `PYTHONPATH=src pytest -q tests/unit` 通过，或记录失败列表。
- [ ] 没有已删除模块仍被 import。
- [ ] 没有明显循环 import。
- [ ] 没有裸 `except` 吞运行错误。
- [ ] 没有新代码依赖本机绝对路径。
- [ ] 没有新增未使用的大段兼容 shim。

建议命令：

```bash
PYTHONPATH=src python -m compileall -q src tests alembic
PYTHONPATH=src pytest -q tests/unit
rg -n 'except:\\s*$|/Users/[^[:space:]]+/Documents/[^[:space:]]+' src tests docs || true
```

## D. 架构边界

- [ ] `orchestration` 没有复活旧 facade。
- [ ] 不存在 `OrchestrationControlService`。
- [ ] 不存在新的 `orchestration/application/services.py`。
- [ ] 不存在新的 `orchestration/application/router.py`。
- [ ] 不存在新的旧式 `session_resolver.py`。
- [ ] `tool` 不直接完成 orchestration run。
- [ ] `llm` 不直接推进 run 或写 session。
- [ ] `events` 不包含业务调度判断。
- [ ] `operations` 不成为业务 owner。
- [ ] 业务模块只提供通用 service/query，不提供 Operations 专用页面 provider。

建议命令：

```bash
rg -n 'OrchestrationControlService|orchestration-observation|session_resolver|application/services.py|application/router.py' src tests docs || true
rg -n 'complete.*orchestration|orchestration.*complete|run.*complete' src/crxzipple/modules/tool src/crxzipple/modules/llm || true
```

## E. Events / Runtime 事实链

- [ ] 关键运行事实有事件名、topic、owner、payload。
- [ ] 跨进程场景默认使用 Redis events backend。
- [ ] in-memory event backend 只用于单进程测试。
- [ ] event contract / definition registry 覆盖新增事件。
- [ ] Trace / Operations 所需事件字段足够重建 read model。
- [ ] HTTP 请求不会为了长窗口图表全量扫所有 topic。

建议命令：

```bash
rg -n 'EventTopicContract|EventRouteContract|register_topic|register_route|publish\\(' src/crxzipple/modules src/crxzipple/shared
rg -n 'read_recent_event_topic|read_event_topic|list_event_topics' src/crxzipple/modules/operations src/crxzipple/interfaces/http
```

## F. Operations 链路

- [ ] `operations-observer` 是独立 daemon worker。
- [ ] 不存在旧 `orchestration-observation` worker。
- [ ] `operations_projection_store` 是 `/operations/*` 主读取源。
- [ ] `operations_projections` migration 存在且已接入 ORM import。
- [ ] `OperationsProjectionMaterializer` 覆盖 9 个模块。
- [ ] `.crxzipple/operations/observer_observation.json` 不保存 page projection。
- [ ] `/operations/tool` 返回 JSON。
- [ ] `/operations/llm` 返回 JSON。
- [ ] `/operations/orchestration` 返回 JSON。
- [ ] 缺 projection 时返回可诊断错误，不静默返回假数据。
- [ ] 各模块关键卡片标明真实数据来源。

建议命令：

```bash
source scripts/dev/infra-env.sh
python -m crxzipple.main db upgrade head
python -m crxzipple.main operations-observer process --limit-per-subscription 10
curl -sS -H 'Accept: application/json' http://127.0.0.1:8000/operations/tool >/tmp/ops-tool.json
curl -sS -H 'Accept: application/json' http://127.0.0.1:8000/operations/llm >/tmp/ops-llm.json
curl -sS -H 'Accept: application/json' http://127.0.0.1:8000/operations/orchestration >/tmp/ops-orchestration.json
rg -n '\"projections\"|\"projection\"' .crxzipple/operations/observer_observation.json || true
```

## G. Daemon / Worker

- [ ] `daemon services` 包含 worker service set。
- [ ] 存在 `worker:orchestration-scheduler`。
- [ ] 存在 `worker:orchestration`。
- [ ] 存在 `worker:event-relay`。
- [ ] 存在 `worker:operations-observer`。
- [ ] 存在 `worker:tool-scheduler`。
- [ ] 存在 `worker:tool`。
- [ ] 不存在 `worker:orchestration-observation`。
- [ ] tool worker `max_in_flight` 配置生效。
- [ ] worker lease / heartbeat / recovery 可查询。
- [ ] 长运行 worker 不需要人工散养启动。

建议命令：

```bash
source scripts/dev/infra-env.sh
python -m crxzipple.main daemon services
python -m crxzipple.main daemon status
python -m crxzipple.main daemon show worker:tool
python -m crxzipple.main daemon show worker:operations-observer
```

## H. 数据库与迁移

- [ ] Postgres + Redis 是默认本地运行路径。
- [ ] SQLite 只作为显式 fallback 或测试路径。
- [ ] Alembic history 无分叉。
- [ ] `python -m crxzipple.main db current` 正常。
- [ ] 新 ORM model 在 `core/db.py import_models()` 中导入。
- [ ] 新表有 repository 测试。
- [ ] projection/read model 表有 `version` / `updated_at` / `query_key`。
- [ ] 查询接口有 `limit/offset` 或 cursor。
- [ ] 没有运行态无限 list 返回。

建议命令：

```bash
source scripts/dev/infra-env.sh
python -m crxzipple.main db current
python -m crxzipple.main db history
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py
rg -n 'limit: int|offset: int|cursor' src/crxzipple/modules/*/interfaces src/crxzipple/modules/*/application
```

## I. API 质量

- [ ] HTTP router 保持薄。
- [ ] 业务逻辑在 application service。
- [ ] 错误响应是 JSON。
- [ ] action endpoint 包含 reason / risk / audit / permission 语义。
- [ ] 危险动作需要确认。
- [ ] response model 不吞前端需要字段。
- [ ] response model 不泄露内部 raw key 给用户。
- [ ] API 和前端 TS 类型一致。

建议命令：

```bash
rg -n 'HTTPException|@router\\.|reason|risk|audit|permission|requires_confirmation' src/crxzipple/modules/*/interfaces src/crxzipple/interfaces/http
rg -n 'response_model|BaseModel' src/crxzipple/modules/*/interfaces src/crxzipple/interfaces/http
```

## J. Frontend 基础闸门

- [ ] `cd frontend && npm run typecheck` 通过。
- [ ] `cd frontend && npm run build` 通过。
- [ ] `cd frontend && npm run audit:operations-layout` 通过。
- [ ] `VITE_API_BASE=/api` proxy 返回 JSON。
- [ ] API HTML 错误页被 client 明确报错。
- [ ] fixture mode 和 api mode 都可进入页面。
- [ ] 没有恢复旧前端目录；当前 UI 只在 `frontend/`。

建议命令：

```bash
cd frontend
npm run typecheck
npm run build
npm run audit:operations-layout
rg -n 'Expected JSON|VITE_API_BASE|VITE_DATA_MODE|fixture|requestJson' src
```

## K. Frontend UI 质量

- [ ] PC 端按全屏应用布局。
- [ ] Operations 首屏显示关键监控信息。
- [ ] 主表格区域占主要面积。
- [ ] 右侧区域用于摘要、图表、风险、详情。
- [ ] 卡片无数据时高度稳定。
- [ ] skeleton 与真实数据布局差异小。
- [ ] 没有卡片内部小滚动条承载核心监控信息。
- [ ] 表格有分页或明确截断。
- [ ] 长错误和详情进入右侧 drawer。
- [ ] 没有裸露 i18n key。
- [ ] 没有明显假数据图表。
- [ ] Tool / LLM / Orchestration 对齐设计稿。
- [ ] 其他 Operations 模块也按全屏控制台思路整理。

建议命令：

```bash
cd frontend
npm run audit:operations-layout
rg -n 'operations\\.[a-zA-Z0-9_.-]+' src/pages src/shared | head -200
rg -n 'overflow-y: auto|overflow: auto|height: [0-9]+px|min-height: [0-9]+px' src/pages src/shared/styles
```

## L. Tests 结构

- [ ] `tests/unit/README.md` 仍准确。
- [ ] CLI 测试在 `test_<module>_cli.py`。
- [ ] HTTP 测试在 `test_<module>_http.py`。
- [ ] domain/application 测试按模块拆分。
- [ ] shared support 放 `<module>_test_support.py`。
- [ ] `test_cli.py` 没有塞模块级 CLI 细节。
- [ ] `test_http.py` 没有塞模块级 HTTP 细节。
- [ ] 测试不依赖真实外部 API key。
- [ ] 测试不依赖本机绝对路径。
- [ ] 测试不依赖执行顺序。

建议命令：

```bash
find tests/unit -maxdepth 1 -type f | sort
rg -n '/Users/|OPENAI_API_KEY|ANTHROPIC_API_KEY|GEMINI_API_KEY|depends on order|pytest.mark.order' tests || true
```

## M. 报告输出

- [ ] 每个问题有文件路径和行号，格式为 `File:line`；无法稳定定位单行时说明原因。
- [ ] 每个问题有严重级别：`P0` / `P1` / `P2` / `P3`。
- [ ] 每个问题有 `Evidence` 字段，摘述触发判断的代码、文档或命令输出。
- [ ] 每个问题有影响说明。
- [ ] 每个问题有建议修复方向。
- [ ] 标记是否阻塞托管 agent 后续开发。
- [ ] 记录已执行命令和结果。
- [ ] 记录未执行验证及原因。
- [ ] 给出建议修复顺序。

报告建议结构：

```markdown
# Code Quality Audit YYYY-MM-DD

## Summary

## Findings

### P0

#### P0-N. Short title

- Severity: `P0`
- File:line: `path/to/file.ext:123`
- Evidence: short quote, symbol name, command result, or behavior observed.
- Impact: why this matters.
- Recommendation: smallest target-architecture fix.
- Blocks hosted agents?: yes/no.

### P1

### P2

### P3

## Verification

## Recommended Fix Order

## Residual Risk
```
