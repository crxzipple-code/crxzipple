from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from crxzipple.modules.settings.application.bootstrap import BootstrapSettingsResource
from crxzipple.modules.settings.application.setup_database import database_url_summary
from crxzipple.shared.settings import SettingsResourceRef


def core_config_resources(settings: object) -> tuple[BootstrapSettingsResource, ...]:
    resources: list[BootstrapSettingsResource] = []
    resources.extend(_tool_catalog_resources(settings))
    resources.extend(_memory_config_resources(settings))
    resources.extend(_runtime_default_resources(settings))
    resources.extend(_environment_resources(settings))
    return tuple(resources)


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
        "storage_root": getattr(settings, "memory_storage_root", None),
        "retrieval_backend": getattr(settings, "memory_retrieval_backend", "keyword"),
        "vector_provider": getattr(settings, "memory_vector_provider", "local"),
        "vector_model": getattr(settings, "memory_vector_model", None),
        "vector_base_url": getattr(settings, "memory_vector_base_url", None),
        "vector_credential_binding_id": getattr(
            settings,
            "memory_vector_credential_binding_id",
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
        "config_id": "defaults",
        "enabled": True,
        "orchestration": {
            "run_lease_seconds": getattr(
                settings,
                "orchestration_run_lease_seconds",
                30,
            ),
            "run_heartbeat_seconds": getattr(
                settings,
                "orchestration_run_heartbeat_seconds",
                5.0,
            ),
            "executor_max_concurrent_assignments": getattr(
                settings,
                "orchestration_executor_max_concurrent_assignments",
                4,
            ),
            "auto_compaction_enabled": getattr(
                settings,
                "orchestration_auto_compaction_enabled",
                True,
            ),
            "auto_compaction_reserve_tokens": getattr(
                settings,
                "orchestration_auto_compaction_reserve_tokens",
                20_000,
            ),
            "auto_compaction_soft_threshold_tokens": getattr(
                settings,
                "orchestration_auto_compaction_soft_threshold_tokens",
                4_000,
            ),
        },
        "tool_worker": {
            "run_max_attempts": getattr(settings, "tool_run_max_attempts", 3),
            "run_lease_seconds": getattr(settings, "tool_run_lease_seconds", 30),
            "run_heartbeat_seconds": getattr(
                settings,
                "tool_run_heartbeat_seconds",
                5.0,
            ),
            "max_in_flight": getattr(settings, "tool_worker_max_in_flight", 4),
            "default_run_concurrency": getattr(
                settings,
                "tool_worker_default_run_concurrency",
                4,
            ),
            "image_run_concurrency": getattr(
                settings,
                "tool_worker_image_run_concurrency",
                4,
            ),
            "shared_state_run_concurrency": getattr(
                settings,
                "tool_worker_shared_state_run_concurrency",
                1,
            ),
            "remote_default_max_concurrency": getattr(
                settings,
                "tool_remote_default_max_concurrency",
                16,
            ),
        },
        "metadata": {"schema_version": 1},
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
        "database_connection": database_url_summary(
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


def _iter_attr(settings: object, attr: str) -> tuple[Any, ...]:
    value = getattr(settings, attr, ())
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return (value,)


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
