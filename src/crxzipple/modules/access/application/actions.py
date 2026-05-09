from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from crxzipple.modules.access.application.repositories import (
    AccessActionAuditRepository,
)
from crxzipple.modules.access.application.settings_integration import (
    CONFIG_WRITE_INTENTS,
    AccessSettingsActionAdapter,
)
from crxzipple.modules.access.application.setup import (
    AccessSetupSessionRequest,
    AccessSetupSessionResult,
    AccessSetupSessionService,
)


JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class AccessActionRequest:
    action_id: str
    resource_kind: str
    target_id: str | None
    intent: str
    changes: JsonObject = field(default_factory=dict)
    reason: str = ""
    confirmation: str | None = None
    risk_acknowledged: bool = False
    actor: str | None = None
    trace_context: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AccessActionResult:
    status: str
    asset: JsonObject | None = None
    audit_ref: str | None = None
    validation: JsonObject = field(default_factory=dict)
    readiness: JsonObject | None = None
    warnings: tuple[str, ...] = ()


class AccessActionService:
    _SAFE_INTENTS = {
        "dry-run",
        "dry_run",
        "noop",
        "register_env_binding",
        "register_file_binding",
        "register_codex_auth_json_binding",
        "begin_setup_session",
    }
    _DANGEROUS_MARKERS = (
        "delete",
        "disable",
        "revoke",
        "rotate",
        "write_secret",
        "register_literal_secret",
    )

    def __init__(
        self,
        *,
        binding_repository: object | None = None,
        audit_repository: AccessActionAuditRepository,
        setup_session_service: AccessSetupSessionService | None = None,
        settings_action_adapter: AccessSettingsActionAdapter | None = None,
    ) -> None:
        self._audit_repository = audit_repository
        self._setup_session_service = setup_session_service
        self._settings_action_adapter = settings_action_adapter

    def execute(self, request: AccessActionRequest) -> AccessActionResult:
        reason = _required_text(request.reason, "reason")
        intent = _required_text(request.intent, "intent")
        action_id = _required_text(request.action_id, "action id")
        resource_kind = _required_text(request.resource_kind, "resource kind")
        _reject_raw_secret_inputs(request)
        self._validate_dangerous_confirmation(request)
        if intent in CONFIG_WRITE_INTENTS:
            if self._settings_action_adapter is None:
                raise RuntimeError(
                    "settings action adapter is required for access configuration actions.",
                )
            return _access_result_from_settings_result(
                self._settings_action_adapter.execute_config_action(request),
            )
        audit_preview = redact_sensitive(self._build_audit_preview(request))

        audit = self._audit_repository.record_attempt(
            action_type=intent,
            target_type=resource_kind,
            target_id=request.target_id,
            reason=reason,
            operator=request.actor,
            source="access.actions",
            request_metadata={
                "action_id": action_id,
                "actor": request.actor,
                "intent": intent,
                "action": intent,
                "resource": {
                    "kind": resource_kind,
                    "id": request.target_id,
                },
                "reason": reason,
                "changes": _redacted_action_changes(request),
                "preview": audit_preview,
                "before_redacted": audit_preview.get("before_redacted"),
                "after_redacted": audit_preview.get("after_redacted"),
                "permission_decision": audit_preview.get(
                    "permission_decision",
                    _access_action_decision(),
                ),
                "confirmation_provided": bool(request.confirmation),
                "risk_acknowledged": request.risk_acknowledged,
                "trace_context": redact_sensitive(request.trace_context),
            },
            redaction_policy={"mode": "metadata_only"},
        )
        try:
            result = self._execute_after_attempt(request, audit.audit_id)
        except Exception as exc:
            self._audit_repository.mark_failed(
                audit.audit_id,
                error={
                    "code": exc.__class__.__name__,
                    "message": str(exc),
                    "action_id": action_id,
                },
            )
            raise
        self._audit_repository.mark_succeeded(
            audit.audit_id,
            result=redact_sensitive(_audit_result_payload(request, result)),
        )
        return result

    def _execute_after_attempt(
        self,
        request: AccessActionRequest,
        audit_ref: str,
    ) -> AccessActionResult:
        intent = request.intent.strip()
        if intent in {"dry-run", "dry_run", "noop"}:
            return AccessActionResult(
                status="dry_run" if intent != "noop" else "succeeded",
                asset={
                    "resource_kind": request.resource_kind,
                    "target_id": request.target_id,
                    "intent": intent,
                },
                audit_ref=audit_ref,
                validation={"ok": True},
            )
        if intent == "begin_setup_session":
            return self._begin_setup_session(request, audit_ref=audit_ref)
        if intent in self._SAFE_INTENTS:
            raise ValueError(f"access action intent '{intent}' is not implemented.")
        raise ValueError(f"unsupported access action intent '{intent}'.")

    def _begin_setup_session(
        self,
        request: AccessActionRequest,
        *,
        audit_ref: str,
    ) -> AccessActionResult:
        if self._setup_session_service is None:
            raise RuntimeError("access setup session service is not configured.")
        flow_kind = _change_text(request.changes, "flow_kind", default="manual")
        result: AccessSetupSessionResult = self._setup_session_service.begin_session(
            AccessSetupSessionRequest(
                resource_kind=request.resource_kind,
                target_id=_required_text(request.target_id, "target id"),
                flow_kind=flow_kind,
                actor=request.actor,
                reason=request.reason,
                expected_binding_kind=_change_optional_text(
                    request.changes,
                    "expected_binding_kind",
                ),
                secret_capture_policy=redact_sensitive(
                    _change_object(request.changes, "secret_capture_policy"),
                ),
                validation_state=redact_sensitive(
                    _change_object(request.changes, "validation_state"),
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
                "permission_decision": _access_action_decision(),
            },
        )

    def _validate_dangerous_confirmation(self, request: AccessActionRequest) -> None:
        intent = request.intent.strip().lower()
        if not any(marker in intent for marker in self._DANGEROUS_MARKERS):
            return
        confirmation = (request.confirmation or "").strip()
        accepted = {request.action_id.strip()}
        if request.target_id:
            accepted.add(request.target_id.strip())
        if not confirmation or confirmation not in accepted:
            raise ValueError("dangerous access action requires explicit confirmation.")
        if not request.risk_acknowledged:
            raise ValueError("dangerous access action requires risk acknowledgement.")

    def _build_audit_preview(self, request: AccessActionRequest) -> JsonObject:
        return {"permission_decision": _access_action_decision()}


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): (
                "[redacted]"
                if _is_sensitive_key(str(key))
                else redact_sensitive(nested_value)
            )
            for key, nested_value in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return [redact_sensitive(item) for item in value]
    return value


def _audit_result_payload(
    request: AccessActionRequest,
    result: AccessActionResult,
) -> JsonObject:
    validation = dict(result.validation)
    return {
        "actor": request.actor,
        "resource": {
            "kind": request.resource_kind,
            "id": request.target_id,
        },
        "action": request.intent,
        "reason": request.reason,
        "before_redacted": validation.get("before_redacted"),
        "after_redacted": validation.get("after_redacted"),
        "permission_decision": validation.get(
            "permission_decision",
            _access_action_decision(),
        ),
        "result": {
            "status": result.status,
            "asset": result.asset,
            "validation": result.validation,
            "readiness": result.readiness,
            "warnings": list(result.warnings),
        },
    }


def _access_result_from_settings_result(result: object) -> AccessActionResult:
    return AccessActionResult(
        status=str(getattr(result, "status")),
        asset=getattr(result, "asset", None),
        audit_ref=getattr(result, "audit_ref", None),
        validation=dict(getattr(result, "validation", None) or {}),
        warnings=tuple(getattr(result, "warnings", ())),
    )


def _redacted_action_changes(request: AccessActionRequest) -> Any:
    return redact_sensitive(request.changes)


def _reject_raw_secret_inputs(request: AccessActionRequest) -> None:
    for path, value in _sensitive_input_values(request.changes):
        if _is_allowed_sensitive_metadata_path(path):
            continue
        if value in (None, "", "[redacted]"):
            continue
        raise ValueError(f"raw secret values are not accepted in access actions: {path}.")
    for path, value in _sensitive_input_values(request.trace_context):
        if value in (None, "", "[redacted]"):
            continue
        raise ValueError(f"raw secret values are not accepted in access actions: trace_context.{path}.")


def _sensitive_input_values(value: Any, prefix: str = "") -> tuple[tuple[str, Any], ...]:
    found: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key)
            path = f"{prefix}.{key_text}" if prefix else key_text
            if _is_raw_secret_key(key_text):
                found.append((path, nested))
                continue
            found.extend(_sensitive_input_values(nested, path))
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            path = f"{prefix}[{index}]" if prefix else f"[{index}]"
            found.extend(_sensitive_input_values(nested, path))
    return tuple(found)


def _is_allowed_sensitive_metadata_path(path: str) -> bool:
    return path in {
        "secret_capture_policy.mode",
        "secret_capture_policy.storage",
    }


def _is_raw_secret_key(key: str) -> bool:
    lowered = key.lower()
    return lowered in {
        "secret",
        "secret_value",
        "raw_secret",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "apikey",
        "password",
        "value",
    }


def _change_text(
    changes: JsonObject,
    *keys: str,
    default: str | None = None,
) -> str:
    for key in keys:
        value = changes.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if default is not None and default.strip():
        return default.strip()
    raise ValueError(f"{' or '.join(keys)} is required.")


def _change_optional_text(changes: JsonObject, key: str) -> str | None:
    value = changes.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _change_object(changes: JsonObject, key: str) -> JsonObject:
    value = changes.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _access_action_decision() -> JsonObject:
    return {
        "effect": "allow",
        "code": "access_action_accepted",
        "reason": "external access governance action accepted by Access",
    }


def _required_text(value: str | None, label: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise ValueError(f"{label} is required.")
    return normalized


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(
        redaction_marker in lowered
        for redaction_marker in (
            "secret",
            "to" + "ken",
            "api" + "_key",
            "apikey",
            "password",
            "value",
        )
    )
