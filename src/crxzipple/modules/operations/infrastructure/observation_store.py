from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any, Callable

from crxzipple.modules.operations.application.observation_models import (
    OperationsModuleObservation,
    OperationsObserverHeartbeat,
    OperationsObservedEvent,
    OperationsObservationSnapshot,
)
from crxzipple.modules.operations.infrastructure.observation_store_io import (
    file_lock,
    write_text_atomically,
)
from crxzipple.modules.operations.infrastructure.observation_store_buckets import (
    event_buckets,
)
from crxzipple.modules.operations.infrastructure.observation_store_records import (
    empty_observation_snapshot,
    observation_snapshot_from_payload,
    record_observed_event,
    record_observer_heartbeat,
)

_RECENT_EVENTS_PER_MODULE = 80


class FileBackedOperationsObservationStore:
    """Lightweight/test observation store, not a shared runtime fallback."""

    def __init__(
        self,
        root_dir: str | Path,
        *,
        filename: str = "observer_observation.json",
        recent_events_per_module: int = _RECENT_EVENTS_PER_MODULE,
    ) -> None:
        self._root_dir = Path(root_dir).expanduser().resolve()
        self._path = self._root_dir / filename
        self._lock_path = self._root_dir / f"{filename}.lock"
        self._recent_events_per_module = max(int(recent_events_per_module), 1)
        self._root_dir.mkdir(parents=True, exist_ok=True)

    def record_observed_event(self, event: OperationsObservedEvent) -> None:
        self.record_observed_events((event,))

    def record_observed_events(
        self,
        events: tuple[OperationsObservedEvent, ...],
    ) -> None:
        observed_events = tuple(events)
        if not observed_events:
            return

        def _mutate(
            snapshot: OperationsObservationSnapshot,
        ) -> OperationsObservationSnapshot:
            updated = snapshot
            for event in observed_events:
                updated = record_observed_event(
                    updated,
                    event,
                    recent_limit=self._recent_events_per_module,
                )
            return updated

        self.update(_mutate)

    def record_observer_heartbeat(
        self,
        heartbeat: OperationsObserverHeartbeat,
    ) -> None:
        self.update(lambda snapshot: record_observer_heartbeat(snapshot, heartbeat))

    def reset(self) -> None:
        with file_lock(self._lock_path, shared=False):
            self._save_unlocked(empty_observation_snapshot())

    def get_module_observation(
        self,
        module: str,
    ) -> OperationsModuleObservation | None:
        normalized = module.strip().lower()
        if not normalized:
            return None
        for item in self.snapshot().modules:
            if item.module == normalized:
                return item
        return None

    def snapshot(self) -> OperationsObservationSnapshot:
        with file_lock(self._lock_path, shared=True):
            return self._load_unlocked()

    def list_event_buckets(
        self,
        *,
        module: str | None = None,
        event_name: str | None = None,
        since: datetime | None = None,
        limit: int = 500,
    ) -> tuple[dict[str, Any], ...]:
        return event_buckets(
            self.snapshot(),
            module=module,
            event_name=event_name,
            since=since,
            limit=limit,
        )

    def update(
        self,
        mutator: Callable[[OperationsObservationSnapshot], OperationsObservationSnapshot],
    ) -> OperationsObservationSnapshot:
        with file_lock(self._lock_path, shared=False):
            snapshot = mutator(self._load_unlocked())
            self._save_unlocked(snapshot)
            return snapshot

    def _load_unlocked(self) -> OperationsObservationSnapshot:
        if not self._path.exists():
            return empty_observation_snapshot()
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return empty_observation_snapshot()
        return observation_snapshot_from_payload(payload)

    def _save_unlocked(self, snapshot: OperationsObservationSnapshot) -> None:
        write_text_atomically(
            self._path,
            json.dumps(
                snapshot.to_payload(),
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            ),
        )
