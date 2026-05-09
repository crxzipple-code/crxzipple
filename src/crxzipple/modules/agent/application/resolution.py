from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Any, Protocol


class AgentProfileQueryPort(Protocol):
    def get_profile(self, profile_id: str) -> Any: ...


class LlmProfileQueryPort(Protocol):
    def list_profiles(self) -> list[Any]: ...


class ToolCatalogQueryPort(Protocol):
    def list_tools(self) -> list[Any]: ...


class SkillCatalogQueryPort(Protocol):
    def list_available(
        self,
        *,
        workspace_dir: str | None = None,
        surface: str = "interactive",
    ) -> list[Any]: ...


class AccessReadinessQueryPort(Protocol):
    def check_requirement(
        self,
        requirement: str,
        *,
        workspace_dir: str | None = None,
    ) -> Any: ...

    def check_credential_binding(
        self,
        binding: str,
        *,
        workspace_dir: str | None = None,
        allow_literal: bool = False,
    ) -> Any: ...


class AuthorizationPolicyQueryPort(Protocol):
    def list_policies(self) -> list[Any]: ...


@dataclass(frozen=True, slots=True)
class AgentResolvedLlm:
    slot: str
    llm_id: str
    resolved: bool
    enabled: bool
    provider: str | None = None
    model_name: str | None = None
    capabilities: tuple[str, ...] = ()
    context_window_tokens: int | None = None
    credential_binding: str | None = None


@dataclass(frozen=True, slots=True)
class AgentResolvedTool:
    tool_id: str
    resolved: bool
    enabled: bool
    name: str | None = None
    kind: str | None = None
    source_kind: str | None = None
    access_requirements: tuple[str, ...] = ()
    access_requirement_sets: tuple[tuple[str, ...], ...] = ()
    required_effect_ids: tuple[str, ...] = ()
    requires_confirmation: bool = False
    mutates_state: bool = False


@dataclass(frozen=True, slots=True)
class AgentResolvedSkill:
    skill_id: str
    resolved: bool
    name: str | None = None
    source: str | None = None
    required_tools: tuple[str, ...] = ()
    optional_tools: tuple[str, ...] = ()
    suggested_tools: tuple[str, ...] = ()
    required_effects: tuple[str, ...] = ()
    access_requirements: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AgentAccessGrant:
    source_type: str
    source_id: str
    requirement: str
    grant_kind: str
    status: str = "unknown"
    ready: bool = False
    setup_available: bool = False
    reason: str | None = None
    _raw_requirement: str = field(default="", repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class AgentAuthorizationGrant:
    policy_id: str
    effect: str
    action: str
    status: str
    effect_ids: tuple[str, ...] = ()
    tool_ids: tuple[str, ...] = ()
    source_kind: str | None = None
    description: str = ""


@dataclass(frozen=True, slots=True)
class AgentValidationIssue:
    severity: str
    code: str
    message: str
    ref: str | None = None


@dataclass(frozen=True, slots=True)
class AgentResolutionTrace:
    source: str
    status: str
    detail: str


@dataclass(frozen=True, slots=True)
class AgentResolutionSummary:
    status: str
    llm_routes: int
    tools: int
    skills: int
    access_grants: int
    authorization_grants: int
    issues: int


@dataclass(frozen=True, slots=True)
class AgentProfileResolution:
    profile_id: str
    profile_updated_at: str
    summary: AgentResolutionSummary
    llm_routes: tuple[AgentResolvedLlm, ...] = ()
    tools: tuple[AgentResolvedTool, ...] = ()
    skills: tuple[AgentResolvedSkill, ...] = ()
    access_grants: tuple[AgentAccessGrant, ...] = ()
    authorization_grants: tuple[AgentAuthorizationGrant, ...] = ()
    validation: tuple[AgentValidationIssue, ...] = ()
    trace: tuple[AgentResolutionTrace, ...] = ()


class AgentProfileResolutionQueryService:
    def __init__(
        self,
        *,
        agent_profiles: AgentProfileQueryPort,
        llm_profiles: LlmProfileQueryPort | None = None,
        tool_catalog: ToolCatalogQueryPort | None = None,
        skill_catalog: SkillCatalogQueryPort | None = None,
        access_readiness: AccessReadinessQueryPort | None = None,
        authorization_policies: AuthorizationPolicyQueryPort | None = None,
    ) -> None:
        self.agent_profiles = agent_profiles
        self.llm_profiles = llm_profiles
        self.tool_catalog = tool_catalog
        self.skill_catalog = skill_catalog
        self.access_readiness = access_readiness
        self.authorization_policies = authorization_policies

    def resolve(self, profile_id: str) -> AgentProfileResolution:
        profile = self.agent_profiles.get_profile(profile_id)
        runtime = profile.runtime_preferences
        workspace_dir = (
            runtime.workdir
            or runtime.workspace
            or runtime.home_dir
        )
        attrs = dict(runtime.attrs)
        tool_ids = _text_list(attrs.get("tool_ids", attrs.get("tools", ())))
        skill_ids = _text_list(attrs.get("skill_ids", attrs.get("skills", ())))

        validation: list[AgentValidationIssue] = []
        trace: list[AgentResolutionTrace] = [
            AgentResolutionTrace(
                source="agent",
                status="resolved",
                detail="profile loaded from Agent owner service",
            ),
        ]

        llm_routes, llm_access = self._resolve_llm_routes(
            profile,
            validation=validation,
            trace=trace,
        )
        tools, tool_access = self._resolve_tools(
            tool_ids,
            validation=validation,
            trace=trace,
        )
        skills, skill_access = self._resolve_skills(
            skill_ids,
            workspace_dir=workspace_dir,
            validation=validation,
            trace=trace,
        )
        access_grants = self._resolve_access_grants(
            [*llm_access, *tool_access, *skill_access],
            workspace_dir=workspace_dir,
        )
        authorization_grants = self._resolve_authorization_grants(
            profile.id,
            trace=trace,
        )

        status = "valid"
        if any(issue.severity == "error" for issue in validation):
            status = "error"
        elif any(issue.severity == "warning" for issue in validation):
            status = "warning"

        return AgentProfileResolution(
            profile_id=profile.id,
            profile_updated_at=profile.updated_at.isoformat(),
            summary=AgentResolutionSummary(
                status=status,
                llm_routes=len(llm_routes),
                tools=len(tools),
                skills=len(skills),
                access_grants=len(access_grants),
                authorization_grants=len(authorization_grants),
                issues=len(validation),
            ),
            llm_routes=tuple(llm_routes),
            tools=tuple(tools),
            skills=tuple(skills),
            access_grants=tuple(access_grants),
            authorization_grants=tuple(authorization_grants),
            validation=tuple(validation),
            trace=tuple(trace),
        )

    def _resolve_llm_routes(
        self,
        profile: Any,
        *,
        validation: list[AgentValidationIssue],
        trace: list[AgentResolutionTrace],
    ) -> tuple[list[AgentResolvedLlm], list[AgentAccessGrant]]:
        llm_by_id: dict[str, Any] = {}
        if self.llm_profiles is None:
            trace.append(
                AgentResolutionTrace(
                    source="llm",
                    status="unavailable",
                    detail="LLM profile query port is not configured",
                ),
            )
        else:
            try:
                llm_by_id = {item.id: item for item in self.llm_profiles.list_profiles()}
                trace.append(
                    AgentResolutionTrace(
                        source="llm",
                        status="resolved",
                        detail=f"{len(llm_by_id)} LLM profiles available",
                    ),
                )
            except Exception as exc:  # pragma: no cover - defensive partial stack guard
                trace.append(
                    AgentResolutionTrace(
                        source="llm",
                        status="error",
                        detail=str(exc),
                    ),
                )

        routes = _llm_route_slots(profile.llm_routing_policy)
        rows: list[AgentResolvedLlm] = []
        access: list[AgentAccessGrant] = []
        for slot, llm_id in routes:
            llm = llm_by_id.get(llm_id)
            if llm is None:
                rows.append(
                    AgentResolvedLlm(
                        slot=slot,
                        llm_id=llm_id,
                        resolved=False,
                        enabled=False,
                    ),
                )
                validation.append(
                    AgentValidationIssue(
                        severity="error",
                        code="agent.llm_not_found",
                        message=(
                            f"LLM route '{slot}' references missing profile '{llm_id}'."
                        ),
                        ref=f"llm:{llm_id}",
                    ),
                )
                continue

            credential_binding = _optional_text(getattr(llm, "credential_binding", None))
            enabled = bool(getattr(llm, "enabled", False))
            rows.append(
                AgentResolvedLlm(
                    slot=slot,
                    llm_id=llm_id,
                    resolved=True,
                    enabled=enabled,
                    provider=_enum_value(getattr(llm, "provider", None)),
                    model_name=_optional_text(getattr(llm, "model_name", None)),
                    capabilities=_enum_tuple(getattr(llm, "capabilities", ())),
                    context_window_tokens=_optional_int(
                        getattr(llm, "context_window_tokens", None),
                    ),
                    credential_binding=_public_credential_binding_label(
                        credential_binding,
                    ),
                ),
            )
            if not enabled:
                validation.append(
                    AgentValidationIssue(
                        severity="warning",
                        code="agent.llm_disabled",
                        message=f"LLM route '{slot}' points to disabled profile '{llm_id}'.",
                        ref=f"llm:{llm_id}",
                    ),
                )
            if credential_binding:
                access.append(
                    _pending_access_grant(
                        source_type="llm",
                        source_id=llm_id,
                        requirement=credential_binding,
                        grant_kind="credential_binding",
                    ),
                )
        return rows, access

    def _resolve_tools(
        self,
        tool_ids: list[str],
        *,
        validation: list[AgentValidationIssue],
        trace: list[AgentResolutionTrace],
    ) -> tuple[list[AgentResolvedTool], list[AgentAccessGrant]]:
        tool_by_id: dict[str, Any] = {}
        if self.tool_catalog is None:
            trace.append(
                AgentResolutionTrace(
                    source="tool",
                    status="unavailable",
                    detail="Tool catalog query port is not configured",
                ),
            )
        else:
            try:
                tool_by_id = {item.id: item for item in self.tool_catalog.list_tools()}
                trace.append(
                    AgentResolutionTrace(
                        source="tool",
                        status="resolved",
                        detail=f"{len(tool_by_id)} tools available",
                    ),
                )
            except Exception as exc:  # pragma: no cover - defensive partial stack guard
                trace.append(
                    AgentResolutionTrace(
                        source="tool",
                        status="error",
                        detail=str(exc),
                    ),
                )

        rows: list[AgentResolvedTool] = []
        access: list[AgentAccessGrant] = []
        for tool_id in dict.fromkeys(tool_ids):
            tool = tool_by_id.get(tool_id)
            if tool is None:
                rows.append(
                    AgentResolvedTool(
                        tool_id=tool_id,
                        resolved=False,
                        enabled=False,
                    ),
                )
                validation.append(
                    AgentValidationIssue(
                        severity="error",
                        code="agent.tool_not_found",
                        message=(
                            f"Tool '{tool_id}' is selected but was not found in Tool catalog."
                        ),
                        ref=f"tool:{tool_id}",
                    ),
                )
                continue

            access_requirements = _text_tuple(getattr(tool, "access_requirements", ()))
            access_requirement_sets = tuple(
                _text_tuple(group)
                for group in getattr(tool, "access_requirement_sets", ())
            )
            enabled = bool(getattr(tool, "enabled", False))
            policy = getattr(tool, "execution_policy", None)
            rows.append(
                AgentResolvedTool(
                    tool_id=tool_id,
                    resolved=True,
                    enabled=enabled,
                    name=_optional_text(getattr(tool, "name", None)),
                    kind=_enum_value(getattr(tool, "kind", None)),
                    source_kind=_enum_value(getattr(tool, "source_kind", None)),
                    access_requirements=access_requirements,
                    access_requirement_sets=access_requirement_sets,
                    required_effect_ids=_text_tuple(
                        getattr(tool, "required_effect_ids", ()),
                    ),
                    requires_confirmation=bool(
                        getattr(policy, "requires_confirmation", False),
                    ),
                    mutates_state=bool(getattr(policy, "mutates_state", False)),
                ),
            )
            if not enabled:
                validation.append(
                    AgentValidationIssue(
                        severity="warning",
                        code="agent.tool_disabled",
                        message=f"Tool '{tool_id}' is selected but disabled.",
                        ref=f"tool:{tool_id}",
                    ),
                )
            for requirement in _flatten_requirements(
                access_requirements,
                access_requirement_sets,
            ):
                access.append(
                    _pending_access_grant(
                        source_type="tool",
                        source_id=tool_id,
                        requirement=requirement,
                        grant_kind="requirement",
                    ),
                )
        return rows, access

    def _resolve_skills(
        self,
        skill_ids: list[str],
        *,
        workspace_dir: str | None,
        validation: list[AgentValidationIssue],
        trace: list[AgentResolutionTrace],
    ) -> tuple[list[AgentResolvedSkill], list[AgentAccessGrant]]:
        skill_by_id: dict[str, Any] = {}
        if self.skill_catalog is None:
            trace.append(
                AgentResolutionTrace(
                    source="skills",
                    status="unavailable",
                    detail="Skills catalog query port is not configured",
                ),
            )
        else:
            try:
                skills = self.skill_catalog.list_available(
                    workspace_dir=workspace_dir,
                    surface="interactive",
                )
                skill_by_id = {item.name: item for item in skills}
                trace.append(
                    AgentResolutionTrace(
                        source="skills",
                        status="resolved",
                        detail=f"{len(skill_by_id)} skills available",
                    ),
                )
            except Exception as exc:  # pragma: no cover - defensive partial stack guard
                trace.append(
                    AgentResolutionTrace(
                        source="skills",
                        status="error",
                        detail=str(exc),
                    ),
                )

        rows: list[AgentResolvedSkill] = []
        access: list[AgentAccessGrant] = []
        for skill_id in dict.fromkeys(skill_ids):
            skill = skill_by_id.get(skill_id)
            if skill is None:
                rows.append(AgentResolvedSkill(skill_id=skill_id, resolved=False))
                validation.append(
                    AgentValidationIssue(
                        severity="warning",
                        code="agent.skill_not_found",
                        message=(
                            f"Skill '{skill_id}' is selected but was not found "
                            "for this workspace/surface."
                        ),
                        ref=f"skill:{skill_id}",
                    ),
                )
                continue

            requirements = getattr(skill, "requirements", None)
            access_requirements = (
                _text_tuple(getattr(requirements, "compatibility_auth", ()))
                + _text_tuple(getattr(requirements, "compatibility_secrets", ()))
                + _text_tuple(
                    getattr(requirements, "compatibility_credential_files", ()),
                )
            )
            rows.append(
                AgentResolvedSkill(
                    skill_id=skill_id,
                    resolved=True,
                    name=_optional_text(getattr(skill, "name", None)),
                    source=_optional_text(getattr(skill, "source", None)),
                    required_tools=_text_tuple(
                        getattr(requirements, "required_tools", ()),
                    ),
                    optional_tools=_text_tuple(
                        getattr(requirements, "optional_tools", ()),
                    ),
                    suggested_tools=_text_tuple(
                        getattr(requirements, "suggested_tools", ()),
                    ),
                    required_effects=_text_tuple(
                        getattr(requirements, "required_effects", ()),
                    ),
                    access_requirements=access_requirements,
                ),
            )
            for requirement in access_requirements:
                access.append(
                    _pending_access_grant(
                        source_type="skill",
                        source_id=skill_id,
                        requirement=requirement,
                        grant_kind="requirement",
                    ),
                )
        return rows, access

    def _resolve_access_grants(
        self,
        grants: list[AgentAccessGrant],
        *,
        workspace_dir: str | None,
    ) -> list[AgentAccessGrant]:
        resolved: list[AgentAccessGrant] = []
        seen: set[tuple[str, str, str, str]] = set()
        for grant in grants:
            raw_requirement = grant._raw_requirement or grant.requirement
            key = (
                grant.source_type,
                grant.source_id,
                grant.grant_kind,
                raw_requirement,
            )
            if key in seen:
                continue
            seen.add(key)
            if self.access_readiness is None:
                resolved.append(grant)
                continue
            try:
                readiness = (
                    self.access_readiness.check_credential_binding(
                        raw_requirement,
                        workspace_dir=workspace_dir,
                    )
                    if grant.grant_kind == "credential_binding"
                    else self.access_readiness.check_requirement(
                        raw_requirement,
                        workspace_dir=workspace_dir,
                    )
                )
                payload = readiness.to_payload()
                resolved.append(
                    AgentAccessGrant(
                        source_type=grant.source_type,
                        source_id=grant.source_id,
                        requirement=grant.requirement,
                        grant_kind=grant.grant_kind,
                        status=str(payload.get("status", "unknown")),
                        ready=bool(payload.get("ready", False)),
                        setup_available=bool(payload.get("setup_available", False)),
                        reason=_optional_text(payload.get("reason")),
                    ),
                )
            except Exception as exc:  # pragma: no cover - host access setup may vary
                resolved.append(
                    AgentAccessGrant(
                        source_type=grant.source_type,
                        source_id=grant.source_id,
                        requirement=grant.requirement,
                        grant_kind=grant.grant_kind,
                        status="unknown",
                        ready=False,
                        setup_available=False,
                        reason=str(exc),
                    ),
                )
        return resolved

    def _resolve_authorization_grants(
        self,
        profile_id: str,
        *,
        trace: list[AgentResolutionTrace],
    ) -> list[AgentAuthorizationGrant]:
        if self.authorization_policies is None:
            trace.append(
                AgentResolutionTrace(
                    source="authorization",
                    status="unavailable",
                    detail="Authorization policy query port is not configured",
                ),
            )
            return []

        try:
            policies = self.authorization_policies.list_policies()
        except Exception as exc:  # pragma: no cover - defensive partial stack guard
            trace.append(
                AgentResolutionTrace(
                    source="authorization",
                    status="error",
                    detail=str(exc),
                ),
            )
            return []

        grants = [
            grant
            for policy in policies
            if (grant := _authorization_grant_from_policy(policy, profile_id)) is not None
        ]
        trace.append(
            AgentResolutionTrace(
                source="authorization",
                status="resolved",
                detail=f"{len(grants)} agent authorization policies matched",
            ),
        )
        return grants


def _llm_route_slots(policy: Any) -> list[tuple[str, str]]:
    slots: list[tuple[str, str]] = []
    default_llm_id = _optional_text(getattr(policy, "default_llm_id", None))
    if default_llm_id:
        slots.append(("default", default_llm_id))
    for index, llm_id in enumerate(
        _text_tuple(getattr(policy, "fallback_llm_ids", ())),
        start=1,
    ):
        slots.append((f"fallback:{index}", llm_id))
    image_llm_id = _optional_text(getattr(policy, "image_llm_id", None))
    if image_llm_id:
        slots.append(("image", image_llm_id))
    document_llm_id = _optional_text(getattr(policy, "document_llm_id", None))
    if document_llm_id:
        slots.append(("document", document_llm_id))
    return list(dict.fromkeys(slots))


def _pending_access_grant(
    *,
    source_type: str,
    source_id: str,
    requirement: str,
    grant_kind: str,
) -> AgentAccessGrant:
    return AgentAccessGrant(
        source_type=source_type,
        source_id=source_id,
        requirement=(
            _public_credential_binding_label(requirement)
            if grant_kind == "credential_binding"
            else requirement
        ),
        grant_kind=grant_kind,
        _raw_requirement=requirement,
    )


def _flatten_requirements(
    requirements: tuple[str, ...],
    requirement_sets: tuple[tuple[str, ...], ...],
) -> tuple[str, ...]:
    values: list[str] = []
    values.extend(requirements)
    for group in requirement_sets:
        values.extend(group)
    return tuple(dict.fromkeys(item for item in values if item))


def _authorization_grant_from_policy(
    policy: Any,
    profile_id: str,
) -> AgentAuthorizationGrant | None:
    if not _policy_targets_agent(policy, profile_id):
        return None

    actions = _text_tuple(getattr(policy, "actions", ()))
    action = _authorization_action(actions)
    if action is None:
        return None

    resource_match = _dict_payload(getattr(policy, "resource_match", {}))
    effect_ids = _text_tuple(resource_match.get("authorization_effect_ids", ()))
    tool_ids = _text_tuple(getattr(policy, "resource_id", None))
    tool_ids = tuple(dict.fromkeys((*tool_ids, *_text_tuple(resource_match.get("tool_ids", ())))))
    if not tool_ids:
        tool_ids = _text_tuple(resource_match.get("tool_id", ()))

    return AgentAuthorizationGrant(
        policy_id=str(getattr(policy, "id", "")).strip(),
        effect=_enum_value(getattr(policy, "effect", None)) or "unknown",
        action=action,
        status="enabled" if bool(getattr(policy, "enabled", False)) else "disabled",
        effect_ids=effect_ids,
        tool_ids=tool_ids,
        source_kind=_optional_text(getattr(policy, "source_kind", None)),
        description=_optional_text(getattr(policy, "description", None)) or "",
    )


def _authorization_action(actions: tuple[str, ...]) -> str | None:
    for candidate in ("tool.effect.authorize", "tool.authorize"):
        if any(fnmatch(candidate, pattern) for pattern in actions):
            return candidate
    return None


def _policy_targets_agent(policy: Any, profile_id: str) -> bool:
    subject_type = _optional_text(getattr(policy, "subject_type", None))
    subject_id = _optional_text(getattr(policy, "subject_id", None))
    if subject_type == "agent" and _matches_agent_selector(subject_id, profile_id):
        return True

    subject_match = _dict_payload(getattr(policy, "subject_match", {}))
    context_match = _dict_payload(getattr(policy, "context_match", {}))
    return any(
        _matches_agent_selector(value, profile_id)
        for value in (
            subject_match.get("agent_id"),
            subject_match.get("profile_id"),
            context_match.get("agent_id"),
            context_match.get("profile_id"),
        )
    )


def _matches_agent_selector(value: object, profile_id: str) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, tuple, set)):
        return any(_matches_agent_selector(item, profile_id) for item in value)
    selector = str(value).strip()
    if not selector:
        return False
    return fnmatch(profile_id, selector)


def _dict_payload(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text_list(value: object) -> list[str]:
    return list(_text_tuple(value))


def _text_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if not isinstance(value, (list, tuple, set)):
        return ()
    return tuple(
        str(item).strip()
        for item in value
        if item is not None and str(item).strip()
    )


def _enum_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple, set)):
        return ()
    return tuple(_enum_value(item) for item in value if _enum_value(item) is not None)


def _enum_value(value: object) -> str | None:
    raw = getattr(value, "value", value)
    return _optional_text(raw)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _public_credential_binding_label(binding: str | None) -> str | None:
    if binding is None or not binding.strip():
        return None
    normalized = binding.strip()
    if normalized.startswith("env:"):
        env_name = normalized.removeprefix("env:").strip()
        return f"env:{env_name}" if env_name else "env"
    if normalized.startswith("file:"):
        return "file credential"
    if normalized.startswith("codex_auth_json") or normalized in {
        "codex-cli",
        "codex_auth_json",
    }:
        return "codex_auth_json"
    return "credential binding"
