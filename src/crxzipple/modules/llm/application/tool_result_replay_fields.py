from __future__ import annotations


def dict_value(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def metadata_artifact_ids(metadata: dict[str, object]) -> tuple[str, ...]:
    raw = metadata.get("artifact_ids")
    if not isinstance(raw, list):
        return ()
    values = [optional_text(item) for item in raw]
    return tuple(dict.fromkeys(value for value in values if value is not None))


def text_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    values = [optional_text(item) for item in value]
    return tuple(dict.fromkeys(item for item in values if item is not None))


def optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def bounded_text(value: str, *, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: max(0, limit - 1)].rstrip()}…"


def append_optional_line(
    lines: list[str],
    label: str,
    value: object,
) -> None:
    text = optional_text(value)
    if text is not None:
        lines.append(f"{label}: {text}")


def append_text_list_line(
    lines: list[str],
    label: str,
    value: object,
) -> None:
    values = text_list(value)
    if values:
        lines.append(f"{label}: {'; '.join(values[:8])}")


__all__ = [
    "append_optional_line",
    "append_text_list_line",
    "bounded_text",
    "dict_value",
    "metadata_artifact_ids",
    "optional_int",
    "optional_text",
    "text_list",
]
