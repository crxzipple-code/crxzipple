from __future__ import annotations

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTabModel,
    RuntimeActionModel,
)


def events_tabs(
    *,
    recent_count: int,
    topic_count: int,
    subscription_count: int,
    observer_definition_count: int,
    contract_count: int,
    route_count: int,
    observer_count: int,
    observer_problem_count: int,
    dead_letter_count: int,
    mapping_count: int,
) -> tuple[OperationsTabModel, ...]:
    return (
        OperationsTabModel("recent", "Recent Events", recent_count),
        OperationsTabModel("topics", "Topics", topic_count),
        OperationsTabModel("subscriptions", "Subscriptions", subscription_count),
        OperationsTabModel(
            "observer",
            "Observer Health",
            observer_count,
            "warning" if observer_problem_count else "neutral",
        ),
        OperationsTabModel(
            "observer_coverage",
            "Observer Coverage",
            observer_definition_count,
        ),
        OperationsTabModel("contracts", "Contracts", contract_count),
        OperationsTabModel("routes", "Routes", route_count),
        OperationsTabModel(
            "dead_letters",
            "Dead Letters",
            dead_letter_count,
            "danger" if dead_letter_count else "neutral",
        ),
        OperationsTabModel(
            "observer_lag",
            "Observer Lag",
            mapping_count,
            "warning" if mapping_count else "neutral",
        ),
        OperationsTabModel("owners", "Owners", None),
    )


def events_actions() -> tuple[RuntimeActionModel, ...]:
    return (
        RuntimeActionModel(
            id="open_trace",
            label="Open Trace",
            owner="events",
            kind="navigation",
            method="GET",
            endpoint="/workbench/traces/{trace_id}",
        ),
        RuntimeActionModel(
            id="inspect_topic",
            label="Inspect Topic",
            owner="events",
            kind="navigation",
            method="GET",
            endpoint="/operations/events?topic={topic}",
        ),
        RuntimeActionModel(
            id="inspect_subscription",
            label="Inspect Subscription",
            owner="events",
            kind="navigation",
            method="GET",
            endpoint="/operations/events?subscription_id={subscription_id}",
        ),
        RuntimeActionModel(
            id="advance_stuck_subscriptions",
            label="Advance Stuck Subscriptions",
            owner="events",
            risk="dangerous",
            requires_confirmation=True,
            reason_required=True,
            audit_event="events.subscriptions.advance_to_head",
            method="POST",
            endpoint="/operations/events/subscriptions/advance-to-head",
        ),
        RuntimeActionModel(
            id="advance_stuck_observers",
            label="Advance Stuck Observers",
            owner="events",
            risk="dangerous",
            requires_confirmation=True,
            reason_required=True,
            audit_event="events.observers.advance_to_head",
            method="POST",
            endpoint="/operations/events/observers/advance-to-head",
        ),
    )
