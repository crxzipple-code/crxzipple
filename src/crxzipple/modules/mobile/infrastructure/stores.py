from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import fcntl
import json
from dataclasses import asdict
import os
from pathlib import Path
import tempfile

from crxzipple.modules.mobile.domain import (
    MobileDeviceLease,
    MobileDeviceConfig,
    MobileDeviceRuntimeState,
    MobileExecutionError,
    MobileStoredRef,
    MobileSystemConfig,
)


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _utcnow() -> datetime:
    return datetime.now(UTC)


@contextmanager
def _file_lock(path: Path, *, shared: bool):
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


class FileBackedMobileSystemConfigStore:
    def __init__(self, root_dir: Path, *, bootstrap_config: MobileSystemConfig) -> None:
        self._path = root_dir / "system.json"
        self._bootstrap_config = bootstrap_config
        if not self._path.exists():
            self.save(bootstrap_config)

    def load(self) -> MobileSystemConfig:
        if not self._path.exists():
            return self.save(self._bootstrap_config)
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        allowed_device_keys = {"name", "platform", "udid", "app_package", "app_activity"}
        return MobileSystemConfig(
            default_device=payload.get("default_device"),
            devices=tuple(
                MobileDeviceConfig(
                    **{
                        key: value
                        for key, value in item.items()
                        if key in allowed_device_keys
                    }
                )
                for item in payload.get("devices", [])
                if isinstance(item, dict)
            ),
            adb_binary=payload.get("adb_binary", "adb"),
        )

    def save(self, config: MobileSystemConfig) -> MobileSystemConfig:
        payload = asdict(config)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return config


class FileBackedMobileRuntimeStateStore:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, *, device_name: str) -> Path:
        return self.root_dir / f"{device_name}.json"

    def get(self, *, device_name: str) -> MobileDeviceRuntimeState | None:
        path = self._path(device_name=device_name)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return MobileDeviceRuntimeState(
            device_name=payload["device_name"],
            last_error=payload.get("last_error"),
            metadata=dict(payload.get("metadata") or {}),
        )

    def save(self, state: MobileDeviceRuntimeState) -> None:
        path = self._path(device_name=state.device_name)
        path.write_text(
            json.dumps(
                {
                    "device_name": state.device_name,
                    "last_error": state.last_error,
                    "metadata": state.metadata,
                },
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    def delete(self, *, device_name: str) -> None:
        path = self._path(device_name=device_name)
        if path.exists():
            path.unlink()


class FileBackedMobileDeviceLeaseStore:
    def __init__(self, root_dir: Path) -> None:
        self._path = root_dir / "leases.json"
        self._lock_path = root_dir / "leases.json.lock"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load_unlocked(self) -> tuple[MobileDeviceLease, ...]:
        if not self._path.exists():
            return ()
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            return ()
        leases: list[MobileDeviceLease] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            leases.append(
                MobileDeviceLease(
                    id=item["id"],
                    device_name=item["device_name"],
                    owner_kind=item["owner_kind"],
                    owner_id=item["owner_id"],
                    status=item.get("status", "active"),
                    acquired_at=_parse_datetime(item.get("acquired_at")) or _utcnow(),
                    heartbeat_at=_parse_datetime(item.get("heartbeat_at")),
                    expires_at=_parse_datetime(item.get("expires_at")),
                    metadata=dict(item.get("metadata") or {}),
                ),
            )
        now = _utcnow()
        active: list[MobileDeviceLease] = []
        for lease in leases:
            if lease.is_active_at(now):
                active.append(lease)
            else:
                lease.expire()
        return tuple(active)

    def _save_unlocked(
        self,
        leases: tuple[MobileDeviceLease, ...],
    ) -> tuple[MobileDeviceLease, ...]:
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

    def acquire(
        self,
        *,
        device_name: str,
        owner_kind: str,
        owner_id: str,
        ttl_seconds: int,
    ) -> MobileDeviceLease:
        with _file_lock(self._lock_path, shared=False):
            current = self._load_unlocked()
            for lease in current:
                if lease.device_name != device_name:
                    continue
                if lease.owner_kind == owner_kind and lease.owner_id == owner_id:
                    lease.heartbeat(ttl_seconds=ttl_seconds)
                    self._save_unlocked(current)
                    return lease
                raise MobileExecutionError(
                    "Mobile device "
                    f"'{device_name}' is currently leased by "
                    f"{lease.owner_kind}:{lease.owner_id}.",
                )
            lease = MobileDeviceLease.create(
                device_name=device_name,
                owner_kind=owner_kind,
                owner_id=owner_id,
                ttl_seconds=ttl_seconds,
            )
            self._save_unlocked((*current, lease))
            return lease

    def release(self, *, lease_id: str, reason: str = "released") -> None:
        with _file_lock(self._lock_path, shared=False):
            leases = list(self._load_unlocked())
            for lease in leases:
                if lease.id != lease_id:
                    continue
                lease.metadata["release_reason"] = reason.strip() or "released"
                lease.release()
                break
            self._save_unlocked(tuple(leases))

    def list_active(
        self,
        *,
        device_name: str | None = None,
    ) -> tuple[MobileDeviceLease, ...]:
        with _file_lock(self._lock_path, shared=False):
            leases = self._save_unlocked(self._load_unlocked())
        if device_name is None:
            return leases
        return tuple(lease for lease in leases if lease.device_name == device_name)


class FileBackedMobileRefStore:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, *, device_name: str, generation: int) -> Path:
        return self.root_dir / f"{device_name}__g{max(int(generation), 1)}.json"

    def get_refs(
        self,
        *,
        device_name: str,
        generation: int,
    ) -> tuple[MobileStoredRef, ...]:
        path = self._path(device_name=device_name, generation=generation)
        if not path.exists():
            return ()
        payload = json.loads(path.read_text(encoding="utf-8"))
        return tuple(MobileStoredRef(**item) for item in payload if isinstance(item, dict))

    def save_refs(
        self,
        *,
        device_name: str,
        generation: int,
        refs: tuple[MobileStoredRef, ...],
    ) -> None:
        path = self._path(device_name=device_name, generation=generation)
        path.write_text(
            json.dumps([asdict(ref) for ref in refs], ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def delete_refs(
        self,
        *,
        device_name: str,
        generation: int,
    ) -> None:
        path = self._path(device_name=device_name, generation=generation)
        if path.exists():
            path.unlink()
