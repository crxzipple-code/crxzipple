from __future__ import annotations

from typing import Mapping


def get_value(obj: object, name: str, default: object = None) -> object:
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def string_value(obj: object, name: str) -> str:
    value = get_value(obj, name)
    normalized = optional_string(value)
    return normalized or ""


def optional_string(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def safe_public_string(value: object) -> str | None:
    if value is None:
        return None
    return str(value).strip() or None


def mapping_value(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def bool_value(obj: object, name: str, *, default: bool) -> bool:
    value = get_value(obj, name, default)
    return bool(value)


def legacy_list(service: object, method_names: tuple[str, ...]) -> tuple[object, ...]:
    if service is None:
        return ()
    for method_name in method_names:
        method = getattr(service, method_name, None)
        if callable(method):
            try:
                return tuple(method())
            except TypeError:
                continue
    return ()


def dedupe_legacy_items(
    items: tuple[object, ...],
    *,
    identity_name: str,
) -> tuple[object, ...]:
    resolved: dict[str, object] = {}
    anonymous: list[object] = []
    for item in items:
        identity = optional_string(get_value(item, identity_name))
        if not identity:
            anonymous.append(item)
            continue
        resolved.setdefault(identity, item)
    return (*tuple(resolved.values()), *tuple(anonymous))
