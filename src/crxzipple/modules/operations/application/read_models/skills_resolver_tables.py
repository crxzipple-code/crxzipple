from __future__ import annotations

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.skills_common import (
    items,
    joined,
    skill_id,
    skill_name,
)
from crxzipple.modules.operations.application.read_models.skills_models import (
    SkillRecord,
)


def resolver_detail_table(
    records: tuple[SkillRecord, ...],
    tool_ids: set[str],
) -> OperationsTableSectionModel:
    rows = [
        OperationsTableRowModel(
            id=f"resolver:{skill_id(record.package)}",
            cells={
                "skill": skill_name(record.package),
                "input": joined(
                    getattr(
                        getattr(record.package, "requirements", None),
                        "required_tools",
                        (),
                    ),
                ),
                "available": str(
                    sum(
                        1
                        for tool in items(
                            getattr(
                                getattr(record.package, "requirements", None),
                                "required_tools",
                                (),
                            ),
                        )
                        if tool in tool_ids
                    ),
                ),
                "missing": joined(
                    (
                        *record.missing_tools,
                        *record.missing_access,
                        *record.missing_effects,
                        *record.unsupported_platforms,
                    ),
                ),
                "result": record.status,
                "next_step": resolver_next_step(record),
            },
            status=record.status,
            tone=record.tone,
        )
        for record in records
    ]
    return OperationsTableSectionModel(
        id="resolver_detail",
        title="Resolver Detail",
        columns=(
            OperationsTableColumnModel("skill", "Skill"),
            OperationsTableColumnModel("input", "Required Tools"),
            OperationsTableColumnModel("available", "Available"),
            OperationsTableColumnModel("missing", "Missing"),
            OperationsTableColumnModel("result", "Result"),
            OperationsTableColumnModel("next_step", "Next Step"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No resolver detail.",
    )


def resolver_next_step(record: SkillRecord) -> str:
    if record.missing_tools:
        return "Register or enable missing tools"
    if record.missing_access:
        return "Complete Access setup"
    if record.missing_effects:
        return "Grant required authorization effects"
    if record.unsupported_surfaces:
        return "Switch surface or update skill manifest"
    if record.unsupported_platforms:
        return "Switch runtime platform or update manifest"
    return "-"
