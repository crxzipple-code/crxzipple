# Runtime Database Reset Playbook 2026-06-11

本文记录 LLM contract / Session / Orchestration / Operations 破坏式升级期间的本地重建流程。目标是让开发者在施工前明确清库重建，不被历史数据兼容牵制。

关联文档：

- [provider-neutral-llm-response-stream-contract-plan-20260611.md](provider-neutral-llm-response-stream-contract-plan-20260611.md)
- [orchestration-llm-contract-driven-runtime-plan-20260611.md](orchestration-llm-contract-driven-runtime-plan-20260611.md)
- [session-module-response-item-migration-plan-20260611.md](session-module-response-item-migration-plan-20260611.md)
- [operations-agent-runtime-projection-plan-20260611.md](operations-agent-runtime-projection-plan-20260611.md)

## 原则

- 开发前允许清除 Postgres / Redis / Operations projection。
- Alembic migration 服务新库初始化，不服务旧数据平滑升级。
- 不写 backfill。
- 不写 dual-read / dual-write。
- reset 后用 smoke tests 验证新链路。

## 推荐流程

```bash
make dev-down
docker compose down -v
make dev-up

source scripts/dev/infra-env.sh
python -m crxzipple.main db upgrade head
python -m crxzipple.main daemon ensure
python -m crxzipple.main daemon status
```

如果项目使用额外本地状态目录，按施工需要清理：

```bash
rm -rf .crxzipple/operations
rm -rf .crxzipple/runtime
```

不要删除用户 workspace 文件或非 CRXZipple 管理的 artifacts。

## Bootstrap 检查

reset 后检查：

```bash
python -m crxzipple.main daemon status
python -m crxzipple.main tool list
python -m crxzipple.main llm profiles
```

如 Settings bootstrap 已经接入，应执行 settings import / validate。

## Smoke Tests

按施工阶段选择：

```bash
PYTHONPATH=src pytest -q tests/unit/test_llm.py tests/unit/test_llm_http.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_prompt_input_collector.py
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py
PYTHONPATH=src pytest -q tests/unit/test_tool_execution.py tests/unit/test_tool_catalog.py
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py tests/unit/test_operations_llm_read_model.py
```

前端：

```bash
cd frontend
npm run typecheck
npm run build
```

## 完成标准

- 新库 migration 可从空库到 head。
- daemon 能启动。
- tool source 能 bootstrap。
- LLM profile 能读取。
- Operations projection 可重建。
- Workbench 能看到新 timeline read model。

## 禁止事项

- 不得为旧数据库写 ad hoc 修复脚本。
- 在 runtime 主路径判断旧/新 schema。
- 不得为旧 projection 写前端兼容 renderer。
- 把 reset playbook 当生产迁移流程。
