from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
from dataclasses import asdict
from datetime import datetime
import os
from pathlib import Path
import tempfile
from typing import Callable, TypeVar

from crxzipple.modules.daemon.domain import DaemonInstance, DaemonLease, DaemonServiceSpec
from crxzipple.modules.daemon.domain.entities import utcnow

_StoreValue = TypeVar("_StoreValue")


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return datetime.fromisoformat(value)


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


class FileBackedDaemonServiceSpecStore:
    def __init__(
        self,
        root_dir: Path,
        *,
        bootstrap_specs: tuple[DaemonServiceSpec, ...] = (),
    ) -> None:
        self._path = root_dir / "services.json"
        self._lock_path = root_dir / "services.json.lock"
        self._bootstrap_specs = tuple(bootstrap_specs)
        if not self._path.exists():
            self.save(self._bootstrap_specs)
        else:
            self.load()

    def _merge_bootstrap_specs(
        self,
        specs: tuple[DaemonServiceSpec, ...],
    ) -> tuple[DaemonServiceSpec, ...]:
        merged: list[DaemonServiceSpec] = []
        seen_keys = {spec.key for spec in self._bootstrap_specs}
        existing_by_key = {spec.key: spec for spec in specs}
        for bootstrap_spec in self._bootstrap_specs:
            merged.append(existing_by_key.get(bootstrap_spec.key, bootstrap_spec))
            merged[-1] = bootstrap_spec
        for spec in specs:
            if spec.key in seen_keys:
                continue
            merged.append(spec)
        return tuple(merged)

    def _sync_bootstrap_specs(self, specs: tuple[DaemonServiceSpec, ...]) -> None:
        if not self._bootstrap_specs:
            return
        current_by_key = {spec.key: spec for spec in specs}
        self._bootstrap_specs = tuple(
            current_by_key.get(bootstrap_spec.key, bootstrap_spec)
            for bootstrap_spec in self._bootstrap_specs
        )

    def _refresh_bootstrap_specs(
        self,
        current: tuple[DaemonServiceSpec, ...],
    ) -> tuple[DaemonServiceSpec, ...]:
        merged = self._merge_bootstrap_specs(current)
        if merged != current:
            self._save_unlocked(merged)
        return merged

    def _load_raw_unlocked(self) -> tuple[DaemonServiceSpec, ...]:
        if not self._path.exists():
            return ()
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            return ()
        return tuple(DaemonServiceSpec(**item) for item in payload if isinstance(item, dict))

    def _save_unlocked(self, specs: tuple[DaemonServiceSpec, ...]) -> tuple[DaemonServiceSpec, ...]:
        self._sync_bootstrap_specs(specs)
        _write_text_atomically(
            self._path,
            json.dumps(
                [asdict(spec) for spec in specs],
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            ),
        )
        return specs

    def load(self) -> tuple[DaemonServiceSpec, ...]:
        with _file_lock(self._lock_path, shared=False):
            if not self._path.exists():
                return self._save_unlocked(self._bootstrap_specs)
            return self._refresh_bootstrap_specs(self._load_raw_unlocked())

    def save(self, specs: tuple[DaemonServiceSpec, ...]) -> tuple[DaemonServiceSpec, ...]:
        with _file_lock(self._lock_path, shared=False):
            return self._save_unlocked(specs)

    def update(
        self,
        mutator: Callable[[tuple[DaemonServiceSpec, ...]], tuple[DaemonServiceSpec, ...]],
    ) -> tuple[DaemonServiceSpec, ...]:
        with _file_lock(self._lock_path, shared=False):
            current = self._refresh_bootstrap_specs(self._load_raw_unlocked())
            updated = tuple(mutator(current))
            if updated == current:
                return current
            return self._save_unlocked(updated)

    def retire_keys(self, keys: tuple[str, ...]) -> tuple[DaemonServiceSpec, ...]:
        retired = {key.strip().lower() for key in keys if key.strip()}
        if not retired:
            return self.load()
        with _file_lock(self._lock_path, shared=False):
            self._bootstrap_specs = tuple(
                spec for spec in self._bootstrap_specs if spec.key not in retired
            )
            current = tuple(
                spec for spec in self._load_raw_unlocked() if spec.key not in retired
            )
            return self._save_unlocked(current)


class FileBackedDaemonInstanceStore:
    def __init__(self, root_dir: Path) -> None:
        self._path = root_dir / "instances.json"
        self._lock_path = root_dir / "instances.json.lock"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load_unlocked(self) -> tuple[DaemonInstance, ...]:
        if not self._path.exists():
            return ()
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            return ()
        instances: list[DaemonInstance] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            instances.append(
                DaemonInstance(
                    id=item["id"],
                    service_key=item["service_key"],
                    status=item.get("status", "stopped"),
                    worker_id=item.get("worker_id"),
                    pid=item.get("pid"),
                    endpoint=item.get("endpoint"),
                    started_at=_parse_datetime(item.get("started_at")),
                    last_healthcheck_at=_parse_datetime(item.get("last_healthcheck_at")),
                    last_error=item.get("last_error"),
                    metadata=dict(item.get("metadata") or {}),
                ),
            )
        return tuple(instances)

    def _save_unlocked(self, instances: tuple[DaemonInstance, ...]) -> tuple[DaemonInstance, ...]:
        _write_text_atomically(
            self._path,
            json.dumps(
                [
                    {
                        **asdict(instance),
                        "started_at": _serialize_datetime(instance.started_at),
                        "last_healthcheck_at": _serialize_datetime(
                            instance.last_healthcheck_at,
                        ),
                    }
                    for instance in instances
                ],
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            ),
        )
        return instances

    def list(self) -> tuple[DaemonInstance, ...]:
        with _file_lock(self._lock_path, shared=True):
            return self._load_unlocked()

    def save(self, instances: tuple[DaemonInstance, ...]) -> tuple[DaemonInstance, ...]:
        with _file_lock(self._lock_path, shared=False):
            return self._save_unlocked(instances)

    def update(
        self,
        mutator: Callable[[tuple[DaemonInstance, ...]], tuple[DaemonInstance, ...]],
    ) -> tuple[DaemonInstance, ...]:
        with _file_lock(self._lock_path, shared=False):
            current = self._load_unlocked()
            updated = tuple(mutator(current))
            if updated == current:
                return current
            return self._save_unlocked(updated)


class FileBackedDaemonLeaseStore:
    def __init__(self, root_dir: Path) -> None:
        self._path = root_dir / "leases.json"
        self._lock_path = root_dir / "leases.json.lock"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load_unlocked(self) -> tuple[DaemonLease, ...]:
        if not self._path.exists():
            return ()
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            return ()
        leases: list[DaemonLease] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            leases.append(
                DaemonLease(
                    id=item["id"],
                    service_key=item["service_key"],
                    instance_id=item["instance_id"],
                    owner_kind=item["owner_kind"],
                    owner_id=item["owner_id"],
                    status=item.get("status", "active"),
                    acquired_at=_parse_datetime(item.get("acquired_at")) or utcnow(),
                    heartbeat_at=_parse_datetime(item.get("heartbeat_at")),
                    expires_at=_parse_datetime(item.get("expires_at")),
                    metadata=dict(item.get("metadata") or {}),
                ),
            )
        return tuple(lease for lease in leases if lease.status == "active")

    def _save_unlocked(self, leases: tuple[DaemonLease, ...]) -> tuple[DaemonLease, ...]:
        active_leases = tuple(lease for lease in leases if lease.status == "active")
        _write_text_atomically(
            self._path,
            json.dumps(
                [
                    {
                        **asdict(lease),
                        "acquired_at": _serialize_datetime(lease.acquired_at),
                        "heartbeat_at": _serialize_datetime(lease.heartbeat_at),
                        "expires_at": _serialize_datetime(lease.expires_at),
                    }
                    for lease in active_leases
                ],
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            ),
        )
        return active_leases

    def list(self) -> tuple[DaemonLease, ...]:
        with _file_lock(self._lock_path, shared=True):
            return self._load_unlocked()

    def save(self, leases: tuple[DaemonLease, ...]) -> tuple[DaemonLease, ...]:
        with _file_lock(self._lock_path, shared=False):
            return self._save_unlocked(leases)

    def update(
        self,
        mutator: Callable[[tuple[DaemonLease, ...]], tuple[DaemonLease, ...]],
    ) -> tuple[DaemonLease, ...]:
        with _file_lock(self._lock_path, shared=False):
            current = self._load_unlocked()
            updated = tuple(mutator(current))
            if updated == current:
                return current
            return self._save_unlocked(updated)


class FileBackedDaemonLeaseEventLog:
    def __init__(self, root_dir: Path) -> None:
        self._path = root_dir / "lease_events.jsonl"
        self._lock_path = root_dir / "lease_events.jsonl.lock"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, records: tuple[dict[str, object], ...]) -> None:
        if not records:
            return
        with _file_lock(self._lock_path, shared=False):
            with self._path.open("a", encoding="utf-8") as handle:
                for record in records:
                    handle.write(
                        json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n",
                    )
