from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.access_common import (
    kind_label,
    status_label,
    tone_for_status,
)
from crxzipple.modules.operations.application.read_models.access_target_projection import (
    impact,
    requirements_text,
    required_by,
    target_checks,
    target_label,
    target_metadata,
    target_reason,
    target_worst_status,
)
from crxzipple.modules.operations.application.read_models.access_values import (
    bool_value,
    int_value,
    string_values,
    text,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)


def access_targets_table(
    targets: tuple[dict[str, Any], ...],
    *,
    total: int,
) -> OperationsTableSectionModel:
    rows = [target_row(target) for target in targets]
    return OperationsTableSectionModel(
        id="access_targets",
        title="Access Targets",
        columns=(
            OperationsTableColumnModel("asset", "Asset"),
            OperationsTableColumnModel("kind", "Kind"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("requirements", "Requirements"),
            OperationsTableColumnModel("usage", "Usage"),
            OperationsTableColumnModel("setup", "Setup"),
            OperationsTableColumnModel("reason", "Reason"),
            OperationsTableColumnModel("action", "Action"),
        ),
        rows=tuple(rows),
        total=total,
        empty_state="No records.",
    )


def missing_access_table(
    targets: tuple[dict[str, Any], ...],
) -> OperationsTableSectionModel:
    rows = [target_row(target) for target in targets]
    return OperationsTableSectionModel(
        id="missing_access",
        title="Missing Access",
        columns=(
            OperationsTableColumnModel("asset", "Asset"),
            OperationsTableColumnModel("kind", "Kind"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("required_by", "Required By"),
            OperationsTableColumnModel("requirements", "Requirements"),
            OperationsTableColumnModel("setup", "Setup"),
            OperationsTableColumnModel("impact", "Impact"),
            OperationsTableColumnModel("action", "Action"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No missing access.",
    )


def provider_auth_blocked_table(
    targets: tuple[dict[str, Any], ...],
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for target in targets:
        metadata = target_metadata(target)
        usage_types = string_values(metadata.get("usage_types"))
        if usage_types and "llm_profile" not in usage_types and "tool" not in usage_types:
            continue
        rows.append(
            OperationsTableRowModel(
                id=text(target.get("resource_id"), ""),
                cells={
                    "asset": target_label(target),
                    "issue": target_reason(target),
                    "affected": str(int_value(metadata.get("usage_count"), 0)),
                    "action": "Setup" if bool_value(target.get("setup_available")) else "Open",
                },
                status=target_worst_status(target),
                tone=tone_for_status(target_worst_status(target)),
            )
        )
    return OperationsTableSectionModel(
        id="provider_auth_blocked",
        title="Provider Auth / Access Blocked",
        columns=(
            OperationsTableColumnModel("asset", "Asset"),
            OperationsTableColumnModel("issue", "Issue"),
            OperationsTableColumnModel("affected", "Affected"),
            OperationsTableColumnModel("action", "Action"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No provider access blockers.",
    )


def authentication_status_table(
    targets: tuple[dict[str, Any], ...],
    *,
    total: int,
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for target in targets:
        status = target_worst_status(target)
        rows.append(
            OperationsTableRowModel(
                id=text(target.get("resource_id"), ""),
                cells={
                    "asset": target_label(target),
                    "status": status_label(status),
                    "readiness": "Ready" if bool_value(target.get("ready")) else "Blocked",
                    "checks": str(len(target_checks(target))),
                    "usage": str(int_value(target_metadata(target).get("usage_count"), 0)),
                    "reason": target_reason(target),
                },
                status=status_label(status),
                tone=tone_for_status(status),
            )
        )
    return OperationsTableSectionModel(
        id="authentication_status",
        title="Authentication Status",
        columns=(
            OperationsTableColumnModel("asset", "Asset"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("readiness", "Readiness"),
            OperationsTableColumnModel("checks", "Checks"),
            OperationsTableColumnModel("usage", "Usage"),
            OperationsTableColumnModel("reason", "Reason"),
        ),
        rows=tuple(rows),
        total=total,
        empty_state="No records.",
    )


def target_row(target: dict[str, Any]) -> OperationsTableRowModel:
    status = target_worst_status(target)
    return OperationsTableRowModel(
        id=text(target.get("resource_id"), ""),
        cells={
            "asset": target_label(target),
            "kind": kind_label(text(target_metadata(target).get("asset_kind"))),
            "status": status_label(status),
            "readiness": "Ready" if bool_value(target.get("ready")) else "Blocked",
            "requirements": requirements_text(target),
            "required_by": required_by(target),
            "usage": text(target_metadata(target).get("usage_count")),
            "setup": "Available" if bool_value(target.get("setup_available")) else "-",
            "impact": impact(target),
            "reason": target_reason(target),
            "action": "Setup" if bool_value(target.get("setup_available")) else "Open",
        },
        status=status_label(status),
        tone=tone_for_status(status),
    )
