from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace as _SimpleNamespace
from unittest.mock import ANY, Mock

from crxzipple.interfaces.runtime_container import AppKey
from crxzipple.modules.daemon import DaemonNotFoundError

from tests.unit.cli_test_support import *


class _NoopChannelControlService:
    def sync_daemon_specs(self) -> tuple[object, ...]:
        return ()


class SimpleNamespace(_SimpleNamespace):
    def require(self, key):  # noqa: ANN001
        value = getattr(key, "value", str(key))
        mapping = {
            "channels.control_service": "channel_control_service",
            "daemon.service": "daemon_service",
            "daemon.manager": "daemon_manager",
            "process.service": "process_service",
        }
        attr = mapping[value]
        if attr == "channel_control_service" and not hasattr(self, attr):
            setattr(self, attr, _NoopChannelControlService())
        return getattr(self, attr)


class DaemonCliTestCase(CliModuleTestCase):
    @staticmethod
    def _process_session(
        *,
        process_id: str = "proc-1",
        status: str = "running",
        command: str = "python -m crxzipple.main daemon supervise-internal",
        session_key: str = "daemon:supervisor",
    ) -> SimpleNamespace:
        timestamp = datetime.now(timezone.utc)
        return SimpleNamespace(
            id=process_id,
            command=command,
            shell="/bin/zsh",
            working_directory="/tmp",
            session_key=session_key,
            metadata={"role": "daemon-supervisor"},
            pid=12345,
            status=SimpleNamespace(value=status),
            exit_code=None,
            created_at=timestamp,
            started_at=timestamp,
            updated_at=timestamp,
            ended_at=None,
            termination_requested_at=None,
            is_running=status == "running",
        )

    def test_daemon_leases_lists_and_filters_status(self) -> None:
        container = SimpleNamespace(
            daemon_service=SimpleNamespace(
                list_leases=lambda **_: (
                    SimpleNamespace(
                        id="lease-1",
                        service_key="host:browser:crxzipple",
                        instance_id="inst-1",
                        owner_kind="browser_profile",
                        owner_id="crxzipple",
                        status="active",
                        acquired_at=None,
                        heartbeat_at=None,
                        expires_at=None,
                        metadata={"profile_name": "crxzipple"},
                    ),
                    SimpleNamespace(
                        id="lease-2",
                        service_key="host:browser:crxzipple",
                        instance_id="inst-1",
                        owner_kind="browser_profile",
                        owner_id="crxzipple",
                        status="released",
                        acquired_at=None,
                        heartbeat_at=None,
                        expires_at=None,
                        metadata={},
                    ),
                ),
            ),
        )

        with patch(
            "crxzipple.modules.daemon.interfaces.cli.ensure_container",
            return_value=container,
        ):
            result = self.runner.invoke(
                app,
                ["daemon", "leases", "--service-key", "host:browser:crxzipple", "--status", "active"],
                env=self.env,
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["id"], "lease-1")
        self.assertEqual(payload[0]["status"], "active")

    def test_daemon_show_returns_service_detail(self) -> None:
        container = SimpleNamespace(
            daemon_service=SimpleNamespace(
                get_service_spec=lambda service_key: SimpleNamespace(
                    key=service_key,
                    display_name="Managed Browser",
                    service_group="browser",
                    role="host",
                    managed_by="internal",
                    transport="process",
                    replica_mode="singleton",
                    desired_replicas=1,
                    start_policy="ensure",
                    restart_policy="on-failure",
                    healthcheck_policy="cdp-version",
                    match_policy="cdp-port",
                    metadata={"cdp_port": 18800},
                ),
                list_leases=lambda **_: (
                    SimpleNamespace(
                        id="lease-1",
                        service_key="host:browser:crxzipple",
                        instance_id="inst-1",
                        owner_kind="browser_profile",
                        owner_id="crxzipple",
                        status="active",
                        acquired_at=None,
                        heartbeat_at=None,
                        expires_at=None,
                        metadata={},
                    ),
                ),
            ),
            daemon_manager=SimpleNamespace(
                list_instances=lambda **_: (
                    SimpleNamespace(
                        id="inst-1",
                        service_key="host:browser:crxzipple",
                        status="failed",
                        worker_id=None,
                        pid=1234,
                        endpoint="http://127.0.0.1:18800",
                        started_at=None,
                        last_healthcheck_at=None,
                        last_error="cdp unavailable",
                        metadata={"browser_pid": 1234},
                    ),
                ),
            ),
        )

        with patch(
            "crxzipple.modules.daemon.interfaces.cli.ensure_container",
            return_value=container,
        ):
            result = self.runner.invoke(
                app,
                ["daemon", "show", "host:browser:crxzipple", "--no-refresh"],
                env=self.env,
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["service"]["key"], "host:browser:crxzipple")
        self.assertEqual(payload["summary"]["availability"], "leased")
        self.assertEqual(payload["summary"]["lease_counts"], {"active": 1})
        self.assertEqual(payload["summary"]["recent_errors"][0]["last_error"], "cdp unavailable")

    def test_daemon_service_sets_lists_predefined_sets(self) -> None:
        container = SimpleNamespace(
            daemon_service=SimpleNamespace(
                list_service_sets=lambda: (
                    SimpleNamespace(
                        key="workers",
                        display_name="Workers",
                        description="All internal worker daemons.",
                        service_keys=(),
                        service_roles=("worker",),
                        service_groups=(),
                    ),
                ),
            ),
        )

        with patch(
            "crxzipple.modules.daemon.interfaces.cli.ensure_container",
            return_value=container,
        ):
            result = self.runner.invoke(app, ["daemon", "service-sets"], env=self.env)

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload[0]["key"], "workers")
        self.assertEqual(payload[0]["service_roles"], ["worker"])

    def test_daemon_services_lists_registered_specs(self) -> None:
        syncer = Mock()
        container = SimpleNamespace(
            channel_control_service=SimpleNamespace(sync_daemon_specs=syncer),
            daemon_service=SimpleNamespace(
                list_service_specs=lambda **_: (
                    SimpleNamespace(
                        key="worker:orchestration",
                        display_name="Orchestration Executor",
                        service_group="core",
                        role="worker",
                        managed_by="internal",
                        transport="process",
                        replica_mode="replicated",
                        desired_replicas=1,
                        start_policy="eager",
                        restart_policy="on-failure",
                        healthcheck_policy=None,
                        match_policy=None,
                        metadata={"cli_args": ["orchestration-executor", "run-executor"]},
                    ),
                ),
            ),
        )

        with patch(
            "crxzipple.modules.daemon.interfaces.cli.ensure_container",
            return_value=container,
        ):
            result = self.runner.invoke(app, ["daemon", "services"], env=self.env)

        self.assertEqual(result.exit_code, 0)
        syncer.assert_called_once_with()
        payload = json.loads(result.stdout)
        self.assertEqual(payload[0]["key"], "worker:orchestration")
        self.assertEqual(payload[0]["service_group"], "core")

    def test_daemon_services_support_role_and_group_filters(self) -> None:
        captured: list[dict[str, object]] = []
        container = SimpleNamespace(
            daemon_service=SimpleNamespace(
                list_service_specs=lambda **kwargs: (
                    captured.append(dict(kwargs)) or (
                        SimpleNamespace(
                            key="host:browser:crxzipple",
                            display_name="Managed Browser",
                            service_group="browser",
                            role="host",
                            managed_by="internal",
                            transport="process",
                            replica_mode="singleton",
                            desired_replicas=1,
                            start_policy="ensure",
                            restart_policy="on-failure",
                            healthcheck_policy=None,
                            match_policy=None,
                            metadata={"cli_args": ["browser", "host", "run", "--profile", "crxzipple"]},
                        ),
                    )
                ),
            ),
        )

        with patch(
            "crxzipple.modules.daemon.interfaces.cli.ensure_container",
            return_value=container,
        ):
            result = self.runner.invoke(
                app,
                ["daemon", "services", "--role", "host", "--group", "browser"],
                env=self.env,
            )

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(captured, [{"role": "host", "service_group": "browser"}])
        payload = json.loads(result.stdout)
        self.assertEqual(payload[0]["service_group"], "browser")

    def test_daemon_ensure_uses_daemon_manager(self) -> None:
        captured_service_keys: list[str] = []
        container = SimpleNamespace(
            daemon_service=SimpleNamespace(list_service_specs=lambda: ()),
            daemon_manager=SimpleNamespace(
                ensure_service=lambda service_key: (
                    captured_service_keys.append(service_key) or (
                        SimpleNamespace(
                            id="inst-1",
                            service_key=service_key,
                            status="ready",
                            worker_id="worker-1",
                            pid=1234,
                            endpoint=None,
                            started_at=None,
                            last_healthcheck_at=None,
                            last_error=None,
                            metadata={"process_id": "proc-1"},
                        ),
                    )
                ),
            ),
        )

        with patch(
            "crxzipple.modules.daemon.interfaces.cli.ensure_container",
            return_value=container,
        ):
            result = self.runner.invoke(
                app,
                ["daemon", "ensure", "worker:orchestration"],
                env=self.env,
            )

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(captured_service_keys, ["worker:orchestration"])
        payload = json.loads(result.stdout)
        self.assertEqual(payload[0]["service_key"], "worker:orchestration")

    def test_daemon_healthcheck_uses_daemon_manager(self) -> None:
        captured_service_keys: list[str] = []
        container = SimpleNamespace(
            daemon_service=SimpleNamespace(list_service_specs=lambda: ()),
            daemon_manager=SimpleNamespace(
                healthcheck_service=lambda service_key: (
                    captured_service_keys.append(service_key) or (
                        SimpleNamespace(
                            id="inst-1",
                            service_key=service_key,
                            status="ready",
                            worker_id="worker-1",
                            pid=1234,
                            endpoint=None,
                            started_at=None,
                            last_healthcheck_at=None,
                            last_error=None,
                            metadata={"process_id": "proc-1"},
                        ),
                    )
                ),
            ),
        )

        with patch(
            "crxzipple.modules.daemon.interfaces.cli.ensure_container",
            return_value=container,
        ):
            result = self.runner.invoke(
                app,
                ["daemon", "healthcheck", "worker:orchestration"],
                env=self.env,
            )

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(captured_service_keys, ["worker:orchestration"])
        payload = json.loads(result.stdout)
        self.assertEqual(payload[0]["service_key"], "worker:orchestration")

    def test_daemon_reconcile_uses_daemon_manager(self) -> None:
        captured_service_keys: list[str] = []
        container = SimpleNamespace(
            daemon_service=SimpleNamespace(list_service_specs=lambda: ()),
            daemon_manager=SimpleNamespace(
                reconcile_service=lambda service_key: (
                    captured_service_keys.append(service_key) or (
                        SimpleNamespace(
                            id="inst-1",
                            service_key=service_key,
                            status="ready",
                            worker_id="worker-1",
                            pid=1234,
                            endpoint=None,
                            started_at=None,
                            last_healthcheck_at=None,
                            last_error=None,
                            metadata={"process_id": "proc-1"},
                        ),
                    )
                ),
            ),
        )

        with patch(
            "crxzipple.modules.daemon.interfaces.cli.ensure_container",
            return_value=container,
        ):
            result = self.runner.invoke(
                app,
                ["daemon", "reconcile", "worker:orchestration"],
                env=self.env,
            )

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(captured_service_keys, ["worker:orchestration"])
        payload = json.loads(result.stdout)
        self.assertEqual(payload[0]["service_key"], "worker:orchestration")

    def test_daemon_run_starts_background_supervisor(self) -> None:
        session = self._process_session()
        process_service = SimpleNamespace(
            list_sessions=Mock(return_value=()),
            start_command=Mock(return_value=session),
            get_session=Mock(return_value=session),
        )
        container = SimpleNamespace(
            daemon_service=SimpleNamespace(
                get_service_set=Mock(),
                get_service_spec=Mock(),
            ),
            process_service=process_service,
        )

        with patch(
            "crxzipple.modules.daemon.interfaces.cli.ensure_container",
            return_value=container,
        ), patch(
            "crxzipple.modules.daemon.interfaces.cli._build_supervisor_process_command",
            return_value="mock-supervisor-command",
        ), patch(
            "crxzipple.modules.daemon.interfaces.cli._resolve_shell_executable",
            return_value="/bin/zsh",
        ):
            result = self.runner.invoke(
                app,
                [
                    "daemon",
                    "run",
                    "--poll-interval-seconds",
                    "1.25",
                    "--max-cycles",
                    "3",
                ],
                env=self.env,
            )

        self.assertEqual(result.exit_code, 0)
        kwargs = process_service.start_command.call_args.kwargs
        self.assertEqual(kwargs["command"], "mock-supervisor-command")
        self.assertEqual(kwargs["session_key"], "daemon:supervisor")
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "started")
        self.assertEqual(payload["supervisor"]["id"], "proc-1")

    def test_daemon_run_rejects_sqlite_without_explicit_runtime_fallback(self) -> None:
        result = self.runner.invoke(
            app,
            ["daemon", "run", "--max-cycles", "1"],
            env=self.env_without_sqlite_runtime_fallback(),
        )

        self.assertEqual(result.exit_code, 1)
        self.assertIn("Refusing to start daemon supervisor with SQLite", result.stderr)
        self.assertIn("APP_ALLOW_SQLITE_RUNTIME_FALLBACK=1", result.stderr)

    def test_daemon_run_returns_active_supervisor_without_restarting(self) -> None:
        session = self._process_session(process_id="proc-running")
        process_service = SimpleNamespace(
            list_sessions=Mock(return_value=(session,)),
            start_command=Mock(),
        )
        container = SimpleNamespace(
            daemon_service=SimpleNamespace(
                get_service_set=Mock(),
                get_service_spec=Mock(),
            ),
            process_service=process_service,
        )

        with patch(
            "crxzipple.modules.daemon.interfaces.cli.ensure_container",
            return_value=container,
        ):
            result = self.runner.invoke(
                app,
                [
                    "daemon",
                    "run",
                ],
                env=self.env,
            )

        self.assertEqual(result.exit_code, 0)
        process_service.start_command.assert_not_called()
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "already_running")
        self.assertEqual(payload["supervisor"]["id"], "proc-running")

    def test_daemon_run_rejects_unknown_service_set_before_starting(self) -> None:
        process_service = SimpleNamespace(
            list_sessions=Mock(return_value=()),
            start_command=Mock(),
        )
        container = SimpleNamespace(
            daemon_service=SimpleNamespace(
                get_service_set=Mock(side_effect=DaemonNotFoundError("Daemon service set 'mobile-stack' is not registered.")),
                get_service_spec=Mock(),
            ),
            process_service=process_service,
        )

        with patch(
            "crxzipple.modules.daemon.interfaces.cli.ensure_container",
            return_value=container,
        ):
            result = self.runner.invoke(
                app,
                ["daemon", "run", "--service-set", "mobile-stack"],
                env=self.env,
            )

        self.assertEqual(result.exit_code, 1)
        process_service.start_command.assert_not_called()
        self.assertIn("mobile-stack", result.stderr)

    def test_daemon_run_reports_supervisor_bootstrap_failure(self) -> None:
        started = self._process_session(process_id="proc-starting")
        failed = self._process_session(process_id="proc-starting", status="failed")
        failed.is_running = False
        failed.exit_code = 1
        failed.ended_at = failed.started_at
        process_service = SimpleNamespace(
            list_sessions=Mock(return_value=()),
            start_command=Mock(return_value=started),
            get_session=Mock(return_value=failed),
            read_output=Mock(
                return_value=SimpleNamespace(
                    process_id="proc-starting",
                    status=SimpleNamespace(value="failed"),
                    exit_code=1,
                    stdout="",
                    stderr="Daemon service set 'mobile-stack' is not registered.",
                    stdout_offset=0,
                    stderr_offset=0,
                    next_stdout_offset=0,
                    next_stderr_offset=49,
                    started_at=failed.started_at,
                    ended_at=failed.ended_at,
                )
            ),
        )
        container = SimpleNamespace(
            daemon_service=SimpleNamespace(
                get_service_set=Mock(),
                get_service_spec=Mock(),
            ),
            process_service=process_service,
        )

        with patch(
            "crxzipple.modules.daemon.interfaces.cli.ensure_container",
            return_value=container,
        ), patch(
            "crxzipple.modules.daemon.interfaces.cli._build_supervisor_process_command",
            return_value="mock-supervisor-command",
        ), patch(
            "crxzipple.modules.daemon.interfaces.cli._resolve_shell_executable",
            return_value="/bin/zsh",
        ), patch(
            "crxzipple.modules.daemon.interfaces.cli._await_supervisor_bootstrap",
            return_value=failed,
        ):
            result = self.runner.invoke(app, ["daemon", "run"], env=self.env)

        self.assertEqual(result.exit_code, 1)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "failed_to_start")
        self.assertEqual(payload["supervisor"]["id"], "proc-starting")
        self.assertIn("mobile-stack", payload["output"]["stderr"])

    def test_daemon_supervise_internal_uses_supervisor_loop(self) -> None:
        syncer = Mock()
        container = SimpleNamespace(
            daemon_manager=SimpleNamespace(),
            channel_control_service=SimpleNamespace(sync_daemon_specs=syncer),
        )

        with patch(
            "crxzipple.modules.daemon.interfaces.cli.ensure_container",
            return_value=container,
        ), patch(
            "crxzipple.modules.daemon.interfaces.cli.run_daemon_supervisor_loop",
        ) as mocked_loop:
            result = self.runner.invoke(
                app,
                [
                    "daemon",
                    "supervise-internal",
                    "--poll-interval-seconds",
                    "1.25",
                    "--max-cycles",
                    "3",
                ],
                env=self.env,
            )

        self.assertEqual(result.exit_code, 0)
        syncer.assert_called_once_with()
        mocked_loop.assert_called_once_with(
            container.require(AppKey.DAEMON_MANAGER),
            poll_interval_seconds=1.25,
            service_set_keys=(),
            service_keys=(),
            service_roles=(),
            service_groups=(),
            include_eager=True,
            max_cycles=3,
            before_cycle=ANY,
        )

    def test_daemon_supervise_internal_can_target_explicit_services(self) -> None:
        container = SimpleNamespace(
            daemon_manager=SimpleNamespace(),
        )

        with patch(
            "crxzipple.modules.daemon.interfaces.cli.ensure_container",
            return_value=container,
        ), patch(
            "crxzipple.modules.daemon.interfaces.cli.run_daemon_supervisor_loop",
        ) as mocked_loop:
            result = self.runner.invoke(
                app,
                [
                    "daemon",
                    "supervise-internal",
                    "--service-key",
                    "host:browser:crxzipple",
                    "--service-key",
                    "host:browser:user",
                    "--no-include-eager",
                    "--max-cycles",
                    "2",
                ],
                env=self.env,
            )

        self.assertEqual(result.exit_code, 0)
        mocked_loop.assert_called_once_with(
            container.require(AppKey.DAEMON_MANAGER),
            poll_interval_seconds=5.0,
            service_set_keys=(),
            service_keys=("host:browser:crxzipple", "host:browser:user"),
            service_roles=(),
            service_groups=(),
            include_eager=False,
            max_cycles=2,
            before_cycle=ANY,
        )

    def test_daemon_supervise_internal_can_target_roles_groups_and_service_sets(self) -> None:
        container = SimpleNamespace(
            daemon_manager=SimpleNamespace(),
        )

        with patch(
            "crxzipple.modules.daemon.interfaces.cli.ensure_container",
            return_value=container,
        ), patch(
            "crxzipple.modules.daemon.interfaces.cli.run_daemon_supervisor_loop",
        ) as mocked_loop:
            result = self.runner.invoke(
                app,
                [
                    "daemon",
                    "supervise-internal",
                    "--service-set",
                    "workers",
                    "--set",
                    "browser-stack",
                    "--role",
                    "host",
                    "--group",
                    "browser",
                    "--max-cycles",
                    "1",
                ],
                env=self.env,
            )

        self.assertEqual(result.exit_code, 0)
        mocked_loop.assert_called_once_with(
            container.require(AppKey.DAEMON_MANAGER),
            poll_interval_seconds=5.0,
            service_set_keys=("workers", "browser-stack"),
            service_keys=(),
            service_roles=("host",),
            service_groups=("browser",),
            include_eager=True,
            max_cycles=1,
            before_cycle=ANY,
        )

    def test_daemon_status_reports_active_supervisor(self) -> None:
        session = self._process_session(process_id="proc-status")
        container = SimpleNamespace(
            process_service=SimpleNamespace(list_sessions=lambda: (session,)),
        )

        with patch(
            "crxzipple.modules.daemon.interfaces.cli.ensure_container",
            return_value=container,
        ):
            result = self.runner.invoke(app, ["daemon", "status"], env=self.env)

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "running")
        self.assertEqual(payload["supervisor"]["id"], "proc-status")

    def test_daemon_status_prefers_lightweight_supervisor_session_listing(self) -> None:
        session = self._process_session(process_id="proc-status-meta")
        process_service = SimpleNamespace(
            list_sessions_metadata=lambda: (session,),
            list_sessions=Mock(side_effect=AssertionError("should not hydrate full sessions")),
        )
        container = SimpleNamespace(process_service=process_service)

        with patch(
            "crxzipple.modules.daemon.interfaces.cli.ensure_container",
            return_value=container,
        ):
            result = self.runner.invoke(app, ["daemon", "status"], env=self.env)

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "running")
        self.assertEqual(payload["supervisor"]["id"], "proc-status-meta")

    def test_daemon_logs_returns_supervisor_output(self) -> None:
        session = self._process_session(process_id="proc-logs")
        output = SimpleNamespace(
            process_id="proc-logs",
            status=SimpleNamespace(value="running"),
            exit_code=None,
            stdout="hello",
            stderr="",
            stdout_offset=0,
            stderr_offset=0,
            next_stdout_offset=5,
            next_stderr_offset=0,
            started_at=session.started_at,
            ended_at=None,
        )
        container = SimpleNamespace(
            process_service=SimpleNamespace(
                list_sessions=lambda: (session,),
                read_output=lambda **_: output,
            ),
        )

        with patch(
            "crxzipple.modules.daemon.interfaces.cli.ensure_container",
            return_value=container,
        ):
            result = self.runner.invoke(app, ["daemon", "logs"], env=self.env)

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "running")
        self.assertEqual(payload["output"]["stdout"], "hello")

    def test_daemon_stop_supervisor_terminates_active_supervisor(self) -> None:
        session = self._process_session(process_id="proc-stop")
        stopped = self._process_session(process_id="proc-stop", status="killed")
        stopped.is_running = False
        stopped.termination_requested_at = stopped.started_at
        process_service = SimpleNamespace(
            list_sessions=lambda: (session,),
            terminate_session=Mock(return_value=stopped),
        )
        container = SimpleNamespace(process_service=process_service)

        with patch(
            "crxzipple.modules.daemon.interfaces.cli.ensure_container",
            return_value=container,
        ):
            result = self.runner.invoke(app, ["daemon", "stop-supervisor"], env=self.env)

        self.assertEqual(result.exit_code, 0)
        process_service.terminate_session.assert_called_once_with(process_id="proc-stop")
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "stopped")
        self.assertEqual(payload["supervisor"]["id"], "proc-stop")

    def test_daemon_shutdown_alias_still_stops_supervisor(self) -> None:
        session = self._process_session(process_id="proc-shutdown")
        stopped = self._process_session(process_id="proc-shutdown", status="killed")
        stopped.is_running = False
        stopped.termination_requested_at = stopped.started_at
        process_service = SimpleNamespace(
            list_sessions=lambda: (session,),
            terminate_session=Mock(return_value=stopped),
        )
        container = SimpleNamespace(process_service=process_service)

        with patch(
            "crxzipple.modules.daemon.interfaces.cli.ensure_container",
            return_value=container,
        ):
            result = self.runner.invoke(app, ["daemon", "shutdown"], env=self.env)

        self.assertEqual(result.exit_code, 0)
        process_service.terminate_session.assert_called_once_with(process_id="proc-shutdown")
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "stopped")
        self.assertEqual(payload["supervisor"]["id"], "proc-shutdown")

    def test_daemon_stop_all_stops_supervisor_and_all_managed_process_services(self) -> None:
        session = self._process_session(process_id="proc-down")
        stopped = self._process_session(process_id="proc-down", status="killed")
        stopped.is_running = False
        stopped.termination_requested_at = stopped.started_at
        stop_calls: list[str] = []

        def stop_service(service_key: str):
            stop_calls.append(service_key)
            return (
                SimpleNamespace(
                    id=f"inst-{service_key}",
                    service_key=service_key,
                    status="stopped",
                    worker_id=None,
                    pid=None,
                    endpoint=None,
                    started_at=None,
                    last_healthcheck_at=None,
                    last_error=None,
                    metadata={},
                ),
            )

        container = SimpleNamespace(
            process_service=SimpleNamespace(
                list_sessions=lambda: (session,),
                terminate_session=Mock(return_value=stopped),
            ),
            daemon_service=SimpleNamespace(
                list_service_specs=lambda: (
                    SimpleNamespace(
                        key="worker:orchestration-scheduler",
                        managed_by="internal",
                        transport="process",
                    ),
                    SimpleNamespace(
                        key="worker:orchestration",
                        managed_by="internal",
                        transport="process",
                    ),
                    SimpleNamespace(
                        key="worker:tool",
                        managed_by="internal",
                        transport="process",
                    ),
                    SimpleNamespace(
                        key="host:browser:crxzipple",
                        managed_by="internal",
                        transport="process",
                    ),
                    SimpleNamespace(
                        key="capability:remote:external",
                        managed_by="external",
                        transport="endpoint",
                    ),
                ),
            ),
            daemon_manager=SimpleNamespace(stop_service=stop_service),
        )

        with patch(
            "crxzipple.modules.daemon.interfaces.cli.ensure_container",
            return_value=container,
        ):
            result = self.runner.invoke(app, ["daemon", "stop-all"], env=self.env)

        self.assertEqual(result.exit_code, 0)
        container.require(AppKey.PROCESS_SERVICE).terminate_session.assert_called_once_with(process_id="proc-down")
        self.assertEqual(
            stop_calls,
            [
                "worker:orchestration-scheduler",
                "worker:orchestration",
                "worker:tool",
                "host:browser:crxzipple",
            ],
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "stopped")
        self.assertEqual(payload["supervisor_status"], "stopped")
        self.assertEqual(
            payload["supervisor"],
            {
                "id": "proc-down",
                "pid": 12345,
                "session_key": "daemon:supervisor",
                "status": "killed",
            },
        )
        self.assertEqual(len(payload["services"]), 4)
        self.assertEqual(
            payload["services"],
            [
                {
                    "service_key": "worker:orchestration-scheduler",
                    "stopped_instance_count": 1,
                },
                {"service_key": "worker:orchestration", "stopped_instance_count": 1},
                {"service_key": "worker:tool", "stopped_instance_count": 1},
                {"service_key": "host:browser:crxzipple", "stopped_instance_count": 1},
            ],
        )

    def test_daemon_down_alias_still_stops_all(self) -> None:
        container = SimpleNamespace(
            process_service=SimpleNamespace(
                list_sessions=lambda: (),
            ),
            daemon_service=SimpleNamespace(
                list_service_specs=lambda: (),
            ),
            daemon_manager=SimpleNamespace(stop_service=Mock()),
        )

        with patch(
            "crxzipple.modules.daemon.interfaces.cli.ensure_container",
            return_value=container,
        ):
            result = self.runner.invoke(app, ["daemon", "down"], env=self.env)

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "stopped")
        self.assertEqual(payload["supervisor_status"], "not_running")
        self.assertIsNone(payload["supervisor"])
        self.assertEqual(payload["services"], [])
