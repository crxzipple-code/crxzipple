from __future__ import annotations

from crxzipple.modules.operations.application.read_models.models import (
    OperationsModuleOverview,
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.modules_helpers import (
    s,
    short,
)


def sections_for_overview(
    overview: OperationsModuleOverview,
) -> tuple[OperationsTableSectionModel, ...]:
    section_specs = {
        "access": (
            ("missing_access", "Missing Access", overview.queue),
            ("access_targets", "Access Targets", overview.executor),
        ),
        "channels": (
            ("runtimes", "Channel Runtimes", overview.queue),
            ("dead_letters", "Dead Letters", overview.lane_locks),
            ("channel_types", "Channel Types", overview.executor),
        ),
        "memory": (
            ("memory_files", "Memory Files", overview.queue),
            ("agents", "Agents", overview.lane_locks),
        ),
        "skills": (
            ("installed_skills", "Installed Skills", overview.queue),
            ("sources", "Skill Sources", overview.lane_locks),
            ("requirements", "Declared Requirements", overview.executor),
        ),
        "events": (
            ("subscriptions", "Subscriptions", overview.queue),
            ("owners", "Owners", overview.lane_locks),
            ("observer_coverage", "Observer Coverage", overview.executor),
        ),
        "daemon": (
            ("service_sets", "Service Sets", overview.queue),
            ("services", "Services", overview.lane_locks),
            ("instances", "Instances", overview.executor),
        ),
    }.get(
        overview.module,
        (
            ("queue", "Queue", overview.queue),
            ("lane_locks", "Lane Locks", overview.lane_locks),
            ("executor", "Executor", overview.executor),
        ),
    )
    return tuple(
        table_section(
            section_id=section_id,
            title=title,
            rows=rows,
            route=f"/operations/{overview.module}?tab={section_id}",
        )
        for section_id, title, rows in section_specs
    )


def table_section(
    *,
    section_id: str,
    title: str,
    rows: tuple[dict[str, str], ...],
    route: str,
) -> OperationsTableSectionModel:
    keys = _table_keys(rows)
    return OperationsTableSectionModel(
        id=section_id,
        title=title,
        columns=tuple(
            OperationsTableColumnModel(key=key, label=_column_label(key))
            for key in keys
        ),
        rows=tuple(
            OperationsTableRowModel(
                id=_row_id(section_id, index, row),
                cells={key: s(row.get(key)) for key in keys},
                status=row.get("status"),
                tone=_row_tone(row),
            )
            for index, row in enumerate(rows)
        ),
        total=len(rows),
        view_all_route=route,
        empty_state=f"No {title.lower()} records.",
    )


def _table_keys(rows: tuple[dict[str, str], ...]) -> tuple[str, ...]:
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    return tuple(keys)


def _column_label(key: str) -> str:
    return " ".join(part.capitalize() for part in key.split("_") if part) or key


def _row_id(section_id: str, index: int, row: dict[str, str]) -> str:
    for key in (
        "id",
        "key",
        "runtime_id",
        "subscription_id",
        "service_key",
        "path",
        "name",
    ):
        value = row.get(key)
        if value:
            return short(value, 80)
    return f"{section_id}:{index}"


def _row_tone(row: dict[str, str]) -> str:
    status = s(row.get("status")).lower()
    if any(
        token in status
        for token in (
            "error",
            "failed",
            "stuck",
            "dead",
            "missing",
            "blocked",
            "stopped",
        )
    ):
        return "danger"
    if any(token in status for token in ("warning", "lagging", "stale", "degraded")):
        return "warning"
    if any(
        token in status
        for token in (
            "ready",
            "healthy",
            "online",
            "installed",
            "registered",
            "configured",
        )
    ):
        return "success"
    return "neutral"
