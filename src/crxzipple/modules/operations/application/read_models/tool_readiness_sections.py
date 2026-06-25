from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.tool_metric_values import (
    runs_since,
)
from crxzipple.modules.operations.application.read_models.tool_readiness_risk import (
    tool_readiness_risk,
)
from crxzipple.modules.operations.application.read_models.tool_run_error_diagnostics import (
    looks_like_access_failure,
)
from crxzipple.modules.operations.application.read_models.ports_tooling import (
    OperationsToolQueryPort,
)
from crxzipple.modules.tool.domain import Tool, ToolRun


def auth_missing_section(
    tools: list[Tool],
    runs: list[ToolRun],
    *,
    tool_service: OperationsToolQueryPort | None = None,
    access_service: Any | None,
    now: datetime,
) -> OperationsTableSectionModel:
    failed_by_tool: Counter[str] = Counter(
        run.tool_id for run in runs if looks_like_access_failure(run)
    )
    recent_by_tool: Counter[str] = Counter(
        run.tool_id for run in runs_since(runs, since=now - timedelta(hours=24))
    )
    rows: list[OperationsTableRowModel] = []
    for tool in sorted(
        [
            item
            for item in tools
            if item.access_requirement_sets
            or item.credential_requirements
            or item.runtime_requirement_sets
        ],
        key=lambda item: item.id,
    ):
        readiness = tool_readiness_risk(
            tool,
            tool_service=tool_service,
            access_service=access_service,
        )
        if readiness["ready"]:
            continue
        rows.append(
            OperationsTableRowModel(
                id=tool.id,
                cells={
                    "tool": tool.id,
                    "category": readiness["category"],
                    "status": readiness["status"],
                    "issue": readiness["reason"],
                    "required_access": readiness["requirements"],
                    "missing_access": readiness["missing"],
                    "affected_24h": str(recent_by_tool[tool.id]),
                    "access_failures": str(failed_by_tool[tool.id]),
                    "setup": readiness["setup"],
                    "action": readiness["action"],
                    "route": readiness["route"],
                },
                status=readiness["status"],
                tone=_readiness_risk_tone(readiness),
            ),
        )
    known_tool_ids = {tool.id for tool in tools}
    row_tool_ids = {row.id for row in rows}
    for tool_id, count in sorted(failed_by_tool.items()):
        if tool_id in row_tool_ids:
            continue
        if tool_id in known_tool_ids:
            tool = next((item for item in tools if item.id == tool_id), None)
            if tool is not None and tool.access_requirement_sets:
                continue
            issue = "access failure observed"
        else:
            issue = "access failure observed for unknown tool"
        if count <= 0:
            continue
        rows.append(
            OperationsTableRowModel(
                id=f"failed-access:{tool_id}",
                cells={
                    "tool": tool_id,
                    "status": "observed_failure",
                    "issue": issue,
                    "required_access": "-",
                    "missing_access": "-",
                    "affected_24h": str(recent_by_tool[tool_id]),
                    "access_failures": str(count),
                    "setup": "-",
                    "action": "Open Trace",
                    "route": "-",
                },
                status="blocked",
                tone="danger",
            ),
        )
    rows.sort(key=_auth_missing_row_sort_key)
    return OperationsTableSectionModel(
        id="auth_missing",
        title="Runtime Risk / Access",
        columns=_columns(
            ("tool", "Tool"),
            ("category", "Category"),
            ("status", "Status"),
            ("issue", "Issue"),
            ("required_access", "Required Access"),
            ("missing_access", "Missing Access"),
            ("affected_24h", "Affected (24h)"),
            ("access_failures", "Access Failures"),
            ("setup", "Setup"),
            ("action", "Action"),
        ),
        rows=tuple(rows[:50]),
        total=len(rows),
        view_all_route="/operations/tool?tab=risk",
        empty_state="No access or runtime readiness risks detected.",
    )


def _auth_missing_row_sort_key(row: OperationsTableRowModel) -> tuple[int, int, str]:
    cells = row.cells
    affected = _int_value(cells.get("affected_24h"))
    failures = _int_value(cells.get("access_failures"))
    return (-affected, -failures, row.id)


def _readiness_risk_tone(readiness: dict[str, Any]) -> str:
    status = str(readiness.get("status") or "")
    if status in {"unsupported", "unknown"}:
        return "danger"
    if status == "degraded":
        return "warning"
    return "warning" if readiness.get("setup") == "available" else "danger"


def _columns(*items: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(
        OperationsTableColumnModel(key=column_id, label=label)
        for column_id, label in items
    )


def _int_value(value: object | None) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("-") and stripped[1:].isdigit():
            return int(stripped)
        if stripped.isdigit():
            return int(stripped)
    return 0
