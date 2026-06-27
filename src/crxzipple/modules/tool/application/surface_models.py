from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class ToolSurfaceFunction:
    function_id: str
    name: str
    title: str
    description: str
    input_schema: Mapping[str, Any]
    source_id: str
    group_key: str
    runtime_kind: str
    execution_modes: tuple[str, ...] = ()
    execution_strategies: tuple[str, ...] = ()
    execution_environments: tuple[str, ...] = ()
    requires_confirmation: bool = False
    mutates_state: bool = False
    supports_parallel: bool = True
    readiness: Mapping[str, Any] = field(default_factory=dict)
    authorization: Mapping[str, Any] = field(default_factory=dict)
    concurrency_key: str | None = None
    provider_schema_hints: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "function_id": self.function_id,
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "input_schema": dict(self.input_schema),
            "source_id": self.source_id,
            "group_key": self.group_key,
            "runtime_kind": self.runtime_kind,
            "execution_modes": list(self.execution_modes),
            "execution_strategies": list(self.execution_strategies),
            "execution_environments": list(self.execution_environments),
            "requires_confirmation": self.requires_confirmation,
            "mutates_state": self.mutates_state,
            "supports_parallel": self.supports_parallel,
            "readiness": dict(self.readiness),
            "authorization": dict(self.authorization),
            "provider_schema_hints": dict(self.provider_schema_hints),
            "metadata": dict(self.metadata),
        }
        if self.concurrency_key is not None:
            payload["concurrency_key"] = self.concurrency_key
        return payload


@dataclass(frozen=True, slots=True)
class ToolSurfaceGroup:
    group_key: str
    title: str
    summary: str
    function_refs: tuple[str, ...] = ()
    default_expanded: bool = False
    schema_enabled: bool = True
    estimate: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "group_key": self.group_key,
            "title": self.title,
            "summary": self.summary,
            "function_refs": list(self.function_refs),
            "default_expanded": self.default_expanded,
            "schema_enabled": self.schema_enabled,
            "estimate": dict(self.estimate),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ToolSurfaceSource:
    source_id: str
    source_key: str
    source_kind: str
    title: str
    summary: str
    groups: tuple[ToolSurfaceGroup, ...] = ()
    readiness: Mapping[str, Any] = field(default_factory=dict)
    authorization: Mapping[str, Any] = field(default_factory=dict)
    runtime_requirements: tuple[Mapping[str, Any], ...] = ()
    runtime_request_metadata: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_key": self.source_key,
            "source_kind": self.source_kind,
            "title": self.title,
            "summary": self.summary,
            "groups": [group.to_payload() for group in self.groups],
            "readiness": dict(self.readiness),
            "authorization": dict(self.authorization),
            "runtime_requirements": [
                dict(requirement) for requirement in self.runtime_requirements
            ],
            "runtime_request_metadata": dict(self.runtime_request_metadata),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ToolSurface:
    surface_id: str
    session_id: str | None = None
    run_id: str | None = None
    agent_id: str | None = None
    policy_version: str = "tool_surface.v1"
    sources: tuple[ToolSurfaceSource, ...] = ()
    functions: tuple[ToolSurfaceFunction, ...] = ()
    default_tool_choice: str = "auto"
    parallel_tool_calls: bool = True
    estimate: Mapping[str, Any] = field(default_factory=dict)
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_payload(self) -> dict[str, Any]:
        return {
            "surface_id": self.surface_id,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "agent_id": self.agent_id,
            "policy_version": self.policy_version,
            "sources": [source.to_payload() for source in self.sources],
            "functions": [function.to_payload() for function in self.functions],
            "default_tool_choice": self.default_tool_choice,
            "parallel_tool_calls": self.parallel_tool_calls,
            "estimate": dict(self.estimate),
            "diagnostics": dict(self.diagnostics),
            "created_at": self.created_at.isoformat(),
        }
