from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
import hashlib
from typing import Any, Mapping

from crxzipple.modules.access.application.migration import (
    AccessMigration,
    AccessMigrationPlan,
)
from crxzipple.modules.access.application.repositories import (
    AccessConsumerBindingRecord,
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


JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class AccessBootstrapImportResult:
    created: JsonObject = field(default_factory=dict)
    skipped: JsonObject = field(default_factory=dict)
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AccessSettingsBootstrapImportResult:
    imported_counts: JsonObject = field(default_factory=dict)
    created: int = 0
    updated: int = 0
    skipped: int = 0
    audit_refs: tuple[str, ...] = ()
    metadata: JsonObject = field(default_factory=dict)

    def to_payload(self) -> JsonObject:
        return {
            "imported_counts": dict(self.imported_counts),
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "audit_refs": list(self.audit_refs),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class AccessBootstrapImporter:
    repository: object

    def import_from_legacy_container(
        self,
        container: object,
    ) -> AccessBootstrapImportResult:
        snapshot = AccessMigration.from_legacy_container(container)
        plan = AccessMigration().build_plan(snapshot)
        return self.import_plan(plan)

    def import_plan(self, plan: AccessMigrationPlan) -> AccessBootstrapImportResult:
        created = _empty_counts()
        skipped = _empty_counts()

        for asset in plan.assets:
            if self._exists("get_asset", asset.asset_id):
                skipped["assets"] += 1
                continue
            self.repository.create_asset(asset)
            created["assets"] += 1

        for binding in plan.credential_bindings:
            if self._exists("get_credential_binding", binding.binding_id):
                skipped["credential_bindings"] += 1
                continue
            self.repository.create_credential_binding(binding)
            created["credential_bindings"] += 1

        for binding in plan.consumer_bindings:
            if self._exists("get_consumer_binding", binding.binding_id):
                skipped["consumer_bindings"] += 1
                continue
            self.repository.create_consumer_binding(_consumer_record(binding))
            created["consumer_bindings"] += 1

        return AccessBootstrapImportResult(
            created=created,
            skipped=skipped,
            metadata={
                "source": plan.metadata.get("source", "legacy"),
                "plan": dict(plan.metadata),
            },
        )

    def _exists(self, method_name: str, record_id: str) -> bool:
        method = getattr(self.repository, method_name, None)
        if not callable(method):
            return False
        return method(record_id) is not None


@dataclass(frozen=True, slots=True)
class _AccessSettingsResourceSeed:
    resource_id: str
    display_name: str
    payload: JsonObject


@dataclass(slots=True)
class AccessSettingsBootstrapImporter:
    action_service: SettingsActionService
    query_service: SettingsQueryService

    def import_from_legacy_container(
        self,
        container: object,
        *,
        actor: str | None = None,
        reason: str = "import access settings resources",
    ) -> AccessSettingsBootstrapImportResult:
        snapshot = AccessMigration.from_legacy_container(container)
        plan = AccessMigration().build_plan(snapshot)
        return self.import_plan(plan, actor=actor, reason=reason)

    def import_plan(
        self,
        plan: AccessMigrationPlan,
        *,
        actor: str | None = None,
        reason: str = "import access settings resources",
    ) -> AccessSettingsBootstrapImportResult:
        counts = _empty_settings_counts()
        created = 0
        updated = 0
        skipped = 0
        audit_refs: list[str] = []

        for seed in _settings_resource_seeds_from_plan(plan):
            declaration_kind = str(seed.payload.get("access_declaration_kind") or "")
            bucket = _settings_count_bucket(declaration_kind)
            desired_enabled = _desired_resource_enabled(seed.payload)
            counts["access-assets"] = counts.get("access-assets", 0) + 1
            if bucket != "access-assets":
                counts[bucket] = counts.get(bucket, 0) + 1
            existing = self._existing(seed.resource_id)
            if existing is None:
                result = self.action_service.create_resource(
                    CreateSettingsResourceInput(
                        resource_id=seed.resource_id,
                        resource_kind="access-assets",
                        owner_module="access",
                        payload=seed.payload,
                        display_name=seed.display_name,
                        actor=actor,
                        reason=reason,
                        publish=True,
                        source="access_settings_import",
                        metadata={"access_declaration_kind": declaration_kind},
                    ),
                )
                created += 1
                audit_refs.append(result.audit_ref)
                audit_refs.extend(
                    self._sync_enablement(
                        seed.resource_id,
                        desired_enabled,
                        actor=actor,
                        reason=reason,
                    ),
                )
                continue
            if existing.resource_kind != "access-assets":
                skipped += 1
                continue
            if self._effective_payload_matches(seed.resource_id, seed.payload):
                skipped += 1
                continue
            result = self.action_service.update_resource(
                UpdateSettingsResourceInput(
                    resource_id=seed.resource_id,
                    payload=seed.payload,
                    actor=actor,
                    reason=reason,
                    publish=True,
                    source="access_settings_import",
                    metadata={"access_declaration_kind": declaration_kind},
                ),
            )
            updated += 1
            audit_refs.append(result.audit_ref)
            audit_refs.extend(
                self._sync_enablement(
                    seed.resource_id,
                    desired_enabled,
                    actor=actor,
                    reason=reason,
                ),
            )

        return AccessSettingsBootstrapImportResult(
            imported_counts=counts,
            created=created,
            updated=updated,
            skipped=skipped,
            audit_refs=tuple(audit_refs),
            metadata={"source": plan.metadata.get("source", "legacy")},
        )

    def _existing(self, resource_id: str):
        try:
            return self.query_service.get_resource(resource_id)
        except SettingsNotFoundError:
            return None

    def _effective_payload_matches(
        self,
        resource_id: str,
        expected: JsonObject,
    ) -> bool:
        try:
            effective = dict(self.query_service.get_effective(resource_id).effective_value)
        except SettingsNotFoundError:
            return False
        if "enabled" not in expected:
            effective.pop("enabled", None)
        return effective == expected

    def _sync_enablement(
        self,
        resource_id: str,
        desired_enabled: bool | None,
        *,
        actor: str | None,
        reason: str,
    ) -> tuple[str, ...]:
        if desired_enabled is None:
            return ()
        resource = self.query_service.get_resource(resource_id)
        if resource.enabled == desired_enabled:
            return ()
        if desired_enabled:
            result = self.action_service.enable_resource(
                resource_id,
                actor=actor,
                reason=reason,
            )
        else:
            result = self.action_service.disable_resource(
                resource_id,
                actor=actor,
                reason=reason,
            )
        return (result.audit_ref,)


def _consumer_record(binding: object) -> AccessConsumerBindingRecord:
    return AccessConsumerBindingRecord(
        binding_id=str(getattr(binding, "binding_id")),
        consumer_module=str(getattr(binding, "consumer_module")),
        consumer_kind=str(getattr(binding, "consumer_kind")),
        consumer_id=str(getattr(binding, "consumer_id")),
        display_name=getattr(binding, "display_name", None),
        enabled=bool(getattr(binding, "enabled", True)),
        asset_id=getattr(binding, "asset_id", None),
        credential_binding_id=getattr(binding, "credential_binding_id", None),
        requirement_sets=tuple(
            tuple(str(item) for item in requirement_set)
            for requirement_set in getattr(binding, "requirement_sets", ())
        ),
        status=str(getattr(binding, "status", "active")),
        metadata=dict(getattr(binding, "metadata", {}) or {}),
        created_at=getattr(binding, "created_at", None),
        updated_at=getattr(binding, "updated_at", None),
    )


def _empty_counts() -> dict[str, int]:
    return {
        "assets": 0,
        "credential_bindings": 0,
        "consumer_bindings": 0,
    }


def _empty_settings_counts() -> dict[str, int]:
    return {
        "access-assets": 0,
        "assets": 0,
        "credential_bindings": 0,
        "consumer_bindings": 0,
        "provider_scope_enablements": 0,
        "permission_enablements": 0,
    }


def _settings_count_bucket(declaration_kind: str) -> str:
    return {
        "asset": "assets",
        "credential_binding": "credential_bindings",
        "consumer_binding": "consumer_bindings",
        "provider_scope_enablement": "provider_scope_enablements",
        "permission_enablement": "permission_enablements",
    }.get(declaration_kind, "access-assets")


def _desired_resource_enabled(payload: Mapping[str, object]) -> bool | None:
    value = payload.get("enabled")
    return value if isinstance(value, bool) else None


def _settings_resource_seeds_from_plan(
    plan: AccessMigrationPlan,
) -> tuple[_AccessSettingsResourceSeed, ...]:
    seeds: list[_AccessSettingsResourceSeed] = []
    seeds.extend(
        _AccessSettingsResourceSeed(
            resource_id=f"access:asset:{asset.asset_id}",
            display_name=asset.display_name,
            payload={
                "access_declaration_kind": "asset",
                **_record_payload(asset),
            },
        )
        for asset in plan.assets
    )
    seeds.extend(
        _AccessSettingsResourceSeed(
            resource_id=f"access:credential:{binding.binding_id}",
            display_name=binding.binding_id,
            payload={
                "access_declaration_kind": "credential_binding",
                **_record_payload(binding),
            },
        )
        for binding in plan.credential_bindings
    )
    seeds.extend(
        _AccessSettingsResourceSeed(
            resource_id=f"access:consumer:{binding.binding_id}",
            display_name=binding.display_name or binding.binding_id,
            payload={
                "access_declaration_kind": "consumer_binding",
                **_record_payload(binding),
            },
        )
        for binding in plan.consumer_bindings
    )
    seeds.extend(
        _mapping_seed(
            declaration_kind="provider_scope_enablement",
            prefix="access:provider-scope",
            payload=payload,
            id_keys=("id", "provider_scope_id", "provider_id", "scope"),
        )
        for payload in plan.provider_scope_enablements
    )
    seeds.extend(
        _mapping_seed(
            declaration_kind="permission_enablement",
            prefix="access:permission",
            payload=payload,
            id_keys=("id", "permission_id", "permission", "scope"),
        )
        for payload in plan.permission_enablements
    )
    return tuple(seeds)


def _mapping_seed(
    *,
    declaration_kind: str,
    prefix: str,
    payload: object,
    id_keys: tuple[str, ...],
) -> _AccessSettingsResourceSeed:
    value = dict(payload) if isinstance(payload, Mapping) else {}
    identity = ":".join(
        str(value[key]).strip()
        for key in id_keys
        if value.get(key) is not None and str(value[key]).strip()
    )
    if not identity:
        identity = _digest(repr(sorted(value.items())))
    return _AccessSettingsResourceSeed(
        resource_id=f"{prefix}:{identity}",
        display_name=identity,
        payload={"access_declaration_kind": declaration_kind, **value},
    )


def _record_payload(record: object) -> JsonObject:
    if is_dataclass(record):
        return {
            item.name: _plain_value(getattr(record, item.name))
            for item in fields(record)
            if _plain_value(getattr(record, item.name)) is not None
        }
    if hasattr(record, "to_payload") and callable(record.to_payload):
        return dict(record.to_payload())
    if isinstance(record, Mapping):
        return dict(record)
    return {
        key: _plain_value(value)
        for key, value in vars(record).items()
        if _plain_value(value) is not None
    }


def _plain_value(value: object) -> object:
    if value is None:
        return None
    if is_dataclass(value):
        return _record_payload(value)
    if isinstance(value, dict):
        return {str(key): _plain_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain_value(item) for item in value]
    if isinstance(value, list):
        return [_plain_value(item) for item in value]
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return isoformat()
    return value


def _digest(value: str, *, length: int = 16) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]
