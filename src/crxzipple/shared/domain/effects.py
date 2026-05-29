from __future__ import annotations

from dataclasses import dataclass

from crxzipple.shared.domain.value_objects import ValueObject


@dataclass(frozen=True, slots=True)
class EffectDescriptor(ValueObject):
    id: str
    label: str
    description: str


EFFECTS: dict[str, EffectDescriptor] = {
    "background_execution": EffectDescriptor(
        id="background_execution",
        label="Background execution",
        description="Run work outside the immediate turn in the background.",
    ),
    "workspace_read": EffectDescriptor(
        id="workspace_read",
        label="Workspace read access",
        description="Read files and inspect the local workspace.",
    ),
    "workspace_write": EffectDescriptor(
        id="workspace_write",
        label="Workspace write access",
        description="Modify files in the local workspace.",
    ),
    "network_search": EffectDescriptor(
        id="network_search",
        label="Network search",
        description="Search remote sources and fetch public web results.",
    ),
    "weather_data": EffectDescriptor(
        id="weather_data",
        label="Weather data access",
        description="Retrieve weather and geocoding data from remote APIs.",
    ),
    "market_data": EffectDescriptor(
        id="market_data",
        label="Market data access",
        description="Retrieve finance and market data from remote APIs.",
    ),
    "command_execution": EffectDescriptor(
        id="command_execution",
        label="Command execution",
        description="Run local shell or command-line actions.",
    ),
    "local_tool_access": EffectDescriptor(
        id="local_tool_access",
        label="Local tool access",
        description="Use locally provided tools that are gated by approval.",
    ),
    "browser.cdp.raw": EffectDescriptor(
        id="browser.cdp.raw",
        label="Raw browser CDP access",
        description="Send a raw Chrome DevTools Protocol command to a browser tab.",
    ),
    "remote_tool_execution": EffectDescriptor(
        id="remote_tool_execution",
        label="Remote tool execution",
        description="Use remote provider tools that are gated by approval.",
    ),
    "state_mutation": EffectDescriptor(
        id="state_mutation",
        label="State-changing access",
        description="Use tools that mutate local or external state.",
    ),
    "skill_authoring.create": EffectDescriptor(
        id="skill_authoring.create",
        label="Skill draft creation",
        description="Create governed skill authoring drafts.",
    ),
    "skill_authoring.update": EffectDescriptor(
        id="skill_authoring.update",
        label="Skill draft update",
        description="Update governed skill authoring drafts.",
    ),
    "skill_authoring.validate": EffectDescriptor(
        id="skill_authoring.validate",
        label="Skill draft validation",
        description="Validate governed skill authoring drafts.",
    ),
    "skill_authoring.diff": EffectDescriptor(
        id="skill_authoring.diff",
        label="Skill draft diff",
        description="Build review diffs for governed skill authoring drafts.",
    ),
    "skill_authoring.apply": EffectDescriptor(
        id="skill_authoring.apply",
        label="Skill draft apply",
        description="Apply an approved skill draft to the owner skill catalog.",
    ),
    "skill_authoring.reject": EffectDescriptor(
        id="skill_authoring.reject",
        label="Skill draft rejection",
        description="Reject governed skill authoring drafts.",
    ),
    "skill.package.write": EffectDescriptor(
        id="skill.package.write",
        label="Skill package write",
        description="Write skill package files in an owner skill source.",
    ),
    "sensitive_operation_confirmation": EffectDescriptor(
        id="sensitive_operation_confirmation",
        label="Sensitive operation confirmation",
        description="Use tools that explicitly require user confirmation.",
    ),
}


def get_effect_descriptor(effect_id: str) -> EffectDescriptor:
    normalized = effect_id.strip()
    return EFFECTS.get(
        normalized,
        EffectDescriptor(
            id=normalized,
            label=normalized.replace("_", " ").strip().title(),
            description="Use an additional gated capability.",
        ),
    )
