from __future__ import annotations

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.skills_common import (
    skill_id,
    skill_name,
    status_label,
    text,
)
from crxzipple.modules.operations.application.read_models.skills_models import (
    SkillRecord,
)


def missing_capabilities_table(
    records: tuple[SkillRecord, ...],
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for record in records:
        rows.extend(_missing_tool_rows(record))
        rows.extend(_missing_access_check_rows(record))
        rows.extend(_missing_access_rows(record))
        rows.extend(_missing_effect_rows(record))
        rows.extend(_unsupported_surface_rows(record))
        rows.extend(_unsupported_platform_rows(record))
    return OperationsTableSectionModel(
        id="missing_capabilities",
        title="Missing Capabilities",
        columns=(
            OperationsTableColumnModel("type", "Capability Type"),
            OperationsTableColumnModel("required", "Required Item"),
            OperationsTableColumnModel("by", "Required By"),
            OperationsTableColumnModel("impact", "Impact"),
            OperationsTableColumnModel("resolved_by", "Resolved By"),
            OperationsTableColumnModel("status", "Status"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No missing skill capabilities.",
    )


def _missing_tool_rows(record: SkillRecord) -> tuple[OperationsTableRowModel, ...]:
    return tuple(
        OperationsTableRowModel(
            id=f"missing-tool:{skill_id(record.package)}:{tool_id}",
            cells={
                "type": "Tool",
                "required": tool_id,
                "by": skill_name(record.package),
                "impact": "Required",
                "resolved_by": "Register or enable tool",
                "status": "Setup Needed",
            },
            status="Setup Needed",
            tone="warning",
        )
        for tool_id in record.missing_tools
    )


def _missing_access_check_rows(
    record: SkillRecord,
) -> tuple[OperationsTableRowModel, ...]:
    rows: list[OperationsTableRowModel] = []
    for check in record.access_checks:
        if bool(getattr(check, "ready", False)):
            continue
        requirement = text(getattr(getattr(check, "requirement", None), "raw", ""))
        if requirement in record.missing_access:
            continue
        status = status_label(getattr(check, "status", "setup_needed"))
        rows.append(
            OperationsTableRowModel(
                id=f"missing-access:{skill_id(record.package)}:{requirement}",
                cells={
                    "type": "Access",
                    "required": requirement,
                    "by": skill_name(record.package),
                    "impact": "Required",
                    "resolved_by": "Access setup",
                    "status": status,
                },
                status=status,
                tone="warning",
            ),
        )
    return tuple(rows)


def _missing_access_rows(record: SkillRecord) -> tuple[OperationsTableRowModel, ...]:
    return tuple(
        OperationsTableRowModel(
            id=f"missing-access:{skill_id(record.package)}:{requirement}",
            cells={
                "type": "Access",
                "required": requirement,
                "by": skill_name(record.package),
                "impact": "Required",
                "resolved_by": "Access setup",
                "status": "Setup Needed",
            },
            status="Setup Needed",
            tone="warning",
        )
        for requirement in record.missing_access
    )


def _missing_effect_rows(record: SkillRecord) -> tuple[OperationsTableRowModel, ...]:
    return tuple(
        OperationsTableRowModel(
            id=f"missing-effect:{skill_id(record.package)}:{effect_id}",
            cells={
                "type": "Authorization Effect",
                "required": effect_id,
                "by": skill_name(record.package),
                "impact": "Required",
                "resolved_by": "Grant effect authorization",
                "status": "Setup Needed",
            },
            status="Setup Needed",
            tone="warning",
        )
        for effect_id in record.missing_effects
    )


def _unsupported_surface_rows(
    record: SkillRecord,
) -> tuple[OperationsTableRowModel, ...]:
    return tuple(
        OperationsTableRowModel(
            id=f"unsupported-surface:{skill_id(record.package)}:{surface_value}",
            cells={
                "type": "Surface",
                "required": surface_value,
                "by": skill_name(record.package),
                "impact": "Not available on this surface",
                "resolved_by": "Switch surface or update manifest",
                "status": "Unsupported",
            },
            status="Unsupported",
            tone="warning",
        )
        for surface_value in record.unsupported_surfaces
    )


def _unsupported_platform_rows(
    record: SkillRecord,
) -> tuple[OperationsTableRowModel, ...]:
    return tuple(
        OperationsTableRowModel(
            id=f"unsupported-platform:{skill_id(record.package)}:{platform}",
            cells={
                "type": "Platform",
                "required": platform,
                "by": skill_name(record.package),
                "impact": "Not available on this runtime platform",
                "resolved_by": "Switch runtime platform or update manifest",
                "status": "Unsupported",
            },
            status="Unsupported",
            tone="warning",
        )
        for platform in record.unsupported_platforms
    )
