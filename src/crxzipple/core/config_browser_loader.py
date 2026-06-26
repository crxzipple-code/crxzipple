from __future__ import annotations

import json
import os

from crxzipple.core.config_browser_models import (
    DEFAULT_BROWSER_DEFAULT_PROFILE_NAME,
    DEFAULT_BROWSER_USER_CDP_URL,
    DEFAULT_BROWSER_USER_PROFILE_NAME,
    BrowserProfileSettings,
    normalize_browser_profile_driver,
    normalize_browser_profile_name,
)


def load_browser_profile_settings() -> tuple[BrowserProfileSettings, ...]:
    raw = os.getenv("APP_BROWSER_PROFILE_SPECS", "").strip()
    if not raw:
        return ensure_default_user_browser_profile_settings(
            (
                BrowserProfileSettings(name=DEFAULT_BROWSER_DEFAULT_PROFILE_NAME),
            ),
        )
    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError(
            "APP_BROWSER_PROFILE_SPECS must decode to a JSON array of objects.",
        )
    resolved_profiles: list[BrowserProfileSettings] = []
    seen: set[str] = set()
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(
                f"APP_BROWSER_PROFILE_SPECS[{index}] must be a JSON object.",
            )
        resolved_profiles.append(_browser_profile_from_item(item, index=index, seen=seen))
    if not resolved_profiles:
        raise ValueError("APP_BROWSER_PROFILE_SPECS must contain at least one profile.")
    return ensure_default_user_browser_profile_settings(tuple(resolved_profiles))


def load_browser_proxy_base_urls() -> tuple[tuple[str, str], ...]:
    raw = os.getenv("APP_BROWSER_PROXY_BASE_URLS", "").strip()
    if not raw:
        return ()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("APP_BROWSER_PROXY_BASE_URLS must decode to a JSON object.")
    resolved: list[tuple[str, str]] = []
    for key, value in payload.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(
                "APP_BROWSER_PROXY_BASE_URLS keys must be non-empty profile names.",
            )
        normalized_key = key.strip()
        if any(separator in normalized_key for separator in ("/", "\\")):
            raise ValueError(
                "APP_BROWSER_PROXY_BASE_URLS profile names must not contain path separators.",
            )
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"APP_BROWSER_PROXY_BASE_URLS entry for '{normalized_key}' must be a non-empty URL string.",
            )
        resolved.append((normalized_key, value.strip().rstrip("/")))
    return tuple(resolved)


def ensure_default_user_browser_profile_settings(
    profiles: tuple[BrowserProfileSettings, ...],
) -> tuple[BrowserProfileSettings, ...]:
    resolved_profiles = profiles
    if not any(
        profile.name == DEFAULT_BROWSER_USER_PROFILE_NAME
        for profile in resolved_profiles
    ):
        resolved_profiles = resolved_profiles + (
            BrowserProfileSettings(
                name=DEFAULT_BROWSER_USER_PROFILE_NAME,
                driver="existing-session",
                cdp_url=DEFAULT_BROWSER_USER_CDP_URL,
                attach_only=True,
            ),
        )
    return resolved_profiles


def _browser_profile_from_item(
    item: dict[str, object],
    *,
    index: int,
    seen: set[str],
) -> BrowserProfileSettings:
    raw_name = item.get("name")
    if not isinstance(raw_name, str):
        raise ValueError(
            f"APP_BROWSER_PROFILE_SPECS[{index}].name must be a non-empty string.",
        )
    name = normalize_browser_profile_name(
        raw_name,
        label=f"APP_BROWSER_PROFILE_SPECS[{index}].name",
    )
    if name in seen:
        raise ValueError(
            f"APP_BROWSER_PROFILE_SPECS contains duplicate profile '{name}'.",
        )
    seen.add(name)
    driver = _profile_driver_from_item(item, index=index)
    _reject_removed_profile_fields(item, index=index)
    return BrowserProfileSettings(
        name=name,
        cdp_url=_optional_profile_string(item, "cdp_url", index=index),
        cdp_port=_optional_profile_int(item, "cdp_port", index=index),
        user_data_dir=_optional_profile_string(item, "user_data_dir", index=index),
        profile_directory=_optional_profile_string(
            item,
            "profile_directory",
            index=index,
        ),
        driver=driver,
        enabled=_optional_profile_bool(item, "enabled", index=index, default=True),
        attach_only=_optional_profile_bool(
            item,
            "attach_only",
            index=index,
            default=False,
        ),
        autostart=_optional_profile_bool(
            item,
            "autostart",
            index=index,
            default=True,
        ),
        proxy_mode=_optional_profile_string(item, "proxy_mode", index=index) or "none",
        proxy_server=_optional_profile_string(item, "proxy_server", index=index),
        proxy_bypass_list=_optional_profile_string_tuple(
            item,
            "proxy_bypass_list",
            index=index,
        ),
        proxy_binding_id=_optional_profile_string(
            item,
            "proxy_binding_id",
            index=index,
        ),
        proxy_credential_kind=(
            _optional_profile_string(item, "proxy_credential_kind", index=index)
            or "basic"
        ),
        close_targets_on_release=_optional_profile_bool(
            item,
            "close_targets_on_release",
            index=index,
            default=True,
        ),
        close_targets_on_expire=_optional_profile_bool(
            item,
            "close_targets_on_expire",
            index=index,
            default=True,
        ),
        color=_optional_profile_string(item, "color", index=index),
    )


def _profile_driver_from_item(item: dict[str, object], *, index: int) -> str:
    raw_driver = item.get("driver")
    if raw_driver is None:
        return "managed"
    if not isinstance(raw_driver, str):
        raise ValueError(
            f"APP_BROWSER_PROFILE_SPECS[{index}].driver must be a string.",
        )
    return normalize_browser_profile_driver(
        raw_driver,
        label=f"APP_BROWSER_PROFILE_SPECS[{index}].driver",
    )


def _reject_removed_profile_fields(item: dict[str, object], *, index: int) -> None:
    removed = {
        "runtime_mode": (
            "runtime_mode has been removed; use driver, cdp_url, attach_only, "
            "autostart, and proxy_* fields."
        ),
        "transport": (
            "transport has been removed; use driver, cdp_url, attach_only, "
            "autostart, and proxy_* fields."
        ),
        "executable_path": (
            "executable_path has been removed; use APP_BROWSER_EXECUTABLE_PATH "
            "for the Browser system executable."
        ),
        "headless": (
            "headless has been removed; use APP_BROWSER_HEADLESS for the Browser "
            "system headless mode."
        ),
    }
    for field_name, message in removed.items():
        if field_name in item:
            raise ValueError(f"APP_BROWSER_PROFILE_SPECS[{index}].{message}")


def _optional_profile_string(
    item: dict[str, object],
    field_name: str,
    *,
    index: int,
) -> str | None:
    raw = item.get(field_name)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError(
            f"APP_BROWSER_PROFILE_SPECS[{index}].{field_name} must be a string when provided.",
        )
    return raw.strip()


def _optional_profile_int(
    item: dict[str, object],
    field_name: str,
    *,
    index: int,
) -> int | None:
    raw = item.get(field_name)
    if raw is None:
        return None
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise ValueError(
            f"APP_BROWSER_PROFILE_SPECS[{index}].{field_name} must be an integer when provided.",
        )
    return raw


def _optional_profile_bool(
    item: dict[str, object],
    field_name: str,
    *,
    index: int,
    default: bool,
) -> bool:
    raw = item.get(field_name)
    if raw is None:
        return default
    if not isinstance(raw, bool):
        raise ValueError(
            f"APP_BROWSER_PROFILE_SPECS[{index}].{field_name} must be a boolean when provided.",
        )
    return raw


def _optional_profile_string_tuple(
    item: dict[str, object],
    field_name: str,
    *,
    index: int,
) -> tuple[str, ...]:
    raw = item.get(field_name)
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(isinstance(entry, str) for entry in raw):
        raise ValueError(
            f"APP_BROWSER_PROFILE_SPECS[{index}].{field_name} must be a string array when provided.",
        )
    return tuple(raw)
