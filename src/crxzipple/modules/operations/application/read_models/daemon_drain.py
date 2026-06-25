from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.daemon_common import (
    _bool,
    _text,
)
from crxzipple.modules.operations.application.read_models.daemon_health import (
    desired_unmet_services,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
    OperationsKeyValueSectionModel,
)


def daemon_drain_overview(
    *,
    services: tuple[dict[str, Any], ...],
    instances: tuple[dict[str, Any], ...],
    leases: tuple[dict[str, Any], ...],
    process_rows: tuple[dict[str, Any], ...],
    instances_by_service: dict[str, list[dict[str, Any]]],
    leases_by_service: dict[str, list[dict[str, Any]]],
    runtime_bootstrap_config: Any | None,
) -> OperationsKeyValueSectionModel:
    del leases_by_service
    instance_ids = {_text(item.get("id"), "") for item in instances}
    active_leases = [item for item in leases if _text(item.get("status"), "").lower() == "active"]
    leased_services = {
        _text(item.get("service_key"), "")
        for item in active_leases
        if _text(item.get("service_key"), "")
    }
    ready_leased_services = sum(
        1
        for service_key in leased_services
        if _ready_count(instances_by_service.get(service_key, [])) > 0
    )
    desired_unmet = len(desired_unmet_services(services, instances_by_service))
    unmatched = sum(
        1
        for lease in active_leases
        if _text(lease.get("instance_id"), "") not in instance_ids
    )
    release_history = len(
        [item for item in leases if _text(item.get("status"), "").lower() == "released"]
    )
    orphaned_processes = sum(1 for item in process_rows if _bool(item.get("orphaned")))
    return OperationsKeyValueSectionModel(
        id="drain_overview",
        title="Lease / Drain Indicators",
        items=(
            OperationsKeyValueItemModel(
                "Active Leases",
                str(len(active_leases)),
                "info" if active_leases else "neutral",
            ),
            OperationsKeyValueItemModel(
                "Leased Services",
                str(len(leased_services)),
                "info" if leased_services else "neutral",
            ),
            OperationsKeyValueItemModel(
                "Ready Leased Services",
                str(ready_leased_services),
                "success" if ready_leased_services == len(leased_services) else "warning",
            ),
            OperationsKeyValueItemModel(
                "Unmatched Leases",
                str(unmatched),
                "danger" if unmatched else "success",
            ),
            OperationsKeyValueItemModel(
                "Orphaned Processes",
                str(orphaned_processes),
                "warning" if orphaned_processes else "success",
            ),
            OperationsKeyValueItemModel(
                "Desired Unmet",
                str(desired_unmet),
                "warning" if desired_unmet else "success",
            ),
            OperationsKeyValueItemModel(
                "Released History",
                str(release_history),
                "neutral",
            ),
            OperationsKeyValueItemModel(
                "Executor Max Assignments",
                _runtime_value(runtime_bootstrap_config, "orchestration_executor_max_concurrent_assignments"),
            ),
            OperationsKeyValueItemModel(
                "Tool Worker Max In-flight",
                _runtime_value(runtime_bootstrap_config, "tool_worker_max_in_flight"),
            ),
            OperationsKeyValueItemModel(
                "Latest Worker Start",
                _latest_instance_start(instances),
            ),
        ),
    )


def _ready_count(items: list[dict[str, Any]]) -> int:
    return sum(1 for item in items if _text(item.get("status"), "").lower() == "ready")


def _runtime_value(runtime_bootstrap_config: Any | None, name: str) -> str:
    value = getattr(runtime_bootstrap_config, name, None)
    if value is None:
        return "-"
    return _text(value)


def _latest_instance_start(instances: tuple[dict[str, Any], ...]) -> str:
    values = sorted(
        (_text(item.get("started_at"), "") for item in instances),
        reverse=True,
    )
    return values[0] if values else "-"
