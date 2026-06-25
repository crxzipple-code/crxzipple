from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.events_event_common import (
    as_dict,
    as_tuple,
    columns,
    contract_status_label,
    display,
    event_tone,
    subscription_tone,
)
from crxzipple.modules.operations.application.read_models.events_models import (
    EventsEventDetailModel,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)


def event_details(
    events: list[dict[str, Any]],
    *,
    subscription_states: list[dict[str, Any]],
) -> tuple[EventsEventDetailModel, ...]:
    details: list[EventsEventDetailModel] = []
    for item in events[:50]:
        topic = display(item.get("topic"))
        matching_subscriptions = [
            state for state in subscription_states if state.get("source_topic") == topic
        ]
        details.append(
            EventsEventDetailModel(
                event_id=display(item.get("event_id")),
                title=display(item.get("event_name")),
                status=contract_status_label(display(item.get("contract_status"))),
                tone=event_tone(item),
                summary=(
                    OperationsKeyValueItemModel("Time", display(item.get("created_at"))),
                    OperationsKeyValueItemModel("Topic", topic),
                    OperationsKeyValueItemModel("Cursor", display(item.get("cursor"))),
                    OperationsKeyValueItemModel("Owner", display(item.get("owner"))),
                    OperationsKeyValueItemModel("Kind", display(item.get("kind"))),
                    OperationsKeyValueItemModel(
                        "Contract",
                        display(item.get("contract_label")),
                        event_tone(item),
                    ),
                    OperationsKeyValueItemModel(
                        "Run ID",
                        display(item.get("run_id") or item.get("entity_id")),
                    ),
                    OperationsKeyValueItemModel("Trace", display(item.get("trace_id"))),
                ),
                payload=as_dict(item.get("payload")),
                trace=as_dict(item.get("trace")),
                contracts=_detail_contracts_table(item),
                subscriptions=_detail_subscriptions_table(matching_subscriptions),
            )
        )
    return tuple(details)


def _detail_contracts_table(item: dict[str, Any]) -> OperationsTableSectionModel:
    rows = []
    for index, match in enumerate(as_tuple(item.get("contract_matches"))):
        contract = as_dict(match.get("contract") if isinstance(match, dict) else None)
        rows.append(
            OperationsTableRowModel(
                id=f"topic:{index}:{display(contract.get('contract_id'))}",
                cells={
                    "kind": "Topic",
                    "contract": display(contract.get("contract_id")),
                    "owner": display(contract.get("owner")),
                    "pattern": display(contract.get("topic_pattern")),
                    "direction": "-",
                },
                status="matched",
                tone="success",
            )
        )
    for index, match in enumerate(as_tuple(item.get("route_matches"))):
        contract = as_dict(match.get("contract") if isinstance(match, dict) else None)
        rows.append(
            OperationsTableRowModel(
                id=f"route:{index}:{display(contract.get('contract_id'))}",
                cells={
                    "kind": "Route",
                    "contract": display(contract.get("contract_id")),
                    "owner": display(contract.get("owner")),
                    "pattern": display(contract.get("source_topic_pattern")),
                    "direction": display(
                        match.get("direction") if isinstance(match, dict) else None
                    ),
                },
                status="matched",
                tone="info",
            )
        )
    return OperationsTableSectionModel(
        id="event_contracts",
        title="Event Contracts",
        columns=columns(
            ("kind", "Kind"),
            ("contract", "Contract"),
            ("owner", "Owner"),
            ("pattern", "Pattern"),
            ("direction", "Direction"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No contract matched this event.",
    )


def _detail_subscriptions_table(
    states: list[dict[str, Any]],
) -> OperationsTableSectionModel:
    rows = tuple(
        OperationsTableRowModel(
            id=f"{item['subscription_id']}:{item['source_topic']}",
            cells={
                "subscription": display(item.get("subscription_id")),
                "status": display(item.get("status")),
                "cursor": display(item.get("cursor")),
                "latest_cursor": display(item.get("latest_cursor")),
                "lag": str(item.get("lag") or 0),
            },
            status=display(item.get("status")).lower().replace(" ", "_"),
            tone=subscription_tone(item),
        )
        for item in states
    )
    return OperationsTableSectionModel(
        id="event_subscriptions",
        title="Event Subscriptions",
        columns=columns(
            ("subscription", "Subscription"),
            ("status", "Status"),
            ("cursor", "Cursor"),
            ("latest_cursor", "Latest Cursor"),
            ("lag", "Lag"),
        ),
        rows=rows,
        total=len(rows),
        empty_state="No subscription cursor for this topic.",
    )
