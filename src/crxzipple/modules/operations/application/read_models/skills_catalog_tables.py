from __future__ import annotations

from collections import defaultdict
from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsChartSectionModel,
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.skills_common import (
    joined,
    short,
    skill_id,
    skill_name,
    source,
    text,
)
from crxzipple.modules.operations.application.read_models.skills_models import (
    SkillRecord,
)
from crxzipple.modules.operations.application.read_models.skills_requirement_tables import (
    access_values,
)


def skills_table(
    records: tuple[SkillRecord, ...],
    *,
    total: int,
) -> OperationsTableSectionModel:
    rows = [
        OperationsTableRowModel(
            id=skill_id(record.package),
            cells={
                "skill": skill_name(record.package),
                "source": source(record.package),
                "status": record.status,
                "version": text(getattr(record.package, "version", None), "1"),
                "tags": joined(getattr(record.package, "tags", ())),
                "required_tools": joined(
                    getattr(
                        getattr(record.package, "requirements", None),
                        "required_tools",
                        (),
                    ),
                ),
                "access": str(
                    len(access_values(getattr(record.package, "requirements", None))),
                ),
                "resources": str(
                    len(tuple(getattr(record.package, "resources", ()) or ())),
                ),
                "path": short(text(getattr(record.package, "root_path", "")), 72),
                "action": "Open",
            },
            status=record.status,
            tone=record.tone,
        )
        for record in records
    ]
    return OperationsTableSectionModel(
        id="recently_resolved_skills",
        title="Installed Skills",
        columns=(
            OperationsTableColumnModel("skill", "Skill"),
            OperationsTableColumnModel("source", "Source"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("version", "Version"),
            OperationsTableColumnModel("tags", "Tags"),
            OperationsTableColumnModel("required_tools", "Required Tools"),
            OperationsTableColumnModel("access", "Access"),
            OperationsTableColumnModel("resources", "Resources"),
            OperationsTableColumnModel("path", "Path"),
            OperationsTableColumnModel("action", "Action"),
        ),
        rows=tuple(rows),
        total=total,
        empty_state="No skills available for this surface.",
    )


def sources_table(chart: OperationsChartSectionModel) -> OperationsTableSectionModel:
    rows = [
        OperationsTableRowModel(
            id=f"source:{segment.id}",
            cells={
                "source": segment.label,
                "skills": str(segment.value),
                "status": "Installed",
            },
            status="Installed",
            tone=segment.tone,
        )
        for segment in chart.segments
    ]
    return OperationsTableSectionModel(
        id="skill_sources",
        title="Skill Package Sources",
        columns=(
            OperationsTableColumnModel("source", "Source"),
            OperationsTableColumnModel("skills", "Skills"),
            OperationsTableColumnModel("status", "Status"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No skill package sources.",
    )


def conflicts_table(packages: tuple[Any, ...]) -> OperationsTableSectionModel:
    by_name: dict[str, list[Any]] = defaultdict(list)
    for package in packages:
        by_name[skill_name(package)].append(package)
    conflicts = tuple((name, items) for name, items in by_name.items() if len(items) > 1)
    rows = [
        OperationsTableRowModel(
            id=f"conflict:{name}",
            cells={
                "type": "Duplicate Skill",
                "details": ", ".join(source(item) for item in items),
                "winner": source(items[0]),
                "action": "Inspect",
            },
            status="Conflict",
            tone="warning",
        )
        for name, items in conflicts
    ]
    return OperationsTableSectionModel(
        id="conflicts_overrides",
        title="Conflicts / Overrides",
        columns=(
            OperationsTableColumnModel("type", "Type"),
            OperationsTableColumnModel("details", "Details"),
            OperationsTableColumnModel("winner", "Winner"),
            OperationsTableColumnModel("action", "Action"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No skill conflicts or overrides.",
    )
