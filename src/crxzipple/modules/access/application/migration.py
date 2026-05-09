from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
from typing import Any, Mapping

from crxzipple.modules.access.application.inventory import (
    credential_binding_for_requirement,
    sanitize_access_metadata,
)
from crxzipple.modules.access.application.read_models import (
    AccessConsumerBindingReadModel,
)
from crxzipple.modules.access.application.repositories import (
    AccessAssetRecord,
    AccessCredentialBindingRecord,
)
from crxzipple.modules.access.application.services import (
    canonical_credential_binding,
    is_codex_auth_json_binding,
    is_credential_binding,
)
from crxzipple.modules.access.domain.resources import AccessResourceKind


JsonObject = dict[str, Any]
_SENSITIVE_CHANNEL_KEYS = (
    "api_key",
    "auth",
    "credential",
    "password",
    "secret",
    "signing",
    "token",
    "webhook",
)


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
        binding = _optional_string(_get_value(profile, "credential_binding"))
        if not profile_id or not binding:
            return
        credential = self._ensure_credential_binding(
            binding,
            consumer_module="llm",
            source_path="llm_profiles.credential_binding",
        )
        self._ensure_consumer_binding(
            consumer_module="llm",
            consumer_kind="llm_profile",
            consumer_id=profile_id,
            display_name=_optional_string(_get_value(profile, "model_name")) or profile_id,
            enabled=_bool_value(profile, "enabled", default=True),
            credential_binding_id=credential.binding_id,
            requirement_sets=(),
            asset_id=credential.asset_id,
            metadata={
                "source": self._source,
                "source_path": "llm_profiles[*].credential_binding",
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


@dataclass(frozen=True, slots=True)
class _CredentialSource:
    identity: str
    binding_kind: str
    source_kind: str
    source_ref: str
    canonical_ref: str
    masked_preview: str
    display_name: str


def _credential_source(binding: str) -> _CredentialSource:
    normalized = binding.strip()
    if is_credential_binding(normalized):
        canonical = canonical_credential_binding(normalized)
        if canonical.startswith("env:"):
            env_name = canonical.removeprefix("env:").strip()
            identity = f"env:{_digest(env_name)}"
            return _CredentialSource(
                identity=identity,
                binding_kind="credential_binding",
                source_kind="env",
                source_ref=env_name,
                canonical_ref=canonical,
                masked_preview=f"env:{env_name}",
                display_name=f"Environment credential {env_name}",
            )
        if canonical.startswith("file:"):
            path_ref = canonical.removeprefix("file:").strip()
            identity = f"file:{_digest(path_ref)}"
            return _CredentialSource(
                identity=identity,
                binding_kind="credential_binding",
                source_kind="file",
                source_ref=path_ref,
                canonical_ref=canonical,
                masked_preview="file:***",
                display_name="File credential",
            )
        if is_codex_auth_json_binding(canonical):
            source_ref = canonical.removeprefix("codex_auth_json:").strip()
            identity = f"codex_auth_json:{_digest(canonical)}"
            return _CredentialSource(
                identity=identity,
                binding_kind="credential_binding",
                source_kind="codex_auth_json",
                source_ref=source_ref,
                canonical_ref=canonical,
                masked_preview=(
                    "codex_auth_json:***" if source_ref else "codex_auth_json"
                ),
                display_name="Codex auth json credential",
            )
    literal_hash = _digest(normalized, length=16)
    return _CredentialSource(
        identity=f"literal:{literal_hash}",
        binding_kind="literal_ref",
        source_kind="literal",
        source_ref=f"sha256:{literal_hash}",
        canonical_ref=f"literal:sha256:{literal_hash}",
        masked_preview="literal:***",
        display_name="Inline literal credential",
    )


def _channel_metadata_requirements(metadata: Mapping[str, object]) -> tuple[str, ...]:
    requirements: list[str] = []
    raw_requirements = metadata.get("access_requirements")
    if isinstance(raw_requirements, (list, tuple)):
        for item in raw_requirements:
            _append_requirement(requirements, item)
    for key, value in metadata.items():
        if not isinstance(key, str):
            continue
        normalized_key = key.strip()
        if normalized_key == "access_requirements":
            continue
        if normalized_key.endswith("_binding"):
            _append_requirement(requirements, value)
            continue
        if not _is_sensitive_channel_key(normalized_key):
            continue
        if isinstance(value, str) and value.strip():
            if is_credential_binding(value):
                _append_requirement(requirements, value)
            else:
                _append_requirement(requirements, _literal_ref(value))
    return tuple(requirements)


def _requirement_sets_from_tool(tool: object) -> tuple[tuple[str, ...], ...]:
    raw_sets = _get_value(tool, "access_requirement_sets", ()) or ()
    sets = _normalize_requirement_sets(
        tuple(
            tuple(item) if isinstance(item, (list, tuple)) else (str(item),)
            for item in raw_sets
        ),
    )
    if sets:
        return sets
    raw_requirements = _get_value(tool, "access_requirements", ()) or ()
    return _normalize_requirement_sets((tuple(raw_requirements),))


def _normalize_requirement_sets(
    requirement_sets: tuple[tuple[str, ...], ...],
) -> tuple[tuple[str, ...], ...]:
    resolved: list[tuple[str, ...]] = []
    for requirement_set in requirement_sets:
        normalized = tuple(
            dict.fromkeys(
                item.strip()
                for item in requirement_set
                if isinstance(item, str) and item.strip()
            ),
        )
        if normalized and normalized not in resolved:
            resolved.append(normalized)
    return tuple(resolved)


def _masked_requirement_sets(
    requirement_sets: tuple[tuple[str, ...], ...],
) -> tuple[tuple[str, ...], ...]:
    return tuple(
        tuple(_masked_requirement(item) for item in requirement_set)
        for requirement_set in requirement_sets
    )


def _masked_requirement(requirement: str) -> str:
    binding = _credential_binding_for_migration_requirement(requirement)
    if binding is None:
        return requirement.strip()
    if is_credential_binding(binding):
        normalized = requirement.strip()
        if normalized == binding.strip():
            return canonical_credential_binding(binding)
        return normalized
    return "literal:***"


def _credential_binding_for_migration_requirement(requirement: str) -> str | None:
    normalized = requirement.strip()
    if normalized.startswith("literal:sha256:"):
        return normalized
    return credential_binding_for_requirement(normalized)


def _literal_ref(value: str) -> str:
    return f"literal:sha256:{_digest(value.strip(), length=16)}"


def _append_requirement(resolved: list[str], value: object) -> None:
    if not isinstance(value, str):
        return
    normalized = value.strip()
    if normalized and normalized not in resolved:
        resolved.append(normalized)


def _get_value(obj: object, name: str, default: object = None) -> object:
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _string_value(obj: object, name: str) -> str:
    value = _get_value(obj, name)
    normalized = _optional_string(value)
    return normalized or ""


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _safe_public_string(value: object) -> str | None:
    if value is None:
        return None
    return str(value).strip() or None


def _mapping_value(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def _bool_value(obj: object, name: str, *, default: bool) -> bool:
    value = _get_value(obj, name, default)
    return bool(value)


def _legacy_list(service: object, method_names: tuple[str, ...]) -> tuple[object, ...]:
    if service is None:
        return ()
    for method_name in method_names:
        method = getattr(service, method_name, None)
        if callable(method):
            try:
                return tuple(method())
            except TypeError:
                continue
    return ()


def _dedupe_legacy_items(
    items: tuple[object, ...],
    *,
    identity_name: str,
) -> tuple[object, ...]:
    resolved: dict[str, object] = {}
    anonymous: list[object] = []
    for item in items:
        identity = _optional_string(_get_value(item, identity_name))
        if not identity:
            anonymous.append(item)
            continue
        resolved.setdefault(identity, item)
    return (*tuple(resolved.values()), *tuple(anonymous))


def _is_sensitive_channel_key(key: str) -> bool:
    normalized = key.lower()
    return any(part in normalized for part in _SENSITIVE_CHANNEL_KEYS)


def _requirement_display(requirement_sets: tuple[tuple[str, ...], ...]) -> str:
    labels = [
        " + ".join(_masked_requirement(item) for item in requirement_set)
        for requirement_set in requirement_sets
    ]
    return " / ".join(label for label in labels if label) or "Access requirement"


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.:-]+", "-", value.strip())
    return normalized.strip("-") or "default"


def _digest(value: str, *, length: int = 12) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def _redaction_policy() -> JsonObject:
    return {
        "secret_material_allowed": False,
        "sensitive_metadata_keys": ("api_key", "password", "secret", "token", "value"),
    }
