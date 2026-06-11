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


def _publisher(container):
    publisher = container.require(AppKey.EVENT_OUTBOX_PUBLISHER_SERVICE)
    if publisher is None:
        raise typer.BadParameter("Event outbox publisher is not available.")
    return publisher


def build_cli() -> typer.Typer:
    app = typer.Typer(help="Run the event outbox publisher.", no_args_is_help=True)

    @app.command("process")
    def process(
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Stable event outbox publisher identifier.",
        ),
        limit: int = typer.Option(
            100,
            "--limit",
            min=1,
            help="Maximum outbox records to publish.",
        ),
    ) -> None:
        settings = load_settings()
        guard_runtime_database(settings, runtime_name="event outbox publisher")
        configure_logging(settings)
        resolved_worker_id = _resolve_worker_id(worker_id)
        with runtime_container(
            settings,
            target=AssemblyTarget.EVENT_OUTBOX_PUBLISHER,
        ) as container:
            result = _publisher(container).publish_available(limit=limit)
        echo_data(
            {
                "processed_events": result.processed,
                "published_events": result.published,
                "failed_events": result.failed,
                "worker_id": resolved_worker_id,
            },
        )

    @app.command("run")
    def run(
        poll_interval_seconds: float = typer.Option(
            0.2,
            "--poll-interval-seconds",
            min=0.05,
            help="Idle wait time between outbox polls.",
        ),
        max_events: int | None = typer.Option(
            None,
            "--max-events",
            min=1,
            help="Optional maximum number of outbox events to process before exiting.",
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
            help="Stable event outbox publisher identifier.",
        ),
        limit: int = typer.Option(
            100,
            "--limit",
            min=1,
            help="Maximum outbox records to publish each poll.",
        ),
    ) -> None:
        settings = load_settings()
        guard_runtime_database(settings, runtime_name="event outbox publisher")
        configure_logging(settings)
        resolved_worker_id = _resolve_worker_id(worker_id)
        with runtime_container(
            settings,
            target=AssemblyTarget.EVENT_OUTBOX_PUBLISHER,
        ) as container:
            processed_events = _publisher(container).run_until_stopped(
                worker_id=resolved_worker_id,
                poll_interval_seconds=poll_interval_seconds,
                max_events=max_events,
                max_idle_cycles=max_idle_cycles,
                limit=limit,
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
