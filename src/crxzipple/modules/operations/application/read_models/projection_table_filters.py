from __future__ import annotations

from typing import Any

_TOOL_ACTIVE_STATUSES = frozenset(
    {"created", "queued", "dispatching", "running", "waiting", "cancel_requested"},
)
_TOOL_WAITING_STATUSES = _TOOL_ACTIVE_STATUSES - {"running"}
_TOOL_LONG_RUNNING_SECONDS = 300


def apply_table_projection_filters(
    payload: dict[str, Any],
    *,
    table: str,
    filters: dict[str, Any],
) -> None:
    section = payload.get(table)
    if not isinstance(section, dict):
        return
    rows = tuple(row for row in section.get("rows", ()) if isinstance(row, dict))
    filtered_rows = [
        row
        for row in rows
        if _row_matches_status(
            row,
            str(filters.get("status") or "all"),
            table=table,
        )
        and _row_matches_search(row, str(filters.get("search") or ""))
        and _row_matches_exact_filters(row, filters)
    ]
    offset = max(_int_filter(filters.get("offset")), 0)
    limit = max(_int_filter(filters.get("limit"), default=len(filtered_rows)), 1)
    section["total"] = len(filtered_rows)
    section["rows"] = filtered_rows[offset : offset + limit]


def apply_related_projection_filters(
    payload: dict[str, Any],
    *,
    module: str,
    primary_table: str,
    filters: dict[str, Any],
) -> None:
    if module != "access":
        return
    for table in (
        "missing_access",
        "provider_auth_blocked",
        "authentication_status",
        "access_usage",
        "setup_flows",
        "expiring_soon",
        "fallback_problems",
    ):
        if table == primary_table:
            continue
        apply_table_projection_filters(payload, table=table, filters=filters)


def _row_matches_status(
    row: dict[str, Any],
    status: str,
    *,
    table: str,
) -> bool:
    normalized = status.strip().lower()
    if not normalized or normalized == "all":
        return True
    row_status = str(row.get("status") or "").strip().lower()
    cells = row.get("cells")
    if isinstance(cells, dict):
        row_status = row_status or str(cells.get("status") or "").strip().lower()
    if table == "tool_runs":
        if normalized == "waiting":
            return row_status in _TOOL_WAITING_STATUSES
        if normalized == "long_running":
            duration = (
                _duration_text_seconds(str(cells.get("duration") or ""))
                if isinstance(cells, dict)
                else 0
            )
            return (
                row_status in _TOOL_ACTIVE_STATUSES
                and duration >= _TOOL_LONG_RUNNING_SECONDS
            )
    if normalized == "active":
        return row_status in {"active", "running", "queued", "waiting", "processing"}
    if normalized == "failed":
        return row_status in {"failed", "timed_out", "timeout", "error"}
    return row_status == normalized


def _duration_text_seconds(value: str) -> int:
    total = 0.0
    for part in value.strip().lower().split():
        if part.endswith("ms"):
            total += _float_text(part.removesuffix("ms")) / 1000
        elif part.endswith("s"):
            total += _float_text(part.removesuffix("s"))
        elif part.endswith("m"):
            total += _float_text(part.removesuffix("m")) * 60
        elif part.endswith("h"):
            total += _float_text(part.removesuffix("h")) * 3600
    return int(round(total))


def _float_text(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        return 0.0


def _row_matches_search(row: dict[str, Any], search: str) -> bool:
    needle = search.strip().lower()
    if not needle:
        return True
    return needle in _row_text(row)


def _row_matches_exact_filters(
    row: dict[str, Any],
    filters: dict[str, Any],
) -> bool:
    ignored = {
        "status",
        "search",
        "limit",
        "offset",
        "time_window",
        "include_ready",
        "include_disabled",
        "surface",
    }
    row_text = _row_text(row)
    cells = row.get("cells")
    for key, value in filters.items():
        if key in ignored:
            continue
        if value is None or isinstance(value, bool):
            continue
        normalized = str(value).strip().lower()
        if not normalized or normalized == "all":
            continue
        if isinstance(cells, dict) and key in cells:
            if str(cells.get(key) or "").strip().lower() != normalized:
                return False
            continue
        if normalized not in row_text:
            return False
    return True


def _row_text(row: dict[str, Any]) -> str:
    cells = row.get("cells")
    parts = [str(row.get("id") or ""), str(row.get("status") or "")]
    if isinstance(cells, dict):
        parts.extend(str(value) for value in cells.values())
    return " ".join(parts).lower()


def _int_filter(value: Any, *, default: int = 0) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError:
            return default
    return default
