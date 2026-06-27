from __future__ import annotations

from pathlib import Path

from crxzipple.core.config import OpenApiCredentialBinding
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.infrastructure.tool_package_credential_source_policy import (
    rejects_forbidden_credential_source,
)
from crxzipple.modules.tool.infrastructure.tool_package_manifest_parsers import (
    optional_manifest_text,
)


def parse_openapi_credential_bindings(
    raw_credentials: object,
    manifest_path: Path,
) -> tuple[OpenApiCredentialBinding, ...]:
    if raw_credentials in (None, {}):
        return ()
    if not isinstance(raw_credentials, dict):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field 'credentials' must be a mapping.",
        )
    bindings: list[OpenApiCredentialBinding] = []
    for raw_scheme_name, raw_binding in raw_credentials.items():
        scheme_name = str(raw_scheme_name).strip()
        if not scheme_name:
            raise ToolValidationError(
                f"Tool namespace manifest '{manifest_path}' credentials require non-empty scheme names.",
            )
        bindings.append(
            _parse_openapi_credential_binding(
                raw_binding,
                manifest_path,
                scheme_name=scheme_name,
            ),
        )
    return tuple(bindings)


def _parse_openapi_credential_binding(
    raw_binding: object,
    manifest_path: Path,
    *,
    scheme_name: str,
) -> OpenApiCredentialBinding:
    if isinstance(raw_binding, str):
        value = raw_binding.strip()
        if not value:
            raise ToolValidationError(
                f"Tool namespace manifest '{manifest_path}' credential binding '{scheme_name}' cannot be empty.",
            )
        _reject_direct_openapi_credential_source(
            value,
            manifest_path=manifest_path,
            scheme_name=scheme_name,
            field_name="credential_binding_id",
        )
        return OpenApiCredentialBinding(
            scheme_name=scheme_name,
            credential_binding_id=value,
        )
    if not isinstance(raw_binding, dict):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' credential binding '{scheme_name}' must be a string or mapping.",
        )
    _reject_legacy_openapi_credential_fields(
        raw_binding,
        manifest_path=manifest_path,
        scheme_name=scheme_name,
    )
    binding = OpenApiCredentialBinding(
        scheme_name=scheme_name,
        credential_binding_id=_optional_mapping_text(
            raw_binding,
            "credential_binding_id",
        ),
        username_binding_id=_optional_mapping_text(
            raw_binding,
            "username_binding_id",
        ),
        password_binding_id=_optional_mapping_text(
            raw_binding,
            "password_binding_id",
        ),
    )
    _ensure_openapi_credential_binding(
        binding,
        manifest_path=manifest_path,
        scheme_name=scheme_name,
    )
    return binding


def _reject_legacy_openapi_credential_fields(
    value: dict[str, object],
    *,
    manifest_path: Path,
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
            raise ToolValidationError(
                f"Tool namespace manifest '{manifest_path}' credential binding "
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
            manifest_path=manifest_path,
            scheme_name=scheme_name,
            field_name=field_name,
        )


def _reject_direct_openapi_credential_source(
    value: str,
    *,
    manifest_path: Path,
    scheme_name: str,
    field_name: str,
) -> None:
    if rejects_forbidden_credential_source(value):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' credential binding "
            f"'{scheme_name}' field '{field_name}' must reference an Access "
            "credential binding id, not a direct credential source.",
        )


def _ensure_openapi_credential_binding(
    binding: OpenApiCredentialBinding,
    *,
    manifest_path: Path,
    scheme_name: str,
) -> None:
    if binding.credential_binding_id is not None:
        return
    if binding.username_binding_id is not None and binding.password_binding_id is not None:
        return
    raise ToolValidationError(
        f"Tool namespace manifest '{manifest_path}' credential binding "
        f"'{scheme_name}' must define credential_binding_id or username/password "
        "binding ids.",
    )


def _optional_mapping_text(value: dict[str, object], *keys: str) -> str | None:
    for key in keys:
        raw = value.get(key)
        if raw is None:
            continue
        normalized = optional_manifest_text(raw)
        if normalized:
            return normalized
    return None


__all__ = ["parse_openapi_credential_bindings"]
