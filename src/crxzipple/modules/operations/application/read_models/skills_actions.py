from __future__ import annotations

from crxzipple.modules.operations.application.read_models.models import (
    RuntimeActionModel,
)


def actions(surface: str) -> tuple[RuntimeActionModel, ...]:
    return (
        RuntimeActionModel(
            id="list_skills",
            label="List Skills",
            owner="skills",
            kind="navigation",
            method="GET",
            endpoint=f"/operations/skills?surface={surface}",
        ),
        RuntimeActionModel(
            id="validate_skill",
            label="Validate Skill",
            owner="skills",
            risk="controlled",
            audit_event="skills.package.validate",
            method="POST",
            endpoint="/operations/skills/validate",
        ),
    )


def import_actions() -> tuple[RuntimeActionModel, ...]:
    return (
        RuntimeActionModel(
            id="validate_skill_package",
            label="Validate Package",
            owner="skills",
            risk="controlled",
            audit_event="skills.package.validate",
            method="POST",
            endpoint="/operations/skills/validate",
        ),
        RuntimeActionModel(
            id="sync_skill_catalog",
            label="Sync Skill Catalog",
            owner="skills",
            risk="controlled",
            audit_event="skills.source.sync",
            method="POST",
            endpoint="/operations/skills/sync",
        ),
        RuntimeActionModel(
            id="install_global_skill",
            label="Install Global Skill",
            owner="skills",
            risk="controlled",
            requires_confirmation=True,
            audit_event="skills.global.install",
            method="POST",
            endpoint="/operations/skills/install",
        ),
    )
