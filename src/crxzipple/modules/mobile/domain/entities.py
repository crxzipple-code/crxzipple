from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from .exceptions import MobileValidationError
from .value_objects import _normalize_name, _normalize_optional_text


@dataclass(slots=True)
class MobileDeviceRuntimeState:
    device_name: str
    last_error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized_name = _normalize_name(self.device_name, label="Runtime device name")
        if normalized_name is None:
            raise MobileValidationError("Runtime device name is required.")
        self.device_name = normalized_name
        self.last_error = _normalize_optional_text(self.last_error)

    def clear_error(self) -> None:
        self.last_error = None

    def mark_command_failed(self, reason: str) -> None:
        self.last_error = _normalize_optional_text(reason)

    def next_ref_generation(self) -> int:
        current = self.metadata.get("current_ref_generation")
        try:
            numeric = int(current)
        except (TypeError, ValueError):
            numeric = 0
        return max(numeric + 1, 1)

    def remember_snapshot(
        self,
        *,
        generation: int,
        ref_count: int,
        snapshot_format: str,
        package_name: str | None = None,
        activity_name: str | None = None,
        source_length: int | None = None,
    ) -> None:
        self.metadata["current_ref_generation"] = max(int(generation), 1)
        self.metadata["last_snapshot_ref_count"] = max(int(ref_count), 0)
        self.metadata["last_snapshot_format"] = snapshot_format.strip()
        if source_length is not None:
            self.metadata["last_snapshot_source_length"] = max(int(source_length), 0)
        if package_name is not None:
            self.metadata["last_known_package"] = package_name.strip()
        if activity_name is not None:
            self.metadata["last_known_activity"] = activity_name.strip()
        self.clear_error()

    @property
    def current_ref_generation(self) -> int | None:
        current = self.metadata.get("current_ref_generation")
        try:
            numeric = int(current)
        except (TypeError, ValueError):
            return None
        return max(numeric, 1)

    @property
    def last_known_package(self) -> str | None:
        raw = self.metadata.get("last_known_package")
        return raw.strip() if isinstance(raw, str) and raw.strip() else None

    @property
    def last_known_activity(self) -> str | None:
        raw = self.metadata.get("last_known_activity")
        return raw.strip() if isinstance(raw, str) and raw.strip() else None

    @property
    def last_snapshot_ref_count(self) -> int | None:
        raw = self.metadata.get("last_snapshot_ref_count")
        try:
            numeric = int(raw)
        except (TypeError, ValueError):
            return None
        return max(numeric, 0)

    @property
    def last_snapshot_source_length(self) -> int | None:
        raw = self.metadata.get("last_snapshot_source_length")
        try:
            numeric = int(raw)
        except (TypeError, ValueError):
            return None
        return max(numeric, 0)

    @property
    def metadata_copy(self) -> dict[str, Any]:
        return cast(dict[str, Any], dict(self.metadata))
