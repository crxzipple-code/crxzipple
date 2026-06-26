from __future__ import annotations

from typing import Any

from crxzipple.modules.agent.application.resolution_access import (
    flatten_requirements,
    pending_access_grant,
)
from crxzipple.modules.agent.application.resolution_authorization import (
    tool_ids_from_authorization_grants,
)
from crxzipple.modules.agent.application.resolution_models import (
    AgentAccessGrant,
    AgentAuthorizationGrant,
    AgentResolutionTrace,
    AgentResolvedTool,
    AgentValidationIssue,
)
from crxzipple.modules.agent.application.resolution_values import (
    enum_value,
    optional_text,
    text_tuple,
)


def resolve_tools(
    authorization_grants: list[AgentAuthorizationGrant],
    *,
    tool_catalog: Any | None,
    validation: list[AgentValidationIssue],
    trace: list[AgentResolutionTrace],
) -> tuple[list[AgentResolvedTool], list[AgentAccessGrant]]:
    tool_by_id: dict[str, Any] = {}
    if tool_catalog is None:
        trace.append(
            AgentResolutionTrace(
                source="tool",
                status="unavailable",
                detail="Tool catalog query port is not configured",
            ),
        )
    else:
        try:
            tool_by_id = {item.id: item for item in tool_catalog.list_tools()}
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
    tool_ids = tool_ids_from_authorization_grants(
        authorization_grants,
        tool_by_id=tool_by_id,
    )
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
                        f"Tool '{tool_id}' is authorized for this agent but was not found in Tool catalog."
                    ),
                    ref=f"tool:{tool_id}",
                ),
            )
            continue

        access_requirements = text_tuple(getattr(tool, "access_requirements", ()))
        access_requirement_sets = tuple(
            text_tuple(group)
            for group in getattr(tool, "access_requirement_sets", ())
        )
        enabled = bool(getattr(tool, "enabled", False))
        policy = getattr(tool, "execution_policy", None)
        rows.append(
            AgentResolvedTool(
                tool_id=tool_id,
                resolved=True,
                enabled=enabled,
                name=optional_text(getattr(tool, "name", None)),
                kind=enum_value(getattr(tool, "kind", None)),
                definition_origin=enum_value(
                    getattr(tool, "definition_origin", None),
                ),
                access_requirements=access_requirements,
                access_requirement_sets=access_requirement_sets,
                required_effect_ids=text_tuple(
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
                    message=f"Tool '{tool_id}' is authorized for this agent but disabled.",
                    ref=f"tool:{tool_id}",
                ),
            )
        for requirement in flatten_requirements(
            access_requirements,
            access_requirement_sets,
        ):
            access.append(
                pending_access_grant(
                    source_type="tool",
                    source_id=tool_id,
                    requirement=requirement,
                    grant_kind="requirement",
                ),
            )
    return rows, access


__all__ = ["resolve_tools"]
