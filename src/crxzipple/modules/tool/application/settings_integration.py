from __future__ import annotations

from dataclasses import dataclass, replace
from fnmatch import fnmatchcase
from typing import Any, Iterable, Mapping

from crxzipple.core.config import (
    McpProviderSettings,
    OpenApiCredentialBinding,
    OpenApiProviderSettings,
)
from crxzipple.modules.tool.application.discovery import ToolDiscoveryGateway
from crxzipple.modules.tool.application.specifications import ToolSpec
from crxzipple.modules.tool.domain import Tool, ToolSourceKind
from crxzipple.shared.settings import (
    ToolEnablementConfig,
    ToolProviderConfig,
    ToolRootConfig,
)


ToolProviderConfigLike = ToolProviderConfig | Mapping[str, Any]
ToolRootConfigLike = ToolRootConfig | Mapping[str, Any]
ToolEnablementConfigLike = ToolEnablementConfig | Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ToolSettingsBootstrapConfig:
    openapi_providers: tuple[OpenApiProviderSettings, ...] = ()
    mcp_providers: tuple[McpProviderSettings, ...] = ()
    local_paths: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ToolEnablementTarget:
    tool_id: str
    name: str
    enabled: bool
    source_kind: ToolSourceKind
    provider_id: str | None = None
    tags: tuple[str, ...] = ()


class ToolEnablementService:
    def __init__(
        self,
        configs: Iterable[ToolEnablementConfigLike] = (),
    ) -> None:
        self._configs = tuple(_tool_enablement_config(config) for config in configs)

    @property
    def configs(self) -> tuple[ToolEnablementConfig, ...]:
        return self._configs

    def enabled_for_target(self, target: ToolEnablementTarget) -> bool:
        enabled = target.enabled
        for config in self._configs:
            if _tool_enablement_matches(config, target):
                enabled = config.enabled
        return enabled

    def apply_to_spec(self, spec: ToolSpec) -> ToolSpec:
        enabled = self.enabled_for_target(
            ToolEnablementTarget(
                tool_id=spec.id,
                name=spec.name,
                enabled=spec.enabled,
                source_kind=spec.source_kind,
                provider_id=spec.provider_name,
                tags=spec.tags,
            ),
        )
        if enabled == spec.enabled:
            return spec
        return replace(spec, enabled=enabled)

    def apply_to_tool(self, tool: Tool, *, provider_id: str | None = None) -> Tool:
        enabled = self.enabled_for_target(
            ToolEnablementTarget(
                tool_id=tool.id,
                name=tool.name,
                enabled=tool.enabled,
                source_kind=tool.source_kind,
                provider_id=provider_id,
                tags=tool.tags,
            ),
        )
        if enabled == tool.enabled:
            return tool
        return replace(tool, enabled=enabled)


class ToolEnablementDiscoveryGateway:
    def __init__(
        self,
        gateway: ToolDiscoveryGateway,
        enablement: ToolEnablementService,
    ) -> None:
        self._gateway = gateway
        self._enablement = enablement

    def list_providers(self):
        return self._gateway.list_providers()

    def discover(self, *, provider_name: str | None = None) -> list[ToolSpec]:
        return [
            self._enablement.apply_to_spec(spec)
            for spec in self._gateway.discover(provider_name=provider_name)
        ]


class ToolEnablementRuntimeGateway:
    def __init__(
        self,
        gateway: object,
        enablement: ToolEnablementService,
    ) -> None:
        self._gateway = gateway
        self._enablement = enablement

    def list_local_tools(self) -> list[Tool]:
        return [
            self._enablement.apply_to_tool(tool)
            for tool in self._gateway.list_local_tools()
        ]

    async def execute(
        self,
        tool: Tool,
        target: object,
        arguments: dict[str, Any],
        execution_context: object | None = None,
    ) -> Any:
        return await self._gateway.execute(
            tool,
            target,
            arguments,
            execution_context=execution_context,
        )


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
        if not include_disabled and not _enabled(provider):
            continue
        provider_kind = _required_text(
            _lookup(provider, "provider_kind", "kind"),
            field_name="provider_kind",
        ).lower()
        if provider_kind == "openapi":
            openapi_providers.append(openapi_provider_settings_from_config(provider))
        elif provider_kind == "mcp":
            mcp_providers.append(mcp_provider_settings_from_config(provider))
        elif provider_kind == "local_root":
            local_paths.append(_local_path_from_provider_config(provider))
        else:
            provider_id = _provider_name(provider)
            raise ValueError(
                f"Tool provider '{provider_id}' provider_kind must be one of: "
                "openapi, mcp, local_root.",
            )

    for root in roots:
        if not include_disabled and not _enabled(root):
            continue
        local_paths.append(_required_text(_lookup(root, "path"), field_name="path"))

    return ToolSettingsBootstrapConfig(
        openapi_providers=tuple(openapi_providers),
        mcp_providers=tuple(mcp_providers),
        local_paths=_dedupe_text(local_paths),
    )


def openapi_provider_settings_from_config(
    config: ToolProviderConfigLike,
) -> OpenApiProviderSettings:
    provider_name = _provider_name(config)
    spec_location = _required_text(
        _lookup(config, "spec_location", "spec_path", "spec_url", "spec"),
        field_name=f"OpenAPI provider '{provider_name}' spec_location/spec_path",
    )
    return OpenApiProviderSettings(
        name=provider_name,
        spec_location=spec_location,
        base_url=_optional_text(_lookup(config, "base_url")),
        description=_optional_text(
            _lookup(config, "description", "display_name"),
        )
        or "",
        timeout_seconds=_positive_int(
            _lookup_configured_value(config, "timeout_seconds"),
            default=30,
            field_name=f"OpenAPI provider '{provider_name}' timeout_seconds",
        ),
        max_concurrency=_optional_positive_int(
            _lookup_configured_value(config, "max_concurrency"),
            field_name=f"OpenAPI provider '{provider_name}' max_concurrency",
        ),
        credential_bindings=_openapi_credential_bindings_from_config(
            config,
            provider_name=provider_name,
        ),
        default_effect_ids=_string_tuple(
            _lookup_configured_value(config, "default_effect_ids"),
        ),
    )


def mcp_provider_settings_from_config(
    config: ToolProviderConfigLike,
) -> McpProviderSettings:
    provider_name = _provider_name(config)
    return McpProviderSettings(
        name=provider_name,
        command=_command_parts_from_config(config, provider_name=provider_name),
        description=_optional_text(
            _lookup(config, "description", "display_name"),
        )
        or "",
        timeout_seconds=_positive_int(
            _lookup_configured_value(config, "timeout_seconds"),
            default=30,
            field_name=f"MCP provider '{provider_name}' timeout_seconds",
        ),
        max_concurrency=_optional_positive_int(
            _lookup_configured_value(config, "max_concurrency"),
            field_name=f"MCP provider '{provider_name}' max_concurrency",
        ),
        default_effect_ids=_string_tuple(
            _lookup_configured_value(config, "default_effect_ids"),
        ),
    )


def _openapi_credential_bindings_from_config(
    config: ToolProviderConfigLike,
    *,
    provider_name: str,
) -> tuple[OpenApiCredentialBinding, ...]:
    raw = _lookup(config, "credential_bindings", "credentials")
    if raw in (None, {}):
        credential_binding = _optional_text(
            _lookup(config, "credential_binding", "credential_binding_ref"),
        )
        if credential_binding is None:
            return ()
        return (
            OpenApiCredentialBinding(
                scheme_name="default",
                source=credential_binding,
            ),
        )
    if isinstance(raw, list | tuple):
        bindings: list[OpenApiCredentialBinding] = []
        for index, item in enumerate(raw):
            if not isinstance(item, Mapping):
                raise ValueError(
                    f"OpenAPI provider '{provider_name}' credential_bindings[{index}] must be an object.",
                )
            scheme_name = _required_text(
                item.get("scheme_name") or item.get("name"),
                field_name=(
                    f"OpenAPI provider '{provider_name}' "
                    f"credential_bindings[{index}].scheme_name"
                ),
            )
            bindings.append(
                OpenApiCredentialBinding(
                    scheme_name=scheme_name,
                    source=_optional_text(item.get("source")),
                    username_source=_optional_text(
                        item.get("username_source") or item.get("username"),
                    ),
                    password_source=_optional_text(
                        item.get("password_source") or item.get("password"),
                    ),
                ),
            )
        return tuple(bindings)
    if not isinstance(raw, Mapping):
        raise ValueError(
            f"OpenAPI provider '{provider_name}' credential_bindings must be a mapping.",
        )

    bindings: list[OpenApiCredentialBinding] = []
    for scheme_name, value in raw.items():
        normalized_scheme_name = _required_text(
            scheme_name,
            field_name=f"OpenAPI provider '{provider_name}' credential scheme",
        )
        if isinstance(value, str):
            bindings.append(
                OpenApiCredentialBinding(
                    scheme_name=normalized_scheme_name,
                    source=_required_text(
                        value,
                        field_name=(
                            f"OpenAPI provider '{provider_name}' credential "
                            f"'{normalized_scheme_name}'"
                        ),
                    ),
                ),
            )
            continue
        if not isinstance(value, Mapping):
            raise ValueError(
                f"OpenAPI provider '{provider_name}' credential "
                f"'{normalized_scheme_name}' must be a string or mapping.",
            )
        source = _optional_text(value.get("source"))
        username_source = _optional_text(
            value.get("username_source") or value.get("username"),
        )
        password_source = _optional_text(
            value.get("password_source") or value.get("password"),
        )
        if source is None and (username_source is None or password_source is None):
            raise ValueError(
                f"OpenAPI provider '{provider_name}' credential "
                f"'{normalized_scheme_name}' must define source or username/password.",
            )
        bindings.append(
            OpenApiCredentialBinding(
                scheme_name=normalized_scheme_name,
                source=source,
                username_source=username_source,
                password_source=password_source,
            ),
        )
    return tuple(bindings)


def _command_parts_from_config(
    config: ToolProviderConfigLike,
    *,
    provider_name: str,
) -> tuple[str, ...]:
    command = _lookup(config, "command")
    args = _lookup(config, "args")
    if isinstance(command, str):
        command_parts = (command, *(_string_tuple(args) if args is not None else ()))
    elif isinstance(command, Iterable):
        command_parts = tuple(str(part).strip() for part in command if str(part).strip())
    else:
        raise ValueError(
            f"MCP provider '{provider_name}' must define command as a string or list.",
        )
    if not command_parts:
        raise ValueError(f"MCP provider '{provider_name}' command cannot be empty.")
    return command_parts


def _local_path_from_provider_config(config: ToolProviderConfigLike) -> str:
    provider_name = _provider_name(config)
    return _required_text(
        _lookup(config, "path", "spec_path", "package_ref"),
        field_name=f"local_root provider '{provider_name}' path",
    )


def _provider_name(config: ToolProviderConfigLike) -> str:
    return _required_text(
        _lookup(config, "provider_id", "id", "name"),
        field_name="provider_id",
    )


def _enabled(config: ToolProviderConfigLike | ToolRootConfigLike) -> bool:
    raw = _lookup(config, "enabled")
    if raw is None:
        return True
    if isinstance(raw, str):
        return raw.strip().lower() not in {"0", "false", "no", "off"}
    return bool(raw)


def _lookup(config: object, *keys: str) -> object:
    if isinstance(config, Mapping):
        for key in keys:
            if key in config:
                return config[key]
        for bucket_name in ("discovery", "metadata"):
            bucket = config.get(bucket_name)
            if isinstance(bucket, Mapping):
                for key in keys:
                    if key in bucket:
                        return bucket[key]
        return None

    for key in keys:
        if hasattr(config, key):
            value = getattr(config, key)
            if value is not None and not (isinstance(value, str) and not value.strip()):
                return value
    for bucket_name in ("discovery", "metadata"):
        bucket = getattr(config, bucket_name, None)
        if isinstance(bucket, Mapping):
            for key in keys:
                if key in bucket:
                    return bucket[key]
    return None


def _lookup_configured_value(config: object, *keys: str) -> object:
    for bucket_name in ("discovery", "metadata"):
        bucket = config.get(bucket_name) if isinstance(config, Mapping) else getattr(config, bucket_name, None)
        if isinstance(bucket, Mapping):
            for key in keys:
                if key in bucket:
                    return bucket[key]
    return _lookup(config, *keys)


def _required_text(value: object, *, field_name: str) -> str:
    text = _optional_text(value)
    if text is None:
        raise ValueError(f"{field_name} cannot be empty.")
    return text


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _positive_int(value: object, *, default: int, field_name: str) -> int:
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a positive integer.") from exc
    if parsed < 1:
        raise ValueError(f"{field_name} must be a positive integer.")
    return parsed


def _optional_positive_int(value: object, *, field_name: str) -> int | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return _positive_int(value, default=1, field_name=field_name)


def _string_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, Iterable):
        return tuple(str(item).strip() for item in value if str(item).strip())
    raise ValueError("Expected a string or iterable of strings.")


def _dedupe_text(values: Iterable[str]) -> tuple[str, ...]:
    resolved: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        resolved.append(normalized)
    return tuple(resolved)


def _tool_enablement_config(config: ToolEnablementConfigLike) -> ToolEnablementConfig:
    if isinstance(config, ToolEnablementConfig):
        return config
    return ToolEnablementConfig.from_payload(config)


def _tool_enablement_matches(
    config: ToolEnablementConfig,
    target: ToolEnablementTarget,
) -> bool:
    scope = config.scope.strip().lower()
    if scope in {"*", "all", "global"}:
        scope_matches = True
    elif scope in {"tool", "tools"}:
        scope_matches = True
    elif scope in {"provider", "provider_id"}:
        scope_matches = (
            config.provider_id is not None and config.provider_id == target.provider_id
        )
    elif scope in {"local", "local_discovery"}:
        scope_matches = target.source_kind is ToolSourceKind.LOCAL_DISCOVERY
    elif scope in {"remote", "remote_registry"}:
        scope_matches = target.source_kind is ToolSourceKind.REMOTE_REGISTRY
    else:
        scope_matches = scope == target.source_kind.value
    if not scope_matches:
        return False

    if config.source_kind is not None and config.source_kind != target.source_kind.value:
        return False
    if config.provider_id is not None and config.provider_id != target.provider_id:
        return False
    if config.tool_id is not None and config.tool_id != target.tool_id:
        return False
    if config.pattern is not None and not (
        fnmatchcase(target.tool_id, config.pattern)
        or fnmatchcase(target.name, config.pattern)
    ):
        return False
    if (
        config.tool_id is None
        and config.pattern is None
        and config.provider_id is None
        and config.source_kind is None
        and scope in {"tool", "tools"}
    ):
        return False
    return True
