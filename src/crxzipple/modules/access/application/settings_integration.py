from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from uuid import uuid4

from crxzipple.modules.access.application.repositories import (
    AccessAssetRecord,
    AccessConsumerBindingRecord,
    AccessCredentialBindingRecord,
)
from crxzipple.modules.access.application.ports import (
    AccessSettingsActionPort,
    AccessSettingsQueryPort,
)
from crxzipple.modules.access.application.services import canonical_credential_binding
from crxzipple.modules.settings.application.materialization import (
    SettingsEffectiveConfigMaterializer,
)
from crxzipple.modules.settings.application.models import (
    CreateSettingsResourceInput,
    UpdateSettingsResourceInput,
)
from crxzipple.modules.settings.domain import SettingsNotFoundError
from crxzipple.shared.settings import AccessConfig


JsonObject = dict[str, Any]

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


class AccessSettingsActionRequest(Protocol):
    action_id: str
    resource_kind: str
    target_id: str | None
    intent: str
    changes: Mapping[str, Any]
    reason: str
    actor: str | None
    trace_context: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class AccessSettingsActionResult:
    status: str
    asset: JsonObject | None = None
    audit_ref: str | None = None
    validation: JsonObject | None = None
    warnings: tuple[str, ...] = ()


@dataclass(slots=True)
class AccessSettingsConfigView:
    configs: tuple[AccessConfig, ...]

    def list_assets(self) -> tuple[AccessAssetRecord, ...]:
        return tuple(
            _asset_record(item)
            for config in self.configs
            if config.enabled
            for item in config.assets
        )

    def list_credential_bindings(self) -> tuple[AccessCredentialBindingRecord, ...]:
        return tuple(
            _credential_binding_record(item)
            for config in self.configs
            if config.enabled
            for item in config.credential_bindings
        )

    def get_credential_binding(
        self,
        binding_id: str,
    ) -> AccessCredentialBindingRecord | None:
        normalized = binding_id.strip()
        return next(
            (
                item
                for item in self.list_credential_bindings()
                if item.binding_id == normalized
            ),
            None,
        )

    def get_consumer_binding(
        self,
        binding_id: str,
    ) -> AccessConsumerBindingRecord | None:
        normalized = binding_id.strip()
        return next(
            (
                item
                for item in self.list_consumer_bindings()
                if item.binding_id == normalized
            ),
            None,
        )

    def list_consumer_bindings(self) -> tuple[AccessConsumerBindingRecord, ...]:
        return tuple(
            _consumer_binding_record(item)
            for config in self.configs
            if config.enabled
            for item in config.consumer_bindings
        )


@dataclass(slots=True)
class AccessSettingsConfigProvider:
    query_service: AccessSettingsQueryPort | None
    environment: str | None = None

    def view(self) -> AccessSettingsConfigView:
        if self.query_service is None:
            return AccessSettingsConfigView(configs=())
        materializer = SettingsEffectiveConfigMaterializer(
            self.query_service,
            environment=self.environment,
        )
        return AccessSettingsConfigView(configs=materializer.access_configs())

    def get_credential_binding(
        self,
        binding_id: str,
    ) -> AccessCredentialBindingRecord | None:
        return self.view().get_credential_binding(binding_id)

    def get_consumer_binding(
        self,
        binding_id: str,
    ) -> AccessConsumerBindingRecord | None:
        return self.view().get_consumer_binding(binding_id)

    def list_assets(self) -> tuple[AccessAssetRecord, ...]:
        return self.view().list_assets()

    def list_credential_bindings(self) -> tuple[AccessCredentialBindingRecord, ...]:
        return self.view().list_credential_bindings()

    def list_consumer_bindings(self) -> tuple[AccessConsumerBindingRecord, ...]:
        return self.view().list_consumer_bindings()


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
        expected_kind = _expected_kind_for_slot(consumer, slot) or _expected_kind_for_consumer(
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
            raise ValueError("slot is required to unbind a multi-slot consumer binding.")
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


def _asset_record(payload: Mapping[str, Any]) -> AccessAssetRecord:
    asset_id = _payload_text(payload, "asset_id", "id")
    return AccessAssetRecord(
        asset_id=asset_id,
        asset_kind=_payload_text(payload, "asset_kind", "kind", default="secret_asset"),
        display_name=_payload_text(payload, "display_name", "name", default=asset_id),
        governance_scope=_payload_text(payload, "governance_scope", "scope", default="global"),
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


def _credential_binding_record(payload: Mapping[str, Any]) -> AccessCredentialBindingRecord:
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


def _credential_binding_from_update_request(
    request: AccessSettingsActionRequest,
    *,
    existing: AccessCredentialBindingRecord,
) -> AccessCredentialBindingRecord:
    requested_source_kind = _change_optional_text(request.changes, "source_kind")
    source_kind = (
        _normalize_credential_binding_source_kind(requested_source_kind)
        if requested_source_kind is not None
        else existing.source_kind
    )
    existing_source_kind = existing.source_kind.strip().lower()
    source_kind_changed = source_kind.strip().lower() != existing_source_kind
    source_ref_changed = _binding_source_ref_change_requested(
        request.changes,
        source_kind,
    )
    source_ref = existing.source_ref
    if source_kind_changed or source_ref_changed:
        if source_kind not in {"env", "file", "app_credential", "oauth_account"}:
            raise ValueError(
                "source_ref updates are only supported for env, file, "
                "app_credential, and oauth_account credential binding sources.",
            )
        source_ref = _binding_source_ref(request, source_kind)
    status = _credential_binding_status_from_changes(request.changes, existing)
    metadata = {
        **dict(existing.metadata),
        "action_id": request.action_id,
        "reason": request.reason,
        "trace_context": dict(request.trace_context),
        "previous_fields": _credential_binding_redacted_metadata(existing),
    }
    return AccessCredentialBindingRecord(
        binding_id=existing.binding_id,
        asset_id=_optional_field_update(
            request.changes,
            "asset_id",
            existing.asset_id,
        ),
        binding_kind=_change_text(
            request.changes,
            "binding_kind",
            default=existing.binding_kind,
        ),
        source_kind=source_kind,
        source_ref=source_ref,
        masked_preview=_optional_field_update(
            request.changes,
            "masked_preview",
            existing.masked_preview,
        ),
        status=status,
        redaction_policy=dict(existing.redaction_policy),
        metadata=metadata,
    )


def _credential_binding_status_from_changes(
    changes: Mapping[str, Any],
    existing: AccessCredentialBindingRecord,
) -> str:
    if "status" not in changes:
        return existing.status
    status = _change_text(changes, "status").strip().lower()
    if status not in {"active", "disabled", "revoked"}:
        raise ValueError(
            "credential binding status must be active, disabled, or revoked.",
        )
    existing_status = existing.status.strip().lower()
    if existing_status == "revoked" and status != "revoked":
        raise ValueError(
            f"credential binding '{existing.binding_id}' is revoked and cannot be re-enabled.",
        )
    return status


def _optional_field_update(
    changes: Mapping[str, Any],
    key: str,
    current: str | None,
) -> str | None:
    if key not in changes:
        return current
    value = changes.get(key)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_credential_binding_source_kind(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"env", "file", "app_credential", "oauth_account"}:
        raise ValueError(
            "credential binding source_kind must be env, file, app_credential, or oauth_account.",
        )
    return normalized


def _binding_source_ref_change_requested(
    changes: Mapping[str, Any],
    source_kind: str,
) -> bool:
    keys = ["source_ref"]
    if source_kind == "env":
        keys.append("env_name")
    elif source_kind == "file":
        keys.append("path")
    elif source_kind == "oauth_account":
        keys.append("account_id")
    elif source_kind == "app_credential":
        keys.append("app_credential_id")
    return any(key in changes for key in keys)


def _credential_binding_redacted_metadata(
    record: AccessCredentialBindingRecord,
) -> JsonObject:
    return {
        "binding_id": record.binding_id,
        "asset_id": record.asset_id,
        "binding_kind": record.binding_kind,
        "source_kind": record.source_kind,
        "source_ref": _credential_binding_public_source_ref(record),
        "masked_preview": record.masked_preview,
        "status": record.status,
    }


def _credential_binding_public_source_ref(
    record: AccessCredentialBindingRecord,
) -> str:
    source_kind = record.source_kind.strip().lower()
    if source_kind in {"env", "file"}:
        return canonical_credential_binding(f"{source_kind}:{record.source_ref}")
    if source_kind == "oauth_account":
        return record.source_ref
    if source_kind == "app_credential":
        return record.source_ref
    return "***"


def _changed_credential_binding_fields(
    *,
    before_redacted: Mapping[str, Any],
    after_redacted: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    fields = (
        "binding_kind",
        "source_kind",
        "source_ref",
        "asset_id",
        "masked_preview",
        "status",
    )
    return {
        field: {
            "before": before_redacted.get(field),
            "after": after_redacted.get(field),
        }
        for field in fields
        if before_redacted.get(field) != after_redacted.get(field)
    }


def _credential_binding_update_validation_metadata(
    *,
    binding_id: str,
    before_redacted: Mapping[str, Any],
    after_redacted: Mapping[str, Any],
    changed: Mapping[str, Mapping[str, Any]],
) -> JsonObject:
    return {
        "binding_id": binding_id,
        "previous_status": before_redacted.get("status"),
        "status": after_redacted.get("status"),
        "previous_fields": {
            field: values.get("before")
            for field, values in changed.items()
        },
        "updated_fields": {
            field: values.get("after")
            for field, values in changed.items()
        },
        "before_redacted": dict(before_redacted),
        "after_redacted": dict(after_redacted),
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
        str(getattr(existing, attr)) if existing is not None and getattr(existing, attr) else None
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
    return ((_requirement_ref(provider=provider, expected_kind=expected_kind, slot=slot),),)


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


def _change_bool(
    changes: Mapping[str, Any],
    key: str,
    *,
    default: bool,
) -> bool:
    value = changes.get(key)
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"0", "false", "no", "off"}:
            return False
        if normalized in {"1", "true", "yes", "on"}:
            return True
    return bool(value)


def _safe_binding_id_part(value: str) -> str:
    normalized = "".join(
        char if char.isalnum() or char in {"_", "-"} else "_"
        for char in value.strip()
    ).strip("_")
    return normalized or "unknown"


def _binding_source_ref(
    request: AccessSettingsActionRequest,
    source_kind: str,
) -> str:
    if source_kind == "oauth_account":
        return _normalize_binding_source_ref(
            source_kind,
            _change_text(request.changes, "source_ref", "account_id"),
        )
    if source_kind == "app_credential":
        return _normalize_binding_source_ref(
            source_kind,
            _change_text(request.changes, "source_ref", "app_credential_id"),
        )
    return _normalize_binding_source_ref(
        source_kind,
        _change_text(
            request.changes,
            "source_ref",
            "env_name" if source_kind == "env" else "path",
        ),
    )


def _normalize_binding_source_ref(source_kind: str, source_ref: str) -> str:
    normalized_kind = source_kind.strip().lower()
    normalized_ref = source_ref.strip()
    if normalized_kind == "env":
        if normalized_ref.startswith("env:"):
            normalized_ref = canonical_credential_binding(normalized_ref).removeprefix(
                "env:",
            )
    elif normalized_kind == "file":
        if normalized_ref.startswith("file:"):
            normalized_ref = canonical_credential_binding(normalized_ref).removeprefix(
                "file:",
            )
    elif normalized_kind == "oauth_account" and normalized_ref.startswith(
        "oauth_account:",
    ):
        normalized_ref = normalized_ref.removeprefix("oauth_account:").strip()
    elif normalized_kind == "app_credential" and normalized_ref.startswith(
        "app_credential:",
    ):
        normalized_ref = normalized_ref.removeprefix("app_credential:").strip()
    if not normalized_ref:
        raise ValueError("credential binding source_ref is required.")
    return normalized_ref


def _default_binding_kind(source_kind: str) -> str:
    if source_kind == "app_credential":
        return "app_secret"
    if source_kind == "oauth_account":
        return "oauth2_account"
    return "api_key"


def _change_text(
    changes: Mapping[str, Any],
    *keys: str,
    default: str | None = None,
) -> str:
    value = _change_optional_text(changes, *keys)
    if value is not None:
        return value
    if default is not None:
        return default
    joined = " or ".join(keys)
    raise ValueError(f"change field '{joined}' is required.")


def _change_optional_text(changes: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = changes.get(key)
        if value is None:
            continue
        normalized = str(value).strip()
        if normalized:
            return normalized
    return None


def _payload_text(
    payload: Mapping[str, Any],
    *keys: str,
    default: str | None = None,
) -> str:
    value = _payload_optional_text(payload, *keys)
    if value is not None:
        return value
    if default is not None:
        return default
    raise ValueError(f"payload field '{' or '.join(keys)}' is required.")


def _payload_optional_text(payload: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        normalized = str(value).strip()
        if normalized:
            return normalized
    return None


def _payload_object(payload: Mapping[str, Any], key: str) -> JsonObject:
    value = payload.get(key)
    return dict(value) if isinstance(value, Mapping) else {}


def _payload_string_tuple(payload: Mapping[str, Any], key: str) -> tuple[str, ...]:
    return tuple(_string_list(payload.get(key)))


def _payload_requirement_sets(value: object) -> tuple[tuple[str, ...], ...]:
    if isinstance(value, (list, tuple)):
        result: list[tuple[str, ...]] = []
        for item in value:
            strings = tuple(_string_list(item))
            if strings:
                result.append(strings)
        return tuple(result)
    return ()


def _payload_slot_bindings(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, str] = {}
    for slot, binding_id in value.items():
        slot_text = str(slot).strip()
        binding_text = str(binding_id).strip()
        if slot_text and binding_text:
            result[slot_text] = binding_text
    return result


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []
