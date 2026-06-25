from __future__ import annotations

from crxzipple.modules.access.application.action_changes import (
    change_optional_text as _change_optional_text,
    required_text as _required_text,
)
from crxzipple.modules.access.application.action_contracts import (
    AccessActionRequest,
    AccessActionResult,
    JsonObject,
)
from crxzipple.modules.access.application.action_oauth_handlers import (
    begin_codex_oauth_login as _begin_codex_oauth_login,
    begin_oauth_setup_session as _begin_oauth_setup_session,
    complete_oauth_setup_session as _complete_oauth_setup_session,
    refresh_oauth_account as _refresh_oauth_account,
    register_oauth_provider as _register_oauth_provider,
    rotate_oauth_account as _rotate_oauth_account,
    update_oauth_account_status as _update_oauth_account_status,
)
from crxzipple.modules.access.application.action_payloads import (
    access_action_decision as _access_action_decision,
    access_action_failure_event_name as _access_action_failure_event_name,
    access_action_success_event_name as _access_action_success_event_name,
    access_result_from_settings_result as _access_result_from_settings_result,
    audit_result_payload as _audit_result_payload,
)
from crxzipple.modules.access.application.action_redaction import (
    redact_sensitive,
    redacted_action_changes as _redacted_action_changes,
    reject_raw_secret_inputs as _reject_raw_secret_inputs,
)
from crxzipple.modules.access.application.action_setup_handlers import (
    begin_setup_session as _begin_setup_session,
    verify_credential_requirement as _verify_credential_requirement,
)
from crxzipple.modules.access.application.events import (
    ACCESS_ACTION_REQUESTED_EVENT,
    AccessEventPublisher,
    publish_access_event,
)
from crxzipple.modules.access.application.repositories import (
    AccessActionAuditRepository,
)
from crxzipple.modules.access.application.settings_integration import (
    CONFIG_WRITE_INTENTS,
    AccessSettingsActionAdapter,
)
from crxzipple.modules.access.application.oauth import AccessOAuthService
from crxzipple.modules.access.application.setup import AccessSetupSessionService


class AccessActionService:
    _SAFE_INTENTS = {
        "dry-run",
        "dry_run",
        "noop",
        "register_env_binding",
        "register_file_binding",
        "register_oauth_provider",
        "begin_oauth_setup_session",
        "complete_oauth_setup_session",
        "begin_codex_oauth_login",
        "update_credential_binding",
        "begin_setup_session",
        "verify_credential_requirement",
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
        oauth_service: AccessOAuthService | None = None,
        event_publisher: AccessEventPublisher | None = None,
    ) -> None:
        self._audit_repository = audit_repository
        self._setup_session_service = setup_session_service
        self._settings_action_adapter = settings_action_adapter
        self._oauth_service = oauth_service
        self._event_publisher = event_publisher

    def execute(self, request: AccessActionRequest) -> AccessActionResult:
        reason = _required_text(request.reason, "reason")
        intent = _required_text(request.intent, "intent")
        action_id = _required_text(request.action_id, "action id")
        resource_kind = _required_text(request.resource_kind, "resource kind")
        _reject_raw_secret_inputs(request)
        self._validate_dangerous_confirmation(request)
        self._publish_action_event(request, ACCESS_ACTION_REQUESTED_EVENT, status="requested")
        if intent in CONFIG_WRITE_INTENTS:
            if self._settings_action_adapter is None:
                raise RuntimeError(
                    "settings action adapter is required for access configuration actions.",
                )
            result = _access_result_from_settings_result(
                self._settings_action_adapter.execute_config_action(request),
            )
            self._publish_action_event(
                request,
                _access_action_success_event_name(intent),
                status=result.status,
                result=result,
            )
            return result
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
            self._publish_action_event(
                request,
                _access_action_failure_event_name(intent),
                status="failed",
                level="error",
                error={"code": exc.__class__.__name__, "message": str(exc)},
                audit_ref=audit.audit_id,
            )
            raise
        self._audit_repository.mark_succeeded(
            audit.audit_id,
            result=redact_sensitive(_audit_result_payload(request, result)),
        )
        self._publish_action_event(
            request,
            _access_action_success_event_name(intent),
            status=result.status,
            result=result,
            audit_ref=audit.audit_id,
        )
        return result

    def _publish_action_event(
        self,
        request: AccessActionRequest,
        event_name: str,
        *,
        status: str,
        level: str = "info",
        result: AccessActionResult | None = None,
        error: JsonObject | None = None,
        audit_ref: str | None = None,
    ) -> None:
        payload: JsonObject = {
            "action_id": request.action_id,
            "intent": request.intent,
            "resource_kind": request.resource_kind,
            "target_id": request.target_id,
            "actor": request.actor,
            "operator": request.actor,
            "reason": request.reason,
            "changes": _redacted_action_changes(request),
            "audit_ref": audit_ref or result.audit_ref if result is not None else audit_ref,
        }
        if result is not None:
            payload["result"] = redact_sensitive(_audit_result_payload(request, result))
        if error is not None:
            payload["error"] = redact_sensitive(error)
        publish_access_event(
            self._event_publisher,
            event_name,
            status=status,
            level=level,
            target_id=request.target_id,
            payload=payload,
            trace_context=request.trace_context,
        )

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
            return _begin_setup_session(
                request,
                audit_ref=audit_ref,
                setup_session_service=self._setup_session_service,
            )
        if intent == "verify_credential_requirement":
            return _verify_credential_requirement(
                request,
                audit_ref=audit_ref,
                settings_action_adapter=self._settings_action_adapter,
            )
        if intent == "register_oauth_provider":
            return _register_oauth_provider(
                request,
                audit_ref=audit_ref,
                oauth_service=self._oauth_service,
            )
        if intent == "begin_oauth_setup_session":
            return _begin_oauth_setup_session(
                request,
                audit_ref=audit_ref,
                oauth_service=self._oauth_service,
            )
        if intent == "complete_oauth_setup_session":
            return _complete_oauth_setup_session(
                request,
                audit_ref=audit_ref,
                oauth_service=self._oauth_service,
            )
        if intent == "begin_codex_oauth_login":
            return _begin_codex_oauth_login(
                request,
                audit_ref=audit_ref,
                oauth_service=self._oauth_service,
            )
        if intent == "refresh_oauth_account":
            return _refresh_oauth_account(
                request,
                audit_ref=audit_ref,
                oauth_service=self._oauth_service,
            )
        if intent == "rotate_oauth_account":
            return _rotate_oauth_account(
                request,
                audit_ref=audit_ref,
                oauth_service=self._oauth_service,
            )
        if intent in {"disable_oauth_account", "revoke_oauth_account"}:
            return _update_oauth_account_status(
                request,
                audit_ref=audit_ref,
                oauth_service=self._oauth_service,
            )
        if intent in self._SAFE_INTENTS:
            raise ValueError(f"access action intent '{intent}' is not implemented.")
        raise ValueError(f"unsupported access action intent '{intent}'.")

    def _validate_dangerous_confirmation(self, request: AccessActionRequest) -> None:
        intent = request.intent.strip().lower()
        dangerous = any(marker in intent for marker in self._DANGEROUS_MARKERS)
        if intent == "update_credential_binding":
            status = _change_optional_text(request.changes, "status")
            dangerous = dangerous or status in {"disabled", "revoked"}
        if not dangerous:
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
