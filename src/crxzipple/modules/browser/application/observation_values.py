from __future__ import annotations

from typing import Any, Mapping


def _result_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    value = payload.get("value")
    if isinstance(value, dict):
        result = value.get("result")
        if isinstance(result, dict):
            return result
    return payload


def _successful_result_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict) or payload.get("ok") is False:
        return None
    return _result_payload(payload)


def _mapping_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _list_of_mappings(value: Any, *, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    return [
        {str(key): item for key, item in raw_item.items()}
        for raw_item in value[:limit]
        if isinstance(raw_item, Mapping)
    ]


def _optional_error(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict) or payload.get("ok") is not False:
        return None
    error = payload.get("error")
    if isinstance(error, dict):
        return error
    return {"message": "Browser observation section failed."}


def _text_list(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    return [
        item
        for item in (_payload_text(entry) for entry in value[:limit])
        if item is not None
    ]


def _payload_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _payload_text_list(value: Any) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    return [
        item for item in (_payload_text(entry) for entry in value) if item is not None
    ]


def _payload_bool(payload: Mapping[str, Any], key: str, *, default: bool) -> bool:
    value = payload.get(key)
    if value is None:
        return default
    return bool(value)


def _payload_int(
    payload: Mapping[str, Any],
    key: str,
    *,
    default: int | None,
) -> int | None:
    value = payload.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return default
    return normalized if normalized >= 0 else default


def _safe_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
