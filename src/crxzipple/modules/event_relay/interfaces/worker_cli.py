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


def _resolve_worker_id(worker_id: str | None) -> str:
    if worker_id is not None and worker_id.strip():
        return worker_id.strip()
    return f"{socket.gethostname()}-{os.getpid()}-{uuid4().hex[:8]}"


def _runtime(container):
    runtime = container.require(AppKey.EVENT_RELAY_RUNTIME_EVENT_SERVICE)
    if runtime is None:
        raise typer.BadParameter("Event relay runtime is not available.")
    return runtime


def build_cli() -> typer.Typer:
    app = typer.Typer(help="Run the event relay runtime.", no_args_is_help=True)

    @app.command("process")
    def process(
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Stable event relay runtime identifier.",
        ),
        limit_per_subscription: int = typer.Option(
            100,
            "--limit-per-subscription",
            min=1,
            help="Maximum source events to consume from each relay subscription.",
        ),
    ) -> None:
        settings = load_settings()
        guard_runtime_database(settings, runtime_name="event relay")
        configure_logging(settings)
        resolved_worker_id = _resolve_worker_id(worker_id)
        with runtime_container(
            settings,
            target=AssemblyTarget.EVENT_RELAY_WORKER,
        ) as container:
            processed_events = _runtime(container).process_available_events(
                limit_per_subscription=limit_per_subscription,
            )
        echo_data(
            {
                "processed_events": processed_events,
                "worker_id": resolved_worker_id,
            },
        )

    @app.command("run")
    def run(
        poll_interval_seconds: float = typer.Option(
            0.5,
            "--poll-interval-seconds",
            min=0.05,
            help="Idle wait time between event relay polls.",
        ),
        max_events: int | None = typer.Option(
            None,
            "--max-events",
            min=1,
            help="Optional maximum number of events to process before exiting.",
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
            help="Stable event relay runtime identifier.",
        ),
        limit_per_subscription: int = typer.Option(
            100,
            "--limit-per-subscription",
            min=1,
            help="Maximum source events to consume from each relay subscription.",
        ),
    ) -> None:
        settings = load_settings()
        guard_runtime_database(settings, runtime_name="event relay")
        configure_logging(settings)
        resolved_worker_id = _resolve_worker_id(worker_id)
        with runtime_container(
            settings,
            target=AssemblyTarget.EVENT_RELAY_WORKER,
        ) as container:
            processed_events = _runtime(container).run_until_stopped(
                worker_id=resolved_worker_id,
                poll_interval_seconds=poll_interval_seconds,
                max_events=max_events,
                max_idle_cycles=max_idle_cycles,
                limit_per_subscription=limit_per_subscription,
            )
        echo_data(
            {
                "processed_events": processed_events,
                "worker_id": resolved_worker_id,
            },
        )

    return app


def main() -> None:
    build_cli()()
