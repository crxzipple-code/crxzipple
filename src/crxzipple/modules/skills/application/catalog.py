from __future__ import annotations

from crxzipple.modules.skills.application.models import (
    SkillRuntimeRequestCatalog,
    SkillPackage,
)


def build_skill_runtime_request_catalog(
    available_skills: tuple[SkillPackage, ...],
) -> SkillRuntimeRequestCatalog | None:
    if not available_skills:
        return None
    lines = [
        "## Skills",
        "",
        "A skill is a local instruction package that can extend the agent with task-specific workflows, tool integrations, or domain guidance.",
        "",
        "### Available Skills",
        "",
        "The following skills are available for this run. Each entry includes its name, description, and source path.",
        "If the user names a skill, or the task clearly matches a skill description, read that skill's SKILL.md with skill_read before acting.",
        "When SKILL.md references relative files, use skill_read to read only the referenced files needed for the task.",
        "Do not read every skill by default. Prefer the smallest useful set, and continue with normal tools when no skill applies.",
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
    lines.extend(
        (
            "",
            "### How to use skills",
            "",
            "- Use skill_read with path `SKILL.md` for the chosen skill before following its workflow.",
            "- If multiple skills apply, read the minimal set that covers the task and follow them in a sensible order.",
            "- If a required skill tool is unavailable or blocked, say what is missing and use the next best available route.",
        ),
    )
    return SkillRuntimeRequestCatalog(
        content="\n".join(lines).strip(),
        metadata={
            "count": len(available_skills),
            "available_skill_names": [skill.name for skill in available_skills],
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
