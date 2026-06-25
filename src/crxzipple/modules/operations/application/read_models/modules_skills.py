from __future__ import annotations

from collections import Counter
import json
from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsModuleOverview,
    RuntimeActionModel,
)
from crxzipple.modules.operations.application.read_models.modules_helpers import (
    health_metric,
    now,
    overview,
    s,
)
from crxzipple.shared.time import format_datetime_utc


def skills_operations_overview(query: Any) -> OperationsModuleOverview:
    current_time = now()
    skills = query.skill_manager.list_available(
        workspace_dir=None, surface="interactive"
    )
    source_counts = Counter(skill.source for skill in skills)
    requirement_rows = _skill_requirement_rows(skills)
    health = "healthy"
    return overview(
        module="skills",
        title="Skills",
        subtitle="聚合技能包目录、来源、声明能力与访问要求。",
        health=health,
        updated_at=format_datetime_utc(current_time),
        metrics=(
            health_metric(health, "Loaded from skills registry"),
            MetricCardModel(
                "installed_skills",
                "Installed Skills",
                str(len(skills)),
                f"{len(source_counts)} sources",
                "info",
            ),
            MetricCardModel(
                "available_skills",
                "Available Skills",
                str(len(skills)),
                "interactive surface",
                "neutral",
            ),
            MetricCardModel(
                "declared_requirements",
                "Declared Requirements",
                str(len(requirement_rows)),
                "tools/auth/credentials",
                "info" if requirement_rows else "success",
            ),
            MetricCardModel(
                "resolution_success_rate",
                "Resolution Success Rate",
                "N/A",
                "resolution metric not exposed",
                "neutral",
            ),
            MetricCardModel(
                "resolution_failures",
                "Resolution Failures",
                "N/A",
                "resolution metric not exposed",
                "neutral",
            ),
        ),
        queue=tuple(_skill_row(skill) for skill in skills),
        lane_locks=tuple(
            {
                "source": s(source),
                "skills": str(count),
                "status": "Installed",
            }
            for source, count in sorted(source_counts.items())
        ),
        executor=tuple(requirement_rows),
        actions=(
            RuntimeActionModel(id="open_skill", label="Open Skill", owner="skills"),
            RuntimeActionModel(
                id="validate_skill",
                label="Validate Skill",
                owner="skills",
                risk="controlled",
            ),
        ),
    )


def _skill_row(skill: Any) -> dict[str, str]:
    requirements = getattr(skill, "requirements", None)
    requirement_payload = {
        "required_tools": list(getattr(requirements, "required_tools", ())),
        "optional_tools": list(getattr(requirements, "optional_tools", ())),
        "suggested_tools": list(getattr(requirements, "suggested_tools", ())),
        "required_access": list(getattr(requirements, "required_access", ())),
    }
    return {
        "name": s(getattr(skill, "name", None)),
        "skill": s(getattr(skill, "name", None)),
        "description": s(getattr(skill, "description", None)),
        "version": s(getattr(skill, "version", None), "1"),
        "tags": s(getattr(skill, "tags", ())),
        "source": s(getattr(skill, "source", None)),
        "root_path": s(getattr(skill, "root_path", None)),
        "result": "Installed",
        "requirements": json.dumps(requirement_payload, ensure_ascii=False),
    }


def _skill_requirement_rows(skills: list[Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for skill in skills:
        requirements = getattr(skill, "requirements", None)
        for field, capability_type in (
            ("required_tools", "Tool"),
            ("required_access", "Access"),
        ):
            for value in getattr(requirements, field, ()):
                rows.append(
                    {
                        "type": capability_type,
                        "capability": s(value),
                        "required": s(value),
                        "by": s(getattr(skill, "name", None)),
                        "resolved": s(value),
                        "status": "Declared",
                    }
                )
    return rows
