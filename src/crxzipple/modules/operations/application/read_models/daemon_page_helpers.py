from __future__ import annotations

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableSectionModel,
    RuntimeActionModel,
)


def daemon_actions() -> tuple[RuntimeActionModel, ...]:
    return (
        RuntimeActionModel(
            id="ensure_service",
            label="Ensure Service",
            owner="daemon",
            risk="controlled",
            audit_event="daemon.service.ensure",
            method="POST",
            endpoint="/operations/daemon/services/{service_key}/ensure",
        ),
        RuntimeActionModel(
            id="healthcheck_service",
            label="Healthcheck Service",
            owner="daemon",
            risk="normal",
            audit_event="daemon.service.healthcheck",
            method="POST",
            endpoint="/operations/daemon/services/{service_key}/healthcheck",
        ),
        RuntimeActionModel(
            id="reconcile_service",
            label="Reconcile Service",
            owner="daemon",
            risk="controlled",
            audit_event="daemon.service.reconcile",
            method="POST",
            endpoint="/operations/daemon/services/{service_key}/reconcile",
        ),
        RuntimeActionModel(
            id="stop_service",
            label="Stop Service",
            owner="daemon",
            risk="dangerous",
            audit_event="daemon.service.stop",
            method="POST",
            endpoint="/operations/daemon/services/{service_key}/stop",
            requires_confirmation=True,
            reason_required=True,
        ),
    )


def daemon_links_to_operations() -> tuple[dict[str, str], ...]:
    return (
        {
            "type": "operations_module",
            "id": "orchestration",
            "label": "Orchestration",
            "owner": "operations",
            "route": "/operations/orchestration",
        },
        {
            "type": "operations_module",
            "id": "tool",
            "label": "Tool",
            "owner": "operations",
            "route": "/operations/tool",
        },
        {
            "type": "operations_module",
            "id": "channels",
            "label": "Channels",
            "owner": "operations",
            "route": "/operations/channels",
        },
        {
            "type": "operations_module",
            "id": "events",
            "label": "Events",
            "owner": "operations",
            "route": "/operations/events",
        },
    )


def overview_rows(section: OperationsTableSectionModel) -> tuple[dict[str, str], ...]:
    return tuple(dict(row.cells) for row in section.rows[:80])
