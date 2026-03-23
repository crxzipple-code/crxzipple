from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from crxzipple.modules.dispatch.application import (
    CompleteDispatchTaskInput,
    CreateDispatchTaskInput,
    EnqueueDispatchTaskInput,
    HeartbeatDispatchTaskInput,
    RequeueDispatchTaskInput,
    RecoverAbandonedDispatchTasksInput,
    WaitDispatchTaskInput,
)
from crxzipple.modules.dispatch.domain import DispatchPolicy, DispatchTaskStatus
from tests.unit.support import SqliteTestHarness


class DispatchTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = SqliteTestHarness()
        self.harness.initialize_schema()
        self.container = self.harness.build_container()

    def tearDown(self) -> None:
        self.harness.close()

    def test_create_enqueue_claim_wait_requeue_and_complete_task(self) -> None:
        task = self.container.dispatch_service.create_task(
            CreateDispatchTaskInput(
                task_id="dispatch-task-1",
                owner_kind="orchestration_run",
                owner_id="run-1",
                lane_key="bulk:conversation:main",
                priority=20,
            ),
        )

        self.assertEqual(task.status, DispatchTaskStatus.CREATED)
        self.assertEqual(task.policy, DispatchPolicy.FIFO)

        queued = self.container.dispatch_service.enqueue_task(
            EnqueueDispatchTaskInput(task_id=task.id),
        )
        claimed = self.container.dispatch_service.claim_next_queued_task(
            worker_id="worker-1",
            claim_token="claim-1",
        )
        waiting = self.container.dispatch_service.wait_task(
            WaitDispatchTaskInput(task_id=task.id, reason="waiting_for_owner"),
        )
        requeued = self.container.dispatch_service.requeue_task(
            RequeueDispatchTaskInput(
                task_id=task.id,
                policy=DispatchPolicy.RESUME_FIRST,
                reason="owner_resumed",
            ),
        )
        reclaimed = self.container.dispatch_service.claim_next_queued_task(
            worker_id="worker-1",
            claim_token="claim-2",
        )
        completed = self.container.dispatch_service.complete_task(
            CompleteDispatchTaskInput(task_id=task.id),
        )

        self.assertEqual(queued.status, DispatchTaskStatus.QUEUED)
        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.status, DispatchTaskStatus.CLAIMED)
        self.assertEqual(claimed.claimed_by, "worker-1")
        self.assertEqual(claimed.claim_token, "claim-1")
        self.assertEqual(waiting.status, DispatchTaskStatus.WAITING)
        self.assertEqual(waiting.waiting_reason, "waiting_for_owner")
        self.assertEqual(requeued.status, DispatchTaskStatus.QUEUED)
        self.assertEqual(requeued.policy, DispatchPolicy.RESUME_FIRST)
        self.assertIsNotNone(reclaimed)
        assert reclaimed is not None
        self.assertEqual(reclaimed.claim_token, "claim-2")
        self.assertEqual(completed.status, DispatchTaskStatus.COMPLETED)
        self.assertIsNotNone(completed.completed_at)

    def test_claim_next_queued_task_skips_lane_blocked_by_active_task(self) -> None:
        active = self.container.dispatch_service.create_task(
            CreateDispatchTaskInput(
                task_id="dispatch-active",
                owner_kind="orchestration_run",
                owner_id="run-active",
                lane_key="bulk:blocked",
                priority=50,
            ),
        )
        available = self.container.dispatch_service.create_task(
            CreateDispatchTaskInput(
                task_id="dispatch-available",
                owner_kind="orchestration_run",
                owner_id="run-available",
                lane_key="bulk:available",
                priority=10,
            ),
        )
        same_lane = self.container.dispatch_service.create_task(
            CreateDispatchTaskInput(
                task_id="dispatch-same-lane",
                owner_kind="orchestration_run",
                owner_id="run-same-lane",
                lane_key="bulk:blocked",
                priority=1,
            ),
        )

        self.container.dispatch_service.enqueue_task(
            EnqueueDispatchTaskInput(task_id=active.id),
        )
        first = self.container.dispatch_service.claim_next_queued_task(
            worker_id="worker-1",
            claim_token="claim-1",
        )
        self.container.dispatch_service.enqueue_task(
            EnqueueDispatchTaskInput(task_id=available.id),
        )
        self.container.dispatch_service.enqueue_task(
            EnqueueDispatchTaskInput(task_id=same_lane.id),
        )

        second = self.container.dispatch_service.claim_next_queued_task(
            worker_id="worker-2",
            claim_token="claim-2",
        )

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        assert first is not None
        assert second is not None
        self.assertEqual(first.id, active.id)
        self.assertEqual(second.id, available.id)

    def test_lane_jump_queue_does_not_jump_ahead_of_other_lane_heads(self) -> None:
        other_lane_fifo = self.container.dispatch_service.create_task(
            CreateDispatchTaskInput(
                task_id="dispatch-other-lane-fifo",
                owner_kind="orchestration_run",
                owner_id="run-other-lane-fifo",
                lane_key="bulk:other",
                priority=10,
            ),
        )
        same_lane_fifo = self.container.dispatch_service.create_task(
            CreateDispatchTaskInput(
                task_id="dispatch-shared-lane-fifo",
                owner_kind="orchestration_run",
                owner_id="run-shared-lane-fifo",
                lane_key="bulk:shared",
                priority=10,
            ),
        )
        lane_jump = self.container.dispatch_service.create_task(
            CreateDispatchTaskInput(
                task_id="dispatch-lane-jump",
                owner_kind="orchestration_run",
                owner_id="run-lane-jump",
                lane_key="bulk:shared",
                priority=10,
                policy=DispatchPolicy.LANE_JUMP_QUEUE,
            ),
        )

        self.container.dispatch_service.enqueue_task(
            EnqueueDispatchTaskInput(task_id=other_lane_fifo.id),
        )
        self.container.dispatch_service.enqueue_task(
            EnqueueDispatchTaskInput(task_id=same_lane_fifo.id),
        )
        self.container.dispatch_service.enqueue_task(
            EnqueueDispatchTaskInput(task_id=lane_jump.id),
        )

        claimed = self.container.dispatch_service.claim_next_queued_task(
            worker_id="worker-1",
            claim_token="claim-1",
        )

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.id, other_lane_fifo.id)

    def test_resume_first_claims_before_jump_queue_and_fifo(self) -> None:
        fifo = self.container.dispatch_service.create_task(
            CreateDispatchTaskInput(
                task_id="dispatch-fifo",
                owner_kind="orchestration_run",
                owner_id="run-fifo",
                lane_key="bulk:fifo",
                priority=10,
            ),
        )
        jump_queue = self.container.dispatch_service.create_task(
            CreateDispatchTaskInput(
                task_id="dispatch-jump",
                owner_kind="orchestration_run",
                owner_id="run-jump",
                lane_key="bulk:jump",
                priority=10,
                policy=DispatchPolicy.JUMP_QUEUE,
            ),
        )
        resume_first = self.container.dispatch_service.create_task(
            CreateDispatchTaskInput(
                task_id="dispatch-resume",
                owner_kind="orchestration_run",
                owner_id="run-resume",
                lane_key="bulk:resume",
                priority=10,
                policy=DispatchPolicy.RESUME_FIRST,
            ),
        )

        self.container.dispatch_service.enqueue_task(
            EnqueueDispatchTaskInput(task_id=fifo.id),
        )
        self.container.dispatch_service.enqueue_task(
            EnqueueDispatchTaskInput(task_id=jump_queue.id),
        )
        self.container.dispatch_service.enqueue_task(
            EnqueueDispatchTaskInput(task_id=resume_first.id),
        )

        claimed = self.container.dispatch_service.claim_next_queued_task(
            worker_id="worker-1",
            claim_token="claim-1",
        )

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.id, resume_first.id)

    def test_claim_uses_owner_filter_and_supports_lease_heartbeat_and_recovery(self) -> None:
        orchestration_task = self.container.dispatch_service.create_task(
            CreateDispatchTaskInput(
                task_id="dispatch-orchestration",
                owner_kind="orchestration_run",
                owner_id="run-orchestration",
                lane_key="bulk:orchestration",
                priority=50,
            ),
        )
        tool_task = self.container.dispatch_service.create_task(
            CreateDispatchTaskInput(
                task_id="dispatch-tool",
                owner_kind="tool_run",
                owner_id="run-tool",
                lane_key="bulk:tool",
                priority=1,
            ),
        )

        self.container.dispatch_service.enqueue_task(
            EnqueueDispatchTaskInput(task_id=orchestration_task.id),
        )
        self.container.dispatch_service.enqueue_task(
            EnqueueDispatchTaskInput(task_id=tool_task.id),
        )

        claimed = self.container.dispatch_service.claim_next_queued_task(
            owner_kind="orchestration_run",
            worker_id="worker-1",
            claim_token="claim-1",
            lease_seconds=30,
        )

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.id, orchestration_task.id)
        self.assertEqual(claimed.claimed_by, "worker-1")
        self.assertIsNotNone(claimed.heartbeat_at)
        self.assertIsNotNone(claimed.lease_expires_at)
        claimed_lease_expires_at = claimed.lease_expires_at
        assert claimed_lease_expires_at is not None

        heartbeated = self.container.dispatch_service.heartbeat_task(
            HeartbeatDispatchTaskInput(
                task_id=claimed.id,
                worker_id="worker-1",
                claim_token="claim-1",
                lease_seconds=45,
                now=claimed_lease_expires_at,
            ),
        )

        self.assertIsNotNone(heartbeated.lease_expires_at)
        assert heartbeated.lease_expires_at is not None
        self.assertGreater(heartbeated.lease_expires_at, claimed_lease_expires_at)

        claimed_tool = self.container.dispatch_service.claim_next_queued_task(
            owner_kind="tool_run",
            worker_id="worker-2",
            claim_token="claim-2",
            lease_seconds=15,
        )
        self.assertIsNotNone(claimed_tool)
        assert claimed_tool is not None
        self.assertEqual(claimed_tool.id, tool_task.id)

        stale_now = datetime.now(timezone.utc) - timedelta(seconds=1)
        with self.container.uow_factory() as uow:
            stale_task = uow.dispatch_tasks.get(tool_task.id)
            self.assertIsNotNone(stale_task)
            assert stale_task is not None
            stale_task.lease_expires_at = stale_now
            uow.dispatch_tasks.add(stale_task)
            uow.commit()

        recovered = self.container.dispatch_service.recover_abandoned_tasks(
            RecoverAbandonedDispatchTasksInput(
                owner_kind="tool_run",
                reason="lease_expired",
            ),
        )

        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0].id, tool_task.id)
        self.assertEqual(recovered[0].status, DispatchTaskStatus.QUEUED)
