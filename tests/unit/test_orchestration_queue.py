from __future__ import annotations

from inspect import signature
from types import SimpleNamespace

from crxzipple.interfaces.runtime_container import build_runtime_container
from crxzipple.modules.orchestration.application.turn_submission import (
    build_submission_options,
    submit_turn,
)
from crxzipple.modules.orchestration.application.coordinators.scheduler_signals import (
    RunSchedulerSignalCoordinator,
)
from crxzipple.modules.orchestration.application.lane import session_lane_key
from crxzipple.modules.orchestration.application import (
    OrchestrationToolTerminalReaction,
    SubmitBoundOrchestrationTurnInput,
    SubmitOrchestrationTurnInput,
)
from crxzipple.modules.channels import (
    ChannelAccountRuntimeBinding,
    ChannelInteraction,
    ChannelRuntimeRegistration,
)
from crxzipple.modules.session.application import EnsureSessionInput, ResolveSessionInput
from crxzipple.modules.orchestration.interfaces.shared import (
    build_accept_run_input,
    build_session_route_context,
)
from crxzipple.shared.domain.events import Event, named_event_topic
from tests.unit.support import SqliteTestHarness
from tests.unit.orchestration_test_support import *  # noqa: F403


def _legacy_runtime_outbound_topic(runtime_id: str) -> str:
    return f"delivery.runtime.{runtime_id.strip()}"


class OrchestrationQueueTestCase(OrchestrationTestCaseBase):
    def test_scheduler_signal_queue_is_idempotent_when_duplicate_insert_races(self) -> None:
        class _SignalRepository:
            def __init__(self, state: dict[str, object]) -> None:
                self.state = state

            def add(self, signal):  # noqa: ANN001, ANN201
                self.state["signal"] = signal

            def get(self, signal_id: str):  # noqa: ANN201
                signal = self.state.get("signal")
                if signal is not None and signal.id == signal_id:
                    return signal
                return None

        class _RaceUnitOfWork:
            def __init__(self, state: dict[str, object]) -> None:
                self.state = state
                self.orchestration_scheduler_signals = _SignalRepository(state)

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def collect(self, aggregate):  # noqa: ANN001, ANN201
                self.state["collected"] = aggregate

            def commit(self) -> None:
                if self.state.pop("raise_on_commit", False):
                    raise RuntimeError("simulated duplicate insert race")

        state: dict[str, object] = {"raise_on_commit": True}
        coordinator = RunSchedulerSignalCoordinator(
            uow_factory=lambda: _RaceUnitOfWork(state),
        )

        signal = coordinator.queue_tool_terminal_signal(tool_run_id="tool-runtime-1")

        self.assertEqual(signal.id, "tool-terminal:tool-runtime-1")
        self.assertIs(signal, state["signal"])

    def test_runtime_container_has_no_implicit_runtime_event_subscriber_switch(self) -> None:
        parameters = signature(build_runtime_container).parameters

        self.assertNotIn("enable_runtime_event_subscribers", parameters)

    def test_orchestration_runtime_services_split_scheduler_and_operations_observer(
        self,
    ) -> None:
        scheduler_runtime = self.orchestration_scheduler_runtime_event_service
        operations_runtime = self.operations_observer_runtime_event_service

        self.assertIsNotNone(scheduler_runtime)
        self.assertIsNotNone(operations_runtime)
        assert scheduler_runtime is not None
        assert operations_runtime is not None
        scheduler_subscription_ids = {
            subscription.subscription_id
            for subscription in scheduler_runtime.subscriptions
        }
        operations_subscription_ids = {
            subscription.subscription_id
            for subscription in operations_runtime.subscriptions
        }

        self.assertIn(
            "orchestration.runtime.tool-terminal.tool.run.succeeded",
            scheduler_subscription_ids,
        )
        self.assertIn(
            "orchestration.runtime.dispatch-recovery",
            scheduler_subscription_ids,
        )
        self.assertIn(
            "orchestration.scheduler.dispatch-wakeup.dispatch.task.queued",
            scheduler_subscription_ids,
        )
        self.assertIn(
            "operations.observer.dispatch.task.queued",
            operations_subscription_ids,
        )
        self.assertIn(
            "operations.observer.orchestration.run.queued",
            operations_subscription_ids,
        )

    def test_scheduler_runtime_event_service_queues_tool_signal_without_background_subscribers(
        self,
    ) -> None:
        custom_harness = SqliteTestHarness()
        try:
            container = custom_harness.build_runtime_container()
            runtime = container.require(AppKey.ORCHESTRATION_SCHEDULER_RUNTIME_EVENT_SERVICE)
            self.assertIsNotNone(runtime)

            topic = named_event_topic("tool.run.succeeded")
            container.require(AppKey.EVENTS_SERVICE).publish(
                Event(
                    name="tool.run.succeeded",
                    payload={
                        "run_id": "tool-runtime-1",
                        "mode": "background",
                    },
                ),
            )

            processed_count = (
                container.require(AppKey.ORCHESTRATION_SCHEDULER_SERVICE).process_runtime_events(
                    limit_per_subscription=10,
                )
            )

            self.assertGreaterEqual(processed_count, 1)
            cursor = container.require(AppKey.EVENTS_SERVICE).get_subscription_cursor(
                "orchestration.runtime.tool-terminal.tool.run.succeeded",
                source_topic=topic,
            )
            self.assertIsNotNone(cursor)
            with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
                signal = uow.orchestration_scheduler_signals.get(
                    "tool-terminal:tool-runtime-1",
                )
            self.assertIsNotNone(signal)
            assert signal is not None
            self.assertEqual(signal.signal_payload["tool_run_id"], "tool-runtime-1")
        finally:
            custom_harness.close()

    def test_scheduler_runtime_event_service_ignores_inline_tool_terminal_events(
        self,
    ) -> None:
        custom_harness = SqliteTestHarness()
        try:
            container = custom_harness.build_runtime_container()

            container.require(AppKey.EVENTS_SERVICE).publish(
                Event(
                    name="tool.run.succeeded",
                    payload={
                        "run_id": "inline-tool-runtime-1",
                        "mode": "inline",
                    },
                ),
            )

            processed_count = (
                container.require(AppKey.ORCHESTRATION_SCHEDULER_SERVICE).process_runtime_events(
                    limit_per_subscription=10,
                )
            )

            self.assertGreaterEqual(processed_count, 1)
            with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
                signal = uow.orchestration_scheduler_signals.get(
                    "tool-terminal:inline-tool-runtime-1",
                )
            self.assertIsNone(signal)
        finally:
            custom_harness.close()

    def test_tool_terminal_reaction_uses_lookup_to_ignore_legacy_inline_events(
        self,
    ) -> None:
        class _Scheduler:
            def __init__(self) -> None:
                self.queued_tool_run_ids: list[str] = []

            def queue_tool_terminal_signal(self, *, tool_run_id: str):  # noqa: ANN201
                self.queued_tool_run_ids.append(tool_run_id)
                return SimpleNamespace(id=f"tool-terminal:{tool_run_id}")

        scheduler = _Scheduler()
        reaction = OrchestrationToolTerminalReaction(
            scheduler_service=scheduler,  # type: ignore[arg-type]
            tool_run_lookup=lambda _run_id: SimpleNamespace(
                target=SimpleNamespace(mode=SimpleNamespace(value="inline")),
            ),
        )

        reaction.react_to_terminal_tool_run(
            Event(
                name="tool.run.succeeded",
                payload={"run_id": "legacy-inline-tool-runtime-1"},
            ),
        )

        self.assertEqual(scheduler.queued_tool_run_ids, [])

    def test_accept_prepare_session_queue_and_claim_assignment(self) -> None:
        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-1",
                inbound_instruction=InboundInstruction(
                    source="http",
                    content="Summarize this",
                    metadata={"request_id": "req-1"},
                ),
                reply_target=ReplyTarget(
                    interface_name="http",
                    address="request:req-1",
                ),
                priority=20,
                max_steps=6,
            ),
        )

        self.assertEqual(run.status, OrchestrationRunStatus.ACCEPTED)
        self.assertEqual(run.stage, OrchestrationRunStage.ACCEPTED)

        prepared = self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="writer",
                    channel="webchat",
                    label="browser",
                    surface="chat",
                    direct_scope=DirectSessionScope.MAIN,
                    metadata={"request_id": "req-1"},
                ),
                priority=10,
            ),
        )
        enqueued = self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )
        claimed_assignment = assign_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )

        self.assertEqual(prepared.stage, OrchestrationRunStage.BULK_READY)
        self.assertEqual(enqueued.status, OrchestrationRunStatus.QUEUED)
        self.assertIsNotNone(claimed_assignment)
        assert claimed_assignment is not None
        self.assertEqual(claimed_assignment.id, run.id)
        self.assertEqual(claimed_assignment.status, OrchestrationRunStatus.RUNNING)
        self.assertEqual(claimed_assignment.stage, OrchestrationRunStage.RUNNING)
        self.assertEqual(claimed_assignment.worker_id, "worker-1")
        self.assertEqual(claimed_assignment.session_key, "agent:writer:main")
        self.assertTrue(claimed_assignment.active_session_id)
        self.assertIsNotNone(claimed_assignment.started_at)
        self.assertEqual(
            claimed_assignment.metadata["session_key"],
            "agent:writer:main",
        )
        self.assertEqual(claimed_assignment.metadata["session_kind"], "main")
        dispatch_task = self.dispatch_service.get_task(run.id)
        self.assertEqual(dispatch_task.status, DispatchTaskStatus.CLAIMED)
        self.assertEqual(dispatch_task.policy, DispatchPolicy.FIFO)
        self.assertEqual(dispatch_task.claimed_by, "worker-1")
        self.assertIsNotNone(dispatch_task.lease_expires_at)

    def test_scheduler_assign_next_assignment_prefers_lower_priority(self) -> None:
        low_priority = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-low",
                inbound_instruction=InboundInstruction(source="cli", content="first"),
                priority=50,
            ),
        )
        high_priority = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-high",
                inbound_instruction=InboundInstruction(source="cli", content="second"),
                priority=5,
            ),
        )

        self.orchestration_intake_service.route(
            RouteOrchestrationRunInput(
                run_id=low_priority.id,
                agent_id="writer",
                lane_key="session:one",
            ),
        )
        self.orchestration_intake_service.route(
            RouteOrchestrationRunInput(
                run_id=high_priority.id,
                agent_id="writer",
                lane_key="session:two",
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=low_priority.id),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=high_priority.id),
        )

        claimed = assign_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.id, high_priority.id)

    def test_scheduler_assign_next_assignment_skips_blocked_lane(self) -> None:
        active = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-active",
                inbound_instruction=InboundInstruction(source="cli", content="active"),
                priority=50,
            ),
        )

        self.orchestration_intake_service.route(
            RouteOrchestrationRunInput(
                run_id=active.id,
                agent_id="writer",
                lane_key="session:lane-a",
            ),
        )

        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=active.id),
        )
        first = assign_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )

        blocked = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-blocked",
                inbound_instruction=InboundInstruction(source="cli", content="blocked"),
                priority=1,
            ),
        )
        available = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-available",
                inbound_instruction=InboundInstruction(source="cli", content="available"),
                priority=10,
            ),
        )

        self.orchestration_intake_service.route(
            RouteOrchestrationRunInput(
                run_id=blocked.id,
                agent_id="writer",
                lane_key="session:lane-a",
            ),
        )
        self.orchestration_intake_service.route(
            RouteOrchestrationRunInput(
                run_id=available.id,
                agent_id="writer",
                lane_key="session:lane-b",
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=blocked.id),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=available.id),
        )

        second = assign_next_orchestration_assignment(self.container,
            worker_id="worker-2",
        )

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        assert first is not None
        assert second is not None
        self.assertEqual(first.id, active.id)
        self.assertEqual(second.id, available.id)

    def test_scheduler_assign_next_assignment_blocks_lane_while_waiting(self) -> None:
        waiting = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-waiting",
                inbound_instruction=InboundInstruction(source="cli", content="waiting"),
                priority=5,
            ),
        )

        self.orchestration_intake_service.route(
            RouteOrchestrationRunInput(
                run_id=waiting.id,
                agent_id="writer",
                lane_key="session:lane-wait",
            ),
        )

        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=waiting.id),
        )

        claimed = assign_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )
        assert claimed is not None
        self.orchestration_executor_service.wait_assignment_on_tool(
            run_id=waiting.id,
            worker_id="worker-1",
            pending_tool_run_ids=("tool-run-1",),
            reason="tool_background_wait",
        )

        queued = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-same-lane",
                inbound_instruction=InboundInstruction(source="cli", content="queued"),
                priority=1,
            ),
        )
        self.orchestration_intake_service.route(
            RouteOrchestrationRunInput(
                run_id=queued.id,
                agent_id="writer",
                lane_key="session:lane-wait",
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=queued.id),
        )

        blocked = assign_next_orchestration_assignment(self.container,
            worker_id="worker-2",
        )

        self.assertIsNone(blocked)

    def test_process_assignment_inline_prefers_requested_run(self) -> None:
        self._register_agent_and_llm()
        profile = self.agent_service.get_profile("assistant")

        first = submit_turn(
            self.orchestration_scheduler_service,
            content="first requested run",
            options=build_submission_options(
                profile=profile,
                llm_id=None,
                channel="webhook",
                chat_type="direct",
                peer_id="user-inline-first",
                conversation_id="conv-inline-first",
                thread_id=None,
                account_id="default",
                main_key="main",
                direct_scope=DirectSessionScope.PER_CHANNEL_PEER,
                source="webhook",
                queue_policy=OrchestrationQueuePolicy.JUMP_QUEUE,
                priority=50,
                max_steps=None,
            ),
            inline_worker_id=None,
        )
        second = submit_turn(
            self.orchestration_scheduler_service,
            content="second requested run",
            options=build_submission_options(
                profile=profile,
                llm_id=None,
                channel="webhook",
                chat_type="direct",
                peer_id="user-inline-second",
                conversation_id="conv-inline-second",
                thread_id=None,
                account_id="default",
                main_key="main",
                direct_scope=DirectSessionScope.PER_CHANNEL_PEER,
                source="webhook",
                queue_policy=OrchestrationQueuePolicy.JUMP_QUEUE,
                priority=5,
                max_steps=None,
            ),
            inline_worker_id=None,
        )

        queued_first = self.orchestration_scheduler_service.process_run_request(
            run_id=first.id,
            worker_id="scheduler-inline-first",
        )
        queued_second = self.orchestration_scheduler_service.process_run_request(
            run_id=second.id,
            worker_id="scheduler-inline-second",
        )

        self.assertIsNotNone(queued_first)
        self.assertIsNotNone(queued_second)

        completed_first = self.orchestration_executor_service.process_assignment_inline(
            run_id=first.id,
            worker_id="worker-inline-first",
        )

        self.assertEqual(completed_first.id, first.id)

        first_after = self.orchestration_run_query_service.get_run(first.id)
        second_after = self.orchestration_run_query_service.get_run(second.id)
        self.assertNotEqual(first_after.status, OrchestrationRunStatus.QUEUED)
        self.assertEqual(second_after.status, OrchestrationRunStatus.QUEUED)

    def test_scheduler_assign_next_assignment_ignores_foreign_dispatch_owner_kind(self) -> None:
        self._register_agent_and_llm()

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-owner-filter",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
                priority=50,
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        foreign_task = self.dispatch_service.create_task(
            CreateDispatchTaskInput(
                task_id="foreign-tool-task",
                owner_kind="tool_run",
                owner_id="tool-run-1",
                priority=1,
            ),
        )
        self.dispatch_service.enqueue_task(
            EnqueueDispatchTaskInput(
                task_id=foreign_task.id,
                priority=1,
            ),
        )

        claimed = assign_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.id, run.id)

        still_queued = self.dispatch_service.get_task(foreign_task.id)
        self.assertEqual(still_queued.status, DispatchTaskStatus.QUEUED)

    def test_heartbeat_assignment_extends_dispatch_lease(self) -> None:
        self._register_agent_and_llm()

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-heartbeat",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )
        claimed = assign_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )
        assert claimed is not None
        first_task = self.dispatch_service.get_task(run.id)
        assert first_task.lease_expires_at is not None

        time.sleep(0.01)
        heartbeated = self.orchestration_executor_service.heartbeat_assignment(
            run_id=run.id,
            worker_id="worker-1",
        )
        updated_task = self.dispatch_service.get_task(run.id)

        self.assertEqual(heartbeated.status, OrchestrationRunStatus.RUNNING)
        assert updated_task.lease_expires_at is not None
        self.assertGreater(updated_task.lease_expires_at, first_task.lease_expires_at)

    def test_recovered_dispatch_task_fails_running_orchestration_run(self) -> None:
        self._register_agent_and_llm()

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-recover-fail",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )
        claimed = assign_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )
        assert claimed is not None

        dispatch_task = self.dispatch_service.get_task(run.id)
        assert dispatch_task.lease_expires_at is not None
        recovered = self.dispatch_service.recover_abandoned_tasks(
            RecoverAbandonedDispatchTasksInput(
                owner_kind="orchestration_run",
                reason="Orchestration worker lease expired before completion.",
                now=dispatch_task.lease_expires_at + timedelta(seconds=1),
            ),
        )

        self.assertEqual([task.id for task in recovered], [run.id])
        processed_events = self.orchestration_scheduler_service.process_runtime_events(
            limit_per_subscription=10,
        )
        failed_run = self.orchestration_run_query_service.get_run(run.id)
        failed_task = self.dispatch_service.get_task(run.id)

        self.assertGreaterEqual(processed_events, 1)
        self.assertEqual(failed_run.status, OrchestrationRunStatus.FAILED)
        assert failed_run.error is not None
        self.assertEqual(failed_run.error.code, "worker_lease_expired")
        self.assertIn("failed for safety", failed_run.error.message)
        self.assertEqual(failed_task.status, DispatchTaskStatus.FAILED)

    def test_run_lifecycle_can_advance_wait_resume_and_complete(self) -> None:
        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-lifecycle",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        claimed = assign_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )
        assert claimed is not None

        advanced = self.orchestration_executor_service.advance_assignment(
            run_id=run.id,
            worker_id="worker-1",
            stage=OrchestrationRunStage.LLM,
            step_increment=1,
        )
        waiting = self.orchestration_executor_service.wait_assignment_on_tool(
            run_id=run.id,
            worker_id="worker-1",
            pending_tool_run_ids=("tool-run-1", "tool-run-2"),
            reason="tool_background_wait",
        )
        resumed = self.orchestration_scheduler_service.resume_run(
            ResumeOrchestrationRunInput(
                run_id=run.id,
                reason="tool_results_ready",
            ),
        )
        reclaimed = assign_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )
        assert reclaimed is not None
        completed = self.orchestration_executor_service.complete_assignment(
            run_id=run.id,
            worker_id="worker-1",
            result_payload={"output": "done"},
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
        dispatch_task = self.dispatch_service.get_task(run.id)
        self.assertEqual(dispatch_task.status, DispatchTaskStatus.COMPLETED)

    def test_complete_run_skips_lark_legacy_runtime_topic_publication(self) -> None:
        self._register_agent_and_llm()
        self.channel_runtime_manager.register_runtime(
            ChannelRuntimeRegistration(
                runtime_id="lark-runtime-1",
                channel_type="lark",
                service_key="channel:lark",
            ),
        )
        self.channel_runtime_manager.bind_account(
            ChannelAccountRuntimeBinding(
                channel_type="lark",
                channel_account_id="default",
                runtime_id="lark-runtime-1",
            ),
        )
        profile = self.agent_service.get_profile("assistant")
        options = build_submission_options(
            profile=profile,
            llm_id=None,
            channel="lark",
            chat_type="direct",
            peer_id="ou_lark_queue_1",
            conversation_id="oc_lark_queue_1",
            thread_id=None,
            account_id="default",
            main_key="main",
            direct_scope=DirectSessionScope.PER_CHANNEL_PEER,
            source="lark_event",
            queue_policy=OrchestrationQueuePolicy.JUMP_QUEUE,
            priority=100,
            max_steps=None,
        )
        run = submit_turn(
            self.orchestration_scheduler_service,
            content="hello from lark",
            options=options,
            inline_worker_id="scheduler-inline",
            reply_interface="lark",
            reply_address="oc_lark_queue_1",
            reply_to="om_parent_1",
            reply_metadata={
                "reply_address": {
                    "channel_type": "lark",
                    "channel_account_id": "default",
                    "external_conversation_id": "oc_lark_queue_1",
                    "external_user_id": "ou_lark_queue_1",
                    "metadata": {
                        "receive_id_type": "chat_id",
                        "chat_type": "direct",
                        "message_id": "om_parent_1",
                    },
                },
            },
        )
        claimed = assign_next_orchestration_assignment(self.container,
            worker_id="worker-lark-1",
        )
        self.assertIsNotNone(claimed)
        legacy_cursor = self.events_service.snapshot_event_topic(
            _legacy_runtime_outbound_topic("lark-runtime-1"),
        )

        completed = self.orchestration_executor_service.complete_assignment(
            run_id=run.id,
            worker_id="worker-lark-1",
            result_payload={"output_text": "done without legacy runtime topic"},
        )

        self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
        legacy_records = self.events_service.read_event_topic(
            _legacy_runtime_outbound_topic("lark-runtime-1"),
            after_cursor=legacy_cursor,
            limit=10,
        )
        self.assertEqual(legacy_records, ())

    def test_submit_turn_sets_reply_target(self) -> None:
        self._register_agent_and_llm()
        profile = self.agent_service.get_profile("assistant")
        options = build_submission_options(
            profile=profile,
            llm_id=None,
            channel="webhook",
            chat_type="direct",
            peer_id="user-reply-1",
            conversation_id="conv-reply-1",
            thread_id=None,
            account_id="default",
            main_key="main",
            direct_scope=DirectSessionScope.PER_CHANNEL_PEER,
            source="webhook",
            queue_policy=OrchestrationQueuePolicy.JUMP_QUEUE,
            priority=100,
            max_steps=None,
        )

        run = submit_turn(
            self.orchestration_scheduler_service,
            content="reply target alias test",
            options=options,
            reply_interface="webhook",
            reply_address="https://example.test/reply",
            reply_to="thread-reply-1",
            reply_metadata={
                "reply_address": {
                    "channel_type": "webhook",
                    "channel_account_id": "default",
                    "webhook_callback_url": "https://example.test/reply",
                },
            },
        )

        self.assertIsNotNone(run.reply_target)
        assert run.reply_target is not None
        self.assertEqual(run.reply_target.interface_name, "webhook")
        self.assertEqual(run.reply_target.address, "https://example.test/reply")
        self.assertEqual(run.reply_target.reply_to, "thread-reply-1")
        self.assertEqual(
            run.reply_target.metadata["reply_address"]["channel_type"],
            "webhook",
        )
        self.assertNotIn("legacy", run.reply_target.metadata)

    def test_submit_turn_routes_through_ingress_before_queueing_run(self) -> None:
        self._register_agent_and_llm()
        profile = self.agent_service.get_profile("assistant")

        run = submit_turn(
            self.orchestration_scheduler_service,
            content="hello through ingress",
            options=build_submission_options(
                profile=profile,
                llm_id=None,
                channel="webhook",
                chat_type="direct",
                peer_id="user-ingress-1",
                conversation_id="conv-ingress-1",
                thread_id=None,
                account_id="default",
                main_key="main",
                direct_scope=DirectSessionScope.PER_CHANNEL_PEER,
                source="webhook",
                queue_policy=OrchestrationQueuePolicy.JUMP_QUEUE,
                priority=80,
                max_steps=None,
            ),
            inline_worker_id="scheduler-inline",
            reply_interface="webhook",
            reply_address="https://example.test/ingress",
            reply_to="conv-ingress-1",
        )

        self.assertEqual(run.status, OrchestrationRunStatus.QUEUED)
        self.assertEqual(run.stage, OrchestrationRunStage.QUEUED)
        self.assertEqual(run.session_key, "agent:assistant:webhook:dm:user-ingress-1")

        with self.uow_factory() as uow:
            request = uow.orchestration_ingress_requests.get_by_run_id(run.id)

        self.assertIsNotNone(request)
        assert request is not None
        self.assertEqual(request.status.value, "completed")
        self.assertEqual(request.run_id, run.id)
        self.assertEqual(request.queue_policy, OrchestrationQueuePolicy.JUMP_QUEUE)

    def test_scheduler_service_processes_pending_ingress_request(self) -> None:
        self._register_agent_and_llm()
        profile = self.agent_service.get_profile("assistant")
        options = build_submission_options(
            profile=profile,
            llm_id=None,
            channel="webhook",
            chat_type="direct",
            peer_id="user-ingress-pending",
            conversation_id=None,
            thread_id=None,
            account_id=None,
            main_key="main",
            direct_scope=DirectSessionScope.MAIN,
            source="webhook",
            queue_policy=OrchestrationQueuePolicy.JUMP_QUEUE,
            priority=50,
            max_steps=None,
        )
        run = self.orchestration_scheduler_service.submit_turn(
            SubmitOrchestrationTurnInput(
                accept_input=build_accept_run_input(
                    source=options.source,
                    content="hello pending ingress",
                    queue_policy=options.queue_policy,
                    priority=options.priority,
                    max_steps=options.max_steps,
                ),
                context=build_session_route_context(
                    agent_id=options.agent_id,
                    channel=options.channel,
                    chat_type=options.chat_type,
                    peer_id=options.peer_id,
                    conversation_id=options.conversation_id,
                    thread_id=options.thread_id,
                    account_id=options.account_id,
                    main_key=options.main_key,
                    direct_scope=options.direct_scope,
                ),
                requested_llm_id=options.llm_id,
                enqueue_queue_policy=options.queue_policy,
                enqueue_priority=options.priority,
            ),
            inline_worker_id=None,
        )

        self.assertEqual(run.status, OrchestrationRunStatus.ACCEPTED)
        self.assertIsNone(run.session_key)

        with self.uow_factory() as uow:
            pending = uow.orchestration_ingress_requests.get_by_run_id(run.id)

        self.assertIsNotNone(pending)
        assert pending is not None
        self.assertEqual(pending.status.value, "queued")

        processed = self.orchestration_scheduler_service.process_run_request(
            run_id=run.id,
            worker_id="scheduler-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.QUEUED)
        self.assertEqual(processed.session_key, "agent:assistant:main")

        with self.uow_factory() as uow:
            completed = uow.orchestration_ingress_requests.get_by_run_id(run.id)

        self.assertIsNotNone(completed)
        assert completed is not None
        self.assertEqual(completed.status.value, "completed")

    def test_inline_ingress_submission_reserves_request_from_background_scheduler(
        self,
    ) -> None:
        self._register_agent_and_llm()
        profile = self.agent_service.get_profile("assistant")
        options = build_submission_options(
            profile=profile,
            llm_id=None,
            channel="webhook",
            chat_type="direct",
            peer_id="user-inline-ingress-reserved",
            conversation_id=None,
            thread_id=None,
            account_id=None,
            main_key="main",
            direct_scope=DirectSessionScope.MAIN,
            source="webhook",
            queue_policy=OrchestrationQueuePolicy.JUMP_QUEUE,
            priority=40,
            max_steps=None,
        )
        run = self.orchestration_scheduler_service.ingress_coordinator.submit_turn(
            SubmitOrchestrationTurnInput(
                accept_input=build_accept_run_input(
                    source=options.source,
                    content="inline reserved ingress",
                    queue_policy=options.queue_policy,
                    priority=options.priority,
                    max_steps=options.max_steps,
                ),
                context=build_session_route_context(
                    agent_id=options.agent_id,
                    channel=options.channel,
                    chat_type=options.chat_type,
                    peer_id=options.peer_id,
                    conversation_id=options.conversation_id,
                    thread_id=options.thread_id,
                    account_id=options.account_id,
                    main_key=options.main_key,
                    direct_scope=options.direct_scope,
                ),
                requested_llm_id=options.llm_id,
                enqueue_queue_policy=options.queue_policy,
                enqueue_priority=options.priority,
            ),
            claimed_worker_id="inline-ingress-reserved",
        )

        with self.uow_factory() as uow:
            request = uow.orchestration_ingress_requests.get_by_run_id(run.id)

        self.assertIsNotNone(request)
        assert request is not None
        self.assertEqual(request.status.value, "processing")
        self.assertEqual(request.worker_id, "inline-ingress-reserved")
        self.assertIsNotNone(request.claimed_at)
        self.assertIsNone(
            self.orchestration_scheduler_service.process_next_request(
                worker_id="scheduler-daemon-1",
            ),
        )

    def test_claim_for_run_returns_none_once_request_is_already_processing(self) -> None:
        self._register_agent_and_llm()
        profile = self.agent_service.get_profile("assistant")
        options = build_submission_options(
            profile=profile,
            llm_id=None,
            channel="webhook",
            chat_type="direct",
            peer_id="user-claimed-ingress",
            conversation_id=None,
            thread_id=None,
            account_id=None,
            main_key="main",
            direct_scope=DirectSessionScope.MAIN,
            source="webhook",
            queue_policy=OrchestrationQueuePolicy.JUMP_QUEUE,
            priority=30,
            max_steps=None,
        )
        run = self.orchestration_scheduler_service.ingress_coordinator.submit_turn(
            SubmitOrchestrationTurnInput(
                accept_input=build_accept_run_input(
                    source=options.source,
                    content="already processing ingress",
                    queue_policy=options.queue_policy,
                    priority=options.priority,
                    max_steps=options.max_steps,
                ),
                context=build_session_route_context(
                    agent_id=options.agent_id,
                    channel=options.channel,
                    chat_type=options.chat_type,
                    peer_id=options.peer_id,
                    conversation_id=options.conversation_id,
                    thread_id=options.thread_id,
                    account_id=options.account_id,
                    main_key=options.main_key,
                    direct_scope=options.direct_scope,
                ),
                requested_llm_id=options.llm_id,
                enqueue_queue_policy=options.queue_policy,
                enqueue_priority=options.priority,
            ),
            claimed_worker_id="inline-ingress-claimed",
        )

        claimed_again = (
            self.orchestration_scheduler_service.ingress_coordinator.claim_request_for_run(
                run_id=run.id,
                worker_id="scheduler-daemon-claimed",
            )
        )

        self.assertIsNone(claimed_again)

    def test_scheduler_service_processes_pending_bound_ingress_request(self) -> None:
        target = self.session_service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
            ),
        )
        run = self.orchestration_scheduler_service.submit_bound_turn(
            SubmitBoundOrchestrationTurnInput(
                accept_input=build_accept_run_input(
                    source="sessions_send",
                    queue_policy=OrchestrationQueuePolicy.JUMP_QUEUE,
                    priority=70,
                ),
                agent_id="assistant",
                session_key=target.id,
                active_session_id=target.active_session_id,
                metadata={
                    "sessions_send": {
                        "message_id": "msg-bound-ingress-1",
                    },
                },
                enqueue_queue_policy=OrchestrationQueuePolicy.JUMP_QUEUE,
                enqueue_priority=70,
            ),
            inline_worker_id=None,
        )

        self.assertEqual(run.status, OrchestrationRunStatus.ACCEPTED)
        self.assertIsNone(run.session_key)
        self.assertIsNone(
            assign_next_orchestration_assignment(
                self.container,
                worker_id="worker-bound-ingress-no-claim",
            ),
        )

        with self.uow_factory() as uow:
            pending = uow.orchestration_ingress_requests.get_by_run_id(run.id)

        self.assertIsNotNone(pending)
        assert pending is not None
        self.assertEqual(pending.kind.value, "bound_turn")
        self.assertIsNotNone(pending.bound_session_target)
        assert pending.bound_session_target is not None
        self.assertEqual(pending.bound_session_target.session_key, target.id)
        self.assertEqual(
            pending.bound_session_target.active_session_id,
            target.active_session_id,
        )

        queued = self.orchestration_scheduler_service.process_run_request(
            run_id=run.id,
            worker_id="scheduler-bound-ingress-1",
        )

        self.assertIsNotNone(queued)
        assert queued is not None
        self.assertEqual(queued.status, OrchestrationRunStatus.QUEUED)
        self.assertEqual(queued.session_key, target.id)
        self.assertEqual(queued.active_session_id, target.active_session_id)
        self.assertEqual(queued.lane_key, f"session:{target.id}")

        with self.uow_factory() as uow:
            completed = uow.orchestration_ingress_requests.get_by_run_id(run.id)

        self.assertIsNotNone(completed)
        assert completed is not None
        self.assertEqual(completed.status.value, "completed")

    def test_executor_does_not_claim_pending_ingress_before_scheduler_processes_it(
        self,
    ) -> None:
        self._register_agent_and_llm()
        profile = self.agent_service.get_profile("assistant")
        options = build_submission_options(
            profile=profile,
            llm_id=None,
            channel="webhook",
            chat_type="direct",
            peer_id="user-ingress-no-claim",
            conversation_id=None,
            thread_id=None,
            account_id=None,
            main_key="main",
            direct_scope=DirectSessionScope.MAIN,
            source="webhook",
            queue_policy=OrchestrationQueuePolicy.JUMP_QUEUE,
            priority=50,
            max_steps=None,
        )
        run = self.orchestration_scheduler_service.submit_turn(
            SubmitOrchestrationTurnInput(
                accept_input=build_accept_run_input(
                    source=options.source,
                    content="hello pending ingress",
                    queue_policy=options.queue_policy,
                    priority=options.priority,
                    max_steps=options.max_steps,
                ),
                context=build_session_route_context(
                    agent_id=options.agent_id,
                    channel=options.channel,
                    chat_type=options.chat_type,
                    peer_id=options.peer_id,
                    conversation_id=options.conversation_id,
                    thread_id=options.thread_id,
                    account_id=options.account_id,
                    main_key=options.main_key,
                    direct_scope=options.direct_scope,
                ),
                requested_llm_id=options.llm_id,
                enqueue_queue_policy=options.queue_policy,
                enqueue_priority=options.priority,
            ),
            inline_worker_id=None,
        )

        self.assertEqual(run.status, OrchestrationRunStatus.ACCEPTED)
        self.assertIsNone(
            assign_next_orchestration_assignment(self.container,
                worker_id="worker-no-ingress-claim",
            )
        )

        queued = self.orchestration_scheduler_service.process_run_request(
            run_id=run.id,
            worker_id="scheduler-no-ingress-claim",
        )

        self.assertIsNotNone(queued)
        claimed = assign_next_orchestration_assignment(self.container,
            worker_id="worker-no-ingress-claim",
        )
        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.id, run.id)

    def test_scheduler_service_backfills_channel_interaction_binding_by_run_id(self) -> None:
        self._register_agent_and_llm()
        profile = self.agent_service.get_profile("assistant")
        options = build_submission_options(
            profile=profile,
            llm_id=None,
            channel="webhook",
            chat_type="direct",
            peer_id="user-bind-run-id-1",
            conversation_id="conv-bind-run-id-1",
            thread_id=None,
            account_id="default",
            main_key="main",
            direct_scope=DirectSessionScope.MAIN,
            source="webhook",
            queue_policy=OrchestrationQueuePolicy.JUMP_QUEUE,
            priority=100,
            max_steps=None,
        )
        run = submit_turn(
            self.orchestration_scheduler_service,
            content={"blocks": [{"type": "text", "text": "hello ingress callback"}]},
            options=options,
            inline_worker_id=None,
            reply_interface="webhook",
            reply_address="https://example.test/callback",
            reply_to="conv-bind-run-id-1",
            reply_metadata={
                "reply_address": {
                    "channel_type": "webhook",
                    "channel_account_id": "default",
                    "webhook_callback_url": "https://example.test/callback",
                    "external_conversation_id": "conv-bind-run-id-1",
                    "external_thread_id": None,
                    "external_user_id": "user-bind-run-id-1",
                    "route_hint": None,
                    "metadata": {},
                },
            },
        )

        interaction = self.channel_interaction_service.upsert_interaction(
            ChannelInteraction(
                interaction_id=f"webhook:default:run:{run.id}",
                channel_type="webhook",
                channel_account_id="default",
                external_conversation_id="conv-bind-run-id-1",
                external_user_id="user-bind-run-id-1",
                agent_id=profile.id,
                run_id=run.id,
                status=run.status.value,
                metadata={"source": "webhook"},
            ),
        )
        self.assertIsNone(interaction.session_key)
        self.assertEqual(interaction.status, "accepted")

        processed = self.orchestration_scheduler_service.process_run_request(
            run_id=run.id,
            worker_id="scheduler-bind-run-id-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.QUEUED)
        self.assertTrue(
            isinstance(processed.session_key, str) and processed.session_key.strip(),
        )

        rebound = self.channel_interaction_service.get_interaction_by_run_id(
            run.id,
        )
        self.assertIsNotNone(rebound)
        assert rebound is not None
        self.assertEqual(rebound.interaction_id, interaction.interaction_id)
        self.assertEqual(rebound.session_key, processed.session_key)
        self.assertEqual(rebound.agent_id, profile.id)
        self.assertEqual(rebound.status, "queued")
        self.assertEqual(
            rebound.metadata["active_session_id"],
            processed.active_session_id,
        )
        self.assertIn("observe_cursor", rebound.metadata)

    def test_complete_run_skips_web_legacy_runtime_topic_publication(self) -> None:
        self._register_agent_and_llm()
        self.channel_runtime_manager.register_runtime(
            ChannelRuntimeRegistration(
                runtime_id="web-runtime-1",
                channel_type="web",
                service_key="channel:web",
            ),
        )
        self.channel_runtime_manager.bind_account(
            ChannelAccountRuntimeBinding(
                channel_type="web",
                channel_account_id="default",
                runtime_id="web-runtime-1",
            ),
        )
        profile = self.agent_service.get_profile("assistant")
        options = build_submission_options(
            profile=profile,
            llm_id=None,
            channel="web",
            chat_type="direct",
            peer_id="web-user-1",
            conversation_id="agent:assistant:web:main",
            thread_id=None,
            account_id="default",
            main_key="main",
            direct_scope=DirectSessionScope.MAIN,
            source="web",
            queue_policy=OrchestrationQueuePolicy.JUMP_QUEUE,
            priority=100,
            max_steps=None,
        )
        run = submit_turn(
            self.orchestration_scheduler_service,
            content="hello from web",
            options=options,
            inline_worker_id="scheduler-inline",
            reply_interface="web",
            reply_address="conn-web-1",
            reply_to="conn-web-1",
            reply_metadata={
                "reply_address": {
                    "channel_type": "web",
                    "channel_account_id": "default",
                    "connection_id": "conn-web-1",
                    "metadata": {},
                },
            },
        )
        claimed = assign_next_orchestration_assignment(self.container,
            worker_id="worker-web-1",
        )
        self.assertIsNotNone(claimed)
        legacy_cursor = self.events_service.snapshot_event_topic(
            _legacy_runtime_outbound_topic("web-runtime-1"),
        )

        completed = self.orchestration_executor_service.complete_assignment(
            run_id=run.id,
            worker_id="worker-web-1",
            result_payload={"output_text": "done without web legacy runtime topic"},
        )

        self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
        legacy_records = self.events_service.read_event_topic(
            _legacy_runtime_outbound_topic("web-runtime-1"),
            after_cursor=legacy_cursor,
            limit=10,
        )
        self.assertEqual(legacy_records, ())

    def test_resume_first_queue_policy_claims_before_fifo_with_same_priority(self) -> None:
        waiting = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-resume-first",
                inbound_instruction=InboundInstruction(source="cli", content="resume me"),
                priority=10,
            ),
        )
        fifo = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-fifo",
                inbound_instruction=InboundInstruction(source="cli", content="fifo"),
                priority=10,
            ),
        )

        self.orchestration_intake_service.route(
            RouteOrchestrationRunInput(
                run_id=waiting.id,
                agent_id="writer",
                lane_key="session:resume",
            ),
        )
        self.orchestration_intake_service.route(
            RouteOrchestrationRunInput(
                run_id=fifo.id,
                agent_id="writer",
                lane_key="session:fifo",
            ),
        )

        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=waiting.id),
        )
        claimed = assign_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )
        assert claimed is not None
        self.orchestration_executor_service.wait_assignment_on_tool(
            run_id=waiting.id,
            worker_id="worker-1",
            pending_tool_run_ids=("tool-run-1",),
        )

        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=fifo.id),
        )
        resumed = self.orchestration_scheduler_service.resume_run(
            ResumeOrchestrationRunInput(
                run_id=waiting.id,
                queue_policy=OrchestrationQueuePolicy.RESUME_FIRST,
                reason="tool_results_ready",
            ),
        )
        next_claimed = assign_next_orchestration_assignment(self.container,
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
        fifo = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-fifo",
                inbound_instruction=InboundInstruction(source="cli", content="fifo"),
                priority=10,
            ),
        )
        jump_queue = self.orchestration_intake_service.accept(
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

        self.orchestration_intake_service.route(
            RouteOrchestrationRunInput(
                run_id=fifo.id,
                agent_id="writer",
                lane_key="session:fifo",
            ),
        )
        self.orchestration_intake_service.route(
            RouteOrchestrationRunInput(
                run_id=jump_queue.id,
                agent_id="writer",
                lane_key="session:jump",
            ),
        )

        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=fifo.id),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=jump_queue.id),
        )

        claimed = assign_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.id, jump_queue.id)

    def test_resume_first_claims_before_jump_queue_with_same_priority(self) -> None:
        resume_first = self.orchestration_intake_service.accept(
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
        jump_queue = self.orchestration_intake_service.accept(
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

        self.orchestration_intake_service.route(
            RouteOrchestrationRunInput(
                run_id=resume_first.id,
                agent_id="writer",
                lane_key="session:resume-first",
            ),
        )
        self.orchestration_intake_service.route(
            RouteOrchestrationRunInput(
                run_id=jump_queue.id,
                agent_id="writer",
                lane_key="session:jump-queue",
            ),
        )

        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=jump_queue.id),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=resume_first.id),
        )

        claimed = assign_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.id, resume_first.id)

    def test_lane_jump_queue_claims_before_fifo_with_same_priority_in_same_lane(self) -> None:
        fifo = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-lane-fifo",
                inbound_instruction=InboundInstruction(source="cli", content="fifo"),
                priority=10,
            ),
        )
        lane_jump_queue = self.orchestration_intake_service.accept(
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

        self.orchestration_intake_service.route(
            RouteOrchestrationRunInput(
                run_id=fifo.id,
                agent_id="writer",
                lane_key="session:lane-shared",
            ),
        )
        self.orchestration_intake_service.route(
            RouteOrchestrationRunInput(
                run_id=lane_jump_queue.id,
                agent_id="writer",
                lane_key="session:lane-shared",
            ),
        )

        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=fifo.id),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=lane_jump_queue.id),
        )

        claimed = assign_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.id, lane_jump_queue.id)

    def test_lane_jump_queue_does_not_jump_ahead_of_other_lane_heads(self) -> None:
        other_lane_fifo = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-other-lane-fifo",
                inbound_instruction=InboundInstruction(
                    source="cli",
                    content="other lane fifo",
                ),
                priority=10,
            ),
        )
        same_lane_fifo = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-shared-lane-fifo",
                inbound_instruction=InboundInstruction(
                    source="cli",
                    content="shared lane fifo",
                ),
                priority=10,
            ),
        )
        lane_jump_queue = self.orchestration_intake_service.accept(
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

        self.orchestration_intake_service.route(
            RouteOrchestrationRunInput(
                run_id=other_lane_fifo.id,
                agent_id="writer",
                lane_key="session:lane-a",
            ),
        )
        self.orchestration_intake_service.route(
            RouteOrchestrationRunInput(
                run_id=same_lane_fifo.id,
                agent_id="writer",
                lane_key="session:lane-b",
            ),
        )
        self.orchestration_intake_service.route(
            RouteOrchestrationRunInput(
                run_id=lane_jump_queue.id,
                agent_id="writer",
                lane_key="session:lane-b",
            ),
        )

        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=other_lane_fifo.id),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=same_lane_fifo.id),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=lane_jump_queue.id),
        )

        claimed = assign_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.id, other_lane_fifo.id)

    def test_waiting_run_can_fail_without_reclaim(self) -> None:
        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-fail",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )
        claimed = assign_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )
        assert claimed is not None
        self.orchestration_executor_service.wait_assignment_on_tool(
            run_id=run.id,
            worker_id="worker-1",
            pending_tool_run_ids=("tool-run-1",),
        )

        failed = self.orchestration_executor_service.fail_assignment(
            run_id=run.id,
            worker_id=None,
            message="tool background failed",
            code="tool_failed",
            details={"tool_run_id": "tool-run-1"},
        )

        self.assertEqual(failed.status, OrchestrationRunStatus.FAILED)
        self.assertEqual(failed.stage, OrchestrationRunStage.FAILED)
        assert failed.error is not None
        self.assertEqual(failed.error.code, "tool_failed")
        self.assertEqual(
            failed.error.details["tool_run_id"],
            "tool-run-1",
        )

    def test_orchestration_resolves_session_bundle_via_session_resolution_service(self) -> None:
        bundle = self.session_resolution_service.resolve(
            ResolveSessionInput(
                context=SessionRouteContext(
                    agent_id="assistant",
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
            session_lane_key(bundle.routing.key_resolution.key),
            "session:agent:assistant:main",
        )
        self.assertTrue(bundle.resolution.resolution.created)
        self.assertIsNotNone(bundle.session)
        self.assertIsNotNone(bundle.active_instance)
        assert bundle.session is not None
        assert bundle.active_instance is not None
        self.assertEqual(bundle.session.id, "agent:assistant:main")
        self.assertEqual(bundle.active_instance.kind.value, "main")

    def test_cancel_run_keeps_it_out_of_queue(self) -> None:
        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-cancel",
                inbound_instruction=InboundInstruction(source="http", content="stop"),
            ),
        )
        self.orchestration_intake_service.route(
            RouteOrchestrationRunInput(
                run_id=run.id,
                agent_id="writer",
                lane_key="session:cancel",
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        cancelled = self.orchestration_cancellation_service.cancel_run(
            run.id,
            reason="user_cancelled",
        )
        claimed = assign_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )

        self.assertEqual(cancelled.status, OrchestrationRunStatus.CANCELLED)
        self.assertEqual(cancelled.stage, OrchestrationRunStage.CANCELLED)
        self.assertIsNone(claimed)
