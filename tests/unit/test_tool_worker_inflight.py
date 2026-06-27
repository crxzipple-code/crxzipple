from __future__ import annotations

import asyncio
import unittest

from crxzipple.modules.tool.application.worker_inflight import (
    launch_assignments,
    reap_inflight_tasks,
)


class _Logger:
    def __init__(self) -> None:
        self.warnings: list[dict[str, object] | None] = []

    def warning(self, *args: object, **kwargs: object) -> None:
        del args
        extra = kwargs.get("extra")
        self.warnings.append(extra if isinstance(extra, dict) else None)

    def exception(self, *args: object, **kwargs: object) -> None:
        del args, kwargs


class ToolWorkerInflightTestCase(unittest.TestCase):
    def test_launch_assignments_never_overwrites_existing_inflight_task(self) -> None:
        async def _run_test() -> None:
            completed = asyncio.Event()
            existing_task = asyncio.create_task(completed.wait())
            launched_run_ids: list[str] = []

            def select_runnable_run_ids(
                worker_id: str,
                exclude_run_ids: tuple[str, ...],
                limit: int,
            ) -> tuple[str, ...]:
                self.assertEqual(worker_id, "worker-1")
                self.assertEqual(exclude_run_ids, ("run-existing",))
                self.assertEqual(limit, 2)
                return (
                    "run-existing",
                    "run-a",
                    "run-a",
                    "run-b",
                    "run-c",
                )

            async def perform_assigned_run(run_id: str) -> object:
                launched_run_ids.append(run_id)
                return object()

            inflight_tasks = {"run-existing": existing_task}

            try:
                launched = await launch_assignments(
                    worker_id="worker-1",
                    inflight_tasks=inflight_tasks,
                    max_new_assignments=2,
                    select_runnable_run_ids=select_runnable_run_ids,
                    perform_assigned_run=perform_assigned_run,
                )
                await asyncio.sleep(0)
                await reap_inflight_tasks(inflight_tasks, logger=_Logger())
            finally:
                completed.set()
                await existing_task

            self.assertEqual(launched, 2)
            self.assertIs(inflight_tasks["run-existing"], existing_task)
            self.assertEqual(launched_run_ids, ["run-a", "run-b"])
            self.assertNotIn("run-c", inflight_tasks)

        asyncio.run(_run_test())

    def test_reap_inflight_tasks_removes_cancelled_child_task(self) -> None:
        async def _run_test() -> None:
            task = asyncio.create_task(asyncio.sleep(10))
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            logger = _Logger()
            inflight_tasks = {"run-cancelled": task}

            completed = await reap_inflight_tasks(inflight_tasks, logger=logger)

            self.assertEqual(completed, 1)
            self.assertEqual(inflight_tasks, {})
            self.assertEqual(logger.warnings, [{"run_id": "run-cancelled"}])

        asyncio.run(_run_test())


if __name__ == "__main__":
    unittest.main()
