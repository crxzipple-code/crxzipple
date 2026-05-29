from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from crxzipple.modules.access.application.inventory import (
    AccessInventoryInput,
    AccessReadinessCheckSpec,
    collect_access_inventory_from_read_models,
)
from crxzipple.modules.access.application.read_models import (
    AccessAssetDetailReadModel,
    AccessConsumerBindingReadModel,
    CredentialBindingReadModel,
)
from crxzipple.modules.access.application.settings_integration import (
    AccessSettingsConfigProvider,
)
from crxzipple.modules.access.interfaces.external_consumers import (
    external_access_consumer_bindings,
)
from crxzipple.modules.access.interfaces.presenters import present_readiness

_ACCESS_SERVICE_KEY = "access.service"
_CORE_SETTINGS_KEY = "core.settings"
_SETTINGS_QUERY_SERVICE_KEY = "settings.query_service"


def collect_access_inventory(
    container: Any,
    *,
    workspace_dir: str | None = None,
    include_ready: bool = False,
    include_disabled: bool = False,
) -> dict[str, object]:
    source = _collect_settings_inventory_input(
        container.require(_SETTINGS_QUERY_SERVICE_KEY),
        environment=container.require(_CORE_SETTINGS_KEY).environment,
    )
    source = _with_external_consumer_bindings(
        source,
        external_access_consumer_bindings(container),
    )
    access_service = container.require(_ACCESS_SERVICE_KEY)
    return collect_access_inventory_from_read_models(
        source,
        check_readiness=_container_readiness_checker(
            access_service,
            workspace_dir=workspace_dir,
        ),
        include_ready=include_ready,
        include_disabled=include_disabled,
    )


def _with_external_consumer_bindings(
    source: AccessInventoryInput,
    external_consumer_bindings: tuple[AccessConsumerBindingReadModel, ...],
) -> AccessInventoryInput:
    if not external_consumer_bindings:
        return source
    return AccessInventoryInput(
        assets=source.assets,
        credential_bindings=source.credential_bindings,
        consumer_bindings=_dedupe_by_attr(
            source.consumer_bindings + external_consumer_bindings,
            "binding_id",
        ),
    )


def _collect_settings_inventory_input(
    settings_query_service: object | None,
    *,
    environment: str | None,
) -> AccessInventoryInput:
    if settings_query_service is None:
        return AccessInventoryInput()
    provider = AccessSettingsConfigProvider(
        settings_query_service,
        environment=environment,
    )
    assets = tuple(_asset_read_model(record) for record in provider.list_assets())
    credential_bindings = tuple(
        _credential_binding_read_model(record)
        for record in provider.list_credential_bindings()
    )
    consumer_bindings = tuple(
        _consumer_binding_read_model(record)
        for record in provider.list_consumer_bindings()
    )
    return AccessInventoryInput(
        assets=_dedupe_by_attr(assets, "asset_id"),
        credential_bindings=_dedupe_by_attr(credential_bindings, "binding_id"),
        consumer_bindings=_dedupe_by_attr(consumer_bindings, "binding_id"),
    )


def _asset_read_model(record: object) -> AccessAssetDetailReadModel:
    return AccessAssetDetailReadModel(
        asset_id=str(getattr(record, "asset_id")),
        asset_kind=str(getattr(record, "asset_kind")),
        display_name=str(getattr(record, "display_name")),
        governance_scope=str(getattr(record, "governance_scope")),
        status=str(getattr(record, "status", "active")),
        secret_policy=dict(getattr(record, "secret_policy", {}) or {}),
        storage_key=getattr(record, "storage_key", None),
        consumer_modules=tuple(getattr(record, "consumer_modules", ()) or ()),
        readiness_policy=dict(getattr(record, "readiness_policy", {}) or {}),
        rotation_policy=dict(getattr(record, "rotation_policy", {}) or {}),
        audit_required=bool(getattr(record, "audit_required", True)),
        export_policy=dict(getattr(record, "export_policy", {}) or {}),
        degraded_reason=getattr(record, "degraded_reason", None),
        metadata=dict(getattr(record, "metadata", {}) or {}),
        created_at=getattr(record, "created_at", None),
        updated_at=getattr(record, "updated_at", None),
    )


def _credential_binding_read_model(record: object) -> CredentialBindingReadModel:
    source_kind = str(getattr(record, "source_kind"))
    source_ref = _credential_source_ref_for_inventory(record)
    return CredentialBindingReadModel(
        binding_id=str(getattr(record, "binding_id")),
        asset_id=getattr(record, "asset_id", None),
        binding_kind=str(getattr(record, "binding_kind")),
        source_kind=source_kind,
        source_ref=source_ref,
        masked_preview=getattr(record, "masked_preview", None),
        status=str(getattr(record, "status", "active")),
        metadata=dict(getattr(record, "metadata", {}) or {}),
        created_at=getattr(record, "created_at", None),
        updated_at=getattr(record, "updated_at", None),
    )


def _consumer_binding_read_model(record: object) -> AccessConsumerBindingReadModel:
    if isinstance(record, AccessConsumerBindingReadModel):
        return record
    return AccessConsumerBindingReadModel(
        binding_id=str(getattr(record, "binding_id")),
        consumer_module=str(getattr(record, "consumer_module")),
        consumer_kind=str(getattr(record, "consumer_kind")),
        consumer_id=str(getattr(record, "consumer_id")),
        display_name=getattr(record, "display_name", None),
        enabled=bool(getattr(record, "enabled", True)),
        asset_id=getattr(record, "asset_id", None),
        credential_binding_id=getattr(record, "credential_binding_id", None),
        requirement_sets=tuple(
            tuple(str(item) for item in requirement_set)
            for requirement_set in getattr(record, "requirement_sets", ()) or ()
        ),
        status=str(getattr(record, "status", "active")),
        metadata=dict(getattr(record, "metadata", {}) or {}),
        created_at=getattr(record, "created_at", None),
        updated_at=getattr(record, "updated_at", None),
    )


def _credential_source_ref_for_inventory(record: object) -> str:
    metadata = getattr(record, "metadata", {}) or {}
    if isinstance(metadata, Mapping):
        canonical_ref = metadata.get("canonical_ref")
        if isinstance(canonical_ref, str) and canonical_ref.strip():
            return canonical_ref.strip()
    source_kind = str(getattr(record, "source_kind")).strip().lower()
    source_ref = str(getattr(record, "source_ref")).strip()
    if source_kind == "env":
        return f"env:{source_ref}" if source_ref else "env:"
    if source_kind == "file":
        return f"file:{source_ref}" if source_ref else "file:"
    return source_ref


def _dedupe_by_attr(items: tuple[Any, ...], attr_name: str) -> tuple[Any, ...]:
    keyed: dict[str, Any] = {}
    for item in items:
        key = str(getattr(item, attr_name, "") or "").strip()
        if not key:
            continue
        keyed.setdefault(key, item)
    return tuple(keyed.values())


def _container_readiness_checker(
    access_service: Any,
    *,
    workspace_dir: str | None,
) -> Callable[[tuple[AccessReadinessCheckSpec, ...]], tuple[dict[str, object], ...]]:
    def check(
        specs: tuple[AccessReadinessCheckSpec, ...],
    ) -> tuple[dict[str, object], ...]:
        checks: list[dict[str, object]] = []
        for target_type, raw, allow_literal in specs:
            if target_type == "credential_binding":
                readiness = access_service.check_credential_binding(
                    raw,
                    workspace_dir=workspace_dir,
                    allow_literal=allow_literal,
                )
            else:
                readiness = access_service.check_requirement(
                    raw,
                    workspace_dir=workspace_dir,
                )
            checks.append(present_readiness(readiness, target_type=target_type))
        return tuple(checks)

    return check
