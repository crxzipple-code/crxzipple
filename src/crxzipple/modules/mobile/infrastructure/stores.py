from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from crxzipple.modules.mobile.domain import (
    MobileDeviceConfig,
    MobileDeviceRuntimeState,
    MobileStoredRef,
    MobileSystemConfig,
)


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
