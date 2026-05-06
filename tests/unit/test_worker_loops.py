from __future__ import annotations

import unittest

from crxzipple.interfaces.worker_loops import (
    run_daemon_supervisor_loop,
    run_orchestration_executor_loop,
    run_orchestration_scheduler_loop,
    run_tool_scheduler_loop,
    run_tool_worker_loop,
)


class _FakeDaemonManager:
    def __init__(self) -> None:
        self.calls = 0
        self.reconciled_service_keys: list[str] = []

    def resolve_reconcile_service_keys(  # noqa: PLR0913
        self,
        *,
        service_set_keys=(),
        service_keys=(),
        service_roles=(),
        service_groups=(),
        include_eager=True,
    ):
        del service_set_keys, service_roles, service_groups, include_eager
        return tuple(service_keys)

    def reconcile_eager_services(self) -> tuple[object, ...]:
        self.calls += 1
        return (object(),)

    def reconcile_service(self, service_key: str) -> tuple[object, ...]:
        self.reconciled_service_keys.append(service_key)
        return (object(),)


class WorkerLoopsTestCase(unittest.TestCase):
    def test_run_orchestration_executor_loop_prefers_service_owned_run_loop(self) -> None:
        class _FakeExecutorService:
            def __init__(self) -> None:
                self.calls: list[tuple[str, float, int | None, int | None]] = []

            def run_until_stopped(
                self,
                *,
                worker_id: str,
                poll_interval_seconds: float,
                max_runs: int | None = None,
                max_idle_cycles: int | None = None,
                stop_event=None,
            ) -> int:
                del stop_event
                self.calls.append(
                    (
                        worker_id,
                        poll_interval_seconds,
                        max_runs,
                        max_idle_cycles,
                    ),
                )
                return 5

        service = _FakeExecutorService()

        processed = run_orchestration_executor_loop(
            service,
            worker_id="executor-owned-loop",
            poll_interval_seconds=0.5,
            max_runs=2,
            max_idle_cycles=3,
        )

        self.assertEqual(processed, 5)
        self.assertEqual(
            service.calls,
            [("executor-owned-loop", 0.5, 2, 3)],
        )

    def test_run_orchestration_executor_loop_requires_service_owned_run_loop(self) -> None:
        class _FakeExecutorService:
            pass

        with self.assertRaises(AttributeError):
            run_orchestration_executor_loop(
                _FakeExecutorService(),
                worker_id="executor-no-direct-claim",
                poll_interval_seconds=0.01,
                max_runs=1,
            )

    def test_run_orchestration_scheduler_loop_prefers_service_owned_run_loop(self) -> None:
        class _FakeSchedulerService:
            def __init__(self) -> None:
                self.calls: list[tuple[str, float, int | None, int | None]] = []

            def run_until_stopped(
                self,
                *,
                worker_id: str,
                poll_interval_seconds: float,
                max_runs: int | None = None,
                max_idle_cycles: int | None = None,
                stop_event=None,
            ) -> int:
                del stop_event
                self.calls.append(
                    (
                        worker_id,
                        poll_interval_seconds,
                        max_runs,
                        max_idle_cycles,
                    ),
                )
                return 7

            def process_next_available(self, *, worker_id: str):
                raise AssertionError("loop should delegate long-lived scheduler execution to the service")

            def wait_for_work(self, *, timeout_seconds: float, stop_event) -> None:
                raise AssertionError("loop should delegate long-lived scheduler execution to the service")

        service = _FakeSchedulerService()

        processed = run_orchestration_scheduler_loop(
            service,
            worker_id="scheduler-owned-loop",
            poll_interval_seconds=0.25,
            max_runs=3,
            max_idle_cycles=2,
        )

        self.assertEqual(processed, 7)
        self.assertEqual(
            service.calls,
            [("scheduler-owned-loop", 0.25, 3, 2)],
        )

    def test_run_orchestration_scheduler_loop_requires_service_owned_run_loop(self) -> None:
        class _FakeSchedulerService:
            pass

        with self.assertRaises(AttributeError):
            run_orchestration_scheduler_loop(
                _FakeSchedulerService(),
                worker_id="scheduler-no-owned-loop",
                poll_interval_seconds=0.01,
                max_runs=1,
            )

    def test_run_tool_worker_loop_prefers_service_owned_run_loop(self) -> None:
        class _FakeService:
            def __init__(self) -> None:
                self.calls: list[tuple[str, float, int | None, int | None, int]] = []

            def run_until_stopped(
                self,
                *,
                worker_id: str,
                poll_interval_seconds: float,
                max_runs: int | None = None,
                max_idle_cycles: int | None = None,
                stop_event=None,
                events_service=None,
                runtime_event_service=None,
                max_in_flight: int = 1,
            ) -> int:
                del stop_event, events_service, runtime_event_service
                self.calls.append(
                    (
                        worker_id,
                        poll_interval_seconds,
                        max_runs,
                        max_idle_cycles,
                        max_in_flight,
                    ),
                )
                return 11

        service = _FakeService()

        processed = run_tool_worker_loop(
            service,
            worker_id="worker-1",
            poll_interval_seconds=0.5,
            max_runs=2,
            max_idle_cycles=3,
            max_in_flight=4,
        )

        self.assertEqual(processed, 11)
        self.assertEqual(
            service.calls,
            [("worker-1", 0.5, 2, 3, 4)],
        )

    def test_run_tool_worker_loop_requires_service_owned_run_loop(self) -> None:
        class _FakeService:
            pass

        with self.assertRaises(AttributeError):
            run_tool_worker_loop(
                _FakeService(),
                worker_id="worker-no-owned-loop",
                poll_interval_seconds=0.01,
                max_runs=1,
            )

    def test_run_tool_scheduler_loop_prefers_service_owned_run_loop(self) -> None:
        class _FakeService:
            def __init__(self) -> None:
                self.calls: list[tuple[float, int | None, int | None]] = []

            def run_until_stopped(
                self,
                *,
                poll_interval_seconds: float,
                max_runs: int | None = None,
                max_idle_cycles: int | None = None,
                stop_event=None,
                events_service=None,
            ) -> int:
                del stop_event, events_service
                self.calls.append(
                    (
                        poll_interval_seconds,
                        max_runs,
                        max_idle_cycles,
                    ),
                )
                return 13

        service = _FakeService()

        processed = run_tool_scheduler_loop(
            service,
            poll_interval_seconds=0.25,
            max_runs=3,
            max_idle_cycles=2,
        )

        self.assertEqual(processed, 13)
        self.assertEqual(
            service.calls,
            [(0.25, 3, 2)],
        )

    def test_run_tool_scheduler_loop_requires_service_owned_run_loop(self) -> None:
        class _FakeService:
            pass

        with self.assertRaises(AttributeError):
            run_tool_scheduler_loop(
                _FakeService(),
                poll_interval_seconds=0.01,
                max_runs=1,
            )

    def test_run_daemon_supervisor_loop_stops_after_max_cycles(self) -> None:
        manager = _FakeDaemonManager()

        completed_cycles = run_daemon_supervisor_loop(
            manager,
            poll_interval_seconds=0.01,
            max_cycles=3,
        )

        self.assertEqual(completed_cycles, 3)
        self.assertEqual(manager.calls, 0)

    def test_run_daemon_supervisor_loop_can_reconcile_explicit_services(self) -> None:
        manager = _FakeDaemonManager()

        completed_cycles = run_daemon_supervisor_loop(
            manager,
            poll_interval_seconds=0.01,
            service_keys=("host:browser:crxzipple",),
            include_eager=False,
            max_cycles=2,
        )

        self.assertEqual(completed_cycles, 2)
        self.assertEqual(manager.calls, 0)
        self.assertEqual(
            manager.reconciled_service_keys,
            ["host:browser:crxzipple", "host:browser:crxzipple"],
        )

    def test_run_daemon_supervisor_loop_invokes_before_cycle_hook(self) -> None:
        manager = _FakeDaemonManager()
        calls: list[str] = []

        completed_cycles = run_daemon_supervisor_loop(
            manager,
            poll_interval_seconds=0.01,
            max_cycles=3,
            before_cycle=lambda: calls.append("tick"),
        )

        self.assertEqual(completed_cycles, 3)
        self.assertEqual(calls, ["tick", "tick", "tick"])

    def test_run_daemon_supervisor_loop_can_reconcile_by_role_and_group(self) -> None:
        class _FilteringManager(_FakeDaemonManager):
            def resolve_reconcile_service_keys(  # noqa: PLR0913
                self,
                *,
                service_set_keys=(),
                service_keys=(),
                service_roles=(),
                service_groups=(),
                include_eager=True,
            ):
                del service_set_keys, service_keys, include_eager
                if service_roles == ("host",) and service_groups == ("browser",):
                    return ("host:browser:crxzipple",)
                return ()

        manager = _FilteringManager()

        completed_cycles = run_daemon_supervisor_loop(
            manager,
            poll_interval_seconds=0.01,
            service_roles=("host",),
            service_groups=("browser",),
            include_eager=False,
            max_cycles=2,
        )

        self.assertEqual(completed_cycles, 2)
        self.assertEqual(
            manager.reconciled_service_keys,
            ["host:browser:crxzipple", "host:browser:crxzipple"],
        )

    def test_run_daemon_supervisor_loop_can_reconcile_service_sets(self) -> None:
        class _SetManager(_FakeDaemonManager):
            def resolve_reconcile_service_keys(  # noqa: PLR0913
                self,
                *,
                service_set_keys=(),
                service_keys=(),
                service_roles=(),
                service_groups=(),
                include_eager=True,
            ):
                del service_keys, service_roles, service_groups, include_eager
                if service_set_keys == ("workers",):
                    return (
                        "worker:orchestration-scheduler",
                        "worker:orchestration",
                        "worker:tool",
                    )
                return ()

        manager = _SetManager()

        completed_cycles = run_daemon_supervisor_loop(
            manager,
            poll_interval_seconds=0.01,
            service_set_keys=("workers",),
            include_eager=False,
            max_cycles=2,
        )

        self.assertEqual(completed_cycles, 2)
        self.assertEqual(
            manager.reconciled_service_keys,
            [
                "worker:orchestration-scheduler",
                "worker:orchestration",
                "worker:tool",
                "worker:orchestration-scheduler",
                "worker:orchestration",
                "worker:tool",
            ],
        )

    def test_run_daemon_supervisor_loop_can_reconcile_orchestration_runtime_set(self) -> None:
        class _SetManager(_FakeDaemonManager):
            def resolve_reconcile_service_keys(  # noqa: PLR0913
                self,
                *,
                service_set_keys=(),
                service_keys=(),
                service_roles=(),
                service_groups=(),
                include_eager=True,
            ):
                del service_keys, service_roles, service_groups, include_eager
                if service_set_keys == ("orchestration-runtime",):
                    return (
                        "worker:orchestration-scheduler",
                        "worker:orchestration",
                    )
                return ()

        manager = _SetManager()

        completed_cycles = run_daemon_supervisor_loop(
            manager,
            poll_interval_seconds=0.01,
            service_set_keys=("orchestration-runtime",),
            include_eager=False,
            max_cycles=1,
        )

        self.assertEqual(completed_cycles, 1)
        self.assertEqual(
            manager.reconciled_service_keys,
                [
                    "worker:orchestration-scheduler",
                    "worker:orchestration",
                ],
            )


if __name__ == "__main__":
    unittest.main()
