from __future__ import annotations

from typing import Any, Mapping

from crxzipple.modules.access.application.repositories import (
    AccessConsumerBindingRecord,
    AccessCredentialBindingRecord,
)
from crxzipple.modules.access.application.settings_action_contracts import (
    AccessSettingsActionRequest,
    AccessSettingsActionResult,
)
from crxzipple.modules.access.application.settings_payloads import (
    _change_bool,
    _change_optional_text,
    _change_text,
    _payload_requirement_sets,
    _safe_binding_id_part,
)


def _consumer_binding_result(
    result: object,
    consumer: AccessConsumerBindingRecord,
    *,
    validation_metadata: Mapping[str, Any],
) -> AccessSettingsActionResult:
    validation = result.validation.to_payload()
    validation["metadata"] = {
        **dict(validation.get("metadata") or {}),
        **dict(validation_metadata),
    }
    return AccessSettingsActionResult(
        status=result.status,
        asset={
            "resource_kind": "consumer_binding",
            "binding_id": consumer.binding_id,
            "consumer_module": consumer.consumer_module,
            "consumer_kind": consumer.consumer_kind,
            "consumer_id": consumer.consumer_id,
            "credential_binding_id": consumer.credential_binding_id,
            "credential_bindings": dict(consumer.credential_bindings),
            "status": consumer.status,
        },
        audit_ref=result.audit_ref,
        validation=validation,
        warnings=tuple(result.warnings),
    )


def _consumer_binding_id_from_request(request: AccessSettingsActionRequest) -> str:
    target_id = request.target_id.strip() if request.target_id else None
    fallback = target_id or _default_consumer_binding_id(request.changes)
    return _change_text(
        request.changes,
        "consumer_binding_id",
        default=fallback,
    )


def _default_consumer_binding_id(changes: Mapping[str, Any]) -> str | None:
    consumer_module = _change_optional_text(changes, "consumer_module", "module")
    consumer_kind = _change_optional_text(changes, "consumer_kind")
    consumer_id = _change_optional_text(changes, "consumer_id")
    slot = _change_optional_text(changes, "slot")
    if not consumer_module or not consumer_id:
        return None
    parts = ["consumer", consumer_module, consumer_kind or "module", consumer_id]
    if slot:
        parts.append(slot)
    return ":".join(_safe_binding_id_part(part) for part in parts)


def _consumer_binding_from_request(
    request: AccessSettingsActionRequest,
    *,
    existing: AccessConsumerBindingRecord | None,
    credential_binding_id: str | None,
    credential: AccessCredentialBindingRecord | None,
    unbind: bool,
) -> AccessConsumerBindingRecord:
    consumer_binding_id = _consumer_binding_id_from_request(request)
    consumer_module = _consumer_change_text(
        request.changes,
        existing,
        "consumer_module",
        "module",
        attr="consumer_module",
    )
    consumer_kind = _consumer_change_text(
        request.changes,
        existing,
        "consumer_kind",
        attr="consumer_kind",
        default="module",
    )
    consumer_id = _consumer_change_text(
        request.changes,
        existing,
        "consumer_id",
        attr="consumer_id",
    )
    expected_kind = _change_optional_text(
        request.changes,
        "expected_kind",
        "credential_kind",
    )
    if expected_kind is None and existing is not None:
        expected_kind = _expected_kind_for_consumer(existing)
    if expected_kind is None and credential is not None:
        expected_kind = credential.binding_kind
    slot = _change_optional_text(request.changes, "slot")
    if slot is None and expected_kind is not None:
        slot = expected_kind
    if slot is None and unbind and existing is not None:
        if len(existing.credential_bindings) == 1:
            slot = next(iter(existing.credential_bindings))
        elif "slot" in existing.metadata:
            slot = str(existing.metadata["slot"])
    requirement_sets = _change_requirement_sets(
        request.changes,
        existing=existing,
        provider=_change_optional_text(request.changes, "provider"),
        expected_kind=expected_kind,
        slot=slot,
    )
    metadata = dict(existing.metadata if existing is not None else {})
    metadata.update(
        {
            "action_id": request.action_id,
            "reason": request.reason,
            "trace_context": dict(request.trace_context),
        },
    )
    if slot is not None:
        metadata["slot"] = slot
    if expected_kind is not None:
        metadata["expected_kind"] = expected_kind
    provider = _change_optional_text(request.changes, "provider")
    if provider is not None:
        metadata["provider"] = provider
    status = _change_text(
        request.changes,
        "status",
        default=existing.status if existing is not None else "active",
    )
    return AccessConsumerBindingRecord(
        binding_id=consumer_binding_id,
        consumer_module=consumer_module,
        consumer_kind=consumer_kind,
        consumer_id=consumer_id,
        display_name=_consumer_optional_text(
            request.changes,
            existing,
            "display_name",
            attr="display_name",
        ),
        enabled=_change_bool(
            request.changes,
            "enabled",
            default=existing.enabled if existing is not None else True,
        ),
        asset_id=(
            _change_optional_text(request.changes, "asset_id")
            or (existing.asset_id if existing is not None else None)
            or (credential.asset_id if credential is not None else None)
        ),
        credential_binding_id=_primary_credential_binding_id(
            _updated_slot_bindings(
                existing=existing,
                slot=slot,
                credential_binding_id=credential_binding_id,
                unbind=unbind,
            ),
        ),
        credential_bindings=_updated_slot_bindings(
            existing=existing,
            slot=slot,
            credential_binding_id=credential_binding_id,
            unbind=unbind,
        ),
        requirement_sets=requirement_sets,
        status=status,
        redaction_policy=(
            dict(existing.redaction_policy) if existing is not None else {}
        ),
        metadata=metadata,
    )


def _consumer_change_text(
    changes: Mapping[str, Any],
    existing: AccessConsumerBindingRecord | None,
    *keys: str,
    attr: str,
    default: str | None = None,
) -> str:
    existing_value = getattr(existing, attr) if existing is not None else None
    return _change_text(
        changes,
        *keys,
        default=str(existing_value or default) if existing_value or default else None,
    )


def _consumer_optional_text(
    changes: Mapping[str, Any],
    existing: AccessConsumerBindingRecord | None,
    key: str,
    *,
    attr: str,
) -> str | None:
    return _change_optional_text(changes, key) or (
        str(getattr(existing, attr))
        if existing is not None and getattr(existing, attr)
        else None
    )


def _updated_slot_bindings(
    *,
    existing: AccessConsumerBindingRecord | None,
    slot: str | None,
    credential_binding_id: str | None,
    unbind: bool,
) -> dict[str, str]:
    slot_bindings = dict(existing.credential_bindings if existing is not None else {})
    if not slot_bindings and existing is not None and existing.credential_binding_id:
        existing_slot = str(existing.metadata.get("slot") or "").strip()
        existing_expected_kind = _expected_kind_for_consumer(existing)
        slot_bindings[existing_slot or existing_expected_kind or "credential"] = (
            existing.credential_binding_id
        )
    if slot is None:
        if credential_binding_id is not None:
            slot_bindings["credential"] = credential_binding_id
        return slot_bindings
    slot_key = slot.strip()
    if not slot_key:
        return slot_bindings
    if unbind:
        slot_bindings.pop(slot_key, None)
        return slot_bindings
    if credential_binding_id is not None:
        slot_bindings[slot_key] = credential_binding_id
    return slot_bindings


def _primary_credential_binding_id(slot_bindings: Mapping[str, str]) -> str | None:
    values = tuple(dict.fromkeys(slot_bindings.values()))
    if len(values) == 1:
        return values[0]
    return None


def _slot_from_request_or_consumer(
    request: AccessSettingsActionRequest,
    consumer: AccessConsumerBindingRecord,
) -> str | None:
    slot = _change_optional_text(request.changes, "slot")
    if slot is not None:
        return slot
    metadata_slot = consumer.metadata.get("slot")
    if isinstance(metadata_slot, str) and metadata_slot.strip():
        return metadata_slot.strip()
    if len(consumer.credential_bindings) == 1:
        return next(iter(consumer.credential_bindings))
    return None


def _change_requirement_sets(
    changes: Mapping[str, Any],
    *,
    existing: AccessConsumerBindingRecord | None,
    provider: str | None,
    expected_kind: str | None,
    slot: str | None,
) -> tuple[tuple[str, ...], ...]:
    if "requirement_sets" in changes:
        parsed = _payload_requirement_sets(changes.get("requirement_sets"))
        if parsed:
            return parsed
    requirement = _change_optional_text(changes, "requirement")
    if requirement is not None:
        return ((requirement,),)
    if existing is not None and existing.requirement_sets:
        return existing.requirement_sets
    if expected_kind is None:
        raise ValueError("expected_kind is required when requirement_sets are omitted.")
    return (
        (_requirement_ref(provider=provider, expected_kind=expected_kind, slot=slot),),
    )


def _requirement_ref(
    *,
    provider: str | None,
    expected_kind: str,
    slot: str | None,
) -> str:
    kind = expected_kind.strip().lower()
    suffix = f"({slot.strip()})" if slot and slot.strip() else ""
    if provider and provider.strip():
        return f"{provider.strip()}:{kind}{suffix}"
    return f"{kind}{suffix}"


def _expected_kind_for_slot(
    consumer: AccessConsumerBindingRecord,
    slot: str | None,
) -> str | None:
    if not slot:
        return None
    for requirement_set in consumer.requirement_sets:
        for requirement in requirement_set:
            parsed_slot = _slot_from_requirement(requirement)
            if parsed_slot == slot:
                return _expected_kind_from_requirement(requirement)
    return None


def _slot_from_requirement(value: str) -> str | None:
    normalized = value.strip()
    if "(" in normalized and normalized.endswith(")"):
        slot = normalized.rsplit("(", 1)[1][:-1].strip()
        if slot and not slot.startswith(("env:", "file:", "literal:", "inline:")):
            return slot
    expected_kind = _expected_kind_from_requirement(normalized)
    return expected_kind


def _expected_kind_for_consumer(
    consumer: AccessConsumerBindingRecord,
) -> str | None:
    metadata_value = consumer.metadata.get("expected_kind")
    if isinstance(metadata_value, str) and metadata_value.strip():
        return metadata_value.strip().lower()
    for requirement_set in consumer.requirement_sets:
        for requirement in requirement_set:
            expected_kind = _expected_kind_from_requirement(requirement)
            if expected_kind is not None:
                return expected_kind
    return None


def _expected_kind_from_requirement(value: str) -> str | None:
    normalized = value.strip().lower()
    candidates = {
        "api_key": ("api_key", "apikey", "x-api-key"),
        "bearer_token": ("bearer", "bearer_token", "access_token"),
        "basic": ("basic", "username", "password"),
        "oauth2_account": ("oauth2", "oauth"),
        "openid_connect": ("openid", "oidc"),
        "app_secret": ("app_secret", "client_secret"),
        "webhook_secret": ("webhook_secret", "webhook"),
        "certificate": ("certificate", "cert", "pem"),
    }
    for kind, markers in candidates.items():
        if any(marker in normalized for marker in markers):
            return kind
    return None
