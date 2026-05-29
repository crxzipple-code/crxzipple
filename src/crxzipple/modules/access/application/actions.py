from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from crxzipple.modules.access.application.events import (
    ACCESS_ACTION_FAILED_EVENT,
    ACCESS_ACTION_REQUESTED_EVENT,
    ACCESS_ACTION_SUCCEEDED_EVENT,
    ACCESS_CREDENTIAL_CONFIGURED_EVENT,
    ACCESS_CREDENTIAL_DISABLED_EVENT,
    ACCESS_CREDENTIAL_FAILED_EVENT,
    ACCESS_CREDENTIAL_REVOKED_EVENT,
    ACCESS_CREDENTIAL_ROTATED_EVENT,
    ACCESS_SETUP_COMPLETED_EVENT,
    ACCESS_SETUP_FAILED_EVENT,
    ACCESS_SETUP_STARTED_EVENT,
    AccessEventPublisher,
    publish_access_event,
)
from crxzipple.modules.access.application.repositories import (
    AccessActionAuditRepository,
    AccessConsumerBindingRecord,
    AccessCredentialBindingRecord,
)
from crxzipple.modules.access.application.settings_integration import (
    CONFIG_WRITE_INTENTS,
    AccessSettingsActionAdapter,
)
from crxzipple.modules.access.application.oauth import AccessOAuthService
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
            return self._begin_setup_session(request, audit_ref=audit_ref)
        if intent == "verify_credential_requirement":
            return self._verify_credential_requirement(request, audit_ref=audit_ref)
        if intent == "register_oauth_provider":
            return self._register_oauth_provider(request, audit_ref=audit_ref)
        if intent == "begin_oauth_setup_session":
            return self._begin_oauth_setup_session(request, audit_ref=audit_ref)
        if intent == "complete_oauth_setup_session":
            return self._complete_oauth_setup_session(request, audit_ref=audit_ref)
        if intent == "begin_codex_oauth_login":
            return self._begin_codex_oauth_login(request, audit_ref=audit_ref)
        if intent == "refresh_oauth_account":
            return self._refresh_oauth_account(request, audit_ref=audit_ref)
        if intent == "rotate_oauth_account":
            return self._rotate_oauth_account(request, audit_ref=audit_ref)
        if intent in {"disable_oauth_account", "revoke_oauth_account"}:
            return self._update_oauth_account_status(request, audit_ref=audit_ref)
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

    def _verify_credential_requirement(
        self,
        request: AccessActionRequest,
        *,
        audit_ref: str,
    ) -> AccessActionResult:
        if self._settings_action_adapter is None:
            raise RuntimeError(
                "settings action adapter is required for access requirement verification.",
            )
        view = self._settings_action_adapter.config_view()
        consumer_binding_id = _change_text(
            request.changes,
            "consumer_binding_id",
            default=request.target_id,
        )
        consumer = view.get_consumer_binding(consumer_binding_id)
        if consumer is None:
            raise ValueError(
                f"consumer binding '{consumer_binding_id}' was not found.",
            )
        slot = _change_optional_text(request.changes, "slot") or _consumer_default_slot(
            consumer,
        )
        if slot is None and len(consumer.credential_bindings) > 1:
            raise ValueError("slot is required to verify a multi-slot consumer binding.")
        credential_binding_id = (
            _change_optional_text(request.changes, "credential_binding_id")
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
        readiness = _credential_requirement_readiness(
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
                "permission_decision": _access_action_decision(),
            },
            readiness=readiness,
        )

    def _register_oauth_provider(
        self,
        request: AccessActionRequest,
        *,
        audit_ref: str,
    ) -> AccessActionResult:
        service = self._required_oauth_service()
        provider = service.register_provider(
            provider_id=_change_text(request.changes, "provider_id", default=request.target_id),
            display_name=_change_optional_text(request.changes, "display_name"),
            provider_kind=_change_text(request.changes, "provider_kind", default="oauth2"),
            authorization_url=_change_optional_text(request.changes, "authorization_url"),
            token_url=_change_optional_text(request.changes, "token_url"),
            revocation_url=_change_optional_text(request.changes, "revocation_url"),
            device_code_url=_change_optional_text(request.changes, "device_code_url"),
            default_scopes=tuple(_string_list(request.changes.get("default_scopes"))),
            client_id=_change_optional_text(request.changes, "client_id"),
            client_credential_binding_id=_change_optional_text(
                request.changes,
                "client_credential_binding_id",
            ),
            callback_url=_change_optional_text(request.changes, "callback_url"),
            callback_mode=_change_text(
                request.changes,
                "callback_mode",
                default="manual_code",
            ),
            status=_change_text(request.changes, "status", default="active"),
            metadata=_change_object(request.changes, "metadata"),
        )
        return AccessActionResult(
            status="succeeded",
            asset={
                "resource_kind": "oauth_provider",
                "provider_id": provider.provider_id,
                "display_name": provider.display_name,
                "provider_kind": provider.provider_kind,
                "status": provider.status,
                "default_scopes": list(provider.default_scopes),
                "callback_mode": provider.callback_mode,
            },
            audit_ref=audit_ref,
            validation={
                "ok": True,
                "after_redacted": {
                    "provider_id": provider.provider_id,
                    "status": provider.status,
                },
                "permission_decision": _access_action_decision(),
            },
        )

    def _begin_oauth_setup_session(
        self,
        request: AccessActionRequest,
        *,
        audit_ref: str,
    ) -> AccessActionResult:
        service = self._required_oauth_service()
        flow_kind = _change_text(request.changes, "flow_kind", default="browser_oauth")
        provider_id = _change_text(
            request.changes,
            "provider_id",
            default=request.target_id,
        )
        requested_scopes = tuple(_string_list(request.changes.get("scopes")))
        account_id = _change_optional_text(request.changes, "account_id")
        credential_binding_id = _change_optional_text(
            request.changes,
            "credential_binding_id",
        )
        if flow_kind == "device_code":
            result = service.begin_device_code_setup(
                provider_id=provider_id,
                requested_scopes=requested_scopes,
                account_id=account_id,
                credential_binding_id=credential_binding_id,
                actor=request.actor,
                reason=request.reason,
            )
        elif flow_kind == "browser_oauth":
            result = service.begin_browser_setup(
                provider_id=provider_id,
                requested_scopes=requested_scopes,
                account_id=account_id,
                credential_binding_id=credential_binding_id,
                actor=request.actor,
                reason=request.reason,
            )
        else:
            raise ValueError(
                "OAuth setup flow_kind must be browser_oauth or device_code.",
            )
        return AccessActionResult(
            status="unsupported" if result.status == "unsupported" else "succeeded",
            asset={
                "resource_kind": "oauth_setup_session",
                **result.to_payload(),
            },
            audit_ref=audit_ref,
            validation={
                "ok": True,
                "after_redacted": result.to_payload(),
                "permission_decision": _access_action_decision(),
            },
        )

    def _complete_oauth_setup_session(
        self,
        request: AccessActionRequest,
        *,
        audit_ref: str,
    ) -> AccessActionResult:
        service = self._required_oauth_service()
        result = service.complete_setup_session(
            session_id=_change_text(
                request.changes,
                "session_id",
                default=request.target_id,
            ),
            code=_change_optional_text(request.changes, "code"),
            state=_change_optional_text(request.changes, "state"),
            account_id=_change_optional_text(request.changes, "account_id"),
            credential_binding_id=_change_optional_text(
                request.changes,
                "credential_binding_id",
            ),
        )
        return AccessActionResult(
            status="succeeded",
            asset=result.to_payload(),
            audit_ref=audit_ref,
            validation={
                "ok": True,
                "after_redacted": result.to_payload(),
                "permission_decision": _access_action_decision(),
            },
        )

    def _begin_codex_oauth_login(
        self,
        request: AccessActionRequest,
        *,
        audit_ref: str,
    ) -> AccessActionResult:
        service = self._required_oauth_service()
        account_id = _change_text(
            request.changes,
            "account_id",
            default="openai-codex:default",
        )
        credential_binding_id = _change_text(
            request.changes,
            "credential_binding_id",
            default="codex-oauth-default",
        )
        result = service.begin_codex_oauth_login(
            account_id=account_id,
            credential_binding_id=credential_binding_id,
            actor=request.actor,
            reason=request.reason,
            open_browser=_change_bool(request.changes, "open_browser", default=True),
        )
        return AccessActionResult(
            status="succeeded",
            asset={
                "resource_kind": "oauth_setup_session",
                "provider_id": "openai-codex",
                "account_id": account_id,
                "credential_binding_id": credential_binding_id,
                **result.to_payload(),
            },
            audit_ref=audit_ref,
            validation={
                "ok": True,
                "after_redacted": {
                    "resource_kind": "oauth_setup_session",
                    "provider_id": "openai-codex",
                    "account_id": account_id,
                    "credential_binding_id": credential_binding_id,
                    **result.to_payload(),
                },
                "permission_decision": _access_action_decision(),
            },
        )

    def _refresh_oauth_account(
        self,
        request: AccessActionRequest,
        *,
        audit_ref: str,
    ) -> AccessActionResult:
        service = self._required_oauth_service()
        result = service.refresh_account(
            _change_text(request.changes, "account_id", default=request.target_id),
        )
        return AccessActionResult(
            status="succeeded",
            asset=result.to_payload(),
            audit_ref=audit_ref,
            validation={
                "ok": True,
                "after_redacted": result.to_payload(),
                "permission_decision": _access_action_decision(),
            },
        )

    def _rotate_oauth_account(
        self,
        request: AccessActionRequest,
        *,
        audit_ref: str,
    ) -> AccessActionResult:
        service = self._required_oauth_service()
        result = service.begin_account_rotation(
            _change_text(request.changes, "account_id", default=request.target_id),
            requested_scopes=tuple(_string_list(request.changes.get("scopes"))),
            actor=request.actor,
            reason=request.reason,
            flow_kind=_change_text(
                request.changes,
                "flow_kind",
                default="browser_oauth",
            ),
        )
        return AccessActionResult(
            status="unsupported" if result.status == "unsupported" else "succeeded",
            asset={
                "resource_kind": "oauth_setup_session",
                **result.to_payload(),
            },
            audit_ref=audit_ref,
            validation={
                "ok": result.status != "unsupported",
                "after_redacted": result.to_payload(),
                "permission_decision": _access_action_decision(),
            },
        )

    def _update_oauth_account_status(
        self,
        request: AccessActionRequest,
        *,
        audit_ref: str,
    ) -> AccessActionResult:
        service = self._required_oauth_service()
        status = "revoked" if request.intent == "revoke_oauth_account" else "disabled"
        account = service.set_account_status(
            _change_text(request.changes, "account_id", default=request.target_id),
            status=status,
        )
        return AccessActionResult(
            status="succeeded",
            asset={
                "resource_kind": "oauth_account",
                "account_id": account.account_id,
                "provider_id": account.provider_id,
                "credential_binding_id": account.credential_binding_id,
                "status": account.status,
            },
            audit_ref=audit_ref,
            validation={
                "ok": True,
                "after_redacted": {
                    "account_id": account.account_id,
                    "status": account.status,
                },
                "permission_decision": _access_action_decision(),
            },
        )

    def _required_oauth_service(self) -> AccessOAuthService:
        if self._oauth_service is None:
            raise RuntimeError("access OAuth service is not configured.")
        return self._oauth_service

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


def _access_action_success_event_name(intent: str) -> str:
    normalized = intent.strip().lower()
    if normalized in {"begin_setup_session", "begin_oauth_setup_session", "begin_codex_oauth_login"}:
        return ACCESS_SETUP_STARTED_EVENT
    if normalized == "complete_oauth_setup_session":
        return ACCESS_SETUP_COMPLETED_EVENT
    if normalized in {"disable_credential_binding", "disable_oauth_account"}:
        return ACCESS_CREDENTIAL_DISABLED_EVENT
    if normalized in {"revoke_credential_binding", "revoke_oauth_account"}:
        return ACCESS_CREDENTIAL_REVOKED_EVENT
    if normalized in {"register_env_binding", "register_file_binding", "register_oauth_account_binding", "register_app_credential_binding", "update_credential_binding"}:
        return ACCESS_CREDENTIAL_CONFIGURED_EVENT
    if normalized in {"refresh_oauth_account", "rotate_oauth_account"}:
        return ACCESS_CREDENTIAL_ROTATED_EVENT
    return ACCESS_ACTION_SUCCEEDED_EVENT


def _access_action_failure_event_name(intent: str) -> str:
    normalized = intent.strip().lower()
    if "setup" in normalized or normalized == "begin_codex_oauth_login":
        return ACCESS_SETUP_FAILED_EVENT
    if "credential" in normalized or "oauth_account" in normalized:
        return ACCESS_CREDENTIAL_FAILED_EVENT
    return ACCESS_ACTION_FAILED_EVENT


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
        "authorization",
        "secret",
        "secret_value",
        "raw_secret",
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "client_secret",
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


def _change_optional_text(changes: JsonObject, *keys: str) -> str | None:
    for key in keys:
        value = changes.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _change_object(changes: JsonObject, key: str) -> JsonObject:
    value = changes.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _change_bool(changes: JsonObject, key: str, *, default: bool) -> bool:
    value = changes.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _access_action_decision() -> JsonObject:
    return {
        "effect": "allow",
        "code": "access_action_accepted",
        "reason": "external access governance action accepted by Access",
    }


def _credential_requirement_readiness(
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


def _consumer_default_slot(consumer: AccessConsumerBindingRecord) -> str | None:
    if len(consumer.credential_bindings) == 1:
        return next(iter(consumer.credential_bindings))
    metadata_slot = consumer.metadata.get("slot")
    if isinstance(metadata_slot, str) and metadata_slot.strip():
        return metadata_slot.strip()
    return None


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
