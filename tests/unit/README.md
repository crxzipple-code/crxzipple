# Unit Test Layout

`tests/unit` follows a module-first layout.

## Rules

- Keep different modules in different files.
- Keep transport-specific tests in transport-specific files:
  - `test_<module>_cli.py`
  - `test_<module>_http.py`
- Keep domain or service tests in `test_<module>.py` when they are not tied to one interface.
- Extract shared setup, fakes, and adapters into `<module>_test_support.py` once a test file starts carrying reusable scaffolding.
- Support files are helpers only. They must not define collected tests.

## Root Surface Files

`test_cli.py` and `test_http.py` are reserved for top-level entrypoint smoke coverage.

- Do not add module-specific CLI tests back into `test_cli.py`.
- Do not add module-specific HTTP tests back into `test_http.py`.

## Split Triggers

Split a file when one of these becomes true:

- The file mixes unrelated modules.
- The file contains multiple transport surfaces for the same module.
- The file grows enough that shared setup dominates the file.
- A reusable fake/adapter/helper appears that another test file would want.

## Current Pattern

- Shared transport scaffolding:
  - `cli_test_support.py`
  - `http_test_support.py`
- Module support files:
  - `orchestration_test_support.py`
  - `tool_test_support.py`
  - `skill_test_support.py`

## Context Workspace Coverage

树化 Prompt / Context Workspace 的单元测试按边界拆开：

- `test_context_workspace_domain.py`：Context Workspace domain value/entity 行为。
- `test_context_workspace_tree_service.py`：workspace/tree/render service、节点状态、snapshot 和 list_recent。
- `test_context_workspace_http.py`：`/context-workspaces/*` HTTP API。
- `test_context_workspace_*_adapter.py`：app integration owner adapters，把 session / memory / tool / skill / artifact / workspace facts 映射为 Context Workspace nodes。
- `test_context_tree_tool.py`：agent-facing `context_tree.*` tools，只验证工具通过 application service 操作树。
- `test_orchestration_context_workspace_snapshot.py`：orchestration 调用 Context Workspace snapshot，并把 `<context_tree>` 与 provider mirror 放入真实 LLM runtime request surface。
- `test_operations_context_workspace_read_model.py`：Operations `context_workspace` read model/projection。

这些测试不应真实调用 LLM，也不应启动 daemon worker。跨进程 Redis、完整 scheduler/executor 运行和浏览器截图属于 runtime/integration 层。

## Agent Loop Governance Coverage

Codex-like loop governance 的单元覆盖分布在几个边界，不放进单一聚合测试文件：

- `test_tool_workspace.py` / `test_tool_catalog.py`：command source schema、`exec.max_output_tokens`、`exec.yield_time_ms`、structured command result、background process handoff。
- `test_context_workspace_session_adapter.py`：tool result history hygiene、历史工具结果摘要、orphan tool result 压缩、长工具链 prompt budget。
- `test_context_workspace_tool_adapter.py`：source prompt group 默认 schema policy、command/web source-local guidance、provider mirror schema 可见性。
- `test_context_workspace_root_nodes.py` / `test_context_workspace_tree_service.py`：global runtime contract 保持能力中立，不回流 Browser/CDP/Playwright/source-specific 路线。
- `test_runtime_transcript.py` / `test_runtime_llm_request_draft_collector.py`：runtime replay window 与 tool result stats。
- `test_orchestration_loop_regression_baseline.py` / `test_orchestration_cli.py`：Phase 7 baseline 指标提取和 `orchestration baseline` CLI smoke。
- `test_orchestration_tool_resource_policy.py` / `test_operations_observation.py` / `test_events.py`：repeated probe observation 和 Operations/Trace 可见性。

Useful focused command:

```bash
PYTHONPATH=src pytest -q tests/unit/test_tool_workspace.py tests/unit/test_tool_catalog.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_context_workspace_root_nodes.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py tests/unit/test_context_render_xml_renderer.py tests/unit/test_runtime_transcript.py tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_tool_resource_policy.py tests/unit/test_orchestration_loop_regression_baseline.py tests/unit/test_tool_execution.py
```

## Runtime Markers

Markers are assigned centrally in `tests/conftest.py`.

- `fast`: module-local tests that avoid full HTTP/CLI/runtime assembly.
- `runtime`: tests that assemble the runtime container, HTTP app, CLI app, worker loop, or daemon surface.
- `benchmark`: CLI benchmark command coverage; these tests must not run real multi-worker SQLite benchmarks.
- `integration` / `live`: external browser/service smoke tests under `tests/integration`.

Useful commands:

```bash
make test-unit-fast
make test-unit-runtime
make test-unit

PYTHONPATH=src pytest -q tests/unit -m fast
PYTHONPATH=src pytest -q tests/unit -m runtime
PYTHONPATH=src pytest -q -o faulthandler_timeout=120 tests/unit --durations=120 --durations-min=0.2
PYTHONPATH=src pytest --collect-only -q tests -m live
```

Do not move slow live/browser/benchmark behavior into unmarked unit tests. If a test only verifies CLI or HTTP wiring, fake the module port instead of launching real worker loops.

`CliModuleTestCase` injects a shared runtime container for commands invoked with the test's default `self.env`. This keeps multi-command CLI scenarios from rebuilding the whole app for every subcommand while preserving Typer parsing and output coverage. Use a custom env or explicit `obj` when a test must verify fresh settings loading or a custom container.

`tests/conftest.py` deliberately forces unit tests onto the file events backend and clears Redis event env vars. Do not remove that isolation to make local dev-stack behavior convenient; cross-process Redis coverage belongs in integration/runtime tests.

## Anti-Patterns

- Reintroducing deleted aggregator files like `test_tool.py` or `test_orchestration.py`
- Mixing CLI and HTTP coverage for the same module into one file
- Hiding large shared fixtures inside the top of a test file instead of moving them into support
