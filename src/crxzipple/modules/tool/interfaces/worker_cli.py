from __future__ import annotations

import os
import socket
from uuid import uuid4

import typer

from crxzipple.core.config import load_settings
from crxzipple.core.logger import configure_logging
from crxzipple.interfaces.cli.crxzipple import guard_runtime_database
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.interfaces.runtime_container import (
    AppKey,
    AssemblyTarget,
    runtime_container,
)
from crxzipple.interfaces.worker_loops import run_tool_worker_loop
from crxzipple.modules.tool.interfaces.dto import ToolRunDTO


def _resolve_worker_id(worker_id: str | None) -> str:
    if worker_id is not None and worker_id.strip():
        return worker_id.strip()
    return f"{socket.gethostname()}-{os.getpid()}-{uuid4().hex[:8]}"


def _resolve_max_in_flight(runtime_bootstrap_config: object, explicit_value: int | None) -> int:
    if explicit_value is not None:
        return max(int(explicit_value), 1)
    configured_value = getattr(runtime_bootstrap_config, "tool_worker_max_in_flight", 4)
    return max(int(configured_value), 1)


def build_cli() -> typer.Typer:
    app = typer.Typer(help="Run the background tool worker.", no_args_is_help=True)

    @app.command("once")
    def run_once(
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Stable worker identifier used for leases and logs.",
        ),
    ) -> None:
        settings = load_settings()
        configure_logging(settings)
        resolved_worker_id = _resolve_worker_id(worker_id)
        with runtime_container(
            settings,
            target=AssemblyTarget.TOOL_WORKER,
        ) as container:
            runtime_event_service = container.require(AppKey.TOOL_RUNTIME_EVENT_SERVICE)
            if runtime_event_service is not None:
                runtime_event_service.process_available_events()
            tool_worker_service = container.require(AppKey.TOOL_WORKER_SERVICE)
            try:
                tool_worker_service.register_worker(
                    worker_id=resolved_worker_id,
                )
                tool_run = tool_worker_service.process_next_assigned_run(
                    worker_id=resolved_worker_id,
                )
                if tool_run is None:
                    echo_data({"status": "idle", "worker_id": resolved_worker_id})
                    return
                echo_data(ToolRunDTO.from_entity(tool_run))
            finally:
                tool_worker_service.mark_worker_stale(
                    worker_id=resolved_worker_id,
                )

    @app.command("run")
    def run_worker(
        poll_interval_seconds: float = typer.Option(
            0.5,
            "--poll-interval-seconds",
            min=0.05,
            help="Idle wait time between queue polls.",
        ),
        max_runs: int | None = typer.Option(
            None,
            "--max-runs",
            min=1,
            help="Optional maximum number of runs to process before exiting.",
        ),
        max_idle_cycles: int | None = typer.Option(
            None,
            "--max-idle-cycles",
            min=1,
            help="Optional maximum consecutive idle polls before exiting.",
        ),
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Stable worker identifier used for leases and logs.",
        ),
        max_in_flight: int | None = typer.Option(
            None,
            "--max-in-flight",
            min=1,
            help=(
                "Maximum number of in-flight assignment slots registered for this worker. "
                "Defaults to Settings runtime defaults."
            ),
        ),
    ) -> None:
        settings = load_settings()
        guard_runtime_database(settings, runtime_name="tool worker")
        configure_logging(settings)
        with runtime_container(
            settings,
            target=AssemblyTarget.TOOL_WORKER,
        ) as container:
            resolved_worker_id = _resolve_worker_id(worker_id)
            resolved_max_in_flight = _resolve_max_in_flight(
                container.require(AppKey.RUNTIME_BOOTSTRAP_CONFIG),
                max_in_flight,
            )

            run_tool_worker_loop(
                container.require(AppKey.TOOL_WORKER_SERVICE),
                worker_id=resolved_worker_id,
                poll_interval_seconds=poll_interval_seconds,
                max_runs=max_runs,
                max_idle_cycles=max_idle_cycles,
                events_service=container.require(AppKey.EVENTS_SERVICE),
                runtime_event_service=container.require(AppKey.TOOL_RUNTIME_EVENT_SERVICE),
                max_in_flight=resolved_max_in_flight,
            )

    return app


app = build_cli()


def main() -> None:
    settings = load_settings()
    configure_logging(settings)
    app()
