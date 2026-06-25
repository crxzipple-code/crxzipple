from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from crxzipple.modules.events.domain import EventTopicRecord
from crxzipple.modules.operations.application.observation_models import (
    OperationsObserverHeartbeat,
)

OperationsObserverHandler = Callable[[EventTopicRecord], None]
OperationsObserverBatchHandler = Callable[[tuple[EventTopicRecord, ...]], None]
OperationsObserverHeartbeatHandler = Callable[[OperationsObserverHeartbeat], None]
OperationsObserverMaintenanceHandler = Callable[[], None]


@dataclass(frozen=True, slots=True)
class OperationsObserverSubscription:
    subscription_id: str
    source_topic: str
    handler: OperationsObserverHandler
    batch_handler: OperationsObserverBatchHandler | None = None
