from __future__ import annotations

import asyncio
import re
import threading
import time
from typing import TYPE_CHECKING
from uuid import uuid4

from crxzipple.interfaces.runtime_container import AppContainer, AppKey

if TYPE_CHECKING:
    from crxzipple.modules.llm.application import LlmAdapterRequest, LlmAdapterResponse


BENCHMARK_RUN_ID_PATTERN = re.compile(
    r"\[benchmark_run[^\]]*\brun_id=(?P<run_id>[^\]\s]+)",
)


class ToolIoBenchmarkStats:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.started_tool_calls = 0
        self.completed_tool_calls = 0
        self.active_tool_calls = 0
        self.max_active_tool_calls = 0
        self.started_llm_invocations = 0
        self.completed_llm_invocations = 0

    def record_llm_started(self) -> None:
        with self._lock:
            self.started_llm_invocations += 1

    def record_llm_completed(self) -> None:
        with self._lock:
            self.completed_llm_invocations += 1

    def record_tool_started(self) -> None:
        with self._lock:
            self.started_tool_calls += 1
            self.active_tool_calls += 1
            self.max_active_tool_calls = max(
                self.max_active_tool_calls,
                self.active_tool_calls,
            )

    def record_tool_completed(self) -> None:
        with self._lock:
            self.completed_tool_calls += 1
            self.active_tool_calls = max(self.active_tool_calls - 1, 0)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "started_tool_calls": self.started_tool_calls,
                "completed_tool_calls": self.completed_tool_calls,
                "active_tool_calls": self.active_tool_calls,
                "max_active_tool_calls": self.max_active_tool_calls,
                "started_llm_invocations": self.started_llm_invocations,
                "completed_llm_invocations": self.completed_llm_invocations,
            }


class SyntheticToolIoLlmAdapter:
    def __init__(
        self,
        *,
        tool_name: str,
        tool_calls_per_run: int,
        tool_sleep_seconds: float,
        llm_latency_seconds: float,
        stats: ToolIoBenchmarkStats,
    ) -> None:
        self.tool_name = tool_name
        self.tool_calls_per_run = max(tool_calls_per_run, 1)
        self.tool_sleep_seconds = max(tool_sleep_seconds, 0.0)
        self.llm_latency_seconds = max(llm_latency_seconds, 0.0)
        self.stats = stats
        self._lock = threading.Lock()
        self._sequence = 0

    def invoke(self, _profile, request: LlmAdapterRequest) -> LlmAdapterResponse:  # noqa: ANN001
        return asyncio.run(self.invoke_async(_profile, request))

    async def invoke_async(
        self,
        _profile,  # noqa: ANN001
        request: LlmAdapterRequest,
    ) -> LlmAdapterResponse:
        from crxzipple.modules.llm.application import LlmAdapterResponse
        from crxzipple.modules.llm.domain import LlmResult, ToolCallIntent

        self.stats.record_llm_started()
        try:
            if self.llm_latency_seconds > 0:
                await asyncio.sleep(self.llm_latency_seconds)
            benchmark_run_id = self._latest_benchmark_run_id(request)
            if self._has_current_tool_result_message(request, benchmark_run_id):
                return LlmAdapterResponse(
                    result=LlmResult(
                        text="synthetic tool io benchmark complete",
                        finish_reason="stop",
                    ),
                )
            with self._lock:
                self._sequence += 1
                sequence = self._sequence
            call_prefix = f"tool-io-{benchmark_run_id or sequence}"
            return LlmAdapterResponse(
                result=LlmResult(
                    tool_calls=tuple(
                        ToolCallIntent(
                            id=f"{call_prefix}-{index + 1}",
                            name=self.tool_name,
                            arguments={
                                "call_index": index + 1,
                                "sleep_seconds": self.tool_sleep_seconds,
                            },
                        )
                        for index in range(self.tool_calls_per_run)
                    ),
                    finish_reason="tool_calls",
                ),
            )
        finally:
            self.stats.record_llm_completed()

    @staticmethod
    def _has_current_tool_result_message(
        request: LlmAdapterRequest,
        benchmark_run_id: str | None,
    ) -> bool:
        expected_prefix = (
            f"tool-io-{benchmark_run_id}-" if benchmark_run_id is not None else None
        )
        for message in request.messages:
            role = getattr(message, "role", None)
            if str(getattr(role, "value", role)) != "tool":
                continue
            if expected_prefix is None:
                return True
            tool_call_id = getattr(message, "tool_call_id", None)
            if isinstance(tool_call_id, str) and tool_call_id.startswith(
                expected_prefix,
            ):
                return True
        return False

    @staticmethod
    def _latest_benchmark_run_id(request: LlmAdapterRequest) -> str | None:
        for message in reversed(request.messages):
            role = getattr(message, "role", None)
            if str(getattr(role, "value", role)) != "user":
                continue
            match = BENCHMARK_RUN_ID_PATTERN.search(
                SyntheticToolIoLlmAdapter._content_text(
                    getattr(message, "content", ""),
                ),
            )
            if match is not None:
                return match.group("run_id")
        return None

    @staticmethod
    def _content_text(content: object) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            return "\n".join(
                SyntheticToolIoLlmAdapter._content_text(value)
                for value in content.values()
            )
        if isinstance(content, (list, tuple)):
            return "\n".join(
                SyntheticToolIoLlmAdapter._content_text(item)
                for item in content
            )
        return str(content)


def ensure_benchmark_agent(
    container: AppContainer,
    *,
    agent_id: str,
    llm_id: str,
) -> None:
    from crxzipple.modules.agent.application import RegisterAgentProfileInput
    from crxzipple.modules.agent.domain import (
        AgentLlmRoutingPolicy,
        AgentNotFoundError,
    )

    agent_service = container.require(AppKey.AGENT_SERVICE)
    try:
        agent_service.get_profile(agent_id)
        return
    except AgentNotFoundError:
        pass
    agent_service.register_profile(
        RegisterAgentProfileInput(
            id=agent_id,
            name=f"Benchmark Tool IO {agent_id}",
            llm_routing_policy=AgentLlmRoutingPolicy(default_llm_id=llm_id),
        ),
    )


def register_tool_io_benchmark_runtime(
    container: AppContainer,
    *,
    agent_id: str,
    tool_calls_per_run: int,
    tool_sleep_seconds: float,
    llm_latency_seconds: float,
) -> tuple[str, str, ToolIoBenchmarkStats]:
    from crxzipple.modules.llm.application import RegisterLlmProfileInput
    from crxzipple.modules.llm.domain import (
        LlmApiFamily,
        LlmCapability,
        LlmModelFamily,
        LlmProviderKind,
    )
    from crxzipple.modules.tool.domain import (
        ToolCatalogSourceKind,
        ToolDefinitionOrigin,
        ToolEnvironment,
        ToolExecutionStrategy,
        ToolExecutionSupport,
        ToolFunction,
        ToolFunctionRuntimeKind,
        ToolFunctionStatus,
        ToolKind,
        ToolMode,
        ToolRunResult,
        ToolSource,
    )

    stats = ToolIoBenchmarkStats()
    synthetic_llm_id = f"benchmark.tool_io.{uuid4().hex[:12]}"
    synthetic_tool_id = f"benchmark_tool_io_sleep_{uuid4().hex[:12]}"
    adapter = SyntheticToolIoLlmAdapter(
        tool_name=synthetic_tool_id,
        tool_calls_per_run=tool_calls_per_run,
        tool_sleep_seconds=tool_sleep_seconds,
        llm_latency_seconds=llm_latency_seconds,
        stats=stats,
    )
    container.require(AppKey.LLM_ADAPTER_REGISTRY).register(
        LlmApiFamily.OLLAMA_NATIVE,
        adapter,
    )
    container.require(AppKey.LLM_SERVICE).register_profile(
        RegisterLlmProfileInput(
            id=synthetic_llm_id,
            provider=LlmProviderKind.OLLAMA,
            api_family=LlmApiFamily.OLLAMA_NATIVE,
            model_name="synthetic-tool-io",
            model_family=LlmModelFamily.GENERAL,
            capabilities=(LlmCapability.TOOL_CALLING,),
            timeout_seconds=30,
        ),
    )
    source_id = f"benchmark.tool_io.{uuid4().hex[:12]}"
    with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
        source = ToolSource(
            id=source_id,
            display_name="Synthetic Tool IO Benchmark",
            kind=ToolCatalogSourceKind.LOCAL_PACKAGE,
            description="Temporary benchmark source for orchestration tool IO tests.",
            config={"namespace": "benchmark.tool_io"},
        )
        function = ToolFunction(
            id=synthetic_tool_id,
            source_id=source_id,
            stable_key=f"{source_id}.{synthetic_tool_id}",
            name=synthetic_tool_id,
            display_name="Synthetic Tool IO Sleep",
            description="Sleeps asynchronously to benchmark inline tool IO concurrency.",
            input_schema={
                "type": "object",
                "properties": {
                    "call_index": {"type": "integer"},
                    "sleep_seconds": {"type": "number"},
                },
            },
            runtime_kind=ToolFunctionRuntimeKind.LOCAL,
            handler_ref={"ref": synthetic_tool_id},
            required_effect_ids=("local_tool_access",),
            execution_support=ToolExecutionSupport(
                supported_modes=(ToolMode.INLINE,),
                supported_strategies=(ToolExecutionStrategy.ASYNC,),
                supported_environments=(ToolEnvironment.LOCAL,),
            ),
            metadata={
                "tool_kind": ToolKind.FUNCTION.value,
                "definition_origin": ToolDefinitionOrigin.LOCAL_DISCOVERY.value,
                "runtime_key": synthetic_tool_id,
                "execution_support": {
                    "supported_modes": (ToolMode.INLINE.value,),
                    "supported_strategies": (ToolExecutionStrategy.ASYNC.value,),
                    "supported_environments": (ToolEnvironment.LOCAL.value,),
                },
            },
            status=ToolFunctionStatus.ACTIVE,
        )
        uow.tool_sources.upsert(source)
        uow.tool_functions.upsert(function)
        uow.commit()
    tool = container.require(AppKey.TOOL_SERVICE).get_tool(
        synthetic_tool_id,
    )

    async def _sleep_tool(arguments: dict[str, object]) -> ToolRunResult:
        stats.record_tool_started()
        started_at = time.perf_counter()
        try:
            sleep_seconds = float(arguments.get("sleep_seconds") or tool_sleep_seconds)
            await asyncio.sleep(max(sleep_seconds, 0.0))
            elapsed_seconds = time.perf_counter() - started_at
            return ToolRunResult.text(
                "synthetic tool io slept",
                details={
                    "call_index": arguments.get("call_index"),
                    "sleep_seconds": sleep_seconds,
                    "elapsed_seconds": round(elapsed_seconds, 6),
                },
            )
        finally:
            stats.record_tool_completed()

    container.require(AppKey.TOOL_LOCAL_RUNTIME_REGISTRY).register(tool, _sleep_tool)
    ensure_benchmark_agent(container, agent_id=agent_id, llm_id=synthetic_llm_id)
    return synthetic_llm_id, synthetic_tool_id, stats
