"""Adapters that let Skills resolve runtime readiness without owning modules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.authorization.domain import (
    AuthorizationContext,
    AuthorizationRequest,
    AuthorizationResource,
    AuthorizationSubject,
)
from crxzipple.modules.skills.application.runtime_request_resolver import (
    SkillAccessRequirementReadiness,
    SkillAuthorizationReadiness,
    SkillRuntimeRequestResolutionContext,
)
from crxzipple.modules.skills.application.models import SkillPackage


@dataclass(slots=True)
class SkillAccessServiceAdapter:
    service: Any

    def check_requirements(
        self,
        requirements: tuple[str, ...],
        *,
        workspace_dir: str | None = None,
    ) -> tuple[SkillAccessRequirementReadiness, ...]:
        return tuple(
            _access_readiness_from_domain(readiness)
            for readiness in self.service.check_requirements(
                requirements,
                workspace_dir=workspace_dir,
            )
        )


@dataclass(slots=True)
class SkillAuthorizationServiceAdapter:
    service: Any

    def check_required_effects(
        self,
        *,
        skill: SkillPackage,
        effect_ids: tuple[str, ...],
        context: SkillRuntimeRequestResolutionContext,
    ) -> SkillAuthorizationReadiness:
        normalized_effect_ids = tuple(
            dict.fromkeys(
                effect_id.strip()
                for effect_id in effect_ids
                if isinstance(effect_id, str) and effect_id.strip()
            )
        )
        if not normalized_effect_ids:
            return SkillAuthorizationReadiness(ready=True, status="ready")
        if hasattr(self.service, "is_enabled") and not self.service.is_enabled():
            return SkillAuthorizationReadiness(
                ready=True,
                status="authorization_disabled",
            )

        missing_effects: list[str] = []
        matched_policy_ids: list[str] = []
        first_reason: str | None = None
        for effect_id in normalized_effect_ids:
            decision = self.service.check(
                AuthorizationRequest(
                    subject=AuthorizationSubject(
                        type="interface",
                        id=context.interface,
                        attrs=_subject_attrs(context),
                    ),
                    action="tool.effect.authorize",
                    resource=AuthorizationResource(
                        kind="tool",
                        id=f"skill:{skill.name}",
                        attrs={
                            "resource_owner": "skills",
                            "skill_name": skill.name,
                            "skill_source": skill.source,
                            "authorization_effect_ids": [effect_id],
                            "required_effect_ids": list(normalized_effect_ids),
                            "tags": list(skill.tags),
                        },
                    ),
                    context=AuthorizationContext(
                        attrs={
                            **context.attrs(),
                            "requested_effect_id": effect_id,
                        },
                    ),
                ),
            )
            matched_policy_ids.extend(decision.matched_policy_ids)
            if decision.allowed:
                continue
            missing_effects.append(effect_id)
            if first_reason is None:
                first_reason = decision.reason

        if missing_effects:
            return SkillAuthorizationReadiness(
                ready=False,
                status="setup_needed",
                missing_effects=tuple(missing_effects),
                reason=first_reason,
                matched_policy_ids=tuple(dict.fromkeys(matched_policy_ids)),
            )
        return SkillAuthorizationReadiness(
            ready=True,
            status="ready",
            matched_policy_ids=tuple(dict.fromkeys(matched_policy_ids)),
        )


@dataclass(slots=True)
class SkillToolSourceQueryAdapter:
    service: Any

    def list_available_tool_ids(self) -> tuple[str, ...]:
        active_sources = {
            str(source.source_id)
            for source in self.service.list_sources(status="active")
            if _status_value(getattr(source, "status", "")) == "active"
        }
        return tuple(
            function.function_id
            for function in self.service.list_functions(status="active")
            if function.enabled
            and _status_value(function.status) == "active"
            and function.source_id in active_sources
        )


def _access_readiness_from_domain(readiness: Any) -> SkillAccessRequirementReadiness:
    requirement = getattr(readiness, "requirement", None)
    raw_requirement = getattr(requirement, "raw", None)
    status = getattr(readiness, "status", None)
    status_value = getattr(status, "value", None) or str(status or "")
    return SkillAccessRequirementReadiness(
        requirement=str(raw_requirement or ""),
        ready=bool(getattr(readiness, "ready", False)),
        status=status_value or "unknown",
        reason=getattr(readiness, "reason", None),
        setup_available=bool(getattr(readiness, "setup_available", False)),
    )


def _status_value(status: Any) -> str:
    return str(getattr(status, "value", status) or "")


def _subject_attrs(context: SkillRuntimeRequestResolutionContext) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    if context.run_id:
        attrs["run_id"] = context.run_id
    if context.agent_id:
        attrs["agent_id"] = context.agent_id
    return attrs
