from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.shared.time import format_datetime_utc


def table_section(
    *,
    section_id: str,
    title: str,
    rows: tuple[dict[str, str], ...],
    total: int,
    empty_state: str,
) -> OperationsTableSectionModel:
    keys = table_keys(rows)
    return OperationsTableSectionModel(
        id=section_id,
        title=title,
        columns=tuple(
            OperationsTableColumnModel(
                key=key,
                label=" ".join(part.capitalize() for part in key.split("_")),
            )
            for key in keys
        ),
        rows=tuple(
            OperationsTableRowModel(
                id=row.get("id", f"{section_id}:{index}"),
                cells={key: row.get(key, "") for key in keys},
                status=row.get("status"),
                tone=row_tone(row),
            )
            for index, row in enumerate(rows)
        ),
        total=total,
        view_all_route=f"/operations/context_workspace?tab={section_id}",
        empty_state=empty_state,
    )


def section_rows(
    sections: tuple[OperationsTableSectionModel, ...],
    section_id: str,
) -> tuple[dict[str, str], ...]:
    for section in sections:
        if section.id == section_id:
            return tuple(dict(row.cells) for row in section.rows)
    return ()


def nodes_from_view(view: Any | None) -> tuple[Any, ...]:
    if view is None:
        return ()
    return tuple(getattr(view, "nodes", ()) or ())


def table_keys(rows: tuple[dict[str, str], ...]) -> tuple[str, ...]:
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key == "id" or key in keys:
                continue
            keys.append(key)
    return tuple(keys)


def estimate_tokens(estimate: Any | None) -> int:
    if estimate is None:
        return 0
    return (
        int(getattr(estimate, "text_tokens", 0) or 0)
        + int(getattr(estimate, "tool_schema_tokens", 0) or 0)
        + int(getattr(estimate, "file_tokens", 0) or 0)
    )


def format_time(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return format_datetime_utc(value)
    except Exception:
        return str(value)


def text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def short_text(value: str, *, max_length: int = 40) -> str:
    if not value:
        return "-"
    if len(value) <= max_length:
        return value
    return f"{value[: max_length - 3]}..."


def metadata(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def metadata_int(metadata: dict[str, Any], key: str) -> int:
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


def metadata_list(metadata: dict[str, Any], key: str) -> tuple[Any, ...]:
    value = metadata.get(key)
    if isinstance(value, list):
        return tuple(value)
    if isinstance(value, tuple):
        return value
    return ()


def health_tone(health: str) -> str:
    if health == "healthy":
        return "success"
    if health == "error":
        return "danger"
    return "warning"


def row_tone(row: dict[str, str]) -> str:
    status = row.get("status", "").lower()
    if status in {"active", "healthy", "visible"}:
        return "success"
    if status in {"warning", "collapsed"}:
        return "warning"
    if status in {"error", "failed"}:
        return "danger"
    return "neutral"
