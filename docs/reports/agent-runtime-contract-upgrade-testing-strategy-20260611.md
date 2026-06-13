# Agent Runtime Contract Upgrade Testing Strategy 2026-06-11

本文记录 LLM request/response contract 升级的测试策略。目标是固定跨模块行为，避免施工时只修单元对象却破坏 agent loop。

关联文档：

- [provider-neutral-llm-response-stream-contract-plan-20260611.md](provider-neutral-llm-response-stream-contract-plan-20260611.md)
- [orchestration-llm-contract-driven-runtime-plan-20260611.md](orchestration-llm-contract-driven-runtime-plan-20260611.md)
- [session-module-response-item-migration-plan-20260611.md](session-module-response-item-migration-plan-20260611.md)
- [context-workspace-llm-request-surface-plan-20260611.md](context-workspace-llm-request-surface-plan-20260611.md)
- [tool-surface-llm-request-contract-plan-20260611.md](tool-surface-llm-request-contract-plan-20260611.md)
- [workbench-agent-timeline-read-model-plan-20260611.md](workbench-agent-timeline-read-model-plan-20260611.md)
- [tests/unit/README.md](../../tests/unit/README.md)

## Cutover Assumption

开发前清库重建，不维护旧数据兼容测试。旧测试如果只验证 `LlmResult.text/tool_calls` 主路径，应改写或删除。

## 测试分层

### LLM module

- response item/event/continuation value object roundtrip。
- OpenAI Responses stream fixture mapping。
- reasoning summary delta/item mapping。
- tool argument delta mapping。
- provider external item mapping。
- derived `LlmResult` summary。

### Orchestration

- request envelope assembly。
- continuation decision。
- `end_turn=false` 不误完成。
- final_answer + no pending work 完成。
- commentary-only 无 follow-up 产生 diagnostic。
- tool_call response item -> ToolExecutionPlan。

### Session

- append SessionItem。
- model-visible replay view。
- tool_call/tool_result call_id continuity。
- commentary 与 final_answer phase 可区分。
- visibility flags 生效。

### Context Workspace

- ContextSurface 包含 Session model-visible facts。
- protocol_required refs 不被预算折叠。
- render snapshot 保存 included/collapsed refs。
- tool schema mirror 引用 ToolSurface id。

### Tool

- ToolSurface source/group/function 结构。
- always-visible tools。
- readiness/authorization filtering。
- ToolResultEnvelope。
- provider external item 不创建 ToolRun。

### Operations / Frontend

- Workbench timeline projection。
- reasoning summary 展示/隐藏 policy。
- tool_call/run/result 分组。
- continuation decision diagnostic。
- 无真实 text 不显示假 progress。

## 跨模块黄金路径

必须覆盖：

```text
user input
  -> request envelope(context + tool surface)
  -> LLM assistant commentary + tool_call
  -> SessionItem commentary/tool_call
  -> ToolRun
  -> ToolResultEnvelope
  -> SessionItem tool_result
  -> next LLM invocation
  -> assistant final_answer
  -> run completed
  -> Workbench timeline
```

## 负向场景

- `end_turn=false` 且无 tool_call。
- provider external item。
- tool_call unknown function。
- tool result missing call_id。
- response item has no session projection。
- context budget tries to collapse protocol-required item。
- provider option unsupported by model capability。

## 推荐命令

### 已跑通矩阵 2026-06-12

```bash
PYTHONPATH=src pytest -q tests/unit/test_llm.py tests/unit/test_llm_adapters.py tests/unit/test_operations_llm_read_model.py
PYTHONPATH=src pytest -q tests/unit/test_session.py tests/unit/test_session_http.py tests/unit/test_session_cli.py tests/unit/test_session_segment_compaction.py
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_http.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_artifact_adapter.py
PYTHONPATH=src pytest -q tests/unit/test_tool_catalog.py tests/unit/test_tool_execution.py tests/unit/test_operations_tool_read_model.py
PYTHONPATH=src pytest -q tests/unit/test_prompt_input_collector.py tests/unit/test_prompt_transcript.py tests/unit/test_orchestration_provider_request_builder.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_context.py tests/unit/test_orchestration_memory.py tests/unit/test_sessions_tool_http.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_approval.py tests/unit/test_orchestration_execution_chain.py tests/unit/test_orchestration_compaction_segment_rotation.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_tools.py tests/unit/test_orchestration_tool_resource_policy.py
PYTHONPATH=src pytest -q tests/unit/test_events.py tests/unit/test_events_http.py tests/unit/test_operations_observation.py
PYTHONPATH=src pytest -q tests/unit/test_db_cli.py tests/unit/test_access_http.py tests/unit/test_auth_http.py
PYTHONPATH=src pytest -q tests/unit/test_agent_http.py tests/unit/test_app_assembly_module_local.py tests/unit/test_authorization.py
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py tests/unit/test_orchestration_context_workspace_snapshot.py
PYTHONPATH=src pytest -q tests/unit/test_ui_http.py
PYTHONPATH=src pytest -q tests/unit/test_llm_http.py tests/unit/test_context_render_xml_renderer.py tests/unit/test_ui_operations_orchestration_http.py
cd frontend && npm run typecheck
cd frontend && npm run build
cd frontend && npm run audit:operations-layout
python -m compileall -q src/crxzipple
```

临时空库 migration smoke 已通过：

```bash
tmp_db="$(mktemp /tmp/crxzipple-migration-smoke-XXXXXX.db)"
rm -f "$tmp_db"
APP_DATABASE_URL="sqlite:///$tmp_db" PYTHONPATH=src python -m crxzipple.main db upgrade head
APP_DATABASE_URL="sqlite:///$tmp_db" PYTHONPATH=src python -m crxzipple.main db current
rm -f "$tmp_db"
```

### 最小施工回归

```bash
PYTHONPATH=src pytest -q tests/unit/test_llm.py tests/unit/test_llm_http.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_prompt_input_collector.py tests/unit/test_orchestration_execution_chain.py
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_render_xml_renderer.py
PYTHONPATH=src pytest -q tests/unit/test_tool_catalog.py tests/unit/test_tool_execution.py
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_read_model.py tests/unit/test_ui_operations_orchestration_http.py
```

## 剩余验收矩阵

- Docker Postgres / Redis 清库重建后 smoke 已通过：`db current` 为 `0076_tool_surface_snapshots (head)`，`daemon status` running，`tool list` 可读取 catalog，`llm list` 可读取 profiles。
- Docker reset 后模块回归已通过：Session 30 passed、Context Workspace 91 passed、Tool/Orchestration 85 passed、Model/Agent/LLM 99 passed、UI/Operations 93 passed、Orchestration/Prompt 106 passed。
- SessionItem context surface 纠偏后回归已通过：Context Workspace/Prompt 104 passed、UI/Operations 95 passed、`git diff --check` passed。
- 真实 LLM smoke 已通过：`openai.gpt-5.4-mini` run `b1f96e59bf6140588c8a8fb6b30aa1e2` completed；snapshot `ctxsnap_d86bd645542a489188d8c9f64e63b4b7` prompt body 已验证包含 `session.items.current` / `session.item.*` / `<item role=...>`，且不包含旧 `session.messages.current` / `session.message.*` / `<message role=...>`。
- 真实长链 agent baseline：至少覆盖一次 `assistant commentary -> tool_call -> tool_result -> follow-up LLM -> final_answer`。
- Workbench 真实运行观察：确认 timeline 中没有假 progress fallback，source refs 可定位 SessionItem / LLM response item / ToolRun / Context snapshot。
- Operations observer 重建：清空 projection 后通过事件侧向重放恢复 LLM、Tool、Orchestration、Workbench 视图。

## 退场测试

删除或改写：

- `tool_calls empty => completed`。
- `session_messages == UI timeline`。
- function_call message 作为 assistant progress。
- Workbench 从 execution summary fallback 生成文案。
- adapter 只断言 `LlmResult.tool_calls`。

## 完成标准

- 所有新 value object roundtrip。
- 黄金路径通过。
- 负向场景有 diagnostic。
- 清库重建后 tests 从空库初始化通过。
- 前端 typecheck/build 通过。
