from __future__ import annotations

from crxzipple.core.config_tool_provider_models import OpenApiCredentialBinding


def load_openapi_credential_bindings(
    raw: object,
    *,
    provider_name: str,
) -> tuple[OpenApiCredentialBinding, ...]:
    if raw in (None, {}):
        return ()
    if not isinstance(raw, dict):
        raise ValueError(
            f"OpenAPI provider '{provider_name}' credentials must decode to a JSON object.",
        )

    bindings: list[OpenApiCredentialBinding] = []
    for scheme_name, value in raw.items():
        bindings.append(
            _openapi_credential_binding(
                scheme_name,
                value,
                provider_name=provider_name,
            ),
        )
    return tuple(bindings)


def _openapi_credential_binding(
    scheme_name: object,
    value: object,
    *,
    provider_name: str,
) -> OpenApiCredentialBinding:
    normalized_scheme_name = str(scheme_name).strip()
    if not normalized_scheme_name:
        raise ValueError(
            f"OpenAPI provider '{provider_name}' credential bindings require non-empty scheme names.",
        )

    if isinstance(value, str):
        return _string_openapi_credential_binding(
            value,
            provider_name=provider_name,
            scheme_name=normalized_scheme_name,
        )
    if not isinstance(value, dict):
        raise ValueError(
            f"OpenAPI provider '{provider_name}' credential binding '{normalized_scheme_name}' must be a string or object.",
        )
    return _object_openapi_credential_binding(
        value,
        provider_name=provider_name,
        scheme_name=normalized_scheme_name,
    )


def _string_openapi_credential_binding(
    value: str,
    *,
    provider_name: str,
    scheme_name: str,
) -> OpenApiCredentialBinding:
    credential_binding_id = value.strip()
    if not credential_binding_id:
        raise ValueError(
            f"OpenAPI provider '{provider_name}' credential binding '{scheme_name}' cannot be empty.",
        )
    _reject_direct_openapi_credential_source(
        credential_binding_id,
        provider_name=provider_name,
        scheme_name=scheme_name,
        field_name="credential_binding_id",
    )
    return OpenApiCredentialBinding(
        scheme_name=scheme_name,
        credential_binding_id=credential_binding_id,
    )


def _object_openapi_credential_binding(
    value: dict[str, object],
    *,
    provider_name: str,
    scheme_name: str,
) -> OpenApiCredentialBinding:
    _reject_legacy_openapi_credential_fields(
        value,
        provider_name=provider_name,
        scheme_name=scheme_name,
    )
    credential_binding_id = _optional_mapping_text(value, "credential_binding_id")
    username_binding_id = _optional_mapping_text(value, "username_binding_id")
    password_binding_id = _optional_mapping_text(value, "password_binding_id")

    if credential_binding_id is None and (
        username_binding_id is None or password_binding_id is None
    ):
        raise ValueError(
            f"OpenAPI provider '{provider_name}' credential binding '{scheme_name}' must define credential_binding_id or username/password binding ids.",
        )

    return OpenApiCredentialBinding(
        scheme_name=scheme_name,
        credential_binding_id=credential_binding_id,
        username_binding_id=username_binding_id,
        password_binding_id=password_binding_id,
    )


def _optional_mapping_text(value: dict[str, object], *keys: str) -> str | None:
    for key in keys:
        raw = value.get(key)
        if raw is None:
            continue
        normalized = str(raw).strip()
        if normalized:
            return normalized
    return None


def _reject_legacy_openapi_credential_fields(
    value: dict[str, object],
    *,
    provider_name: str,
    scheme_name: str,
) -> None:
    legacy_fields = (
        "source",
        "username_source",
        "password_source",
        "username",
        "password",
        "credential_binding",
        "credential_binding_ref",
        "binding_id",
        "username_binding",
        "password_binding",
    )
    for field_name in legacy_fields:
        if value.get(field_name) is not None:
            raise ValueError(
                f"OpenAPI provider '{provider_name}' credential binding "
                f"'{scheme_name}' must use Access credential binding ids; "
                f"field '{field_name}' is no longer accepted.",
            )
    for field_name in (
        "credential_binding_id",
        "username_binding_id",
        "password_binding_id",
    ):
        candidate = value.get(field_name)
        if candidate is None:
            continue
        _reject_direct_openapi_credential_source(
            str(candidate),
            provider_name=provider_name,
            scheme_name=scheme_name,
            field_name=field_name,
        )


def _reject_direct_openapi_credential_source(
    value: str,
    *,
    provider_name: str,
    scheme_name: str,
    field_name: str,
) -> None:
    normalized = value.strip()
    if normalized.startswith(("env:", "file:", "codex_auth_json", "codex-cli")):
        raise ValueError(
            f"OpenAPI provider '{provider_name}' credential binding '{scheme_name}' "
            f"field '{field_name}' must reference an Access credential binding id, "
            "not a direct credential source.",
        )
