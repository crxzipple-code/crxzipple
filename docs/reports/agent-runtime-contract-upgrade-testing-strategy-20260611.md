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

```bash
PYTHONPATH=src pytest -q tests/unit/test_llm.py tests/unit/test_llm_http.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_prompt_input_collector.py tests/unit/test_orchestration_execution_chain.py
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_render_xml_renderer.py
PYTHONPATH=src pytest -q tests/unit/test_tool_catalog.py tests/unit/test_tool_execution.py
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_read_model.py tests/unit/test_ui_operations_orchestration_http.py
```

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
