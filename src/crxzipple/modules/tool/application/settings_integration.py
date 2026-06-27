from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from crxzipple.core.config import McpProviderSettings, OpenApiProviderSettings
from crxzipple.modules.tool.application.settings_config_values import (
    ToolProviderConfigLike,
    ToolRootConfigLike,
    dedupe_text,
    enabled,
    lookup,
    provider_name,
    required_text,
)
from crxzipple.modules.tool.application.settings_provider_projection import (
    local_path_from_provider_config,
    mcp_provider_settings_from_config,
    openapi_provider_settings_from_config,
)


@dataclass(frozen=True, slots=True)
class ToolSettingsBootstrapConfig:
    openapi_providers: tuple[OpenApiProviderSettings, ...] = ()
    mcp_providers: tuple[McpProviderSettings, ...] = ()
    local_paths: tuple[str, ...] = ()


def tool_settings_bootstrap_config_from_settings(
    providers: Iterable[ToolProviderConfigLike] = (),
    roots: Iterable[ToolRootConfigLike] = (),
    *,
    include_disabled: bool = False,
) -> ToolSettingsBootstrapConfig:
    openapi_providers: list[OpenApiProviderSettings] = []
    mcp_providers: list[McpProviderSettings] = []
    local_paths: list[str] = []

    for provider in providers:
        if not include_disabled and not enabled(provider):
            continue
        provider_kind = required_text(
            lookup(provider, "provider_kind", "kind"),
            field_name="provider_kind",
        ).lower()
        if provider_kind == "openapi":
            openapi_providers.append(openapi_provider_settings_from_config(provider))
        elif provider_kind == "mcp":
            mcp_providers.append(mcp_provider_settings_from_config(provider))
        elif provider_kind == "local_root":
            local_paths.append(local_path_from_provider_config(provider))
        else:
            raise ValueError(
                f"Tool provider '{provider_name(provider)}' provider_kind must be one of: "
                "openapi, mcp, local_root.",
            )

    for root in roots:
        if not include_disabled and not enabled(root):
            continue
        local_paths.append(required_text(lookup(root, "path"), field_name="path"))

    return ToolSettingsBootstrapConfig(
        openapi_providers=tuple(openapi_providers),
        mcp_providers=tuple(mcp_providers),
        local_paths=dedupe_text(local_paths),
    )


__all__ = [
    "ToolSettingsBootstrapConfig",
    "mcp_provider_settings_from_config",
    "openapi_provider_settings_from_config",
    "tool_settings_bootstrap_config_from_settings",
]
