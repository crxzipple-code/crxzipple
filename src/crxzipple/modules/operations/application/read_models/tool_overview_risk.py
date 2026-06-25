from __future__ import annotations

from crxzipple.modules.tool.domain import Tool


def risky_tools(tools: list[Tool]) -> list[Tool]:
    return [
        tool
        for tool in tools
        if tool.execution_policy.requires_confirmation
        or tool.execution_policy.mutates_state
        or tool.access_requirement_sets
        or tool.runtime_requirement_sets
        or tool.required_effect_ids
    ]


def overview_risky_tools(tools: list[Tool]) -> list[Tool]:
    return [
        tool
        for tool in tools
        if tool.execution_policy.requires_confirmation
        or tool.execution_policy.mutates_state
        or tool.access_requirement_sets
        or tool.runtime_requirement_sets
    ]


def tool_risk_reason(tool: Tool) -> str:
    reasons: list[str] = []
    if tool.execution_policy.requires_confirmation:
        reasons.append("confirmation")
    if tool.execution_policy.mutates_state:
        reasons.append("mutates state")
    if tool.access_requirement_sets:
        requirement_sets = [
            "+".join(requirements)
            for requirements in tool.access_requirement_sets
            if requirements
        ]
        if requirement_sets:
            reasons.append(f"access: {' OR '.join(requirement_sets)}")
        else:
            reasons.append("access gated")
    if tool.runtime_requirement_sets:
        requirement_sets = [
            "+".join(requirements)
            for requirements in tool.runtime_requirement_sets
            if requirements
        ]
        if requirement_sets:
            reasons.append(f"runtime: {' OR '.join(requirement_sets)}")
        else:
            reasons.append("runtime gated")
    if tool.required_effect_ids:
        reasons.append(f"effects: {', '.join(tool.required_effect_ids)}")
    return ", ".join(reasons) or "standard"
