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
    runtime = container.require(AppKey.OPERATIONS_OBSERVER_RUNTIME_EVENT_SERVICE)
    if runtime is None:
        raise typer.BadParameter("Operations observer runtime is not available.")
    return runtime


def build_cli() -> typer.Typer:
    app = typer.Typer(help="Run the operations observer runtime.", no_args_is_help=True)

    @app.command("process")
    def process(
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Stable operations observer runtime identifier.",
        ),
        limit_per_subscription: int = typer.Option(
            100,
            "--limit-per-subscription",
            min=1,
            help="Maximum source events to consume from each observer subscription.",
        ),
        from_beginning: bool = typer.Option(
            False,
            "--from-beginning",
            help="Ignore persisted subscription cursors for this pass.",
        ),
    ) -> None:
        settings = load_settings()
        guard_runtime_database(settings, runtime_name="operations observer")
        configure_logging(settings)
        resolved_worker_id = _resolve_worker_id(worker_id)
        with runtime_container(
            settings,
            target=AssemblyTarget.OPERATIONS_OBSERVER,
        ) as container:
            runtime = _runtime(container)
            processed_events = runtime.process_available_events(
                limit_per_subscription=limit_per_subscription,
                from_beginning=from_beginning,
            )
            runtime.record_heartbeat(
                worker_id=resolved_worker_id,
                status="completed",
                processed_events=processed_events,
                limit_per_subscription=limit_per_subscription,
            )
            materialized_modules = _materialize_all(container)
        echo_data(
            {
                "processed_events": processed_events,
                "materialized_modules": materialized_modules,
                "worker_id": resolved_worker_id,
            },
        )

    @app.command("rebuild")
    def rebuild(
        worker_id: str | None = typer.Option(
            None,
            "--worker-id",
            help="Stable operations observer runtime identifier.",
        ),
    ) -> None:
        settings = load_settings()
        guard_runtime_database(settings, runtime_name="operations observer rebuild")
        configure_logging(settings)
        resolved_worker_id = _resolve_worker_id(worker_id)
        with runtime_container(
            settings,
            target=AssemblyTarget.OPERATIONS_OBSERVER,
        ) as container:
            projection_store = container.require(AppKey.OPERATIONS_PROJECTION_STORE)
            clear_projection_store = getattr(projection_store, "clear", None)
            if callable(clear_projection_store):
                clear_projection_store()
            materialized_modules = _materialize_all(container)
        echo_data(
            {
                "processed_events": 0,
                "materialized_modules": materialized_modules,
                "worker_id": resolved_worker_id,
                "observation_reset": False,
                "projection_reset": True,
            },
        )

    @app.command("run")
    def run(
        poll_interval_seconds: float = typer.Option(
            0.2,
            "--poll-interval-seconds",
            min=0.05,
            help="Idle wait time between operations observer polls.",
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
            help="Stable operations observer runtime identifier.",
        ),
        limit_per_subscription: int = typer.Option(
            100,
            "--limit-per-subscription",
            min=1,
            help="Maximum source events to consume from each observer subscription.",
        ),
    ) -> None:
        settings = load_settings()
        guard_runtime_database(settings, runtime_name="operations observer")
        configure_logging(settings)
        resolved_worker_id = _resolve_worker_id(worker_id)
        with runtime_container(
            settings,
            target=AssemblyTarget.OPERATIONS_OBSERVER,
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


def _materialize_all(container) -> int:  # noqa: ANN001
    materializer = container.require(AppKey.OPERATIONS_PROJECTION_MATERIALIZER)
    if materializer is None:
        return 0
    return int(materializer.materialize_all())
