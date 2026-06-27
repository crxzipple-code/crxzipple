from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from crxzipple.core.config import OpenApiCredentialBinding
from crxzipple.modules.tool.application.specifications import ToolSpec
from crxzipple.modules.tool.domain import ToolDefinitionOrigin
from crxzipple.modules.tool.domain.value_objects import (
    ToolEnvironment,
    ToolExecutionPolicy,
    ToolExecutionSupport,
    ToolExecutionStrategy,
    ToolKind,
    ToolMode,
    ToolParameter,
)

from .openapi_access_requirements import (
    operation_access_requirement_sets,
    operation_credential_requirement_sets,
)


@dataclass(frozen=True, slots=True)
class OpenApiSecurityScheme:
    name: str
    scheme_type: str
    parameter_name: str | None = None
    location: str | None = None
    http_scheme: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OpenApiSecurityRequirement:
    scheme_names: tuple[str, ...]
    scopes_by_scheme: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OpenApiOperation:
    provider_name: str
    tool_id: str
    runtime_key: str
    name: str
    description: str
    method: str
    path_template: str
    base_url: str
    timeout_seconds: int
    path_parameters: tuple[str, ...]
    query_parameters: tuple[str, ...]
    body_required: bool
    tags: tuple[str, ...]
    parameters: tuple[ToolParameter, ...]
    security_schemes: tuple[OpenApiSecurityScheme, ...] = ()
    security_requirements: tuple[OpenApiSecurityRequirement, ...] = ()
    credential_bindings: tuple[OpenApiCredentialBinding, ...] = ()
    required_effect_ids: tuple[str, ...] = ()
    capability_ids: tuple[str, ...] = ()

    def to_tool_spec(self) -> ToolSpec:
        return ToolSpec(
            id=self.tool_id,
            name=self.name,
            description=self.description,
            provider_name=self.provider_name,
            kind=ToolKind.HTTP,
            parameters=self.parameters,
            tags=self.tags,
            required_effect_ids=self.required_effect_ids,
            access_requirement_sets=operation_access_requirement_sets(self),
            credential_requirements=operation_credential_requirement_sets(self),
            capability_ids=self.capability_ids,
            execution_policy=ToolExecutionPolicy(
                timeout_seconds=self.timeout_seconds,
                requires_confirmation=False,
                mutates_state=self.method.lower() not in {"get", "head", "options"},
            ),
            execution_support=ToolExecutionSupport(
                supported_modes=(ToolMode.INLINE, ToolMode.BACKGROUND),
                supported_strategies=(ToolExecutionStrategy.ASYNC,),
                supported_environments=(ToolEnvironment.REMOTE,),
            ),
            definition_origin=ToolDefinitionOrigin.REMOTE_DISCOVERY,
            runtime_key=self.runtime_key,
            enabled=True,
        )


__all__ = [
    "OpenApiOperation",
    "OpenApiSecurityRequirement",
    "OpenApiSecurityScheme",
]
