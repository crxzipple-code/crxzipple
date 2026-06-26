from __future__ import annotations

from dataclasses import dataclass

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
            normalize_mobile_device_name(self.name, label="Mobile device name"),
        )
        object.__setattr__(
            self,
            "platform",
            normalize_mobile_platform(
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


def normalize_mobile_device_name(value: str, *, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} must be a non-empty device name.")
    if any(separator in normalized for separator in ("/", "\\")):
        raise ValueError(f"{label} must not contain path separators.")
    return normalized


def normalize_mobile_platform(value: str, *, label: str) -> str:
    normalized = value.strip().lower()
    if normalized in _ALLOWED_MOBILE_PLATFORMS:
        return normalized
    raise ValueError(f"{label} must be one of: android.")
