# Code Quality Follow-up Checklist 2026-05-06

本文档是当前仍需处理的代码规范性问题清单，来源于 2026-05-06 第二轮 agent 审查。旧
`code-quality-audit-20260506.md` 和 `code-quality-remediation-tasks-20260506.md`
已经归档到 `docs/archive/reports/`，不得再作为当前待办依据。

## 执行规则

- 优先处理 P1，再处理 P2/P3。
- 不回滚用户或其他 agent 的改动。
- 不增加兼容 shim；所有修复服务重构后的目标结构。
- 每项完成时必须补测试或扫描命令，并在本文件勾掉对应项。
- 若发现本清单与 `AGENTS.md` / `docs/agents/hosted-agent-operating-contract.md` 冲突，以 agent contract 为准，并同步修本文档。

## P1 必修

### F1. Operations action surface 收口到 `/operations/*`

状态：已处理。

处理记录：

- Runtime action 增加 `kind`，可执行动作 endpoint 收口到 `/operations/*`；纯跳转标记为 `navigation`。
- `/ui/bootstrap` 不再为 Operations action 暴露 owner module 动作 route。
- 验证：`rg -n 'endpoint="/(turns|orchestration|tools|llms|channels|skills|access|daemon|memory)' src/crxzipple/modules/operations/application/read_models src/crxzipple/interfaces/http/ui.py || true` 无输出；`PYTHONPATH=src pytest -q tests/unit/test_ui_http.py tests/unit/test_operations_observation.py` 通过。

问题：

- Operations read model 仍把 action endpoint 指向 owner module API，例如 `/turns`、`/orchestration`、`/tools`、`/daemon`、`/access`。
- 这些 action 会绕过 Operations 统一 reason/risk/audit/permission 语义。

目标：

- Operations read model 中所有可执行 action 指向 `/operations/{module}/actions/*` 或统一 `/operations/actions/*` dispatcher。
- `/ui/bootstrap` 不再为 Operations 动作暴露 owner module route。
- 前端 Operations 页面不直接执行 owner module action。
- 保留纯导航链接时必须显式标记为 navigation，不作为 action。

建议验证：

```bash
rg -n 'endpoint="/(turns|orchestration|tools|llms|channels|skills|access|daemon|memory)' \
  src/crxzipple/modules/operations/application/read_models src/crxzipple/interfaces/http/ui.py || true
PYTHONPATH=src pytest -q tests/unit/test_ui_http.py tests/unit/test_operations_observation.py
```

### F2. Operations 实时刷新改成 Operations SSE surface

状态：已处理。

处理记录：

- 新增 `/operations/stream`，输出 `projection_updated` 等 Operations 语义 SSE。
- OperationsShell 改为订阅 `/operations/stream`；raw `/events/stream` helper 移到 Workbench 本地 API，不再位于 shared/Operations surface。
- 验证：`rg -n '/events/stream|openEventStream|source_payload|topicPrefix: "events.named.operations.projection' frontend/src/pages/operations frontend/src/shared || true` 无输出；`cd frontend && npm run typecheck && npm run build` 通过。

问题：

- `frontend` OperationsShell 直接订阅 `/events/stream`。
- 前端解析 raw event record 的 `source_payload.module/module_id/modules` 来决定刷新哪个模块。

目标：

- 新增 `/operations/stream`、`/operations/refresh-feed` 或等价 Operations-owned SSE endpoint。
- SSE payload 使用 Operations 语义，例如 `projection_updated`、`module_invalidated`、`runtime_status_changed`。
- 前端不读取 event topic、cursor、source_payload，不依赖 Events 模块 raw record schema。
- Events 模块仍可作为诊断页展示 raw stream，但不作为 Operations shell 的刷新协议。

建议验证：

```bash
rg -n '/events/stream|openEventStream|source_payload|topicPrefix: "events.named.operations.projection' \
  frontend/src/pages/operations frontend/src/shared || true
cd frontend && npm run typecheck && npm run build
```

### F3. 危险动作不能由前端自动确认风险

状态：已处理。

处理记录：

- 前端 `operationsActionPayload()` 不再自动补危险动作确认或风险确认。
- Events / Channels / Daemon 危险动作显式确认后才传 `confirmation` 与 `risk_acknowledged`。
- 后端保持强校验，新增 HTTP 测试覆盖危险动作缺确认/缺风险确认返回 400。
- 验证：`PYTHONPATH=src pytest -q tests/unit/test_ui_http.py tests/unit/test_operations_observation.py` 通过。

问题：

- `operationsActionPayload()` 对 dangerous action 默认 `confirmation=true`、`risk_acknowledged=true`。
- Events advance action 只 prompt reason，没有独立确认。

目标：

- 前端不得自动补危险动作确认。
- dangerous action 必须有明确确认 UI，且确认内容进入 payload/audit。
- 后端继续强校验 reason、confirmation、risk_acknowledged。
- 增加至少一条前端或 HTTP 测试覆盖未确认危险动作失败。

建议验证：

```bash
rg -n 'confirmation:.*true|risk_acknowledged:.*true|dangerous' \
  frontend/src/pages/operations src/crxzipple/modules/operations
PYTHONPATH=src pytest -q tests/unit/test_ui_http.py tests/unit/test_operations_observation.py
```

### F4. EventDefinition 覆盖 observer 订阅和投影刷新事件

状态：已处理。

处理记录：

- 补齐 `tool.enabled`、`tool.disabled`、`llm.stream_delta_observed`、`operations.projection.invalidated` 与 orchestration operational events 的 EventDefinition。
- 新增 observer 订阅事件集合必须被 registry 覆盖的防回归测试。
- 验证：缺口脚本无输出；`PYTHONPATH=src pytest -q tests/unit/test_events.py tests/unit/test_operations_observation.py` 通过。

问题：

- 当前 observer 订阅和代码发布的事件仍有缺口。
- 已核出的缺失包括 `tool.enabled`、`tool.disabled`、`llm.stream_delta_observed`、`operations.projection.invalidated`，以及多条 orchestration ingress/scheduler/executor operational event。

目标：

- `operations_observer_event_names(registry)` 中所有事件都有 EventDefinition。
- `operations.projection.invalidated` 注册为稳定 UI/Operations refresh contract。
- EventDefinition 包含 owner、level、summary/display、linked entity 字段。
- `tests/unit/test_events.py` 增加防回归测试。

建议验证：

```bash
PYTHONPATH=src python - <<'PY'
from crxzipple.bootstrap.container import _build_event_definition_registry
from crxzipple.modules.operations.application.runtime import operations_observer_event_names

registry = _build_event_definition_registry()
defined = {item.event_name for item in registry.list_definitions()}
missing = sorted(set(operations_observer_event_names(registry)) - defined)
print("\n".join(missing))
raise SystemExit(1 if missing else 0)
PY
PYTHONPATH=src pytest -q tests/unit/test_events.py tests/unit/test_operations_observation.py
```

### F5. Operations tool/llm 列表和详情做真正分页

状态：已处理。

处理记录：

- Tool / LLM page projection 缩回首屏；主表格数据另存为 `kind=table`、`query_key=tool_runs/recent_invocations` 的 projection。
- detail projection 随分页 table materialization 补齐，窗口外 detail 可按 id 读取；缺失仍返回 404。
- `/operations/tool`、`/operations/llm` 查询优先读取 table projection 后再应用筛选与 `limit/offset`。
- 验证：`PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py tests/unit/test_ui_http.py` 通过。

问题：

- 当前 `/operations/tool` 和 `/operations/llm` 只在已物化窗口中 slice。
- materializer/provider 有固定窗口，超过窗口的数据和 detail projection 不可达。

目标：

- page projection 只保存首屏/摘要；表格查询走 query_key 或独立 list projection。
- `limit/offset` 或 cursor 能触达全量历史，而不是 200 条窗口内分页。
- detail endpoint 能按 id 查询窗口外记录，缺失时返回明确 404/diagnostic。
- 前端分页不展示超过真实可达范围的页码。

建议验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py tests/unit/test_ui_http.py
rg -n 'limit=1000|max(.*200|offset' \
  src/crxzipple/modules/operations/application/projections.py \
  src/crxzipple/modules/operations/application/read_models \
  src/crxzipple/modules/operations/interfaces/http.py
```

### F6. 长运行入口 SQLite guard 收尾

状态：已处理。

处理记录：

- `channel-runtime run` 加入统一 `guard_runtime_database`。
- `serve` 移除 `APP_ALLOW_SQLITE_SERVE` 专用放行，SQLite runtime fallback 只接受 `APP_ALLOW_SQLITE_RUNTIME_FALLBACK=1`。
- 验证：`PYTHONPATH=src pytest -q tests/unit/test_channels_cli.py tests/unit/test_serve_cli.py tests/unit/test_config.py` 通过；接口层无 `APP_ALLOW_SQLITE_SERVE` 残留。

问题：

- `channel-runtime run` 是长运行入口，但没有 `guard_runtime_database`。
- `serve` 仍接受非统一 env `APP_ALLOW_SQLITE_SERVE`。

目标：

- `channel-runtime run` 使用与 daemon/scheduler/executor/observer/tool worker 相同的 runtime DB guard。
- SQLite runtime fallback 只接受 `APP_ALLOW_SQLITE_RUNTIME_FALLBACK=1`。
- 移除或废弃 `APP_ALLOW_SQLITE_SERVE`。
- 补 `test_channels_cli.py` 和 `test_serve_cli.py` 负向测试。

建议验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_channels_cli.py tests/unit/test_serve_cli.py tests/unit/test_config.py
rg -n 'APP_ALLOW_SQLITE_SERVE|guard_runtime_database' src/crxzipple/interfaces src/crxzipple/modules/*/interfaces
```

### F7. 当前 agent/dev/migration 关键文件必须进入版本控制边界

状态：已处理。

处理记录：

- 已在 `da41ccf` / `417712d` 将 agent contract、dev stack、migration head、当前唯一 `frontend/` 与基础验证纳入版本控制。
- 验证：`PYTHONPATH=src python -m alembic heads` 为 `0041_create_operations_action_audits (head)`；当前无未跟踪关键文件。

问题：

- `AGENTS.md`、`Makefile`、`compose.yaml`、`docs/README.md`、`docs/agents/`、`tests/conftest.py` 仍是未跟踪文件。
- `0041_create_operations_action_audits.py` 是当前 head，但 migration 文件未跟踪。
- 多个旧 migration 有修改，需要明确是历史整理还是误改。

目标：

- 当前 agent contract、dev stack、test setup、migration head 都不处于 `??` 状态。
- 对旧 migration 改动逐个确认；若不是刻意历史整理，应改为新 migration 或撤回对应改动。
- 测试中的 Alembic expected head 与实际 migration head 保持一致。

建议验证：

```bash
git status --short -- AGENTS.md Makefile compose.yaml docs/README.md docs/agents alembic/versions tests/conftest.py
PYTHONPATH=src python -m alembic heads
PYTHONPATH=src pytest -q tests/unit/test_db_cli.py
```

## P2 结构收口

### F8. 收轻 file-backed orchestration observation 依赖

状态：已处理。

处理记录：

- Operations orchestration page 不再读取 rich file-backed orchestration observation；运行事实来自 orchestration query service、executor control 与 Operations event projection。
- 保留 file-backed observer 轻量状态读取，仅用于 observer health/freshness。
- 移除 rich orchestration snapshot 模型、file-backed 写入和 snapshot `orchestration` 字段；旧文件中的 `orchestration` key 读取时会被忽略，新写文件不再带该 key。
- 新增回归测试确保 orchestration page 只依赖 module observation。
- 验证：`PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py tests/unit/test_ui_http.py -q` 通过。

目标：

- `.crxzipple/operations/observer_observation.json` 只保存 observer 轻量状态。
- orchestration page projection 不再依赖 rich file-backed runs/ingress/signals/executors state。
- 运行态事实来自事件投影、query service 或 projection store。

建议验证：

```bash
rg -n 'OperationsOrchestrationObservation|record_orchestration|get_orchestration_observation|"orchestration"\s*:' \
  src/crxzipple/modules/operations/application/observation.py \
  src/crxzipple/modules/operations/application/orchestration_observation.py \
  src/crxzipple/modules/operations/infrastructure/observation_store.py
```

### F9. application 层 shared infrastructure 依赖收口为 port

状态：已处理。

处理记录：

- daemon application 通过 `ShellResolver` / `EndpointProbe` port 注入 shell 和 endpoint probe。
- orchestration application 通过 database transient error classifier port 隔离 SQLAlchemy-aware 判断。
- channels application 从 `shared.infrastructure.http` 迁到 `shared.http`，不再直接依赖 shared infrastructure package。
- 验证：`rg -n 'from crxzipple\.shared\.infrastructure|import crxzipple\.shared\.infrastructure' src/crxzipple/modules/*/application src/crxzipple/modules/*/domain || true` 无输出。

目标：

- `daemon.application` 不直接调用 shared infrastructure HTTP helper。
- `orchestration.application` 不直接依赖 SQLAlchemy-aware database error classifier。
- 通过 application port / injected adapter 隔离基础设施实现。

建议验证：

```bash
rg -n 'from crxzipple\.shared\.infrastructure|import crxzipple\.shared\.infrastructure' \
  src/crxzipple/modules/*/application src/crxzipple/modules/*/domain || true
```

### F10. HTTP error envelope 与 tool run 404 一致化

状态：已处理。

处理记录：

- `GET /tools/runs/{run_id}` 对缺失 run 返回 404 JSON detail。
- HTTP unhandled exception handler 移到 `crxzipple.shared.http`，旧 infrastructure 入口仅作内部 re-export。
- 补充 tool run 404 与 shared JSON exception handler 单测。
- 验证：`PYTHONPATH=src pytest -q tests/unit/test_tool_http.py tests/unit/test_shared_http.py` 通过。

目标：

- `GET /tools/runs/{run_id}` 缺失时返回 404 JSON，而不是 unhandled 500。
- authorization、module `HTTPException`、unhandled exception 使用一致 JSON envelope。
- 前端 API client 对错误 envelope 有稳定解析。

建议验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_tool_http.py tests/unit/test_shared_http.py
rg -n 'HTTPException|ToolRunNotFoundError|exception_handler' src/crxzipple
```

### F11. raw key/i18n/DOM 后处理收口

状态：已处理。

处理记录：

- 移除 AppShell 全局 `MutationObserver` 静态文案替换。
- DataTable 与 Operations formatter 对 raw key 增加稳定 fallback；Events/Trace/debug 场景可保留 raw value。
- Orchestration event rows 不再把 raw event key 作为主显示文案。
- 验证：`cd frontend && npm run typecheck` 通过；`npm run audit:operations-layout -- --warn-only --no-screenshots` 通过。

目标：

- 主视图不裸露 backend raw event/topic/metric key；raw key 仅在 Events/Trace/debug drawer。
- 移除或逐步退场全局 DOM MutationObserver 静态文案替换。
- 固定用户可见文案进入 i18n message table。
- 未知动态 key 展示稳定 fallback label，并保留 debug 原值。

建议验证：

```bash
cd frontend && npm run typecheck
rg -n 'MutationObserver|return value|source_payload|event_key|topic' \
  src/app src/pages/operations src/shared
```

### F12. action audit risk 语义保持 `normal/controlled/dangerous`

状态：已处理。

处理记录：

- Operations action audit payload 保持 `normal`、`controlled`、`dangerous` 三值语义，`controlled` 不再被压扁成 `normal`。
- Runtime action response 和 audit response 均暴露稳定 `audit_event`；audits read API 保留 `/operations/actions/audits`。
- 补充 controlled audit payload、action `audit_event` 与 dangerous audit response 单测。
- 验证：`PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py tests/unit/test_ui_http.py -q` 通过。

目标：

- `controlled` risk 不再被 audit payload 压扁成 `normal`。
- response model 与 docs 中的 `audit_event` / audit id / risk 字段一致。
- Operations action audit 列表进入后续运维面，至少提供 read API。

建议验证：

```bash
rg -n 'controlled|dangerous|audit_event|operations_action_audits' \
  src/crxzipple/modules/operations docs/ui/runtime-ui-read-model-contracts.md tests/unit
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py
```

### F13. frontend Operations 布局稳定性继续压实

状态：已处理。

处理记录：

- Operations shared styles 压实 empty/table panel 高度，降低 loading/empty/loaded 之间的大幅跳变。
- Operations 多模块页面继续按全屏应用主表格 + 侧栏摘要布局，避免卡片内部无意义滚动。
- `audit:operations-layout` 默认端口改为 Vite preview `4174`。
- 验证：`cd frontend && npm run typecheck` 通过；`npm run audit:operations-layout -- --warn-only --no-screenshots` 通过。

目标：

- loading placeholder / empty 与真实数据布局高度稳定。
- Access 等模块无数据时也保留 metric/card grid 尺寸。
- 主表格、右侧摘要、drawer 继续按全屏监控应用布局。
- `audit:operations-layout` 默认端口与 Vite preview/dev 配置一致。

建议验证：

```bash
cd frontend
npm run build
OPERATIONS_AUDIT_BASE_URL=http://127.0.0.1:4174 npm run audit:operations-layout
```

## P3 工程卫生

### F14. 巨型测试与巨型组件拆分

状态：已处理。

处理记录：

- 从 `ToolOperationsPage.vue` 抽出 Tool Operations 页面稳定 view helper、filter/tab 常量、formatter、artifact/row helper 到 `frontend/src/pages/operations/modules/tool/viewHelpers.ts`，页面行为保持原引用路径和模板结构不变。
- 将 Operations action/audit HTTP 测试迁出到 `tests/unit/test_ui_operations_actions_http.py`，降低 `test_ui_http.py` 聚合压力。
- 新增 `tests/unit/test_code_quality_budgets.py`，对 F14 关注的巨型组件/测试文件设置轻量行数 budget；`tests/browser/test_browser_tool_http.py` 当前不存在，guard 会在存在时自动覆盖。
- 验证：`cd frontend && npm run typecheck` 通过；`PYTHONPATH=src pytest -q tests/unit/test_ui_operations_actions_http.py tests/unit/test_code_quality_budgets.py` 通过。

目标：

- `test_ui_http.py`、`test_browser_tool_http.py` 等按模块/契约拆分。
- `ToolOperationsPage.vue` 拆出表格、drawer、artifact preview、charts、i18n helper 等子模块。
- 为组件/测试文件大小增加轻量 guard 或 checklist 项。

### F15. 文档口径保持单一

状态：已处理。

处理记录：

- `docs/README.md` 以当前 follow-up checklist 为待办入口，历史 audit/remediation 继续指向 archive。
- active docs 保留当前 Operations/daemon 架构约束，但不再把已完成的旧 observation worker 清理和旧 SQLite guard 缺口写成当前待办。
- 验证：建议扫描无输出。

目标：

- active docs 只指向当前 checklist 和当前架构约束。
- 历史 audit/remediation 留在 `docs/archive/reports/`。
- active docs 不再把已完成的旧 observation 清理、旧 SQLite guard 缺口写成当前待办。

建议验证：

```bash
rg -n 'orchestration-observation|HEAD_REVISION|DB CLI|SQLite.*worker/observer' \
  docs -g '!docs/archive/**' -g '!docs/reports/code-quality-followup-checklist-20260506.md' || true
```

### F16. 临时产物和旧项目元数据清理

状态：已处理。

处理记录：

- `.gitignore` 覆盖 `tmp/`、DB backup、Python cache/build/test artifacts、Vite/Vitest artifacts。
- `pyproject.toml` 描述更新为当前本地 Agent Runtime 控制台口径。
- 当前工作树未出现指定 DB backup/tmp 误导性产物。
- 验证：建议扫描无输出。

目标：

- `.gitignore` 覆盖 `tmp/`、`*.db.bak-*`、常见 Python/Vite build artifacts。
- 当前工作树不再出现误导性的 DB backup/tmp 产物。
- `pyproject.toml` 描述不再是旧项目模板口径。

建议验证：

```bash
git status --short -- tmp crxzipple.db.bak-20260408113406 crxzipple.db.bak-20260410141011 crxzipple.db.bak-20260410174540 pyproject.toml .gitignore
rg -n 'DDD-oriented Python project skel[e]ton|project skel[e]ton' pyproject.toml README.md docs -g '!docs/archive/**' || true
```

## 推荐处理顺序

1. F7：先让 agent contract、dev stack、migration head 进入版本控制边界，避免后续 agent clean checkout 失真。
2. F1-F3：收 Operations action/refresh/危险确认，防止运维面继续绕过自身契约。
3. F4-F5：补事件 contract 和真分页，让 read model 可长期演进。
4. F6：补 runtime guard 尾巴，统一 SQLite fallback 口径。
5. F8-F12：清 application/Operations/API/i18n 结构债。
6. F13-F16：收 UI 稳定性、文件拆分、文档和工程卫生。
