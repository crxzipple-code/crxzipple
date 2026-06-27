from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from typing import Any

from crxzipple.core.config import (
    McpProviderSettings,
    OpenApiCredentialBinding,
    OpenApiProviderSettings,
)
from crxzipple.modules.tool.application.catalog_models import (
    ToolSourceCatalogKind,
    ToolSourceCatalogRecord,
)
from crxzipple.modules.tool.domain.exceptions import ToolValidationError

CONFIGURED_PROVIDER_SOURCE_PREFIX = "configured"


def tool_source_records_from_configured_providers(
    *,
    openapi_providers: tuple[OpenApiProviderSettings, ...] = (),
    mcp_providers: tuple[McpProviderSettings, ...] = (),
) -> tuple[ToolSourceCatalogRecord, ...]:
    records: list[ToolSourceCatalogRecord] = []
    records.extend(_openapi_source_record(provider) for provider in openapi_providers)
    records.extend(_mcp_source_record(provider) for provider in mcp_providers)
    return tuple(records)


def configured_openapi_source_id(provider: OpenApiProviderSettings) -> str:
    return f"{CONFIGURED_PROVIDER_SOURCE_PREFIX}.openapi.{provider.name}"


def configured_mcp_source_id(provider: McpProviderSettings) -> str:
    return f"{CONFIGURED_PROVIDER_SOURCE_PREFIX}.mcp.{provider.name}"


def openapi_provider_settings_from_source(
    source: ToolSourceCatalogRecord,
) -> OpenApiProviderSettings:
    payload = provider_config(source)
    return OpenApiProviderSettings(
        name=required_text(payload.get("name"), source=source, field_name="name"),
        spec_location=required_text(
            payload.get("spec_location"),
            source=source,
            field_name="spec_location",
        ),
        base_url=optional_text(payload.get("base_url")),
        description=str(payload.get("description") or ""),
        timeout_seconds=positive_int(payload.get("timeout_seconds"), default=30),
        max_concurrency=optional_positive_int(payload.get("max_concurrency")),
        credential_bindings=tuple(
            credential_binding_from_payload(item)
            for item in payload.get("credential_bindings", ())
            if isinstance(item, Mapping)
        ),
        default_effect_ids=text_tuple(payload.get("default_effect_ids")),
        runtime_requirements=text_tuple(payload.get("runtime_requirements")),
    )


def mcp_provider_settings_from_source(
    source: ToolSourceCatalogRecord,
) -> McpProviderSettings:
    payload = provider_config(source)
    return McpProviderSettings(
        name=required_text(payload.get("name"), source=source, field_name="name"),
        command=text_tuple(payload.get("command")),
        transport=str(payload.get("transport") or "stdio"),
        endpoint_url=optional_text(payload.get("endpoint_url")),
        description=str(payload.get("description") or ""),
        timeout_seconds=positive_int(payload.get("timeout_seconds"), default=30),
        max_concurrency=optional_positive_int(payload.get("max_concurrency")),
        default_effect_ids=text_tuple(payload.get("default_effect_ids")),
        runtime_requirements=text_tuple(payload.get("runtime_requirements")),
    )


def provider_config(source: ToolSourceCatalogRecord) -> Mapping[str, Any]:
    provider = source.config.get("provider")
    if not isinstance(provider, Mapping):
        raise ToolValidationError(
            f"Configured provider source '{source.source_id}' config.provider must be an object.",
        )
    return provider


def credential_binding_from_payload(
    payload: Mapping[str, Any],
) -> OpenApiCredentialBinding:
    return OpenApiCredentialBinding(
        scheme_name=required_text(
            payload.get("scheme_name"),
            source=None,
            field_name="scheme_name",
        ),
        credential_binding_id=optional_text(payload.get("credential_binding_id")),
        username_binding_id=optional_text(payload.get("username_binding_id")),
        password_binding_id=optional_text(payload.get("password_binding_id")),
    )


def provider_payload(provider: OpenApiProviderSettings | McpProviderSettings) -> dict[str, Any]:
    return stable_payload(provider)


def stable_payload(value: Any) -> Any:
    if is_dataclass(value):
        return {
            field.name: stable_payload(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key): stable_payload(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, tuple | list):
        return [stable_payload(item) for item in value]
    return value


def required_text(
    value: object,
    *,
    source: ToolSourceCatalogRecord | None,
    field_name: str,
) -> str:
    text = str(value or "").strip()
    if not text:
        prefix = (
            f"Configured provider source '{source.source_id}' "
            if source is not None
            else ""
        )
        raise ToolValidationError(f"{prefix}{field_name} cannot be empty.")
    return text


def optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def text_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(
        dict.fromkeys(
            str(item).strip()
            for item in value
            if str(item).strip()
        ),
    )


def positive_int(value: object, *, default: int) -> int:
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        resolved = default
    return max(resolved, 1)


def optional_positive_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return None
    return max(resolved, 1)


def _openapi_source_record(
    provider: OpenApiProviderSettings,
) -> ToolSourceCatalogRecord:
    return ToolSourceCatalogRecord(
        source_id=configured_openapi_source_id(provider),
        kind=ToolSourceCatalogKind.OPENAPI,
        display_name=provider.description or provider.name,
        description=(
            provider.description
            or f"Configured OpenAPI tool provider '{provider.name}'."
        ),
        config={
            "source": "configured_tool_provider",
            "package_kind": "openapi",
            "provider": provider_payload(provider),
        },
        runtime_requirements=provider.runtime_requirements,
    )


def _mcp_source_record(provider: McpProviderSettings) -> ToolSourceCatalogRecord:
    return ToolSourceCatalogRecord(
        source_id=configured_mcp_source_id(provider),
        kind=ToolSourceCatalogKind.MCP,
        display_name=provider.description or provider.name,
        description=provider.description or f"Configured MCP tool provider '{provider.name}'.",
        config={
            "source": "configured_tool_provider",
            "package_kind": "mcp",
            "provider": provider_payload(provider),
        },
        runtime_requirements=provider.runtime_requirements,
    )
