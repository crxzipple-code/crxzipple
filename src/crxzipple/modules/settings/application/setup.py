from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from crxzipple.modules.settings.application.bootstrap import BootstrapSettingsResource
from crxzipple.modules.settings.application.in_memory import InMemorySettingsRepository
from crxzipple.modules.settings.application.models import (
    CreateSettingsResourceInput,
    UpdateSettingsResourceInput,
)
from crxzipple.modules.settings.application.services import (
    SettingsActionService,
    SettingsEffectiveResolutionService,
    SettingsQueryService,
)
from crxzipple.modules.settings.domain.entities import (
    SettingsResource,
    SettingsResourceVersion,
)
from crxzipple.modules.settings.domain.exceptions import (
    SettingsAlreadyExistsError,
    SettingsNotFoundError,
)
from crxzipple.modules.settings.domain.value_objects import validate_settings_payload
from crxzipple.shared.settings import SettingsResourceRef


@dataclass(frozen=True, slots=True)
class SettingsServices:
    repositories: InMemorySettingsRepository
    actions: SettingsActionService
    queries: SettingsQueryService
    resolver: SettingsEffectiveResolutionService


@dataclass(frozen=True, slots=True)
class SettingsBootstrapImportResult:
    imported_counts: Mapping[str, int]
    created: int = 0
    updated: int = 0
    skipped: int = 0
    audit_refs: tuple[str, ...] = field(default_factory=tuple)

    def to_payload(self) -> dict[str, Any]:
        return {
            "imported_counts": dict(self.imported_counts),
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "audit_refs": list(self.audit_refs),
        }


def create_in_memory_settings_services() -> SettingsServices:
    repositories = InMemorySettingsRepository()
    resolver = SettingsEffectiveResolutionService(
        resource_repository=repositories.resources,
        version_repository=repositories.versions,
        override_repository=repositories.overrides,
        snapshot_repository=repositories.snapshots,
    )
    actions = SettingsActionService(
        resource_repository=repositories.resources,
        version_repository=repositories.versions,
        override_repository=repositories.overrides,
        snapshot_repository=repositories.snapshots,
        audit_repository=repositories.audits,
        resolver=resolver,
    )
    queries = SettingsQueryService(
        resource_repository=repositories.resources,
        version_repository=repositories.versions,
        override_repository=repositories.overrides,
        snapshot_repository=repositories.snapshots,
        audit_repository=repositories.audits,
        resolver=resolver,
    )
    return SettingsServices(
        repositories=repositories,
        actions=actions,
        queries=queries,
        resolver=resolver,
    )


def create_bootstrap_settings_services(settings: object) -> SettingsServices:
    services = create_in_memory_settings_services()
    seed_core_settings_resources(settings, services=services)
    return services


def import_core_settings_resources(
    settings: object,
    *,
    services: SettingsServices | None = None,
    actions: SettingsActionService | None = None,
    queries: SettingsQueryService | None = None,
    actor: str | None = None,
    reason: str = "import core settings resources",
) -> SettingsBootstrapImportResult:
    if services is not None:
        actions = services.actions
        queries = services.queries
    if actions is None or queries is None:
        raise ValueError("settings actions and queries are required to import resources.")

    counts = {kind: 0 for kind in SETTINGS_GOVERNANCE_RESOURCE_KINDS}
    created = 0
    updated = 0
    skipped = 0
    audit_refs: list[str] = []

    for seed in collect_core_settings_resources(settings):
        counts[seed.ref.resource_kind] = counts.get(seed.ref.resource_kind, 0) + 1
        existing = _get_existing_resource(queries, seed.ref.resource_id)
        if existing is None:
            result = actions.create_resource(
                CreateSettingsResourceInput(
                    resource_id=seed.ref.resource_id,
                    resource_kind=seed.ref.resource_kind,
                    owner_module=seed.ref.owner_module,
                    scope=seed.ref.scope,
                    display_name=seed.ref.display_name,
                    payload=seed.payload,
                    actor=actor,
                    reason=reason,
                    publish=True,
                    source=seed.source,
                    metadata=seed.metadata,
                    trace_context={"bootstrap_source": seed.source},
                ),
            )
            created += 1
            audit_refs.append(result.audit_ref)
            continue
        if existing.resource_kind != seed.ref.resource_kind:
            skipped += 1
            continue
        if _effective_payload_matches_seed(queries, existing.id, seed.payload):
            skipped += 1
            continue
        result = actions.update_resource(
            UpdateSettingsResourceInput(
                resource_id=seed.ref.resource_id,
                payload=seed.payload,
                actor=actor,
                reason=reason,
                publish=True,
                source=seed.source,
                metadata=seed.metadata,
                trace_context={"bootstrap_source": seed.source},
            ),
        )
        updated += 1
        audit_refs.append(result.audit_ref)

    return SettingsBootstrapImportResult(
        imported_counts=counts,
        created=created,
        updated=updated,
        skipped=skipped,
        audit_refs=tuple(audit_refs),
    )


def seed_core_settings_resources(
    settings: object,
    *,
    services: SettingsServices,
) -> SettingsBootstrapImportResult:
    counts = {kind: 0 for kind in SETTINGS_GOVERNANCE_RESOURCE_KINDS}
    created = 0
    updated = 0
    skipped = 0

    for seed in collect_core_settings_resources(settings):
        counts[seed.ref.resource_kind] = counts.get(seed.ref.resource_kind, 0) + 1
        existing = services.repositories.resources.get(seed.ref.resource_id)
        if existing is not None:
            if existing.resource_kind != seed.ref.resource_kind:
                skipped += 1
                continue
            if _effective_payload_matches_seed(
                services.queries,
                existing.id,
                seed.payload,
            ):
                skipped += 1
                continue
            validation = validate_settings_payload(seed.payload)
            existing.owner_module = seed.ref.owner_module
            existing.scope = seed.ref.scope
            existing.display_name = seed.ref.display_name
            existing.metadata = seed.metadata
            version = _add_seed_update_version(
                services,
                resource=existing,
                payload=seed.payload,
                validation=validation,
                source=seed.source,
                metadata=seed.metadata,
            )
            if version is None:
                skipped += 1
                continue
            services.repositories.resources.save(existing)
            if validation.ok:
                snapshot = services.resolver.snapshot(
                    existing.id,
                    trace_context={"bootstrap_source": seed.source},
                )
                services.repositories.snapshots.add(snapshot)
            updated += 1
            continue
        validation = validate_settings_payload(seed.payload)
        resource = SettingsResource(
            id=seed.ref.resource_id,
            resource_kind=seed.ref.resource_kind,
            owner_module=seed.ref.owner_module,
            scope=seed.ref.scope,
            display_name=seed.ref.display_name,
            metadata=seed.metadata,
        )
        version = SettingsResourceVersion(
            id=f"{seed.ref.resource_id}:v1",
            resource_id=seed.ref.resource_id,
            resource_kind=seed.ref.resource_kind,
            payload=seed.payload,
            version_number=1,
            validation=validation,
            source=seed.source,
            reason="bootstrap settings seed",
            created_by="system",
            metadata=seed.metadata,
        )
        if validation.ok:
            version.publish()
            resource.publish(version.id)
        services.repositories.resources.add(resource)
        services.repositories.versions.add(version)
        if validation.ok:
            snapshot = services.resolver.snapshot(
                resource.id,
                trace_context={"bootstrap_source": seed.source},
            )
            services.repositories.snapshots.add(snapshot)
        created += 1

    return SettingsBootstrapImportResult(
        imported_counts=counts,
        created=created,
        updated=updated,
        skipped=skipped,
    )


SETTINGS_GOVERNANCE_RESOURCE_KINDS = (
    "agent-profiles",
    "llm-profiles",
    "tool-catalog",
    "skill-catalog",
    "memory-config",
    "access-assets",
    "channel-profiles",
    "event-registry",
    "runtime-defaults",
    "environment",
    "audit-logs",
    "backup-restore",
)


def collect_core_settings_resources(settings: object) -> tuple[BootstrapSettingsResource, ...]:
    seeds: list[BootstrapSettingsResource] = []
    seeds.extend(_tool_catalog_resources(settings))
    seeds.extend(_memory_config_resources(settings))
    seeds.extend(_runtime_default_resources(settings))
    seeds.extend(_environment_resources(settings))
    return tuple(seeds)


def _tool_catalog_resources(settings: object) -> tuple[BootstrapSettingsResource, ...]:
    resources: list[BootstrapSettingsResource] = []
    for index, path in enumerate(_iter_attr(settings, "tool_local_paths"), start=1):
        resource_id = f"local-root-{index}"
        resources.append(
            _resource(
                kind="tool-catalog",
                owner="tool",
                resource_id=resource_id,
                display_name=f"Local tool root {index}",
                payload={
                    "provider_kind": "local_root",
                    "path": str(path),
                    "enabled": True,
                },
                source="bootstrap:tool_local_paths",
            ),
        )
    for provider in _iter_attr(settings, "tool_openapi_providers"):
        payload = _to_plain_payload(provider)
        if not isinstance(payload, dict):
            continue
        provider_name = str(payload.get("name") or uuid4().hex)
        resources.append(
            _resource(
                kind="tool-catalog",
                owner="tool",
                resource_id=f"openapi:{provider_name}",
                display_name=provider_name,
                payload={"provider_kind": "openapi", **payload, "enabled": True},
                source="bootstrap:tool_openapi_providers",
            ),
        )
    for provider in _iter_attr(settings, "tool_mcp_providers"):
        payload = _to_plain_payload(provider)
        if not isinstance(payload, dict):
            continue
        provider_name = str(payload.get("name") or uuid4().hex)
        resources.append(
            _resource(
                kind="tool-catalog",
                owner="tool",
                resource_id=f"mcp:{provider_name}",
                display_name=provider_name,
                payload={"provider_kind": "mcp", **payload, "enabled": True},
                source="bootstrap:tool_mcp_providers",
            ),
        )
    return tuple(resources)


def _memory_config_resources(settings: object) -> tuple[BootstrapSettingsResource, ...]:
    payload = {
        "id": "default",
        "retrieval_backend": getattr(settings, "memory_retrieval_backend", "keyword"),
        "vector_provider": getattr(settings, "memory_vector_provider", "local"),
        "vector_model": getattr(settings, "memory_vector_model", None),
        "vector_base_url": getattr(settings, "memory_vector_base_url", None),
        "vector_credential_binding": getattr(
            settings,
            "memory_vector_credential_binding",
            None,
        ),
        "vector_timeout_seconds": getattr(settings, "memory_vector_timeout_seconds", 30),
        "watch_interval_seconds": getattr(settings, "memory_watch_interval_seconds", 300.0),
        "enabled": True,
    }
    return (
        _resource(
            kind="memory-config",
            owner="memory",
            resource_id="default",
            display_name="Default memory config",
            payload=payload,
            source="bootstrap:memory",
        ),
    )


def _runtime_default_resources(settings: object) -> tuple[BootstrapSettingsResource, ...]:
    payload = {
        "id": "defaults",
        "orchestration_run_lease_seconds": getattr(
            settings,
            "orchestration_run_lease_seconds",
            30,
        ),
        "orchestration_run_heartbeat_seconds": getattr(
            settings,
            "orchestration_run_heartbeat_seconds",
            5.0,
        ),
        "orchestration_executor_max_concurrent_assignments": getattr(
            settings,
            "orchestration_executor_max_concurrent_assignments",
            4,
        ),
        "orchestration_auto_compaction_enabled": getattr(
            settings,
            "orchestration_auto_compaction_enabled",
            True,
        ),
        "orchestration_auto_compaction_reserve_tokens": getattr(
            settings,
            "orchestration_auto_compaction_reserve_tokens",
            20_000,
        ),
        "orchestration_auto_compaction_soft_threshold_tokens": getattr(
            settings,
            "orchestration_auto_compaction_soft_threshold_tokens",
            4_000,
        ),
        "tool_run_max_attempts": getattr(settings, "tool_run_max_attempts", 3),
        "tool_run_lease_seconds": getattr(settings, "tool_run_lease_seconds", 30),
        "tool_run_heartbeat_seconds": getattr(settings, "tool_run_heartbeat_seconds", 5.0),
        "tool_worker_max_in_flight": getattr(settings, "tool_worker_max_in_flight", 4),
        "tool_worker_default_run_concurrency": getattr(
            settings,
            "tool_worker_default_run_concurrency",
            4,
        ),
        "tool_worker_image_run_concurrency": getattr(
            settings,
            "tool_worker_image_run_concurrency",
            4,
        ),
        "tool_worker_shared_state_run_concurrency": getattr(
            settings,
            "tool_worker_shared_state_run_concurrency",
            1,
        ),
        "tool_remote_default_max_concurrency": getattr(
            settings,
            "tool_remote_default_max_concurrency",
            16,
        ),
        "enabled": True,
    }
    return (
        _resource(
            kind="runtime-defaults",
            owner="runtime",
            resource_id="defaults",
            display_name="Runtime defaults",
            payload=payload,
            source="bootstrap:runtime_defaults",
        ),
    )


def _environment_resources(settings: object) -> tuple[BootstrapSettingsResource, ...]:
    environment = str(getattr(settings, "environment", "") or "default")
    payload = {
        "id": environment,
        "app_name": getattr(settings, "app_name", "crxzipple"),
        "environment": environment,
        "database_connection": _database_url_summary(
            getattr(settings, "database_url", None),
        ),
        "events_backend": getattr(settings, "events_backend", None),
        "sandbox_backend": getattr(settings, "sandbox_backend", None),
        "authorization_enabled": getattr(settings, "authorization_enabled", True),
        "authorization_policy_paths": list(
            getattr(settings, "authorization_policy_paths", ()) or (),
        ),
        "authorization_runtime_policy_path": getattr(
            settings,
            "authorization_runtime_policy_path",
            None,
        ),
        "enabled": True,
    }
    return (
        _resource(
            kind="environment",
            owner="settings",
            resource_id=environment,
            display_name=f"Environment: {environment}",
            payload=payload,
            source="bootstrap:environment",
        ),
    )


def _database_url_summary(value: object) -> dict[str, Any]:
    raw_value = str(value or "").strip()
    if not raw_value:
        return {
            "configured": False,
            "driver": None,
            "host": None,
            "port": None,
            "database": None,
            "username_present": False,
            "password_present": False,
            "query_keys": [],
            "redacted_url": None,
            "fingerprint": None,
        }

    try:
        parts = urlsplit(raw_value)
    except ValueError:
        return {
            "configured": True,
            "driver": None,
            "host": None,
            "port": None,
            "database": None,
            "username_present": False,
            "password_present": False,
            "query_keys": [],
            "redacted_url": "***",
            "fingerprint": _settings_fingerprint(raw_value),
            "parse_status": "invalid",
        }

    return {
        "configured": True,
        "driver": parts.scheme or None,
        "host": parts.hostname,
        "port": _url_port(parts),
        "database": _database_name_from_url_path(parts.path),
        "username_present": bool(_url_username(parts)),
        "password_present": _url_password_present(parts),
        "query_keys": _url_query_keys(parts.query),
        "redacted_url": _redacted_database_url(parts),
        "fingerprint": _settings_fingerprint(raw_value),
    }


def _settings_fingerprint(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"sha256:{digest[:16]}"


def _database_name_from_url_path(path: str) -> str | None:
    database = path.lstrip("/")
    return database or None


def _url_username(parts: Any) -> str | None:
    try:
        return parts.username
    except ValueError:
        return None


def _url_password_present(parts: Any) -> bool:
    try:
        return parts.password is not None
    except ValueError:
        return False


def _url_port(parts: Any) -> int | None:
    try:
        return parts.port
    except ValueError:
        return None


def _url_host_port(parts: Any) -> str | None:
    host = parts.hostname
    if not host:
        return None
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = _url_port(parts)
    if port is None:
        return host
    return f"{host}:{port}"


def _url_query_keys(query: str) -> list[str]:
    return sorted(
        {
            key
            for key, _value in parse_qsl(query, keep_blank_values=True)
            if key
        },
    )


def _redacted_database_url(parts: Any) -> str:
    if not parts.scheme:
        return "***"
    host_port = _url_host_port(parts)
    username_present = bool(_url_username(parts))
    password_present = _url_password_present(parts)
    if host_port is None:
        netloc = ""
    elif password_present:
        netloc = f"<user>:***@{host_port}" if username_present else f"***@{host_port}"
    elif username_present:
        netloc = f"<user>@{host_port}"
    else:
        netloc = host_port
    redacted_query = urlencode(
        [(key, "***") for key in _url_query_keys(parts.query)],
        safe="*",
    )
    return urlunsplit(
        (
            parts.scheme,
            netloc,
            parts.path,
            redacted_query,
            "",
        ),
    )


def _resource(
    *,
    kind: str,
    owner: str,
    resource_id: str,
    display_name: str,
    payload: Mapping[str, Any],
    source: str,
) -> BootstrapSettingsResource:
    return BootstrapSettingsResource(
        ref=SettingsResourceRef(
            resource_id=resource_id,
            resource_kind=kind,
            owner_module=owner,
            display_name=display_name,
        ),
        payload=dict(payload),
        source=source,
        metadata={"bootstrap_source": source},
    )


def _get_existing_resource(query: SettingsQueryService, resource_id: str):
    try:
        return query.get_resource(resource_id)
    except SettingsNotFoundError:
        return None


def _effective_payload_matches_seed(
    query: SettingsQueryService,
    resource_id: str,
    payload: Mapping[str, Any],
) -> bool:
    try:
        effective = dict(query.get_effective(resource_id).effective_value)
    except SettingsNotFoundError:
        return False
    expected = dict(payload)
    if "enabled" not in expected:
        effective.pop("enabled", None)
    return effective == expected


def _add_seed_update_version(
    services: SettingsServices,
    *,
    resource: SettingsResource,
    payload: Mapping[str, Any],
    validation: Any,
    source: str,
    metadata: Mapping[str, Any],
) -> SettingsResourceVersion | None:
    for _attempt in range(3):
        versions = services.repositories.versions.list_for_resource(resource.id)
        version = SettingsResourceVersion(
            id=_next_seed_version_id(resource.id, versions),
            resource_id=resource.id,
            resource_kind=resource.resource_kind,
            payload=payload,
            version_number=_next_seed_version_number(versions),
            validation=validation,
            source=source,
            reason="bootstrap settings seed",
            created_by="system",
            metadata=metadata,
        )
        if validation.ok:
            version.publish()
            resource.publish(version.id)
        try:
            services.repositories.versions.add(version)
            return version
        except SettingsAlreadyExistsError:
            if _effective_payload_matches_seed(services.queries, resource.id, payload):
                return None
    services.repositories.versions.add(version)
    return version


def _next_seed_version_id(
    resource_id: str,
    versions: tuple[SettingsResourceVersion, ...],
) -> str:
    return f"{resource_id}:v{_next_seed_version_number(versions)}"


def _next_seed_version_number(
    versions: tuple[SettingsResourceVersion, ...],
) -> int:
    if not versions:
        return 1
    return max(version.version_number for version in versions) + 1


def _iter_attr(settings: object, attr: str) -> tuple[Any, ...]:
    value = getattr(settings, attr, ())
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return (value,)


def _resource_id_from_payload(
    payload: Mapping[str, Any],
    *,
    keys: tuple[str, ...] = ("id", "name", "key"),
    default_prefix: str,
) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"{default_prefix}:{uuid4().hex}"


def _to_plain_payload(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    to_payload = getattr(value, "to_payload", None)
    if callable(to_payload):
        return _to_plain_payload(to_payload())
    if is_dataclass(value):
        return _to_plain_payload(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _to_plain_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_plain_payload(item) for item in value]
    return str(value)
