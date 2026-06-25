from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from uuid import uuid4

from crxzipple.modules.access.application.credential_requirement_rules import (
    canonical_credential_binding,
)
from crxzipple.modules.access.application.repositories import (
    AccessConsumerBindingRecord,
    AccessCredentialBindingRecord,
)
from crxzipple.modules.access.application.ports import (
    AccessSettingsActionPort,
    AccessSettingsQueryPort,
)
from crxzipple.modules.access.application.settings_action_contracts import (
    AccessSettingsActionRequest,
    AccessSettingsActionResult,
)
from crxzipple.modules.access.application.settings_consumer_bindings import (
    _consumer_binding_from_request,
    _consumer_binding_id_from_request,
    _consumer_binding_result,
    _expected_kind_for_consumer,
    _expected_kind_for_slot,
    _slot_from_request_or_consumer,
)
from crxzipple.modules.access.application.settings_config_views import (
    AccessSettingsConfigProvider,
    AccessSettingsConfigView,
)
from crxzipple.modules.access.application.settings_credential_bindings import (
    _binding_source_ref,
    _changed_credential_binding_fields,
    _credential_binding_from_update_request,
    _credential_binding_public_source_ref,
    _credential_binding_redacted_metadata,
    _credential_binding_update_validation_metadata,
    _default_binding_kind,
)
from crxzipple.modules.access.application.settings_payloads import (
    _change_optional_text,
    _change_text,
)
from crxzipple.modules.access.application.settings_record_models import (
    _consumer_binding_payload,
    _credential_binding_payload,
)
from crxzipple.modules.settings.application.models import (
    CreateSettingsResourceInput,
    UpdateSettingsResourceInput,
)
from crxzipple.modules.settings.domain import SettingsNotFoundError


CONFIG_WRITE_INTENTS = frozenset(
    {
        "bind_credential_requirement",
        "register_env_binding",
        "register_file_binding",
        "register_app_credential_binding",
        "register_oauth_account_binding",
        "update_credential_binding",
        "unbind_credential_requirement",
        "disable_credential_binding",
        "enable_credential_binding",
        "revoke_credential_binding",
    },
)


@dataclass(slots=True)
class AccessSettingsActionAdapter:
    action_service: AccessSettingsActionPort
    query_service: AccessSettingsQueryPort
    environment: str | None = None

    def execute_config_action(
        self,
        request: AccessSettingsActionRequest,
    ) -> AccessSettingsActionResult:
        intent = request.intent.strip()
        if intent == "bind_credential_requirement":
            return self._bind_consumer_requirement(request)
        if intent == "register_env_binding":
            return self._register_binding(request, source_kind="env")
        if intent == "register_file_binding":
            return self._register_binding(request, source_kind="file")
        if intent == "register_app_credential_binding":
            return self._register_binding(request, source_kind="app_credential")
        if intent == "register_oauth_account_binding":
            return self._register_binding(request, source_kind="oauth_account")
        if intent == "update_credential_binding":
            return self._update_credential_binding(request)
        if intent == "unbind_credential_requirement":
            return self._unbind_consumer_requirement(request)
        if intent == "disable_credential_binding":
            return self._update_credential_binding_status(request, status="disabled")
        if intent == "enable_credential_binding":
            return self._update_credential_binding_status(request, status="active")
        if intent == "revoke_credential_binding":
            return self._update_credential_binding_status(request, status="revoked")
        raise ValueError(f"unsupported settings-owned access action intent '{intent}'.")

    def config_view(self) -> AccessSettingsConfigView:
        return AccessSettingsConfigProvider(
            self.query_service,
            environment=self.environment,
        ).view()

    def _register_binding(
        self,
        request: AccessSettingsActionRequest,
        *,
        source_kind: str,
    ) -> AccessSettingsActionResult:
        source_ref = _binding_source_ref(request, source_kind)
        binding_id = _change_text(
            request.changes,
            "binding_id",
            default=request.target_id or f"cred_{uuid4().hex}",
        )
        binding = AccessCredentialBindingRecord(
            binding_id=binding_id,
            asset_id=_change_optional_text(request.changes, "asset_id"),
            binding_kind=_change_text(
                request.changes,
                "binding_kind",
                default=_default_binding_kind(source_kind),
            ),
            source_kind=source_kind,
            source_ref=source_ref,
            masked_preview=_change_optional_text(request.changes, "masked_preview"),
            status=_change_text(request.changes, "status", default="active"),
            redaction_policy={"mode": "metadata_only"},
            metadata={
                "action_id": request.action_id,
                "reason": request.reason,
                "trace_context": dict(request.trace_context),
            },
        )
        payload = {
            "credential_bindings": [_credential_binding_payload(binding)],
            "metadata": {"settings_owner": "access_config"},
        }
        result = self._upsert_settings_resource(
            resource_id=binding.binding_id,
            payload=payload,
            display_name=binding.binding_id,
            request=request,
        )
        return AccessSettingsActionResult(
            status=result.status,
            asset={
                "resource_kind": "credential_binding",
                "binding_id": binding.binding_id,
                "binding_kind": binding.binding_kind,
                "source_kind": binding.source_kind,
                "source_ref": canonical_credential_binding(
                    f"{binding.source_kind}:{binding.source_ref}"
                    if binding.source_kind in {"env", "file"}
                    else binding.source_ref,
                ),
                "asset_id": binding.asset_id,
                "status": binding.status,
            },
            audit_ref=result.audit_ref,
            validation=result.validation.to_payload(),
            warnings=tuple(result.warnings),
        )

    def _update_credential_binding(
        self,
        request: AccessSettingsActionRequest,
    ) -> AccessSettingsActionResult:
        binding_id = _change_text(
            request.changes,
            "binding_id",
            default=request.target_id,
        )
        existing = self.config_view().get_credential_binding(binding_id)
        if existing is None:
            raise ValueError(f"credential binding '{binding_id}' was not found.")
        before_redacted = _credential_binding_redacted_metadata(existing)
        binding = _credential_binding_from_update_request(request, existing=existing)
        after_redacted = _credential_binding_redacted_metadata(binding)
        changed = _changed_credential_binding_fields(
            before_redacted=before_redacted,
            after_redacted=after_redacted,
        )
        validation_metadata = _credential_binding_update_validation_metadata(
            binding_id=binding.binding_id,
            before_redacted=before_redacted,
            after_redacted=after_redacted,
            changed=changed,
        )
        result = self._upsert_settings_resource(
            resource_id=binding.binding_id,
            payload={
                "credential_bindings": [_credential_binding_payload(binding)],
                "metadata": {
                    "settings_owner": "access_config",
                    "access_action_validation": validation_metadata,
                },
            },
            display_name=binding.binding_id,
            request=request,
        )
        validation = result.validation.to_payload()
        validation["before_redacted"] = before_redacted
        validation["after_redacted"] = after_redacted
        validation["metadata"] = {
            **dict(validation.get("metadata") or {}),
            **validation_metadata,
        }
        return AccessSettingsActionResult(
            status=result.status,
            asset={
                "resource_kind": "credential_binding",
                "binding_id": binding.binding_id,
                "binding_kind": binding.binding_kind,
                "source_kind": binding.source_kind,
                "source_ref": _credential_binding_public_source_ref(binding),
                "asset_id": binding.asset_id,
                "masked_preview": binding.masked_preview,
                "previous_fields": validation_metadata["previous_fields"],
                "updated_fields": validation_metadata["updated_fields"],
                "previous_status": existing.status,
                "status": binding.status,
            },
            audit_ref=result.audit_ref,
            validation=validation,
            warnings=tuple(result.warnings),
        )

    def _bind_consumer_requirement(
        self,
        request: AccessSettingsActionRequest,
    ) -> AccessSettingsActionResult:
        view = self.config_view()
        consumer_binding_id = _consumer_binding_id_from_request(request)
        existing = view.get_consumer_binding(consumer_binding_id)
        credential_binding_id = _change_text(
            request.changes,
            "credential_binding_id",
        )
        credential = view.get_credential_binding(credential_binding_id)
        if credential is None:
            raise ValueError(
                f"credential binding '{credential_binding_id}' was not found.",
            )
        consumer = _consumer_binding_from_request(
            request,
            existing=existing,
            credential_binding_id=credential.binding_id,
            credential=credential,
            unbind=False,
        )
        slot = _slot_from_request_or_consumer(request, consumer)
        expected_kind = _expected_kind_for_slot(
            consumer, slot
        ) or _expected_kind_for_consumer(
            consumer,
        )
        binding_kind = credential.binding_kind.strip().lower()
        if (
            expected_kind is not None
            and binding_kind != expected_kind
            and not bool(request.changes.get("allow_kind_mismatch"))
        ):
            raise ValueError(
                "credential binding kind does not match requirement: "
                f"expected '{expected_kind}', got '{binding_kind}'.",
            )
        result = self._upsert_consumer_binding_resource(
            consumer,
            request=request,
        )
        return _consumer_binding_result(
            result,
            consumer,
            validation_metadata={
                "credential_binding_id": credential.binding_id,
                "slot": slot,
                "expected_kind": expected_kind,
                "binding_kind": binding_kind,
            },
        )

    def _unbind_consumer_requirement(
        self,
        request: AccessSettingsActionRequest,
    ) -> AccessSettingsActionResult:
        view = self.config_view()
        consumer_binding_id = _consumer_binding_id_from_request(request)
        existing = view.get_consumer_binding(consumer_binding_id)
        if (
            existing is not None
            and len(existing.credential_bindings) > 1
            and _change_optional_text(request.changes, "slot") is None
        ):
            raise ValueError(
                "slot is required to unbind a multi-slot consumer binding."
            )
        consumer = _consumer_binding_from_request(
            request,
            existing=existing,
            credential_binding_id=None,
            credential=None,
            unbind=True,
        )
        result = self._upsert_consumer_binding_resource(
            consumer,
            request=request,
        )
        return _consumer_binding_result(
            result,
            consumer,
            validation_metadata={
                "credential_binding_id": None,
                "slot": _slot_from_request_or_consumer(request, consumer),
            },
        )

    def _update_credential_binding_status(
        self,
        request: AccessSettingsActionRequest,
        *,
        status: str,
    ) -> AccessSettingsActionResult:
        binding_id = _change_text(
            request.changes,
            "binding_id",
            default=request.target_id,
        )
        existing = self.config_view().get_credential_binding(binding_id)
        if existing is None:
            raise ValueError(f"credential binding '{binding_id}' was not found.")
        existing_status = existing.status.strip().lower()
        if status == "active" and existing_status == "revoked":
            raise ValueError(
                f"credential binding '{binding_id}' is revoked and cannot be re-enabled.",
            )
        metadata = {
            **dict(existing.metadata),
            "action_id": request.action_id,
            "reason": request.reason,
            "trace_context": dict(request.trace_context),
            "previous_status": existing.status,
        }
        binding = AccessCredentialBindingRecord(
            binding_id=existing.binding_id,
            asset_id=existing.asset_id,
            binding_kind=existing.binding_kind,
            source_kind=existing.source_kind,
            source_ref=existing.source_ref,
            masked_preview=existing.masked_preview,
            status=status,
            redaction_policy=dict(existing.redaction_policy),
            metadata=metadata,
        )
        result = self._upsert_settings_resource(
            resource_id=binding.binding_id,
            payload={
                "credential_bindings": [_credential_binding_payload(binding)],
                "metadata": {"settings_owner": "access_config"},
            },
            display_name=binding.binding_id,
            request=request,
        )
        validation = result.validation.to_payload()
        validation["metadata"] = {
            **dict(validation.get("metadata") or {}),
            "binding_id": binding.binding_id,
            "previous_status": existing.status,
            "status": binding.status,
        }
        return AccessSettingsActionResult(
            status=result.status,
            asset={
                "resource_kind": "credential_binding",
                "binding_id": binding.binding_id,
                "binding_kind": binding.binding_kind,
                "source_kind": binding.source_kind,
                "asset_id": binding.asset_id,
                "previous_status": existing.status,
                "status": binding.status,
            },
            audit_ref=result.audit_ref,
            validation=validation,
            warnings=tuple(result.warnings),
        )

    def _upsert_consumer_binding_resource(
        self,
        consumer: AccessConsumerBindingRecord,
        *,
        request: AccessSettingsActionRequest,
    ):
        payload = {
            "consumer_bindings": [_consumer_binding_payload(consumer)],
            "metadata": {"settings_owner": "access_config"},
        }
        return self._upsert_settings_resource(
            resource_id=consumer.binding_id,
            payload=payload,
            display_name=consumer.display_name or consumer.binding_id,
            request=request,
        )

    def _upsert_settings_resource(
        self,
        *,
        resource_id: str,
        payload: Mapping[str, Any],
        display_name: str,
        request: AccessSettingsActionRequest,
    ):
        try:
            self.query_service.get_resource(resource_id)
        except SettingsNotFoundError:
            return self.action_service.create_resource(
                CreateSettingsResourceInput(
                    resource_id=resource_id,
                    resource_kind="access-assets",
                    owner_module="settings",
                    payload=payload,
                    display_name=display_name,
                    actor=request.actor,
                    reason=request.reason,
                    publish=True,
                    source="access_settings_action",
                    metadata={"access_action_id": request.action_id},
                    trace_context=request.trace_context,
                ),
            )
        return self.action_service.update_resource(
            UpdateSettingsResourceInput(
                resource_id=resource_id,
                payload=payload,
                actor=request.actor,
                reason=request.reason,
                publish=True,
                source="access_settings_action",
                metadata={"access_action_id": request.action_id},
                trace_context=request.trace_context,
            ),
        )
