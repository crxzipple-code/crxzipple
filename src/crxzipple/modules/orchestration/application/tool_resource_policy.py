from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.llm.domain import ToolCallIntent
from crxzipple.modules.orchestration.application.tool_resolver import ResolvedTool


@dataclass(frozen=True, slots=True)
class ToolResourcePolicy:
    supports_parallel: bool
    mutates_state: bool
    execution_lane: str
    resource_scope: str | None = None
    resource_key: str | None = None
    serial_group_key: str | None = None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "supports_parallel": self.supports_parallel,
            "mutates_state": self.mutates_state,
            "execution_lane": self.execution_lane,
        }
        if self.resource_scope is not None:
            payload["resource_scope"] = self.resource_scope
        if self.resource_key is not None:
            payload["resource_key"] = self.resource_key
        if self.serial_group_key is not None:
            payload["serial_group_key"] = self.serial_group_key
        return payload


def tool_resource_policy(
    resolved_tool: ResolvedTool,
    *,
    tool_call: ToolCallIntent,
    context_attrs: dict[str, object],
) -> ToolResourcePolicy:
    policy = resolved_tool.tool.execution_policy
    resource_scope = optional_context_text(policy.resource_scope)
    serial_group_key = optional_context_text(policy.serial_group_key)
    execution_lane = (
        "serial"
        if serial_group_key is not None or not policy.supports_parallel
        else "parallel"
    )
    return ToolResourcePolicy(
        supports_parallel=bool(policy.supports_parallel),
        mutates_state=bool(policy.mutates_state),
        execution_lane=execution_lane,
        resource_scope=resource_scope,
        resource_key=resource_key(
            resource_scope,
            arguments=tool_call.arguments,
            context_attrs=context_attrs,
            tool_id=resolved_tool.tool.id,
        ),
        serial_group_key=serial_group_key,
    )


def resource_policies_conflict(
    left: ToolResourcePolicy,
    right: ToolResourcePolicy,
) -> bool:
    if (
        left.execution_lane != "serial"
        and right.execution_lane != "serial"
        and left.supports_parallel
        and right.supports_parallel
    ):
        return False
    if left.resource_scope == "browser.target" and right.resource_scope == "browser.target":
        return browser_target_resources_conflict(
            left.resource_key,
            right.resource_key,
        )
    if left.resource_key is not None and right.resource_key is not None:
        return left.resource_key == right.resource_key
    return True


def resource_key(
    resource_scope: str | None,
    *,
    arguments: dict[str, object],
    context_attrs: dict[str, object],
    tool_id: str,
) -> str | None:
    if resource_scope is None:
        return None
    if resource_scope == "browser.target":
        return browser_target_resource_key(arguments, context_attrs)
    return f"{resource_scope}:{tool_id}"


def browser_target_resource_key(
    arguments: dict[str, object],
    context_attrs: dict[str, object],
) -> str:
    allocation = (
        optional_context_text(arguments.get("allocation_id"))
        or optional_context_text(arguments.get("lease_id"))
        or optional_context_text(arguments.get("browser_allocation_id"))
        or optional_context_text(context_attrs.get("browser_allocation_id"))
        or optional_context_text(context_attrs.get("browser_lease_id"))
    )
    target = (
        optional_context_text(arguments.get("target_id"))
        or optional_context_text(arguments.get("targetId"))
        or optional_context_text(context_attrs.get("browser_target_id"))
        or "*"
    )
    if allocation is not None:
        return f"browser.target:allocation={allocation};target={target}"
    profile = (
        optional_context_text(arguments.get("profile"))
        or optional_context_text(context_attrs.get("browser_profile"))
        or optional_context_text(context_attrs.get("default_browser_profile"))
        or "*"
    )
    return f"browser.target:profile={profile};target={target}"


def browser_target_resources_conflict(
    left_key: str | None,
    right_key: str | None,
) -> bool:
    left = browser_target_resource_parts(left_key)
    right = browser_target_resource_parts(right_key)
    if not left or not right:
        return True
    left_allocation = left.get("allocation")
    right_allocation = right.get("allocation")
    if left_allocation is not None or right_allocation is not None:
        if left_allocation is None or right_allocation is None:
            return True
        if left_allocation != right_allocation:
            return False
    else:
        left_profile = left.get("profile") or "*"
        right_profile = right.get("profile") or "*"
        if left_profile != "*" and right_profile != "*" and left_profile != right_profile:
            return False
    left_target = left.get("target") or "*"
    right_target = right.get("target") or "*"
    return left_target == "*" or right_target == "*" or left_target == right_target


def browser_target_resource_parts(resource_key: str | None) -> dict[str, str]:
    if resource_key is None or not resource_key.startswith("browser.target:"):
        return {}
    parts: dict[str, str] = {}
    raw = resource_key.removeprefix("browser.target:")
    for item in raw.split(";"):
        key, separator, value = item.partition("=")
        if separator and key.strip() and value.strip():
            parts[key.strip()] = value.strip()
    return parts


def optional_context_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
