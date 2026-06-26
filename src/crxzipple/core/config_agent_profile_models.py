from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class AgentProfileDefaultsSettings:
    enabled: bool = True
    identity: dict[str, Any] = field(default_factory=dict)
    instruction_policy: dict[str, Any] = field(default_factory=dict)
    llm_routing_policy: dict[str, Any] = field(default_factory=dict)
    llm_policy: dict[str, Any] = field(default_factory=dict)
    execution_policy: dict[str, Any] = field(default_factory=dict)
    runtime_preferences: dict[str, Any] = field(default_factory=dict)
    memory: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentProfileSettings:
    id: str
    name: str
    enabled: bool = True
    identity: dict[str, Any] = field(default_factory=dict)
    instruction_policy: dict[str, Any] = field(default_factory=dict)
    llm_routing_policy: dict[str, Any] = field(default_factory=dict)
    llm_policy: dict[str, Any] = field(default_factory=dict)
    execution_policy: dict[str, Any] = field(default_factory=dict)
    runtime_preferences: dict[str, Any] = field(default_factory=dict)
    memory: dict[str, Any] = field(default_factory=dict)
