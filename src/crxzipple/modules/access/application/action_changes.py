from __future__ import annotations

from crxzipple.modules.access.application.action_contracts import JsonObject


def change_text(
    changes: JsonObject,
    *keys: str,
    default: str | None = None,
) -> str:
    for key in keys:
        value = changes.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if default is not None and default.strip():
        return default.strip()
    raise ValueError(f"{' or '.join(keys)} is required.")


def change_optional_text(changes: JsonObject, *keys: str) -> str | None:
    for key in keys:
        value = changes.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def change_object(changes: JsonObject, key: str) -> JsonObject:
    value = changes.get(key)
    return dict(value) if isinstance(value, dict) else {}


def change_bool(changes: JsonObject, key: str, *, default: bool) -> bool:
    value = changes.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def required_text(value: str | None, label: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise ValueError(f"{label} is required.")
    return normalized
