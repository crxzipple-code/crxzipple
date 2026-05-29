from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from crxzipple.shared.settings import MemoryConfig


@dataclass(frozen=True, slots=True)
class MemorySettingsBootstrapConfig:
    storage_root: str = ".crxzipple/memory"
    retrieval_backend: str = "keyword"
    vector_provider: str = "local"
    vector_model: str | None = None
    vector_base_url: str | None = None
    vector_credential_binding_id: str | None = None
    vector_timeout_seconds: int = 30
    watch_interval_seconds: float = 300.0


def memory_bootstrap_config_from_settings(
    config: MemoryConfig | Mapping[str, Any],
) -> MemorySettingsBootstrapConfig:
    payload = _payload_from_config(config)
    defaults = _mapping(payload.get("defaults"))
    metadata = _mapping(payload.get("metadata"))

    return MemorySettingsBootstrapConfig(
        storage_root=_optional_text(
            _first_present(payload, defaults, metadata, key="storage_root"),
        )
        or ".crxzipple/memory",
        retrieval_backend=_normalized_choice(
            _first_present(payload, defaults, metadata, key="retrieval_backend"),
            default="keyword",
            allowed={"keyword", "hybrid", "vector"},
            field_name="retrieval_backend",
        ),
        vector_provider=_normalized_choice(
            _first_present(payload, defaults, metadata, key="vector_provider"),
            default="local",
            allowed={"local", "openai_compatible"},
            field_name="vector_provider",
        ),
        vector_model=_optional_text(
            _first_present(defaults, payload, metadata, key="vector_model"),
        ),
        vector_base_url=_optional_text(
            _first_present(defaults, payload, metadata, key="vector_base_url"),
        ),
        vector_credential_binding_id=_optional_text(
            _first_present(defaults, payload, metadata, key="vector_credential_binding_id"),
        ),
        vector_timeout_seconds=_positive_int(
            _first_present(defaults, payload, metadata, key="vector_timeout_seconds"),
            default=30,
            field_name="vector_timeout_seconds",
        ),
        watch_interval_seconds=_non_negative_float(
            _first_present(payload, defaults, metadata, key="watch_interval_seconds"),
            default=300.0,
            field_name="watch_interval_seconds",
        ),
    )


def _payload_from_config(config: MemoryConfig | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(config, MemoryConfig):
        return dict(config.to_payload())
    if isinstance(config, Mapping):
        return dict(config)
    raise TypeError("Memory settings config must be a MemoryConfig or mapping.")


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first_present(*mappings: Mapping[str, Any], key: str) -> object:
    for mapping in mappings:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalized_choice(
    value: object,
    *,
    default: str,
    allowed: set[str],
    field_name: str,
) -> str:
    normalized = (_optional_text(value) or default).lower()
    if normalized not in allowed:
        raise ValueError(f"{field_name} must be one of: {', '.join(sorted(allowed))}.")
    return normalized


def _positive_int(value: object, *, default: int, field_name: str) -> int:
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    parsed = int(value)
    if parsed < 1:
        raise ValueError(f"{field_name} must be positive.")
    return parsed


def _non_negative_float(value: object, *, default: float, field_name: str) -> float:
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    parsed = float(value)
    if parsed < 0:
        raise ValueError(f"{field_name} cannot be negative.")
    return parsed


__all__ = [
    "MemorySettingsBootstrapConfig",
    "memory_bootstrap_config_from_settings",
]
