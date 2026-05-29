from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from crxzipple.core.config import (
    McpProviderSettings,
    OpenApiCredentialBinding,
    OpenApiProviderSettings,
)
from crxzipple.shared.settings import (
    ToolProviderConfig,
    ToolRootConfig,
)


ToolProviderConfigLike = ToolProviderConfig | Mapping[str, Any]
ToolRootConfigLike = ToolRootConfig | Mapping[str, Any]

_forbidden_openapi_credential_source_prefixes = (
    "env:",  # forbidden direct source
    "file:",  # forbidden direct source
    "codex_auth_json",  # forbidden direct source
    "codex-cli",  # forbidden direct source
    "auth_ref",  # forbidden legacy credential field
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
        runtime_requirements=_string_tuple(
            _lookup_configured_value(config, "runtime_requirements"),
        ),
    )


def mcp_provider_settings_from_config(
    config: ToolProviderConfigLike,
) -> McpProviderSettings:
    provider_name = _provider_name(config)
    transport = str(_lookup_configured_value(config, "transport") or "stdio").strip().lower()
    return McpProviderSettings(
        name=provider_name,
        command=_command_parts_from_config(
            config,
            provider_name=provider_name,
            required=transport == "stdio",
        ),
        transport=transport,
        endpoint_url=_optional_text(
            _lookup_configured_value(config, "endpoint_url", "url"),
        ),
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
        for field_name in ("credential_binding", "credential_binding_ref"):
            if _lookup(config, field_name) is not None:
                raise ValueError(
                    f"OpenAPI provider '{provider_name}' must use credential_bindings; "
                    f"field '{field_name}' is no longer accepted.",
                )
        return ()
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
            _reject_legacy_credential_fields(
                item,
                provider_name=provider_name,
                scheme_name=scheme_name,
            )
            bindings.append(
                OpenApiCredentialBinding(
                    scheme_name=scheme_name,
                    credential_binding_id=_optional_text(item.get("credential_binding_id")),
                    username_binding_id=_optional_text(item.get("username_binding_id")),
                    password_binding_id=_optional_text(item.get("password_binding_id")),
                ),
            )
            _validate_openapi_credential_binding(
                bindings[-1],
                raw=item,
                provider_name=provider_name,
                scheme_name=scheme_name,
            )
            _ensure_openapi_credential_binding(
                bindings[-1],
                provider_name=provider_name,
                scheme_name=scheme_name,
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
            credential_binding_id = _required_text(
                value,
                field_name=(
                    f"OpenAPI provider '{provider_name}' credential "
                    f"'{normalized_scheme_name}'"
                ),
            )
            _reject_direct_credential_source(
                credential_binding_id,
                provider_name=provider_name,
                scheme_name=normalized_scheme_name,
                field_name="credential_binding_id",
            )
            bindings.append(
                OpenApiCredentialBinding(
                    scheme_name=normalized_scheme_name,
                    credential_binding_id=credential_binding_id,
                ),
            )
            continue
        if not isinstance(value, Mapping):
            raise ValueError(
                f"OpenAPI provider '{provider_name}' credential "
                f"'{normalized_scheme_name}' must be a string or mapping.",
            )
        _reject_legacy_credential_fields(
            value,
            provider_name=provider_name,
            scheme_name=normalized_scheme_name,
        )
        credential_binding_id = _optional_text(value.get("credential_binding_id"))
        username_binding_id = _optional_text(value.get("username_binding_id"))
        password_binding_id = _optional_text(value.get("password_binding_id"))
        if (
            credential_binding_id is None
            and (
                username_binding_id is None
                or password_binding_id is None
            )
        ):
            raise ValueError(
                f"OpenAPI provider '{provider_name}' credential "
                f"'{normalized_scheme_name}' must define credential_binding_id or username/password binding ids.",
            )
        binding = OpenApiCredentialBinding(
            scheme_name=normalized_scheme_name,
            credential_binding_id=credential_binding_id,
            username_binding_id=username_binding_id,
            password_binding_id=password_binding_id,
        )
        _validate_openapi_credential_binding(
            binding,
            raw=value,
            provider_name=provider_name,
            scheme_name=normalized_scheme_name,
        )
        bindings.append(binding)
    return tuple(bindings)


def _validate_openapi_credential_binding(
    binding: OpenApiCredentialBinding,
    *,
    raw: Mapping[str, object],
    provider_name: str,
    scheme_name: str,
) -> None:
    _reject_legacy_credential_fields(
        raw,
        provider_name=provider_name,
        scheme_name=scheme_name,
    )
    for field_name, value in (
        ("credential_binding_id", binding.credential_binding_id),
        ("username_binding_id", binding.username_binding_id),
        ("password_binding_id", binding.password_binding_id),
    ):
        if value is None:
            continue
        _reject_direct_credential_source(
            value,
            provider_name=provider_name,
            scheme_name=scheme_name,
            field_name=field_name,
        )


def _ensure_openapi_credential_binding(
    binding: OpenApiCredentialBinding,
    *,
    provider_name: str,
    scheme_name: str,
) -> None:
    if binding.credential_binding_id is not None:
        return
    if binding.username_binding_id is not None and binding.password_binding_id is not None:
        return
    raise ValueError(
        f"OpenAPI provider '{provider_name}' credential '{scheme_name}' must define "
        "credential_binding_id or username/password binding ids.",
    )


def _reject_legacy_credential_fields(
    value: Mapping[str, object],
    *,
    provider_name: str,
    scheme_name: str,
) -> None:
    for field_name in (
        "source",
        "username_source",
        "password_source",
        "username",
        "password",
        "auth_ref",  # forbidden legacy credential field
        "credential_binding",
        "credential_binding_ref",
        "binding_id",
        "username_binding",
        "password_binding",
    ):
        if value.get(field_name) is not None:
            raise ValueError(
                f"OpenAPI provider '{provider_name}' credential "
                f"'{scheme_name}' must use Access credential binding ids; "
                f"field '{field_name}' is no longer accepted.",
            )


def _reject_direct_credential_source(
    value: str,
    *,
    provider_name: str,
    scheme_name: str,
    field_name: str,
) -> None:
    normalized = value.strip()
    if normalized.startswith(_forbidden_openapi_credential_source_prefixes):
        raise ValueError(
            f"OpenAPI provider '{provider_name}' credential '{scheme_name}' "
            f"field '{field_name}' must reference an Access credential binding id, "
            "not a direct credential source.",
        )


def _command_parts_from_config(
    config: ToolProviderConfigLike,
    *,
    provider_name: str,
    required: bool = True,
) -> tuple[str, ...]:
    command = _lookup(config, "command")
    args = _lookup(config, "args")
    if isinstance(command, str):
        command_parts = (command, *(_string_tuple(args) if args is not None else ()))
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
