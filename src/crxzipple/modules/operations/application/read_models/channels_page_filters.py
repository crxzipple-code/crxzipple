from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.channels_common import (
    interaction_search_text,
)
from crxzipple.modules.operations.application.read_models.channels_event_helpers import (
    event_search_text,
)
from crxzipple.modules.operations.application.read_models.channels_formatting import (
    normalized_filter,
    sort_datetime,
    text,
)
from crxzipple.modules.operations.application.read_models.channels_models import (
    ChannelEventRecord,
    ChannelsOperationsQuery,
)


def normalize_channels_query(
    query: ChannelsOperationsQuery | None,
) -> ChannelsOperationsQuery:
    if query is None:
        return ChannelsOperationsQuery()
    return ChannelsOperationsQuery(
        status=normalized_filter(query.status),
        channel_type=normalized_filter(query.channel_type),
        search=query.search.strip() if isinstance(query.search, str) else "",
        limit=max(1, min(int(query.limit), 200)),
        offset=max(0, int(query.offset)),
    )


def filter_runtime_records(
    rows: tuple[dict[str, Any], ...],
    query: ChannelsOperationsQuery,
) -> tuple[dict[str, Any], ...]:
    filtered: list[dict[str, Any]] = []
    needle = query.search.lower()
    for row in rows:
        if query.channel_type != "all" and row["channel_type"].lower() != query.channel_type:
            continue
        if query.status != "all" and normalized_filter(row["status"]) != query.status:
            continue
        if needle and needle not in " ".join(text(value, "") for value in row.values()).lower():
            continue
        filtered.append(row)
    return tuple(filtered)


def filter_events(
    events: tuple[ChannelEventRecord, ...],
    query: ChannelsOperationsQuery,
) -> tuple[ChannelEventRecord, ...]:
    filtered: list[ChannelEventRecord] = []
    needle = query.search.lower()
    for event in events:
        if query.channel_type != "all" and (event.channel_type or "").lower() != query.channel_type:
            continue
        if query.status != "all" and normalized_filter(event.status) != query.status:
            continue
        if needle and needle not in event_search_text(event):
            continue
        filtered.append(event)
    return tuple(filtered)


def filter_interactions(
    interactions: tuple[Any, ...],
    query: ChannelsOperationsQuery,
) -> tuple[Any, ...]:
    filtered: list[Any] = []
    needle = query.search.lower()
    for interaction in interactions:
        if (
            query.channel_type != "all"
            and text(getattr(interaction, "channel_type", None), "").lower()
            != query.channel_type
        ):
            continue
        if (
            query.status != "all"
            and normalized_filter(getattr(interaction, "status", None))
            != query.status
        ):
            continue
        if needle and needle not in interaction_search_text(interaction):
            continue
        filtered.append(interaction)
    filtered.sort(
        key=lambda item: sort_datetime(getattr(item, "updated_at", None)),
        reverse=True,
    )
    return tuple(filtered)
