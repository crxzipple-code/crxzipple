from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from crxzipple.modules.access.application.inventory import (
    AccessInventoryInput,
    AccessReadinessCheckSpec,
    collect_access_inventory_from_read_models,
)
from crxzipple.modules.access.application.migration import (
    AccessMigration,
    AccessMigrationSnapshot,
)
from crxzipple.modules.access.application.read_models import (
    AccessAssetDetailReadModel,
    AccessConsumerBindingReadModel,
    CredentialBindingReadModel,
)
from crxzipple.modules.access.application.settings_integration import (
    AccessSettingsConfigProvider,
)
from crxzipple.modules.settings.application import SettingsEffectiveConfigMaterializer
from crxzipple.modules.access.interfaces.presenters import present_readiness


def collect_access_inventory(
    container: Any,
    *,
    workspace_dir: str | None = None,
    include_ready: bool = False,
    include_disabled: bool = False,
) -> dict[str, object]:
    source = _collect_settings_inventory_input(
        getattr(container, "settings_query_service", None),
        environment=getattr(getattr(container, "settings", None), "environment", None),
    )
    return collect_access_inventory_from_read_models(
        source,
        check_readiness=_container_readiness_checker(
            container,
            workspace_dir=workspace_dir,
        ),
        include_ready=include_ready,
        include_disabled=include_disabled,
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
    inferred = _infer_access_inventory_from_settings_profiles(
        settings_query_service,
        environment=environment,
    )
    return AccessInventoryInput(
        assets=_dedupe_by_attr(
            (*assets, *inferred.assets),
            "asset_id",
        ),
        credential_bindings=_dedupe_by_attr(
            (*credential_bindings, *inferred.credential_bindings),
            "binding_id",
        ),
        consumer_bindings=_dedupe_by_attr(
            (*consumer_bindings, *inferred.consumer_bindings),
            "binding_id",
        ),
    )


def _infer_access_inventory_from_settings_profiles(
    settings_query_service: object,
    *,
    environment: str | None,
) -> AccessInventoryInput:
    materializer = SettingsEffectiveConfigMaterializer(
        settings_query_service,
        environment=environment,
    )
    llm_profiles = _dedupe_profile_payloads(
        *(
            _llm_profile_payload(profile)
            for profile in materializer.legacy_llm_profile_payloads()
        ),
    )
    if not llm_profiles:
        return AccessInventoryInput()
    plan = AccessMigration().build_plan(
        AccessMigrationSnapshot(
            llm_profiles=llm_profiles,
            source="settings",
        ),
    )
    return AccessInventoryInput(
        assets=tuple(_asset_read_model(record) for record in plan.assets),
        credential_bindings=tuple(
            _credential_binding_read_model(record)
            for record in plan.credential_bindings
        ),
        consumer_bindings=tuple(
            _consumer_binding_read_model(record) for record in plan.consumer_bindings
        ),
    )


def _llm_profile_payload(profile: object) -> dict[str, object]:
    if isinstance(profile, Mapping):
        return {
            "id": str(profile.get("profile_id") or profile.get("id") or "").strip(),
            "enabled": bool(profile.get("enabled", True)),
            "credential_binding": profile.get("credential_binding"),
            "model_name": profile.get("model_name"),
            "provider": profile.get("provider"),
            "api_family": profile.get("api_family"),
        }
    profile_id = str(
        getattr(profile, "profile_id", None) or getattr(profile, "id", None) or "",
    ).strip()
    credential_binding = getattr(profile, "credential_binding", None)
    return {
        "id": profile_id,
        "enabled": bool(getattr(profile, "enabled", True)),
        "credential_binding": credential_binding,
        "model_name": getattr(profile, "model_name", None),
        "provider": getattr(profile, "provider", None),
        "api_family": getattr(profile, "api_family", None),
    }


def _dedupe_profile_payloads(
    *profiles: dict[str, object]
) -> tuple[dict[str, object], ...]:
    keyed: dict[str, dict[str, object]] = {}
    for profile in profiles:
        profile_id = str(profile.get("id") or "").strip()
        credential_binding = str(profile.get("credential_binding") or "").strip()
        if not profile_id or not credential_binding:
            continue
        keyed.setdefault(profile_id, profile)
    return tuple(keyed.values())


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
    if source_kind == "codex_auth_json":
        return f"codex_auth_json:{source_ref}" if source_ref else "codex_auth_json"
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
    container: Any,
    *,
    workspace_dir: str | None,
) -> Callable[[tuple[AccessReadinessCheckSpec, ...]], tuple[dict[str, object], ...]]:
    def check(
        specs: tuple[AccessReadinessCheckSpec, ...],
    ) -> tuple[dict[str, object], ...]:
        checks: list[dict[str, object]] = []
        for target_type, raw, allow_literal in specs:
            if target_type == "credential_binding":
                readiness = container.access_service.check_credential_binding(
                    raw,
                    workspace_dir=workspace_dir,
                    allow_literal=allow_literal,
                )
            else:
                readiness = container.access_service.check_requirement(
                    raw,
                    workspace_dir=workspace_dir,
                )
            checks.append(present_readiness(readiness, target_type=target_type))
        return tuple(checks)

    return check
