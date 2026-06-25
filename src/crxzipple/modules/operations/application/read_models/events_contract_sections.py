from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.events_contract_matching import (
    contract_matches_topic,
    pattern_matches,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)


def topics_table(
    rows: list[OperationsTableRowModel],
    *,
    total_count: int,
) -> OperationsTableSectionModel:
    return OperationsTableSectionModel(
        id="topics",
        title="Topics",
        columns=_columns(
            ("topic", "Topic"),
            ("latest_cursor", "Latest Cursor"),
            ("recent_events", "Recent Events"),
            ("subscriptions", "Subscriptions"),
            ("contract", "Contract"),
            ("routes", "Routes"),
            ("latest_event", "Latest Event"),
            ("kinds", "Kinds"),
        ),
        rows=tuple(rows),
        total=total_count,
        view_all_route="/operations/events?tab=topics",
        empty_state="No event topics observed.",
    )


def contracts_table(
    topic_contracts: tuple[Any, ...],
    live_topics: tuple[str, ...],
) -> OperationsTableSectionModel:
    rows = []
    for contract in topic_contracts:
        contract_id = _display(getattr(contract, "contract_id", None))
        matches = [
            topic
            for topic in live_topics
            if contract_matches_topic(contract, topic)
        ]
        rows.append(
            OperationsTableRowModel(
                id=contract_id,
                cells={
                    "contract": contract_id,
                    "topic_pattern": _display(getattr(contract, "topic_pattern", None)),
                    "owner": _display(getattr(contract, "owner", None)),
                    "kinds": _join(getattr(contract, "kinds", ()) or ()),
                    "producers": _join(getattr(contract, "producers", ()) or ()),
                    "consumers": _join(getattr(contract, "consumers", ()) or ()),
                    "durability": _display(getattr(contract, "durability", None)),
                    "live_matches": str(len(matches)),
                },
                status="active" if matches else "registered",
                tone="success" if matches else "neutral",
            )
        )
    return OperationsTableSectionModel(
        id="contracts",
        title="Contracts",
        columns=_columns(
            ("contract", "Contract"),
            ("topic_pattern", "Topic Pattern"),
            ("owner", "Owner"),
            ("kinds", "Kinds"),
            ("producers", "Producers"),
            ("consumers", "Consumers"),
            ("durability", "Durability"),
            ("live_matches", "Live Matches"),
        ),
        rows=tuple(rows),
        total=len(rows),
        view_all_route="/operations/events?tab=contracts",
        empty_state="No topic contracts registered.",
    )


def routes_table(
    route_contracts: tuple[Any, ...],
    subscription_states: list[dict[str, Any]],
) -> OperationsTableSectionModel:
    rows = []
    for contract in route_contracts:
        contract_id = _display(getattr(contract, "contract_id", None))
        source_pattern = _display(getattr(contract, "source_topic_pattern", None))
        subscription_matches = [
            item
            for item in subscription_states
            if pattern_matches(source_pattern, _display(item.get("source_topic")))
        ]
        rows.append(
            OperationsTableRowModel(
                id=contract_id,
                cells={
                    "route": contract_id,
                    "source_topic": source_pattern,
                    "target_topic": _display(
                        getattr(contract, "target_topic_pattern", None)
                    ),
                    "owner": _display(getattr(contract, "owner", None)),
                    "observer": _display(getattr(contract, "observer", None)),
                    "source_kinds": _join(getattr(contract, "source_kinds", ()) or ()),
                    "target_kind": _display(getattr(contract, "target_kind", None)),
                    "subscriptions": str(len(subscription_matches)),
                },
                status="active" if subscription_matches else "registered",
                tone="info" if subscription_matches else "neutral",
            )
        )
    return OperationsTableSectionModel(
        id="routes",
        title="Routes",
        columns=_columns(
            ("route", "Route"),
            ("source_topic", "Source Topic"),
            ("target_topic", "Target Topic"),
            ("owner", "Owner"),
            ("observer", "Observer"),
            ("source_kinds", "Source Kinds"),
            ("target_kind", "Target Kind"),
            ("subscriptions", "Subscriptions"),
        ),
        rows=tuple(rows),
        total=len(rows),
        view_all_route="/operations/events?tab=routes",
        empty_state="No route contracts registered.",
    )


def _columns(*items: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(OperationsTableColumnModel(key=key, label=label) for key, label in items)


def _display(value: Any, fallback: str = "-") -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        return value.strip() or fallback
    if isinstance(value, (tuple, list, set)):
        return _join(tuple(_display(item) for item in value))
    return str(value)


def _join(values: tuple[Any, ...] | list[Any]) -> str:
    rendered = [
        str(value).strip()
        for value in values
        if str(value).strip() and str(value).strip() != "-"
    ]
    return ", ".join(rendered) if rendered else "-"
