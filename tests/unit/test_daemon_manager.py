from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from crxzipple.modules.daemon import (
    DaemonApplicationService,
    DaemonInstance,
    DaemonManager,
    DaemonServiceSpec,
    FileBackedDaemonInstanceStore,
    FileBackedDaemonLeaseStore,
    FileBackedDaemonServiceSpecStore,
    bootstrap_daemon_state_root,
)
from crxzipple.modules.process.domain import ProcessSession, ProcessStatus


class _FakeProcessService:
    def __init__(self) -> None:
        self.sessions: dict[str, ProcessSession] = {}
        self.started_commands: list[str] = []

    def start_command(  # noqa: PLR0913
        self,
        *,
        command: str,
        shell: str,
        working_directory: str,
        session_key: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ProcessSession:
        process_id = f"proc-{len(self.sessions) + 1}"
        session = ProcessSession(
            id=process_id,
            command=command,
            shell=shell,
            working_directory=working_directory,
            session_key=session_key,
            metadata=dict(metadata or {}),
            pid=len(self.sessions) + 1000,
            status=ProcessStatus.RUNNING,
        )
        self.sessions[process_id] = session
        self.started_commands.append(command)
        return session

    def get_session(self, *, process_id: str) -> ProcessSession:
        return self.sessions[process_id]

    def list_sessions(self) -> tuple[ProcessSession, ...]:
        return tuple(self.sessions.values())

    def terminate_session(self, *, process_id: str) -> ProcessSession:
        session = self.sessions[process_id]
        session.mark_termination_requested()
        session.mark_exited(exit_code=0)
        return session


class DaemonManagerTestCase(unittest.TestCase):
    def _build_service(self, root_dir: Path) -> DaemonApplicationService:
        state_root = bootstrap_daemon_state_root(str(root_dir))
        spec_store = FileBackedDaemonServiceSpecStore(
            state_root.config_dir,
            bootstrap_specs=(
                DaemonServiceSpec(
                    key="worker:orchestration",
                    role="worker",
                    managed_by="internal",
                    transport="process",
                    replica_mode="replicated",
                    desired_replicas=2,
                    start_policy="eager",
                    restart_policy="on-failure",
                    metadata={"cli_args": ["orchestration-executor", "run-executor"]},
                ),
            ),
        )
        return DaemonApplicationService(
            service_spec_store=spec_store,
            instance_store=FileBackedDaemonInstanceStore(state_root.instances_dir),
            lease_store=FileBackedDaemonLeaseStore(state_root.leases_dir),
        )

    def _build_host_service(self, root_dir: Path) -> DaemonApplicationService:
        state_root = bootstrap_daemon_state_root(str(root_dir))
        spec_store = FileBackedDaemonServiceSpecStore(
            state_root.config_dir,
            bootstrap_specs=(
                DaemonServiceSpec(
                    key="host:browser:crxzipple",
                    role="host",
                    managed_by="internal",
                    transport="process",
                    start_policy="ensure",
                    restart_policy="on-failure",
                    metadata={"cli_args": ["browser", "host", "run", "--profile", "crxzipple"]},
                ),
            ),
        )
        return DaemonApplicationService(
            service_spec_store=spec_store,
            instance_store=FileBackedDaemonInstanceStore(state_root.instances_dir),
            lease_store=FileBackedDaemonLeaseStore(state_root.leases_dir),
        )

    def _build_channel_service(self, root_dir: Path) -> DaemonApplicationService:
        state_root = bootstrap_daemon_state_root(str(root_dir))
        spec_store = FileBackedDaemonServiceSpecStore(
            state_root.config_dir,
            bootstrap_specs=(
                DaemonServiceSpec(
                    key="channel:web",
                    role="host",
                    service_group="channels",
                    managed_by="internal",
                    transport="process",
                    start_policy="eager",
                    restart_policy="on-failure",
                    metadata={
                        "cli_args": [
                            "channel-runtime",
                            "run",
                            "--channel",
                            "web",
                            "--service-key",
                            "channel:web",
                        ]
                    },
                ),
            ),
        )
        return DaemonApplicationService(
            service_spec_store=spec_store,
            instance_store=FileBackedDaemonInstanceStore(state_root.instances_dir),
            lease_store=FileBackedDaemonLeaseStore(state_root.leases_dir),
        )

    def test_ensure_service_starts_desired_worker_replicas(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            daemon_service = self._build_service(Path(temp_dir))
            process_service = _FakeProcessService()
            manager = DaemonManager(
                daemon_service=daemon_service,
                process_service=process_service,
                working_directory=temp_dir,
                shell_resolver=lambda: "/bin/sh",
                python_executable="/usr/bin/python3",
            )

            instances = manager.ensure_service("worker:orchestration")

            self.assertEqual(len(instances), 2)
            self.assertEqual(len(process_service.started_commands), 2)
            self.assertIn("orchestration-executor run-executor --worker-id", process_service.started_commands[0])
            self.assertTrue(all(instance.status == "ready" for instance in instances))

    def test_operations_observer_command_receives_daemon_worker_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_root = bootstrap_daemon_state_root(str(Path(temp_dir)))
            daemon_service = DaemonApplicationService(
                service_spec_store=FileBackedDaemonServiceSpecStore(
                    state_root.config_dir,
                    bootstrap_specs=(
                        DaemonServiceSpec(
                            key="worker:operations-observer",
                            role="worker",
                            service_group="core",
                            managed_by="internal",
                            transport="process",
                            replica_mode="singleton",
                            desired_replicas=1,
                            start_policy="eager",
                            restart_policy="on-failure",
                            metadata={
                                "cli_args": [
                                    "operations-observer",
                                    "run",
                                ],
                            },
                        ),
                    ),
                ),
                instance_store=FileBackedDaemonInstanceStore(state_root.instances_dir),
                lease_store=FileBackedDaemonLeaseStore(state_root.leases_dir),
            )
            process_service = _FakeProcessService()
            manager = DaemonManager(
                daemon_service=daemon_service,
                process_service=process_service,
                working_directory=temp_dir,
                shell_resolver=lambda: "/bin/sh",
                python_executable="/usr/bin/python3",
            )

            instances = manager.ensure_eager_services()

            self.assertEqual(len(instances), 1)
            self.assertEqual(instances[0].worker_id, "worker-operations-observer-1")
            self.assertIn(
                (
                    "/usr/bin/python3 -m crxzipple.main operations-observer "
                    "run --worker-id worker-operations-observer-1"
                ),
                process_service.started_commands[0],
            )
            self.assertEqual(
                process_service.list_sessions()[0].metadata["daemon_worker_id"],
                "worker-operations-observer-1",
            )

    def test_tool_scheduler_command_receives_daemon_worker_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_root = bootstrap_daemon_state_root(str(Path(temp_dir)))
            daemon_service = DaemonApplicationService(
                service_spec_store=FileBackedDaemonServiceSpecStore(
                    state_root.config_dir,
                    bootstrap_specs=(
                        DaemonServiceSpec(
                            key="worker:tool-scheduler",
                            role="worker",
                            service_group="core",
                            managed_by="internal",
                            transport="process",
                            replica_mode="singleton",
                            desired_replicas=1,
                            start_policy="eager",
                            restart_policy="on-failure",
                            metadata={
                                "cli_args": ["tool-scheduler", "run-scheduler"],
                            },
                        ),
                    ),
                ),
                instance_store=FileBackedDaemonInstanceStore(state_root.instances_dir),
                lease_store=FileBackedDaemonLeaseStore(state_root.leases_dir),
            )
            process_service = _FakeProcessService()
            manager = DaemonManager(
                daemon_service=daemon_service,
                process_service=process_service,
                working_directory=temp_dir,
                shell_resolver=lambda: "/bin/sh",
                python_executable="/usr/bin/python3",
            )

            instances = manager.ensure_eager_services()

            self.assertEqual(len(instances), 1)
            self.assertEqual(instances[0].worker_id, "worker-tool-scheduler-1")
            self.assertIn(
                (
                    "/usr/bin/python3 -m crxzipple.main tool-scheduler "
                    "run-scheduler --worker-id worker-tool-scheduler-1"
                ),
                process_service.started_commands[0],
            )
            self.assertEqual(
                process_service.list_sessions()[0].metadata["daemon_worker_id"],
                "worker-tool-scheduler-1",
            )

    def test_stop_service_marks_instances_stopped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            daemon_service = self._build_service(Path(temp_dir))
            process_service = _FakeProcessService()
            manager = DaemonManager(
                daemon_service=daemon_service,
                process_service=process_service,
                working_directory=temp_dir,
                shell_resolver=lambda: "/bin/sh",
                python_executable="/usr/bin/python3",
            )
            manager.ensure_service("worker:orchestration")

            instances = manager.stop_service("worker:orchestration")

            self.assertEqual(len(instances), 2)
            self.assertTrue(all(instance.status == "stopped" for instance in instances))

    def test_stop_service_skips_historical_failed_instances_without_process(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            daemon_service = self._build_host_service(Path(temp_dir))
            process_service = _FakeProcessService()
            manager = DaemonManager(
                daemon_service=daemon_service,
                process_service=process_service,
                working_directory=temp_dir,
                shell_resolver=lambda: "/bin/sh",
                python_executable="/usr/bin/python3",
            )
            ready = manager.ensure_service("host:browser:crxzipple")[0]
            historical = DaemonInstance(
                id="daemon-host-browser-crxzipple-history",
                service_key="host:browser:crxzipple",
                status="failed",
                metadata={},
            )
            daemon_service.save_instance(historical)

            instances = manager.stop_service("host:browser:crxzipple")

            self.assertEqual(len(instances), 1)
            self.assertEqual(instances[0].id, ready.id)
            self.assertEqual(instances[0].status, "stopped")
            saved = daemon_service.get_instance("daemon-host-browser-crxzipple-history")
            self.assertEqual(saved.status, "failed")

    def test_healthcheck_service_refreshes_process_backed_instances(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            daemon_service = self._build_service(Path(temp_dir))
            process_service = _FakeProcessService()
            manager = DaemonManager(
                daemon_service=daemon_service,
                process_service=process_service,
                working_directory=temp_dir,
                shell_resolver=lambda: "/bin/sh",
                python_executable="/usr/bin/python3",
            )
            instances = manager.ensure_service("worker:orchestration")
            first_process_id = instances[0].metadata["process_id"]
            process_service.sessions[first_process_id].mark_exited(exit_code=0)

            refreshed = manager.healthcheck_service("worker:orchestration")

            self.assertEqual(refreshed[0].status, "stopped")
            self.assertEqual(refreshed[1].status, "ready")

    def test_healthcheck_service_discovers_running_process_sessions_without_instance(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            daemon_service = self._build_service(Path(temp_dir))
            process_service = _FakeProcessService()
            process_service.start_command(
                command="PYTHONPATH=src python -m crxzipple.main orchestration-executor run-executor",
                shell="/bin/sh",
                working_directory=temp_dir,
                session_key="daemon:worker:orchestration",
                metadata={
                    "daemon_service_key": "worker:orchestration",
                    "daemon_worker_id": "worker-orchestration-1",
                },
            )
            manager = DaemonManager(
                daemon_service=daemon_service,
                process_service=process_service,
                working_directory=temp_dir,
                shell_resolver=lambda: "/bin/sh",
                python_executable="/usr/bin/python3",
            )

            refreshed = manager.healthcheck_service("worker:orchestration")

            self.assertEqual(len(refreshed), 1)
            self.assertEqual(refreshed[0].status, "ready")
            self.assertEqual(refreshed[0].worker_id, "worker-orchestration-1")
            self.assertIn("process_id", refreshed[0].metadata)

    def test_reconcile_service_trims_extra_worker_replicas(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            daemon_service = self._build_service(Path(temp_dir))
            process_service = _FakeProcessService()
            manager = DaemonManager(
                daemon_service=daemon_service,
                process_service=process_service,
                working_directory=temp_dir,
                shell_resolver=lambda: "/bin/sh",
                python_executable="/usr/bin/python3",
            )
            manager.ensure_service("worker:orchestration")
            daemon_service.register_service_spec(
                DaemonServiceSpec(
                    key="worker:orchestration",
                    role="worker",
                    managed_by="internal",
                    transport="process",
                    replica_mode="replicated",
                    desired_replicas=1,
                    start_policy="eager",
                    restart_policy="on-failure",
                    metadata={"cli_args": ["orchestration-executor", "run-executor"]},
                ),
            )

            instances = manager.reconcile_service("worker:orchestration")

            ready_instances = [instance for instance in instances if instance.status == "ready"]
            stopped_instances = [instance for instance in instances if instance.status == "stopped"]
            self.assertEqual(len(ready_instances), 1)
            self.assertEqual(len(stopped_instances), 1)

    def test_ensure_host_service_does_not_append_worker_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            daemon_service = self._build_host_service(Path(temp_dir))
            process_service = _FakeProcessService()
            manager = DaemonManager(
                daemon_service=daemon_service,
                process_service=process_service,
                working_directory=temp_dir,
                shell_resolver=lambda: "/bin/sh",
                python_executable="/usr/bin/python3",
            )

            instances = manager.ensure_service("host:browser:crxzipple")

            self.assertEqual(len(instances), 1)
            self.assertEqual(instances[0].worker_id, None)
            self.assertIn("browser host run --profile crxzipple", process_service.started_commands[0])
            self.assertNotIn("--worker-id", process_service.started_commands[0])

    def test_ensure_channel_service_uses_channel_runtime_command_without_worker_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            daemon_service = self._build_channel_service(Path(temp_dir))
            process_service = _FakeProcessService()
            manager = DaemonManager(
                daemon_service=daemon_service,
                process_service=process_service,
                working_directory=temp_dir,
                shell_resolver=lambda: "/bin/sh",
                python_executable="/usr/bin/python3",
            )

            instances = manager.ensure_service("channel:web")

            self.assertEqual(len(instances), 1)
            self.assertEqual(instances[0].worker_id, None)
            self.assertIn(
                "channel-runtime run --channel web --service-key channel:web",
                process_service.started_commands[0],
            )
            self.assertNotIn("--worker-id", process_service.started_commands[0])

    def test_reconcile_channel_service_restarts_when_managed_env_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            daemon_service = self._build_channel_service(Path(temp_dir))
            process_service = _FakeProcessService()
            manager = DaemonManager(
                daemon_service=daemon_service,
                process_service=process_service,
                working_directory=temp_dir,
                shell_resolver=lambda: "/bin/sh",
                python_executable="/usr/bin/python3",
            )

            with patch.dict("os.environ", {}, clear=True):
                instances = manager.ensure_service("channel:web")

            self.assertEqual(len(instances), 1)
            original = instances[0]
            original_process_id = original.metadata["process_id"]
            original_env_fingerprint = original.metadata["env_fingerprint"]

            with patch.dict(
                "os.environ",
                {
                    "PYTHONPATH": "src",
                    "APP_EVENTS_BACKEND": "redis",
                    "APP_EVENTS_REDIS_URL": "redis://127.0.0.1:6379/0",
                },
                clear=True,
            ):
                reconciled = manager.reconcile_service("channel:web")

            ready_instances = [instance for instance in reconciled if instance.status == "ready"]
            stopped_instances = [instance for instance in reconciled if instance.status == "stopped"]
            self.assertEqual(len(ready_instances), 1)
            self.assertEqual(len(stopped_instances), 1)
            restarted = ready_instances[0]
            self.assertNotEqual(restarted.metadata["process_id"], original_process_id)
            self.assertNotEqual(
                restarted.metadata["env_fingerprint"],
                original_env_fingerprint,
            )
            self.assertEqual(stopped_instances[0].metadata.get("env_drift_detected"), True)
            self.assertIn("APP_EVENTS_BACKEND=redis", process_service.started_commands[-1])
            self.assertIn(
                "APP_EVENTS_REDIS_URL=redis://127.0.0.1:6379/0",
                process_service.started_commands[-1],
            )
            self.assertIn(
                process_service.sessions[original_process_id].status,
                {ProcessStatus.EXITED, ProcessStatus.KILLED},
            )
            self.assertEqual(len(process_service.started_commands), 2)

    def test_channel_service_includes_spec_env_keys_in_process_command_and_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_root = bootstrap_daemon_state_root(str(Path(temp_dir)))
            daemon_service = DaemonApplicationService(
                service_spec_store=FileBackedDaemonServiceSpecStore(
                    state_root.config_dir,
                    bootstrap_specs=(
                        DaemonServiceSpec(
                            key="channel:lark",
                            role="host",
                            service_group="channels",
                            managed_by="internal",
                            transport="process",
                            start_policy="lazy",
                            restart_policy="on-failure",
                            metadata={
                                "env_keys": [
                                    "LARK_APP_ID",
                                    "LARK_APP_SECRET",
                                ],
                                "cli_args": [
                                    "channel-runtime",
                                    "run",
                                    "--channel",
                                    "lark",
                                    "--service-key",
                                    "channel:lark",
                                ],
                            },
                        ),
                    ),
                ),
                instance_store=FileBackedDaemonInstanceStore(state_root.instances_dir),
                lease_store=FileBackedDaemonLeaseStore(state_root.leases_dir),
            )
            process_service = _FakeProcessService()
            manager = DaemonManager(
                daemon_service=daemon_service,
                process_service=process_service,
                working_directory=temp_dir,
                shell_resolver=lambda: "/bin/sh",
                python_executable="/usr/bin/python3",
            )

            with patch.dict(
                "os.environ",
                {
                    "PYTHONPATH": "src",
                    "APP_DATABASE_URL": "postgresql+psycopg://test:test@127.0.0.1:5432/test",
                    "APP_OPERATIONS_STATE_DIR": "/tmp/crxzipple-ops-test",
                    "APP_TOOL_WORKER_MAX_IN_FLIGHT": "8",
                    "APP_TOOL_WORKER_IMAGE_RUN_CONCURRENCY": "4",
                    "LARK_APP_ID": "cli-test",
                    "LARK_APP_SECRET": "secret-test",
                },
                clear=True,
            ):
                instances = manager.ensure_service("channel:lark")

            self.assertEqual(len(instances), 1)
            self.assertIn(
                "APP_DATABASE_URL=postgresql+psycopg://test:test@127.0.0.1:5432/test",
                process_service.started_commands[0],
            )
            self.assertIn(
                "APP_OPERATIONS_STATE_DIR=/tmp/crxzipple-ops-test",
                process_service.started_commands[0],
            )
            self.assertIn("LARK_APP_ID=cli-test", process_service.started_commands[0])
            self.assertIn("LARK_APP_SECRET=secret-test", process_service.started_commands[0])
            self.assertIn(
                "APP_TOOL_WORKER_MAX_IN_FLIGHT=8",
                process_service.started_commands[0],
            )
            self.assertIn(
                "APP_TOOL_WORKER_IMAGE_RUN_CONCURRENCY=4",
                process_service.started_commands[0],
            )
            env_keys = instances[0].metadata["env_keys"]
            for key in (
                "PYTHONPATH",
                "APP_DATABASE_URL",
                "APP_OPERATIONS_STATE_DIR",
                "APP_EVENTS_BACKEND",
                "APP_EVENTS_REDIS_URL",
                "APP_ORCHESTRATION_RUN_LEASE_SECONDS",
                "APP_TOOL_RUN_LEASE_SECONDS",
                "APP_TOOL_WORKER_MAX_IN_FLIGHT",
                "APP_TOOL_WORKER_DEFAULT_RUN_CONCURRENCY",
                "APP_TOOL_WORKER_IMAGE_RUN_CONCURRENCY",
                "APP_TOOL_WORKER_SHARED_STATE_RUN_CONCURRENCY",
                "LARK_APP_ID",
                "LARK_APP_SECRET",
            ):
                self.assertIn(key, env_keys)
            self.assertEqual(env_keys[-2:], ["LARK_APP_ID", "LARK_APP_SECRET"])

            original_process_id = instances[0].metadata["process_id"]
            original_env_fingerprint = instances[0].metadata["env_fingerprint"]
            with patch.dict(
                "os.environ",
                {
                    "PYTHONPATH": "src",
                    "APP_DATABASE_URL": "postgresql+psycopg://test:test@127.0.0.1:5432/test",
                    "APP_OPERATIONS_STATE_DIR": "/tmp/crxzipple-ops-test",
                    "LARK_APP_ID": "cli-test-updated",
                    "LARK_APP_SECRET": "secret-test",
                },
                clear=True,
            ):
                reconciled = manager.reconcile_service("channel:lark")

            ready_instances = [instance for instance in reconciled if instance.status == "ready"]
            stopped_instances = [instance for instance in reconciled if instance.status == "stopped"]
            self.assertEqual(len(ready_instances), 1)
            self.assertEqual(len(stopped_instances), 1)
            self.assertNotEqual(
                ready_instances[0].metadata["process_id"],
                original_process_id,
            )
            self.assertNotEqual(
                ready_instances[0].metadata["env_fingerprint"],
                original_env_fingerprint,
            )
            self.assertEqual(stopped_instances[0].metadata.get("env_drift_detected"), True)
            self.assertIn(
                "LARK_APP_ID=cli-test-updated",
                process_service.started_commands[-1],
            )

    def test_healthcheck_service_marks_browser_host_ready_via_cdp_probe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_root = bootstrap_daemon_state_root(str(Path(temp_dir)))
            daemon_service = DaemonApplicationService(
                service_spec_store=FileBackedDaemonServiceSpecStore(
                    state_root.config_dir,
                    bootstrap_specs=(
                        DaemonServiceSpec(
                            key="host:browser:crxzipple",
                            role="host",
                            managed_by="internal",
                            transport="process",
                            start_policy="ensure",
                            restart_policy="on-failure",
                            healthcheck_policy="cdp-version",
                            match_policy="cdp-port",
                            metadata={
                                "cli_args": ["browser", "host", "run", "--profile", "crxzipple"],
                                "server_url": "http://127.0.0.1:9222",
                            },
                        ),
                    ),
                ),
                instance_store=FileBackedDaemonInstanceStore(state_root.instances_dir),
                lease_store=FileBackedDaemonLeaseStore(state_root.leases_dir),
            )
            process_service = _FakeProcessService()
            manager = DaemonManager(
                daemon_service=daemon_service,
                process_service=process_service,
                working_directory=temp_dir,
                shell_resolver=lambda: "/bin/sh",
                python_executable="/usr/bin/python3",
                endpoint_probe=lambda **_: None,
            )
            instances = manager.ensure_service("host:browser:crxzipple")

            refreshed = manager.healthcheck_service("host:browser:crxzipple")

            self.assertEqual(len(instances), 1)
            self.assertEqual(len(refreshed), 1)
            self.assertEqual(refreshed[0].status, "ready")
            self.assertEqual(refreshed[0].endpoint, "http://127.0.0.1:9222")

    def test_ensure_process_backed_capability_can_use_raw_command_argv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_root = bootstrap_daemon_state_root(str(Path(temp_dir)))
            daemon_service = DaemonApplicationService(
                service_spec_store=FileBackedDaemonServiceSpecStore(
                    state_root.config_dir,
                    bootstrap_specs=(
                        DaemonServiceSpec(
                            key="capability:chrome-mcp:user",
                            role="capability",
                            service_group="browser",
                            managed_by="internal",
                            transport="process",
                            start_policy="ensure",
                            restart_policy="on-failure",
                            metadata={
                                "command_argv": [
                                    "google-chrome-mcp",
                                    "--port",
                                    "8787",
                                ]
                            },
                        ),
                    ),
                ),
                instance_store=FileBackedDaemonInstanceStore(state_root.instances_dir),
                lease_store=FileBackedDaemonLeaseStore(state_root.leases_dir),
            )
            process_service = _FakeProcessService()
            manager = DaemonManager(
                daemon_service=daemon_service,
                process_service=process_service,
                working_directory=temp_dir,
                shell_resolver=lambda: "/bin/sh",
                python_executable="/usr/bin/python3",
            )

            instances = manager.ensure_service("capability:chrome-mcp:user")

            self.assertEqual(len(instances), 1)
            self.assertEqual(
                process_service.started_commands[0],
                "google-chrome-mcp --port 8787",
            )

    def test_healthcheck_service_attaches_existing_browser_capability_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_root = bootstrap_daemon_state_root(str(Path(temp_dir)))
            daemon_service = DaemonApplicationService(
                service_spec_store=FileBackedDaemonServiceSpecStore(
                    state_root.config_dir,
                    bootstrap_specs=(
                        DaemonServiceSpec(
                            key="capability:chrome-mcp:user",
                            role="capability",
                            service_group="browser",
                            managed_by="external",
                            transport="endpoint",
                            start_policy="attach-only",
                            restart_policy="manual",
                            healthcheck_policy="cdp-version",
                            match_policy="cdp-port",
                            metadata={"server_url": "http://127.0.0.1:9222"},
                        ),
                    ),
                ),
                instance_store=FileBackedDaemonInstanceStore(state_root.instances_dir),
                lease_store=FileBackedDaemonLeaseStore(state_root.leases_dir),
            )
            manager = DaemonManager(
                daemon_service=daemon_service,
                process_service=_FakeProcessService(),
                working_directory=temp_dir,
                shell_resolver=lambda: "/bin/sh",
                python_executable="/usr/bin/python3",
                endpoint_probe=lambda **_: None,
            )

            refreshed = manager.healthcheck_service("capability:chrome-mcp:user")

            self.assertEqual(len(refreshed), 1)
            self.assertEqual(refreshed[0].status, "ready")
            self.assertEqual(refreshed[0].endpoint, "http://127.0.0.1:9222")

    def test_reconcile_process_backed_browser_capability_restarts_killed_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_root = bootstrap_daemon_state_root(str(Path(temp_dir)))
            daemon_service = DaemonApplicationService(
                service_spec_store=FileBackedDaemonServiceSpecStore(
                    state_root.config_dir,
                    bootstrap_specs=(
                        DaemonServiceSpec(
                            key="capability:chrome-mcp:user",
                            role="capability",
                            service_group="browser",
                            managed_by="internal",
                            transport="process",
                            start_policy="ensure",
                            restart_policy="on-failure",
                            healthcheck_policy="cdp-version",
                            metadata={
                                "command_argv": [
                                    "google-chrome-mcp",
                                    "--port",
                                    "8787",
                                ],
                                "server_url": "http://127.0.0.1:8787",
                            },
                        ),
                    ),
                ),
                instance_store=FileBackedDaemonInstanceStore(state_root.instances_dir),
                lease_store=FileBackedDaemonLeaseStore(state_root.leases_dir),
            )
            process_service = _FakeProcessService()

            def _unexpected_probe(**_: object) -> None:
                raise AssertionError("stopped process-backed instances should not run endpoint probe")

            manager = DaemonManager(
                daemon_service=daemon_service,
                process_service=process_service,
                working_directory=temp_dir,
                shell_resolver=lambda: "/bin/sh",
                python_executable="/usr/bin/python3",
                endpoint_probe=_unexpected_probe,
            )
            instances = manager.ensure_service("capability:chrome-mcp:user")
            original_instance_id = instances[0].id
            original_session = process_service.sessions["proc-1"]
            original_session.mark_termination_requested()
            original_session.mark_exited(exit_code=0)

            reconciled = manager.reconcile_service("capability:chrome-mcp:user")

            ready_instances = [instance for instance in reconciled if instance.status == "ready"]
            stopped_instances = [instance for instance in reconciled if instance.status == "stopped"]
            self.assertEqual(len(ready_instances), 1)
            self.assertEqual(len(stopped_instances), 1)
            self.assertEqual(stopped_instances[0].id, original_instance_id)
            self.assertIsNone(stopped_instances[0].pid)
            self.assertNotIn("process_id", stopped_instances[0].metadata)
            self.assertEqual(process_service.started_commands[-1], "google-chrome-mcp --port 8787")

    def test_reconcile_process_backed_browser_capability_ignores_legacy_endpoint_only_ready_instance(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_root = bootstrap_daemon_state_root(str(Path(temp_dir)))
            daemon_service = DaemonApplicationService(
                service_spec_store=FileBackedDaemonServiceSpecStore(
                    state_root.config_dir,
                    bootstrap_specs=(
                        DaemonServiceSpec(
                            key="capability:chrome-mcp:user",
                            role="capability",
                            service_group="browser",
                            managed_by="internal",
                            transport="process",
                            start_policy="ensure",
                            restart_policy="on-failure",
                            healthcheck_policy="cdp-version",
                            metadata={
                                "command_argv": [
                                    "google-chrome-mcp",
                                    "--port",
                                    "8787",
                                ],
                                "server_url": "http://127.0.0.1:8787",
                            },
                        ),
                    ),
                ),
                instance_store=FileBackedDaemonInstanceStore(state_root.instances_dir),
                lease_store=FileBackedDaemonLeaseStore(state_root.leases_dir),
            )
            legacy = DaemonInstance(
                id="daemon-capability-chrome-mcp-user",
                service_key="capability:chrome-mcp:user",
                status="ready",
                endpoint="http://127.0.0.1:8787",
                metadata={"server_url": "http://127.0.0.1:8787"},
            )
            daemon_service.save_instance(legacy)
            process_service = _FakeProcessService()

            manager = DaemonManager(
                daemon_service=daemon_service,
                process_service=process_service,
                working_directory=temp_dir,
                shell_resolver=lambda: "/bin/sh",
                python_executable="/usr/bin/python3",
                endpoint_probe=lambda **_: None,
            )

            reconciled = manager.reconcile_service("capability:chrome-mcp:user")

            ready_instances = [instance for instance in reconciled if instance.status == "ready"]
            stopped_instances = [instance for instance in reconciled if instance.status == "stopped"]
            self.assertEqual(len(ready_instances), 1)
            self.assertEqual(len(stopped_instances), 1)
            self.assertEqual(stopped_instances[0].id, "daemon-capability-chrome-mcp-user")
            self.assertEqual(process_service.started_commands[-1], "google-chrome-mcp --port 8787")

    def test_resolve_reconcile_service_keys_supports_roles_and_groups(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_root = bootstrap_daemon_state_root(str(Path(temp_dir)))
            daemon_service = DaemonApplicationService(
                service_spec_store=FileBackedDaemonServiceSpecStore(
                    state_root.config_dir,
                    bootstrap_specs=(
                        DaemonServiceSpec(
                            key="worker:orchestration-scheduler",
                            role="worker",
                            service_group="core",
                            managed_by="internal",
                            transport="process",
                            replica_mode="singleton",
                            desired_replicas=1,
                            start_policy="eager",
                            restart_policy="on-failure",
                            metadata={"cli_args": ["orchestration-scheduler", "run-scheduler"]},
                        ),
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
                        DaemonServiceSpec(
                            key="host:browser:crxzipple",
                            role="host",
                            service_group="browser",
                            managed_by="internal",
                            transport="process",
                            start_policy="ensure",
                            restart_policy="on-failure",
                            metadata={"cli_args": ["browser", "host", "run", "--profile", "crxzipple"]},
                        ),
                    ),
                ),
                instance_store=FileBackedDaemonInstanceStore(state_root.instances_dir),
                lease_store=FileBackedDaemonLeaseStore(state_root.leases_dir),
            )
            manager = DaemonManager(
                daemon_service=daemon_service,
                process_service=_FakeProcessService(),
                working_directory=temp_dir,
                shell_resolver=lambda: "/bin/sh",
                python_executable="/usr/bin/python3",
            )

            keys = manager.resolve_reconcile_service_keys(
                service_roles=("host",),
                service_groups=("browser",),
                include_eager=False,
            )

            self.assertEqual(keys, ("host:browser:crxzipple",))

    def test_resolve_reconcile_service_keys_supports_service_sets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_root = bootstrap_daemon_state_root(str(Path(temp_dir)))
            daemon_service = DaemonApplicationService(
                service_spec_store=FileBackedDaemonServiceSpecStore(
                    state_root.config_dir,
                    bootstrap_specs=(
                        DaemonServiceSpec(
                            key="worker:orchestration-scheduler",
                            role="worker",
                            service_group="core",
                            managed_by="internal",
                            transport="process",
                            replica_mode="singleton",
                            desired_replicas=1,
                            start_policy="eager",
                            restart_policy="on-failure",
                            metadata={"cli_args": ["orchestration-scheduler", "run-scheduler"]},
                        ),
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
                        DaemonServiceSpec(
                            key="worker:tool",
                            role="worker",
                            service_group="core",
                            managed_by="internal",
                            transport="process",
                            replica_mode="replicated",
                            desired_replicas=1,
                            start_policy="eager",
                            restart_policy="on-failure",
                            metadata={"cli_args": ["tool-worker", "run"]},
                        ),
                    ),
                ),
                instance_store=FileBackedDaemonInstanceStore(state_root.instances_dir),
                lease_store=FileBackedDaemonLeaseStore(state_root.leases_dir),
            )
            manager = DaemonManager(
                daemon_service=daemon_service,
                process_service=_FakeProcessService(),
                working_directory=temp_dir,
                shell_resolver=lambda: "/bin/sh",
                python_executable="/usr/bin/python3",
            )

            keys = manager.resolve_reconcile_service_keys(
                service_set_keys=("workers",),
                include_eager=False,
            )

            self.assertEqual(
                keys,
                (
                    "worker:orchestration-scheduler",
                    "worker:orchestration",
                    "worker:tool",
                ),
            )


if __name__ == "__main__":
    unittest.main()
