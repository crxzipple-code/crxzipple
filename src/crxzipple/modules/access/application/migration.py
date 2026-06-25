from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from crxzipple.modules.access.application.migration_requirement_payloads import (
    channel_metadata_requirements as _channel_metadata_requirements,
    credential_binding_for_migration_requirement as _credential_binding_for_migration_requirement,
    credential_source as _credential_source,
    digest as _digest,
    masked_requirement_sets as _masked_requirement_sets,
    normalize_requirement_sets as _normalize_requirement_sets,
    redaction_policy as _redaction_policy,
    requirement_display as _requirement_display,
    requirement_sets_from_tool as _requirement_sets_from_tool,
    slugify as _slugify,
)
from crxzipple.modules.access.application.inventory_redaction import (
    sanitize_access_metadata,
)
from crxzipple.modules.access.application.migration_value_helpers import (
    bool_value as _bool_value,
    dedupe_legacy_items as _dedupe_legacy_items,
    get_value as _get_value,
    legacy_list as _legacy_list,
    mapping_value as _mapping_value,
    optional_string as _optional_string,
    safe_public_string as _safe_public_string,
    string_value as _string_value,
)
from crxzipple.modules.access.application.read_models import (
    AccessConsumerBindingReadModel,
)
from crxzipple.modules.access.application.repositories import (
    AccessAssetRecord,
    AccessCredentialBindingRecord,
)
from crxzipple.modules.access.domain.resources import AccessResourceKind


@dataclass(frozen=True, slots=True)
class AccessMigrationSnapshot:
    llm_profiles: tuple[object, ...] = ()
    tool_specs: tuple[object, ...] = ()
    channel_profiles: tuple[object, ...] = ()
    ready_auth_requirements: tuple[str, ...] = ()
    ready_auth_requirements_env: str | None = None
    source: str = "legacy"


@dataclass(frozen=True, slots=True)
class AccessMigrationPlan:
    assets: tuple[AccessAssetRecord, ...] = ()
    credential_bindings: tuple[AccessCredentialBindingRecord, ...] = ()
    consumer_bindings: tuple[AccessConsumerBindingReadModel, ...] = ()
    provider_scope_enablements: tuple[Mapping[str, object], ...] = ()
    permission_enablements: tuple[Mapping[str, object], ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)


class AccessMigration:
    def build_plan(self, snapshot: AccessMigrationSnapshot) -> AccessMigrationPlan:
        return build_access_migration_plan(snapshot)

    @classmethod
    def from_legacy_container(cls, container: object) -> AccessMigrationSnapshot:
        settings = _get_value(container, "settings")
        llm_profiles = _dedupe_legacy_items(
            (
                *tuple(_get_value(settings, "llm_profiles", ()) or ()),
                *_legacy_list(_get_value(container, "llm_service"), ("list_profiles",)),
            ),
            identity_name="id",
        )
        tool_service = _get_value(container, "tool_service")
        channel_service = _get_value(container, "channel_profile_service")
        return AccessMigrationSnapshot(
            llm_profiles=llm_profiles,
            tool_specs=_legacy_list(tool_service, ("list_specs", "list_tools")),
            channel_profiles=_legacy_list(channel_service, ("list_profiles",)),
            ready_auth_requirements=tuple(
                _get_value(settings, "ready_auth_requirements", ()) or (),
            ),
            source="legacy_container",
        )


def build_access_migration_plan(
    snapshot: AccessMigrationSnapshot,
) -> AccessMigrationPlan:
    builder = _AccessMigrationPlanBuilder(snapshot.source)
    for profile in snapshot.llm_profiles:
        builder.add_llm_profile(profile)
    for tool in snapshot.tool_specs:
        builder.add_tool_spec(tool)
    for profile in snapshot.channel_profiles:
        builder.add_channel_profile(profile)
    builder.add_ready_auth_requirements(
        snapshot.ready_auth_requirements,
        env_value=snapshot.ready_auth_requirements_env,
    )
    return builder.build()


class _AccessMigrationPlanBuilder:
    def __init__(self, source: str) -> None:
        self._source = source
        self._assets: dict[str, AccessAssetRecord] = {}
        self._credential_bindings: dict[str, AccessCredentialBindingRecord] = {}
        self._consumer_bindings: dict[str, AccessConsumerBindingReadModel] = {}

    def add_llm_profile(self, profile: object) -> None:
        profile_id = _string_value(profile, "id")
        binding_id = _optional_string(_get_value(profile, "credential_binding_id"))
        if not profile_id or not binding_id:
            return
        self._ensure_consumer_binding(
            consumer_module="llm",
            consumer_kind="llm_profile",
            consumer_id=profile_id,
            display_name=_optional_string(_get_value(profile, "model_name")) or profile_id,
            enabled=_bool_value(profile, "enabled", default=True),
            credential_binding_id=binding_id,
            requirement_sets=(),
            metadata={
                "source": self._source,
                "source_path": "llm_profiles[*].credential_binding_id",
                "provider": _safe_public_string(_get_value(profile, "provider")),
                "api_family": _safe_public_string(_get_value(profile, "api_family")),
            },
        )

    def add_tool_spec(self, tool: object) -> None:
        tool_id = _string_value(tool, "id")
        requirement_sets = _requirement_sets_from_tool(tool)
        if not tool_id or not requirement_sets:
            return
        asset_id = self._ensure_access_requirement_asset(
            requirement_sets,
            consumer_module="tool",
            source_path="tool.access_requirement_sets",
        )
        for requirement_set in requirement_sets:
            for requirement in requirement_set:
                self._ensure_requirement_resources(
                    requirement,
                    consumer_module="tool",
                    source_path="tool.access_requirement_sets",
                )
        self._ensure_consumer_binding(
            consumer_module="tool",
            consumer_kind="tool",
            consumer_id=tool_id,
            display_name=_optional_string(_get_value(tool, "name")) or tool_id,
            enabled=_bool_value(tool, "enabled", default=True),
            requirement_sets=requirement_sets,
            asset_id=asset_id,
            metadata={
                "source": self._source,
                "source_path": "tool.access_requirement_sets",
                "provider_name": _safe_public_string(_get_value(tool, "provider_name")),
            },
        )

    def add_channel_profile(self, profile: object) -> None:
        channel_type = _string_value(profile, "channel_type")
        if not channel_type:
            return
        profile_requirements = _channel_metadata_requirements(
            _mapping_value(_get_value(profile, "metadata")),
        )
        if profile_requirements:
            self._add_channel_consumer(
                channel_type=channel_type,
                consumer_kind="channel_profile",
                consumer_id=channel_type,
                enabled=_bool_value(profile, "enabled", default=True),
                requirement_sets=(profile_requirements,),
                source_path="channel_profile.metadata",
            )
        for account in tuple(_get_value(profile, "accounts", ()) or ()):
            if not _bool_value(account, "enabled", default=True):
                continue
            account_id = _string_value(account, "account_id")
            requirements = list(
                _channel_metadata_requirements(
                    _mapping_value(_get_value(account, "metadata")),
                ),
            )
            auth_ref = _optional_string(_get_value(account, "auth_ref"))
            if auth_ref and auth_ref not in requirements:
                requirements.append(auth_ref)
            if requirements:
                self._add_channel_consumer(
                    channel_type=channel_type,
                    consumer_kind="channel_account",
                    consumer_id=f"{channel_type}:{account_id or 'default'}",
                    enabled=True,
                    requirement_sets=(tuple(requirements),),
                    source_path="channel_profile.accounts.metadata",
                )

    def add_ready_auth_requirements(
        self,
        requirements: tuple[str, ...],
        *,
        env_value: str | None,
    ) -> None:
        resolved = list(requirements)
        if env_value:
            resolved.extend(item.strip() for item in env_value.split(","))
        requirement_set = tuple(dict.fromkeys(item for item in resolved if item))
        if not requirement_set:
            return
        asset_id = self._ensure_access_requirement_asset(
            (requirement_set,),
            consumer_module="access",
            source_path="CRXZIPPLE_READY_AUTH_REQUIREMENTS",
        )
        for requirement in requirement_set:
            self._ensure_requirement_resources(
                requirement,
                consumer_module="access",
                source_path="CRXZIPPLE_READY_AUTH_REQUIREMENTS",
            )
        self._ensure_consumer_binding(
            consumer_module="access",
            consumer_kind="environment_ready_requirement",
            consumer_id="CRXZIPPLE_READY_AUTH_REQUIREMENTS",
            display_name="Ready access requirements",
            requirement_sets=(requirement_set,),
            asset_id=asset_id,
            metadata={
                "source": self._source,
                "source_path": "CRXZIPPLE_READY_AUTH_REQUIREMENTS",
            },
        )

    def build(self) -> AccessMigrationPlan:
        return AccessMigrationPlan(
            assets=tuple(self._assets[key] for key in sorted(self._assets)),
            credential_bindings=tuple(
                self._credential_bindings[key]
                for key in sorted(self._credential_bindings)
            ),
            consumer_bindings=tuple(
                self._consumer_bindings[key]
                for key in sorted(self._consumer_bindings)
            ),
            provider_scope_enablements=(),
            permission_enablements=(),
            metadata={
                "source": self._source,
                "asset_count": len(self._assets),
                "credential_binding_count": len(self._credential_bindings),
                "consumer_binding_count": len(self._consumer_bindings),
            },
        )

    def _add_channel_consumer(
        self,
        *,
        channel_type: str,
        consumer_kind: str,
        consumer_id: str,
        enabled: bool,
        requirement_sets: tuple[tuple[str, ...], ...],
        source_path: str,
    ) -> None:
        asset_id = self._ensure_access_requirement_asset(
            requirement_sets,
            consumer_module="channels",
            source_path=source_path,
        )
        for requirement_set in requirement_sets:
            for requirement in requirement_set:
                self._ensure_requirement_resources(
                    requirement,
                    consumer_module="channels",
                    source_path=source_path,
                )
        self._ensure_consumer_binding(
            consumer_module="channels",
            consumer_kind=consumer_kind,
            consumer_id=consumer_id,
            display_name=consumer_id,
            enabled=enabled,
            requirement_sets=requirement_sets,
            asset_id=asset_id,
            metadata={
                "source": self._source,
                "source_path": source_path,
                "channel_type": channel_type,
            },
        )

    def _ensure_requirement_resources(
        self,
        requirement: str,
        *,
        consumer_module: str,
        source_path: str,
    ) -> None:
        binding = _credential_binding_for_migration_requirement(requirement)
        if binding is not None:
            self._ensure_credential_binding(
                binding,
                consumer_module=consumer_module,
                source_path=source_path,
            )
            return
        self._ensure_access_requirement_asset(
            ((requirement,),),
            consumer_module=consumer_module,
            source_path=source_path,
        )

    def _ensure_credential_binding(
        self,
        binding: str,
        *,
        consumer_module: str,
        source_path: str,
    ) -> AccessCredentialBindingRecord:
        source = _credential_source(binding)
        asset_id = f"access_asset:credential:{source.identity}"
        binding_id = f"credential_binding:{source.identity}"
        self._ensure_asset(
            AccessAssetRecord(
                asset_id=asset_id,
                asset_kind=AccessResourceKind.CREDENTIAL_BINDING.value,
                display_name=source.display_name,
                governance_scope="module",
                secret_policy={
                    "storage_mode": "binding_only",
                    "secret_material_allowed": False,
                    "masked_preview_required": True,
                },
                consumer_modules=(consumer_module,),
                readiness_policy={"checks": ("credential_binding",)},
                export_policy={"exportable": True, "include_masked_metadata": True},
                redaction_policy=_redaction_policy(),
                metadata={
                    "source": self._source,
                    "source_path": source_path,
                    "source_kind": source.source_kind,
                    "source_ref": source.source_ref,
                    "masked_preview": source.masked_preview,
                },
            ),
        )
        record = self._credential_bindings.get(binding_id)
        if record is not None:
            return record
        record = AccessCredentialBindingRecord(
            binding_id=binding_id,
            asset_id=asset_id,
            binding_kind=source.binding_kind,
            source_kind=source.source_kind,
            source_ref=source.source_ref,
            masked_preview=source.masked_preview,
            redaction_policy=_redaction_policy(),
            metadata={
                "source": self._source,
                "source_path": source_path,
                "canonical_ref": source.canonical_ref,
            },
        )
        self._credential_bindings[binding_id] = record
        return record

    def _ensure_access_requirement_asset(
        self,
        requirement_sets: tuple[tuple[str, ...], ...],
        *,
        consumer_module: str,
        source_path: str,
    ) -> str:
        normalized_sets = _normalize_requirement_sets(requirement_sets)
        digest = _digest(repr(normalized_sets))
        asset_id = f"access_asset:requirement:{digest}"
        display = _requirement_display(normalized_sets)
        self._ensure_asset(
            AccessAssetRecord(
                asset_id=asset_id,
                asset_kind=AccessResourceKind.ACCESS_REQUIREMENT.value,
                display_name=display,
                governance_scope="module",
                secret_policy={"storage_mode": "none", "secret_material_allowed": False},
                consumer_modules=(consumer_module,),
                readiness_policy={"requirement_sets": _masked_requirement_sets(normalized_sets)},
                export_policy={"exportable": True, "include_masked_metadata": True},
                redaction_policy=_redaction_policy(),
                metadata={
                    "source": self._source,
                    "source_path": source_path,
                    "requirement_sets": _masked_requirement_sets(normalized_sets),
                },
            ),
        )
        return asset_id

    def _ensure_consumer_binding(
        self,
        *,
        consumer_module: str,
        consumer_kind: str,
        consumer_id: str,
        display_name: str | None = None,
        enabled: bool = True,
        asset_id: str | None = None,
        credential_binding_id: str | None = None,
        requirement_sets: tuple[tuple[str, ...], ...] = (),
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        binding_id = (
            f"consumer_binding:{consumer_module}:{consumer_kind}:"
            f"{_slugify(consumer_id)}:{_digest(consumer_id)}"
        )
        self._consumer_bindings[binding_id] = AccessConsumerBindingReadModel(
            binding_id=binding_id,
            consumer_module=consumer_module,
            consumer_kind=consumer_kind,
            consumer_id=consumer_id,
            display_name=display_name,
            enabled=enabled,
            asset_id=asset_id,
            credential_binding_id=credential_binding_id,
            requirement_sets=_masked_requirement_sets(
                _normalize_requirement_sets(requirement_sets),
            ),
            metadata=sanitize_access_metadata(dict(metadata or {})),
        )

    def _ensure_asset(self, record: AccessAssetRecord) -> None:
        existing = self._assets.get(record.asset_id)
        if existing is None:
            self._assets[record.asset_id] = record
            return
        modules = tuple(
            dict.fromkeys((*existing.consumer_modules, *record.consumer_modules)),
        )
        metadata = dict(existing.metadata)
        metadata.update(record.metadata)
        self._assets[record.asset_id] = AccessAssetRecord(
            asset_id=existing.asset_id,
            asset_kind=existing.asset_kind,
            display_name=existing.display_name,
            governance_scope=existing.governance_scope,
            status=existing.status,
            secret_policy=existing.secret_policy,
            storage_key=existing.storage_key,
            consumer_modules=modules,
            readiness_policy=existing.readiness_policy,
            rotation_policy=existing.rotation_policy,
            audit_required=existing.audit_required,
            export_policy=existing.export_policy,
            degraded_reason=existing.degraded_reason,
            redaction_policy=existing.redaction_policy,
            metadata=metadata,
            created_at=existing.created_at,
            updated_at=existing.updated_at,
        )
