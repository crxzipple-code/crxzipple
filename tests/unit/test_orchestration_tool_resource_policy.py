from __future__ import annotations

import asyncio

from crxzipple.modules.llm.domain import ToolCallIntent, ToolSchema
from crxzipple.modules.orchestration.application.engine_tool_executor import (
    OrchestrationEngineToolExecutor,
)
from crxzipple.modules.orchestration.application.engine_session_recorder import (
    SessionProtocolRecord,
)
from crxzipple.modules.orchestration.application.tool_resolver import (
    ResolvedTool,
    ResolvedToolSet,
    ToolExecutionDecision,
)
from crxzipple.modules.orchestration.domain import InboundInstruction, OrchestrationRun
from crxzipple.modules.tool.application import ExecuteToolInput
from crxzipple.modules.tool.domain import (
    Tool,
    ToolExecutionPolicy,
    ToolExecutionTarget,
    ToolRun,
    ToolRunResult,
)


class _FakeSessionRecorder:
    def __init__(self) -> None:
        self.tool_call_batches: list[tuple[ToolCallIntent, ...]] = []
        self.tool_result_batches: list[tuple[tuple[ToolCallIntent, ToolRun, str, str], ...]] = []

    def append_tool_call_messages(self, **_kwargs: object) -> tuple[str, ...]:
        return self.append_tool_call_records(**_kwargs).message_ids

    def append_tool_call_records(self, **_kwargs: object) -> SessionProtocolRecord:
        tool_calls = tuple(_kwargs.get("tool_calls") or ())
        self.tool_call_batches.append(tool_calls)
        append_session_items = bool(_kwargs.get("append_session_items"))
        return SessionProtocolRecord(
            message_ids=tuple(
                f"tool-call-message-{tool_call.id}" for tool_call in tool_calls
            ),
            item_ids=(
                tuple(f"tool-call-item-{tool_call.id}" for tool_call in tool_calls)
                if append_session_items
                else ()
            ),
        )

    def append_tool_result_messages(self, **kwargs: object) -> tuple[str, ...]:
        return self.append_tool_result_records(**kwargs).message_ids

    def append_tool_result_records(self, **kwargs: object) -> SessionProtocolRecord:
        items = tuple(kwargs.get("items") or ())
        self.tool_result_batches.append(items)
        return SessionProtocolRecord(
            message_ids=tuple(
                f"tool-result-message-{index + 1}" for index, _ in enumerate(items)
            ),
            item_ids=tuple(
                f"tool-result-item-{index + 1}" for index, _ in enumerate(items)
            ),
        )


class _AllowingToolResolver:
    def __init__(self, *, context_attrs: dict[str, object] | None = None) -> None:
        self.context_attrs = dict(context_attrs or {})

    def invocation_context_attrs(
        self,
        _run: OrchestrationRun,
        *,
        session_key: str | None = None,
    ) -> dict[str, object]:
        attrs = dict(self.context_attrs)
        if session_key:
            attrs["session_key"] = session_key
        return attrs

    def resource_attrs(
        self,
        _tool: Tool,
        *,
        target: ToolExecutionTarget,
    ) -> dict[str, object]:
        return {
            "mode": target.mode.value,
            "strategy": target.strategy.value,
            "environment": target.environment.value,
        }

    def execution_decision(self, *_args: object, **_kwargs: object) -> ToolExecutionDecision:
        return ToolExecutionDecision(mode="allow")


class _RecordingToolExecutionPort:
    def __init__(
        self,
        *,
        result_metadata_by_tool_id: dict[str, dict[str, object]] | None = None,
    ) -> None:
        self.batches: list[tuple[ExecuteToolInput, ...]] = []
        self._counter = 0
        self.result_metadata_by_tool_id = dict(result_metadata_by_tool_id or {})

    async def execute(self, data: ExecuteToolInput) -> ToolRun:
        return (await self.execute_many((data,)))[0]

    async def execute_many(
        self,
        items: tuple[ExecuteToolInput, ...],
    ) -> tuple[ToolRun, ...]:
        self.batches.append(items)
        runs: list[ToolRun] = []
        for item in items:
            self._counter += 1
            target = ToolExecutionTarget(
                mode=item.mode,
                strategy=item.strategy,
                environment=item.environment,
            )
            tool_run = ToolRun.create(
                run_id=f"tool-run-{self._counter}",
                tool_id=item.tool_id,
                input_payload=dict(item.arguments),
                metadata=dict(item.metadata),
                target=target,
            )
            tool_run.succeed(
                ToolRunResult.text(
                    "ok",
                    metadata=dict(self.result_metadata_by_tool_id.get(item.tool_id) or {}),
                ),
            )
            runs.append(tool_run)
        return tuple(runs)

    def get_tool_run(self, run_id: str) -> ToolRun:
        raise AssertionError(f"unexpected get_tool_run({run_id})")

    def cancel_tool_run(self, run_id: str) -> ToolRun:
        raise AssertionError(f"unexpected cancel_tool_run({run_id})")


def test_mutating_browser_tool_calls_same_target_are_submitted_serially() -> None:
    executor, execution_port, resolved_tools = _executor_for_tool(
        tool_id="browser.click",
        execution_policy=ToolExecutionPolicy(
            mutates_state=True,
            supports_parallel=False,
            resource_scope="browser.target",
            serial_group_key="browser.target",
        ),
    )

    outcome = asyncio.run(
        executor.execute_tool_calls_async(
            _run(),
            session_key="agent:assistant:main",
            active_session_id="session-1",
            resolved_tools=resolved_tools,
            tool_calls=(
                ToolCallIntent(
                    id="call-click-1",
                    name="browser.click",
                    arguments={"profile": "crxzipple", "target_id": "page-1"},
                ),
                ToolCallIntent(
                    id="call-click-2",
                    name="browser.click",
                    arguments={"profile": "crxzipple", "target_id": "page-1"},
                ),
            ),
            append_tool_call_messages=False,
            append_tool_result_messages=False,
        ),
    )

    assert len(outcome.inline_runs) == 2
    assert [len(batch) for batch in execution_port.batches] == [1, 1]
    first_policy = execution_port.batches[0][0].metadata["tool_resource_policy"]
    assert first_policy == {
        "supports_parallel": False,
        "mutates_state": True,
        "execution_lane": "serial",
        "resource_scope": "browser.target",
        "resource_key": "browser.target:profile=crxzipple;target=page-1",
        "serial_group_key": "browser.target",
    }


def test_read_only_browser_tool_calls_same_target_can_share_execution_batch() -> None:
    executor, execution_port, resolved_tools = _executor_for_tool(
        tool_id="browser.snapshot",
        execution_policy=ToolExecutionPolicy(
            mutates_state=False,
            supports_parallel=True,
            resource_scope="browser.target",
        ),
    )

    asyncio.run(
        executor.execute_tool_calls_async(
            _run(),
            session_key="agent:assistant:main",
            active_session_id="session-1",
            resolved_tools=resolved_tools,
            tool_calls=(
                ToolCallIntent(
                    id="call-snapshot-1",
                    name="browser.snapshot",
                    arguments={"profile": "crxzipple", "target_id": "page-1"},
                ),
                ToolCallIntent(
                    id="call-snapshot-2",
                    name="browser.snapshot",
                    arguments={"profile": "crxzipple", "target_id": "page-1"},
                ),
            ),
            append_tool_call_messages=False,
            append_tool_result_messages=False,
        ),
    )

    assert [len(batch) for batch in execution_port.batches] == [2]
    policies = [
        item.metadata["tool_resource_policy"]
        for item in execution_port.batches[0]
    ]
    assert all(policy["execution_lane"] == "parallel" for policy in policies)
    assert all(policy["resource_scope"] == "browser.target" for policy in policies)


def test_repeated_probe_observation_is_recorded_in_run_metadata() -> None:
    executor, _execution_port, resolved_tools = _executor_for_tool(
        tool_id="web.fetch_text",
        execution_policy=ToolExecutionPolicy(
            mutates_state=False,
            supports_parallel=True,
        ),
    )
    run = _run()

    outcome = asyncio.run(
        executor.execute_tool_calls_async(
            run,
            session_key="agent:assistant:main",
            active_session_id="session-1",
            resolved_tools=resolved_tools,
            tool_calls=(
                ToolCallIntent(
                    id="call-fetch-1",
                    name="web.fetch_text",
                    arguments={"url": "https://www.ceair.com/booking/04ffa1f.js?v=1"},
                ),
                ToolCallIntent(
                    id="call-fetch-2",
                    name="web.fetch_text",
                    arguments={"url": "https://www.ceair.com/booking/04ffa1f.js?v=2"},
                ),
                ToolCallIntent(
                    id="call-fetch-3",
                    name="web.fetch_text",
                    arguments={"url": "https://www.ceair.com/booking/04ffa1f.js?v=3"},
                ),
            ),
            append_tool_call_messages=False,
            append_tool_result_messages=False,
        ),
    )

    assert len(outcome.inline_runs) == 3
    observation = run.metadata["repeated_probe_observation"]
    assert isinstance(observation, dict)
    assert observation["repeated_count"] == 1
    repeated = observation["repeated"]
    assert isinstance(repeated, list)
    assert repeated[0]["count"] == 3
    assert repeated[0]["tool_id"] == "web.fetch_text"
    assert repeated[0]["domain"] == "www.ceair.com"
    assert repeated[0]["path"] == "/booking/04ffa1f.js"
    assert repeated[0]["first_seen_step"] == 1
    assert repeated[0]["last_seen_step"] == 3


def test_repeated_command_probe_observation_is_recorded_in_run_metadata() -> None:
    executor, _execution_port, resolved_tools = _executor_for_tool(
        tool_id="exec",
        execution_policy=ToolExecutionPolicy(
            mutates_state=True,
            supports_parallel=False,
        ),
    )
    run = _run()

    asyncio.run(
        executor.execute_tool_calls_async(
            run,
            session_key="agent:assistant:main",
            active_session_id="session-1",
            resolved_tools=resolved_tools,
            tool_calls=(
                ToolCallIntent(
                    id="call-exec-1",
                    name="exec",
                    arguments={"command": "python fetch_js.py"},
                ),
                ToolCallIntent(
                    id="call-exec-2",
                    name="exec",
                    arguments={"command": "python   fetch_js.py"},
                ),
                ToolCallIntent(
                    id="call-exec-3",
                    name="exec",
                    arguments={"command": "python fetch_js.py"},
                ),
            ),
            append_tool_call_messages=False,
            append_tool_result_messages=False,
        ),
    )

    observation = run.metadata["repeated_probe_observation"]
    assert isinstance(observation, dict)
    repeated = observation["repeated"]
    assert isinstance(repeated, list)
    assert repeated[0]["count"] == 3
    assert repeated[0]["kind"] == "command"
    assert repeated[0]["tool_id"] == "exec"
    assert "command_fingerprint" in repeated[0]


def test_unspecified_browser_profile_uses_wildcard_resource_key() -> None:
    executor, execution_port, resolved_tools = _executor_for_tool(
        tool_id="browser.click",
        execution_policy=ToolExecutionPolicy(
            mutates_state=True,
            supports_parallel=False,
            resource_scope="browser.target",
            serial_group_key="browser.target",
        ),
    )

    asyncio.run(
        executor.execute_tool_calls_async(
            _run(),
            session_key="agent:assistant:main",
            active_session_id="session-1",
            resolved_tools=resolved_tools,
            tool_calls=(
                ToolCallIntent(
                    id="call-click-1",
                    name="browser.click",
                    arguments={"target_id": "page-1"},
                ),
                ToolCallIntent(
                    id="call-click-2",
                    name="browser.click",
                    arguments={"profile": "crxzipple", "target_id": "page-1"},
                ),
            ),
            append_tool_call_messages=False,
            append_tool_result_messages=False,
        ),
    )

    assert [len(batch) for batch in execution_port.batches] == [1, 1]
    first_policy = execution_port.batches[0][0].metadata["tool_resource_policy"]
    assert first_policy["resource_key"] == "browser.target:profile=*;target=page-1"


def test_terminal_context_tree_plan_stops_remaining_tool_batch() -> None:
    recorder = _FakeSessionRecorder()
    execution_port = _RecordingToolExecutionPort(
        result_metadata_by_tool_id={
            "context_tree.update_plan": {
                "tool": "context_tree.update_plan",
                "terminal_plan": True,
            },
        },
    )
    executor = OrchestrationEngineToolExecutor(
        session_recorder=recorder,
        tool_resolver=_AllowingToolResolver(),
        tool_execution_port=execution_port,
    )
    resolved_tools = ResolvedToolSet(
        tools=(
            _resolved_tool(
                "context_tree.update_plan",
                execution_policy=ToolExecutionPolicy(
                    mutates_state=True,
                    supports_parallel=True,
                ),
            ),
            _resolved_tool(
                "browser.runtime.call_client",
                execution_policy=ToolExecutionPolicy(
                    mutates_state=False,
                    supports_parallel=True,
                ),
            ),
        ),
    )

    outcome = asyncio.run(
        executor.execute_tool_calls_async(
            _run(),
            session_key="agent:assistant:main",
            active_session_id="session-1",
            resolved_tools=resolved_tools,
            tool_calls=(
                ToolCallIntent(
                    id="call-plan-done",
                    name="context_tree.update_plan",
                    arguments={"objective": "finish", "status": "done"},
                ),
                ToolCallIntent(
                    id="call-browser-extra",
                    name="browser.runtime.call_client",
                    arguments={"target_id": "page-1"},
                ),
            ),
            append_tool_call_messages=True,
            append_tool_call_session_items=True,
            append_tool_result_messages=True,
        ),
    )

    assert outcome.yield_requested is False
    assert outcome.yield_reason is None
    assert len(outcome.inline_runs) == 1
    assert len(outcome.tool_call_session_item_ids) == 1
    assert [item.tool_id for item in execution_port.batches[0]] == [
        "context_tree.update_plan",
    ]
    assert len(execution_port.batches) == 1
    assert [
        tool_call.id for batch in recorder.tool_call_batches for tool_call in batch
    ] == ["call-plan-done"]


def test_cancelled_run_does_not_dispatch_tool_calls() -> None:
    executor, execution_port, resolved_tools = _executor_for_tool(
        tool_id="web.fetch_text",
        execution_policy=ToolExecutionPolicy(),
    )
    run = _run()
    run.cancel(reason="stopped from workbench")

    outcome = asyncio.run(
        executor.execute_tool_calls_async(
            run,
            session_key="agent:assistant:main",
            active_session_id="session-1",
            resolved_tools=resolved_tools,
            tool_calls=(
                ToolCallIntent(
                    id="call-fetch",
                    name="web.fetch_text",
                    arguments={"url": "https://example.com"},
                ),
            ),
            append_tool_call_messages=True,
            append_tool_result_messages=True,
        ),
    )

    assert outcome.tool_call_session_item_ids == ()
    assert outcome.inline_runs == ()
    assert execution_port.batches == []


def test_stale_running_run_rechecks_dispatch_guard_before_tool_creation() -> None:
    recorder = _FakeSessionRecorder()
    execution_port = _RecordingToolExecutionPort()
    executor = OrchestrationEngineToolExecutor(
        session_recorder=recorder,
        tool_resolver=_AllowingToolResolver(),
        tool_execution_port=execution_port,
        run_dispatch_guard=lambda _run: False,
    )
    resolved_tools = ResolvedToolSet(
        tools=(
            _resolved_tool(
                "web.fetch_text",
                execution_policy=ToolExecutionPolicy(),
            ),
        ),
    )

    outcome = asyncio.run(
        executor.execute_tool_calls_async(
            _run(),
            session_key="agent:assistant:main",
            active_session_id="session-1",
            resolved_tools=resolved_tools,
            tool_calls=(
                ToolCallIntent(
                    id="call-fetch",
                    name="web.fetch_text",
                    arguments={"url": "https://example.com"},
                ),
            ),
            append_tool_call_messages=True,
            append_tool_result_messages=True,
        ),
    )

    assert outcome.tool_call_session_item_ids == ()
    assert outcome.inline_runs == ()
    assert recorder.tool_call_batches == []
    assert execution_port.batches == []


def _executor_for_tool(
    *,
    tool_id: str,
    execution_policy: ToolExecutionPolicy,
) -> tuple[OrchestrationEngineToolExecutor, _RecordingToolExecutionPort, ResolvedToolSet]:
    tool = Tool(
        id=tool_id,
        name=tool_id,
        description=f"{tool_id} test tool",
        execution_policy=execution_policy,
    )
    execution_port = _RecordingToolExecutionPort()
    return (
        OrchestrationEngineToolExecutor(
            session_recorder=_FakeSessionRecorder(),
            tool_resolver=_AllowingToolResolver(),
            tool_execution_port=execution_port,
        ),
        execution_port,
        ResolvedToolSet(
            tools=(
                ResolvedTool(
                    tool=tool,
                    schema=ToolSchema(name=tool_id, description=tool.description),
                    target=ToolExecutionTarget(),
                ),
            ),
        ),
    )


def _resolved_tool(
    tool_id: str,
    *,
    execution_policy: ToolExecutionPolicy,
) -> ResolvedTool:
    tool = Tool(
        id=tool_id,
        name=tool_id,
        description=f"{tool_id} test tool",
        execution_policy=execution_policy,
    )
    return ResolvedTool(
        tool=tool,
        schema=ToolSchema(name=tool_id, description=tool.description),
        target=ToolExecutionTarget(),
    )


def _run() -> OrchestrationRun:
    run = OrchestrationRun.accept(
        run_id="run-tool-resource-policy",
        inbound_instruction=InboundInstruction(source="cli", content="use tools"),
        metadata={"session_key": "agent:assistant:main"},
    )
    run.route(agent_id="assistant")
    run.bind_session(active_session_id="session-1")
    run.claim(worker_id="worker-1")
    return run
