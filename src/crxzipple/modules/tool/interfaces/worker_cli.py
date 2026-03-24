from __future__ import annotations

import os
import socket
from uuid import uuid4

import typer

from crxzipple.bootstrap import build_container
from crxzipple.core.config import load_settings
from crxzipple.core.logger import configure_logging
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.interfaces.worker_loops import run_tool_worker_loop
from crxzipple.modules.tool.interfaces.dto import ToolRunDTO


def _resolve_worker_id(worker_id: str | None) -> str:
    if worker_id is not None and worker_id.strip():
        return worker_id.strip()
    return f"{socket.gethostname()}-{os.getpid()}-{uuid4().hex[:8]}"


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
        container = build_container(settings=settings)
        resolved_worker_id = _resolve_worker_id(worker_id)
        try:
            tool_run = container.tool_service.process_next_queued_run(
                worker_id=resolved_worker_id,
            )
            if tool_run is None:
                echo_data({"status": "idle", "worker_id": resolved_worker_id})
                return
            echo_data(ToolRunDTO.from_entity(tool_run))
        finally:
            container.engine.dispose()

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
    ) -> None:
        settings = load_settings()
        configure_logging(settings)
        container = build_container(settings=settings)
        resolved_worker_id = _resolve_worker_id(worker_id)

        try:
            run_tool_worker_loop(
                container.tool_service,
                worker_id=resolved_worker_id,
                poll_interval_seconds=poll_interval_seconds,
                max_runs=max_runs,
                max_idle_cycles=max_idle_cycles,
            )
        finally:
            container.engine.dispose()

    return app


app = build_cli()


def main() -> None:
    settings = load_settings()
    configure_logging(settings)
    app()
