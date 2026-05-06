from __future__ import annotations

import os
import socket
from uuid import uuid4

import typer

from crxzipple.bootstrap import build_container
from crxzipple.core.config import load_settings
from crxzipple.core.logger import configure_logging
from crxzipple.interfaces.cli.crxzipple import guard_runtime_database
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.events.domain import EventTopicRecord
from crxzipple.modules.operations.application.observation import OperationsEventObserver
from crxzipple.modules.operations.application.runtime import (
    OperationsObserverRuntimeService,
    OperationsObserverSubscription,
)
from crxzipple.shared.time import coerce_utc_datetime


def _resolve_worker_id(worker_id: str | None) -> str:
    if worker_id is not None and worker_id.strip():
        return worker_id.strip()
    return f"{socket.gethostname()}-{os.getpid()}-{uuid4().hex[:8]}"


def _runtime(container):
    runtime = container.operations_observer_runtime_event_service
    if runtime is None:
        raise typer.BadParameter("Operations observer runtime is not available.")
    return runtime


def _read_subscription_records(
    runtime: OperationsObserverRuntimeService,
    subscription: OperationsObserverSubscription,
    *,
    limit: int,
) -> tuple[EventTopicRecord, ...]:
    records = runtime.events_service.read_event_topic(
        subscription.source_topic,
        after_cursor=None,
        limit=limit,
    )
    if records:
        runtime.events_service.set_subscription_cursor(
            subscription.subscription_id,
            source_topic=subscription.source_topic,
            cursor=records[-1].cursor,
        )
    return records


def _record_sort_key(record: EventTopicRecord) -> tuple[str, str, str]:
    return (
        coerce_utc_datetime(record.envelope.occurred_at).isoformat(),
        record.envelope.topic or "",
        record.cursor,
    )


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
        container = build_container(settings=settings)
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
        limit_per_subscription: int = typer.Option(
            10000,
            "--limit-per-subscription",
            min=1,
            help="Maximum source events to replay from each observer subscription.",
        ),
    ) -> None:
        settings = load_settings()
        guard_runtime_database(settings, runtime_name="operations observer rebuild")
        configure_logging(settings)
        resolved_worker_id = _resolve_worker_id(worker_id)
        container = build_container(settings=settings)
        container.operations_observation_store.reset()
        projection_store = getattr(container, "operations_projection_store", None)
        clear_projection_store = getattr(projection_store, "clear", None)
        if callable(clear_projection_store):
            clear_projection_store()
        runtime = _runtime(container)
        records = tuple(
            record
            for subscription in runtime.subscriptions
            for record in _read_subscription_records(
                runtime,
                subscription,
                limit=limit_per_subscription,
            )
        )
        observer = OperationsEventObserver(
            observation_store=container.operations_observation_store,
            definition_registry=container.event_definition_registry,
        )
        observer.observe_event_records(
            tuple(sorted(records, key=_record_sort_key)),
        )
        materialized_modules = _materialize_all(container)
        runtime.record_heartbeat(
            worker_id=resolved_worker_id,
            status="rebuilt",
            processed_events=len(records),
            limit_per_subscription=limit_per_subscription,
        )
        echo_data(
            {
                "processed_events": len(records),
                "materialized_modules": materialized_modules,
                "worker_id": resolved_worker_id,
                "observation_reset": True,
            },
        )

    @app.command("run")
    def run(
        poll_interval_seconds: float = typer.Option(
            0.5,
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
        container = build_container(settings=settings)
        _materialize_all(container)
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
    materializer = getattr(container, "operations_projection_materializer", None)
    if materializer is None:
        return 0
    return int(materializer.materialize_all())
