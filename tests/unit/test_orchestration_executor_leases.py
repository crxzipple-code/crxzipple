from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

from crxzipple.modules.orchestration.application import (
    orchestration_executor_assignment_requested_topic,
)
from crxzipple.modules.orchestration.application.dispatch_owner_kinds import (
    ORCHESTRATION_STEP_DISPATCH_OWNER_KIND,
)
from crxzipple.modules.orchestration.application.lease_manager import (
    OrchestrationLeaseManager,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationExecutorLeaseStatus,
    OrchestrationRunStatus,
)
from crxzipple.shared.domain.events import named_event_topic
from tests.unit.orchestration_test_support import *  # noqa: F403


def _latest_dispatch_task_id(orchestration_run_query_service, run_id: str) -> str:
    chain = orchestration_run_query_service.get_active_execution_chain(run_id)
    if chain is None:
        chains = orchestration_run_query_service.list_execution_chains(run_id)
        assert chains
        chain = chains[-1]
    for step in reversed(orchestration_run_query_service.list_execution_steps(chain.id)):
        if step.dispatch_task_id is not None and step.dispatch_task_id.strip():
            return step.dispatch_task_id
    raise AssertionError(f"Run '{run_id}' has no dispatch execution step.")


class OrchestrationExecutorLeaseTestCase(OrchestrationTestCaseBase):
    def _queue_run(
        self,
        *,
        run_id: str,
        lane_key: str,
        priority: int = 10,
    ):
        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id=run_id,
                inbound_instruction=InboundInstruction(source="cli", content=run_id),
                priority=priority,
            ),
        )
        self.orchestration_intake_service.route(
            RouteOrchestrationRunInput(
                run_id=run.id,
                agent_id="assistant",
                lane_key=lane_key,
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )
        return run

    def _queue_session_run(
        self,
        *,
        run_id: str,
        channel: str = "webchat",
        direct_scope: DirectSessionScope = DirectSessionScope.MAIN,
        peer_id: str | None = None,
    ):
        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id=run_id,
                inbound_instruction=InboundInstruction(source="cli", content=run_id),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel=channel,
                    direct_scope=direct_scope,
                    peer_id=peer_id,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )
        return run

    def test_executor_heartbeat_registers_and_updates_shared_lease(self) -> None:
        lease = self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-1",
            max_inflight_assignments=4,
            inflight_assignment_count=1,
            metadata={"pool": "io"},
        )

        self.assertEqual(lease.worker_id, "executor-1")
        self.assertEqual(lease.status, OrchestrationExecutorLeaseStatus.ONLINE)
        self.assertEqual(lease.max_inflight_assignments, 4)
        self.assertEqual(lease.inflight_assignment_count, 1)
        self.assertEqual(lease.metadata, {"pool": "io"})
        self.assertIsNotNone(lease.lease_expires_at)

        updated = self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-1",
            max_inflight_assignments=8,
            inflight_assignment_count=2,
            draining=True,
            metadata={"region": "local"},
        )

        self.assertEqual(updated.worker_id, "executor-1")
        self.assertEqual(updated.status, OrchestrationExecutorLeaseStatus.DRAINING)
        self.assertEqual(updated.max_inflight_assignments, 8)
        self.assertEqual(updated.inflight_assignment_count, 2)
        self.assertEqual(updated.metadata, {"pool": "io", "region": "local"})
        self.assertGreaterEqual(updated.updated_at, lease.updated_at)

        draining = self.orchestration_executor_service.list_executor_leases(
            status=OrchestrationExecutorLeaseStatus.DRAINING,
        )
        self.assertEqual([item.worker_id for item in draining], ["executor-1"])

        with self.uow_factory() as uow:
            persisted = uow.orchestration_executor_leases.get("executor-1")
        self.assertIsNotNone(persisted)
        assert persisted is not None
        self.assertEqual(persisted.status, OrchestrationExecutorLeaseStatus.DRAINING)

        self.publish_outbox_events()
        heartbeat_records = self.events_service.read_recent_event_topic(
            named_event_topic("orchestration.executor.lease.heartbeated"),
            limit=5,
        )
        self.assertTrue(
            any(
                record.envelope.payload.get("worker_id") == "executor-1"
                for record in heartbeat_records
            ),
        )

    def test_executor_heartbeat_rejects_inflight_above_capacity(self) -> None:
        with self.assertRaises(OrchestrationValidationError):
            self.orchestration_executor_service.heartbeat_executor(
                worker_id="executor-invalid",
                max_inflight_assignments=1,
                inflight_assignment_count=2,
            )

    def test_executor_loop_reports_lease_even_when_idle(self) -> None:
        processed = self.orchestration_executor_service.run_until_stopped(
            worker_id="executor-loop-1",
            poll_interval_seconds=0.01,
            max_idle_cycles=1,
        )

        self.assertEqual(processed, 0)
        leases = self.orchestration_executor_service.list_executor_leases()
        self.assertEqual([item.worker_id for item in leases], ["executor-loop-1"])
        self.assertEqual(leases[0].inflight_assignment_count, 0)
        self.assertEqual(
            leases[0].metadata["runtime_state"]["active_assignment_count"],
            0,
        )
        self.assertIn("runtime_metrics", leases[0].metadata)

    def test_executor_async_loop_reports_lease_even_when_idle(self) -> None:
        async def _run() -> int:
            return await self.orchestration_executor_service.run_until_stopped_async(
                worker_id="executor-async-loop-1",
                poll_interval_seconds=0.01,
                max_idle_cycles=1,
            )

        processed = asyncio.run(_run())

        self.assertEqual(processed, 0)
        leases = self.orchestration_executor_service.list_executor_leases()
        self.assertEqual([item.worker_id for item in leases], ["executor-async-loop-1"])
        self.assertEqual(
            leases[0].metadata["runtime_state"]["max_concurrent_assignments"],
            1,
        )

    def test_heartbeat_while_processing_supports_keyword_only_callback(self) -> None:
        lease_manager = OrchestrationLeaseManager(
            uow_factory=lambda: None,
            dispatch_port=SimpleNamespace(),
            worker_lease_seconds=30,
            worker_heartbeat_seconds=0.01,
        )
        calls: list[tuple[str, str]] = []

        def heartbeat_assignment(
            *,
            run_id: str,
            worker_id: str,
        ) -> SimpleNamespace:
            calls.append((run_id, worker_id))
            return SimpleNamespace(status=OrchestrationRunStatus.RUNNING)

        with lease_manager.heartbeat_while_processing(
            run_id="run-keyword-heartbeat",
            worker_id="worker-keyword-heartbeat",
            heartbeat_assignment=heartbeat_assignment,
        ):
            time.sleep(0.04)

        self.assertGreaterEqual(len(calls), 1)
        self.assertEqual(
            calls[0],
            ("run-keyword-heartbeat", "worker-keyword-heartbeat"),
        )

    def test_executor_async_loop_revives_draining_lease_to_online(self) -> None:
        self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-async-revive-1",
            max_inflight_assignments=2,
            inflight_assignment_count=0,
            draining=True,
        )

        async def _run() -> int:
            return await self.orchestration_executor_service.run_until_stopped_async(
                worker_id="executor-async-revive-1",
                poll_interval_seconds=0.01,
                max_idle_cycles=1,
                max_concurrent_assignments=2,
            )

        processed = asyncio.run(_run())

        self.assertEqual(processed, 0)
        [lease] = self.orchestration_executor_service.list_executor_leases()
        self.assertEqual(lease.worker_id, "executor-async-revive-1")
        self.assertEqual(lease.status, OrchestrationExecutorLeaseStatus.ONLINE)
        self.assertEqual(lease.max_inflight_assignments, 2)

    def test_executor_sync_loop_rejects_nested_asyncio_loop(self) -> None:
        async def _run_sync_from_async() -> None:
            self.orchestration_executor_service.run_until_stopped(
                worker_id="executor-nested-loop",
                poll_interval_seconds=0.01,
                max_idle_cycles=1,
            )

        with self.assertRaisesRegex(
            OrchestrationValidationError,
            "run_until_stopped_async",
        ):
            asyncio.run(_run_sync_from_async())

    def test_executor_available_path_does_not_claim_unassigned_queue(self) -> None:
        self._queue_run(run_id="run-unassigned-loop-1", lane_key="session:unassigned-1")
        self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-unassigned-1",
            max_inflight_assignments=1,
            inflight_assignment_count=0,
        )

        processed = self.orchestration_executor_service.process_next_available(
            worker_id="executor-unassigned-1",
        )

        self.assertIsNone(processed)
        run = self.orchestration_run_query_service.get_run("run-unassigned-loop-1")
        self.assertEqual(run.status, OrchestrationRunStatus.QUEUED)

    def test_scheduler_assign_next_assignment_respects_executor_capacity(self) -> None:
        self._queue_run(run_id="run-capacity-1", lane_key="session:capacity-1")
        self._queue_run(run_id="run-capacity-2", lane_key="session:capacity-2")
        self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-capacity-1",
            max_inflight_assignments=1,
            inflight_assignment_count=0,
        )

        first = assign_next_orchestration_assignment(self.container,
            worker_id="executor-capacity-1",
        )
        blocked = assign_next_orchestration_assignment(self.container,
            worker_id="executor-capacity-1",
        )

        self.assertIsNotNone(first)
        self.assertIsNone(blocked)
        leases = self.orchestration_executor_service.list_executor_leases()
        self.assertEqual(leases[0].inflight_assignment_count, 1)

        self.orchestration_executor_service.complete_assignment(
            run_id="run-capacity-1",
            worker_id="executor-capacity-1",
            result_payload={"output": "done"},
        )
        released = self.orchestration_executor_service.list_executor_leases()[0]
        self.assertEqual(released.inflight_assignment_count, 0)

        second = assign_next_orchestration_assignment(self.container,
            worker_id="executor-capacity-1",
        )
        self.assertIsNotNone(second)
        assert second is not None
        self.assertEqual(second.id, "run-capacity-2")

    def test_executor_capacity_claim_is_atomic_guard(self) -> None:
        self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-atomic-capacity",
            max_inflight_assignments=1,
            inflight_assignment_count=0,
        )

        with self.uow_factory() as uow:
            first = uow.orchestration_executor_leases.claim_assignment_capacity(
                worker_id="executor-atomic-capacity",
                lease_seconds=30,
            )
            self.assertIsNotNone(first)
            assert first is not None
            uow.collect(first)
            uow.commit()

        with self.uow_factory() as uow:
            second = uow.orchestration_executor_leases.claim_assignment_capacity(
                worker_id="executor-atomic-capacity",
                lease_seconds=30,
            )

        self.assertIsNone(second)
        lease = self.orchestration_executor_service.list_executor_leases()[0]
        self.assertEqual(lease.inflight_assignment_count, 1)
        self.assertEqual(lease.max_inflight_assignments, 1)

    def test_executor_heartbeat_without_inflight_preserves_claimed_capacity(self) -> None:
        self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-heartbeat-preserve",
            max_inflight_assignments=2,
            inflight_assignment_count=0,
        )
        with self.uow_factory() as uow:
            claimed = uow.orchestration_executor_leases.claim_assignment_capacity(
                worker_id="executor-heartbeat-preserve",
                lease_seconds=30,
            )
            assert claimed is not None
            uow.collect(claimed)
            uow.commit()

        heartbeated = self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-heartbeat-preserve",
            max_inflight_assignments=4,
            inflight_assignment_count=None,
        )

        self.assertEqual(heartbeated.max_inflight_assignments, 4)
        self.assertEqual(heartbeated.inflight_assignment_count, 1)

    def test_expired_online_executor_lease_reports_effective_offline(self) -> None:
        self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-effective-expired",
            max_inflight_assignments=3,
            inflight_assignment_count=1,
        )
        with self.uow_factory() as uow:
            lease = uow.orchestration_executor_leases.get("executor-effective-expired")
            assert lease is not None
            lease.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            uow.orchestration_executor_leases.add(lease)
            uow.collect(lease)
            uow.commit()

        [expired] = self.orchestration_executor_service.list_executor_leases()

        self.assertEqual(expired.status, OrchestrationExecutorLeaseStatus.ONLINE)
        self.assertTrue(expired.is_expired())
        self.assertEqual(
            expired.effective_status(),
            OrchestrationExecutorLeaseStatus.OFFLINE,
        )
        self.assertFalse(expired.counts_toward_capacity())
        self.assertEqual(expired.available_assignment_slots(), 0)
        self.assertFalse(expired.can_accept_assignment)

    def test_recover_abandoned_runs_marks_expired_executor_offline(self) -> None:
        self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-expired-offline",
            max_inflight_assignments=2,
            inflight_assignment_count=0,
        )
        with self.uow_factory() as uow:
            lease = uow.orchestration_executor_leases.get("executor-expired-offline")
            assert lease is not None
            lease.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            uow.orchestration_executor_leases.add(lease)
            uow.collect(lease)
            uow.commit()

        recovered = self.orchestration_scheduler_service.recover_abandoned_runs()

        self.assertEqual(recovered, [])
        [offline] = self.orchestration_executor_service.list_executor_leases()
        self.assertEqual(offline.status, OrchestrationExecutorLeaseStatus.OFFLINE)

    def test_scheduler_expire_executor_leases_marks_expired_online_offline(self) -> None:
        self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-expire-command",
            max_inflight_assignments=2,
            inflight_assignment_count=0,
        )
        with self.uow_factory() as uow:
            lease = uow.orchestration_executor_leases.get("executor-expire-command")
            assert lease is not None
            lease.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            uow.orchestration_executor_leases.add(lease)
            uow.collect(lease)
            uow.commit()

        expired = self.orchestration_scheduler_service.expire_executor_leases()

        self.assertEqual([item.worker_id for item in expired], ["executor-expire-command"])
        [offline] = self.orchestration_executor_service.list_executor_leases()
        self.assertEqual(offline.status, OrchestrationExecutorLeaseStatus.OFFLINE)

    def test_executor_heartbeat_revives_offline_executor(self) -> None:
        self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-offline-revive",
            max_inflight_assignments=2,
            inflight_assignment_count=0,
        )
        with self.uow_factory() as uow:
            lease = uow.orchestration_executor_leases.get("executor-offline-revive")
            assert lease is not None
            lease.mark_offline()
            uow.orchestration_executor_leases.add(lease)
            uow.collect(lease)
            uow.commit()

        revived = self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-offline-revive",
            max_inflight_assignments=4,
            inflight_assignment_count=None,
        )

        self.assertEqual(revived.status, OrchestrationExecutorLeaseStatus.ONLINE)
        self.assertEqual(revived.max_inflight_assignments, 4)
        self.assertEqual(revived.inflight_assignment_count, 0)

    def test_recovered_running_assignment_requeues_and_releases_executor_capacity(self) -> None:
        self._queue_run(run_id="run-recovered-capacity", lane_key="session:recover-capacity")
        self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-recovered-capacity",
            max_inflight_assignments=1,
            inflight_assignment_count=0,
        )
        claimed = assign_next_orchestration_assignment(self.container,
            worker_id="executor-recovered-capacity",
        )
        self.assertIsNotNone(claimed)
        lease = self.orchestration_executor_service.list_executor_leases()[0]
        self.assertEqual(lease.inflight_assignment_count, 1)
        dispatch_task_id = _latest_dispatch_task_id(
            self.orchestration_run_query_service,
            "run-recovered-capacity",
        )
        task = self.dispatch_service.get_task(dispatch_task_id)
        assert task.lease_expires_at is not None

        recovered = self.dispatch_service.recover_abandoned_tasks(
            RecoverAbandonedDispatchTasksInput(
                owner_kind=ORCHESTRATION_STEP_DISPATCH_OWNER_KIND,
                reason="Orchestration worker lease expired before completion.",
                now=task.lease_expires_at + timedelta(seconds=1),
            ),
        )
        self.assertEqual([item.id for item in recovered], [dispatch_task_id])
        self.publish_outbox_events()
        self.orchestration_scheduler_service.process_runtime_events(
            limit_per_subscription=10,
        )

        recovered_run = self.orchestration_run_query_service.get_run(
            "run-recovered-capacity",
        )
        released = self.orchestration_executor_service.list_executor_leases()[0]
        self.assertEqual(recovered_run.status, OrchestrationRunStatus.QUEUED)
        self.assertIsNone(recovered_run.worker_id)
        self.assertEqual(released.inflight_assignment_count, 0)

    def test_recovered_running_assignment_requeues_claimed_dispatch_task(self) -> None:
        self._queue_run(
            run_id="run-recovered-dispatch-task",
            lane_key="session:recover-dispatch-task",
        )
        self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-recovered-dispatch-task",
            max_inflight_assignments=1,
            inflight_assignment_count=0,
        )
        claimed = assign_next_orchestration_assignment(
            self.container,
            worker_id="executor-recovered-dispatch-task",
        )
        self.assertIsNotNone(claimed)
        dispatch_task_id = _latest_dispatch_task_id(
            self.orchestration_run_query_service,
            "run-recovered-dispatch-task",
        )
        claimed_task = self.dispatch_service.get_task(dispatch_task_id)
        self.assertEqual(claimed_task.status, DispatchTaskStatus.CLAIMED)

        recovered = self.orchestration_scheduler_service.handle_recovered_dispatch_task(
            dispatch_task_id=dispatch_task_id,
            reason="lease expired in test",
        )

        assert recovered is not None
        recovered_task = self.dispatch_service.get_task(dispatch_task_id)
        released = self.orchestration_executor_service.list_executor_leases()[0]
        self.assertEqual(recovered.status, OrchestrationRunStatus.QUEUED)
        self.assertIsNone(recovered.worker_id)
        self.assertEqual(recovered_task.status, DispatchTaskStatus.QUEUED)
        self.assertIsNone(recovered_task.claimed_by)
        self.assertIsNone(recovered_task.lease_expires_at)
        self.assertEqual(released.inflight_assignment_count, 0)

    def test_control_cancel_running_assignment_releases_executor_capacity(self) -> None:
        self._queue_run(run_id="run-cancel-capacity", lane_key="session:cancel-capacity")
        self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-cancel-capacity",
            max_inflight_assignments=1,
            inflight_assignment_count=0,
        )
        claimed = assign_next_orchestration_assignment(self.container,
            worker_id="executor-cancel-capacity",
        )
        self.assertIsNotNone(claimed)

        cancelled = self.orchestration_cancellation_service.cancel_run(
            "run-cancel-capacity",
            reason="test_cancel",
        )

        released = self.orchestration_executor_service.list_executor_leases()[0]
        self.assertEqual(cancelled.status, OrchestrationRunStatus.CANCELLED)
        self.assertEqual(released.inflight_assignment_count, 0)

    def test_fail_without_worker_id_releases_original_executor_capacity(self) -> None:
        self._queue_run(run_id="run-fail-capacity", lane_key="session:fail-capacity")
        self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-fail-capacity",
            max_inflight_assignments=1,
            inflight_assignment_count=0,
        )
        claimed = assign_next_orchestration_assignment(self.container,
            worker_id="executor-fail-capacity",
        )
        self.assertIsNotNone(claimed)

        failed = self.orchestration_executor_service.fail_assignment(
            run_id="run-fail-capacity",
            message="failed by controller",
            code="controller_failure",
            worker_id=None,
        )

        released = self.orchestration_executor_service.list_executor_leases()[0]
        self.assertEqual(failed.status, OrchestrationRunStatus.FAILED)
        self.assertEqual(released.inflight_assignment_count, 0)

    def test_draining_executor_does_not_claim_new_assignments(self) -> None:
        self._queue_run(run_id="run-draining-1", lane_key="session:draining-1")
        self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-draining-1",
            max_inflight_assignments=2,
            inflight_assignment_count=0,
            draining=True,
        )

        blocked = assign_next_orchestration_assignment(self.container,
            worker_id="executor-draining-1",
        )
        self.assertIsNone(blocked)

        self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-draining-1",
            draining=False,
        )
        claimed = assign_next_orchestration_assignment(self.container,
            worker_id="executor-draining-1",
        )
        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.id, "run-draining-1")

    def test_scheduler_assigns_next_assignment_to_available_executor(self) -> None:
        self._queue_run(run_id="run-scheduler-assign-1", lane_key="session:assign-1")
        self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-scheduler-1",
            max_inflight_assignments=2,
            inflight_assignment_count=0,
        )

        assigned = self.orchestration_scheduler_service.assign_next_assignment()

        self.assertIsNotNone(assigned)
        assert assigned is not None
        self.assertEqual(assigned.id, "run-scheduler-assign-1")
        self.assertEqual(assigned.status, OrchestrationRunStatus.RUNNING)
        self.assertEqual(assigned.worker_id, "executor-scheduler-1")
        lease = self.orchestration_executor_service.list_executor_leases()[0]
        self.assertEqual(lease.inflight_assignment_count, 1)

    def test_scheduler_async_runtime_assigns_available_work(self) -> None:
        self._queue_run(run_id="run-scheduler-async-1", lane_key="session:async-1")
        self._queue_run(run_id="run-scheduler-async-2", lane_key="session:async-2")
        self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-scheduler-async",
            max_inflight_assignments=2,
            inflight_assignment_count=0,
        )

        processed = asyncio.run(
            self.orchestration_scheduler_service.run_until_stopped_async(
                worker_id="scheduler-async",
                poll_interval_seconds=0.01,
                max_runs=2,
                max_idle_cycles=1,
            ),
        )

        first = self.orchestration_run_query_service.get_run(
            "run-scheduler-async-1",
        )
        second = self.orchestration_run_query_service.get_run(
            "run-scheduler-async-2",
        )
        lease = self.orchestration_executor_service.list_executor_leases()[0]
        self.assertEqual(processed, 2)
        self.assertEqual(first.status, OrchestrationRunStatus.RUNNING)
        self.assertEqual(second.status, OrchestrationRunStatus.RUNNING)
        self.assertEqual(first.worker_id, "executor-scheduler-async")
        self.assertEqual(second.worker_id, "executor-scheduler-async")
        self.assertEqual(lease.inflight_assignment_count, 2)

    def test_scheduler_assignment_publishes_executor_wakeup(self) -> None:
        self._queue_run(run_id="run-scheduler-wakeup-1", lane_key="session:wakeup-1")
        self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-scheduler-wakeup",
            max_inflight_assignments=1,
            inflight_assignment_count=0,
        )
        topic = orchestration_executor_assignment_requested_topic()
        cursor = self.events_service.snapshot_event_topic(topic)

        assigned = self.orchestration_scheduler_service.assign_next_assignment()

        self.assertIsNotNone(assigned)
        records = self.events_service.read_event_topic(
            topic,
            after_cursor=cursor,
            limit=10,
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].envelope.payload["run_id"], "run-scheduler-wakeup-1")
        self.assertEqual(
            records[0].envelope.payload["worker_id"],
            "executor-scheduler-wakeup",
        )

    def test_scheduler_skips_draining_executor_when_assigning(self) -> None:
        self._queue_run(run_id="run-scheduler-draining-1", lane_key="session:assign-2")
        self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-scheduler-draining",
            max_inflight_assignments=2,
            inflight_assignment_count=0,
            draining=True,
        )
        self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-scheduler-online",
            max_inflight_assignments=2,
            inflight_assignment_count=0,
        )

        assigned = self.orchestration_scheduler_service.assign_next_assignment()

        self.assertIsNotNone(assigned)
        assert assigned is not None
        self.assertEqual(assigned.worker_id, "executor-scheduler-online")

    def test_scheduler_skips_expired_executor_when_assigning(self) -> None:
        self._queue_run(run_id="run-scheduler-expired-1", lane_key="session:assign-3")
        self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-scheduler-expired",
            max_inflight_assignments=2,
            inflight_assignment_count=0,
        )
        self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-scheduler-fresh",
            max_inflight_assignments=2,
            inflight_assignment_count=0,
        )
        with self.uow_factory() as uow:
            expired = uow.orchestration_executor_leases.get("executor-scheduler-expired")
            assert expired is not None
            expired.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            uow.orchestration_executor_leases.add(expired)
            uow.collect(expired)
            uow.commit()

        assigned = self.orchestration_scheduler_service.assign_next_assignment()

        self.assertIsNotNone(assigned)
        assert assigned is not None
        self.assertEqual(assigned.worker_id, "executor-scheduler-fresh")

    def test_scheduler_uses_orchestration_run_state_for_lane_blocking(self) -> None:
        self._queue_run(
            run_id="run-scheduler-lane-active",
            lane_key="session:scheduler-lane",
            priority=10,
        )
        self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-scheduler-lane",
            max_inflight_assignments=2,
            inflight_assignment_count=0,
        )
        active = self.orchestration_scheduler_service.assign_next_assignment()
        self.assertIsNotNone(active)
        assert active is not None
        self.assertEqual(active.id, "run-scheduler-lane-active")

        dispatch_task_id = _latest_dispatch_task_id(
            self.orchestration_run_query_service,
            active.id,
        )
        with self.uow_factory() as uow:
            task = uow.dispatch_tasks.get(dispatch_task_id)
            assert task is not None
            task.complete(now=datetime.now(timezone.utc))
            uow.dispatch_tasks.add(task)
            uow.collect(task)
            uow.commit()

        self._queue_run(
            run_id="run-scheduler-lane-blocked",
            lane_key="session:scheduler-lane",
            priority=1,
        )
        self._queue_run(
            run_id="run-scheduler-lane-open",
            lane_key="session:scheduler-open",
            priority=50,
        )

        assigned = self.orchestration_scheduler_service.assign_next_assignment()

        self.assertIsNotNone(assigned)
        assert assigned is not None
        self.assertEqual(assigned.id, "run-scheduler-lane-open")

    def test_run_assignment_claim_enforces_active_lane_guard(self) -> None:
        self._queue_run(
            run_id="run-atomic-lane-active",
            lane_key="session:atomic-lane",
            priority=10,
        )
        self._queue_run(
            run_id="run-atomic-lane-blocked",
            lane_key="session:atomic-lane",
            priority=20,
        )

        with self.uow_factory() as uow:
            active = uow.orchestration_runs.claim_queued_for_assignment(
                run_id="run-atomic-lane-active",
                worker_id="executor-atomic-lane-1",
            )
            self.assertIsNotNone(active)
            assert active is not None
            active.claim(
                worker_id="executor-atomic-lane-1",
                claimed_at=active.started_at,
            )
            uow.orchestration_runs.add(active)
            uow.collect(active)
            uow.commit()

        with self.uow_factory() as uow:
            blocked = uow.orchestration_runs.claim_queued_for_assignment(
                run_id="run-atomic-lane-blocked",
                worker_id="executor-atomic-lane-2",
            )

        self.assertIsNone(blocked)
        still_queued = self.orchestration_run_query_service.get_run(
            "run-atomic-lane-blocked",
        )
        self.assertEqual(still_queued.status, OrchestrationRunStatus.QUEUED)

    def test_executor_processes_scheduler_assigned_assignment(self) -> None:
        adapter = _StaticTextAdapter(text="assigned execution complete")
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()
        self._queue_session_run(run_id="run-assigned-process-1")
        self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-assigned-process",
            max_inflight_assignments=1,
            inflight_assignment_count=0,
        )
        assigned = self.orchestration_scheduler_service.assign_next_assignment()
        self.assertIsNotNone(assigned)
        assert assigned is not None
        self.assertEqual(assigned.worker_id, "executor-assigned-process")

        processed = (
            self.orchestration_executor_service.process_next_assigned_assignment(
                worker_id="executor-assigned-process",
            )
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.id, "run-assigned-process-1")
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        self.assertIsNotNone(processed.result_payload)
        assert processed.result_payload is not None
        self.assertEqual(
            processed.result_payload["output_text"],
            "assigned execution complete",
        )
        lease = self.orchestration_executor_service.list_executor_leases()[0]
        self.assertEqual(lease.inflight_assignment_count, 0)

    def test_executor_loop_processes_scheduler_assigned_assignment(self) -> None:
        adapter = _StaticTextAdapter(text="assigned loop complete")
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()
        self._queue_session_run(run_id="run-assigned-loop-1")
        self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-assigned-loop",
            max_inflight_assignments=1,
            inflight_assignment_count=0,
        )
        assigned = self.orchestration_scheduler_service.assign_next_assignment()
        self.assertIsNotNone(assigned)

        processed_count = self.orchestration_executor_service.run_until_stopped(
            worker_id="executor-assigned-loop",
            poll_interval_seconds=0.01,
            max_runs=1,
        )

        self.assertEqual(processed_count, 1)
        run = self.orchestration_run_query_service.get_run("run-assigned-loop-1")
        self.assertEqual(run.status, OrchestrationRunStatus.COMPLETED)
        assert run.result_payload is not None
        self.assertEqual(run.result_payload["output_text"], "assigned loop complete")

    def test_executor_loop_processes_multiple_assigned_runs(self) -> None:
        class _CountingAdapter:
            def __init__(self) -> None:
                self._lock = threading.Lock()
                self._entered = 0

            @property
            def invocation_count(self) -> int:
                return self._entered

            def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
                del request
                with self._lock:
                    self._entered += 1
                return LlmAdapterResponse(result=LlmResult(text="concurrent complete"))

        adapter = _CountingAdapter()
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()
        self._queue_session_run(
            run_id="run-concurrent-assigned-1",
            channel="webchat-concurrent-1",
            direct_scope=DirectSessionScope.PER_CHANNEL_PEER,
            peer_id="peer-concurrent-1",
        )
        self._queue_session_run(
            run_id="run-concurrent-assigned-2",
            channel="webchat-concurrent-2",
            direct_scope=DirectSessionScope.PER_CHANNEL_PEER,
            peer_id="peer-concurrent-2",
        )
        self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-concurrent-loop",
            max_inflight_assignments=2,
            inflight_assignment_count=0,
        )
        first = self.orchestration_scheduler_service.assign_next_assignment()
        second = self.orchestration_scheduler_service.assign_next_assignment()
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)

        processed_count = self.orchestration_executor_service.run_until_stopped(
            worker_id="executor-concurrent-loop",
            poll_interval_seconds=0.01,
            max_runs=2,
            max_concurrent_assignments=2,
        )

        self.assertEqual(processed_count, 2)
        first_run = self.orchestration_run_query_service.get_run(
            "run-concurrent-assigned-1",
        )
        second_run = self.orchestration_run_query_service.get_run(
            "run-concurrent-assigned-2",
        )
        self.assertEqual(
            first_run.status,
            OrchestrationRunStatus.COMPLETED,
            first_run.error,
        )
        self.assertEqual(
            second_run.status,
            OrchestrationRunStatus.COMPLETED,
            second_run.error,
        )
        self.assertEqual(adapter.invocation_count, 2)
        leases = self.orchestration_executor_service.list_executor_leases()
        self.assertEqual(leases[0].inflight_assignment_count, 0)
        runtime_state = leases[0].metadata["runtime_state"]
        self.assertEqual(runtime_state["active_assignment_count"], 0)
        self.assertEqual(runtime_state["active_run_ids"], [])
        runtime_metrics = leases[0].metadata["runtime_metrics"]
        completion_counter = next(
            item
            for item in runtime_metrics["counters"]
            if item["name"] == "orchestration.executor.assignment_completions"
        )
        self.assertEqual(completion_counter["value"], 2)

    def test_executor_async_loop_processes_multiple_assigned_runs(self) -> None:
        class _AsyncCountingAdapter:
            def __init__(self) -> None:
                self.entered = 0

            async def invoke_async(
                self,
                _profile: object,
                request: LlmAdapterRequest,
            ) -> LlmAdapterResponse:
                del request
                self.entered += 1
                await asyncio.sleep(0)
                return LlmAdapterResponse(
                    result=LlmResult(text="async concurrent complete"),
                )

        adapter = _AsyncCountingAdapter()
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()
        self._queue_session_run(
            run_id="run-async-concurrent-assigned-1",
            channel="webchat-async-concurrent-1",
            direct_scope=DirectSessionScope.PER_CHANNEL_PEER,
            peer_id="peer-async-concurrent-1",
        )
        self._queue_session_run(
            run_id="run-async-concurrent-assigned-2",
            channel="webchat-async-concurrent-2",
            direct_scope=DirectSessionScope.PER_CHANNEL_PEER,
            peer_id="peer-async-concurrent-2",
        )
        self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-async-concurrent-loop",
            max_inflight_assignments=2,
            inflight_assignment_count=0,
        )
        first = self.orchestration_scheduler_service.assign_next_assignment()
        second = self.orchestration_scheduler_service.assign_next_assignment()
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)

        processed_count = asyncio.run(
            self.orchestration_executor_service.run_until_stopped_async(
                worker_id="executor-async-concurrent-loop",
                poll_interval_seconds=0.01,
                max_runs=2,
                max_concurrent_assignments=2,
            ),
        )

        self.assertEqual(processed_count, 2)
        first_run = self.orchestration_run_query_service.get_run(
            "run-async-concurrent-assigned-1",
        )
        second_run = self.orchestration_run_query_service.get_run(
            "run-async-concurrent-assigned-2",
        )
        self.assertEqual(
            first_run.status,
            OrchestrationRunStatus.COMPLETED,
            first_run.error,
        )
        self.assertEqual(
            second_run.status,
            OrchestrationRunStatus.COMPLETED,
            second_run.error,
        )
        self.assertEqual(adapter.entered, 2)
        assert first_run.result_payload is not None
        self.assertEqual(
            first_run.result_payload["output_text"],
            "async concurrent complete",
        )

    def test_scheduler_and_executor_async_runtimes_flow_multiple_waves(self) -> None:
        class _AsyncConcurrentAdapter:
            def __init__(self) -> None:
                self.entered = 0
                self.active = 0
                self.max_active = 0
                self._lock: asyncio.Lock | None = None
                self._first_wave_entered: asyncio.Event | None = None

            async def invoke_async(
                self,
                _profile: object,
                request: LlmAdapterRequest,
            ) -> LlmAdapterResponse:
                del request
                if self._lock is None:
                    self._lock = asyncio.Lock()
                if self._first_wave_entered is None:
                    self._first_wave_entered = asyncio.Event()
                async with self._lock:
                    self.entered += 1
                    self.active += 1
                    self.max_active = max(self.max_active, self.active)
                    if self.entered >= 2:
                        self._first_wave_entered.set()
                try:
                    await asyncio.wait_for(
                        self._first_wave_entered.wait(),
                        timeout=5.0,
                    )
                except TimeoutError:
                    pass
                await asyncio.sleep(0.05)
                async with self._lock:
                    self.active -= 1
                return LlmAdapterResponse(
                    result=LlmResult(text="linked runtime complete"),
                )

        async def _run_linked_runtimes() -> tuple[int, int]:
            return await asyncio.gather(
                self.orchestration_scheduler_service.run_until_stopped_async(
                    worker_id="scheduler-linked-runtime",
                    poll_interval_seconds=0.01,
                    max_runs=4,
                    max_idle_cycles=100,
                ),
                self.orchestration_executor_service.run_until_stopped_async(
                    worker_id="executor-linked-runtime",
                    poll_interval_seconds=0.01,
                    max_runs=4,
                    max_idle_cycles=100,
                    max_concurrent_assignments=2,
                ),
            )

        adapter = _AsyncConcurrentAdapter()
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()
        for index in range(4):
            self._queue_session_run(
                run_id=f"run-linked-runtime-{index + 1}",
                channel=f"webchat-linked-runtime-{index + 1}",
                direct_scope=DirectSessionScope.PER_CHANNEL_PEER,
                peer_id=f"peer-linked-runtime-{index + 1}",
            )
        self.orchestration_executor_service.heartbeat_executor(
            worker_id="executor-linked-runtime",
            max_inflight_assignments=2,
            inflight_assignment_count=0,
        )

        scheduler_count, executor_count = asyncio.run(_run_linked_runtimes())

        self.assertEqual(scheduler_count, 4)
        self.assertEqual(executor_count, 4)
        self.assertEqual(adapter.entered, 4)
        self.assertEqual(adapter.max_active, 2)
        for index in range(4):
            run = self.orchestration_run_query_service.get_run(
                f"run-linked-runtime-{index + 1}",
            )
            self.assertEqual(run.status, OrchestrationRunStatus.COMPLETED)
            assert run.result_payload is not None
            self.assertEqual(
                run.result_payload["output_text"],
                "linked runtime complete",
            )
        lease = self.orchestration_executor_service.list_executor_leases()[0]
        self.assertEqual(lease.inflight_assignment_count, 0)
        self.assertEqual(lease.metadata["runtime_state"]["active_assignment_count"], 0)
