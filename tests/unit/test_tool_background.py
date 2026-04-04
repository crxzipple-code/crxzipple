from __future__ import annotations

from crxzipple.modules.tool.domain import ToolRunResult

from tests.unit.tool_test_support import *  # noqa: F403


class ToolBackgroundTestCase(ToolTestCaseBase):
    def test_executes_local_background_async_tool_and_updates_lifecycle(self) -> None:
        self.container.tool_service.discover_local_tools()

        queued_run = asyncio.run(
            self.container.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "background hello"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )

        self.assertEqual(queued_run.status, ToolRunStatus.QUEUED)
        dispatch_task = self.container.dispatch_service.get_task(queued_run.id)
        self.assertEqual(dispatch_task.status, DispatchTaskStatus.QUEUED)
        self.assertEqual(dispatch_task.owner_kind, "tool_run")

        deadline = time.monotonic() + 5
        persisted = None
        while time.monotonic() < deadline:
            if persisted is None or persisted.status is ToolRunStatus.QUEUED:
                self.container.tool_service.process_next_queued_run(
                    worker_id="worker-local",
                )
            persisted = self.container.tool_service.get_tool_run(queued_run.id)
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
        completed_dispatch_task = self.container.dispatch_service.get_task(queued_run.id)
        self.assertEqual(completed_dispatch_task.status, DispatchTaskStatus.COMPLETED)

        event_names = [event.name for event in self.container.event_bus.published_events]
        self.assertIn("tool.run.queued", event_names)

    def test_background_claim_and_heartbeat_keep_dispatch_lease_in_sync(self) -> None:
        self.container.tool_service.discover_local_tools()
        queued_run = asyncio.run(
            self.container.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "lease hello"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )

        claimed = self.container.tool_service.claim_next_queued_run(
            worker_id="worker-lease",
        )

        self.assertIsNotNone(claimed)
        assert claimed is not None
        dispatch_task = self.container.dispatch_service.get_task(queued_run.id)
        self.assertEqual(dispatch_task.status, DispatchTaskStatus.CLAIMED)
        self.assertIsNotNone(dispatch_task.lease_expires_at)
        initial_lease_expires_at = dispatch_task.lease_expires_at
        time.sleep(0.01)

        self.container.tool_service.heartbeat_run(
            queued_run.id,
            worker_id="worker-lease",
        )

        refreshed_task = self.container.dispatch_service.get_task(queued_run.id)
        self.assertIsNotNone(refreshed_task.lease_expires_at)
        assert refreshed_task.lease_expires_at is not None
        assert initial_lease_expires_at is not None
        self.assertGreater(refreshed_task.lease_expires_at, initial_lease_expires_at)

    def test_background_async_run_heartbeats_while_sync_handler_blocks(self) -> None:
        def blocking_echo(arguments: dict[str, object]) -> ToolRunResult:
            time.sleep(0.2)
            return ToolRunResult.text(
                str(arguments.get("message") or ""),
                details={"message": arguments.get("message")},
            )

        tool = self.container.tool_service.register(
            RegisterToolInput(
                id="blocking_echo",
                name="Blocking Echo",
                description="Blocks synchronously before returning.",
                supported_modes=(ToolMode.BACKGROUND,),
                runtime_key="blocking_echo",
            ),
        )
        self.container.local_tool_catalog.register(tool, blocking_echo)
        self.container.tool_service.worker_lease_seconds = 1
        self.container.tool_service.worker_heartbeat_seconds = 0.02

        queued_run = asyncio.run(
            self.container.tool_service.execute(
                ExecuteToolInput(
                    tool_id="blocking_echo",
                    arguments={"message": "keep alive"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )

        worker_result: dict[str, object] = {}

        def run_worker() -> None:
            worker_result["run"] = self.container.tool_service.process_next_queued_run(
                worker_id="worker-heartbeat-thread",
            )

        thread = threading.Thread(target=run_worker)
        thread.start()

        deadline = time.monotonic() + 2
        initial_heartbeat_at = None
        while time.monotonic() < deadline:
            current = self.container.tool_service.get_tool_run(queued_run.id)
            if current.status is ToolRunStatus.RUNNING:
                initial_heartbeat_at = current.heartbeat_at
                break
            time.sleep(0.01)
        else:
            self.fail("Tool run never reached RUNNING state.")

        assert initial_heartbeat_at is not None

        heartbeat_advanced = False
        while time.monotonic() < deadline:
            current = self.container.tool_service.get_tool_run(queued_run.id)
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

        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertTrue(heartbeat_advanced)

        finished = self.container.tool_service.get_tool_run(queued_run.id)
        self.assertEqual(finished.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(finished.output_payload["message"], "keep alive")
        self.assertIn("run", worker_result)

    def test_executes_local_background_thread_tool_and_updates_lifecycle(self) -> None:
        self.container.tool_service.discover_local_tools()

        queued_run = asyncio.run(
            self.container.tool_service.execute(
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
                self.container.tool_service.process_next_queued_run(
                    worker_id="worker-thread-bg",
                )
            persisted = self.container.tool_service.get_tool_run(queued_run.id)
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
        self.container.tool_service.discover_local_tools()

        queued_run = asyncio.run(
            self.container.tool_service.execute(
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
                self.container.tool_service.process_next_queued_run(
                    worker_id="worker-process-bg",
                )
            persisted = self.container.tool_service.get_tool_run(queued_run.id)
            if persisted.status is ToolRunStatus.SUCCEEDED:
                break
            time.sleep(0.05)

        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(persisted.output_payload["message"], "background process hello")
        self.assertNotEqual(persisted.result.metadata["process_id"], os.getpid())
        self.assertEqual(persisted.worker_id, "worker-process-bg")

    def test_executes_remote_background_async_tool_and_updates_lifecycle(self) -> None:
        self.container.tool_service.register(
            RegisterToolInput(
                id="remote_echo",
                name="Remote Echo",
                description="Executes through the remote adapter.",
                supported_modes=(ToolMode.INLINE, ToolMode.BACKGROUND),
                supported_environments=(ToolEnvironment.REMOTE,),
                source_kind=ToolSourceKind.REMOTE_REGISTRY,
                runtime_key="remote.echo",
            ),
        )

        queued_run = asyncio.run(
            self.container.tool_service.execute(
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
                self.container.tool_service.process_next_queued_run(
                    worker_id="worker-remote",
                )
            persisted = self.container.tool_service.get_tool_run(queued_run.id)
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

        tool = self.container.tool_service.register(
            RegisterToolInput(
                id="always_fail",
                name="Always Fail",
                description="Fails every time.",
                supported_modes=(ToolMode.BACKGROUND,),
                runtime_key="always_fail",
            ),
        )
        self.container.local_tool_catalog.register(tool, always_fail)

        queued_run = asyncio.run(
            self.container.tool_service.execute(
                ExecuteToolInput(
                    tool_id="always_fail",
                    arguments={"message": "retry me"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )

        self.assertEqual(queued_run.status, ToolRunStatus.QUEUED)

        first_attempt = self.container.tool_service.process_next_queued_run(
            worker_id="worker-retry",
        )
        second_attempt = self.container.tool_service.process_next_queued_run(
            worker_id="worker-retry",
        )
        final_attempt = self.container.tool_service.process_next_queued_run(
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

        persisted = self.container.tool_service.get_tool_run(queued_run.id)
        self.assertEqual(persisted.status, ToolRunStatus.FAILED)
        self.assertEqual(persisted.attempt_count, 3)
        self.assertEqual(persisted.max_attempts, 3)
        dispatch_task = self.container.dispatch_service.get_task(queued_run.id)
        self.assertEqual(dispatch_task.status, DispatchTaskStatus.FAILED)

    def test_recovers_abandoned_background_run_when_lease_expires(self) -> None:
        self.container.tool_service.discover_local_tools()
        queued_run = asyncio.run(
            self.container.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "recover me"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )

        claimed = self.container.tool_service.claim_next_queued_run(
            worker_id="worker-abandoned",
        )
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.status, ToolRunStatus.DISPATCHING)
        self.assertEqual(claimed.attempt_count, 1)

        with self.container.uow_factory() as uow:
            stale = uow.tool_runs.get(queued_run.id)
            dispatch_task = uow.dispatch_tasks.get(queued_run.id)
            self.assertIsNotNone(stale)
            self.assertIsNotNone(dispatch_task)
            stale.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            dispatch_task.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            uow.tool_runs.add(stale)
            uow.dispatch_tasks.add(dispatch_task)
            uow.commit()

        recovered = self.container.dispatch_service.recover_abandoned_tasks(
            RecoverAbandonedDispatchTasksInput(
                owner_kind="tool_run",
                reason="Worker lease expired before completion.",
            ),
        )
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0].status, DispatchTaskStatus.QUEUED)

        persisted = self.container.tool_service.get_tool_run(queued_run.id)
        self.assertEqual(persisted.status, ToolRunStatus.QUEUED)
        self.assertEqual(persisted.error_message, "Worker lease expired before completion.")
        dispatch_task = self.container.dispatch_service.get_task(queued_run.id)
        self.assertEqual(dispatch_task.status, DispatchTaskStatus.QUEUED)

    def test_can_cancel_queued_background_run(self) -> None:
        self.container.tool_service.discover_local_tools()
        queued_run = asyncio.run(
            self.container.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "cancel me"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )

        cancelled = self.container.tool_service.cancel_tool_run(queued_run.id)

        self.assertEqual(cancelled.status, ToolRunStatus.CANCELLED)
        self.assertIsNotNone(cancelled.cancel_requested_at)
        dispatch_task = self.container.dispatch_service.get_task(queued_run.id)
        self.assertEqual(dispatch_task.status, DispatchTaskStatus.CANCELLED)
        self.assertIsNone(
            self.container.tool_service.process_next_queued_run(worker_id="worker-cancel"),
        )

    def test_running_background_run_can_be_cancel_requested(self) -> None:
        async def slow_echo(arguments: dict[str, object]) -> ToolRunResult:
            await asyncio.sleep(0.2)
            return ToolRunResult.text(
                str(arguments.get("message") or ""),
                details={"message": arguments.get("message")},
            )

        tool = self.container.tool_service.register(
            RegisterToolInput(
                id="slow_echo",
                name="Slow Echo",
                description="Sleeps before returning.",
                supported_modes=(ToolMode.BACKGROUND,),
                runtime_key="slow_echo",
            ),
        )
        self.container.local_tool_catalog.register(tool, slow_echo)

        queued_run = asyncio.run(
            self.container.tool_service.execute(
                ExecuteToolInput(
                    tool_id="slow_echo",
                    arguments={"message": "cancel later"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )

        worker_result: dict[str, object] = {}

        def run_worker() -> None:
            worker_result["run"] = self.container.tool_service.process_next_queued_run(
                worker_id="worker-slow",
            )

        thread = threading.Thread(target=run_worker)
        thread.start()

        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            current = self.container.tool_service.get_tool_run(queued_run.id)
            if current.status is ToolRunStatus.RUNNING:
                break
            time.sleep(0.01)
        else:
            self.fail("Tool run never reached RUNNING state.")

        requested = self.container.tool_service.cancel_tool_run(queued_run.id)
        self.assertEqual(requested.status, ToolRunStatus.CANCEL_REQUESTED)

        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertIn("run", worker_result)

        finished = self.container.tool_service.get_tool_run(queued_run.id)
        self.assertEqual(finished.status, ToolRunStatus.CANCELLED)
        self.assertIsNotNone(finished.cancel_requested_at)
        self.assertEqual(finished.attempt_count, 1)
