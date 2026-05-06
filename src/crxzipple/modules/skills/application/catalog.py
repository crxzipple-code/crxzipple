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
        "Skill requirements describe applicability, not permission grants.",
        "Use skill_read to read SKILL.md or another file inside a skill package when that guidance would genuinely help.",
        "You may read multiple skills or referenced files before deciding what to do.",
        "Do not read every skill by default. Prefer the smallest useful set.",
        "",
        "<available_skills>",
    ]
    for skill in available_skills:
        details: list[str] = [f"location: {skill.root_path}"]
        if skill.manifest.when_to_use:
            details.append(f"use when: {skill.manifest.when_to_use}")
        if skill.required_tools:
            details.append(f"requires tools: {', '.join(skill.required_tools)}")
        if skill.suggested_tools:
            details.append(f"suggested tools: {', '.join(skill.suggested_tools)}")
        requirements = skill.requirements
        if requirements.required_effects:
            details.append(
                f"requires effects: {', '.join(requirements.required_effects)}",
            )
        if skill.resources:
            details.append(
                "resources: "
                + ", ".join(resource.path for resource in skill.resources[:5]),
            )
        lines.append(
            f"- {skill.name}: {skill.description} ({'; '.join(details)})",
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
                    "requirements": skill.requirements.to_payload(),
                    "path": skill.root_path,
                    "manifest_path": skill.manifest_path,
                    "instructions_path": skill.instructions_path,
                    "source": skill.source,
                    "resources": [
                        {
                            "path": resource.path,
                            "kind": resource.kind,
                            "size_bytes": resource.size_bytes,
                        }
                        for resource in skill.resources
                    ],
                }
                for skill in available_skills
            ],
        },
    )
