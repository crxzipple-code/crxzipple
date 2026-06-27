from __future__ import annotations

from crxzipple.core.config import OpenApiProviderSettings
from crxzipple.modules.tool.application.capabilities import (
    DEFAULT_TOOL_CAPABILITY_CATALOG,
)
from crxzipple.modules.tool.application.specifications import ToolSpec
from crxzipple.modules.tool.domain import ToolDefinitionOrigin

from .openapi_document import parse_openapi_operations
from .openapi_models import (
    OpenApiOperation,
    OpenApiSecurityRequirement,
    OpenApiSecurityScheme,
)


class OpenApiDiscoveryProvider:
    definition_origin = ToolDefinitionOrigin.REMOTE_DISCOVERY

    def __init__(
        self,
        config: OpenApiProviderSettings,
        *,
        capability_ids: tuple[str, ...] = (),
    ) -> None:
        self.config = config
        self.capability_ids = DEFAULT_TOOL_CAPABILITY_CATALOG.validate_capability_ids(
            capability_ids,
        )
        self.name = config.name
        self.description = (
            config.description
            or f"Discovers remote HTTP tools from OpenAPI document '{config.name}'."
        )
        self._operations_cache: tuple[OpenApiOperation, ...] | None = None

    def discover_specs(self) -> list[ToolSpec]:
        return [operation.to_tool_spec() for operation in self.operations()]

    def operations(self) -> tuple[OpenApiOperation, ...]:
        if self._operations_cache is None:
            self._operations_cache = tuple(
                parse_openapi_operations(
                    self.config,
                    capability_ids=self.capability_ids,
                ),
            )
        return self._operations_cache


__all__ = [
    "OpenApiDiscoveryProvider",
    "OpenApiOperation",
    "OpenApiSecurityRequirement",
    "OpenApiSecurityScheme",
]
