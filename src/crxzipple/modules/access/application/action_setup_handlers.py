from __future__ import annotations

from crxzipple.modules.access.application.action_changes import (
    change_object,
    change_optional_text,
    change_text,
    required_text,
)
from crxzipple.modules.access.application.action_contracts import (
    AccessActionRequest,
    AccessActionResult,
)
from crxzipple.modules.access.application.action_payloads import access_action_decision
from crxzipple.modules.access.application.action_readiness import (
    consumer_default_slot,
    credential_requirement_readiness,
)
from crxzipple.modules.access.application.action_redaction import redact_sensitive
from crxzipple.modules.access.application.settings_integration import (
    AccessSettingsActionAdapter,
)
from crxzipple.modules.access.application.setup import (
    AccessSetupSessionRequest,
    AccessSetupSessionResult,
    AccessSetupSessionService,
)


def begin_setup_session(
    request: AccessActionRequest,
    *,
    audit_ref: str,
    setup_session_service: AccessSetupSessionService | None,
) -> AccessActionResult:
    if setup_session_service is None:
        raise RuntimeError("access setup session service is not configured.")
    flow_kind = change_text(request.changes, "flow_kind", default="manual")
    result: AccessSetupSessionResult = setup_session_service.begin_session(
        AccessSetupSessionRequest(
            resource_kind=request.resource_kind,
            target_id=required_text(request.target_id, "target id"),
            flow_kind=flow_kind,
            actor=request.actor,
            reason=request.reason,
            expected_binding_kind=change_optional_text(
                request.changes,
                "expected_binding_kind",
            ),
            secret_capture_policy=redact_sensitive(
                change_object(request.changes, "secret_capture_policy"),
            ),
            validation_state=redact_sensitive(
                change_object(request.changes, "validation_state"),
            ),
            trace_context=redact_sensitive(request.trace_context),
        ),
    )
    return AccessActionResult(
        status="succeeded",
        asset={
            "resource_kind": "setup_session",
            "session_id": result.session_id,
            "status": result.status,
            "flow_kind": result.flow_kind,
            "target": result.target,
            "setup_audit_ref": result.audit_ref,
        },
        audit_ref=audit_ref,
        validation={
            "ok": True,
            "before_redacted": None,
            "after_redacted": {
                "resource_kind": "setup_session",
                "session_id": result.session_id,
                "status": result.status,
                "flow_kind": result.flow_kind,
                "target": result.target,
            },
            "permission_decision": access_action_decision(),
        },
    )


def verify_credential_requirement(
    request: AccessActionRequest,
    *,
    audit_ref: str,
    settings_action_adapter: AccessSettingsActionAdapter | None,
) -> AccessActionResult:
    if settings_action_adapter is None:
        raise RuntimeError(
            "settings action adapter is required for access requirement verification.",
        )
    view = settings_action_adapter.config_view()
    consumer_binding_id = change_text(
        request.changes,
        "consumer_binding_id",
        default=request.target_id,
    )
    consumer = view.get_consumer_binding(consumer_binding_id)
    if consumer is None:
        raise ValueError(
            f"consumer binding '{consumer_binding_id}' was not found.",
        )
    slot = change_optional_text(request.changes, "slot") or consumer_default_slot(
        consumer,
    )
    if slot is None and len(consumer.credential_bindings) > 1:
        raise ValueError("slot is required to verify a multi-slot consumer binding.")
    credential_binding_id = (
        change_optional_text(request.changes, "credential_binding_id")
        or (
            consumer.credential_bindings.get(slot)
            if slot is not None
            else None
        )
        or consumer.credential_binding_id
    )
    credential = (
        view.get_credential_binding(credential_binding_id)
        if credential_binding_id
        else None
    )
    readiness = credential_requirement_readiness(
        consumer=consumer,
        credential=credential,
        credential_binding_id=credential_binding_id,
        slot=slot,
    )
    return AccessActionResult(
        status="succeeded" if readiness["ready"] else "blocked",
        asset={
            "resource_kind": "consumer_binding",
            "binding_id": consumer.binding_id,
            "consumer_module": consumer.consumer_module,
            "consumer_kind": consumer.consumer_kind,
            "consumer_id": consumer.consumer_id,
            "slot": slot,
            "credential_binding_id": credential_binding_id,
        },
        audit_ref=audit_ref,
        validation={
            "ok": bool(readiness["ready"]),
            "before_redacted": None,
            "after_redacted": {
                "consumer_binding_id": consumer.binding_id,
                "slot": slot,
                "credential_binding_id": credential_binding_id,
                "status": readiness["status"],
            },
            "permission_decision": access_action_decision(),
        },
        readiness=readiness,
    )
