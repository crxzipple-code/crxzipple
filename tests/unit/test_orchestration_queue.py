from __future__ import annotations

from tests.unit.orchestration_test_support import *  # noqa: F403


class OrchestrationQueueTestCase(OrchestrationTestCaseBase):
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
        self.assertEqual(claimed.session_key, "agent:writer:main")
        self.assertTrue(claimed.active_session_id)
        self.assertIsNotNone(claimed.started_at)
        self.assertEqual(claimed.metadata["session_key"], "agent:writer:main")
        self.assertEqual(claimed.metadata["session_kind"], "main")
        dispatch_task = self.container.dispatch_service.get_task(run.id)
        self.assertEqual(dispatch_task.status, DispatchTaskStatus.CLAIMED)
        self.assertEqual(dispatch_task.policy, DispatchPolicy.FIFO)
        self.assertEqual(dispatch_task.claimed_by, "worker-1")
        self.assertIsNotNone(dispatch_task.lease_expires_at)

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
                lane_key="session:one",
            ),
        )
        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=high_priority.id,
                agent_id="writer",
                lane_key="session:two",
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
                lane_key="session:lane-a",
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
                lane_key="session:lane-a",
            ),
        )
        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=available.id,
                agent_id="writer",
                lane_key="session:lane-b",
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
                lane_key="session:lane-wait",
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
                lane_key="session:lane-wait",
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
                lane_key="session:resume",
            ),
        )
        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=fifo.id,
                agent_id="writer",
                lane_key="session:fifo",
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
                lane_key="session:fifo",
            ),
        )
        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=jump_queue.id,
                agent_id="writer",
                lane_key="session:jump",
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
                lane_key="session:resume-first",
            ),
        )
        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=jump_queue.id,
                agent_id="writer",
                lane_key="session:jump-queue",
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
                lane_key="session:lane-shared",
            ),
        )
        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=lane_jump_queue.id,
                agent_id="writer",
                lane_key="session:lane-shared",
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
                lane_key="session:lane-a",
            ),
        )
        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=same_lane_fifo.id,
                agent_id="writer",
                lane_key="session:lane-b",
            ),
        )
        self.container.orchestration_service.route(
            RouteOrchestrationRunInput(
                run_id=lane_jump_queue.id,
                agent_id="writer",
                lane_key="session:lane-b",
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
            bundle.routing.lane_key,
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
                lane_key="session:cancel",
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

