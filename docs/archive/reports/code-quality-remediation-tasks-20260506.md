# Code Quality Remediation Tasks 2026-05-06

本文档由 [code-quality-audit-20260506.md](code-quality-audit-20260506.md) 转换而来，作为后续 agent 修复任务清单。目标是先收口 P1 架构问题，再处理 P2/P3。

## 执行规则

- 每个 agent 只修改自己声明的 write scope。
- 不回滚用户或其他 agent 的改动。
- 优先修复目标结构，不增加兼容 shim。
- 每个任务完成时必须给出：修改文件、验证命令、剩余风险。

## 执行结果

状态：R1-R15、R6.1、R8.1 已全部完成。

本轮组织的 agent 覆盖：

- R1-R5：P1 架构收口，清理旧观察 worker、补事件契约、SQLite runtime guard、文档口径、Operations API/action 旁路。
- R6-R10：P2 运维面质量收口，详情按需加载、500 JSON envelope、统一 action 契约、projection invalidation、orchestration 展示语义。
- R11-R15：P3 卫生项，合并重复 projection、拆 CLI 测试、Tool 动态 i18n fallback、frontend-v2 bundle split、application -> infrastructure import 收口。

最终聚合验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py tests/unit/test_shared_http.py
PYTHONPATH=src pytest -q tests/unit/test_cli.py tests/unit/test_hidden_runtime_cli.py tests/unit/test_main_cli.py tests/unit/test_serve_cli.py tests/unit/test_file_backed_memory.py tests/unit/test_skills_context.py tests/unit/test_skills_cli.py tests/unit/test_process_repository.py tests/unit/test_artifacts_service.py tests/unit/test_ocr_service.py tests/unit/test_memory_watching.py
cd frontend-v2 && npm run build
rg -n 'orchestration-observation|run-observation|orchestration_observation_runtime_service|orchestration_observation_runtime_event_service' src tests || true
rg -n 'from crxzipple\.modules\..*\.infrastructure|import crxzipple\.modules\..*\.infrastructure' src/crxzipple/modules/*/application || true
rg -n 'requestJson<.*>\(\"/(turns|orchestration|tools|channels|skills|access|daemon|memory)' frontend-v2/src/pages/operations frontend-v2/src/shared || true
```

结果：`67 passed`、`42 passed`，frontend-v2 build 通过且无 chunk warning，三条 `rg` 扫描无输出。

追加整改验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py tests/unit/test_shared_http.py tests/unit/test_ui_http.py tests/unit/test_db_cli.py tests/unit/test_event_relay_cli.py
PYTHONPATH=src pytest -q tests/unit/test_event_relay_cli.py tests/unit/test_tool_cli.py tests/unit/test_daemon_cli.py tests/unit/test_orchestration_cli.py -k 'sqlite or run_rejects_sqlite or process_rejects_sqlite or scheduler_run_accepts_daemon_worker_id'
python -m py_compile src/crxzipple/modules/operations/interfaces/http.py src/crxzipple/modules/operations/application/read_models/tool.py src/crxzipple/modules/event_relay/interfaces/worker_cli.py tests/unit/test_ui_http.py tests/unit/test_event_relay_cli.py
cd frontend-v2 && npm run build
```

结果：`69 passed`、`11 passed, 62 deselected`，py_compile 通过，frontend-v2 build 通过。

剩余风险：

- 当前 Operations HTTP 保持纯 projection 读取；若 observer/projection worker 未运行，接口会继续返回 503，不回退 owner module。
- action audit 已持久化到 `operations_action_audits`，但前端运维面尚未单独展示审计日志列表。

## 追加整改 2026-05-06

### R6.1. Operations detail projection 拆分

状态：已完成。

目标：

- `tool` / `llm` page projection 存储不再携带完整详情数组。
- tool run detail 与 llm invocation detail 独立写入 `operations_projections` detail kind + query_key。
- 详情 endpoint 从独立 detail projection 读取。
- materialize 时清理 stale detail projection。
- Operations HTTP 查询旧测试改为显式物化 projection；`tool_runs` 的 projection 表格补轻量筛选索引，支持 status/provider/artifact/retryable/search 过滤但不恢复完整详情 payload。

### R8.1. Operations action audit 持久化

状态：已完成。

目标：

- Operations action audit payload 落到持久化存储。
- 记录 action、target、reason、risk、confirmation、operator/source/metadata、status/result/error。
- 校验通过后的业务失败也必须记录 failed audit。
- 可提供最小只读查询能力，方便后续运维面展示。

### R3.1. Event relay runtime SQLite guard 补齐

状态：已完成。

目标：

- `event-relay process` / `event-relay run` 与 scheduler、executor、observer、tool worker 保持同一运行库约束。
- 入口统一通过 `load_settings()` 读取配置，拒绝未显式 fallback 的 SQLite runtime database。
- CLI 测试覆盖 `process` 与 `run` 两个入口。

## P1 必修

### R1. 清理旧 `orchestration-observation`

状态：已完成。

Write scope：

- `src/crxzipple/bootstrap/container.py`
- `src/crxzipple/modules/orchestration/interfaces/worker_cli.py`
- `tests/unit/test_daemon_service.py`
- `tests/unit/test_orchestration_cli.py`
- `tests/unit/test_events.py`
- `tests/unit/test_cli.py`
- `tests/unit/test_daemon_manager.py`

目标：

- 删除旧 orchestration observation runtime/builder/CLI 暴露。
- 测试只认可 `worker:operations-observer`。
- 不复活 `worker:orchestration-observation`。

验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_daemon_service.py tests/unit/test_orchestration_cli.py -k observation
PYTHONPATH=src pytest -q tests/unit/test_events.py tests/unit/test_cli.py tests/unit/test_daemon_manager.py
rg -n 'orchestration-observation|run-observation|orchestration_observation_runtime_service' src tests
```

### R2. 补 tool / llm EventDefinition

状态：已完成。

Write scope：

- `src/crxzipple/shared/event_contracts.py`
- `tests/unit/test_events.py`

目标：

- 为 `tool.run.*`、`tool.assignment.*`、`tool.worker.*` 补 EventDefinition。
- 为 `llm.invocation_*`、`llm.profile_*` 补 EventDefinition。
- 增加测试确保 registry 覆盖这些事件。

验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_events.py
rg -n 'tool.run|tool.assignment|tool.worker|llm.invocation|llm.profile' src/crxzipple/shared/event_contracts.py tests/unit/test_events.py
```

### R3. 收口 runtime SQLite guard 与 DB test head

状态：已完成。

Write scope：

- `src/crxzipple/core/config.py`
- `src/crxzipple/interfaces/cli/crxzipple.py`
- `src/crxzipple/modules/daemon/interfaces/cli.py`
- `src/crxzipple/modules/operations/interfaces/worker_cli.py`
- `src/crxzipple/modules/event_relay/interfaces/worker_cli.py`
- `src/crxzipple/modules/tool/interfaces/worker_cli.py`
- `src/crxzipple/modules/tool/interfaces/scheduler_cli.py`
- `src/crxzipple/modules/orchestration/interfaces/worker_cli.py`
- `tests/unit/cli_test_support.py`
- relevant CLI tests

目标：

- 长运行 runtime 入口在未显式 fallback 时拒绝 SQLite。
- `HEAD_REVISION` 更新到当前 migration head `0041_create_operations_action_audits`。

验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_db_cli.py tests/unit/test_config.py
PYTHONPATH=src pytest -q tests/unit/test_daemon_cli.py tests/unit/test_tool_cli.py tests/unit/test_orchestration_cli.py
```

### R4. 修正 active UI 文档与 README/checklist

状态：已完成。

Write scope：

- `README.md`
- `docs/README.md`
- `docs/ui/current-ui-design-functional-spec.md`
- `docs/reports/code-quality-audit-checklist.md`
- `docs/reports/code-quality-audit-20260506.md`
- `docs/reports/code-quality-remediation-tasks-20260506.md`

目标：

- UI 文档不再建议 `/ui/operations/*` 或 owner module Operations provider。
- README 项目简介不再是 skeleton。
- checklist 扫描不误报 `docs/ui/operations/*.png`。
- checklist 报告模板补 line/evidence 字段。
- 审计报告同步标记 P1-5 / P3-4 / P3-5 / P3-6 已由 R4 修正。

验证：

```bash
rg -n 'A DDD-oriented Python project skeleton|owner module 提供模块内 read model provider|后台按 owner module 补 read model provider' README.md docs/ui/current-ui-design-functional-spec.md || true
rg -n "GET /ui/operations|POST /ui/operations|PATCH /ui/operations|DELETE /ui/operations|[\`\"'=]/ui/operations" docs AGENTS.md README.md -g '!docs/reports/**' -g '!docs/ui/operations/*.png' || true
git diff --check -- README.md docs/ui/current-ui-design-functional-spec.md docs/reports
```

### R5. Operations 前端 action/read 旁路收口

状态：已完成。

Write scope：

- `frontend-v2/src/pages/operations/api.ts`
- `frontend-v2/src/pages/operations/modules/*.vue`
- backend Operations action API files if needed

目标：

- Operations 前端不直接拼运维真相。
- Daemon action 传递 reason。
- 仍必须保留必要导航跳转，不把导航链接误判为数据真相读取。

验证：

```bash
cd frontend-v2
npm run typecheck
npm run build
rg -n 'requestJson<.*>\\(\"/(turns|orchestration|tools|channels|skills|access|daemon|memory)' src/pages/operations src/shared || true
```

## P2 后续

### R6. Operations 大详情分页/按需加载

状态：已完成。

目标：

- `/operations/tool?limit=1` 不返回全部 `tool_run_details`。
- `/operations/llm?limit=1` 不返回全部 `invocation_details`。
- 右侧 drawer 按 id 拉详情或读取按 query_key 物化的详情 projection。

### R7. HTTP 500 JSON envelope

状态：已完成。

目标：

- 全局未捕获异常返回 JSON error envelope。
- 前端不会收到 plain text `Internal Server Error`。

### R8. action reason/risk/audit 统一契约

状态：已完成。

目标：

- daemon/browser/mobile/tool 等状态变更 endpoint 接入统一 action request model。
- 危险动作强制 reason/confirmation。

### R9. Operations refresh feed 去 raw event 语义

状态：已完成。

目标：

- 前端只消费 projection/module invalidation。
- 不再根据 raw owner/topic 推断模块。

### R10. Orchestration raw event key 展示本地化

状态：已完成。

目标：

- projection 提供 display label/tone/summary。
- raw key 放 debug/detail，不在主视图裸露。

## P3 卫生项

### R11. 合并重复 `OperationsProjection`

状态：已完成。

目标：

- `OperationsProjection` 只保留一个应用层定义。
- DB projection store 使用同一 projection entity，不再依赖被覆盖的重复 dataclass。

### R12. 拆分 `tests/unit/test_cli.py`

状态：已完成。

目标：

- 顶层 CLI 测试保留 smoke 与入口行为。
- 技能、memory、hidden runtime、serve、main CLI 等模块级行为拆入独立测试文件。

### R13. Tool 页动态 i18n fallback

状态：已完成。

目标：

- Tool 运维页对后端动态 key 使用稳定 fallback，不在主视图裸露缺失 key。
- 动态详情仍保留原始 key 供排障查看。

### R14. frontend-v2 bundle split

状态：已完成。

目标：

- Operations 大模块按页面拆分加载。
- `npm run build` 不再产生原有 chunk 体积 warning。

### R15. application -> infrastructure import 收口

状态：已完成。

目标：

- 应用层不再直接导入本模块 infrastructure 实现。
- 跨模块读取通过 application service / port surface，而不是从 UI 或 application 层拼基础设施细节。
