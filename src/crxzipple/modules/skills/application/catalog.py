from __future__ import annotations

from crxzipple.modules.skills.application.models import (
    SkillCatalogPrompt,
    SkillPackage,
)


def build_skill_catalog_prompt(
    available_skills: tuple[SkillPackage, ...],
) -> SkillCatalogPrompt | None:
    if not available_skills:
        return None
    lines = [
        "# Available Skills",
        "",
        "The following optional skills are available for this run.",
        "Use a skill only when it clearly matches the current task.",
        "Use skill_read to read SKILL.md or another file inside a skill package when that guidance would genuinely help.",
        "You may read multiple skills or referenced files before deciding what to do.",
        "Do not read every skill by default. Prefer the smallest useful set.",
        "",
        "<available_skills>",
    ]
    for skill in available_skills:
        lines.append(
            f"- {skill.name}: {skill.description} (location: {skill.root_path})",
        )
    lines.append("</available_skills>")
    return SkillCatalogPrompt(
        content="\n".join(lines).strip(),
        metadata={
            "count": len(available_skills),
            "skills": [
                {
                    "name": skill.name,
                    "version": skill.version,
                    "tags": list(skill.tags),
                    "allowed_tools": list(skill.allowed_tools),
                    "path": skill.root_path,
                    "manifest_path": skill.manifest_path,
                    "instructions_path": skill.instructions_path,
                    "source": skill.source,
                }
                for skill in available_skills
            ],
        },
    )
