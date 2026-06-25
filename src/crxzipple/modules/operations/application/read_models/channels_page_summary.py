from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.modules.operations.application.read_models.channels_common import (
    interaction_tone,
    is_recent_channel_event,
    is_recent_interaction,
    runtime_is_recent_stale,
)
from crxzipple.modules.operations.application.read_models.channels_formatting import (
    text,
)
from crxzipple.modules.operations.application.read_models.channels_models import (
    ChannelEventRecord,
)
from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsTabModel,
    RuntimeActionModel,
)
from crxzipple.modules.operations.application.read_models.presenters import (
    health_delta,
    health_label,
    health_tone,
)


def metrics(
    *,
    health: str,
    profiles: tuple[Any, ...],
    runtimes: tuple[dict[str, Any], ...],
    account_bindings: tuple[Any, ...],
    connection_bindings: tuple[Any, ...],
    events: tuple[ChannelEventRecord, ...],
    dead_letters: tuple[ChannelEventRecord, ...],
    interactions: tuple[Any, ...],
    now: datetime,
) -> tuple[MetricCardModel, ...]:
    online = sum(1 for row in runtimes if row["status"] == "Online")
    recent_stale = sum(1 for row in runtimes if runtime_is_recent_stale(row))
    retained_stale = sum(1 for row in runtimes if row["status"] == "Stale")
    enabled_profiles = sum(1 for profile in profiles if bool(getattr(profile, "enabled", True)))
    bound_interactions = sum(
        1 for interaction in interactions if text(getattr(interaction, "run_id", None), "")
    )
    failed_interactions = sum(
        1
        for interaction in interactions
        if interaction_tone(interaction) == "danger"
        and is_recent_interaction(interaction, now=now)
    )
    recent_dead_letters = tuple(
        event for event in dead_letters if is_recent_channel_event(event, now=now)
    )
    return (
        MetricCardModel(
            id="health",
            label="Overall Health",
            value=health_label(health),
            delta=health_delta(health, healthy="Channel runtime state is queryable"),
            tone=health_tone(health),
        ),
        MetricCardModel(
            id="runtimes",
            label="Runtimes",
            value=str(len(runtimes)),
            delta=f"{online} online / {recent_stale} recent stale / {retained_stale} retained stale",
            tone="warning" if recent_stale else "success",
        ),
        MetricCardModel(
            id="profiles",
            label="Channel Profiles",
            value=str(len(profiles)),
            delta=f"{enabled_profiles} enabled",
            tone="success" if enabled_profiles else "warning",
        ),
        MetricCardModel(
            id="connections",
            label="Connections",
            value=str(len(connection_bindings)),
            delta="runtime connection bindings",
            tone="info" if connection_bindings else "neutral",
        ),
        MetricCardModel(
            id="accounts",
            label="Accounts",
            value=str(len(account_bindings)),
            delta="runtime account bindings",
            tone="info" if account_bindings else "neutral",
        ),
        MetricCardModel(
            id="interactions",
            label="Interactions",
            value=str(len(interactions)),
            delta=f"{bound_interactions} bound / {failed_interactions} failed",
            tone="danger" if failed_interactions else "info" if interactions else "neutral",
        ),
        MetricCardModel(
            id="dead_letters",
            label="Dead Letters",
            value=str(len(recent_dead_letters)),
            delta=f"{len(dead_letters)} retained channel failures",
            tone="danger" if recent_dead_letters else "success",
        ),
        MetricCardModel(
            id="events",
            label="Channel Events",
            value=str(len(events)),
            delta="recent event-bus records",
            tone="info" if events else "neutral",
        ),
    )


def tabs(
    *,
    runtimes: int,
    interactions: int,
    connections: int,
    accounts: int,
    profiles: int,
    messages: int,
    dead_letters: int,
    contracts: int,
) -> tuple[OperationsTabModel, ...]:
    return (
        OperationsTabModel("runtimes", "Runtimes", runtimes, "warning" if runtimes else "neutral"),
        OperationsTabModel("interactions", "Interactions", interactions, "danger" if interactions else "neutral"),
        OperationsTabModel("connections", "Connections", connections),
        OperationsTabModel("accounts", "Accounts", accounts),
        OperationsTabModel("profiles", "Profiles", profiles),
        OperationsTabModel("messages", "Recent Messages", messages),
        OperationsTabModel("dead_letters", "Dead Letters", dead_letters, "danger" if dead_letters else "neutral"),
        OperationsTabModel("events", "Channel Events", messages),
        OperationsTabModel("contracts", "Contracts", contracts),
    )


def actions() -> tuple[RuntimeActionModel, ...]:
    return (
        RuntimeActionModel(
            id="open_channel_runtime",
            label="Open Runtime",
            owner="channels",
            kind="navigation",
        ),
        RuntimeActionModel(
            id="inspect_dead_letter",
            label="Inspect Dead Letter",
            owner="channels",
            kind="navigation",
            risk="controlled",
        ),
        RuntimeActionModel(
            id="replay_dead_letter",
            label="Replay Dead Letter",
            owner="channels",
            risk="dangerous",
            requires_confirmation=True,
            audit_event="channels.dead_letter.replay",
            method="POST",
            endpoint="/operations/channels/dead-letters/{channel_type}/replay",
        ),
        RuntimeActionModel(
            id="prune_stale_runtimes",
            label="Prune Stale Runtimes",
            owner="channels",
            risk="dangerous",
            requires_confirmation=True,
            reason_required=True,
            audit_event="channels.runtimes.prune_stale",
            method="POST",
            endpoint="/operations/channels/runtimes/prune-stale",
        ),
    )
