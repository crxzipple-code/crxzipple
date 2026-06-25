from __future__ import annotations

from pathlib import Path
from typing import Any

from crxzipple.core.config import OpenApiCredentialBinding, OpenApiProviderSettings
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.shared.access import (
    AccessConsumerRef,
    AccessCredentialKind,
    AccessCredentialRequirementDeclaration,
    AccessCredentialRequirementSet,
    AccessCredentialSlotRef,
    AccessCredentialTransport,
    AccessSetupFlowHint,
    AccessSetupFlowKind,
)


_FORBIDDEN_CREDENTIAL_SOURCE_PREFIXES = (
    "env:",
    "file:",
    "codex_auth_json",
    "codex-cli",
    "auth_ref",
)


def load_openapi_provider_from_manifest(
    payload: dict[str, Any],
    manifest_path: Path,
) -> OpenApiProviderSettings:
    spec_raw = str(payload.get("spec", "")).strip()
    if not spec_raw:
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' kind openapi must define spec.",
        )
    spec_path = (manifest_path.parent / spec_raw).resolve()
    if not spec_path.is_file():
        raise ToolValidationError(
            f"OpenAPI spec '{spec_raw}' referenced by '{manifest_path}' was not found.",
        )
    return OpenApiProviderSettings(
        name=_required_string(payload, "namespace", manifest_path),
        spec_location=str(spec_path),
        base_url=(
            str(payload["base_url"]).strip()
            if payload.get("base_url") is not None
            else None
        ),
        description=str(payload.get("description", "")).strip(),
        timeout_seconds=max(int(payload.get("timeout_seconds", 30)), 1),
        max_concurrency=_parse_optional_positive_int(
            payload.get("max_concurrency"),
            field_name="max_concurrency",
            manifest_path=manifest_path,
        ),
        credential_bindings=_parse_openapi_credentials(
            payload.get("credentials", {}),
            manifest_path,
        ),
        default_effect_ids=_parse_string_list(
            payload.get("default_effect_ids", []),
            "default_effect_ids",
            manifest_path,
        ),
        runtime_requirements=tuple(
            _parse_string_list(
                payload.get("runtime_requirements", []),
                "runtime_requirements",
                manifest_path,
            ),
        ),
    )


def parse_credential_requirement_sets(
    raw_values: object,
    manifest_path: Path,
    *,
    tool_id: str,
    runtime_key: str | None,
) -> tuple[AccessCredentialRequirementSet, ...]:
    if raw_values in (None, []):
        return ()
    if not isinstance(raw_values, list):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field 'credential_requirements' must be a list.",
        )
    consumer = AccessConsumerRef(
        consumer_id=tool_id,
        module="tool",
        component="local_package",
        runtime_ref=runtime_key,
        metadata={"manifest_path": str(manifest_path)},
    )
    requirement_sets: list[AccessCredentialRequirementSet] = []
    for index, raw_set in enumerate(raw_values):
        if not isinstance(raw_set, dict):
            raise ToolValidationError(
                f"Tool namespace manifest '{manifest_path}' credential_requirements[{index}] must be a mapping.",
            )
        raw_requirements = raw_set.get("requirements")
        if raw_requirements is None:
            raw_requirements = [raw_set]
        if not isinstance(raw_requirements, list):
            raise ToolValidationError(
                f"Tool namespace manifest '{manifest_path}' credential_requirements[{index}].requirements must be a list.",
            )
        declarations = tuple(
            _parse_credential_requirement(
                raw_requirement,
                manifest_path,
                consumer=consumer,
                set_index=index,
                requirement_index=requirement_index,
            )
            for requirement_index, raw_requirement in enumerate(raw_requirements)
        )
        requirement_sets.append(
            AccessCredentialRequirementSet(
                requirement_set_id=str(
                    raw_set.get("requirement_set_id")
                    or raw_set.get("id")
                    or f"{tool_id}.credentials.{index}",
                ),
                consumer=consumer,
                requirements=declarations,
                alternative=bool(raw_set.get("alternative", False)),
                metadata=_mapping_payload(raw_set.get("metadata")),
            ),
        )
    return tuple(requirement_sets)


def _parse_openapi_credentials(
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
            bindings.append(
                OpenApiCredentialBinding(
                    scheme_name=scheme_name,
                    credential_binding_id=value,
                ),
            )
            continue
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
        bindings.append(binding)
    return tuple(bindings)


def _parse_credential_requirement(
    raw_value: object,
    manifest_path: Path,
    *,
    consumer: AccessConsumerRef,
    set_index: int,
    requirement_index: int,
) -> AccessCredentialRequirementDeclaration:
    if not isinstance(raw_value, dict):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' credential requirement entries must be mappings.",
        )
    raw_slot = raw_value.get("slot")
    slot_payload = raw_slot if isinstance(raw_slot, dict) else {}
    slot = _required_text_value(
        slot_payload.get("slot") if slot_payload else raw_slot,
        field_name="slot",
        manifest_path=manifest_path,
    )
    expected_kind = _parse_access_credential_kind(
        slot_payload.get("expected_kind")
        or raw_value.get("expected_kind")
        or raw_value.get("kind"),
        manifest_path=manifest_path,
    )
    provider = _optional_text(raw_value.get("provider"))
    binding_id = _optional_text(
        slot_payload.get("binding_id") or raw_value.get("binding_id"),
    )
    if binding_id is not None:
        _reject_direct_credential_requirement_binding(
            binding_id,
            manifest_path=manifest_path,
            slot=slot,
        )
    return AccessCredentialRequirementDeclaration(
        requirement_id=str(
            raw_value.get("requirement_id")
            or raw_value.get("id")
            or f"{consumer.consumer_id}.{slot}.{set_index}.{requirement_index}",
        ),
        consumer=consumer,
        slot=AccessCredentialSlotRef(
            slot=slot,
            expected_kind=expected_kind,
            binding_id=binding_id,
            required=bool(slot_payload.get("required", raw_value.get("required", True))),
            display_name=_optional_text(
                slot_payload.get("display_name") or raw_value.get("display_name"),
            ),
            scopes=_string_tuple(
                slot_payload.get("scopes") or raw_value.get("scopes") or (),
            ),
            metadata=_mapping_payload(slot_payload.get("metadata")),
        ),
        provider=provider,
        transport=_parse_access_credential_transport(
            raw_value.get("transport"),
            manifest_path=manifest_path,
        ),
        parameter_name=_optional_text(raw_value.get("parameter_name")),
        setup_flow_hint=_parse_setup_flow_hint(
            raw_value.get("setup_flow_hint"),
            provider=provider,
            manifest_path=manifest_path,
        ),
        metadata=_mapping_payload(raw_value.get("metadata")),
    )


def _parse_optional_positive_int(
    raw_value: object,
    *,
    field_name: str,
    manifest_path: Path,
) -> int | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, str) and not raw_value.strip():
        return None
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field '{field_name}' must be a positive integer.",
        ) from exc
    if parsed < 1:
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field '{field_name}' must be a positive integer.",
        )
    return parsed


def _parse_access_credential_kind(
    raw_value: object,
    *,
    manifest_path: Path,
) -> AccessCredentialKind:
    normalized = _required_text_value(
        raw_value,
        field_name="expected_kind",
        manifest_path=manifest_path,
    )
    try:
        return AccessCredentialKind(normalized)
    except ValueError as exc:
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' uses unsupported credential kind '{normalized}'.",
        ) from exc


def _parse_access_credential_transport(
    raw_value: object,
    *,
    manifest_path: Path,
) -> AccessCredentialTransport:
    normalized = str(raw_value or AccessCredentialTransport.RUNTIME_CONTEXT).strip()
    try:
        return AccessCredentialTransport(normalized)
    except ValueError as exc:
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' uses unsupported credential transport '{normalized}'.",
        ) from exc


def _parse_setup_flow_hint(
    raw_value: object,
    *,
    provider: str | None,
    manifest_path: Path,
) -> AccessSetupFlowHint:
    if raw_value in (None, {}):
        return AccessSetupFlowHint(
            flow_kind=AccessSetupFlowKind.MANUAL,
            provider=provider,
        )
    if not isinstance(raw_value, dict):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' setup_flow_hint must be a mapping.",
        )
    raw_flow_kind = raw_value.get("flow_kind") or AccessSetupFlowKind.MANUAL
    try:
        flow_kind = AccessSetupFlowKind(str(raw_flow_kind).strip())
    except ValueError as exc:
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' uses unsupported setup flow '{raw_flow_kind}'.",
        ) from exc
    return AccessSetupFlowHint(
        flow_kind=flow_kind,
        provider=_optional_text(raw_value.get("provider")) or provider,
        authorization_url=_optional_text(raw_value.get("authorization_url")),
        token_url=_optional_text(raw_value.get("token_url")),
        device_code_url=_optional_text(raw_value.get("device_code_url")),
        callback_url=_optional_text(raw_value.get("callback_url")),
        metadata=_mapping_payload(raw_value.get("metadata")),
    )


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
    normalized = value.strip()
    if normalized.startswith(_FORBIDDEN_CREDENTIAL_SOURCE_PREFIXES):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' credential binding "
            f"'{scheme_name}' field '{field_name}' must reference an Access "
            "credential binding id, not a direct credential source.",
        )


def _reject_direct_credential_requirement_binding(
    value: str,
    *,
    manifest_path: Path,
    slot: str,
) -> None:
    normalized = value.strip()
    if normalized.startswith(_FORBIDDEN_CREDENTIAL_SOURCE_PREFIXES):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' credential requirement "
            f"slot '{slot}' must reference an Access credential binding id, "
            "not a direct credential source.",
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


def _required_string(
    payload: dict[str, Any],
    field_name: str,
    manifest_path: Path,
) -> str:
    value = str(payload.get(field_name, "")).strip()
    if not value:
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' missing required field '{field_name}'.",
        )
    return value


def _required_text_value(
    raw_value: object,
    *,
    field_name: str,
    manifest_path: Path,
) -> str:
    normalized = str(raw_value or "").strip()
    if not normalized:
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' credential requirement must define '{field_name}'.",
        )
    return normalized


def _optional_mapping_text(value: dict[str, object], *keys: str) -> str | None:
    for key in keys:
        raw = value.get(key)
        if raw is None:
            continue
        normalized = str(raw).strip()
        if normalized:
            return normalized
    return None


def _optional_text(raw_value: object) -> str | None:
    if raw_value is None:
        return None
    normalized = str(raw_value).strip()
    return normalized or None


def _parse_string_list(
    raw_values: object,
    field_name: str,
    manifest_path: Path,
) -> tuple[str, ...]:
    if not isinstance(raw_values, list):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field '{field_name}' must be a list.",
        )
    return tuple(
        str(item).strip()
        for item in raw_values
        if str(item).strip()
    )


def _string_tuple(raw_value: object) -> tuple[str, ...]:
    if raw_value is None:
        return ()
    if isinstance(raw_value, str):
        return (raw_value.strip(),) if raw_value.strip() else ()
    if isinstance(raw_value, list | tuple):
        return tuple(str(item).strip() for item in raw_value if str(item).strip())
    return ()


def _mapping_payload(raw_value: object) -> dict[str, object]:
    return dict(raw_value) if isinstance(raw_value, dict) else {}
