from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import timedelta
import time
import unittest

from crxzipple.core.config import load_settings
from crxzipple.modules.agent.application import RegisterAgentProfileInput
from crxzipple.modules.dispatch.application import (
    CreateDispatchTaskInput,
    EnqueueDispatchTaskInput,
    RecoverAbandonedDispatchTasksInput,
)
from crxzipple.modules.agent.domain import AgentInstructionPolicy, AgentLlmRoutingPolicy
from crxzipple.modules.dispatch.domain import DispatchPolicy, DispatchTaskStatus
from crxzipple.modules.llm.application import RegisterLlmProfileInput
from crxzipple.modules.llm.application.adapters import (
    LlmAdapterRequest,
    LlmAdapterResponse,
)
from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmMessageRole,
    LlmProviderKind,
    LlmResult,
    ToolCallIntent,
)
from crxzipple.modules.orchestration.application import (
    AcceptOrchestrationRunInput,
    AdvanceOrchestrationRunInput,
    CompleteOrchestrationRunInput,
    EnqueueOrchestrationRunInput,
    FailOrchestrationRunInput,
    PrepareSessionRunInput,
    ResumeOrchestrationRunInput,
    ResolveSessionBundleInput,
    RouteOrchestrationRunInput,
    WaitOnToolInput,
)
from crxzipple.modules.orchestration.domain import (
    DeliveryTarget,
    InboundInstruction,
    OrchestrationQueuePolicy,
    OrchestrationRunStage,
    OrchestrationRunStatus,
)
from crxzipple.modules.session.application import ListSessionMessagesInput
from crxzipple.modules.session.domain import DirectSessionScope, SessionRouteContext
from crxzipple.modules.tool.application import ExecuteToolInput, RegisterToolInput
from crxzipple.modules.tool.domain import ToolMode, ToolRunStatus
from tests.unit.support import SqliteTestHarness


class _StaticTextAdapter:
    def __init__(self, *, text: str) -> None:
        self.text = text
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        return LlmAdapterResponse(result=LlmResult(text=self.text))


class _ToolCallAdapter:
    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        return LlmAdapterResponse(
            result=LlmResult(
                text="calling tool",
                tool_calls=(
                    ToolCallIntent(
                        id="call-1",
                        name="search_docs",
                        arguments={"query": "ddd"},
                    ),
                ),
            ),
        )


class _InlineToolLoopAdapter:
    def __init__(self) -> None:
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        tool_messages = [
            message
            for message in request.messages
            if message.role is LlmMessageRole.TOOL
        ]
        if not tool_messages:
            return LlmAdapterResponse(
                result=LlmResult(
                    tool_calls=(
                        ToolCallIntent(
                            id="call-echo-1",
                            name="echo",
                            arguments={"message": "hello from tool"},
                        ),
                    ),
                ),
            )
        return LlmAdapterResponse(result=LlmResult(text="tool loop complete"))


class _BackgroundToolAdapter:
    def __init__(self) -> None:
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        return LlmAdapterResponse(
            result=LlmResult(
                tool_calls=(
                    ToolCallIntent(
                        id="call-bg-1",
                        name="background_echo",
                        arguments={"message": "background hello"},
                    ),
                ),
            ),
        )


class _BackgroundResumeAdapter:
    def __init__(self) -> None:
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        tool_messages = [
            message
            for message in request.messages
            if message.role is LlmMessageRole.TOOL
        ]
        if not tool_messages:
            return LlmAdapterResponse(
                result=LlmResult(
                    tool_calls=(
                        ToolCallIntent(
                            id="call-bg-1",
                            name="background_echo",
                            arguments={"message": "background hello"},
                        ),
                    ),
                ),
            )
        return LlmAdapterResponse(result=LlmResult(text="background loop complete"))


class _FailingAdapter:
    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        del request
        raise RuntimeError("sample adapter failure")


class _SlowStaticTextAdapter:
    def __init__(self, *, text: str, delay_seconds: float) -> None:
        self.text = text
        self.delay_seconds = delay_seconds
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        time.sleep(self.delay_seconds)
        return LlmAdapterResponse(result=LlmResult(text=self.text))


class OrchestrationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = SqliteTestHarness()
        self.harness.initialize_schema()
        self.container = self.harness.build_container()

    def tearDown(self) -> None:
        self.harness.close()

    def _register_agent_and_llm(self, *, llm_id: str = "openai.gpt-5.4-mini") -> None:
        self.container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id=llm_id,
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
            ),
        )
        self.container.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="assistant",
                name="Assistant",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Be helpful and concise.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(default_llm_id=llm_id),
            ),
        )

    def test_accept_prepare_session_queue_and_claim_run(self) -> None:
        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-1",
                inbound_instruction=InboundInstruction(
                    source="http",
                    content="Summarize this",
                    metadata={"request_id": "req-1"},
                ),
                delivery_target=DeliveryTarget(
                    interface_name="http",
                    address="request:req-1",
                ),
                priority=20,
                max_steps=6,
            ),
        )

        self.assertEqual(run.status, OrchestrationRunStatus.ACCEPTED)
        self.assertEqual(run.stage, OrchestrationRunStage.ACCEPTED)

        prepared = self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="writer",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    label="browser",
                    surface="chat",
                    direct_scope=DirectSessionScope.MAIN,
                    metadata={"request_id": "req-1"},
                ),
                priority=10,
            ),
        )
        queued = self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )
        claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )

        self.assertEqual(prepared.stage, OrchestrationRunStage.BULK_READY)
        self.assertEqual(queued.status, OrchestrationRunStatus.QUEUED)
        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.id, run.id)
        self.assertEqual(claimed.status, OrchestrationRunStatus.RUNNING)
        self.assertEqual(claimed.stage, OrchestrationRunStage.RUNNING)
        self.assertEqual(claimed.worker_id, "worker-1")
        self.assertEqual(claimed.bulk_key, "conversation:main:webchat:default:main")
        self.assertTrue(claimed.active_session_id)
        self.assertIsNotNone(claimed.started_at)
        self.assertEqual(claimed.metadata["session_key"], "agent:writer:main")
        self.assertEqual(claimed.metadata["session_kind"], "main")
        dispatch_task = self.container.dispatch_service.get_task(run.id)
        self.assertEqual(dispatch_task.status, DispatchTaskStatus.CLAIMED)
        self.assertEqual(dispatch_task.policy, DispatchPolicy.FIFO)
        self.assertEqual(dispatch_task.claimed_by, "worker-1")
        self.assertIsNotNone(dispatch_task.lease_expires_at)
        self.assertEqual(
            dispatch_task.lane_key,
            "bulk:conversation:main:webchat:default:main",
        )

        with self.container.uow_factory() as uow:
            persisted = uow.orchestration_runs.get(run.id)

        self.assertIsNotNone(persisted)
        assert persisted is not None
        self.assertEqual(persisted.status, OrchestrationRunStatus.RUNNING)
        self.assertEqual(persisted.stage, OrchestrationRunStage.RUNNING)
        self.assertEqual(persisted.worker_id, "worker-1")
        self.assertEqual(persisted.bulk_key, "conversation:main:webchat:default:main")

        event_names = [
            event.name
            for event in self.container.event_bus.published_events
            if event.name.startswith("orchestration.run.")
        ][-5:]
        self.assertEqual(
            event_names,
            [
                "orchestration.run.accepted",
                "orchestration.run.routed",
                "orchestration.run.bulk_ready",
                "orchestration.run.queued",
                "orchestration.run.claimed",
            ],
        )

    def test_claim_next_queued_run_prefers_lower_priority(self) -> None:
        low_priority = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-low",
                inbound_instruction=InboundInstruction(source="cli", content="first"),
                priority=50,
            ),
        )
        high_priority = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-high",
                inbound_instruction=InboundInstruction(source="cli", content="second"),
                priority=5,
            ),
        )

        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=low_priority.id,
                agent_id="writer",
                bulk_key="conversation:one",
                lane_key="bulk:conversation:one",
            ),
        )
        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=high_priority.id,
                agent_id="writer",
                bulk_key="conversation:two",
                lane_key="bulk:conversation:two",
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=low_priority.id),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=high_priority.id),
        )

        claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.id, high_priority.id)

    def test_claim_next_queued_run_skips_blocked_lane(self) -> None:
        active = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-active",
                inbound_instruction=InboundInstruction(source="cli", content="active"),
                priority=50,
            ),
        )

        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=active.id,
                agent_id="writer",
                bulk_key="conversation:lane-a",
                lane_key="bulk:conversation:lane-a",
            ),
        )

        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=active.id),
        )
        first = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )

        blocked = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-blocked",
                inbound_instruction=InboundInstruction(source="cli", content="blocked"),
                priority=1,
            ),
        )
        available = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-available",
                inbound_instruction=InboundInstruction(source="cli", content="available"),
                priority=10,
            ),
        )

        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=blocked.id,
                agent_id="writer",
                bulk_key="conversation:lane-a",
                lane_key="bulk:conversation:lane-a",
            ),
        )
        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=available.id,
                agent_id="writer",
                bulk_key="conversation:lane-b",
                lane_key="bulk:conversation:lane-b",
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=blocked.id),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=available.id),
        )

        second = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-2",
        )

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        assert first is not None
        assert second is not None
        self.assertEqual(first.id, active.id)
        self.assertEqual(second.id, available.id)

    def test_claim_next_queued_run_blocks_lane_while_waiting(self) -> None:
        waiting = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-waiting",
                inbound_instruction=InboundInstruction(source="cli", content="waiting"),
                priority=5,
            ),
        )

        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=waiting.id,
                agent_id="writer",
                bulk_key="conversation:lane-wait",
                lane_key="bulk:conversation:lane-wait",
            ),
        )

        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=waiting.id),
        )

        claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )
        assert claimed is not None
        self.container.orchestration_service.wait_on_tool(
            WaitOnToolInput(
                run_id=waiting.id,
                worker_id="worker-1",
                pending_tool_run_ids=("tool-run-1",),
                reason="tool_background_wait",
            ),
        )

        queued = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-same-lane",
                inbound_instruction=InboundInstruction(source="cli", content="queued"),
                priority=1,
            ),
        )
        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=queued.id,
                agent_id="writer",
                bulk_key="conversation:lane-wait",
                lane_key="bulk:conversation:lane-wait",
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=queued.id),
        )

        blocked = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-2",
        )

        self.assertIsNone(blocked)

    def test_claim_next_queued_run_ignores_foreign_dispatch_owner_kind(self) -> None:
        self._register_agent_and_llm()

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-owner-filter",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
                priority=50,
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        foreign_task = self.container.dispatch_service.create_task(
            CreateDispatchTaskInput(
                task_id="foreign-tool-task",
                owner_kind="tool_run",
                owner_id="tool-run-1",
                priority=1,
            ),
        )
        self.container.dispatch_service.enqueue_task(
            EnqueueDispatchTaskInput(
                task_id=foreign_task.id,
                priority=1,
            ),
        )

        claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.id, run.id)

        still_queued = self.container.dispatch_service.get_task(foreign_task.id)
        self.assertEqual(still_queued.status, DispatchTaskStatus.QUEUED)

    def test_heartbeat_run_extends_dispatch_lease(self) -> None:
        self._register_agent_and_llm()

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-heartbeat",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )
        claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )
        assert claimed is not None
        first_task = self.container.dispatch_service.get_task(run.id)
        assert first_task.lease_expires_at is not None

        time.sleep(0.01)
        heartbeated = self.container.orchestration_service.heartbeat_run(
            run.id,
            worker_id="worker-1",
        )
        updated_task = self.container.dispatch_service.get_task(run.id)

        self.assertEqual(heartbeated.status, OrchestrationRunStatus.RUNNING)
        assert updated_task.lease_expires_at is not None
        self.assertGreater(updated_task.lease_expires_at, first_task.lease_expires_at)

    def test_recovered_dispatch_task_fails_running_orchestration_run(self) -> None:
        self._register_agent_and_llm()

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-recover-fail",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )
        claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )
        assert claimed is not None

        dispatch_task = self.container.dispatch_service.get_task(run.id)
        assert dispatch_task.lease_expires_at is not None
        recovered = self.container.dispatch_service.recover_abandoned_tasks(
            RecoverAbandonedDispatchTasksInput(
                owner_kind="orchestration_run",
                reason="Orchestration worker lease expired before completion.",
                now=dispatch_task.lease_expires_at + timedelta(seconds=1),
            ),
        )

        self.assertEqual([task.id for task in recovered], [run.id])
        failed_run = self.container.orchestration_service.get_run(run.id)
        failed_task = self.container.dispatch_service.get_task(run.id)

        self.assertEqual(failed_run.status, OrchestrationRunStatus.FAILED)
        assert failed_run.error is not None
        self.assertEqual(failed_run.error.code, "worker_lease_expired")
        self.assertIn("failed for safety", failed_run.error.message)
        self.assertEqual(failed_task.status, DispatchTaskStatus.FAILED)

    def test_wait_on_tool_reconciles_when_tool_finished_before_wait_mapping(self) -> None:
        self._register_agent_and_llm()

        tool = self.container.tool_service.register(
            RegisterToolInput(
                id="background_echo",
                name="Background Echo",
                description="Only runs in the background.",
                supported_modes=(ToolMode.BACKGROUND,),
                runtime_key="background_echo",
            ),
        )

        async def background_echo(arguments: dict[str, object]) -> dict[str, object]:
            return {"message": arguments.get("message")}

        self.container.local_tool_catalog.register(tool, background_echo)

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-early-tool-finish",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )
        claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )
        assert claimed is not None

        queued_tool_run = asyncio.run(
            self.container.tool_service.execute(
                ExecuteToolInput(
                    tool_id="background_echo",
                    arguments={"message": "background hello"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )
        finished_tool_run = self.container.tool_service.process_next_queued_run(
            worker_id="tool-worker-1",
        )

        self.assertEqual(queued_tool_run.status, ToolRunStatus.QUEUED)
        self.assertIsNotNone(finished_tool_run)
        assert finished_tool_run is not None
        self.assertEqual(finished_tool_run.status, ToolRunStatus.SUCCEEDED)

        reconciled = self.container.orchestration_service.wait_on_tool(
            WaitOnToolInput(
                run_id=run.id,
                worker_id="worker-1",
                pending_tool_run_ids=(queued_tool_run.id,),
                reason="tool_background_wait",
            ),
        )

        self.assertEqual(reconciled.status, OrchestrationRunStatus.QUEUED)
        self.assertEqual(reconciled.stage, OrchestrationRunStage.QUEUED)
        self.assertEqual(reconciled.pending_tool_run_ids, ())
        self.assertEqual(reconciled.queue_policy, OrchestrationQueuePolicy.RESUME_FIRST)

    def test_process_next_queued_run_heartbeats_dispatch_during_long_execution(self) -> None:
        custom_harness = SqliteTestHarness()
        custom_settings = replace(
            load_settings(),
            orchestration_run_lease_seconds=1,
            orchestration_run_heartbeat_seconds=0.05,
        )
        custom_harness.initialize_schema(settings=custom_settings)
        container = custom_harness.build_container(settings=custom_settings)
        try:
            adapter = _SlowStaticTextAdapter(
                text="slow llm response",
                delay_seconds=0.15,
            )
            container.llm_adapter_registry.register(
                LlmApiFamily.OPENAI_RESPONSES,
                adapter,
            )
            container.llm_service.register_profile(
                RegisterLlmProfileInput(
                    id="openai.gpt-5.4-mini",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                ),
            )
            container.agent_service.register_profile(
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(
                        system_prompt="Be helpful and concise.",
                    ),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                ),
            )

            run = container.orchestration_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-heartbeat-loop",
                    inbound_instruction=InboundInstruction(source="cli", content="hello"),
                ),
            )
            container.orchestration_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        llm_id="openai.gpt-5.4-mini",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.orchestration_service.enqueue(
                EnqueueOrchestrationRunInput(run_id=run.id),
            )

            processed = container.orchestration_service.process_next_queued_run(
                worker_id="worker-1",
            )

            self.assertIsNotNone(processed)
            assert processed is not None
            self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
            self.assertIn(
                "dispatch.task.heartbeated",
                [event.name for event in container.event_bus.published_events],
            )
        finally:
            custom_harness.close()

    def test_run_lifecycle_can_advance_wait_resume_and_complete(self) -> None:
        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-lifecycle",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )
        assert claimed is not None

        advanced = self.container.orchestration_service.advance_run(
            AdvanceOrchestrationRunInput(
                run_id=run.id,
                worker_id="worker-1",
                stage=OrchestrationRunStage.LLM,
                step_increment=1,
            ),
        )
        waiting = self.container.orchestration_service.wait_on_tool(
            WaitOnToolInput(
                run_id=run.id,
                worker_id="worker-1",
                pending_tool_run_ids=("tool-run-1", "tool-run-2"),
                reason="tool_background_wait",
            ),
        )
        resumed = self.container.orchestration_service.resume_run(
            ResumeOrchestrationRunInput(
                run_id=run.id,
                reason="tool_results_ready",
            ),
        )
        reclaimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )
        assert reclaimed is not None
        completed = self.container.orchestration_service.complete_run(
            CompleteOrchestrationRunInput(
                run_id=run.id,
                worker_id="worker-1",
                result_payload={"output": "done"},
            ),
        )

        self.assertEqual(advanced.stage, OrchestrationRunStage.LLM)
        self.assertEqual(advanced.current_step, 1)
        self.assertEqual(waiting.status, OrchestrationRunStatus.WAITING)
        self.assertEqual(waiting.stage, OrchestrationRunStage.WAITING_ON_TOOL)
        self.assertEqual(
            waiting.pending_tool_run_ids,
            ("tool-run-1", "tool-run-2"),
        )
        self.assertEqual(resumed.status, OrchestrationRunStatus.QUEUED)
        self.assertEqual(resumed.stage, OrchestrationRunStage.QUEUED)
        self.assertEqual(resumed.pending_tool_run_ids, ())
        self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(completed.stage, OrchestrationRunStage.COMPLETED)
        self.assertEqual(completed.result_payload, {"output": "done"})
        dispatch_task = self.container.dispatch_service.get_task(run.id)
        self.assertEqual(dispatch_task.status, DispatchTaskStatus.COMPLETED)

    def test_resume_first_queue_policy_claims_before_fifo_with_same_priority(self) -> None:
        waiting = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-resume-first",
                inbound_instruction=InboundInstruction(source="cli", content="resume me"),
                priority=10,
            ),
        )
        fifo = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-fifo",
                inbound_instruction=InboundInstruction(source="cli", content="fifo"),
                priority=10,
            ),
        )

        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=waiting.id,
                agent_id="writer",
                bulk_key="conversation:resume",
                lane_key="bulk:conversation:resume",
            ),
        )
        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=fifo.id,
                agent_id="writer",
                bulk_key="conversation:fifo",
                lane_key="bulk:conversation:fifo",
            ),
        )

        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=waiting.id),
        )
        claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )
        assert claimed is not None
        self.container.orchestration_service.wait_on_tool(
            WaitOnToolInput(
                run_id=waiting.id,
                worker_id="worker-1",
                pending_tool_run_ids=("tool-run-1",),
            ),
        )

        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=fifo.id),
        )
        resumed = self.container.orchestration_service.resume_run(
            ResumeOrchestrationRunInput(
                run_id=waiting.id,
                queue_policy=OrchestrationQueuePolicy.RESUME_FIRST,
                reason="tool_results_ready",
            ),
        )
        next_claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-2",
        )

        self.assertEqual(
            resumed.queue_policy,
            OrchestrationQueuePolicy.RESUME_FIRST,
        )
        self.assertIsNotNone(next_claimed)
        assert next_claimed is not None
        self.assertEqual(next_claimed.id, waiting.id)

    def test_jump_queue_claims_before_fifo_with_same_priority(self) -> None:
        fifo = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-fifo",
                inbound_instruction=InboundInstruction(source="cli", content="fifo"),
                priority=10,
            ),
        )
        jump_queue = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-jump-queue",
                inbound_instruction=InboundInstruction(
                    source="cli",
                    content="jump queue",
                ),
                priority=10,
                queue_policy=OrchestrationQueuePolicy.JUMP_QUEUE,
            ),
        )

        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=fifo.id,
                agent_id="writer",
                bulk_key="conversation:fifo",
                lane_key="bulk:conversation:fifo",
            ),
        )
        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=jump_queue.id,
                agent_id="writer",
                bulk_key="conversation:jump",
                lane_key="bulk:conversation:jump",
            ),
        )

        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=fifo.id),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=jump_queue.id),
        )

        claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.id, jump_queue.id)

    def test_resume_first_claims_before_jump_queue_with_same_priority(self) -> None:
        resume_first = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-resume-first-priority",
                inbound_instruction=InboundInstruction(
                    source="cli",
                    content="resume first",
                ),
                priority=10,
                queue_policy=OrchestrationQueuePolicy.RESUME_FIRST,
            ),
        )
        jump_queue = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-jump-queue-priority",
                inbound_instruction=InboundInstruction(
                    source="cli",
                    content="jump queue",
                ),
                priority=10,
                queue_policy=OrchestrationQueuePolicy.JUMP_QUEUE,
            ),
        )

        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=resume_first.id,
                agent_id="writer",
                bulk_key="conversation:resume-first",
                lane_key="bulk:conversation:resume-first",
            ),
        )
        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=jump_queue.id,
                agent_id="writer",
                bulk_key="conversation:jump-queue",
                lane_key="bulk:conversation:jump-queue",
            ),
        )

        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=jump_queue.id),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=resume_first.id),
        )

        claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.id, resume_first.id)

    def test_lane_jump_queue_claims_before_fifo_with_same_priority_in_same_lane(self) -> None:
        fifo = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-lane-fifo",
                inbound_instruction=InboundInstruction(source="cli", content="fifo"),
                priority=10,
            ),
        )
        lane_jump_queue = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-lane-jump",
                inbound_instruction=InboundInstruction(
                    source="cli",
                    content="lane jump queue",
                ),
                priority=10,
                queue_policy=OrchestrationQueuePolicy.LANE_JUMP_QUEUE,
            ),
        )

        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=fifo.id,
                agent_id="writer",
                bulk_key="conversation:lane-shared",
                lane_key="bulk:conversation:lane-shared",
            ),
        )
        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=lane_jump_queue.id,
                agent_id="writer",
                bulk_key="conversation:lane-shared",
                lane_key="bulk:conversation:lane-shared",
            ),
        )

        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=fifo.id),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=lane_jump_queue.id),
        )

        claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.id, lane_jump_queue.id)

    def test_lane_jump_queue_does_not_jump_ahead_of_other_lane_heads(self) -> None:
        other_lane_fifo = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-other-lane-fifo",
                inbound_instruction=InboundInstruction(
                    source="cli",
                    content="other lane fifo",
                ),
                priority=10,
            ),
        )
        same_lane_fifo = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-shared-lane-fifo",
                inbound_instruction=InboundInstruction(
                    source="cli",
                    content="shared lane fifo",
                ),
                priority=10,
            ),
        )
        lane_jump_queue = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-shared-lane-jump",
                inbound_instruction=InboundInstruction(
                    source="cli",
                    content="shared lane jump",
                ),
                priority=10,
                queue_policy=OrchestrationQueuePolicy.LANE_JUMP_QUEUE,
            ),
        )

        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=other_lane_fifo.id,
                agent_id="writer",
                bulk_key="conversation:lane-a",
                lane_key="bulk:conversation:lane-a",
            ),
        )
        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=same_lane_fifo.id,
                agent_id="writer",
                bulk_key="conversation:lane-b",
                lane_key="bulk:conversation:lane-b",
            ),
        )
        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=lane_jump_queue.id,
                agent_id="writer",
                bulk_key="conversation:lane-b",
                lane_key="bulk:conversation:lane-b",
            ),
        )

        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=other_lane_fifo.id),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=same_lane_fifo.id),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=lane_jump_queue.id),
        )

        claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.id, other_lane_fifo.id)

    def test_waiting_run_can_fail_without_reclaim(self) -> None:
        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-fail",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )
        claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )
        assert claimed is not None
        self.container.orchestration_service.wait_on_tool(
            WaitOnToolInput(
                run_id=run.id,
                worker_id="worker-1",
                pending_tool_run_ids=("tool-run-1",),
            ),
        )

        failed = self.container.orchestration_service.fail_run(
            FailOrchestrationRunInput(
                run_id=run.id,
                worker_id=None,
                message="tool background failed",
                code="tool_failed",
                details={"tool_run_id": "tool-run-1"},
            ),
        )

        self.assertEqual(failed.status, OrchestrationRunStatus.FAILED)
        self.assertEqual(failed.stage, OrchestrationRunStage.FAILED)
        assert failed.error is not None
        self.assertEqual(failed.error.code, "tool_failed")
        self.assertEqual(
            failed.error.details["tool_run_id"],
            "tool-run-1",
        )

    def test_orchestration_resolves_session_bundle_via_router_and_session_resolver(self) -> None:
        bundle = self.container.orchestration_service.resolve_session_bundle(
            ResolveSessionBundleInput(
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    label="browser",
                    surface="chat",
                    direct_scope=DirectSessionScope.MAIN,
                    metadata={"scope": "main"},
                ),
                ensure=True,
            ),
        )

        self.assertEqual(bundle.routing.key_resolution.key, "agent:assistant:main")
        self.assertEqual(
            bundle.routing.bulk_key,
            "conversation:main:webchat:default:main",
        )
        self.assertEqual(
            bundle.routing.lane_key,
            "bulk:conversation:main:webchat:default:main",
        )
        self.assertTrue(bundle.resolution.resolution.created)
        self.assertIsNotNone(bundle.session)
        self.assertIsNotNone(bundle.active_instance)
        assert bundle.session is not None
        assert bundle.active_instance is not None
        self.assertEqual(bundle.session.id, "agent:assistant:main")
        self.assertEqual(bundle.active_instance.kind.value, "main")

    def test_process_next_queued_run_completes_minimal_llm_loop(self) -> None:
        adapter = _StaticTextAdapter(text="hello from fake llm")
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-process",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        processed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(processed.stage, OrchestrationRunStage.COMPLETED)
        self.assertEqual(processed.current_step, 1)
        assert processed.result_payload is not None
        self.assertEqual(processed.result_payload["output_text"], "hello from fake llm")
        self.assertEqual(
            processed.result_payload["llm_id"],
            "openai.gpt-5.4-mini",
        )
        self.assertEqual(processed.worker_id, "worker-1")

        self.assertEqual(len(adapter.requests), 1)
        self.assertEqual(adapter.requests[0].messages[0].role, LlmMessageRole.SYSTEM)
        self.assertEqual(
            adapter.requests[0].messages[0].content,
            "Be helpful and concise.",
        )
        self.assertEqual(adapter.requests[0].messages[1].role, LlmMessageRole.USER)
        self.assertEqual(adapter.requests[0].messages[1].content, "hello")

        session_messages = self.container.session_service.list_messages(
            ListSessionMessagesInput(
                session_key="agent:assistant:main",
                active_session_only=True,
            ),
        )
        self.assertEqual([message.role for message in session_messages], ["user", "assistant"])
        self.assertEqual(session_messages[0].source_kind, "orchestration_run")
        self.assertEqual(session_messages[0].source_id, run.id)
        self.assertEqual(session_messages[1].source_kind, "llm_invocation")

    def test_process_next_queued_run_prefers_active_instance_binding_over_legacy_session_llm(
        self,
    ) -> None:
        adapter = _StaticTextAdapter(text="binding-aware llm")
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-binding-llm",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        prepared = self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        assert prepared.active_session_id is not None
        with self.container.uow_factory() as uow:
            session = uow.sessions.get("agent:assistant:main")
            assert session is not None
            session.llm_id = "legacy-stale-llm"
            session.metadata["runtime_binding"] = {
                "agent_id": "assistant",
                "llm_id": "legacy-stale-llm",
            }
            uow.sessions.add(session)
            instance = uow.session_instances.get(prepared.active_session_id)
            assert instance is not None
            instance.metadata["runtime_binding"] = {
                "agent_id": "assistant",
                "llm_id": "openai.gpt-5.4-mini",
            }
            instance.metadata["agent_id"] = "assistant"
            instance.metadata["llm_id"] = "openai.gpt-5.4-mini"
            uow.session_instances.add(instance)
            uow.commit()

        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )
        processed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        assert processed.result_payload is not None
        self.assertEqual(processed.result_payload["llm_id"], "openai.gpt-5.4-mini")
        self.assertEqual(processed.result_payload["output_text"], "binding-aware llm")

    def test_process_next_queued_run_completes_inline_tool_loop(self) -> None:
        adapter = _InlineToolLoopAdapter()
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()
        self.container.tool_service.discover_local_tools()

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-process-inline-tool",
                inbound_instruction=InboundInstruction(source="cli", content="search"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        processed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(processed.stage, OrchestrationRunStage.COMPLETED)
        self.assertEqual(processed.current_step, 2)
        assert processed.result_payload is not None
        self.assertEqual(processed.result_payload["output_text"], "tool loop complete")
        self.assertEqual(processed.result_payload["llm_id"], "openai.gpt-5.4-mini")
        self.assertEqual(len(adapter.requests), 2)
        self.assertEqual([schema.name for schema in adapter.requests[0].tool_schemas], ["echo"])
        self.assertEqual(
            [message.role for message in adapter.requests[1].messages],
            [
                LlmMessageRole.SYSTEM,
                LlmMessageRole.USER,
                LlmMessageRole.ASSISTANT,
                LlmMessageRole.TOOL,
            ],
        )
        self.assertEqual(adapter.requests[1].messages[2].tool_call_id, "call-echo-1")
        self.assertEqual(adapter.requests[1].messages[3].tool_call_id, "call-echo-1")
        self.assertEqual(adapter.requests[1].messages[3].name, "echo")

        session_messages = self.container.session_service.list_messages(
            ListSessionMessagesInput(
                session_key="agent:assistant:main",
                active_session_only=True,
            ),
        )
        self.assertEqual(
            [message.role for message in session_messages],
            ["user", "assistant", "tool", "assistant"],
        )
        self.assertEqual(session_messages[1].metadata["tool_call_id"], "call-echo-1")
        self.assertEqual(session_messages[2].metadata["tool_call_id"], "call-echo-1")

    def test_process_next_queued_run_waits_when_tool_is_background(self) -> None:
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            _BackgroundToolAdapter(),
        )
        self._register_agent_and_llm()

        tool = self.container.tool_service.register(
            RegisterToolInput(
                id="background_echo",
                name="Background Echo",
                description="Only runs in the background.",
                supported_modes=(ToolMode.BACKGROUND,),
                runtime_key="background_echo",
            ),
        )

        async def background_echo(arguments: dict[str, object]) -> dict[str, object]:
            return {"message": arguments.get("message")}

        self.container.local_tool_catalog.register(tool, background_echo)

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-process-tool",
                inbound_instruction=InboundInstruction(source="cli", content="search"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        processed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.WAITING)
        self.assertEqual(processed.stage, OrchestrationRunStage.WAITING_ON_TOOL)
        self.assertEqual(processed.current_step, 1)
        self.assertEqual(processed.waiting_reason, "tool_background_wait")
        self.assertEqual(len(processed.pending_tool_run_ids), 1)

        tool_run = self.container.tool_service.get_tool_run(processed.pending_tool_run_ids[0])
        self.assertEqual(tool_run.status, ToolRunStatus.QUEUED)

        session_messages = self.container.session_service.list_messages(
            ListSessionMessagesInput(
                session_key="agent:assistant:main",
                active_session_only=True,
            ),
        )
        self.assertEqual([message.role for message in session_messages], ["user", "assistant"])
        self.assertEqual(session_messages[1].metadata["tool_call_id"], "call-bg-1")

    def test_background_tool_completion_event_resumes_run_and_allows_next_turn(self) -> None:
        adapter = _BackgroundResumeAdapter()
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        tool = self.container.tool_service.register(
            RegisterToolInput(
                id="background_echo",
                name="Background Echo",
                description="Only runs in the background.",
                supported_modes=(ToolMode.BACKGROUND,),
                runtime_key="background_echo",
            ),
        )

        async def background_echo(arguments: dict[str, object]) -> dict[str, object]:
            return {"message": arguments.get("message")}

        self.container.local_tool_catalog.register(tool, background_echo)

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-process-background-resume",
                inbound_instruction=InboundInstruction(source="cli", content="search"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        waiting = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )
        assert waiting is not None
        self.assertEqual(waiting.status, OrchestrationRunStatus.WAITING)
        self.assertEqual(len(waiting.pending_tool_run_ids), 1)
        background_tool_run_id = waiting.pending_tool_run_ids[0]

        finished_tool_run = self.container.tool_service.process_next_queued_run(
            worker_id="tool-worker-1",
        )
        self.assertIsNotNone(finished_tool_run)
        assert finished_tool_run is not None
        self.assertEqual(finished_tool_run.id, background_tool_run_id)
        self.assertEqual(finished_tool_run.status, ToolRunStatus.SUCCEEDED)

        resumed = self.container.orchestration_service.get_run(run.id)
        self.assertEqual(resumed.status, OrchestrationRunStatus.QUEUED)
        self.assertEqual(resumed.stage, OrchestrationRunStage.QUEUED)
        self.assertEqual(resumed.pending_tool_run_ids, ())
        self.assertEqual(resumed.waiting_reason, None)
        self.assertEqual(
            resumed.queue_policy,
            OrchestrationQueuePolicy.RESUME_FIRST,
        )

        session_messages = self.container.session_service.list_messages(
            ListSessionMessagesInput(
                session_key="agent:assistant:main",
                active_session_only=True,
            ),
        )
        self.assertEqual(
            [message.role for message in session_messages],
            ["user", "assistant", "tool"],
        )
        self.assertEqual(session_messages[2].source_id, background_tool_run_id)
        self.assertEqual(session_messages[2].metadata["tool_call_id"], "call-bg-1")

        completed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )
        self.assertIsNotNone(completed)
        assert completed is not None
        self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(completed.stage, OrchestrationRunStage.COMPLETED)
        self.assertEqual(completed.current_step, 2)
        assert completed.result_payload is not None
        self.assertEqual(completed.result_payload["output_text"], "background loop complete")
        self.assertEqual(len(adapter.requests), 2)
        self.assertEqual(
            [message.role for message in adapter.requests[1].messages],
            [
                LlmMessageRole.SYSTEM,
                LlmMessageRole.USER,
                LlmMessageRole.ASSISTANT,
                LlmMessageRole.TOOL,
            ],
        )

    def test_process_next_queued_run_fails_when_llm_requests_unknown_tool(self) -> None:
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            _ToolCallAdapter(),
        )
        self._register_agent_and_llm()

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-process-tool",
                inbound_instruction=InboundInstruction(source="cli", content="search"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        processed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.FAILED)
        self.assertEqual(processed.stage, OrchestrationRunStage.FAILED)
        self.assertEqual(processed.current_step, 1)
        assert processed.error is not None
        self.assertEqual(processed.error.code, "engine_failed")
        self.assertIn("search_docs", processed.error.message)

        session_messages = self.container.session_service.list_messages(
            ListSessionMessagesInput(
                session_key="agent:assistant:main",
                active_session_only=True,
            ),
        )
        self.assertEqual(
            [message.role for message in session_messages],
            ["user", "assistant", "assistant"],
        )

    def test_cancel_run_keeps_it_out_of_queue(self) -> None:
        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-cancel",
                inbound_instruction=InboundInstruction(source="http", content="stop"),
            ),
        )
        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=run.id,
                agent_id="writer",
                bulk_key="conversation:cancel",
                lane_key="bulk:conversation:cancel",
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        cancelled = self.container.orchestration_service.cancel_run(
            run.id,
            reason="user_cancelled",
        )
        claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )

        self.assertEqual(cancelled.status, OrchestrationRunStatus.CANCELLED)
        self.assertEqual(cancelled.stage, OrchestrationRunStage.CANCELLED)
        self.assertIsNone(claimed)

    def test_llm_adapter_failure_is_surface_in_orchestration_error(self) -> None:
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            _FailingAdapter(),
        )
        self._register_agent_and_llm()

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-llm-failure",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    llm_id="openai.gpt-5.4-mini",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        processed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.FAILED)
        self.assertEqual(processed.stage, OrchestrationRunStage.FAILED)
        assert processed.error is not None
        self.assertEqual(processed.error.code, "engine_failed")
        self.assertIn("adapter_error", processed.error.message)
        self.assertIn("sample adapter failure", processed.error.message)


if __name__ == "__main__":
    unittest.main()
