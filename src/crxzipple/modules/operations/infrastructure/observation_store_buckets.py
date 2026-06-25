from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.modules.operations.application.observation_models import (
    OperationsObservationSnapshot,
)
from crxzipple.shared.time import coerce_utc_datetime


def event_buckets(
    snapshot: OperationsObservationSnapshot,
    *,
    module: str | None = None,
    event_name: str | None = None,
    since: datetime | None = None,
    limit: int = 500,
) -> tuple[dict[str, Any], ...]:
    rows: dict[tuple[str, str, str, datetime], dict[str, Any]] = {}
    module_filter = module.strip().lower() if isinstance(module, str) else None
    event_filter = event_name.strip() if isinstance(event_name, str) else None
    since_at = coerce_utc_datetime(since) if since is not None else None
    for observation in snapshot.modules:
        if module_filter and observation.module != module_filter:
            continue
        for event in observation.recent_events:
            if event_filter and event.event_name != event_filter:
                continue
            occurred_at = coerce_utc_datetime(event.occurred_at)
            if since_at is not None and occurred_at < since_at:
                continue
            bucket_start = occurred_at.replace(minute=0, second=0, microsecond=0)
            key = (event.module, event.event_name, event.status, bucket_start)
            row = rows.setdefault(
                key,
                {
                    "module": event.module,
                    "owner": event.owner,
                    "event_name": event.event_name,
                    "status": event.status,
                    "level": event.level,
                    "bucket_start": bucket_start,
                    "count": 0,
                    "updated_at": occurred_at,
                },
            )
            row["count"] = int(row["count"]) + 1
            if occurred_at > coerce_utc_datetime(row["updated_at"]):
                row["updated_at"] = occurred_at
    return tuple(
        sorted(
            rows.values(),
            key=lambda item: (
                coerce_utc_datetime(item["bucket_start"]),
                str(item["module"]),
                str(item["event_name"]),
                str(item["status"]),
            ),
            reverse=True,
        )[: max(int(limit), 1)]
    )
