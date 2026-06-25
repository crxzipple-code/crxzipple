from __future__ import annotations

from crxzipple.modules.operations.application.read_models.browser_tones import (
    health_delta,
    health_tone,
)
from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsTabModel,
    OperationsTableRowModel,
    RuntimeActionModel,
)


def metrics(
    *,
    health: str,
    profile_rows: tuple[OperationsTableRowModel, ...],
    pool_rows: tuple[OperationsTableRowModel, ...],
    allocation_rows: tuple[OperationsTableRowModel, ...],
    page_rows: tuple[OperationsTableRowModel, ...],
    daemon_rows: tuple[OperationsTableRowModel, ...],
    network_activity_rows: tuple[OperationsTableRowModel, ...],
    diagnostic_rows: tuple[OperationsTableRowModel, ...],
) -> tuple[MetricCardModel, ...]:
    attached = sum(1 for row in profile_rows if row.status == "attached")
    active_pools = sum(1 for row in pool_rows if row.status == "active")
    active_allocations = sum(1 for row in allocation_rows if row.status == "active")
    cooling_pools = sum(1 for row in pool_rows if row.cells.get("cooling") != "-")
    failed_allocations = sum(1 for row in allocation_rows if row.status == "failed")
    stale_pages = sum(1 for row in page_rows if row.status == "stale")
    ready_daemons = sum(1 for row in daemon_rows if row.status == "ready")
    network_failures = sum(1 for row in network_activity_rows if row.tone == "danger")
    diagnostic_warnings = sum(
        1 for row in diagnostic_rows if row.tone in {"warning", "danger"}
    )
    return (
        MetricCardModel(
            "health",
            "Overall Health",
            health.title(),
            health_delta(health),
            health_tone(health),
        ),
        MetricCardModel(
            "profiles",
            "Profiles",
            str(len(profile_rows)),
            f"{attached} attached",
            "info",
        ),
        MetricCardModel(
            "profile_pools",
            "Profile Pools",
            str(len(pool_rows)),
            (
                f"{active_pools} active · {cooling_pools} cooling"
                if cooling_pools
                else f"{active_pools} active"
            ),
            "warning" if cooling_pools else "success" if active_pools else "neutral",
        ),
        MetricCardModel(
            "profile_allocations",
            "Profile Allocations",
            str(len(allocation_rows)),
            (
                f"{active_allocations} active · {failed_allocations} failed"
                if failed_allocations
                else f"{active_allocations} active"
            ),
            "warning" if failed_allocations else "info" if active_allocations else "neutral",
        ),
        MetricCardModel(
            "pages",
            "Page Observations",
            str(len(page_rows)),
            f"{stale_pages} stale",
            "warning" if stale_pages else "success",
        ),
        MetricCardModel(
            "daemon_runtimes",
            "Daemon Runtimes",
            str(len(daemon_rows)),
            f"{ready_daemons} ready",
            "success" if ready_daemons else "neutral",
        ),
        MetricCardModel(
            "network_activity",
            "Network Activity",
            str(len(network_activity_rows)),
            f"{network_failures} failed",
            "warning" if network_failures else "info" if network_activity_rows else "neutral",
        ),
        MetricCardModel(
            "diagnostics",
            "Diagnostics",
            str(len(diagnostic_rows)),
            f"{diagnostic_warnings} warnings",
            "warning" if diagnostic_warnings else "success" if diagnostic_rows else "neutral",
        ),
    )


def tabs(
    *,
    profile_count: int,
    pool_count: int,
    allocation_count: int,
    page_count: int,
    daemon_count: int,
    network_count: int,
    diagnostic_count: int,
) -> tuple[OperationsTabModel, ...]:
    return (
        OperationsTabModel("profiles", "Profiles", profile_count),
        OperationsTabModel("pools", "Pools", pool_count),
        OperationsTabModel("allocations", "Allocations", allocation_count),
        OperationsTabModel("pages", "Pages", page_count),
        OperationsTabModel("daemon", "Daemon", daemon_count),
        OperationsTabModel("network", "Network", network_count),
        OperationsTabModel("diagnostics", "Diagnostics", diagnostic_count),
    )


def actions() -> tuple[RuntimeActionModel, ...]:
    return (
        RuntimeActionModel(
            id="open_daemon",
            label="Open Daemon",
            owner="daemon",
            method="GET",
            endpoint="/operations/daemon?service_group=browser",
        ),
        RuntimeActionModel(
            id="open_tool_sources",
            label="Open Tool Sources",
            owner="tool",
            method="GET",
            endpoint="/operations/tool?tab=sources&provider=browser",
        ),
    )


def health(
    *,
    profile_rows: tuple[OperationsTableRowModel, ...],
    page_rows: tuple[OperationsTableRowModel, ...],
    pool_rows: tuple[OperationsTableRowModel, ...],
    allocation_rows: tuple[OperationsTableRowModel, ...],
    network_activity_rows: tuple[OperationsTableRowModel, ...],
    diagnostic_rows: tuple[OperationsTableRowModel, ...],
) -> str:
    if any(row.tone == "danger" for row in profile_rows):
        return "error"
    if any(row.tone == "danger" for row in pool_rows):
        return "error"
    if any(row.tone == "danger" for row in allocation_rows):
        return "error"
    if any(row.tone == "danger" for row in network_activity_rows):
        return "error"
    if any(row.status == "stale" for row in page_rows):
        return "warning"
    if any(row.tone == "warning" for row in profile_rows):
        return "warning"
    if any(row.tone == "warning" for row in pool_rows):
        return "warning"
    if any(row.tone == "warning" for row in allocation_rows):
        return "warning"
    if any(row.tone == "warning" for row in diagnostic_rows):
        return "warning"
    return "healthy"
