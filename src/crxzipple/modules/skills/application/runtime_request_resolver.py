from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from crxzipple.modules.skills.application.catalog import build_skill_runtime_request_catalog
from crxzipple.modules.skills.application.environment import unsupported_platforms
from crxzipple.modules.skills.application.models import SkillRuntimeRequestCatalog, SkillPackage
from crxzipple.modules.skills.application.surface import skill_surface_matches


SKILL_READINESS_READY = "ready"
SKILL_READINESS_SETUP_NEEDED = "setup_needed"
SKILL_READINESS_UNSUPPORTED = "unsupported"
_NO_READY_SKILLS_RUNTIME_REQUEST_TEXT = "\n".join(
    (
        "## Skills",
        "",
        "No optional skills are currently available for this run.",
        "Do not call skill_read unless a skill is listed as available.",
    ),
)


@dataclass(frozen=True, slots=True)
class SkillRuntimeRequestResolutionContext:
    workspace_dir: str | None = None
    surface: str | None = None
    interface: str | None = None
    agent_id: str | None = None
    run_id: str | None = None
    session_key: str | None = None
    active_session_id: str | None = None
    platform: str | None = None

    def attrs(self) -> dict[str, object]:
        attrs: dict[str, object] = {}
        for key, value in (
            ("workspace_dir", self.workspace_dir),
            ("surface", self.surface),
            ("interface", self.interface),
            ("agent_id", self.agent_id),
            ("run_id", self.run_id),
            ("session_key", self.session_key),
            ("active_session_id", self.active_session_id),
            ("platform", self.platform),
        ):
            if value is not None and str(value).strip():
                attrs[key] = str(value).strip()
        return attrs


@dataclass(frozen=True, slots=True)
class SkillAccessRequirementReadiness:
    requirement: str
    ready: bool
    status: str
    reason: str | None = None
    setup_available: bool = False

    def to_metadata(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "requirement": self.requirement,
            "ready": self.ready,
            "status": self.status,
            "setup_available": self.setup_available,
        }
        if self.reason:
            payload["reason"] = self.reason
        return payload


class SkillAccessReadinessPort(Protocol):
    def check_requirements(
        self,
        requirements: tuple[str, ...],
        *,
        workspace_dir: str | None = None,
    ) -> tuple[SkillAccessRequirementReadiness, ...]:
        ...


class SkillToolReadinessPort(Protocol):
    def list_available_tool_ids(self) -> tuple[str, ...]:
        ...


@dataclass(frozen=True, slots=True)
class SkillAuthorizationReadiness:
    ready: bool
    status: str
    missing_effects: tuple[str, ...] = ()
    reason: str | None = None
    matched_policy_ids: tuple[str, ...] = ()

    def to_metadata(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "ready": self.ready,
            "status": self.status,
            "missing_effects": list(self.missing_effects),
            "matched_policy_ids": list(self.matched_policy_ids),
        }
        if self.reason:
            payload["reason"] = self.reason
        return payload


class SkillAuthorizationReadinessPort(Protocol):
    def check_required_effects(
        self,
        *,
        skill: SkillPackage,
        effect_ids: tuple[str, ...],
        context: SkillRuntimeRequestResolutionContext,
    ) -> SkillAuthorizationReadiness:
        ...


@dataclass(frozen=True, slots=True)
class ResolvedSkillReadiness:
    status: str
    missing_tools: tuple[str, ...] = ()
    missing_access: tuple[str, ...] = ()
    missing_effects: tuple[str, ...] = ()
    unsupported_surfaces: tuple[str, ...] = ()
    unsupported_platforms: tuple[str, ...] = ()
    access_checks: tuple[SkillAccessRequirementReadiness, ...] = ()
    authorization: SkillAuthorizationReadiness | None = None

    @property
    def ready(self) -> bool:
        return self.status == SKILL_READINESS_READY

    def to_metadata(self) -> dict[str, object]:
        return {
            "status": self.status,
            "missing_tools": list(self.missing_tools),
            "missing_access": list(self.missing_access),
            "missing_effects": list(self.missing_effects),
            "unsupported_surfaces": list(self.unsupported_surfaces),
            "unsupported_platforms": list(self.unsupported_platforms),
            "access_checks": [
                check.to_metadata()
                for check in self.access_checks
            ],
            "authorization": (
                self.authorization.to_metadata()
                if self.authorization is not None
                else None
            ),
        }


@dataclass(frozen=True, slots=True)
class ResolvedSkill:
    package: SkillPackage
    readiness: ResolvedSkillReadiness

    @property
    def ready(self) -> bool:
        return self.readiness.ready


@dataclass(frozen=True, slots=True)
class SkillRuntimeRequestResolution:
    skills: tuple[ResolvedSkill, ...]

    @property
    def ready_skills(self) -> tuple[SkillPackage, ...]:
        return tuple(skill.package for skill in self.skills if skill.ready)

    @property
    def runtime_request_catalog(self) -> SkillRuntimeRequestCatalog | None:
        catalog = build_skill_runtime_request_catalog(self.ready_skills)
        if catalog is None:
            if not self.skills:
                return None
            return SkillRuntimeRequestCatalog(
                content=_NO_READY_SKILLS_RUNTIME_REQUEST_TEXT,
                metadata={
                    "count": 0,
                    "skills": [],
                    "available_skill_names": [],
                    "resolved_skills": self._resolved_skills_metadata(),
                },
            )
        readiness_by_name = self._readiness_by_name()
        metadata = dict(catalog.metadata)
        metadata["available_skill_names"] = [skill.name for skill in self.ready_skills]
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
        return SkillRuntimeRequestCatalog(content=catalog.content, metadata=metadata)

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
class SkillRuntimeRequestResolver:
    access_port: SkillAccessReadinessPort | None = None
    authorization_port: SkillAuthorizationReadinessPort | None = None

    def resolve(
        self,
        packages: tuple[SkillPackage, ...],
        *,
        available_tool_ids: tuple[str, ...],
        context: SkillRuntimeRequestResolutionContext | None = None,
    ) -> SkillRuntimeRequestResolution:
        resolved_context = context or SkillRuntimeRequestResolutionContext()
        normalized_tool_ids = frozenset(
            tool_id.strip()
            for tool_id in available_tool_ids
            if isinstance(tool_id, str) and tool_id.strip()
        )
        return SkillRuntimeRequestResolution(
            skills=tuple(
                ResolvedSkill(
                    package=package,
                    readiness=self._resolve_readiness(
                        package,
                        available_tool_ids=normalized_tool_ids,
                        context=resolved_context,
                    ),
                )
                for package in packages
            ),
        )

    def _resolve_readiness(
        self,
        package: SkillPackage,
        *,
        available_tool_ids: frozenset[str],
        context: SkillRuntimeRequestResolutionContext,
    ) -> ResolvedSkillReadiness:
        missing_tools = tuple(
            tool_id
            for tool_id in package.requirements.required_tools
            if tool_id not in available_tool_ids
        )
        unsupported_surfaces = _unsupported_surfaces(package, context.surface)
        unsupported_platform_values = unsupported_platforms(
            package.requirements.supported_platforms,
            active_platform=context.platform,
        )
        access_checks = self._access_checks(package, context=context)
        missing_access = tuple(
            check.requirement
            for check in access_checks
            if not check.ready
        )
        authorization = self._authorization_readiness(package, context=context)
        missing_effects = (
            authorization.missing_effects
            if authorization is not None
            else ()
        )
        if (
            missing_tools
            or unsupported_surfaces
            or unsupported_platform_values
            or missing_access
            or missing_effects
        ):
            status = (
                SKILL_READINESS_UNSUPPORTED
                if unsupported_platform_values
                else SKILL_READINESS_SETUP_NEEDED
            )
        else:
            status = SKILL_READINESS_READY
        return ResolvedSkillReadiness(
            status=status,
            missing_tools=missing_tools,
            missing_access=missing_access,
            missing_effects=missing_effects,
            unsupported_surfaces=unsupported_surfaces,
            unsupported_platforms=unsupported_platform_values,
            access_checks=access_checks,
            authorization=authorization,
        )

    def _access_checks(
        self,
        package: SkillPackage,
        *,
        context: SkillRuntimeRequestResolutionContext,
    ) -> tuple[SkillAccessRequirementReadiness, ...]:
        requirements = _access_requirements(package)
        if not requirements:
            return ()
        if self.access_port is None:
            return tuple(
                SkillAccessRequirementReadiness(
                    requirement=requirement,
                    ready=False,
                    status=SKILL_READINESS_SETUP_NEEDED,
                    reason="access readiness service is not available",
                )
                for requirement in requirements
            )
        return self.access_port.check_requirements(
            requirements,
            workspace_dir=context.workspace_dir,
        )

    def _authorization_readiness(
        self,
        package: SkillPackage,
        *,
        context: SkillRuntimeRequestResolutionContext,
    ) -> SkillAuthorizationReadiness | None:
        effect_ids = _normalize_values(package.requirements.required_effects)
        if not effect_ids:
            return None
        if self.authorization_port is None:
            return SkillAuthorizationReadiness(
                ready=False,
                status=SKILL_READINESS_SETUP_NEEDED,
                missing_effects=effect_ids,
                reason="authorization service is not available",
            )
        return self.authorization_port.check_required_effects(
            skill=package,
            effect_ids=effect_ids,
            context=context,
        )


def _unsupported_surfaces(
    package: SkillPackage,
    surface: str | None,
) -> tuple[str, ...]:
    supported = _normalize_values(package.requirements.surfaces)
    if skill_surface_matches(supported, surface):
        return ()
    normalized_surface = surface.strip() if surface is not None else ""
    return (normalized_surface,)


def _access_requirements(package: SkillPackage) -> tuple[str, ...]:
    return _normalize_values(package.requirements.required_access)


def _normalize_values(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            value.strip()
            for value in values
            if isinstance(value, str) and value.strip()
        )
    )
