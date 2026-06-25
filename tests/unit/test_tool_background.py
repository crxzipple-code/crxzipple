from __future__ import annotations

from crxzipple.modules.tool.domain import (
    ToolRunAssignmentStatus,
    ToolRunResult,
    ToolWorkerStatus,
)
from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationRunNotFoundError,
)
from crxzipple.modules.tool.application.result_envelope import (
    TOOL_RESULT_ENVELOPE_METADATA_KEY,
)
from crxzipple.shared.domain.events import Event

from tests.unit.tool_test_support import *  # noqa: F403
from tests.unit.tool_runtime_test_support import (
    assign_next_background_tool_run,
    process_next_background_tool_run,
)


class ToolBackgroundTestCase(ToolTestCaseBase):
    def test_scheduler_ignores_expired_online_workers(self) -> None:
        self.tool_worker_service.register_worker(
            worker_id="worker-expired",
        )
        self.tool_worker_service.register_worker(
            worker_id="worker-live",
        )
        with self.uow_factory() as uow:
            worker = uow.tool_workers.get("worker-expired")
            assert worker is not None
            worker.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            uow.tool_workers.add(worker)
            uow.collect(worker)
            uow.commit()

        queued_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "skip expired"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )

        assigned = self.tool_scheduler_service.assign_next_available()

        self.assertIsNotNone(assigned)
        assert assigned is not None
        self.assertEqual(assigned.id, queued_run.id)
        self.assertEqual(assigned.worker_id, "worker-live")

    def test_worker_registration_releases_terminal_assignment_slots(self) -> None:
        queued_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "stale slot"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )
        claimed = assign_next_background_tool_run(
            self.container,
            worker_id="worker-stale-slot",
        )
        self.assertIsNotNone(claimed)
        with self.uow_factory() as uow:
            run = uow.tool_runs.get(queued_run.id)
            assert run is not None
            run.fail("terminal before assignment cleanup")
            uow.tool_runs.add(run)
            uow.collect(run)
            uow.commit()

        worker = self.tool_worker_service.register_worker(
            worker_id="worker-stale-slot",
        )

        self.assertEqual(worker.current_in_flight, 0)
        with self.uow_factory() as uow:
            assignment = uow.tool_run_assignments.get_latest_for_run(queued_run.id)
        self.assertIsNotNone(assignment)
        assert assignment is not None
        self.assertEqual(assignment.status, ToolRunAssignmentStatus.EXPIRED)

    def test_background_run_tracks_assignment_and_worker_terminal_state(self) -> None:

        queued_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "tracked hello"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )

        claimed = assign_next_background_tool_run(
            self.container,
            worker_id="worker-tracked",
        )
        self.assertIsNotNone(claimed)

        with self.uow_factory() as uow:
            assignment = uow.tool_run_assignments.get_latest_for_run(queued_run.id)
            worker = uow.tool_workers.get("worker-tracked")

        self.assertIsNotNone(assignment)
        self.assertEqual(assignment.status, ToolRunAssignmentStatus.ASSIGNED)
        self.assertIsNotNone(worker)
        self.assertEqual(worker.current_in_flight, 1)

        finished = self.tool_worker_service.process_next_assigned_run(
            worker_id="worker-tracked",
        )

        self.assertEqual(finished.status, ToolRunStatus.SUCCEEDED)
        with self.uow_factory() as uow:
            assignment = uow.tool_run_assignments.get_latest_for_run(queued_run.id)
            worker = uow.tool_workers.get("worker-tracked")

        self.assertIsNotNone(assignment)
        self.assertEqual(assignment.status, ToolRunAssignmentStatus.SUCCEEDED)
        self.assertIsNotNone(assignment.completed_at)
        self.assertIsNotNone(worker)
        self.assertEqual(worker.status, ToolWorkerStatus.ONLINE)
        self.assertEqual(worker.current_in_flight, 0)

    def test_recovered_background_run_expires_assignment_and_releases_worker(self) -> None:

        queued_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "expire me"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )

        claimed = assign_next_background_tool_run(
            self.container,
            worker_id="worker-expire",
        )
        self.assertIsNotNone(claimed)

        recovered = self.tool_worker_service.handle_recovered_dispatch_task(
            tool_run_id=queued_run.id,
            reason="lease expired in test",
        )

        self.assertIsNotNone(recovered)
        self.assertEqual(recovered.status, ToolRunStatus.QUEUED)
        with self.uow_factory() as uow:
            assignment = uow.tool_run_assignments.get_latest_for_run(queued_run.id)
            worker = uow.tool_workers.get("worker-expire")

        self.assertIsNotNone(assignment)
        self.assertEqual(assignment.status, ToolRunAssignmentStatus.EXPIRED)
        self.assertEqual(assignment.terminal_reason, "lease expired in test")
        self.assertIsNotNone(worker)
        self.assertEqual(worker.current_in_flight, 0)

    def test_executes_local_background_async_tool_and_updates_lifecycle(self) -> None:

        queued_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "background hello"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )

        self.assertEqual(queued_run.status, ToolRunStatus.QUEUED)
        dispatch_task = self.dispatch_service.get_task(queued_run.id)
        self.assertEqual(dispatch_task.status, DispatchTaskStatus.QUEUED)
        self.assertEqual(dispatch_task.owner_kind, "tool_run")

        deadline = time.monotonic() + 5
        persisted = None
        while time.monotonic() < deadline:
            if persisted is None or persisted.status is ToolRunStatus.QUEUED:
                process_next_background_tool_run(
                    self.container,
                    worker_id="worker-local",
                )
            persisted = self.tool_service.get_tool_run(queued_run.id)
            if persisted.status is ToolRunStatus.SUCCEEDED:
                break
            time.sleep(0.05)

        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(persisted.output_payload["message"], "background hello")
        self.assertEqual(persisted.result.metadata["environment"], "local")
        self.assertEqual(persisted.attempt_count, 1)
        self.assertEqual(persisted.worker_id, "worker-local")
        self.assertIsNotNone(persisted.heartbeat_at)
        self.assertIsNone(persisted.lease_expires_at)
        completed_dispatch_task = self.dispatch_service.get_task(queued_run.id)
        self.assertEqual(completed_dispatch_task.status, DispatchTaskStatus.COMPLETED)

        event_names = [
            event.event_name
            for event in self.published_event_bus_events()
            if isinstance(event, Event) and bool(event.name)
        ]
        self.assertIn("tool.run.queued", event_names)

    def test_background_run_externalizes_large_text_result_to_artifact_refs(self) -> None:
        tool = self.seed_tool(
            tool_id="background_large_text_tool",
            name="Background Large Text Tool",
            description="Returns a large text payload from a background worker.",
            supported_modes=(ToolMode.BACKGROUND,),
            runtime_key="background_large_text_tool",
        )
        large_text = "background header\n" + ("x" * 24_000)

        async def large_text_tool(_arguments: dict[str, object]) -> ToolRunResult:
            return ToolRunResult.text(large_text)

        self.local_runtime_registry.register(tool, large_text_tool)
        queued_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="background_large_text_tool",
                    arguments={},
                    mode=ToolMode.BACKGROUND,
                    call_id="call-background-large-text",
                    tool_surface_id="tool_surface:background-large-text",
                ),
            ),
        )

        completed = process_next_background_tool_run(
            self.container,
            worker_id="worker-background-large-text",
        )

        self.assertIsNotNone(completed)
        assert completed is not None
        self.assertEqual(completed.id, queued_run.id)
        self.assertEqual(completed.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(completed.worker_id, "worker-background-large-text")
        self.assertEqual(completed.call_id, "call-background-large-text")
        self.assertEqual(completed.tool_surface_id, "tool_surface:background-large-text")
        assert completed.result is not None
        result_text = completed.result.blocks[0]["text"]
        self.assertIn("[large tool result externalized]", result_text)
        self.assertLess(len(result_text), len(large_text))
        artifact_ids = completed.result.metadata.get("artifact_ids")
        self.assertIsInstance(artifact_ids, list)
        assert isinstance(artifact_ids, list)
        self.assertEqual(completed.result.metadata.get("large_text_artifact_ids"), artifact_ids)
        envelope = completed.result.metadata.get(TOOL_RESULT_ENVELOPE_METADATA_KEY)
        self.assertIsInstance(envelope, dict)
        assert isinstance(envelope, dict)
        self.assertEqual(envelope["status"], "ok")
        self.assertTrue(envelope["truncated"])
        self.assertEqual(envelope["provider_replay_payload"]["artifact_refs"], artifact_ids)
        self.assertEqual(completed.result_envelope_payload["artifact_refs"][0]["artifact_id"], artifact_ids[0])
        artifact = self.artifact_service.get_artifact(str(artifact_ids[0]))
        self.assertEqual(artifact.mime_type, "text/plain")
        self.assertEqual(artifact.metadata["source"], "tool.large_text_result")
        self.assertEqual(self.artifact_service.resolve_variant(artifact.id).path.read_text(), large_text)
        with self.uow_factory() as uow:
            assignment = uow.tool_run_assignments.get_latest_for_run(queued_run.id)
            worker = uow.tool_workers.get("worker-background-large-text")
        self.assertIsNotNone(assignment)
        assert assignment is not None
        self.assertEqual(assignment.status, ToolRunAssignmentStatus.SUCCEEDED)
        self.assertIsNotNone(worker)
        assert worker is not None
        self.assertEqual(worker.current_in_flight, 0)
        self.assertEqual(
            self.dispatch_service.get_task(queued_run.id).status,
            DispatchTaskStatus.COMPLETED,
        )

    def test_background_claim_and_heartbeat_keep_dispatch_lease_in_sync(self) -> None:
        queued_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "lease hello"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )

        claimed = assign_next_background_tool_run(
            self.container,
            worker_id="worker-lease",
        )

        self.assertIsNotNone(claimed)
        assert claimed is not None
        dispatch_task = self.dispatch_service.get_task(queued_run.id)
        self.assertEqual(dispatch_task.status, DispatchTaskStatus.CLAIMED)
        self.assertIsNotNone(dispatch_task.lease_expires_at)
        initial_lease_expires_at = dispatch_task.lease_expires_at
        time.sleep(0.01)

        self.tool_worker_service.heartbeat_run(
            queued_run.id,
            worker_id="worker-lease",
        )

        refreshed_task = self.dispatch_service.get_task(queued_run.id)
        self.assertIsNotNone(refreshed_task.lease_expires_at)
        assert refreshed_task.lease_expires_at is not None
        assert initial_lease_expires_at is not None
        self.assertGreater(refreshed_task.lease_expires_at, initial_lease_expires_at)

        event_names = [
            event.event_name
            for event in self.published_event_bus_events()
            if isinstance(event, Event) and bool(event.name)
        ]
        self.assertIn("tool.run.heartbeated", event_names)
        self.assertIn("tool.assignment.heartbeated", event_names)

    def test_worker_run_loop_processes_multiple_assigned_runs_concurrently(self) -> None:
        active_runs = 0
        max_active_runs = 0
        lock = threading.Lock()

        async def concurrent_echo(arguments: dict[str, object]) -> ToolRunResult:
            nonlocal active_runs, max_active_runs
            with lock:
                active_runs += 1
                max_active_runs = max(max_active_runs, active_runs)
            try:
                await asyncio.sleep(0.1)
                return ToolRunResult.text(
                    str(arguments.get("message") or ""),
                    details={"message": arguments.get("message")},
                )
            finally:
                with lock:
                    active_runs -= 1

        tool = self.seed_tool(
            tool_id="concurrent_echo",
            name="Concurrent Echo",
            description="Sleeps asynchronously before returning.",
            supported_modes=(ToolMode.BACKGROUND,),
            runtime_key="concurrent_echo",
        )
        self.local_runtime_registry.register(tool, concurrent_echo)

        queued_runs = tuple(
            asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="concurrent_echo",
                        arguments={"message": f"concurrent-{index}"},
                        mode=ToolMode.BACKGROUND,
                    ),
                ),
            )
            for index in range(2)
        )
        worker_id = "worker-concurrent"
        self.tool_worker_service.register_worker(
            worker_id=worker_id,
            max_in_flight=2,
        )

        first_assignment = self.tool_scheduler_service.assign_next_available(
            worker_id=worker_id,
        )
        second_assignment = self.tool_scheduler_service.assign_next_available(
            worker_id=worker_id,
        )

        self.assertIsNotNone(first_assignment)
        self.assertIsNotNone(second_assignment)

        processed = self.tool_worker_service.run_until_stopped(
            worker_id=worker_id,
            poll_interval_seconds=0.01,
            max_runs=2,
            max_idle_cycles=5,
            max_in_flight=2,
        )

        self.assertEqual(processed, 2)
        self.assertGreaterEqual(max_active_runs, 2)
        for queued_run in queued_runs:
            persisted = self.tool_service.get_tool_run(queued_run.id)
            self.assertEqual(persisted.status, ToolRunStatus.SUCCEEDED)
            self.assertEqual(persisted.worker_id, worker_id)

    def test_worker_run_loop_processes_image_tools_concurrently(self) -> None:
        active_runs = 0
        max_active_runs = 0
        lock = threading.Lock()

        async def concurrent_image(arguments: dict[str, object]) -> ToolRunResult:
            nonlocal active_runs, max_active_runs
            with lock:
                active_runs += 1
                max_active_runs = max(max_active_runs, active_runs)
            try:
                await asyncio.sleep(0.1)
                return ToolRunResult.text(
                    str(arguments.get("message") or ""),
                    details={"message": arguments.get("message")},
                )
            finally:
                with lock:
                    active_runs -= 1

        tool = self.seed_tool(
            tool_id="concurrent_openai_image",
            name="Concurrent OpenAI Image",
            description="Image-like async background tool.",
            tags=("openai", "image", "generation"),
            supported_modes=(ToolMode.BACKGROUND,),
            runtime_key="concurrent_openai_image",
        )
        self.local_runtime_registry.register(tool, concurrent_image)
        queued_runs = tuple(
            asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="concurrent_openai_image",
                        arguments={"message": f"image-{index}"},
                        mode=ToolMode.BACKGROUND,
                    ),
                ),
            )
            for index in range(2)
        )
        worker_id = "worker-concurrent-image"
        self.tool_worker_service.register_worker(
            worker_id=worker_id,
            max_in_flight=2,
        )
        for _ in queued_runs:
            assigned = self.tool_scheduler_service.assign_next_available(
                worker_id=worker_id,
            )
            self.assertIsNotNone(assigned)

        processed = self.tool_worker_service.run_until_stopped(
            worker_id=worker_id,
            poll_interval_seconds=0.01,
            max_runs=2,
            max_idle_cycles=5,
            max_in_flight=2,
        )

        self.assertEqual(processed, 2)
        self.assertGreaterEqual(max_active_runs, 2)
        for queued_run in queued_runs:
            persisted = self.tool_service.get_tool_run(queued_run.id)
            self.assertEqual(persisted.status, ToolRunStatus.SUCCEEDED)
            self.assertEqual(persisted.worker_id, worker_id)

    def test_scheduler_loop_fills_available_worker_inflight_slots(self) -> None:
        worker_id = "worker-scheduler-slots"
        self.tool_worker_service.register_worker(
            worker_id=worker_id,
            max_in_flight=2,
        )
        queued_runs = tuple(
            asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="echo",
                        arguments={"message": f"slot-{index}"},
                        mode=ToolMode.BACKGROUND,
                    ),
                ),
            )
            for index in range(2)
        )

        assigned_count = self.tool_scheduler_service.run_until_stopped(
            poll_interval_seconds=0.01,
            max_runs=2,
            max_idle_cycles=1,
        )

        self.assertEqual(assigned_count, 2)
        with self.uow_factory() as uow:
            worker = uow.tool_workers.get(worker_id)
            assignments = [
                uow.tool_run_assignments.get_latest_for_run(run.id)
                for run in queued_runs
            ]

        self.assertIsNotNone(worker)
        assert worker is not None
        self.assertEqual(worker.current_in_flight, 2)
        self.assertEqual(
            [assignment.worker_id if assignment is not None else None for assignment in assignments],
            [worker_id, worker_id],
        )
        self.assertEqual(
            [assignment.status if assignment is not None else None for assignment in assignments],
            [ToolRunAssignmentStatus.ASSIGNED, ToolRunAssignmentStatus.ASSIGNED],
        )

    def test_scheduler_does_not_assign_beyond_worker_inflight_limit(self) -> None:
        worker_id = "worker-single-slot"
        self.tool_worker_service.register_worker(
            worker_id=worker_id,
            max_in_flight=1,
        )
        first_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "first"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )
        second_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "second"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )

        first_assignment = self.tool_scheduler_service.assign_next_available(
            worker_id=worker_id,
        )
        second_assignment = self.tool_scheduler_service.assign_next_available(
            worker_id=worker_id,
        )

        self.assertIsNotNone(first_assignment)
        assert first_assignment is not None
        self.assertEqual(first_assignment.id, first_run.id)
        self.assertIsNone(second_assignment)
        with self.uow_factory() as uow:
            worker = uow.tool_workers.get(worker_id)
            assigned = uow.tool_run_assignments.get_latest_for_run(first_run.id)
            blocked = uow.tool_run_assignments.get_latest_for_run(second_run.id)
            second_dispatch_task = uow.dispatch_tasks.get(second_run.id)

        self.assertIsNotNone(worker)
        assert worker is not None
        self.assertEqual(worker.current_in_flight, 1)
        self.assertIsNotNone(assigned)
        self.assertIsNone(blocked)
        self.assertIsNotNone(second_dispatch_task)
        assert second_dispatch_task is not None
        self.assertEqual(second_dispatch_task.status, DispatchTaskStatus.QUEUED)

    def test_scheduler_allows_image_capability_to_fill_worker_slots(self) -> None:
        self.seed_tool(
            tool_id="test_image_generate",
            name="Test Image Generate",
            description="Image-like async background tool.",
            tags=("openai", "image", "generation"),
            supported_modes=(ToolMode.BACKGROUND,),
            runtime_key="test_image_generate",
        )
        worker_id = "worker-image-slots"
        self.tool_worker_service.register_worker(
            worker_id=worker_id,
            max_in_flight=2,
        )
        queued_runs = tuple(
            asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="test_image_generate",
                        arguments={"message": f"image-{index}"},
                        mode=ToolMode.BACKGROUND,
                    ),
                ),
            )
            for index in range(2)
        )

        first = self.tool_scheduler_service.assign_next_available(
            worker_id=worker_id,
        )
        second = self.tool_scheduler_service.assign_next_available(
            worker_id=worker_id,
        )

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual({first.id, second.id}, {run.id for run in queued_runs})
        with self.uow_factory() as uow:
            worker = uow.tool_workers.get(worker_id)
        self.assertIsNotNone(worker)
        assert worker is not None
        self.assertEqual(worker.current_in_flight, 2)

    def test_scheduler_limits_shared_state_tool_assignments(self) -> None:
        self.seed_tool(
            tool_id="test_browser_action",
            name="Test Browser Action",
            description="Browser-like shared state background tool.",
            tags=("browser",),
            supported_modes=(ToolMode.BACKGROUND,),
            runtime_key="test_browser_action",
        )
        worker_id = "worker-browser-limited"
        self.tool_worker_service.register_worker(
            worker_id=worker_id,
            max_in_flight=2,
        )
        queued_runs = tuple(
            asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="test_browser_action",
                        arguments={"message": f"browser-{index}"},
                        mode=ToolMode.BACKGROUND,
                    ),
                ),
            )
            for index in range(2)
        )

        first = self.tool_scheduler_service.assign_next_available(
            worker_id=worker_id,
        )
        second = self.tool_scheduler_service.assign_next_available(
            worker_id=worker_id,
        )

        self.assertIsNotNone(first)
        self.assertIsNone(second)
        with self.uow_factory() as uow:
            worker = uow.tool_workers.get(worker_id)
            first_assignment = uow.tool_run_assignments.get_latest_for_run(
                queued_runs[0].id,
            )
            second_assignment = uow.tool_run_assignments.get_latest_for_run(
                queued_runs[1].id,
            )
        self.assertIsNotNone(worker)
        assert worker is not None
        self.assertEqual(worker.current_in_flight, 1)
        self.assertIsNotNone(first_assignment)
        self.assertIsNone(second_assignment)

    def test_scheduler_skips_blocked_shared_state_head_for_image_run(self) -> None:
        self.seed_tool(
            tool_id="test_browser_snapshot",
            name="Test Browser Snapshot",
            description="Browser-like shared state background tool.",
            tags=("browser",),
            supported_modes=(ToolMode.BACKGROUND,),
            runtime_key="test_browser_snapshot",
        )
        self.seed_tool(
            tool_id="test_openai_image_generate",
            name="Test OpenAI Image Generate",
            description="Image-like async background tool.",
            tags=("openai", "image", "generation"),
            supported_modes=(ToolMode.BACKGROUND,),
            runtime_key="test_openai_image_generate",
        )
        worker_id = "worker-skip-blocked"
        self.tool_worker_service.register_worker(
            worker_id=worker_id,
            max_in_flight=2,
        )
        first_browser = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="test_browser_snapshot",
                    arguments={"message": "browser-active"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )
        queued_browser = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="test_browser_snapshot",
                    arguments={"message": "browser-blocked"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )
        queued_image = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="test_openai_image_generate",
                    arguments={"message": "image-can-run"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )

        first = self.tool_scheduler_service.assign_next_available(
            worker_id=worker_id,
        )
        second = self.tool_scheduler_service.assign_next_available(
            worker_id=worker_id,
        )

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        assert first is not None
        assert second is not None
        self.assertEqual(first.id, first_browser.id)
        self.assertEqual(second.id, queued_image.id)
        with self.uow_factory() as uow:
            blocked_assignment = uow.tool_run_assignments.get_latest_for_run(
                queued_browser.id,
            )
        self.assertIsNone(blocked_assignment)

    def test_scheduler_tries_next_worker_when_first_capability_group_is_full(self) -> None:
        self.seed_tool(
            tool_id="test_browser_page_action",
            name="Test Browser Page Action",
            description="Browser-like shared state background tool.",
            tags=("browser",),
            supported_modes=(ToolMode.BACKGROUND,),
            runtime_key="test_browser_page_action",
        )
        self.seed_tool(
            tool_id="test_image_variation",
            name="Test Image Variation",
            description="Image-like async background tool.",
            tags=("openai", "image", "generation"),
            supported_modes=(ToolMode.BACKGROUND,),
            runtime_key="test_image_variation",
        )
        self.tool_worker_service.register_worker(
            worker_id="worker-cap-a",
            max_in_flight=2,
        )
        self.tool_worker_service.register_worker(
            worker_id="worker-cap-b",
            max_in_flight=2,
        )
        first_browser = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="test_browser_page_action",
                    arguments={"message": "browser-active"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )
        first_image = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="test_image_variation",
                    arguments={"message": "image-active"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )

        assigned_browser = self.tool_scheduler_service.assign_next_available(
            worker_id="worker-cap-a",
        )
        assigned_image = self.tool_scheduler_service.assign_next_available(
            worker_id="worker-cap-b",
        )
        self.assertIsNotNone(assigned_browser)
        self.assertIsNotNone(assigned_image)
        assert assigned_browser is not None
        assert assigned_image is not None
        self.assertEqual(assigned_browser.id, first_browser.id)
        self.assertEqual(assigned_image.id, first_image.id)

        queued_browser = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="test_browser_page_action",
                    arguments={"message": "browser-next-worker"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )

        assigned = self.tool_scheduler_service.assign_next_available()

        self.assertIsNotNone(assigned)
        assert assigned is not None
        self.assertEqual(assigned.id, queued_browser.id)
        self.assertEqual(assigned.worker_id, "worker-cap-b")

    def test_background_async_run_heartbeats_while_sync_handler_blocks(self) -> None:
        handler_entered = threading.Event()
        release_handler = threading.Event()

        def blocking_echo(arguments: dict[str, object]) -> ToolRunResult:
            handler_entered.set()
            release_handler.wait(timeout=2)
            return ToolRunResult.text(
                str(arguments.get("message") or ""),
                details={"message": arguments.get("message")},
            )

        tool = self.seed_tool(
            tool_id="blocking_echo",
            name="Blocking Echo",
            description="Blocks synchronously before returning.",
            supported_modes=(ToolMode.BACKGROUND,),
            runtime_key="blocking_echo",
        )
        self.local_runtime_registry.register(tool, blocking_echo)
        self.tool_service.worker_lease_seconds = 1
        self.tool_service.worker_heartbeat_seconds = 0.02

        queued_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="blocking_echo",
                    arguments={"message": "keep alive"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )

        worker_result: dict[str, object] = {}

        def run_worker() -> None:
            worker_result["run"] = process_next_background_tool_run(
                self.container,
                worker_id="worker-heartbeat-thread",
            )

        thread = threading.Thread(target=run_worker)
        thread.start()

        deadline = time.monotonic() + 2
        initial_heartbeat_at = None
        while time.monotonic() < deadline:
            current = self.tool_service.get_tool_run(queued_run.id)
            if current.status is ToolRunStatus.RUNNING:
                initial_heartbeat_at = current.heartbeat_at
                break
            time.sleep(0.01)
        else:
            self.fail("Tool run never reached RUNNING state.")

        assert initial_heartbeat_at is not None

        heartbeat_advanced = False
        while time.monotonic() < deadline:
            current = self.tool_service.get_tool_run(queued_run.id)
            if (
                current.status is ToolRunStatus.RUNNING
                and current.heartbeat_at is not None
                and current.heartbeat_at > initial_heartbeat_at
            ):
                heartbeat_advanced = True
                break
            if not thread.is_alive():
                break
            time.sleep(0.01)

        release_handler.set()
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertTrue(handler_entered.is_set())
        self.assertTrue(heartbeat_advanced)

        finished = self.tool_service.get_tool_run(queued_run.id)
        self.assertEqual(finished.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(finished.output_payload["message"], "keep alive")
        self.assertIn("run", worker_result)

    def test_executes_local_background_thread_tool_and_updates_lifecycle(self) -> None:

        queued_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "background thread hello"},
                    mode=ToolMode.BACKGROUND,
                    strategy=ToolExecutionStrategy.THREAD,
                ),
            ),
        )

        self.assertEqual(queued_run.status, ToolRunStatus.QUEUED)

        deadline = time.monotonic() + 5
        persisted = None
        while time.monotonic() < deadline:
            if persisted is None or persisted.status is ToolRunStatus.QUEUED:
                process_next_background_tool_run(
                    self.container,
                    worker_id="worker-thread-bg",
                )
            persisted = self.tool_service.get_tool_run(queued_run.id)
            if persisted.status is ToolRunStatus.SUCCEEDED:
                break
            time.sleep(0.05)

        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(persisted.output_payload["message"], "background thread hello")
        self.assertEqual(persisted.result.metadata["process_id"], os.getpid())
        self.assertNotEqual(
            persisted.result.metadata["thread_ident"],
            threading.get_ident(),
        )
        self.assertEqual(persisted.worker_id, "worker-thread-bg")

    def test_executes_local_background_process_tool_and_updates_lifecycle(self) -> None:

        queued_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "background process hello"},
                    mode=ToolMode.BACKGROUND,
                    strategy=ToolExecutionStrategy.PROCESS,
                ),
            ),
        )

        self.assertEqual(queued_run.status, ToolRunStatus.QUEUED)

        deadline = time.monotonic() + 5
        persisted = None
        while time.monotonic() < deadline:
            if persisted is None or persisted.status is ToolRunStatus.QUEUED:
                process_next_background_tool_run(
                    self.container,
                    worker_id="worker-process-bg",
                )
            persisted = self.tool_service.get_tool_run(queued_run.id)
            if persisted.status is ToolRunStatus.SUCCEEDED:
                break
            time.sleep(0.05)

        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(persisted.output_payload["message"], "background process hello")
        self.assertNotEqual(persisted.result.metadata["process_id"], os.getpid())
        self.assertEqual(persisted.worker_id, "worker-process-bg")

    def test_executes_remote_background_async_tool_and_updates_lifecycle(self) -> None:
        self.seed_tool(
            tool_id="remote_echo",
            name="Remote Echo",
            description="Executes through the remote adapter.",
            supported_modes=(ToolMode.INLINE, ToolMode.BACKGROUND),
            supported_environments=(ToolEnvironment.REMOTE,),
            definition_origin=ToolDefinitionOrigin.REMOTE_DISCOVERY,
            runtime_key="remote.echo",
        )

        queued_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="remote_echo",
                    arguments={"message": "remote hello"},
                    mode=ToolMode.BACKGROUND,
                    environment=ToolEnvironment.REMOTE,
                ),
            ),
        )

        self.assertEqual(queued_run.status, ToolRunStatus.QUEUED)

        deadline = time.monotonic() + 5
        persisted = None
        while time.monotonic() < deadline:
            if persisted is None or persisted.status is ToolRunStatus.QUEUED:
                process_next_background_tool_run(
                    self.container,
                    worker_id="worker-remote",
                )
            persisted = self.tool_service.get_tool_run(queued_run.id)
            if persisted.status is ToolRunStatus.SUCCEEDED:
                break
            time.sleep(0.05)

        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(persisted.output_payload["message"], "remote hello")
        self.assertEqual(persisted.result.metadata["environment"], "remote")

    def test_retries_background_run_until_attempt_budget_is_exhausted(self) -> None:
        async def always_fail(arguments: dict[str, object]) -> dict[str, object]:
            raise RuntimeError(f"boom: {arguments.get('message')}")

        tool = self.seed_tool(
            tool_id="always_fail",
            name="Always Fail",
            description="Fails every time.",
            supported_modes=(ToolMode.BACKGROUND,),
            runtime_key="always_fail",
        )
        self.local_runtime_registry.register(tool, always_fail)

        queued_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="always_fail",
                    arguments={"message": "retry me"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )

        self.assertEqual(queued_run.status, ToolRunStatus.QUEUED)

        first_attempt = process_next_background_tool_run(
            self.container,
            worker_id="worker-retry",
        )
        second_attempt = process_next_background_tool_run(
            self.container,
            worker_id="worker-retry",
        )
        final_attempt = process_next_background_tool_run(
            self.container,
            worker_id="worker-retry",
        )

        self.assertIsNotNone(first_attempt)
        self.assertEqual(first_attempt.status, ToolRunStatus.QUEUED)
        self.assertIsNotNone(second_attempt)
        self.assertEqual(second_attempt.status, ToolRunStatus.QUEUED)
        self.assertIsNotNone(final_attempt)
        self.assertEqual(final_attempt.status, ToolRunStatus.FAILED)
        self.assertEqual(final_attempt.attempt_count, 3)
        self.assertIn("boom: retry me", final_attempt.error_message)

        persisted = self.tool_service.get_tool_run(queued_run.id)
        self.assertEqual(persisted.status, ToolRunStatus.FAILED)
        self.assertEqual(persisted.attempt_count, 3)
        self.assertEqual(persisted.max_attempts, 3)
        dispatch_task = self.dispatch_service.get_task(queued_run.id)
        self.assertEqual(dispatch_task.status, DispatchTaskStatus.FAILED)
        with self.uow_factory() as uow:
            assignments = uow.tool_run_assignments.list_for_run(queued_run.id)
            worker = uow.tool_workers.get("worker-retry")
        self.assertEqual(len(assignments), 3)
        self.assertEqual(
            {assignment.status for assignment in assignments},
            {ToolRunAssignmentStatus.FAILED},
        )
        self.assertTrue(
            all("boom: retry me" in (assignment.terminal_reason or "") for assignment in assignments),
        )
        self.assertIsNotNone(worker)
        assert worker is not None
        self.assertEqual(worker.current_in_flight, 0)

    def test_recovers_abandoned_background_run_when_lease_expires(self) -> None:
        queued_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "recover me"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )

        claimed = assign_next_background_tool_run(
            self.container,
            worker_id="worker-abandoned",
        )
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.status, ToolRunStatus.DISPATCHING)
        self.assertEqual(claimed.attempt_count, 1)

        with self.uow_factory() as uow:
            stale = uow.tool_runs.get(queued_run.id)
            dispatch_task = uow.dispatch_tasks.get(queued_run.id)
            self.assertIsNotNone(stale)
            self.assertIsNotNone(dispatch_task)
            stale.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            dispatch_task.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            uow.tool_runs.add(stale)
            uow.dispatch_tasks.add(dispatch_task)
            uow.commit()

        recovered = self.dispatch_service.recover_abandoned_tasks(
            RecoverAbandonedDispatchTasksInput(
                owner_kind="tool_run",
                reason="Worker lease expired before completion.",
            ),
        )
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0].status, DispatchTaskStatus.QUEUED)
        self.assertIsNotNone(self.tool_runtime_event_service)
        assert self.tool_runtime_event_service is not None
        self.publish_outbox_events()
        self.tool_runtime_event_service.process_available_events()

        persisted = self.tool_service.get_tool_run(queued_run.id)
        self.assertEqual(persisted.status, ToolRunStatus.QUEUED)
        self.assertEqual(persisted.error_message, "Worker lease expired before completion.")
        dispatch_task = self.dispatch_service.get_task(queued_run.id)
        self.assertEqual(dispatch_task.status, DispatchTaskStatus.QUEUED)

    def test_recovered_dispatch_failure_exhausts_retry_without_orchestration_side_effect(
        self,
    ) -> None:
        queued_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "recover exhausted"},
                    mode=ToolMode.BACKGROUND,
                    metadata={"orchestration_run_id": "orch-run-not-owned-by-tool"},
                ),
            ),
        )
        claimed = assign_next_background_tool_run(
            self.container,
            worker_id="worker-recovery-exhausted",
        )
        self.assertIsNotNone(claimed)
        assert claimed is not None
        with self.uow_factory() as uow:
            run = uow.tool_runs.get(queued_run.id)
            assert run is not None
            run.max_attempts = run.attempt_count
            uow.tool_runs.add(run)
            uow.collect(run)
            uow.commit()

        recovered = self.tool_worker_service.handle_recovered_dispatch_task(
            tool_run_id=queued_run.id,
            reason="lease expired after final attempt",
        )

        self.assertIsNotNone(recovered)
        assert recovered is not None
        self.assertEqual(recovered.status, ToolRunStatus.FAILED)
        self.assertIn("retry budget exhausted", recovered.error_message)
        dispatch_task = self.dispatch_service.get_task(queued_run.id)
        self.assertEqual(dispatch_task.status, DispatchTaskStatus.FAILED)
        with self.uow_factory() as uow:
            assignment = uow.tool_run_assignments.get_latest_for_run(queued_run.id)
            worker = uow.tool_workers.get("worker-recovery-exhausted")
        self.assertIsNotNone(assignment)
        assert assignment is not None
        self.assertEqual(assignment.status, ToolRunAssignmentStatus.EXPIRED)
        self.assertEqual(assignment.terminal_reason, "lease expired after final attempt")
        self.assertIsNotNone(worker)
        assert worker is not None
        self.assertEqual(worker.current_in_flight, 0)
        with self.assertRaises(OrchestrationRunNotFoundError):
            self.orchestration_run_query_service.get_run("orch-run-not-owned-by-tool")

    def test_can_cancel_queued_background_run(self) -> None:
        queued_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "cancel me"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )

        cancelled = self.tool_service.cancel_tool_run(queued_run.id)

        self.assertEqual(cancelled.status, ToolRunStatus.CANCELLED)
        self.assertIsNotNone(cancelled.cancel_requested_at)
        dispatch_task = self.dispatch_service.get_task(queued_run.id)
        self.assertEqual(dispatch_task.status, DispatchTaskStatus.CANCELLED)
        self.assertIsNone(
            process_next_background_tool_run(
                self.container,
                worker_id="worker-cancel",
            ),
        )

    def test_running_background_run_can_be_cancel_requested(self) -> None:
        async def slow_echo(arguments: dict[str, object]) -> ToolRunResult:
            await asyncio.sleep(0.2)
            return ToolRunResult.text(
                str(arguments.get("message") or ""),
                details={"message": arguments.get("message")},
            )

        tool = self.seed_tool(
            tool_id="slow_echo",
            name="Slow Echo",
            description="Sleeps before returning.",
            supported_modes=(ToolMode.BACKGROUND,),
            runtime_key="slow_echo",
        )
        self.local_runtime_registry.register(tool, slow_echo)

        queued_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="slow_echo",
                    arguments={"message": "cancel later"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )

        worker_result: dict[str, object] = {}

        def run_worker() -> None:
            worker_result["run"] = process_next_background_tool_run(
                self.container,
                worker_id="worker-slow",
            )

        thread = threading.Thread(target=run_worker)
        thread.start()

        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            current = self.tool_service.get_tool_run(queued_run.id)
            if current.status is ToolRunStatus.RUNNING:
                break
            time.sleep(0.01)
        else:
            self.fail("Tool run never reached RUNNING state.")

        requested = self.tool_service.cancel_tool_run(queued_run.id)
        self.assertEqual(requested.status, ToolRunStatus.CANCEL_REQUESTED)

        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertIn("run", worker_result)

        finished = self.tool_service.get_tool_run(queued_run.id)
        self.assertEqual(finished.status, ToolRunStatus.CANCELLED)
        self.assertIsNotNone(finished.cancel_requested_at)
        self.assertEqual(finished.attempt_count, 1)
