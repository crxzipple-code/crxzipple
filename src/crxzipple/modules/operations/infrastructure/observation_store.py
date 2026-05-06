from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable

from crxzipple.modules.operations.application.observation import (
    OperationsModuleObservation,
    OperationsObserverHeartbeat,
    OperationsObservedEvent,
    OperationsObservationSnapshot,
)
from crxzipple.shared.time import coerce_utc_datetime

_OBSERVATION_VERSION = 4
_RECENT_EVENTS_PER_MODULE = 80


class FileBackedOperationsObservationStore:
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
                updated = _record_observed_event(
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
        self.update(lambda snapshot: _record_observer_heartbeat(snapshot, heartbeat))

    def reset(self) -> None:
        with _file_lock(self._lock_path, shared=False):
            self._save_unlocked(
                OperationsObservationSnapshot(
                    version=_OBSERVATION_VERSION,
                    updated_at=None,
                    modules=(),
                    observer_heartbeats=(),
                ),
            )

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
        with _file_lock(self._lock_path, shared=True):
            return self._load_unlocked()

    def update(
        self,
        mutator: Callable[[OperationsObservationSnapshot], OperationsObservationSnapshot],
    ) -> OperationsObservationSnapshot:
        with _file_lock(self._lock_path, shared=False):
            snapshot = mutator(self._load_unlocked())
            self._save_unlocked(snapshot)
            return snapshot

    def _load_unlocked(self) -> OperationsObservationSnapshot:
        if not self._path.exists():
            return OperationsObservationSnapshot(
                version=_OBSERVATION_VERSION,
                updated_at=None,
                modules=(),
                observer_heartbeats=(),
            )
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return OperationsObservationSnapshot(
                version=_OBSERVATION_VERSION,
                updated_at=None,
                modules=(),
                observer_heartbeats=(),
            )
        if not isinstance(payload, dict):
            return OperationsObservationSnapshot(
                version=_OBSERVATION_VERSION,
                updated_at=None,
                modules=(),
                observer_heartbeats=(),
            )
        modules = tuple(
            module
            for item in payload.get("modules", ())
            if isinstance(item, dict)
            for module in (OperationsModuleObservation.from_payload(item),)
            if module is not None
        )
        observer_heartbeats = tuple(
            heartbeat
            for item in payload.get("observer_heartbeats", ())
            if isinstance(item, dict)
            for heartbeat in (OperationsObserverHeartbeat.from_payload(item),)
            if heartbeat is not None
        )
        return OperationsObservationSnapshot(
            version=max(_int(payload.get("version")), _OBSERVATION_VERSION),
            updated_at=_parse_datetime(payload.get("updated_at")),
            modules=modules,
            observer_heartbeats=observer_heartbeats,
        )

    def _save_unlocked(self, snapshot: OperationsObservationSnapshot) -> None:
        _write_text_atomically(
            self._path,
            json.dumps(
                snapshot.to_payload(),
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            ),
        )


def _record_module_event(
    current: OperationsModuleObservation | None,
    event: OperationsObservedEvent,
    *,
    recent_limit: int,
) -> OperationsModuleObservation:
    status_counts = dict(current.status_counts) if current is not None else {}
    event_name_counts = dict(current.event_name_counts) if current is not None else {}
    status_counts[event.status] = status_counts.get(event.status, 0) + 1
    event_name_counts[event.event_name] = event_name_counts.get(event.event_name, 0) + 1
    recent_events = (event,)
    if current is not None:
        recent_events = recent_events + tuple(
            item
            for item in current.recent_events
            if item.id != event.id or item.cursor != event.cursor
        )
    return OperationsModuleObservation(
        module=event.module,
        owner=event.owner,
        updated_at=event.occurred_at,
        event_count=(current.event_count if current is not None else 0) + 1,
        status_counts=status_counts,
        event_name_counts=event_name_counts,
        last_event_id=event.id,
        last_event_name=event.event_name,
        last_topic=event.topic,
        last_cursor=event.cursor,
        last_event_at=event.occurred_at,
        recent_events=recent_events[:recent_limit],
    )


def _record_observed_event(
    snapshot: OperationsObservationSnapshot,
    event: OperationsObservedEvent,
    *,
    recent_limit: int,
) -> OperationsObservationSnapshot:
    modules_by_key = {module.module: module for module in snapshot.modules}
    current = modules_by_key.get(event.module)
    modules_by_key[event.module] = _record_module_event(
        current,
        event,
        recent_limit=recent_limit,
    )
    return OperationsObservationSnapshot(
        version=_OBSERVATION_VERSION,
        updated_at=event.occurred_at,
        modules=tuple(modules_by_key[key] for key in sorted(modules_by_key)),
        observer_heartbeats=snapshot.observer_heartbeats,
    )


def _record_observer_heartbeat(
    snapshot: OperationsObservationSnapshot,
    heartbeat: OperationsObserverHeartbeat,
) -> OperationsObservationSnapshot:
    heartbeats_by_key = {
        (item.runtime_name, item.worker_id): item
        for item in snapshot.observer_heartbeats
    }
    heartbeats_by_key[(heartbeat.runtime_name, heartbeat.worker_id)] = heartbeat
    latest_update = snapshot.updated_at
    heartbeat_seen_at = coerce_utc_datetime(heartbeat.last_seen_at)
    if latest_update is None or heartbeat_seen_at > coerce_utc_datetime(latest_update):
        latest_update = heartbeat_seen_at
    return OperationsObservationSnapshot(
        version=_OBSERVATION_VERSION,
        updated_at=latest_update,
        modules=snapshot.modules,
        observer_heartbeats=tuple(
            heartbeats_by_key[key] for key in sorted(heartbeats_by_key)
        ),
    )


@contextmanager
def _file_lock(path: Path, *, shared: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _write_text_atomically(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_path_raw = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temp_path = Path(temp_path_raw)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(float(value))
        except ValueError:
            return 0
    return 0


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return coerce_utc_datetime(datetime.fromisoformat(value))
    except ValueError:
        return None
