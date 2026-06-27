from __future__ import annotations

from typing import Iterable

from crxzipple.core.config import McpProviderSettings, OpenApiProviderSettings
from crxzipple.modules.tool.application.settings_config_values import (
    ToolProviderConfigLike,
    lookup,
    lookup_configured_value,
    optional_positive_int,
    optional_text,
    positive_int,
    provider_name,
    required_text,
    string_tuple,
)
from crxzipple.modules.tool.application.settings_openapi_credentials import (
    openapi_credential_bindings_from_config,
)


def openapi_provider_settings_from_config(
    config: ToolProviderConfigLike,
) -> OpenApiProviderSettings:
    name = provider_name(config)
    spec_location = required_text(
        lookup(config, "spec_location", "spec_path", "spec_url", "spec"),
        field_name=f"OpenAPI provider '{name}' spec_location/spec_path",
    )
    return OpenApiProviderSettings(
        name=name,
        spec_location=spec_location,
        base_url=optional_text(lookup(config, "base_url")),
        description=optional_text(lookup(config, "description", "display_name")) or "",
        timeout_seconds=positive_int(
            lookup_configured_value(config, "timeout_seconds"),
            default=30,
            field_name=f"OpenAPI provider '{name}' timeout_seconds",
        ),
        max_concurrency=optional_positive_int(
            lookup_configured_value(config, "max_concurrency"),
            field_name=f"OpenAPI provider '{name}' max_concurrency",
        ),
        credential_bindings=openapi_credential_bindings_from_config(
            config,
            provider_name=name,
        ),
        default_effect_ids=string_tuple(
            lookup_configured_value(config, "default_effect_ids"),
        ),
        runtime_requirements=string_tuple(
            lookup_configured_value(config, "runtime_requirements"),
        ),
    )


def mcp_provider_settings_from_config(
    config: ToolProviderConfigLike,
) -> McpProviderSettings:
    name = provider_name(config)
    transport = str(lookup_configured_value(config, "transport") or "stdio").strip().lower()
    return McpProviderSettings(
        name=name,
        command=command_parts_from_config(
            config,
            provider_name=name,
            required=transport == "stdio",
        ),
        transport=transport,
        endpoint_url=optional_text(lookup_configured_value(config, "endpoint_url", "url")),
        description=optional_text(lookup(config, "description", "display_name")) or "",
        timeout_seconds=positive_int(
            lookup_configured_value(config, "timeout_seconds"),
            default=30,
            field_name=f"MCP provider '{name}' timeout_seconds",
        ),
        max_concurrency=optional_positive_int(
            lookup_configured_value(config, "max_concurrency"),
            field_name=f"MCP provider '{name}' max_concurrency",
        ),
        default_effect_ids=string_tuple(
            lookup_configured_value(config, "default_effect_ids"),
        ),
    )


def command_parts_from_config(
    config: ToolProviderConfigLike,
    *,
    provider_name: str,
    required: bool = True,
) -> tuple[str, ...]:
    command = lookup(config, "command")
    args = lookup(config, "args")
    if isinstance(command, str):
        command_parts = (command, *(string_tuple(args) if args is not None else ()))
    elif isinstance(command, Iterable):
        command_parts = tuple(str(part).strip() for part in command if str(part).strip())
    else:
        if not required:
            return ()
        raise ValueError(
            f"MCP provider '{provider_name}' must define command as a string or list.",
        )
    if not command_parts:
        if not required:
            return ()
        raise ValueError(f"MCP provider '{provider_name}' command cannot be empty.")
    return command_parts


def local_path_from_provider_config(config: ToolProviderConfigLike) -> str:
    name = provider_name(config)
    return required_text(
        lookup(config, "path", "spec_path", "package_ref"),
        field_name=f"local_root provider '{name}' path",
    )
