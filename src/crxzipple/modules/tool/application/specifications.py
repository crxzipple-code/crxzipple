from __future__ import annotations

from dataclasses import dataclass, field

from crxzipple.shared.domain import ValueObject

from crxzipple.modules.tool.domain.entities import Tool
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.domain.value_objects import (
    ToolExecutionPolicy,
    ToolExecutionSupport,
    ToolKind,
    ToolParameter,
    ToolSourceKind,
)


@dataclass(frozen=True, slots=True)
class ToolSpec(ValueObject):
    id: str
    name: str
    description: str
    provider_name: str
    kind: ToolKind = ToolKind.FUNCTION
    parameters: tuple[ToolParameter, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)
    required_effect_ids: tuple[str, ...] = field(default_factory=tuple)
    execution_policy: ToolExecutionPolicy = field(default_factory=ToolExecutionPolicy)
    execution_support: ToolExecutionSupport = field(default_factory=ToolExecutionSupport)
    source_kind: ToolSourceKind = ToolSourceKind.MANUAL
    runtime_key: str | None = None
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ToolValidationError("Tool spec id cannot be empty.")
        if not self.provider_name.strip():
            raise ToolValidationError("Tool spec provider_name cannot be empty.")
        object.__setattr__(self, "parameters", tuple(self.parameters))
        object.__setattr__(
            self,
            "tags",
            tuple(
                dict.fromkeys(
                    tag.strip().lower()
                    for tag in self.tags
                    if tag is not None and tag.strip()
                ),
            ),
        )
        object.__setattr__(
            self,
            "required_effect_ids",
            tuple(
                dict.fromkeys(
                    effect_id.strip()
                    for effect_id in self.required_effect_ids
                    if effect_id is not None and effect_id.strip()
                ),
            ),
        )

    @classmethod
    def from_tool(cls, tool: Tool, *, provider_name: str) -> "ToolSpec":
        return cls(
            id=tool.id,
            name=tool.name,
            description=tool.description,
            provider_name=provider_name,
            kind=tool.kind,
            parameters=tool.parameters,
            tags=tool.tags,
            required_effect_ids=tool.required_effect_ids,
            execution_policy=tool.execution_policy,
            execution_support=tool.execution_support,
            source_kind=tool.source_kind,
            runtime_key=tool.runtime_key,
            enabled=tool.enabled,
        )
