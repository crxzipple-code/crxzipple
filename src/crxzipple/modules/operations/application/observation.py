from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from crxzipple.modules.events.domain import EventTopicRecord
from crxzipple.modules.operations.application.observation_event_projection import (
    observed_event_from_record,
)
from crxzipple.modules.operations.application.observation_models import (
    OperationsModuleObservation,
    OperationsObservedEvent,
    OperationsObserverHeartbeat,
    OperationsObservationSnapshot,
)
from crxzipple.shared.event_contracts import EventDefinitionRegistry


class OperationsObservationStore(Protocol):
    def record_observed_event(self, event: OperationsObservedEvent) -> None:
        ...

    def record_observed_events(
        self,
        events: tuple[OperationsObservedEvent, ...],
    ) -> None:
        ...

    def record_observer_heartbeat(
        self,
        heartbeat: OperationsObserverHeartbeat,
    ) -> None:
        ...

    def reset(self) -> None:
        ...

    def get_module_observation(
        self,
        module: str,
    ) -> OperationsModuleObservation | None:
        ...

    def snapshot(self) -> OperationsObservationSnapshot:
        ...

    def list_event_buckets(
        self,
        *,
        module: str | None = None,
        event_name: str | None = None,
        since: datetime | None = None,
        limit: int = 500,
    ) -> tuple[dict[str, Any], ...]:
        ...


@dataclass(frozen=True, slots=True)
class OperationsEventObserver:
    observation_store: OperationsObservationStore
    definition_registry: EventDefinitionRegistry | None = None

    def observe_event_record(self, record: EventTopicRecord) -> None:
        self.observation_store.record_observed_event(
            observed_event_from_record(
                record,
                definition_registry=self.definition_registry,
            ),
        )

    def observe_event_records(self, records: tuple[EventTopicRecord, ...]) -> None:
        self.observation_store.record_observed_events(
            tuple(
                observed_event_from_record(
                    record,
                    definition_registry=self.definition_registry,
                )
                for record in records
            ),
        )
