from __future__ import annotations

import json
import os

from crxzipple.core.config_mobile_models import (
    MobileDeviceSettings,
    normalize_mobile_device_name,
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
        name = normalize_mobile_device_name(
            raw_name,
            label=f"APP_MOBILE_DEVICE_SPECS[{index}].name",
        )
        if name in seen:
            raise ValueError(
                f"APP_MOBILE_DEVICE_SPECS contains duplicate device '{name}'.",
            )
        seen.add(name)
        resolved.append(_mobile_device_settings_from_item(item, name=name))
    return tuple(resolved)


def _mobile_device_settings_from_item(
    item: dict[str, object],
    *,
    name: str,
) -> MobileDeviceSettings:
    return MobileDeviceSettings(
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
