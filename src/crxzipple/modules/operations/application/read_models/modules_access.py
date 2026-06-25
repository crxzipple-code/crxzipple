from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.modules_access_inventory import (
    collect_access_inventory_for_operations,
)
from crxzipple.modules.operations.application.read_models.modules_access_projection import (
    access_target_row,
    setup_available_count,
)
from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsModuleOverview,
    RuntimeActionModel,
)
from crxzipple.modules.operations.application.read_models.modules_helpers import (
    as_dict,
    as_list,
    health_metric,
    int_value,
    now,
    overview,
)
from crxzipple.shared.time import format_datetime_utc


def access_operations_overview(
    query: Any,
) -> OperationsModuleOverview:
    current_time = now()
    inventory = collect_access_inventory_for_operations(
        query,
        include_ready=True,
    )
    targets = as_list(inventory.get("targets"))
    counts = as_dict(inventory.get("counts"))
    total = int_value(counts.get("total"), len(targets))
    ready = int_value(counts.get("ready"))
    blocked = int_value(counts.get("blocked"), total - ready)
    health = "warning" if blocked else "healthy"
    blocked_targets = [target for target in targets if not bool(target.get("ready"))]

    return overview(
        module="access",
        title="Access",
        subtitle="聚合凭证、授权要求与访问可用性，前端只消费 UI readiness 读面。",
        health=health,
        updated_at=format_datetime_utc(current_time),
        metrics=(
            health_metric(health, "Loaded from access inventory"),
            MetricCardModel(
                "access_assets", "Access Assets", str(total), f"{ready} ready", "info"
            ),
            MetricCardModel(
                "missing_access",
                "Missing Access",
                str(blocked),
                "blocked or missing targets",
                "warning" if blocked else "success",
            ),
            MetricCardModel("ready", "Ready", str(ready), "ready targets", "success"),
            MetricCardModel(
                "setup_available",
                "Setup Available",
                str(setup_available_count(targets)),
                "targets with setup flow",
                "info",
            ),
            MetricCardModel(
                "failed_auth",
                "Failed Auth",
                "N/A",
                "auth event metric not exposed",
                "neutral",
            ),
        ),
        queue=tuple(access_target_row(target) for target in blocked_targets[:20]),
        lane_locks=tuple(access_target_row(target) for target in targets[:40]),
        executor=tuple(access_target_row(target) for target in targets[:40]),
        actions=(
            RuntimeActionModel(id="open_access", label="Open Access", owner="access"),
            RuntimeActionModel(
                id="setup_access",
                label="Setup Access",
                owner="access",
                risk="controlled",
            ),
            RuntimeActionModel(id="open_trace", label="Open Trace", owner="access"),
        ),
    )
