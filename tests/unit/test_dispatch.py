from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
import unittest

from crxzipple.modules.dispatch.application import (
    CancelDispatchTaskInput,
    CompleteDispatchTaskInput,
    CreateDispatchTaskInput,
    EnqueueDispatchTaskInput,
    FailDispatchTaskInput,
    HeartbeatDispatchTaskInput,
    RequeueDispatchTaskInput,
    RecoverAbandonedDispatchTasksInput,
    WaitDispatchTaskInput,
)
from crxzipple.modules.dispatch.domain import (
    DispatchPolicy,
    DispatchTaskStatus,
    DispatchValidationError,
)
from crxzipple.interfaces.runtime_container import AppKey
from tests.unit.support import SqliteTestHarness


class DispatchTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = SqliteTestHarness()
        self.harness.initialize_schema()
        self.container = self.harness.build_runtime_container()
        self.dispatch_service = self.container.require(AppKey.DISPATCH_SERVICE)
        self.uow_factory = self.container.require(AppKey.UNIT_OF_WORK_FACTORY)

    def tearDown(self) -> None:
        self.harness.close()

    def test_create_enqueue_claim_wait_requeue_and_complete_task(self) -> None:
        task = self.dispatch_service.create_task(
            CreateDispatchTaskInput(
                task_id="dispatch-task-1",
                owner_kind="orchestration_step",
                owner_id="run-1",
                lane_key="bulk:conversation:main",
                priority=20,
            ),
        )

        self.assertEqual(task.status, DispatchTaskStatus.CREATED)
        self.assertEqual(task.policy, DispatchPolicy.FIFO)

        queued = self.dispatch_service.enqueue_task(
            EnqueueDispatchTaskInput(task_id=task.id),
        )
        claimed = self.dispatch_service.claim_next_queued_task(
            worker_id="worker-1",
            claim_token="claim-1",
        )
        waiting = self.dispatch_service.wait_task(
            WaitDispatchTaskInput(task_id=task.id, reason="waiting_for_owner"),
        )
        requeued = self.dispatch_service.requeue_task(
            RequeueDispatchTaskInput(
                task_id=task.id,
                policy=DispatchPolicy.RESUME_FIRST,
                reason="owner_resumed",
            ),
        )
        reclaimed = self.dispatch_service.claim_next_queued_task(
            worker_id="worker-1",
            claim_token="claim-2",
        )
        completed = self.dispatch_service.complete_task(
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
        active = self.dispatch_service.create_task(
            CreateDispatchTaskInput(
                task_id="dispatch-active",
                owner_kind="orchestration_step",
                owner_id="run-active",
                lane_key="bulk:blocked",
                priority=50,
            ),
        )
        available = self.dispatch_service.create_task(
            CreateDispatchTaskInput(
                task_id="dispatch-available",
                owner_kind="orchestration_step",
                owner_id="run-available",
                lane_key="bulk:available",
                priority=10,
            ),
        )
        same_lane = self.dispatch_service.create_task(
            CreateDispatchTaskInput(
                task_id="dispatch-same-lane",
                owner_kind="orchestration_step",
                owner_id="run-same-lane",
                lane_key="bulk:blocked",
                priority=1,
            ),
        )

        self.dispatch_service.enqueue_task(
            EnqueueDispatchTaskInput(task_id=active.id),
        )
        first = self.dispatch_service.claim_next_queued_task(
            worker_id="worker-1",
            claim_token="claim-1",
        )
        self.dispatch_service.enqueue_task(
            EnqueueDispatchTaskInput(task_id=available.id),
        )
        self.dispatch_service.enqueue_task(
            EnqueueDispatchTaskInput(task_id=same_lane.id),
        )

        second = self.dispatch_service.claim_next_queued_task(
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
        other_lane_fifo = self.dispatch_service.create_task(
            CreateDispatchTaskInput(
                task_id="dispatch-other-lane-fifo",
                owner_kind="orchestration_step",
                owner_id="run-other-lane-fifo",
                lane_key="bulk:other",
                priority=10,
            ),
        )
        same_lane_fifo = self.dispatch_service.create_task(
            CreateDispatchTaskInput(
                task_id="dispatch-shared-lane-fifo",
                owner_kind="orchestration_step",
                owner_id="run-shared-lane-fifo",
                lane_key="bulk:shared",
                priority=10,
            ),
        )
        lane_jump = self.dispatch_service.create_task(
            CreateDispatchTaskInput(
                task_id="dispatch-lane-jump",
                owner_kind="orchestration_step",
                owner_id="run-lane-jump",
                lane_key="bulk:shared",
                priority=10,
                policy=DispatchPolicy.LANE_JUMP_QUEUE,
            ),
        )

        self.dispatch_service.enqueue_task(
            EnqueueDispatchTaskInput(task_id=other_lane_fifo.id),
        )
        self.dispatch_service.enqueue_task(
            EnqueueDispatchTaskInput(task_id=same_lane_fifo.id),
        )
        self.dispatch_service.enqueue_task(
            EnqueueDispatchTaskInput(task_id=lane_jump.id),
        )

        claimed = self.dispatch_service.claim_next_queued_task(
            worker_id="worker-1",
            claim_token="claim-1",
        )

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.id, other_lane_fifo.id)

    def test_resume_first_claims_before_jump_queue_and_fifo(self) -> None:
        fifo = self.dispatch_service.create_task(
            CreateDispatchTaskInput(
                task_id="dispatch-fifo",
                owner_kind="orchestration_step",
                owner_id="run-fifo",
                lane_key="bulk:fifo",
                priority=10,
            ),
        )
        jump_queue = self.dispatch_service.create_task(
            CreateDispatchTaskInput(
                task_id="dispatch-jump",
                owner_kind="orchestration_step",
                owner_id="run-jump",
                lane_key="bulk:jump",
                priority=10,
                policy=DispatchPolicy.JUMP_QUEUE,
            ),
        )
        resume_first = self.dispatch_service.create_task(
            CreateDispatchTaskInput(
                task_id="dispatch-resume",
                owner_kind="orchestration_step",
                owner_id="run-resume",
                lane_key="bulk:resume",
                priority=10,
                policy=DispatchPolicy.RESUME_FIRST,
            ),
        )

        self.dispatch_service.enqueue_task(
            EnqueueDispatchTaskInput(task_id=fifo.id),
        )
        self.dispatch_service.enqueue_task(
            EnqueueDispatchTaskInput(task_id=jump_queue.id),
        )
        self.dispatch_service.enqueue_task(
            EnqueueDispatchTaskInput(task_id=resume_first.id),
        )

        claimed = self.dispatch_service.claim_next_queued_task(
            worker_id="worker-1",
            claim_token="claim-1",
        )

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.id, resume_first.id)

    def test_claim_uses_owner_filter_and_supports_lease_heartbeat_and_recovery(self) -> None:
        orchestration_task = self.dispatch_service.create_task(
            CreateDispatchTaskInput(
                task_id="dispatch-orchestration",
                owner_kind="orchestration_step",
                owner_id="run-orchestration",
                lane_key="bulk:orchestration",
                priority=50,
            ),
        )
        tool_task = self.dispatch_service.create_task(
            CreateDispatchTaskInput(
                task_id="dispatch-tool",
                owner_kind="tool_run",
                owner_id="run-tool",
                lane_key="bulk:tool",
                priority=1,
            ),
        )

        self.dispatch_service.enqueue_task(
            EnqueueDispatchTaskInput(task_id=orchestration_task.id),
        )
        self.dispatch_service.enqueue_task(
            EnqueueDispatchTaskInput(task_id=tool_task.id),
        )

        claimed = self.dispatch_service.claim_next_queued_task(
            owner_kind="orchestration_step",
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

        heartbeated = self.dispatch_service.heartbeat_task(
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

        claimed_tool = self.dispatch_service.claim_next_queued_task(
            owner_kind="tool_run",
            worker_id="worker-2",
            claim_token="claim-2",
            lease_seconds=15,
        )
        self.assertIsNotNone(claimed_tool)
        assert claimed_tool is not None
        self.assertEqual(claimed_tool.id, tool_task.id)

        stale_now = datetime.now(timezone.utc) - timedelta(seconds=1)
        with self.uow_factory() as uow:
            stale_task = uow.dispatch_tasks.get(tool_task.id)
            self.assertIsNotNone(stale_task)
            assert stale_task is not None
            stale_task.lease_expires_at = stale_now
            uow.dispatch_tasks.add(stale_task)
            uow.commit()

        recovered = self.dispatch_service.recover_abandoned_tasks(
            RecoverAbandonedDispatchTasksInput(
                owner_kind="tool_run",
                reason="lease_expired",
            ),
        )

        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0].id, tool_task.id)
        self.assertEqual(recovered[0].status, DispatchTaskStatus.QUEUED)

    def test_sql_repository_concurrent_claims_do_not_duplicate_tasks(self) -> None:
        task_ids = [f"dispatch-concurrent-{index}" for index in range(6)]
        for index, task_id in enumerate(task_ids):
            task = self.dispatch_service.create_task(
                CreateDispatchTaskInput(
                    task_id=task_id,
                    owner_kind="concurrent_owner",
                    owner_id=f"run-{index}",
                    priority=index,
                ),
            )
            self.dispatch_service.enqueue_task(EnqueueDispatchTaskInput(task_id=task.id))

        worker_count = 12
        barrier = Barrier(worker_count)

        def claim(worker_index: int) -> str | None:
            barrier.wait(timeout=10)
            task = self.dispatch_service.claim_next_queued_task(
                owner_kind="concurrent_owner",
                worker_id=f"worker-{worker_index}",
                claim_token=f"claim-{worker_index}",
                lease_seconds=60,
            )
            return None if task is None else task.id

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            claimed_ids = list(executor.map(claim, range(worker_count)))

        non_empty_claims = [task_id for task_id in claimed_ids if task_id is not None]
        self.assertEqual(len(non_empty_claims), len(task_ids))
        self.assertEqual(sorted(non_empty_claims), sorted(task_ids))
        self.assertEqual(len(set(non_empty_claims)), len(non_empty_claims))

        claimed_tasks = self.dispatch_service.list_tasks(
            status=DispatchTaskStatus.CLAIMED,
            owner_kind="concurrent_owner",
        )
        self.assertEqual(len(claimed_tasks), len(task_ids))
        self.assertEqual(
            sorted(task.claim_token for task in claimed_tasks if task.claim_token),
            sorted(
                claim_token
                for claim_token in (
                    f"claim-{index}" if task_id is not None else None
                    for index, task_id in enumerate(claimed_ids)
                )
                if claim_token is not None
            ),
        )

    def test_recover_abandoned_tasks_only_requeues_expired_leased_claims(self) -> None:
        task_ids = {
            "expired": "dispatch-recover-expired",
            "live": "dispatch-recover-live",
            "unleased": "dispatch-recover-unleased",
            "queued": "dispatch-recover-queued",
        }
        for priority, task_id in enumerate(task_ids.values()):
            task = self.dispatch_service.create_task(
                CreateDispatchTaskInput(
                    task_id=task_id,
                    owner_kind="recovery_owner",
                    owner_id=f"run-{task_id}",
                    priority=priority,
                ),
            )
            self.dispatch_service.enqueue_task(EnqueueDispatchTaskInput(task_id=task.id))

        expired = self.dispatch_service.claim_next_queued_task(
            owner_kind="recovery_owner",
            worker_id="worker-expired",
            claim_token="claim-expired",
            lease_seconds=30,
        )
        live = self.dispatch_service.claim_next_queued_task(
            owner_kind="recovery_owner",
            worker_id="worker-live",
            claim_token="claim-live",
            lease_seconds=30,
        )
        unleased = self.dispatch_service.claim_next_queued_task(
            owner_kind="recovery_owner",
            worker_id="worker-unleased",
            claim_token="claim-unleased",
        )
        self.assertIsNotNone(expired)
        self.assertIsNotNone(live)
        self.assertIsNotNone(unleased)
        assert expired is not None
        assert live is not None
        assert unleased is not None

        now = datetime.now(timezone.utc)
        with self.uow_factory() as uow:
            expired_task = uow.dispatch_tasks.get(expired.id)
            live_task = uow.dispatch_tasks.get(live.id)
            unleased_task = uow.dispatch_tasks.get(unleased.id)
            assert expired_task is not None
            assert live_task is not None
            assert unleased_task is not None
            expired_task.lease_expires_at = now - timedelta(seconds=1)
            live_task.lease_expires_at = now + timedelta(seconds=30)
            unleased_task.lease_expires_at = None
            uow.dispatch_tasks.add(expired_task)
            uow.dispatch_tasks.add(live_task)
            uow.dispatch_tasks.add(unleased_task)
            uow.commit()

        recovered = self.dispatch_service.recover_abandoned_tasks(
            RecoverAbandonedDispatchTasksInput(
                owner_kind="recovery_owner",
                reason="lease_expired",
                now=now,
            ),
        )

        self.assertEqual([task.id for task in recovered], [task_ids["expired"]])
        latest_by_id = {
            task.id: task
            for task in self.dispatch_service.list_tasks(owner_kind="recovery_owner")
        }
        self.assertEqual(
            latest_by_id[task_ids["expired"]].status,
            DispatchTaskStatus.QUEUED,
        )
        self.assertEqual(
            latest_by_id[task_ids["live"]].status,
            DispatchTaskStatus.CLAIMED,
        )
        self.assertEqual(
            latest_by_id[task_ids["unleased"]].status,
            DispatchTaskStatus.CLAIMED,
        )
        self.assertEqual(
            latest_by_id[task_ids["queued"]].status,
            DispatchTaskStatus.QUEUED,
        )

    def test_terminal_transitions_are_idempotent_and_cannot_be_overwritten(self) -> None:
        task = self.dispatch_service.create_task(
            CreateDispatchTaskInput(
                task_id="dispatch-terminal",
                owner_kind="terminal_owner",
                owner_id="run-terminal",
            ),
        )
        self.dispatch_service.enqueue_task(EnqueueDispatchTaskInput(task_id=task.id))
        self.dispatch_service.claim_next_queued_task(
            owner_kind="terminal_owner",
            worker_id="worker-terminal",
            claim_token="claim-terminal",
        )
        completed_at = datetime(2026, 6, 21, 10, 0, tzinfo=timezone.utc)
        repeated_at = completed_at + timedelta(minutes=1)

        completed = self.dispatch_service.complete_task(
            CompleteDispatchTaskInput(task_id=task.id, now=completed_at),
        )
        repeated = self.dispatch_service.complete_task(
            CompleteDispatchTaskInput(task_id=task.id, now=repeated_at),
        )

        self.assertEqual(completed.status, DispatchTaskStatus.COMPLETED)
        self.assertEqual(repeated.status, DispatchTaskStatus.COMPLETED)
        self.assertIsNotNone(completed.completed_at)
        self.assertIsNotNone(repeated.completed_at)
        assert completed.completed_at is not None
        assert repeated.completed_at is not None
        self.assertEqual(
            repeated.completed_at.replace(tzinfo=None),
            completed.completed_at.replace(tzinfo=None),
        )
        with self.assertRaisesRegex(
            DispatchValidationError,
            "Terminal dispatch tasks cannot be failed",
        ):
            self.dispatch_service.fail_task(
                FailDispatchTaskInput(
                    task_id=task.id,
                    message="too late",
                    now=repeated_at,
                ),
            )
        with self.assertRaisesRegex(
            DispatchValidationError,
            "Terminal dispatch tasks cannot be cancelled",
        ):
            self.dispatch_service.cancel_task(
                CancelDispatchTaskInput(
                    task_id=task.id,
                    reason="too late",
                    now=repeated_at,
                ),
            )
