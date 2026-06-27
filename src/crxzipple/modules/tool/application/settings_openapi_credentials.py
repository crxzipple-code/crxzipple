from __future__ import annotations

from typing import Mapping

from crxzipple.core.config import OpenApiCredentialBinding
from crxzipple.modules.tool.application.settings_config_values import (
    ToolProviderConfigLike,
    lookup,
    optional_text,
    required_text,
)


_FORBIDDEN_OPENAPI_CREDENTIAL_SOURCE_PREFIXES = (
    "env:",
    "file:",
    "codex_auth_json",
    "codex-cli",
    "auth_ref",
)


def openapi_credential_bindings_from_config(
    config: ToolProviderConfigLike,
    *,
    provider_name: str,
) -> tuple[OpenApiCredentialBinding, ...]:
    raw = lookup(config, "credential_bindings", "credentials")
    if raw in (None, {}):
        for field_name in ("credential_binding", "credential_binding_ref"):
            if lookup(config, field_name) is not None:
                raise ValueError(
                    f"OpenAPI provider '{provider_name}' must use credential_bindings; "
                    f"field '{field_name}' is no longer accepted.",
                )
        return ()
    if isinstance(raw, list | tuple):
        return _openapi_list_credential_bindings(raw, provider_name=provider_name)
    if isinstance(raw, Mapping):
        return _openapi_mapping_credential_bindings(raw, provider_name=provider_name)
    raise ValueError(
        f"OpenAPI provider '{provider_name}' credential_bindings must be a mapping.",
    )


def _openapi_list_credential_bindings(
    raw: list[object] | tuple[object, ...],
    *,
    provider_name: str,
) -> tuple[OpenApiCredentialBinding, ...]:
    bindings: list[OpenApiCredentialBinding] = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise ValueError(
                f"OpenAPI provider '{provider_name}' credential_bindings[{index}] must be an object.",
            )
        scheme_name = required_text(
            item.get("scheme_name") or item.get("name"),
            field_name=(
                f"OpenAPI provider '{provider_name}' "
                f"credential_bindings[{index}].scheme_name"
            ),
        )
        reject_legacy_credential_fields(
            item,
            provider_name=provider_name,
            scheme_name=scheme_name,
        )
        binding = OpenApiCredentialBinding(
            scheme_name=scheme_name,
            credential_binding_id=optional_text(item.get("credential_binding_id")),
            username_binding_id=optional_text(item.get("username_binding_id")),
            password_binding_id=optional_text(item.get("password_binding_id")),
        )
        validate_openapi_credential_binding(
            binding,
            raw=item,
            provider_name=provider_name,
            scheme_name=scheme_name,
        )
        ensure_openapi_credential_binding(
            binding,
            provider_name=provider_name,
            scheme_name=scheme_name,
        )
        bindings.append(binding)
    return tuple(bindings)


def _openapi_mapping_credential_bindings(
    raw: Mapping[object, object],
    *,
    provider_name: str,
) -> tuple[OpenApiCredentialBinding, ...]:
    bindings: list[OpenApiCredentialBinding] = []
    for scheme_name, value in raw.items():
        normalized_scheme_name = required_text(
            scheme_name,
            field_name=f"OpenAPI provider '{provider_name}' credential scheme",
        )
        if isinstance(value, str):
            binding_id = required_text(
                value,
                field_name=(
                    f"OpenAPI provider '{provider_name}' credential "
                    f"'{normalized_scheme_name}'"
                ),
            )
            reject_direct_credential_source(
                binding_id,
                provider_name=provider_name,
                scheme_name=normalized_scheme_name,
                field_name="credential_binding_id",
            )
            bindings.append(
                OpenApiCredentialBinding(
                    scheme_name=normalized_scheme_name,
                    credential_binding_id=binding_id,
                ),
            )
            continue
        if not isinstance(value, Mapping):
            raise ValueError(
                f"OpenAPI provider '{provider_name}' credential "
                f"'{normalized_scheme_name}' must be a string or mapping.",
            )
        reject_legacy_credential_fields(
            value,
            provider_name=provider_name,
            scheme_name=normalized_scheme_name,
        )
        binding = OpenApiCredentialBinding(
            scheme_name=normalized_scheme_name,
            credential_binding_id=optional_text(value.get("credential_binding_id")),
            username_binding_id=optional_text(value.get("username_binding_id")),
            password_binding_id=optional_text(value.get("password_binding_id")),
        )
        ensure_openapi_credential_binding(
            binding,
            provider_name=provider_name,
            scheme_name=normalized_scheme_name,
        )
        validate_openapi_credential_binding(
            binding,
            raw=value,
            provider_name=provider_name,
            scheme_name=normalized_scheme_name,
        )
        bindings.append(binding)
    return tuple(bindings)


def validate_openapi_credential_binding(
    binding: OpenApiCredentialBinding,
    *,
    raw: Mapping[str, object],
    provider_name: str,
    scheme_name: str,
) -> None:
    reject_legacy_credential_fields(
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
        reject_direct_credential_source(
            value,
            provider_name=provider_name,
            scheme_name=scheme_name,
            field_name=field_name,
        )


def ensure_openapi_credential_binding(
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


def reject_legacy_credential_fields(
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
        "auth_ref",
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


def reject_direct_credential_source(
    value: str,
    *,
    provider_name: str,
    scheme_name: str,
    field_name: str,
) -> None:
    normalized = value.strip()
    if normalized.startswith(_FORBIDDEN_OPENAPI_CREDENTIAL_SOURCE_PREFIXES):
        raise ValueError(
            f"OpenAPI provider '{provider_name}' credential '{scheme_name}' "
            f"field '{field_name}' must reference an Access credential binding id, "
            "not a direct credential source.",
        )
