from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from crxzipple.core.config_env import load_structured_config
from crxzipple.core.config_paths import PROJECT_ROOT

if TYPE_CHECKING:
    from crxzipple.modules.channels.domain.value_objects import (
        ChannelAccountProfile,
        ChannelProfile,
    )

DEFAULT_CHANNEL_PROFILE_DIR = PROJECT_ROOT / "config" / "channel_profiles"


def load_channel_profile_settings() -> tuple[ChannelProfile, ...]:
    profiles_by_type: dict[str, ChannelProfile] = {}

    for config_path in _iter_channel_profile_config_paths():
        for profile in _load_channel_profile_settings_from_path(config_path):
            profiles_by_type[profile.channel_type.strip().lower()] = profile

    raw = os.getenv("APP_CHANNEL_PROFILES")
    if raw is None or not raw.strip():
        return tuple(profiles_by_type.values())

    payload = json.loads(raw)
    items = _coerce_channel_profile_items(
        payload,
        source_description="APP_CHANNEL_PROFILES",
    )
    for item in items:
        profile = _build_channel_profile_settings(
            item,
            source_description="APP_CHANNEL_PROFILES",
        )
        profiles_by_type[profile.channel_type.strip().lower()] = profile

    return tuple(profiles_by_type.values())


def _iter_channel_profile_config_paths() -> tuple[Path, ...]:
    raw = os.getenv("APP_CHANNEL_PROFILE_PATHS", "").strip()
    if raw:
        configured_paths = [
            Path(part.strip()).expanduser()
            for part in raw.split(os.pathsep)
            if part.strip()
        ]
    elif DEFAULT_CHANNEL_PROFILE_DIR.exists():
        configured_paths = [DEFAULT_CHANNEL_PROFILE_DIR]
    else:
        configured_paths = []

    resolved_files: list[Path] = []
    for path in configured_paths:
        if path.is_dir():
            resolved_files.extend(
                candidate
                for pattern in ("*.yaml", "*.yml", "*.json")
                for candidate in sorted(path.glob(pattern))
                if candidate.is_file()
            )
            continue
        if path.is_file():
            resolved_files.append(path)

    unique_files: list[Path] = []
    seen: set[Path] = set()
    for path in resolved_files:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_files.append(resolved)
    return tuple(unique_files)


def _load_channel_profile_settings_from_path(
    config_path: Path,
) -> tuple[ChannelProfile, ...]:
    payload = load_structured_config(config_path)
    items = _coerce_channel_profile_items(payload, source_description=str(config_path))
    return tuple(
        _build_channel_profile_settings(item, source_description=str(config_path))
        for item in items
    )


def _coerce_channel_profile_items(
    payload: object,
    *,
    source_description: str,
) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        if isinstance(payload.get("profiles"), list):
            items = payload.get("profiles") or []
        else:
            items = [payload]
    elif isinstance(payload, list):
        items = payload
    else:
        raise ValueError(
            f"{source_description} channel profile config must decode to an object or list.",
        )
    resolved: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(
                f"{source_description} channel profile items must decode to JSON/YAML objects.",
            )
        resolved.append(dict(item))
    return resolved


def _build_channel_profile_settings(
    raw: object,
    *,
    source_description: str,
) -> ChannelProfile:
    from crxzipple.modules.channels.domain.value_objects import (
        ChannelCapabilities,
        ChannelProfile,
    )

    if not isinstance(raw, dict):
        raise ValueError(
            f"{source_description} channel profile items must decode to JSON/YAML objects.",
        )
    channel_type = str(raw.get("channel_type") or "").strip()
    if not channel_type:
        raise ValueError(f"{source_description} channel profile must define channel_type.")

    raw_capabilities = raw.get("capabilities")
    if raw_capabilities is None:
        capabilities = ChannelCapabilities()
    elif isinstance(raw_capabilities, dict):
        capabilities = ChannelCapabilities.from_payload(dict(raw_capabilities))
    else:
        raise ValueError(
            f"{source_description} channel profile '{channel_type}' capabilities must decode to an object.",
        )

    return ChannelProfile(
        channel_type=channel_type,
        enabled=bool(raw.get("enabled", True)),
        capabilities=capabilities,
        accounts=_channel_profile_accounts(
            raw,
            source_description=source_description,
            channel_type=channel_type,
        ),
        metadata=_channel_profile_metadata(
            raw,
            source_description=source_description,
            channel_type=channel_type,
        ),
    )


def _channel_profile_accounts(
    raw: dict[str, object],
    *,
    source_description: str,
    channel_type: str,
) -> tuple[ChannelAccountProfile, ...]:
    raw_accounts = raw.get("accounts")
    if raw_accounts is None:
        return ()
    if isinstance(raw_accounts, list):
        return tuple(
            _build_channel_account_profile_settings(
                item,
                source_description=source_description,
                channel_type=channel_type,
                index=index,
            )
            for index, item in enumerate(raw_accounts)
        )
    raise ValueError(
        f"{source_description} channel profile '{channel_type}' accounts must decode to a list.",
    )


def _channel_profile_metadata(
    raw: dict[str, object],
    *,
    source_description: str,
    channel_type: str,
) -> dict[str, Any]:
    raw_metadata = raw.get("metadata")
    if raw_metadata is None:
        return {}
    if isinstance(raw_metadata, dict):
        return dict(raw_metadata)
    raise ValueError(
        f"{source_description} channel profile '{channel_type}' metadata must decode to an object.",
    )


def _build_channel_account_profile_settings(
    raw: object,
    *,
    source_description: str,
    channel_type: str,
    index: int,
) -> ChannelAccountProfile:
    from crxzipple.modules.channels.domain.value_objects import ChannelAccountProfile

    if not isinstance(raw, dict):
        raise ValueError(
            f"{source_description} channel profile '{channel_type}' accounts[{index}] must decode to an object.",
        )
    account_id = str(raw.get("account_id") or "").strip()
    if not account_id:
        raise ValueError(
            f"{source_description} channel profile '{channel_type}' accounts[{index}] must define account_id.",
        )
    return ChannelAccountProfile.from_payload(
        {
            **raw,
            "account_id": account_id,
            "enabled": bool(raw.get("enabled", True)),
            "transport_mode": str(raw.get("transport_mode") or "push"),
            "metadata": _channel_account_metadata(
                raw,
                source_description=source_description,
                channel_type=channel_type,
                index=index,
            ),
        },
        channel_type=channel_type,
    )


def _channel_account_metadata(
    raw: dict[str, object],
    *,
    source_description: str,
    channel_type: str,
    index: int,
) -> dict[str, Any]:
    raw_metadata = raw.get("metadata")
    if raw_metadata is None:
        return {}
    if isinstance(raw_metadata, dict):
        return dict(raw_metadata)
    raise ValueError(
        f"{source_description} channel profile '{channel_type}' accounts[{index}] metadata must decode to an object.",
    )
