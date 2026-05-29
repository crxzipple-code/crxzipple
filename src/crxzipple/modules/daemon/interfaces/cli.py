from __future__ import annotations

from datetime import timezone
import os
from pathlib import Path
import shlex
import shutil
import sys
import time
from typing import Any
import typer

from crxzipple.interfaces.worker_loops import run_daemon_supervisor_loop
from crxzipple.core.config import load_settings
from crxzipple.interfaces.cli.crxzipple import guard_runtime_database
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.daemon import DaemonNotFoundError, DaemonValidationError
from crxzipple.modules.process import ProcessValidationError
from .presenters import (
    instance_payload,
    lease_payload,
    service_detail_payload,
    service_set_payload,
    spec_payload,
)


def _exit_error(exc: Exception) -> None:
    typer.secho(str(exc), err=True, fg=typer.colors.RED)
    raise SystemExit(1) from None


_SUPERVISOR_SESSION_KEY = "daemon:supervisor"
_DAEMON_CONTAINER_KEY = "daemon_runtime_container"


def ensure_container(ctx: typer.Context) -> Any:
    from crxzipple.interfaces.runtime_container import (
        AssemblyTarget,
        ensure_typer_runtime_container,
    )

    return ensure_typer_runtime_container(
        ctx,
        target=AssemblyTarget.DAEMON_SUPERVISOR,
        key=_DAEMON_CONTAINER_KEY,
    )


def _daemon_service(container: Any) -> Any:
    from crxzipple.interfaces.runtime_container import AppKey

    return container.require(AppKey.DAEMON_SERVICE)


def _daemon_manager(container: Any) -> Any:
    from crxzipple.interfaces.runtime_container import AppKey

    return container.require(AppKey.DAEMON_MANAGER)


def _process_service(container: Any) -> Any:
    from crxzipple.interfaces.runtime_container import AppKey

    return container.require(AppKey.PROCESS_SERVICE)


def _channel_control_service(container: Any) -> Any:
    from crxzipple.interfaces.runtime_container import AppKey

    return container.require(AppKey.CHANNEL_CONTROL_SERVICE)


def _process_session_payload(session) -> dict[str, object]:  # noqa: ANN001
    return {
        "id": session.id,
        "command": session.command,
        "shell": session.shell,
        "working_directory": session.working_directory,
        "session_key": session.session_key,
        "metadata": dict(session.metadata),
        "pid": session.pid,
        "status": session.status.value,
        "exit_code": session.exit_code,
        "created_at": session.created_at.isoformat(),
        "started_at": session.started_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "ended_at": session.ended_at.isoformat() if session.ended_at is not None else None,
        "termination_requested_at": (
            session.termination_requested_at.isoformat()
            if session.termination_requested_at is not None
            else None
        ),
    }


def _process_output_payload(output) -> dict[str, object]:  # noqa: ANN001
    return {
        "process_id": output.process_id,
        "status": output.status.value,
        "exit_code": output.exit_code,
        "stdout": output.stdout,
        "stderr": output.stderr,
        "stdout_offset": output.stdout_offset,
        "stderr_offset": output.stderr_offset,
        "next_stdout_offset": output.next_stdout_offset,
        "next_stderr_offset": output.next_stderr_offset,
        "started_at": output.started_at.isoformat(),
        "ended_at": output.ended_at.isoformat() if output.ended_at is not None else None,
    }


def _process_session_summary(session) -> dict[str, object] | None:  # noqa: ANN001
    if session is None:
        return None
    return {
        "id": session.id,
        "pid": session.pid,
        "session_key": session.session_key,
        "status": session.status.value,
    }


def _resolve_shell_executable() -> str:
    preferred = os.environ.get("SHELL", "").strip()
    if preferred:
        preferred_name = Path(preferred).name.lower()
        if preferred_name in {"sh", "bash", "zsh"}:
            resolved = shutil.which(preferred)
            if resolved:
                return resolved
    fallback = shutil.which("/bin/sh") or shutil.which("sh")
    if fallback:
        return fallback
    raise typer.BadParameter("No POSIX shell is available for daemon supervisor start.")


def _normalized_tuple(items: list[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for item in items:
        candidate = item.strip().lower()
        if not candidate or candidate in normalized:
            continue
        normalized.append(candidate)
    return tuple(normalized)


def _list_supervisor_sessions(process_service) -> tuple[object, ...]:  # noqa: ANN001
    list_sessions = getattr(process_service, "list_sessions_metadata", None)
    if list_sessions is None:
        list_sessions = process_service.list_sessions
    sessions = [
        session
        for session in list_sessions()
        if (session.session_key or "").strip().lower() == _SUPERVISOR_SESSION_KEY
    ]
    sessions.sort(
        key=lambda session: (
            session.started_at.astimezone(timezone.utc)
            if session.started_at.tzinfo is not None
            else session.started_at.replace(tzinfo=timezone.utc)
        ),
        reverse=True,
    )
    return tuple(sessions)


def _active_supervisor_session(process_service):  # noqa: ANN001
    for session in _list_supervisor_sessions(process_service):
        if session.is_running:
            return session
    return None


def _latest_supervisor_session(process_service):  # noqa: ANN001
    sessions = _list_supervisor_sessions(process_service)
    return sessions[0] if sessions else None


def _build_supervisor_process_command(
    *,
    poll_interval_seconds: float,
    service_set_keys: tuple[str, ...],
    service_keys: tuple[str, ...],
    service_roles: tuple[str, ...],
    service_groups: tuple[str, ...],
    include_eager: bool,
    max_cycles: int | None,
) -> str:
    argv: list[str] = [
        sys.executable,
        "-m",
        "crxzipple.main",
        "daemon",
        "supervise-internal",
        "--poll-interval-seconds",
        str(poll_interval_seconds),
    ]
    for item in service_set_keys:
        argv.extend(["--service-set", item])
    for item in service_keys:
        argv.extend(["--service-key", item])
    for item in service_roles:
        argv.extend(["--role", item])
    for item in service_groups:
        argv.extend(["--group", item])
    if not include_eager:
        argv.append("--no-include-eager")
    if max_cycles is not None:
        argv.extend(["--max-cycles", str(max_cycles)])
    command = shlex.join(argv)
    pythonpath = os.environ.get("PYTHONPATH", "").strip()
    if pythonpath:
        return f"PYTHONPATH={shlex.quote(pythonpath)} {command}"
    return command


def _managed_process_service_keys(daemon_service) -> tuple[str, ...]:  # noqa: ANN001
    keys: list[str] = []
    for spec in daemon_service.list_service_specs():
        if spec.managed_by != "internal" or spec.transport != "process":
            continue
        if spec.key in keys:
            continue
        keys.append(spec.key)
    return tuple(keys)


def _validate_supervisor_targets(
    daemon_service,  # noqa: ANN001
    *,
    service_set_keys: tuple[str, ...],
    service_keys: tuple[str, ...],
) -> None:
    for service_set_key in service_set_keys:
        daemon_service.get_service_set(service_set_key)
    for service_key in service_keys:
        daemon_service.get_service_spec(service_key)


def _await_supervisor_bootstrap(
    process_service,  # noqa: ANN001
    *,
    process_id: str,
    wait_seconds: float = 0.75,
):
    deadline = time.monotonic() + max(float(wait_seconds), 0.0)
    session = process_service.get_session(process_id=process_id)
    while session.is_running and time.monotonic() < deadline:
        time.sleep(0.1)
        session = process_service.get_session(process_id=process_id)
    return session


def _sync_managed_specs(container) -> None:  # noqa: ANN001
    _channel_control_service(container).sync_daemon_specs()


def build_cli() -> typer.Typer:
    app = typer.Typer(help="Manage daemon services and instances.", no_args_is_help=True)

    @app.command("service-sets")
    def list_service_sets(ctx: typer.Context) -> None:
        container = ensure_container(ctx)
        _sync_managed_specs(container)
        echo_data(
            [
                service_set_payload(service_set)
                for service_set in _daemon_service(container).list_service_sets()
            ]
        )

    @app.command("services")
    def list_services(
        ctx: typer.Context,
        role: str | None = typer.Option(None, "--role", help="Optional daemon role filter."),
        service_group: str | None = typer.Option(
            None,
            "--group",
            help="Optional daemon service group filter.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        _sync_managed_specs(container)
        echo_data(
            [
                spec_payload(spec)
                for spec in _daemon_service(container).list_service_specs(
                    role=role,
                    service_group=service_group,
                )
            ]
        )

    @app.command("instances")
    def list_instances(
        ctx: typer.Context,
        service_key: str | None = typer.Option(
            None,
            "--service-key",
            help="Optional daemon service key filter.",
        ),
        refresh: bool = typer.Option(
            True,
            "--refresh/--no-refresh",
            help="Refresh process-backed daemon state before listing.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        _sync_managed_specs(container)
        try:
            instances = _daemon_manager(container).list_instances(
                service_key=service_key,
                refresh=refresh,
            )
        except (DaemonValidationError, DaemonNotFoundError) as exc:
            _exit_error(exc)
        echo_data([instance_payload(instance) for instance in instances])

    @app.command("leases")
    def list_leases(
        ctx: typer.Context,
        service_key: str | None = typer.Option(
            None,
            "--service-key",
            help="Optional daemon service key filter.",
        ),
        status: str | None = typer.Option(
            None,
            "--status",
            help="Optional current lease status filter. Runtime leases only retain active entries.",
        ),
        owner_kind: str | None = typer.Option(
            None,
            "--owner-kind",
            help="Optional lease owner kind filter.",
        ),
        owner_id: str | None = typer.Option(
            None,
            "--owner-id",
            help="Optional lease owner id filter.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        leases = _daemon_service(container).list_leases(service_key=service_key)
        if status is not None:
            normalized_status = status.strip().lower()
            leases = tuple(lease for lease in leases if lease.status == normalized_status)
        if owner_kind is not None:
            normalized_owner_kind = owner_kind.strip().lower()
            leases = tuple(
                lease for lease in leases if lease.owner_kind == normalized_owner_kind
            )
        if owner_id is not None:
            normalized_owner_id = owner_id.strip().lower()
            leases = tuple(lease for lease in leases if lease.owner_id == normalized_owner_id)
        echo_data([lease_payload(lease) for lease in leases])

    @app.command("show")
    def show_service(
        ctx: typer.Context,
        service_key: str = typer.Argument(..., help="Daemon service key."),
        refresh: bool = typer.Option(
            True,
            "--refresh/--no-refresh",
            help="Refresh daemon instances before building the service detail view.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        _sync_managed_specs(container)
        try:
            daemon_service = _daemon_service(container)
            spec = daemon_service.get_service_spec(service_key)
            instances = _daemon_manager(container).list_instances(
                service_key=service_key,
                refresh=refresh,
            )
            leases = daemon_service.list_leases(service_key=service_key)
        except (DaemonValidationError, DaemonNotFoundError) as exc:
            _exit_error(exc)
        echo_data(
            service_detail_payload(
                spec=spec,
                instances=instances,
                leases=leases,
            )
        )

    @app.command("ensure")
    def ensure_service(
        ctx: typer.Context,
        service_key: str = typer.Argument(..., help="Daemon service key."),
    ) -> None:
        guard_runtime_database(load_settings(), runtime_name="daemon supervisor")
        container = ensure_container(ctx)
        _sync_managed_specs(container)
        try:
            instances = _daemon_manager(container).ensure_service(service_key)
        except (DaemonValidationError, DaemonNotFoundError) as exc:
            _exit_error(exc)
        echo_data([instance_payload(instance) for instance in instances])

    @app.command("healthcheck")
    def healthcheck_service(
        ctx: typer.Context,
        service_key: str = typer.Argument(..., help="Daemon service key."),
    ) -> None:
        container = ensure_container(ctx)
        _sync_managed_specs(container)
        try:
            instances = _daemon_manager(container).healthcheck_service(service_key)
        except (DaemonValidationError, DaemonNotFoundError) as exc:
            _exit_error(exc)
        echo_data([instance_payload(instance) for instance in instances])

    @app.command("reconcile")
    def reconcile_service(
        ctx: typer.Context,
        service_key: str = typer.Argument(..., help="Daemon service key."),
    ) -> None:
        container = ensure_container(ctx)
        _sync_managed_specs(container)
        try:
            instances = _daemon_manager(container).reconcile_service(service_key)
        except (DaemonValidationError, DaemonNotFoundError) as exc:
            _exit_error(exc)
        echo_data([instance_payload(instance) for instance in instances])

    @app.command("run")
    def run_supervisor(
        ctx: typer.Context,
        poll_interval_seconds: float = typer.Option(
            5.0,
            "--poll-interval-seconds",
            min=0.1,
            help="Idle wait time between eager daemon reconciliation cycles.",
        ),
        service_set: list[str] = typer.Option(
            [],
            "--service-set",
            "--set",
            help="Predefined daemon service set to reconcile every cycle. Repeatable.",
        ),
        service_key: list[str] = typer.Option(
            [],
            "--service-key",
            help="Specific daemon service key to reconcile every cycle. Repeatable.",
        ),
        role: list[str] = typer.Option(
            [],
            "--role",
            help="Daemon role to reconcile every cycle. Repeatable.",
        ),
        service_group: list[str] = typer.Option(
            [],
            "--group",
            help="Daemon service group to reconcile every cycle. Repeatable.",
        ),
        include_eager: bool = typer.Option(
            True,
            "--include-eager/--no-include-eager",
            help="Whether to reconcile all eager daemon services each cycle.",
        ),
        max_cycles: int | None = typer.Option(
            None,
            "--max-cycles",
            min=1,
            help="Optional maximum reconcile cycles before exiting.",
        ),
    ) -> None:
        guard_runtime_database(load_settings(), runtime_name="daemon supervisor")
        container = ensure_container(ctx)
        _sync_managed_specs(container)
        service_set_keys = _normalized_tuple(service_set)
        service_keys = _normalized_tuple(service_key)
        service_roles = _normalized_tuple(role)
        service_groups = _normalized_tuple(service_group)
        try:
            _validate_supervisor_targets(
                _daemon_service(container),
                service_set_keys=service_set_keys,
                service_keys=service_keys,
            )
        except (DaemonValidationError, DaemonNotFoundError) as exc:
            _exit_error(exc)
        process_service = _process_service(container)
        active_session = _active_supervisor_session(process_service)
        if active_session is not None:
            echo_data(
                {
                    "status": "already_running",
                    "supervisor": _process_session_payload(active_session),
                }
            )
            return
        command = _build_supervisor_process_command(
            poll_interval_seconds=poll_interval_seconds,
            service_set_keys=service_set_keys,
            service_keys=service_keys,
            service_roles=service_roles,
            service_groups=service_groups,
            include_eager=include_eager,
            max_cycles=max_cycles,
        )
        try:
            session = process_service.start_command(
                command=command,
                shell=_resolve_shell_executable(),
                working_directory=str(Path.cwd().resolve()),
                session_key=_SUPERVISOR_SESSION_KEY,
                metadata={
                    "role": "daemon-supervisor",
                    "poll_interval_seconds": poll_interval_seconds,
                    "service_set_keys": list(service_set_keys),
                    "service_keys": list(service_keys),
                    "service_roles": list(service_roles),
                    "service_groups": list(service_groups),
                    "include_eager": include_eager,
                    "max_cycles": max_cycles,
                },
            )
        except (DaemonValidationError, ProcessValidationError) as exc:
            _exit_error(exc)
        session = _await_supervisor_bootstrap(
            process_service,
            process_id=session.id,
        )
        if not session.is_running:
            output = process_service.read_output(process_id=session.id, limit=4000)
            echo_data(
                {
                    "status": "failed_to_start",
                    "supervisor": _process_session_payload(session),
                    "output": _process_output_payload(output),
                }
            )
            raise typer.Exit(code=1)
        echo_data({"status": "started", "supervisor": _process_session_payload(session)})

    @app.command("supervise-internal", hidden=True)
    def supervise_internal(
        ctx: typer.Context,
        poll_interval_seconds: float = typer.Option(
            5.0,
            "--poll-interval-seconds",
            min=0.1,
            help="Idle wait time between eager daemon reconciliation cycles.",
        ),
        service_set: list[str] = typer.Option(
            [],
            "--service-set",
            "--set",
            help="Predefined daemon service set to reconcile every cycle. Repeatable.",
        ),
        service_key: list[str] = typer.Option(
            [],
            "--service-key",
            help="Specific daemon service key to reconcile every cycle. Repeatable.",
        ),
        role: list[str] = typer.Option(
            [],
            "--role",
            help="Daemon role to reconcile every cycle. Repeatable.",
        ),
        service_group: list[str] = typer.Option(
            [],
            "--group",
            help="Daemon service group to reconcile every cycle. Repeatable.",
        ),
        include_eager: bool = typer.Option(
            True,
            "--include-eager/--no-include-eager",
            help="Whether to reconcile all eager daemon services each cycle.",
        ),
        max_cycles: int | None = typer.Option(
            None,
            "--max-cycles",
            min=1,
            help="Optional maximum reconcile cycles before exiting.",
        ),
    ) -> None:
        guard_runtime_database(load_settings(), runtime_name="daemon supervisor")
        container = ensure_container(ctx)
        _sync_managed_specs(container)
        try:
            run_daemon_supervisor_loop(
                _daemon_manager(container),
                poll_interval_seconds=poll_interval_seconds,
                service_set_keys=_normalized_tuple(service_set),
                service_keys=_normalized_tuple(service_key),
                service_roles=_normalized_tuple(role),
                service_groups=_normalized_tuple(service_group),
                include_eager=include_eager,
                max_cycles=max_cycles,
                before_cycle=lambda: _sync_managed_specs(container),
            )
        except (DaemonValidationError, DaemonNotFoundError) as exc:
            _exit_error(exc)

    @app.command("status")
    def supervisor_status(ctx: typer.Context) -> None:
        container = ensure_container(ctx)
        process_service = _process_service(container)
        active_session = _active_supervisor_session(process_service)
        latest_session = active_session or _latest_supervisor_session(process_service)
        echo_data(
            {
                "status": "running" if active_session is not None else "stopped",
                "supervisor": (
                    _process_session_payload(latest_session)
                    if latest_session is not None
                    else None
                ),
            }
        )

    @app.command("logs")
    def supervisor_logs(
        ctx: typer.Context,
        stdout_offset: int = typer.Option(0, min=0, help="Stdout offset."),
        stderr_offset: int = typer.Option(0, min=0, help="Stderr offset."),
        limit: int = typer.Option(4000, min=1, max=20000, help="Maximum characters."),
    ) -> None:
        container = ensure_container(ctx)
        process_service = _process_service(container)
        session = _active_supervisor_session(process_service)
        if session is None:
            session = _latest_supervisor_session(process_service)
        if session is None:
            echo_data({"status": "not_running", "supervisor": None, "output": None})
            return
        output = process_service.read_output(
            process_id=session.id,
            stdout_offset=stdout_offset,
            stderr_offset=stderr_offset,
            limit=limit,
        )
        echo_data(
            {
                "status": "running" if session.is_running else "stopped",
                "supervisor": _process_session_payload(session),
                "output": _process_output_payload(output),
            }
        )

    def _stop_supervisor_impl(ctx: typer.Context) -> None:
        container = ensure_container(ctx)
        process_service = _process_service(container)
        active_session = _active_supervisor_session(process_service)
        if active_session is None:
            latest_session = _latest_supervisor_session(process_service)
            echo_data(
                {
                    "status": "not_running",
                    "supervisor": (
                        _process_session_payload(latest_session)
                        if latest_session is not None
                        else None
                    ),
                }
            )
            return
        session = process_service.terminate_session(process_id=active_session.id)
        echo_data({"status": "stopped", "supervisor": _process_session_payload(session)})

    @app.command("stop-supervisor")
    def stop_supervisor(ctx: typer.Context) -> None:
        _stop_supervisor_impl(ctx)

    @app.command("shutdown", hidden=True)
    def shutdown_supervisor(ctx: typer.Context) -> None:
        _stop_supervisor_impl(ctx)

    def _stop_all_impl(ctx: typer.Context) -> None:
        container = ensure_container(ctx)
        _sync_managed_specs(container)
        process_service = _process_service(container)
        active_session = _active_supervisor_session(process_service)
        latest_session = None
        supervisor_payload: dict[str, object] | None = None
        supervisor_status = "not_running"
        if active_session is not None:
            session = process_service.terminate_session(process_id=active_session.id)
            supervisor_payload = _process_session_summary(session)
            supervisor_status = "stopped"
        else:
            latest_session = _latest_supervisor_session(process_service)
            if latest_session is not None:
                supervisor_payload = _process_session_summary(latest_session)

        stopped_services: list[dict[str, object]] = []
        daemon_service = _daemon_service(container)
        daemon_manager = _daemon_manager(container)
        for service_key in _managed_process_service_keys(daemon_service):
            try:
                instances = daemon_manager.stop_service(service_key)
            except (DaemonValidationError, DaemonNotFoundError) as exc:
                _exit_error(exc)
            stopped_services.append(
                {
                    "service_key": service_key,
                    "stopped_instance_count": len(instances),
                }
            )

        echo_data(
            {
                "status": "stopped",
                "supervisor_status": supervisor_status,
                "supervisor": supervisor_payload,
                "services": stopped_services,
            }
        )

    @app.command("stop-all")
    def stop_all(ctx: typer.Context) -> None:
        _stop_all_impl(ctx)

    @app.command("down", hidden=True)
    def shutdown_all(ctx: typer.Context) -> None:
        _stop_all_impl(ctx)

    @app.command("stop")
    def stop_service(
        ctx: typer.Context,
        service_key: str = typer.Argument(..., help="Daemon service key."),
    ) -> None:
        container = ensure_container(ctx)
        _sync_managed_specs(container)
        try:
            instances = _daemon_manager(container).stop_service(service_key)
        except (DaemonValidationError, DaemonNotFoundError) as exc:
            _exit_error(exc)
        echo_data([instance_payload(instance) for instance in instances])

    return app
