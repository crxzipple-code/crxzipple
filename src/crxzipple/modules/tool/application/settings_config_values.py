from __future__ import annotations

from typing import Any, Iterable, Mapping

from crxzipple.shared.settings import ToolProviderConfig, ToolRootConfig


ToolProviderConfigLike = ToolProviderConfig | Mapping[str, Any]
ToolRootConfigLike = ToolRootConfig | Mapping[str, Any]


def provider_name(config: ToolProviderConfigLike) -> str:
    return required_text(lookup(config, "provider_id", "id", "name"), field_name="provider_id")


def enabled(config: ToolProviderConfigLike | ToolRootConfigLike) -> bool:
    raw = lookup(config, "enabled")
    if raw is None:
        return True
    if isinstance(raw, str):
        return raw.strip().lower() not in {"0", "false", "no", "off"}
    return bool(raw)


def lookup(config: object, *keys: str) -> object:
    if isinstance(config, Mapping):
        for key in keys:
            if key in config:
                return config[key]
        for bucket_name in ("discovery", "metadata"):
            bucket = config.get(bucket_name)
            if isinstance(bucket, Mapping):
                for key in keys:
                    if key in bucket:
                        return bucket[key]
        return None

    for key in keys:
        if hasattr(config, key):
            value = getattr(config, key)
            if value is not None and not (isinstance(value, str) and not value.strip()):
                return value
    for bucket_name in ("discovery", "metadata"):
        bucket = getattr(config, bucket_name, None)
        if isinstance(bucket, Mapping):
            for key in keys:
                if key in bucket:
                    return bucket[key]
    return None


def lookup_configured_value(config: object, *keys: str) -> object:
    for bucket_name in ("discovery", "metadata"):
        bucket = config.get(bucket_name) if isinstance(config, Mapping) else getattr(config, bucket_name, None)
        if isinstance(bucket, Mapping):
            for key in keys:
                if key in bucket:
                    return bucket[key]
    return lookup(config, *keys)


def required_text(value: object, *, field_name: str) -> str:
    text = optional_text(value)
    if text is None:
        raise ValueError(f"{field_name} cannot be empty.")
    return text


def optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def positive_int(value: object, *, default: int, field_name: str) -> int:
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a positive integer.") from exc
    if parsed < 1:
        raise ValueError(f"{field_name} must be a positive integer.")
    return parsed


def optional_positive_int(value: object, *, field_name: str) -> int | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return positive_int(value, default=1, field_name=field_name)


def string_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, Iterable):
        return tuple(str(item).strip() for item in value if str(item).strip())
    raise ValueError("Expected a string or iterable of strings.")


def dedupe_text(values: Iterable[str]) -> tuple[str, ...]:
    resolved: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        resolved.append(normalized)
    return tuple(resolved)
