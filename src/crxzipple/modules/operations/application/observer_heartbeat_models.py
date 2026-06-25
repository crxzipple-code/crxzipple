from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from crxzipple.modules.operations.application.observation_payloads import (
    int_value,
    optional_float,
    optional_text,
    parse_datetime,
)
from crxzipple.shared.time import format_datetime_utc


@dataclass(frozen=True, slots=True)
class OperationsObserverHeartbeat:
    runtime_name: str
    worker_id: str
    status: str
    started_at: datetime | None
    last_seen_at: datetime
    processed_events: int = 0
    idle_cycles: int = 0
    subscription_count: int = 0
    poll_interval_seconds: float | None = None
    limit_per_subscription: int | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "runtime_name": self.runtime_name,
            "worker_id": self.worker_id,
            "status": self.status,
            "started_at": (
                format_datetime_utc(self.started_at)
                if self.started_at is not None
                else None
            ),
            "last_seen_at": format_datetime_utc(self.last_seen_at),
            "processed_events": self.processed_events,
            "idle_cycles": self.idle_cycles,
            "subscription_count": self.subscription_count,
            "poll_interval_seconds": self.poll_interval_seconds,
            "limit_per_subscription": self.limit_per_subscription,
        }

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
    ) -> "OperationsObserverHeartbeat | None":
        runtime_name = optional_text(payload.get("runtime_name"))
        worker_id = optional_text(payload.get("worker_id"))
        last_seen_at = parse_datetime(payload.get("last_seen_at"))
        if runtime_name is None or worker_id is None or last_seen_at is None:
            return None
        return cls(
            runtime_name=runtime_name,
            worker_id=worker_id,
            status=optional_text(payload.get("status")) or "observed",
            started_at=parse_datetime(payload.get("started_at")),
            last_seen_at=last_seen_at,
            processed_events=int_value(payload.get("processed_events")),
            idle_cycles=int_value(payload.get("idle_cycles")),
            subscription_count=int_value(payload.get("subscription_count")),
            poll_interval_seconds=optional_float(
                payload.get("poll_interval_seconds"),
            ),
            limit_per_subscription=(
                int_value(payload.get("limit_per_subscription"))
                if payload.get("limit_per_subscription") is not None
                else None
            ),
        )
