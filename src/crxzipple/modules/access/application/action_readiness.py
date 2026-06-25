from __future__ import annotations

from crxzipple.modules.access.application.action_contracts import JsonObject
from crxzipple.modules.access.application.repositories import (
    AccessConsumerBindingRecord,
    AccessCredentialBindingRecord,
)


def credential_requirement_readiness(
    *,
    consumer: AccessConsumerBindingRecord,
    credential: AccessCredentialBindingRecord | None,
    credential_binding_id: str | None,
    slot: str | None,
) -> JsonObject:
    expected_kind = _expected_kind_for_slot(consumer, slot) or _expected_kind_for_consumer(
        consumer,
    )
    if not consumer.enabled or consumer.status not in {"active", "unbound"}:
        return _readiness_payload(
            ready=False,
            status="disabled",
            reason="consumer binding is disabled",
            expected_kind=expected_kind,
            slot=slot,
            credential=credential,
            credential_binding_id=credential_binding_id,
        )
    if credential_binding_id is None or credential is None:
        return _readiness_payload(
            ready=False,
            status="missing",
            reason="credential binding is missing",
            expected_kind=expected_kind,
            slot=slot,
            credential=credential,
            credential_binding_id=credential_binding_id,
        )
    if credential.status != "active":
        return _readiness_payload(
            ready=False,
            status=credential.status,
            reason="credential binding is not active",
            expected_kind=expected_kind,
            slot=slot,
            credential=credential,
            credential_binding_id=credential_binding_id,
        )
    binding_kind = credential.binding_kind.strip().lower()
    if expected_kind is not None and binding_kind != expected_kind:
        return _readiness_payload(
            ready=False,
            status="credential_kind_mismatch",
            reason="credential binding kind does not match requirement",
            expected_kind=expected_kind,
            slot=slot,
            credential=credential,
            credential_binding_id=credential_binding_id,
        )
    source_kind = credential.source_kind.strip().lower()
    if source_kind == "oauth_account" and binding_kind not in {
        "oauth2_account",
        "openid_connect",
    }:
        return _readiness_payload(
            ready=False,
            status="credential_source_kind_mismatch",
            reason="oauth_account source can only satisfy OAuth or OpenID Connect credentials",
            expected_kind=expected_kind,
            slot=slot,
            credential=credential,
            credential_binding_id=credential_binding_id,
        )
    if binding_kind in {"oauth2_account", "openid_connect"} and source_kind != "oauth_account":
        return _readiness_payload(
            ready=False,
            status="credential_source_kind_mismatch",
            reason="OAuth credential bindings must use an oauth_account source",
            expected_kind=expected_kind,
            slot=slot,
            credential=credential,
            credential_binding_id=credential_binding_id,
        )
    return _readiness_payload(
        ready=True,
        status="ready",
        reason=None,
        expected_kind=expected_kind or binding_kind,
        slot=slot,
        credential=credential,
        credential_binding_id=credential_binding_id,
    )


def consumer_default_slot(consumer: AccessConsumerBindingRecord) -> str | None:
    if len(consumer.credential_bindings) == 1:
        return next(iter(consumer.credential_bindings))
    metadata_slot = consumer.metadata.get("slot")
    if isinstance(metadata_slot, str) and metadata_slot.strip():
        return metadata_slot.strip()
    return None


def _readiness_payload(
    *,
    ready: bool,
    status: str,
    reason: str | None,
    expected_kind: str | None,
    slot: str | None,
    credential: AccessCredentialBindingRecord | None,
    credential_binding_id: str | None,
) -> JsonObject:
    binding_kind = credential.binding_kind if credential is not None else None
    source_kind = credential.source_kind if credential is not None else None
    return {
        "ready": ready,
        "status": status,
        "reason": reason,
        "slot": slot,
        "expected_kind": expected_kind,
        "credential_binding_id": credential_binding_id,
        "binding_kind": binding_kind,
        "source_kind": source_kind,
        "checks": [
            {
                "code": "credential_binding_present",
                "ready": credential is not None,
                "target_id": credential_binding_id,
            },
            {
                "code": "credential_kind_matches",
                "ready": (
                    credential is not None
                    and (
                        expected_kind is None
                        or credential.binding_kind.strip().lower() == expected_kind
                    )
                ),
                "expected_kind": expected_kind,
                "binding_kind": binding_kind,
            },
            {
                "code": "credential_source_kind_compatible",
                "ready": (
                    credential is not None
                    and _source_kind_compatible(
                        binding_kind=credential.binding_kind,
                        source_kind=credential.source_kind,
                    )
                ),
                "binding_kind": binding_kind,
                "source_kind": source_kind,
            },
        ],
    }


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


def _source_kind_compatible(*, binding_kind: str, source_kind: str) -> bool:
    normalized_binding_kind = binding_kind.strip().lower()
    normalized_source_kind = source_kind.strip().lower()
    oauth_binding = normalized_binding_kind in {"oauth2_account", "openid_connect"}
    if normalized_source_kind == "oauth_account":
        return oauth_binding
    if oauth_binding:
        return normalized_source_kind == "oauth_account"
    return True


def _expected_kind_for_slot(
    consumer: AccessConsumerBindingRecord,
    slot: str | None,
) -> str | None:
    if not slot:
        return None
    for requirement_set in consumer.requirement_sets:
        for requirement in requirement_set:
            if _slot_from_requirement(requirement) == slot:
                return _expected_kind_from_requirement(requirement)
    return None


def _slot_from_requirement(value: str) -> str | None:
    normalized = value.strip()
    if "(" in normalized and normalized.endswith(")"):
        slot = normalized.rsplit("(", 1)[1][:-1].strip()
        if slot and not slot.startswith(("env:", "file:", "literal:", "inline:")):
            return slot
    return _expected_kind_from_requirement(normalized)


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
