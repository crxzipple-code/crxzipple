from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.skills_common import (
    items,
    short,
    skill_id,
    skill_name,
    status_label,
    text,
)
from crxzipple.modules.operations.application.read_models.skills_models import (
    SkillRecord,
)


def access_values(requirements: Any | None) -> tuple[str, ...]:
    return tuple(dict.fromkeys(items(getattr(requirements, "required_access", ()))))


def access_requirements_table(
    records: tuple[SkillRecord, ...],
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for record in records:
        seen_requirements: set[str] = set()
        for check in record.access_checks:
            requirement = text(getattr(getattr(check, "requirement", None), "raw", ""))
            seen_requirements.add(requirement)
            status = (
                "Ready"
                if bool(getattr(check, "ready", False))
                else status_label(getattr(check, "status", "setup_needed"))
            )
            rows.append(
                OperationsTableRowModel(
                    id=f"access:{skill_id(record.package)}:{requirement}",
                    cells={
                        "asset": requirement,
                        "skill": skill_name(record.package),
                        "purpose": status_label(
                            getattr(getattr(check, "requirement", None), "kind", "access"),
                        ),
                        "status": status,
                        "reason": short(getattr(check, "reason", ""), 96),
                        "setup": "Available"
                        if bool(getattr(check, "setup_available", False))
                        else "-",
                    },
                    status=status,
                    tone="success" if bool(getattr(check, "ready", False)) else "warning",
                ),
            )
        for requirement in record.missing_access:
            if requirement in seen_requirements:
                continue
            rows.append(
                OperationsTableRowModel(
                    id=f"access:{skill_id(record.package)}:{requirement}",
                    cells={
                        "asset": requirement,
                        "skill": skill_name(record.package),
                        "purpose": "Access",
                        "status": "Setup Needed",
                        "reason": "reported by skills readiness",
                        "setup": "-",
                    },
                    status="Setup Needed",
                    tone="warning",
                ),
            )
    return OperationsTableSectionModel(
        id="access_requirements",
        title="Access Requirements",
        columns=(
            OperationsTableColumnModel("asset", "Access Asset"),
            OperationsTableColumnModel("skill", "Required By"),
            OperationsTableColumnModel("purpose", "Purpose"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("reason", "Reason"),
            OperationsTableColumnModel("setup", "Setup"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No access requirements declared by skills.",
    )


def capability_requirements_table(
    records: tuple[SkillRecord, ...],
    tool_ids: set[str],
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for record in records:
        requirements = getattr(record.package, "requirements", None)
        for field, requirement_type in (
            ("required_tools", "Required Tool"),
            ("suggested_tools", "Suggested Tool"),
            ("optional_tools", "Optional Tool"),
            ("required_effects", "Required Effect"),
            ("supported_platforms", "Supported Platform"),
        ):
            for value in items(getattr(requirements, field, ())):
                if field == "required_tools":
                    ready = value in tool_ids and value not in record.missing_tools
                elif field == "required_effects":
                    ready = value not in record.missing_effects
                elif field == "supported_platforms":
                    ready = not record.unsupported_platforms
                else:
                    ready = True
                status = "Ready" if ready else "Unsupported"
                rows.append(
                    OperationsTableRowModel(
                        id=f"capability:{skill_id(record.package)}:{field}:{value}",
                        cells={
                            "capability": value,
                            "type": requirement_type,
                            "by": skill_name(record.package),
                            "resolved": value if ready else "-",
                            "status": status,
                        },
                        status=status,
                        tone="success" if ready else "warning",
                    ),
                )
    return OperationsTableSectionModel(
        id="capability_requirements",
        title="Capability Requirements",
        columns=(
            OperationsTableColumnModel("capability", "Capability"),
            OperationsTableColumnModel("type", "Type"),
            OperationsTableColumnModel("by", "Required By"),
            OperationsTableColumnModel("resolved", "Resolved To"),
            OperationsTableColumnModel("status", "Status"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No capability requirements declared by skills.",
    )

