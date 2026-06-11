"""Shared metadata helpers for the Context Workspace orchestration adapter."""

from __future__ import annotations


def metadata_dict(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def metadata_int(metadata: dict[str, object], key: str) -> int:
    value = metadata.get(key)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return 0


def metadata_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def metadata_positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        parsed = int(value)
        return parsed if parsed > 0 else None
    if isinstance(value, str) and value.strip():
        try:
            parsed = int(value.strip())
        except ValueError:
            return None
        return parsed if parsed > 0 else None
    return None


def metadata_string_list(value: object) -> list[str]:
    if isinstance(value, str):
        candidates: tuple[object, ...] = (value,)
    elif isinstance(value, (list, tuple, set, frozenset)):
        candidates = tuple(value)
    else:
        return []
    items: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        item = candidate.strip()
        if item and item not in items:
            items.append(item)
    return items


def estimate_text_tokens(text: str) -> int:
    normalized = text or ""
    return max((len(normalized) + 3) // 4, 1) if normalized else 0


def estimate_text_tokens_from_chars(chars: int) -> int:
    return max((max(chars, 0) + 3) // 4, 1) if chars > 0 else 0
