from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from crxzipple.modules.operations.application.observation_event_models import (
    OperationsModuleObservation,
)
from crxzipple.modules.operations.application.observer_heartbeat_models import (
    OperationsObserverHeartbeat,
)
from crxzipple.shared.time import format_datetime_utc


@dataclass(frozen=True, slots=True)
class OperationsObservationSnapshot:
    version: int
    updated_at: datetime | None
    modules: tuple[OperationsModuleObservation, ...]
    observer_heartbeats: tuple[OperationsObserverHeartbeat, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "updated_at": (
                format_datetime_utc(self.updated_at)
                if self.updated_at is not None
                else None
            ),
            "modules": [module.to_payload() for module in self.modules],
            "observer_heartbeats": [
                heartbeat.to_payload() for heartbeat in self.observer_heartbeats
            ],
        }
