from __future__ import annotations

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)


def profiles_table(
    rows: tuple[OperationsTableRowModel, ...],
    *,
    total: int,
) -> OperationsTableSectionModel:
    return OperationsTableSectionModel(
        id="profiles",
        title="Browser Profiles",
        columns=(
            OperationsTableColumnModel("profile", "Profile"),
            OperationsTableColumnModel("driver", "Driver"),
            OperationsTableColumnModel("enabled", "Enabled"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("endpoint", "CDP Endpoint"),
            OperationsTableColumnModel("host_generation", "Host Gen"),
            OperationsTableColumnModel("active_target", "Active Target"),
            OperationsTableColumnModel("pages", "Pages"),
            OperationsTableColumnModel("snapshot_generation", "Snapshot Gen"),
            OperationsTableColumnModel("proxy", "Proxy"),
            OperationsTableColumnModel("proxy_readiness", "Proxy Ready"),
            OperationsTableColumnModel("proxy_egress", "Egress"),
        ),
        rows=rows,
        total=total,
        view_all_route="/operations/browser?tab=profiles",
        empty_state="No browser profiles configured.",
    )


def profile_pools_table(
    rows: tuple[OperationsTableRowModel, ...],
    *,
    total: int,
) -> OperationsTableSectionModel:
    return OperationsTableSectionModel(
        id="profile_pools",
        title="Browser Profile Pools",
        columns=(
            OperationsTableColumnModel("pool", "Pool"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("profiles", "Profiles"),
            OperationsTableColumnModel("ready_profiles", "Ready"),
            OperationsTableColumnModel("available_profiles", "Available"),
            OperationsTableColumnModel("active_allocations", "Active"),
            OperationsTableColumnModel("cooling", "Cooling"),
            OperationsTableColumnModel("recent_failures", "Failures"),
            OperationsTableColumnModel("strategy", "Strategy"),
            OperationsTableColumnModel("concurrency", "Concurrency"),
            OperationsTableColumnModel("ttl", "TTL"),
            OperationsTableColumnModel("cooldown", "Cooldown"),
            OperationsTableColumnModel("target_hosts", "Target Hosts"),
            OperationsTableColumnModel("missing", "Missing"),
        ),
        rows=rows,
        total=total,
        view_all_route="/operations/browser?tab=pools",
        empty_state="No browser profile pools configured.",
    )


def profile_allocations_table(
    rows: tuple[OperationsTableRowModel, ...],
    *,
    total: int,
) -> OperationsTableSectionModel:
    return OperationsTableSectionModel(
        id="profile_allocations",
        title="Browser Profile Allocations",
        columns=(
            OperationsTableColumnModel("allocation", "Allocation"),
            OperationsTableColumnModel("pool", "Pool"),
            OperationsTableColumnModel("profile", "Profile"),
            OperationsTableColumnModel("consumer", "Consumer"),
            OperationsTableColumnModel("target_host", "Target Host"),
            OperationsTableColumnModel("targets", "Targets"),
            OperationsTableColumnModel("age", "Age"),
            OperationsTableColumnModel("heartbeat", "Heartbeat"),
            OperationsTableColumnModel("ttl", "TTL"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("release_reason", "Release Reason"),
        ),
        rows=rows,
        total=total,
        view_all_route="/operations/browser?tab=allocations",
        empty_state="No browser profile allocations recorded.",
    )


def page_observations_table(
    rows: tuple[OperationsTableRowModel, ...],
    *,
    total: int,
) -> OperationsTableSectionModel:
    return OperationsTableSectionModel(
        id="page_observations",
        title="Page Observations",
        columns=(
            OperationsTableColumnModel("profile", "Profile"),
            OperationsTableColumnModel("target_id", "Target"),
            OperationsTableColumnModel("page_generation", "Page Gen"),
            OperationsTableColumnModel("reason", "Reason"),
            OperationsTableColumnModel("snapshot_generation", "Snapshot Gen"),
            OperationsTableColumnModel("ref_generation", "Ref Gen"),
            OperationsTableColumnModel("last_action", "Last Action"),
            OperationsTableColumnModel("refs", "Refs"),
            OperationsTableColumnModel("stale", "Stale"),
        ),
        rows=rows,
        total=total,
        view_all_route="/operations/browser?tab=pages",
        empty_state="No browser page observations yet.",
    )
