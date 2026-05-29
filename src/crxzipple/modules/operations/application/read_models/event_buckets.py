from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from crxzipple.shared.time import coerce_utc_datetime


def recent_event_buckets(
    operations_observation: Any | None,
    *,
    module: str | None = None,
    event_name: str | None = None,
    hours: int = 24,
    limit: int = 1000,
) -> tuple[dict[str, Any], ...]:
    list_event_buckets = getattr(operations_observation, "list_event_buckets", None)
    if not callable(list_event_buckets):
        return ()
    since = datetime.now(timezone.utc) - timedelta(hours=max(int(hours), 1))
    try:
        rows = tuple(
            list_event_buckets(
                module=module,
                event_name=event_name,
                since=since,
                limit=max(int(limit), 1),
            )
            or (),
        )
    except Exception:
        return ()
    return tuple(
        bucket
        for item in rows
        for bucket in (_bucket_payload(item),)
        if bucket is not None
        and coerce_utc_datetime(bucket["bucket_start"]) >= since
    )


def _bucket_payload(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        payload = dict(value)
    else:
        payload = {
            "module": getattr(value, "module", None),
            "owner": getattr(value, "owner", None),
            "event_name": getattr(value, "event_name", None),
            "status": getattr(value, "status", None),
            "level": getattr(value, "level", None),
            "bucket_start": getattr(value, "bucket_start", None),
            "count": getattr(value, "count", None),
            "updated_at": getattr(value, "updated_at", None),
        }
    if not payload.get("event_name") or payload.get("bucket_start") is None:
        return None
    payload["count"] = _int(payload.get("count"))
    return payload


def _int(value: Any) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0
