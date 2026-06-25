from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.access_charts import (
    failed_access_event_count,
)
from crxzipple.modules.operations.application.read_models.access_common import (
    health_delta,
    health_label,
    health_tone,
)
from crxzipple.modules.operations.application.read_models.access_target_projection import (
    setup_flow_records,
    target_worst_status,
    usage_records,
)
from crxzipple.modules.operations.application.read_models.access_values import (
    bool_value,
)
from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsTabModel,
    RuntimeActionModel,
)


def health(
    *,
    access_service: Any | None,
    targets: tuple[dict[str, Any], ...],
) -> str:
    if access_service is None:
        return "error"
    if any(target_worst_status(target) in {"expired"} for target in targets):
        return "error"
    if any(not bool_value(target.get("ready")) for target in targets):
        return "warning"
    return "healthy"


def metrics(
    *,
    health: str,
    targets: tuple[dict[str, Any], ...],
    observed_events: tuple[OperationsObservedEvent, ...],
    event_buckets: tuple[dict[str, Any], ...] = (),
) -> tuple[MetricCardModel, ...]:
    ready = sum(1 for item in targets if bool_value(item.get("ready")))
    blocked = len(targets) - ready
    setup = sum(1 for item in targets if bool_value(item.get("setup_available")))
    failed_events = failed_access_event_count(
        observed_events,
        event_buckets=event_buckets,
    )
    return (
        MetricCardModel(
            "health",
            "Overall Health",
            health_label(health),
            health_delta(health),
            health_tone(health),
        ),
        MetricCardModel(
            "access_assets",
            "Access Assets",
            str(len(targets)),
            f"{ready} ready",
            "info" if targets else "neutral",
        ),
        MetricCardModel(
            "missing_access",
            "Missing Access",
            str(blocked),
            "blocked or missing targets",
            "warning" if blocked else "success",
        ),
        MetricCardModel(
            "setup_available",
            "Setup Available",
            str(setup),
            "targets with setup flow",
            "info" if setup else "neutral",
        ),
        MetricCardModel(
            "usage",
            "Consumers",
            str(len(usage_records(targets))),
            "declared LLM/tool/channel usages",
            "info",
        ),
        MetricCardModel(
            "failed_auth",
            "Failed Auth",
            str(failed_events),
            "observed access error events",
            "danger" if failed_events else "success",
        ),
    )


def tabs(
    *,
    targets: int,
    missing: int,
    requirements: int,
    usage: int,
    setup: int,
    events: int,
    audit: int,
) -> tuple[OperationsTabModel, ...]:
    return (
        OperationsTabModel("targets", "Access Targets", targets),
        OperationsTabModel("requirements", "Credential Requirements", requirements),
        OperationsTabModel("missing", "Missing Access", missing, "warning" if missing else "success"),
        OperationsTabModel("auth_status", "Authentication Status", targets),
        OperationsTabModel("usage", "Access Usage", usage),
        OperationsTabModel("setup", "Setup Flows", setup),
        OperationsTabModel("events", "Access Events", events),
        OperationsTabModel("audit", "Audit Summary", audit),
        OperationsTabModel("fallbacks", "Fallback Problems", missing + events),
    )


def actions() -> tuple[RuntimeActionModel, ...]:
    return (
        RuntimeActionModel(
            id="open_access_inventory",
            label="Open Access Inventory",
            owner="access",
            risk="normal",
            method="GET",
            endpoint="/operations/access/inventory",
        ),
        RuntimeActionModel(
            id="check_access",
            label="Check Access",
            owner="access",
            risk="normal",
            audit_event="access.readiness.check",
            method="POST",
            endpoint="/operations/access/check",
        ),
        RuntimeActionModel(
            id="setup_access",
            label="Setup Access",
            owner="access",
            risk="controlled",
            method="GET",
            endpoint="/operations/access/setup?target={target}",
        ),
    )


def setup_count(targets: tuple[dict[str, Any], ...]) -> int:
    return len(setup_flow_records(targets))
