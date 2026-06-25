from __future__ import annotations

from dataclasses import dataclass
import json
import os

_ALLOWED_MOBILE_PLATFORMS = {"android"}


@dataclass(frozen=True, slots=True)
class MobileDeviceSettings:
    name: str
    platform: str = "android"
    udid: str | None = None
    app_package: str | None = None
    app_activity: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "name",
            _normalize_mobile_device_name(self.name, label="Mobile device name"),
        )
        object.__setattr__(
            self,
            "platform",
            _normalize_mobile_platform(
                self.platform,
                label=f"Mobile device '{self.name}' platform",
            ),
        )
        object.__setattr__(
            self,
            "udid",
            self.udid.strip() if isinstance(self.udid, str) and self.udid.strip() else None,
        )
        object.__setattr__(
            self,
            "app_package",
            self.app_package.strip()
            if isinstance(self.app_package, str) and self.app_package.strip()
            else None,
        )
        object.__setattr__(
            self,
            "app_activity",
            self.app_activity.strip()
            if isinstance(self.app_activity, str) and self.app_activity.strip()
            else None,
        )


def load_mobile_device_settings() -> tuple[MobileDeviceSettings, ...]:
    raw = os.getenv("APP_MOBILE_DEVICE_SPECS", "").strip()
    if not raw:
        return ()
    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError(
            "APP_MOBILE_DEVICE_SPECS must decode to a JSON array of objects.",
        )
    resolved: list[MobileDeviceSettings] = []
    seen: set[str] = set()
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(
                f"APP_MOBILE_DEVICE_SPECS[{index}] must be a JSON object.",
            )
        raw_name = item.get("name")
        if not isinstance(raw_name, str):
            raise ValueError(
                f"APP_MOBILE_DEVICE_SPECS[{index}].name must be a non-empty string.",
            )
        name = _normalize_mobile_device_name(
            raw_name,
            label=f"APP_MOBILE_DEVICE_SPECS[{index}].name",
        )
        if name in seen:
            raise ValueError(
                f"APP_MOBILE_DEVICE_SPECS contains duplicate device '{name}'.",
            )
        seen.add(name)
        resolved.append(
            MobileDeviceSettings(
                name=name,
                platform=str(item.get("platform", "android")),
                udid=(
                    str(item["udid"]).strip()
                    if isinstance(item.get("udid"), str)
                    else None
                ),
                app_package=(
                    str(item["app_package"]).strip()
                    if isinstance(item.get("app_package"), str)
                    else None
                ),
                app_activity=(
                    str(item["app_activity"]).strip()
                    if isinstance(item.get("app_activity"), str)
                    else None
                ),
            )
        )
    return tuple(resolved)


def _normalize_mobile_device_name(value: str, *, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} must be a non-empty device name.")
    if any(separator in normalized for separator in ("/", "\\")):
        raise ValueError(f"{label} must not contain path separators.")
    return normalized


def _normalize_mobile_platform(value: str, *, label: str) -> str:
    normalized = value.strip().lower()
    if normalized in _ALLOWED_MOBILE_PLATFORMS:
        return normalized
    raise ValueError(f"{label} must be one of: android.")
