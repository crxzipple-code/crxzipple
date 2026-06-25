from __future__ import annotations

from typing import Any, Mapping

from crxzipple.modules.access.application.repositories import (
    AccessAssetRecord,
    AccessConsumerBindingRecord,
    AccessCredentialBindingRecord,
)
from crxzipple.modules.access.application.settings_action_contracts import JsonObject
from crxzipple.modules.access.application.settings_payloads import (
    _payload_object,
    _payload_optional_text,
    _payload_requirement_sets,
    _payload_slot_bindings,
    _payload_string_tuple,
    _payload_text,
)


def _asset_record(payload: Mapping[str, Any]) -> AccessAssetRecord:
    asset_id = _payload_text(payload, "asset_id", "id")
    return AccessAssetRecord(
        asset_id=asset_id,
        asset_kind=_payload_text(payload, "asset_kind", "kind", default="secret_asset"),
        display_name=_payload_text(payload, "display_name", "name", default=asset_id),
        governance_scope=_payload_text(
            payload, "governance_scope", "scope", default="global"
        ),
        status=_payload_text(payload, "status", default="active"),
        secret_policy=_payload_object(payload, "secret_policy"),
        storage_key=_payload_optional_text(payload, "storage_key"),
        consumer_modules=_payload_string_tuple(payload, "consumer_modules"),
        readiness_policy=_payload_object(payload, "readiness_policy"),
        rotation_policy=_payload_object(payload, "rotation_policy"),
        audit_required=bool(payload.get("audit_required", True)),
        export_policy=_payload_object(payload, "export_policy"),
        degraded_reason=_payload_optional_text(payload, "degraded_reason"),
        redaction_policy=_payload_object(payload, "redaction_policy"),
        metadata=_payload_object(payload, "metadata"),
    )


def _credential_binding_record(
    payload: Mapping[str, Any],
) -> AccessCredentialBindingRecord:
    source_kind = _payload_text(payload, "source_kind", default="env")
    source_ref = _payload_text(payload, "source_ref")
    return AccessCredentialBindingRecord(
        binding_id=_payload_text(payload, "binding_id", "id"),
        asset_id=_payload_optional_text(payload, "asset_id"),
        binding_kind=_payload_text(payload, "binding_kind", default="api_key"),
        source_kind=source_kind,
        source_ref=source_ref,
        masked_preview=_payload_optional_text(payload, "masked_preview"),
        status=_payload_text(payload, "status", default="active"),
        redaction_policy=_payload_object(payload, "redaction_policy"),
        metadata=_payload_object(payload, "metadata"),
    )


def _consumer_binding_record(payload: Mapping[str, Any]) -> AccessConsumerBindingRecord:
    consumer_module = _payload_text(payload, "consumer_module", "module")
    consumer_id = _payload_text(payload, "consumer_id", default=consumer_module)
    return AccessConsumerBindingRecord(
        binding_id=_payload_text(payload, "binding_id", "id"),
        consumer_module=consumer_module,
        consumer_kind=_payload_text(payload, "consumer_kind", default="module"),
        consumer_id=consumer_id,
        display_name=_payload_optional_text(payload, "display_name"),
        enabled=bool(payload.get("enabled", True)),
        asset_id=_payload_optional_text(payload, "asset_id"),
        credential_binding_id=_payload_optional_text(payload, "credential_binding_id"),
        credential_bindings=_payload_slot_bindings(payload.get("credential_bindings")),
        requirement_sets=_payload_requirement_sets(payload.get("requirement_sets")),
        status=_payload_text(payload, "status", default="active"),
        redaction_policy=_payload_object(payload, "redaction_policy"),
        metadata=_payload_object(payload, "metadata"),
    )


def _credential_binding_payload(record: AccessCredentialBindingRecord) -> JsonObject:
    return {
        "binding_id": record.binding_id,
        "asset_id": record.asset_id,
        "binding_kind": record.binding_kind,
        "source_kind": record.source_kind,
        "source_ref": record.source_ref,
        "masked_preview": record.masked_preview,
        "status": record.status,
        "redaction_policy": dict(record.redaction_policy),
        "metadata": dict(record.metadata),
    }


def _consumer_binding_payload(record: AccessConsumerBindingRecord) -> JsonObject:
    return {
        "binding_id": record.binding_id,
        "consumer_module": record.consumer_module,
        "consumer_kind": record.consumer_kind,
        "consumer_id": record.consumer_id,
        "display_name": record.display_name,
        "enabled": record.enabled,
        "asset_id": record.asset_id,
        "credential_binding_id": record.credential_binding_id,
        "credential_bindings": dict(record.credential_bindings),
        "requirement_sets": [list(items) for items in record.requirement_sets],
        "status": record.status,
        "redaction_policy": dict(record.redaction_policy),
        "metadata": dict(record.metadata),
    }
