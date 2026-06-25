from __future__ import annotations


def optional_dict(value: object) -> dict[str, object] | None:
    return dict(value) if isinstance(value, dict) else None


def copy_first_text(
    target: dict[str, object],
    target_key: str,
    *sources: dict[str, object],
    source_keys: tuple[str, ...] | None = None,
) -> None:
    keys = source_keys or (target_key,)
    for source in sources:
        for key in keys:
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                target[target_key] = value.strip()
                return


def copy_first_int(
    target: dict[str, object],
    target_key: str,
    *sources: dict[str, object],
    source_keys: tuple[str, ...] | None = None,
) -> None:
    keys = source_keys or (target_key,)
    for source in sources:
        for key in keys:
            value = source.get(key)
            if value in (None, "", {}, []):
                continue
            target[target_key] = int_value(value)
            return


def int_value(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    if isinstance(value, str):
        try:
            return max(int(value), 0)
        except ValueError:
            return 0
    return 0


def bounded_text(value: str, *, limit: int) -> str:
    if len(value) <= limit:
        return value
    if limit <= 1:
        return value[:limit]
    return value[: limit - 1].rstrip() + "..."


def enum_or_text(value: object) -> str | None:
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str):
        return enum_value
    if isinstance(value, str):
        return value
    return None


def iso_or_none(value: object) -> str | None:
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())
    return None
