from __future__ import annotations

from crxzipple.modules.skills.application.authoring_conversions import draft_package
from crxzipple.modules.skills.application.environment import unsupported_platforms
from crxzipple.modules.skills.application.models import SkillDraft
from crxzipple.modules.skills.application.runtime_request_resolver import (
    ResolvedSkillReadiness,
    SkillRuntimeRequestResolutionContext,
    SkillRuntimeRequestResolver,
    SkillToolReadinessPort,
)


def draft_requirement_readiness(
    draft: SkillDraft,
    *,
    runtime_request_resolver: SkillRuntimeRequestResolver,
    tool_readiness_port: SkillToolReadinessPort | None,
) -> ResolvedSkillReadiness:
    if tool_readiness_port is None:
        return static_draft_requirement_readiness(draft)
    resolution = runtime_request_resolver.resolve(
        (draft_package(draft),),
        available_tool_ids=tool_readiness_port.list_available_tool_ids(),
        context=SkillRuntimeRequestResolutionContext(
            workspace_dir=draft.workspace_dir,
        ),
    )
    return resolution.skills[0].readiness


def static_draft_requirement_readiness(draft: SkillDraft) -> ResolvedSkillReadiness:
    unsupported_platform_values = unsupported_platforms(
        draft.requirements.supported_platforms,
    )
    missing_tools = draft.requirements.required_tools
    missing_access = draft.requirements.required_access
    missing_effects = draft.requirements.required_effects
    if unsupported_platform_values:
        status = "unsupported"
    elif missing_tools or missing_access or missing_effects:
        status = "setup_needed"
    else:
        status = "ready"
    return ResolvedSkillReadiness(
        status=status,
        missing_tools=missing_tools,
        missing_access=missing_access,
        missing_effects=missing_effects,
        unsupported_platforms=unsupported_platform_values,
    )
