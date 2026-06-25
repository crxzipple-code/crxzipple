from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.access_common import (
    status_label,
    tone_for_status,
)
from crxzipple.modules.operations.application.read_models.access_target_projection import (
    setup_flow_records,
    target_checks,
    target_metadata,
)
from crxzipple.modules.operations.application.read_models.access_values import (
    bool_value,
    dict_value,
    short,
    text,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)


def checks_table(target: dict[str, Any]) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for index, check in enumerate(target_checks(target)):
        status = text(check.get("status"), "unknown")
        rows.append(
            OperationsTableRowModel(
                id=f"{text(target.get('resource_id'), '')}:check:{index}",
                cells={
                    "requirement": text(check.get("requirement")),
                    "target_type": text(check.get("target_type")),
                    "kind": text(check.get("kind")),
                    "status": status_label(status),
                    "setup": "Available" if bool_value(check.get("setup_available")) else "-",
                    "reason": text(check.get("reason")),
                },
                status=status_label(status),
                tone=tone_for_status(status),
            )
        )
    return OperationsTableSectionModel(
        id="checks",
        title="Checks",
        columns=(
            OperationsTableColumnModel("requirement", "Requirement"),
            OperationsTableColumnModel("target_type", "Target Type"),
            OperationsTableColumnModel("kind", "Kind"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("setup", "Setup"),
            OperationsTableColumnModel("reason", "Reason"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No checks.",
    )


def target_usages_table(target: dict[str, Any]) -> OperationsTableSectionModel:
    usages = target_metadata(target).get("usages")
    rows = [
        OperationsTableRowModel(
            id=f"{text(target.get('resource_id'), '')}:usage:{index}",
            cells={
                "consumer": text(dict_value(usage).get("display_name") or dict_value(usage).get("usage_id")),
                "usage_type": text(dict_value(usage).get("usage_type")),
                "usage_id": text(dict_value(usage).get("usage_id")),
                "enabled": "Yes" if bool_value(dict_value(usage).get("enabled")) else "No",
            },
            status="Enabled" if bool_value(dict_value(usage).get("enabled")) else "Disabled",
            tone="success" if bool_value(dict_value(usage).get("enabled")) else "neutral",
        )
        for index, usage in enumerate(usages if isinstance(usages, list | tuple) else [])
    ]
    return OperationsTableSectionModel(
        id="usages",
        title="Usages",
        columns=(
            OperationsTableColumnModel("consumer", "Consumer"),
            OperationsTableColumnModel("usage_type", "Usage Type"),
            OperationsTableColumnModel("usage_id", "Usage ID"),
            OperationsTableColumnModel("enabled", "Enabled"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No usages.",
    )


def target_setup_table(target: dict[str, Any]) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for index, record in enumerate(
        item
        for item in setup_flow_records((target,))
        if text(item["target"].get("resource_id"), "") == text(target.get("resource_id"), "")
    ):
        check = record["check"]
        flow = dict_value(check.get("setup_flow"))
        rows.append(
            OperationsTableRowModel(
                id=f"{text(target.get('resource_id'), '')}:setup:{index}",
                cells={
                    "flow": text(flow.get("kind")),
                    "title": text(flow.get("title")),
                    "action": text(flow.get("action_label") or "Setup"),
                    "path": text(flow.get("path")),
                    "description": short(flow.get("description"), 120),
                },
                status=text(check.get("status"), ""),
                tone=tone_for_status(check.get("status")),
            )
        )
    return OperationsTableSectionModel(
        id="setup",
        title="Setup",
        columns=(
            OperationsTableColumnModel("flow", "Flow Type"),
            OperationsTableColumnModel("title", "Title"),
            OperationsTableColumnModel("action", "Action"),
            OperationsTableColumnModel("path", "Path"),
            OperationsTableColumnModel("description", "Description"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No setup flow.",
    )
