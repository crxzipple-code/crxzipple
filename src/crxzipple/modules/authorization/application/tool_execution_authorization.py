from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from crxzipple.modules.authorization.domain import (
    AuthorizationContext,
    AuthorizationDecision,
    AuthorizationDecisionCode,
    AuthorizationRequest,
    ToolExecutionAuthorizationRequest,
)


@dataclass(frozen=True, slots=True)
class GrantedAuthorizationPayload:
    tool_ids: tuple[str, ...] = ()
    effect_ids: tuple[str, ...] = ()


def check_tool_execution_authorization(
    request: ToolExecutionAuthorizationRequest,
    *,
    temporary_authorization: GrantedAuthorizationPayload,
    evaluate_request: Callable[[AuthorizationRequest], AuthorizationDecision],
) -> AuthorizationDecision:
    context_attrs = dict(request.context.attrs)
    granted_tool_ids = tuple(
        tool_id.strip()
        for tool_id in (*request.granted_tool_ids, *temporary_authorization.tool_ids)
        if tool_id is not None and tool_id.strip()
    )
    granted_effect_ids = tuple(
        effect_id.strip()
        for effect_id in (
            *request.granted_effect_ids,
            *temporary_authorization.effect_ids,
        )
        if effect_id is not None and effect_id.strip()
    )
    base_context = AuthorizationContext(
        attrs={
            **context_attrs,
            "granted_tool_ids": list(granted_tool_ids),
            "granted_effect_ids": list(granted_effect_ids),
        },
    )

    tool_access_decision = evaluate_request(
        AuthorizationRequest(
            subject=request.subject,
            action="tool.authorize",
            resource=request.resource,
            context=base_context,
        ),
    )
    if tool_access_decision.code is AuthorizationDecisionCode.POLICY_DENIED:
        return tool_access_decision

    tool_run_decision = evaluate_request(
        AuthorizationRequest(
            subject=request.subject,
            action="tool.run",
            resource=request.resource,
            context=base_context,
        ),
    )
    if tool_run_decision.code is AuthorizationDecisionCode.POLICY_DENIED:
        return tool_run_decision

    required_effect_ids = tuple(
        effect_id.strip()
        for effect_id in request.required_effect_ids
        if effect_id is not None and effect_id.strip()
    )
    matched_policy_ids: list[str] = list(tool_access_decision.matched_policy_ids)
    obligations = list(tool_access_decision.obligations)
    matched_policy_ids.extend(tool_run_decision.matched_policy_ids)
    obligations.extend(tool_run_decision.obligations)
    allowed_effect_ids: set[str] = set()
    for effect_id in required_effect_ids:
        effect_decision = evaluate_request(
            AuthorizationRequest(
                subject=request.subject,
                action="tool.effect.authorize",
                resource=request.resource,
                context=AuthorizationContext(
                    attrs={
                        **base_context.attrs,
                        "requested_effect_id": effect_id,
                    },
                ),
            ),
        )
        if effect_decision.code is AuthorizationDecisionCode.POLICY_DENIED:
            return AuthorizationDecision(
                allowed=False,
                reason=effect_decision.reason,
                code=AuthorizationDecisionCode.POLICY_DENIED,
                matched_policy_ids=effect_decision.matched_policy_ids,
                obligations=effect_decision.obligations,
                details={
                    **effect_decision.details,
                    "requested_effect_id": effect_id,
                },
            )
        if effect_decision.allowed:
            allowed_effect_ids.add(effect_id)
            matched_policy_ids.extend(effect_decision.matched_policy_ids)
            obligations.extend(effect_decision.obligations)

    missing_effect_ids = [
        effect_id
        for effect_id in required_effect_ids
        if effect_id not in granted_effect_ids and effect_id not in allowed_effect_ids
    ]
    if missing_effect_ids:
        resource_id = request.resource.id or "this tool"
        return AuthorizationDecision(
            allowed=False,
            reason=(
                f"Approval is required to execute '{resource_id}' with effect(s): "
                + ", ".join(missing_effect_ids)
                + "."
            ),
            code=AuthorizationDecisionCode.APPROVAL_REQUIRED,
            matched_policy_ids=tuple(dict.fromkeys(matched_policy_ids)),
            obligations=tuple(obligations),
            details={"missing_effect_ids": missing_effect_ids},
        )

    if request.resource.id is not None and request.resource.id in granted_tool_ids:
        return AuthorizationDecision(
            allowed=True,
            reason=(
                "Tool execution allowed because temporary authorization was "
                f"granted for '{request.resource.id}'."
            ),
            code=AuthorizationDecisionCode.ALLOW,
            matched_policy_ids=tuple(dict.fromkeys(matched_policy_ids)),
            obligations=tuple(obligations),
            details={
                "granted_tool_ids": list(granted_tool_ids),
                "granted_effect_ids": list(granted_effect_ids),
            },
        )
    if tool_access_decision.allowed:
        return AuthorizationDecision(
            allowed=True,
            reason=tool_access_decision.reason,
            code=AuthorizationDecisionCode.ALLOW,
            matched_policy_ids=tuple(dict.fromkeys(matched_policy_ids)),
            obligations=tuple(obligations),
            details={"granted_effect_ids": list(granted_effect_ids)},
        )

    return AuthorizationDecision(
        allowed=True,
        reason=(
            f"Tool execution allowed because required access is satisfied for "
            f"'{request.resource.id or 'tool'}'."
        ),
        code=AuthorizationDecisionCode.ALLOW,
        matched_policy_ids=tuple(dict.fromkeys(matched_policy_ids)),
        obligations=tuple(obligations),
    )
