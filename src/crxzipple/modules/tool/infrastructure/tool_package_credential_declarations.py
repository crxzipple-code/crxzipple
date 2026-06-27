from __future__ import annotations

from pathlib import Path

from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.infrastructure.tool_package_credential_source_policy import (
    rejects_forbidden_credential_source,
)
from crxzipple.modules.tool.infrastructure.tool_package_manifest_parsers import (
    mapping_payload,
    optional_manifest_text,
)
from crxzipple.shared.access import (
    AccessConsumerRef,
    AccessCredentialKind,
    AccessCredentialRequirementDeclaration,
    AccessCredentialSlotRef,
    AccessCredentialTransport,
    AccessSetupFlowHint,
    AccessSetupFlowKind,
)


def parse_credential_requirement_declaration(
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
    provider = optional_manifest_text(raw_value.get("provider"))
    binding_id = optional_manifest_text(
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
            display_name=optional_manifest_text(
                slot_payload.get("display_name") or raw_value.get("display_name"),
            ),
            scopes=_string_tuple(
                slot_payload.get("scopes") or raw_value.get("scopes") or (),
            ),
            metadata=mapping_payload(slot_payload.get("metadata")),
        ),
        provider=provider,
        transport=_parse_access_credential_transport(
            raw_value.get("transport"),
            manifest_path=manifest_path,
        ),
        parameter_name=optional_manifest_text(raw_value.get("parameter_name")),
        setup_flow_hint=_parse_setup_flow_hint(
            raw_value.get("setup_flow_hint"),
            provider=provider,
            manifest_path=manifest_path,
        ),
        metadata=mapping_payload(raw_value.get("metadata")),
    )


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
        provider=optional_manifest_text(raw_value.get("provider")) or provider,
        authorization_url=optional_manifest_text(raw_value.get("authorization_url")),
        token_url=optional_manifest_text(raw_value.get("token_url")),
        device_code_url=optional_manifest_text(raw_value.get("device_code_url")),
        callback_url=optional_manifest_text(raw_value.get("callback_url")),
        metadata=mapping_payload(raw_value.get("metadata")),
    )


def _reject_direct_credential_requirement_binding(
    value: str,
    *,
    manifest_path: Path,
    slot: str,
) -> None:
    if rejects_forbidden_credential_source(value):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' credential requirement "
            f"slot '{slot}' must reference an Access credential binding id, "
            "not a direct credential source.",
        )


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


def _string_tuple(raw_value: object) -> tuple[str, ...]:
    if raw_value is None:
        return ()
    if isinstance(raw_value, str):
        return (raw_value.strip(),) if raw_value.strip() else ()
    if isinstance(raw_value, list | tuple):
        return tuple(str(item).strip() for item in raw_value if str(item).strip())
    return ()


__all__ = ["parse_credential_requirement_declaration"]
