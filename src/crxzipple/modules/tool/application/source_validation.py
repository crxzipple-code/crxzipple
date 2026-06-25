from __future__ import annotations

from collections.abc import Mapping

from crxzipple.modules.tool.application.catalog_models import (
    ToolSourceCatalogKind,
    ToolSourceCatalogRecord,
)
from crxzipple.modules.tool.domain.exceptions import ToolValidationError


def validate_owner_writable_source(source: ToolSourceCatalogRecord) -> None:
    config_source = str(source.config.get("source") or "").strip()
    if config_source == "bundled_tool_package":
        raise ToolValidationError(
            "Bundled tool package sources are managed by the Tool package loader.",
        )
    if source.kind not in {
        ToolSourceCatalogKind.OPENAPI,
        ToolSourceCatalogKind.MCP,
        ToolSourceCatalogKind.CLI,
    }:
        raise ToolValidationError(
            "Tool source create/update currently supports configured OpenAPI, MCP and CLI sources.",
        )
    if config_source != "configured_tool_provider":
        raise ToolValidationError(
            "Configured Tool source config.source must be 'configured_tool_provider'.",
        )
    package_kind = str(source.config.get("package_kind") or "").strip()
    if package_kind != source.kind.value:
        raise ToolValidationError(
            f"Configured Tool source config.package_kind must be '{source.kind.value}'.",
        )
    provider = source.config.get("provider")
    if not isinstance(provider, Mapping):
        raise ToolValidationError(
            "Configured Tool source config.provider must be an object.",
        )
    provider_name = str(provider.get("name") or "").strip()
    if not provider_name:
        raise ToolValidationError(
            "Configured Tool source config.provider.name is required.",
        )
    if source.kind is ToolSourceCatalogKind.OPENAPI:
        spec_location = str(provider.get("spec_location") or "").strip()
        if not spec_location:
            raise ToolValidationError(
                "Configured OpenAPI source config.provider.spec_location is required.",
            )
    if source.kind is ToolSourceCatalogKind.MCP:
        command = provider.get("command")
        if not isinstance(command, list | tuple) or not all(
            isinstance(item, str) and item.strip()
            for item in command
        ):
            raise ToolValidationError(
                "Configured MCP source config.provider.command must be a non-empty string list.",
            )
    if source.kind is ToolSourceCatalogKind.CLI:
        executable = str(provider.get("executable") or "").strip()
        command = provider.get("command")
        has_command = isinstance(command, list | tuple) and all(
            isinstance(item, str) and item.strip()
            for item in command
        )
        if not executable and not has_command:
            raise ToolValidationError(
                "Configured CLI source config.provider.executable or command is required.",
            )
        allowed_subcommands = provider.get("allowed_subcommands")
        if (
            not isinstance(allowed_subcommands, list | tuple)
            or not allowed_subcommands
            or not all(
                isinstance(item, str) and item.strip()
                for item in allowed_subcommands
            )
        ):
            raise ToolValidationError(
                "Configured CLI source config.provider.allowed_subcommands must be a non-empty string list.",
            )


__all__ = ["validate_owner_writable_source"]
