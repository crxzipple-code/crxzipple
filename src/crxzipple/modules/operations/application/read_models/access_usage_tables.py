from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.access_common import (
    status_label,
    tone_for_status,
)
from crxzipple.modules.operations.application.read_models.access_target_projection import (
    setup_flow_records,
    target_label,
    target_worst_status,
    usage_records,
)
from crxzipple.modules.operations.application.read_models.access_values import (
    bool_value,
    dict_value,
    text,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)


def access_usage_table(
    targets: tuple[dict[str, Any], ...],
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for record in usage_records(targets):
        target = record["target"]
        usage = record["usage"]
        status = target_worst_status(target)
        rows.append(
            OperationsTableRowModel(
                id=f"{text(target.get('resource_id'), '')}:{text(usage.get('usage_type'), '')}:{text(usage.get('usage_id'), '')}",
                cells={
                    "consumer": text(usage.get("display_name") or usage.get("usage_id")),
                    "usage_type": text(usage.get("usage_type")),
                    "usage_id": text(usage.get("usage_id")),
                    "asset": target_label(target),
                    "status": status_label(status),
                    "enabled": "Yes" if bool_value(usage.get("enabled")) else "No",
                },
                status=status_label(status),
                tone=tone_for_status(status),
            )
        )
    return OperationsTableSectionModel(
        id="access_usage",
        title="Access Usage",
        columns=(
            OperationsTableColumnModel("consumer", "Consumer"),
            OperationsTableColumnModel("usage_type", "Usage Type"),
            OperationsTableColumnModel("usage_id", "Usage ID"),
            OperationsTableColumnModel("asset", "Asset"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("enabled", "Enabled"),
        ),
        rows=tuple(rows[:160]),
        total=len(rows),
        empty_state="No access usage records.",
    )


def setup_flows_table(
    targets: tuple[dict[str, Any], ...],
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for record in setup_flow_records(targets):
        target = record["target"]
        check = record["check"]
        flow = dict_value(check.get("setup_flow"))
        rows.append(
            OperationsTableRowModel(
                id=f"{text(target.get('resource_id'), '')}:{text(check.get('requirement'), '')}",
                cells={
                    "asset": target_label(target),
                    "flow": text(flow.get("kind")),
                    "title": text(flow.get("title")),
                    "requirement": text(check.get("requirement")),
                    "action": text(flow.get("action_label") or "Setup"),
                    "path": text(flow.get("path")),
                },
                status=text(check.get("status"), ""),
                tone=tone_for_status(check.get("status")),
            )
        )
    return OperationsTableSectionModel(
        id="setup_flows",
        title="Setup Flows",
        columns=(
            OperationsTableColumnModel("asset", "Asset"),
            OperationsTableColumnModel("flow", "Flow Type"),
            OperationsTableColumnModel("title", "Title"),
            OperationsTableColumnModel("requirement", "Requirement"),
            OperationsTableColumnModel("action", "Action"),
            OperationsTableColumnModel("path", "Path"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No setup flows.",
    )


def expiring_soon_table(
    targets: tuple[dict[str, Any], ...],
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for record in setup_flow_records(targets):
        flow = dict_value(record["check"].get("setup_flow"))
        expires_at = text(flow.get("expires_at"), "")
        if not expires_at:
            continue
        target = record["target"]
        rows.append(
            OperationsTableRowModel(
                id=f"{text(target.get('resource_id'), '')}:{expires_at}",
                cells={
                    "asset": target_label(target),
                    "expires_at": expires_at,
                    "action": "Setup",
                },
                status=target_worst_status(target),
                tone="warning",
            )
        )
    return OperationsTableSectionModel(
        id="expiring_soon",
        title="Expiring Soon",
        columns=(
            OperationsTableColumnModel("asset", "Asset"),
            OperationsTableColumnModel("expires_at", "Expires At"),
            OperationsTableColumnModel("action", "Action"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No expiring access flows.",
    )
