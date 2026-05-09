from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from uuid import uuid4

from crxzipple.modules.access.application.repositories import (
    AccessAssetRecord,
    AccessConsumerBindingRecord,
    AccessCredentialBindingRecord,
)
from crxzipple.modules.access.application.services import (
    canonical_credential_binding,
    codex_auth_json_path_for_binding,
)
from crxzipple.modules.settings.application.materialization import (
    SettingsEffectiveConfigMaterializer,
)
from crxzipple.modules.settings.application.models import (
    CreateSettingsResourceInput,
    UpdateSettingsResourceInput,
)
from crxzipple.modules.settings.application.services import (
    SettingsActionService,
    SettingsQueryService,
)
from crxzipple.modules.settings.domain import SettingsNotFoundError
from crxzipple.shared.settings import AccessConfig


JsonObject = dict[str, Any]

CONFIG_WRITE_INTENTS = frozenset(
    {
        "register_env_binding",
        "register_file_binding",
        "register_codex_auth_json_binding",
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

    def list_consumer_bindings(self) -> tuple[AccessConsumerBindingRecord, ...]:
        return tuple(
            _consumer_binding_record(item)
            for config in self.configs
            if config.enabled
            for item in config.consumer_bindings
        )


@dataclass(slots=True)
class AccessSettingsConfigProvider:
    query_service: SettingsQueryService | None
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

    def list_assets(self) -> tuple[AccessAssetRecord, ...]:
        return self.view().list_assets()

    def list_credential_bindings(self) -> tuple[AccessCredentialBindingRecord, ...]:
        return self.view().list_credential_bindings()

    def list_consumer_bindings(self) -> tuple[AccessConsumerBindingRecord, ...]:
        return self.view().list_consumer_bindings()


@dataclass(slots=True)
class AccessSettingsActionAdapter:
    action_service: SettingsActionService
    query_service: SettingsQueryService
    environment: str | None = None

    def execute_config_action(
        self,
        request: AccessSettingsActionRequest,
    ) -> AccessSettingsActionResult:
        intent = request.intent.strip()
        if intent == "register_env_binding":
            return self._register_binding(request, source_kind="env")
        if intent == "register_file_binding":
            return self._register_binding(request, source_kind="file")
        if intent == "register_codex_auth_json_binding":
            return self._register_binding(request, source_kind="codex_auth_json")
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


def _binding_source_ref(
    request: AccessSettingsActionRequest,
    source_kind: str,
) -> str:
    if source_kind == "codex_auth_json":
        return _change_text(
            request.changes,
            "source_ref",
            "path",
            default=str(codex_auth_json_path_for_binding("codex_auth_json")),
        )
    return _change_text(
        request.changes,
        "source_ref",
        "env_name" if source_kind == "env" else "path",
    )


def _default_binding_kind(source_kind: str) -> str:
    if source_kind == "file":
        return "credential_file"
    if source_kind == "codex_auth_json":
        return "oauth_token"
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


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []
