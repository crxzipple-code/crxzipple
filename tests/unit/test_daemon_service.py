from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from crxzipple.core.config import load_settings
from crxzipple.modules.daemon import (
    DaemonApplicationService,
    DaemonInstance,
    DaemonServiceSpec,
    DaemonValidationError,
    FileBackedDaemonInstanceStore,
    FileBackedDaemonLeaseEventLog,
    FileBackedDaemonLeaseStore,
    FileBackedDaemonServiceSpecStore,
    bootstrap_daemon_state_root,
)
from tests.unit.support import SqliteTestHarness


class DaemonServiceTestCase(unittest.TestCase):
    def _build_service(self, root_dir: Path) -> DaemonApplicationService:
        state_root = bootstrap_daemon_state_root(str(root_dir))
        spec_store = FileBackedDaemonServiceSpecStore(
            state_root.config_dir,
            bootstrap_specs=(
                DaemonServiceSpec(
                    key="worker:orchestration",
                    role="worker",
                    service_group="core",
                    managed_by="internal",
                    transport="process",
                    replica_mode="replicated",
                    desired_replicas=1,
                    start_policy="eager",
                    restart_policy="on-failure",
                ),
            ),
        )
        return DaemonApplicationService(
            service_spec_store=spec_store,
            instance_store=FileBackedDaemonInstanceStore(state_root.instances_dir),
            lease_store=FileBackedDaemonLeaseStore(state_root.leases_dir),
            lease_event_log=FileBackedDaemonLeaseEventLog(state_root.leases_dir),
        )

    def test_bootstrap_specs_are_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._build_service(Path(temp_dir))

            specs = service.list_service_specs()

            self.assertEqual(len(specs), 1)
            self.assertEqual(specs[0].key, "worker:orchestration")
            self.assertEqual(specs[0].service_group, "core")

    def test_list_service_specs_supports_role_and_group_filters(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_root = bootstrap_daemon_state_root(str(Path(temp_dir)))
            service = DaemonApplicationService(
                service_spec_store=FileBackedDaemonServiceSpecStore(
                    state_root.config_dir,
                    bootstrap_specs=(
                        DaemonServiceSpec(
                            key="worker:orchestration",
                            role="worker",
                            service_group="core",
                            managed_by="internal",
                            transport="process",
                            replica_mode="replicated",
                            desired_replicas=1,
                            start_policy="eager",
                            restart_policy="on-failure",
                        ),
                        DaemonServiceSpec(
                            key="host:browser:crxzipple",
                            role="host",
                            service_group="browser",
                            managed_by="internal",
                            transport="process",
                            start_policy="ensure",
                            restart_policy="on-failure",
                        ),
                    ),
                ),
                instance_store=FileBackedDaemonInstanceStore(state_root.instances_dir),
                lease_store=FileBackedDaemonLeaseStore(state_root.leases_dir),
            )

            self.assertEqual(
                tuple(spec.key for spec in service.list_service_specs(role="worker")),
                ("worker:orchestration",),
            )
            self.assertEqual(
                tuple(spec.key for spec in service.list_service_specs(service_group="browser")),
                ("host:browser:crxzipple",),
            )

    def test_default_service_sets_are_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._build_service(Path(temp_dir))

            service_sets = service.list_service_sets()

            self.assertEqual(
                tuple(service_set.key for service_set in service_sets),
                (
                    "workers",
                    "orchestration-runtime",
                    "operations-runtime",
                    "channels-stack",
                    "browser-stack",
                    "ocr-stack",
                ),
            )
            self.assertEqual(
                service.get_service_set("operations-runtime").service_keys,
                ("worker:operations-observer",),
            )
            self.assertEqual(service.get_service_set("workers").service_roles, ("worker",))
            self.assertEqual(
                service.get_service_set("orchestration-runtime").service_keys,
                (
                    "worker:orchestration-scheduler",
                    "worker:orchestration",
                ),
            )

    def test_real_orchestration_specs_declare_service_owned_entrypoints(self) -> None:
        harness = SqliteTestHarness()
        try:
            container = harness.build_container()
            specs = {
                spec.key: spec
                for spec in container.daemon_service.list_service_specs(role="worker")
            }

            scheduler_spec = specs["worker:orchestration-scheduler"]
            executor_spec = specs["worker:orchestration"]
            operations_observer_spec = specs["worker:operations-observer"]
            tool_scheduler_spec = specs["worker:tool-scheduler"]
            tool_worker_spec = specs["worker:tool"]

            self.assertEqual(
                scheduler_spec.metadata["application_service"],
                "orchestration_scheduler_service",
            )
            self.assertEqual(
                scheduler_spec.metadata["run_method"],
                "run_until_stopped",
            )
            self.assertEqual(
                scheduler_spec.metadata["cli_args"],
                ["orchestration-scheduler", "run-scheduler"],
            )

            self.assertEqual(
                executor_spec.metadata["application_service"],
                "orchestration_executor_service",
            )
            self.assertEqual(
                executor_spec.metadata["run_method"],
                "run_until_stopped",
            )
            self.assertEqual(
                executor_spec.metadata["cli_args"],
                [
                    "orchestration-executor",
                    "run-executor",
                    "--max-concurrent-assignments",
                    "4",
                ],
            )
            self.assertEqual(
                operations_observer_spec.metadata["application_service"],
                "operations_observer_runtime_event_service",
            )
            self.assertEqual(
                operations_observer_spec.metadata["run_method"],
                "run_until_stopped",
            )
            self.assertEqual(
                operations_observer_spec.metadata["cli_args"],
                ["operations-observer", "run"],
            )
            self.assertEqual(
                tool_scheduler_spec.metadata["application_service"],
                "tool_scheduler_service",
            )
            self.assertEqual(
                tool_scheduler_spec.metadata["run_method"],
                "run_until_stopped",
            )
            self.assertEqual(
                tool_scheduler_spec.metadata["cli_args"],
                ["tool-scheduler", "run-scheduler"],
            )
            self.assertEqual(
                tool_worker_spec.metadata["application_service"],
                "tool_worker_service",
            )
            self.assertEqual(
                tool_worker_spec.metadata["run_method"],
                "run_until_stopped",
            )
            self.assertEqual(
                tool_worker_spec.metadata["cli_args"],
                ["tool-worker", "run", "--max-in-flight", "4"],
            )
        finally:
            harness.close()

    def test_real_tool_worker_spec_uses_configured_inflight_capacity(self) -> None:
        harness = SqliteTestHarness()
        try:
            settings = replace(
                load_settings(),
                tool_worker_max_in_flight=6,
            )
            container = harness.build_container(settings=settings)
            worker_spec = container.daemon_service.get_service_spec("worker:tool")

            self.assertEqual(
                worker_spec.metadata["cli_args"],
                ["tool-worker", "run", "--max-in-flight", "6"],
            )
        finally:
            harness.close()

    def test_real_orchestration_executor_spec_uses_configured_concurrency(self) -> None:
        harness = SqliteTestHarness()
        try:
            settings = replace(
                load_settings(),
                orchestration_executor_max_concurrent_assignments=3,
            )
            container = harness.build_container(settings=settings)
            executor_spec = container.daemon_service.get_service_spec(
                "worker:orchestration",
            )

            self.assertEqual(
                executor_spec.metadata["cli_args"],
                [
                    "orchestration-executor",
                    "run-executor",
                    "--max-concurrent-assignments",
                    "3",
                ],
            )
        finally:
            harness.close()

    def test_real_eager_reconcile_keys_include_split_orchestration_runtimes(self) -> None:
        harness = SqliteTestHarness()
        try:
            container = harness.build_container()

            keys = container.daemon_manager.resolve_reconcile_service_keys(include_eager=True)

            self.assertIn("worker:orchestration-scheduler", keys)
            self.assertIn("worker:orchestration", keys)
            self.assertIn("worker:operations-observer", keys)
            self.assertLess(
                keys.index("worker:orchestration-scheduler"),
                keys.index("worker:orchestration"),
            )
        finally:
            harness.close()

    def test_save_instance_and_acquire_lease(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._build_service(Path(temp_dir))
            instance = DaemonInstance.create(
                service_key="worker:orchestration",
                worker_id="orch-worker-1",
            )
            instance.mark_ready(pid=1111)
            service.save_instance(instance)

            lease = service.acquire_lease(
                service_key="worker:orchestration",
                owner_kind="orchestration_run",
                owner_id="run-1",
                ttl_seconds=15,
            )

            self.assertEqual(lease.service_key, "worker:orchestration")
            self.assertEqual(lease.instance_id, instance.id)
            self.assertEqual(len(service.list_leases(service_key="worker:orchestration")), 1)

    def test_save_instance_uses_atomic_store_update_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._build_service(Path(temp_dir))
            update_calls: list[str] = []
            original_update = service.instance_store.update

            def _wrapped_update(mutator):
                update_calls.append("update")
                return original_update(mutator)

            service.instance_store.update = _wrapped_update
            original_list = service.instance_store.list

            def _unexpected_list():
                raise AssertionError("save_instance should use store.update for atomic mutation")

            service.instance_store.list = _unexpected_list
            try:
                instance = DaemonInstance.create(
                    service_key="worker:orchestration",
                    worker_id="orch-worker-atomic",
                )
                instance.mark_ready(pid=2222)

                service.save_instance(instance)
            finally:
                service.instance_store.list = original_list

            self.assertEqual(update_calls, ["update"])

    def test_list_instances_compacts_inactive_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._build_service(Path(temp_dir))
            active = DaemonInstance.create(
                service_key="worker:orchestration",
                worker_id="active-worker",
                pid=1234,
            )
            active.mark_ready(pid=1234)
            service.save_instance(active)
            for index in range(40):
                stopped = DaemonInstance.create(
                    service_key="worker:orchestration",
                    worker_id=f"stopped-worker-{index}",
                )
                stopped.mark_stopped()
                service.save_instance(stopped)

            instances = service.list_instances(service_key="worker:orchestration")

            active_instances = [instance for instance in instances if instance.status == "ready"]
            stopped_instances = [
                instance for instance in instances if instance.status == "stopped"
            ]
            self.assertEqual(
                [instance.worker_id for instance in active_instances],
                ["active-worker"],
            )
            self.assertEqual(len(stopped_instances), 8)
            self.assertEqual(len(service.instance_store.list()), 9)

    def test_acquire_lease_uses_atomic_store_update_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._build_service(Path(temp_dir))
            instance = DaemonInstance.create(
                service_key="worker:orchestration",
                worker_id="orch-worker-lease",
            )
            instance.mark_ready(pid=3333)
            service.save_instance(instance)

            update_calls: list[str] = []
            original_update = service.lease_store.update

            def _wrapped_update(mutator):
                update_calls.append("update")
                return original_update(mutator)

            service.lease_store.update = _wrapped_update
            original_list = service.lease_store.list

            def _unexpected_list():
                raise AssertionError("acquire_lease should use store.update for atomic mutation")

            service.lease_store.list = _unexpected_list
            try:
                lease = service.acquire_lease(
                    service_key="worker:orchestration",
                    owner_kind="orchestration_run",
                    owner_id="run-atomic",
                    ttl_seconds=15,
                )
            finally:
                service.lease_store.list = original_list

            self.assertEqual(update_calls, ["update"])
            self.assertEqual(lease.instance_id, instance.id)

    def test_acquire_lease_blocks_other_owner_until_released(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._build_service(Path(temp_dir))
            instance = DaemonInstance.create(
                service_key="worker:orchestration",
                worker_id="orch-worker-1",
            )
            instance.mark_ready(pid=1111)
            service.save_instance(instance)

            lease = service.acquire_lease(
                service_key="worker:orchestration",
                owner_kind="orchestration_run",
                owner_id="run-1",
                ttl_seconds=15,
            )

            with self.assertRaises(DaemonValidationError):
                service.acquire_lease(
                    service_key="worker:orchestration",
                    owner_kind="orchestration_run",
                    owner_id="run-2",
                    ttl_seconds=15,
                )

            released = service.release_lease(lease.id)
            self.assertEqual(released.status, "released")
            self.assertEqual(service.list_leases(service_key="worker:orchestration"), ())

            next_lease = service.acquire_lease(
                service_key="worker:orchestration",
                owner_kind="orchestration_run",
                owner_id="run-2",
                ttl_seconds=15,
            )
            self.assertEqual(next_lease.owner_id, "run-2")

    def test_released_leases_move_to_event_log_and_leave_no_active_lease(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._build_service(Path(temp_dir))
            instance = DaemonInstance.create(
                service_key="worker:orchestration",
                worker_id="orch-worker-history",
            )
            instance.mark_ready(pid=4444)
            service.save_instance(instance)

            lease = service.acquire_lease(
                service_key="worker:orchestration",
                owner_kind="orchestration_run",
                owner_id="run-history",
                ttl_seconds=15,
            )
            service.release_lease(lease.id)

            leases = service.list_leases(service_key="worker:orchestration")
            self.assertEqual(leases, ())

            state_root = bootstrap_daemon_state_root(str(Path(temp_dir)))
            events_path = state_root.leases_dir / "lease_events.jsonl"
            event_lines = events_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(event_lines), 2)
            self.assertIn('"event_kind": "acquired"', event_lines[0])
            self.assertIn('"event_kind": "released"', event_lines[1])

    def test_same_owner_reentrant_lease_requires_matching_release_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._build_service(Path(temp_dir))
            instance = DaemonInstance.create(
                service_key="worker:orchestration",
                worker_id="orch-worker-reentrant",
            )
            instance.mark_ready(pid=5555)
            service.save_instance(instance)

            first = service.acquire_lease(
                service_key="worker:orchestration",
                owner_kind="orchestration_run",
                owner_id="run-reentrant",
                ttl_seconds=15,
            )
            second = service.acquire_lease(
                service_key="worker:orchestration",
                owner_kind="orchestration_run",
                owner_id="run-reentrant",
                ttl_seconds=15,
            )

            self.assertEqual(first.id, second.id)
            self.assertEqual(service.list_leases(service_key="worker:orchestration")[0].metadata["_lease_depth"], 2)

            still_active = service.release_lease(first.id)
            self.assertEqual(still_active.status, "active")
            self.assertEqual(still_active.metadata["_lease_depth"], 1)
            self.assertEqual(len(service.list_leases(service_key="worker:orchestration")), 1)

            fully_released = service.release_lease(first.id)
            self.assertEqual(fully_released.status, "released")
            self.assertEqual(service.list_leases(service_key="worker:orchestration"), ())

            state_root = bootstrap_daemon_state_root(str(Path(temp_dir)))
            events_path = state_root.leases_dir / "lease_events.jsonl"
            event_lines = events_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(event_lines), 3)
            self.assertIn('"event_kind": "acquired"', event_lines[0])
            self.assertIn('"event_kind": "acquired"', event_lines[1])
            self.assertIn('"event_kind": "released"', event_lines[2])

    def test_remove_service_specs_prunes_specs_instances_and_leases(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_root = bootstrap_daemon_state_root(str(Path(temp_dir)))
            service = DaemonApplicationService(
                service_spec_store=FileBackedDaemonServiceSpecStore(
                    state_root.config_dir,
                    bootstrap_specs=(
                        DaemonServiceSpec(
                            key="worker:orchestration",
                            role="worker",
                            service_group="core",
                            managed_by="internal",
                            transport="process",
                            start_policy="eager",
                            restart_policy="on-failure",
                            metadata={"cli_args": ["orchestration-executor", "run-executor"]},
                        ),
                        DaemonServiceSpec(
                            key="capability:appium:default",
                            role="capability",
                            service_group="mobile",
                            managed_by="internal",
                            transport="process",
                            start_policy="ensure",
                            restart_policy="on-failure",
                            metadata={"command_argv": ["appium", "server"]},
                        ),
                    ),
                ),
                instance_store=FileBackedDaemonInstanceStore(state_root.instances_dir),
                lease_store=FileBackedDaemonLeaseStore(state_root.leases_dir),
            )
            appium_instance = DaemonInstance.create(service_key="capability:appium:default")
            appium_instance.mark_ready(pid=1234)
            service.save_instance(appium_instance)
            service.acquire_lease(
                service_key="capability:appium:default",
                owner_kind="orchestration_run",
                owner_id="run-1",
                ttl_seconds=15,
            )

            removed = service.remove_service_specs(
                lambda spec: spec.key.startswith("capability:appium:"),
            )

            self.assertEqual(removed, ("capability:appium:default",))
            self.assertEqual(
                tuple(spec.key for spec in service.list_service_specs()),
                ("worker:orchestration",),
            )
            self.assertEqual(service.list_instances(service_key="capability:appium:default"), ())
            self.assertEqual(
                tuple(lease.service_key for lease in service.list_leases()),
                (),
            )

    def test_bootstrap_specs_refresh_existing_service_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_root = bootstrap_daemon_state_root(str(Path(temp_dir)))
            initial_store = FileBackedDaemonServiceSpecStore(
                state_root.config_dir,
                bootstrap_specs=(
                    DaemonServiceSpec(
                        key="worker:orchestration",
                        role="worker",
                        service_group="core",
                        managed_by="internal",
                        transport="process",
                        replica_mode="replicated",
                        desired_replicas=1,
                        start_policy="eager",
                        restart_policy="on-failure",
                        metadata={"entrypoint": "old"},
                    ),
                ),
            )
            initial_store.load()

            refreshed_store = FileBackedDaemonServiceSpecStore(
                state_root.config_dir,
                bootstrap_specs=(
                    DaemonServiceSpec(
                        key="worker:orchestration",
                        role="worker",
                        service_group="core",
                        managed_by="internal",
                        transport="process",
                        replica_mode="replicated",
                        desired_replicas=1,
                        start_policy="eager",
                        restart_policy="on-failure",
                        metadata={"cli_args": ["orchestration-executor", "run-executor"]},
                    ),
                ),
            )

            specs = refreshed_store.load()

            self.assertEqual(len(specs), 1)
            self.assertEqual(
                specs[0].metadata,
                {"cli_args": ["orchestration-executor", "run-executor"]},
            )


if __name__ == "__main__":
    unittest.main()
