from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.orchestration.application.tool_resolver import ResolvedToolSet
from crxzipple.modules.skills.application import (
    SkillCatalogPrompt,
    SkillPackage,
    build_skill_catalog_prompt,
)


SKILL_READINESS_READY = "ready"
SKILL_READINESS_SETUP_NEEDED = "setup_needed"
_NO_READY_SKILLS_PROMPT = "\n".join(
    (
        "# Available Skills",
        "",
        "No optional skills are currently available for this run.",
        "Do not call skill_read unless a skill is listed as available.",
    ),
)


@dataclass(frozen=True, slots=True)
class ResolvedSkillReadiness:
    status: str
    missing_tools: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return self.status == SKILL_READINESS_READY

    def to_metadata(self) -> dict[str, object]:
        return {
            "status": self.status,
            "missing_tools": list(self.missing_tools),
        }


@dataclass(frozen=True, slots=True)
class ResolvedSkill:
    package: SkillPackage
    readiness: ResolvedSkillReadiness

    @property
    def ready(self) -> bool:
        return self.readiness.ready


@dataclass(frozen=True, slots=True)
class ResolvedSkillCatalog:
    skills: tuple[ResolvedSkill, ...]

    @property
    def ready_skills(self) -> tuple[SkillPackage, ...]:
        return tuple(skill.package for skill in self.skills if skill.ready)

    def build_prompt_catalog(self) -> SkillCatalogPrompt | None:
        prompt = build_skill_catalog_prompt(self.ready_skills)
        if prompt is None:
            if not self.skills:
                return None
            return SkillCatalogPrompt(
                content=_NO_READY_SKILLS_PROMPT,
                metadata={
                    "count": 0,
                    "skills": [],
                    "resolved_skills": self._resolved_skills_metadata(),
                },
            )
        readiness_by_name = self._readiness_by_name()
        metadata = dict(prompt.metadata)
        metadata["resolved_skills"] = self._resolved_skills_metadata()
        metadata["skills"] = [
            {
                **item,
                "readiness": readiness_by_name.get(
                    str(item.get("name", "")),
                    {"status": SKILL_READINESS_READY},
                ),
            }
            for item in metadata.get("skills", [])
            if isinstance(item, dict)
        ]
        return SkillCatalogPrompt(content=prompt.content, metadata=metadata)

    def _readiness_by_name(self) -> dict[str, dict[str, object]]:
        return {
            skill.package.name: skill.readiness.to_metadata()
            for skill in self.skills
        }

    def _resolved_skills_metadata(self) -> list[dict[str, object]]:
        return [
            {
                "name": skill.package.name,
                "readiness": skill.readiness.to_metadata(),
            }
            for skill in self.skills
        ]


@dataclass(slots=True)
class ResolveSkill:
    def resolve(
        self,
        packages: tuple[SkillPackage, ...],
        *,
        resolved_tools: ResolvedToolSet | None,
        workspace_dir: str | None,
    ) -> ResolvedSkillCatalog:
        available_tool_ids = (
            tuple(item.tool.id for item in resolved_tools.tools)
            if resolved_tools is not None
            else ()
        )
        return ResolvedSkillCatalog(
            skills=tuple(
                ResolvedSkill(
                    package=package,
                    readiness=self._resolve_readiness(
                        package,
                        available_tool_ids=available_tool_ids,
                    ),
                )
                for package in packages
            ),
        )

    def _resolve_readiness(
        self,
        package: SkillPackage,
        *,
        available_tool_ids: tuple[str, ...],
    ) -> ResolvedSkillReadiness:
        missing_tools = tuple(
            tool_id
            for tool_id in package.requirements.required_tools
            if tool_id not in available_tool_ids
        )
        if missing_tools:
            status = SKILL_READINESS_SETUP_NEEDED
        else:
            status = SKILL_READINESS_READY
        return ResolvedSkillReadiness(
            status=status,
            missing_tools=missing_tools,
        )
