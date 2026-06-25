from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.modules.operations.application.read_models.browser_runtime_facts import (
    browser_runtime_kind,
    is_browser_service,
    preferred_browser_instances_by_service,
    proxy_egress_label,
)
from crxzipple.modules.operations.application.read_models.browser_tones import (
    allocation_tone,
    daemon_tone,
    pool_tone,
)
from crxzipple.modules.operations.application.read_models.browser_values import (
    age_label,
    consumer_label,
    dict_value,
    duration_seconds_label,
    int_value,
    join,
    pool_concurrency_label,
    text,
    ttl_label,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
)


def daemon_rows(
    *,
    services: tuple[dict[str, Any], ...],
    instances: tuple[dict[str, Any], ...],
) -> tuple[OperationsTableRowModel, ...]:
    rows: list[OperationsTableRowModel] = []
    service_by_key = {
        text(service.get("key"), ""): service
        for service in services
        if is_browser_service(text(service.get("key"), ""))
    }
    instance_by_service = preferred_browser_instances_by_service(instances)
    for service_key in sorted({*service_by_key.keys(), *instance_by_service.keys()}):
        service = service_by_key.get(service_key, {})
        instance = instance_by_service.get(service_key, {})
        status = text(instance.get("status") or service.get("status") or "configured")
        metadata = dict_value(instance.get("metadata"))
        rows.append(
            OperationsTableRowModel(
                id=f"daemon:{service_key}",
                status=status,
                tone=daemon_tone(status),
                cells={
                    "service_key": service_key,
                    "runtime": browser_runtime_kind(service_key),
                    "status": status,
                    "profile": service_key.rsplit(":", 1)[-1],
                    "endpoint": text(
                        instance.get("endpoint")
                        or metadata.get("cdp_url"),
                    ),
                    "pid": text(instance.get("pid") or metadata.get("browser_pid")),
                    "manifest": text(metadata.get("manifest_status")),
                    "required": text(service.get("requires_service_key")),
                    "proxy_egress": proxy_egress_label(metadata),
                    "last_error": text(instance.get("last_error")),
                },
            ),
        )
    return tuple(rows)


def pool_rows(pools: tuple[Any, ...]) -> tuple[OperationsTableRowModel, ...]:
    rows: list[OperationsTableRowModel] = []
    for pool in pools:
        status = text(getattr(pool, "status", None), "active").lower()
        pool_id = text(getattr(pool, "pool_id", None), "unknown")
        diagnostics = dict_value(getattr(pool, "diagnostics", None))
        profile_names = tuple(getattr(pool, "profile_names", ()) or ())
        missing = tuple(getattr(pool, "missing_profile_names", ()) or ())
        disabled = tuple(getattr(pool, "disabled_profile_names", ()) or ())
        attach_only = tuple(getattr(pool, "attach_only_profile_names", ()) or ())
        rows.append(
            OperationsTableRowModel(
                id=f"pool:{pool_id}",
                status=status,
                tone=pool_tone(status, diagnostics=diagnostics),
                cells={
                    "pool": pool_id,
                    "profile": join(profile_names),
                    "name": text(getattr(pool, "display_name", None)),
                    "status": status,
                    "profiles": join(profile_names),
                    "ready_profiles": str(
                        int_value(getattr(pool, "ready_profile_count", 0)),
                    ),
                    "available_profiles": text(
                        diagnostics.get("available_profile_count"),
                    ),
                    "active_allocations": str(
                        int_value(getattr(pool, "active_allocation_count", 0)),
                    ),
                    "cooling": join(diagnostics.get("cooling_profiles")),
                    "failure_cooldown": join(
                        diagnostics.get("failure_cooldown_profiles"),
                    ),
                    "recent_failures": str(
                        int_value(diagnostics.get("failed_allocation_count")),
                    ),
                    "strategy": text(getattr(pool, "selection_strategy", None)),
                    "concurrency": pool_concurrency_label(pool),
                    "ttl": duration_seconds_label(
                        getattr(pool, "allocation_ttl_seconds", None),
                    ),
                    "cooldown": duration_seconds_label(
                        getattr(pool, "cooldown_seconds", None),
                    ),
                    "target_hosts": join(getattr(pool, "target_hosts", ()) or ()),
                    "missing": join(missing),
                    "disabled": join(disabled),
                    "attach_only": join(attach_only),
                },
            ),
        )
    return tuple(rows)


def allocation_rows(
    allocations: tuple[Any, ...],
    *,
    now: datetime,
) -> tuple[OperationsTableRowModel, ...]:
    rows: list[OperationsTableRowModel] = []
    for allocation in allocations:
        status = text(getattr(allocation, "status", None), "unknown").lower()
        allocation_id = text(getattr(allocation, "allocation_id", None), "unknown")
        consumer = consumer_label(allocation)
        owned_target_ids = tuple(getattr(allocation, "owned_target_ids", ()) or ())
        rows.append(
            OperationsTableRowModel(
                id=f"allocation:{allocation_id}",
                status=status,
                tone=allocation_tone(status),
                cells={
                    "allocation": allocation_id,
                    "pool": text(getattr(allocation, "pool_id", None)),
                    "profile": text(getattr(allocation, "profile_name", None)),
                    "consumer": consumer,
                    "target_host": text(getattr(allocation, "target_host", None)),
                    "targets": str(len(owned_target_ids)),
                    "age": age_label(getattr(allocation, "acquired_at", None), now=now),
                    "heartbeat": age_label(
                        getattr(allocation, "last_heartbeat_at", None),
                        now=now,
                    ),
                    "ttl": ttl_label(
                        getattr(allocation, "expires_at", None),
                        now=now,
                    ),
                    "status": status,
                    "release_reason": text(
                        getattr(allocation, "release_reason", None),
                    ),
                },
            ),
        )
    return tuple(rows)
