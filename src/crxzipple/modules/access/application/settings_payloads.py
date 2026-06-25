from __future__ import annotations

from typing import Any, Mapping

from crxzipple.modules.access.application.settings_action_contracts import JsonObject


def _change_bool(
    changes: Mapping[str, Any],
    key: str,
    *,
    default: bool,
) -> bool:
    value = changes.get(key)
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"0", "false", "no", "off"}:
            return False
        if normalized in {"1", "true", "yes", "on"}:
            return True
    return bool(value)


def _safe_binding_id_part(value: str) -> str:
    normalized = "".join(
        char if char.isalnum() or char in {"_", "-"} else "_" for char in value.strip()
    ).strip("_")
    return normalized or "unknown"


def _change_text(
    changes: Mapping[str, Any],
    *keys: str,
    default: str | None = None,
) -> str:
    value = _change_optional_text(changes, *keys)
    if value is not None:
        return value
    if default is not None:
        return default
    joined = " or ".join(keys)
    raise ValueError(f"change field '{joined}' is required.")


def _change_optional_text(changes: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = changes.get(key)
        if value is None:
            continue
        normalized = str(value).strip()
        if normalized:
            return normalized
    return None


def _payload_text(
    payload: Mapping[str, Any],
    *keys: str,
    default: str | None = None,
) -> str:
    value = _payload_optional_text(payload, *keys)
    if value is not None:
        return value
    if default is not None:
        return default
    raise ValueError(f"payload field '{' or '.join(keys)}' is required.")


def _payload_optional_text(payload: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        normalized = str(value).strip()
        if normalized:
            return normalized
    return None


def _payload_object(payload: Mapping[str, Any], key: str) -> JsonObject:
    value = payload.get(key)
    return dict(value) if isinstance(value, Mapping) else {}


def _payload_string_tuple(payload: Mapping[str, Any], key: str) -> tuple[str, ...]:
    return tuple(_string_list(payload.get(key)))


def _payload_requirement_sets(value: object) -> tuple[tuple[str, ...], ...]:
    if isinstance(value, (list, tuple)):
        result: list[tuple[str, ...]] = []
        for item in value:
            strings = tuple(_string_list(item))
            if strings:
                result.append(strings)
        return tuple(result)
    return ()


def _payload_slot_bindings(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, str] = {}
    for slot, binding_id in value.items():
        slot_text = str(slot).strip()
        binding_text = str(binding_id).strip()
        if slot_text and binding_text:
            result[slot_text] = binding_text
    return result


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []
