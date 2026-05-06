from __future__ import annotations

import typer

from crxzipple.bootstrap import build_container
from crxzipple.core.config import load_settings
from crxzipple.core.logger import configure_logging
from crxzipple.interfaces.cli.crxzipple import guard_runtime_database
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.interfaces.worker_loops import run_tool_scheduler_loop
from crxzipple.modules.tool.interfaces.dto import ToolRunDTO


def build_cli() -> typer.Typer:
    app = typer.Typer(help="Run the tool scheduler.", no_args_is_help=True)

    @app.command("once")
    def run_once(
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Optional worker identifier to register/target for this assignment pass.",
        ),
        max_in_flight: int = typer.Option(
            1,
            "--max-in-flight",
            min=1,
            help="Maximum assignment slots to register when --worker-id is provided.",
        ),
    ) -> None:
        settings = load_settings()
        configure_logging(settings)
        container = build_container(settings=settings)
        try:
            if worker_id is not None and worker_id.strip():
                container.tool_worker_service.register_worker(
                    worker_id=worker_id.strip(),
                    max_in_flight=max_in_flight,
                )
                resolved_worker_id = worker_id.strip()
            else:
                resolved_worker_id = None
            tool_run = container.tool_scheduler_service.assign_next_available(
                worker_id=resolved_worker_id,
            )
            if tool_run is None:
                payload = {"status": "idle"}
                if resolved_worker_id is not None:
                    payload["worker_id"] = resolved_worker_id
                echo_data(payload)
                return
            echo_data(ToolRunDTO.from_entity(tool_run))
        finally:
            container.engine.dispose()

    @app.command("run-scheduler")
    def run_scheduler(
        poll_interval_seconds: float = typer.Option(
            0.5,
            "--poll-interval-seconds",
            min=0.05,
            help="Idle wait time between scheduling polls.",
        ),
        max_runs: int | None = typer.Option(
            None,
            "--max-runs",
            min=1,
            help="Optional maximum number of assignments to create before exiting.",
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
            help=(
                "Daemon scheduler identifier. Accepted so daemon-managed worker "
                "services share a consistent process contract."
            ),
        ),
    ) -> None:
        del worker_id
        settings = load_settings()
        guard_runtime_database(settings, runtime_name="tool scheduler")
        configure_logging(settings)
        container = build_container(settings=settings)
        try:
            run_tool_scheduler_loop(
                container.tool_scheduler_service,
                poll_interval_seconds=poll_interval_seconds,
                max_runs=max_runs,
                max_idle_cycles=max_idle_cycles,
                events_service=container.events_service,
            )
        finally:
            container.engine.dispose()

    return app


app = build_cli()


def main() -> None:
    settings = load_settings()
    configure_logging(settings)
    app()
