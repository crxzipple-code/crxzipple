from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.operations.application.read_models.memory_events import (
    recent_memory_events,
)
from crxzipple.modules.operations.application.read_models.memory_health import (
    health as memory_health,
)
from crxzipple.modules.operations.application.read_models.memory_models import (
    MemoryContextRecord,
    MemoryOperationsQuery,
)
from crxzipple.modules.operations.application.read_models.memory_records import (
    context_records,
    filter_files,
    record_for_agent,
    safe_tuple,
    search_hits,
    select_profile,
    watch_metrics,
)
from crxzipple.modules.operations.application.read_models.memory_values import (
    normalized_filter,
    text,
)


@dataclass(frozen=True, slots=True)
class MemoryPageFacts:
    query: MemoryOperationsQuery
    now: datetime
    profiles: tuple[Any, ...]
    selected_profile: Any | None
    selected_agent_id: str
    records: tuple[MemoryContextRecord, ...]
    selected_record: MemoryContextRecord | None
    selected_files: tuple[Any, ...]
    filtered_files: tuple[Any, ...]
    visible_files: tuple[Any, ...]
    events: tuple[Any, ...]
    search_hits: tuple[Any, ...]
    watch_metrics: Any | None
    health: str


def collect_memory_page_facts(
    *,
    query: MemoryOperationsQuery | None,
    agent_service: Any | None,
    memory_query_service: Any | None,
    memory_watch_registry: Any | None,
    events_service: Any | None,
    event_definition_registry: Any | None,
    operations_observation: Any | None,
) -> MemoryPageFacts:
    normalized_query = normalize_memory_query(query)
    now = datetime.now(timezone.utc)
    profiles = safe_tuple(agent_service, "list_profiles")
    selected_profile = select_profile(profiles, normalized_query.agent_id)
    selected_agent_id = text(
        getattr(selected_profile, "id", "") or normalized_query.agent_id,
        "",
    )
    records = context_records(
        profiles=profiles,
        memory_query_service=memory_query_service,
        selected_agent_id=selected_agent_id,
    )
    selected_record = record_for_agent(records, selected_agent_id)
    selected_files = selected_record.files if selected_record else ()
    filtered_files = filter_files(selected_files, normalized_query)
    visible_files = filtered_files[
        normalized_query.offset : normalized_query.offset + normalized_query.limit
    ]
    events = recent_memory_events(
        operations_observation=operations_observation,
        events_service=events_service,
        definition_registry=event_definition_registry,
    )
    found_hits = search_hits(
        memory_query_service,
        agent_id=selected_record.agent_id if selected_record else "",
        query=normalized_query.search,
        limit=min(normalized_query.limit, 50),
    )
    metrics = watch_metrics(memory_watch_registry)
    health = memory_health(
        service_available=memory_query_service is not None,
        selected_record=selected_record,
        records=records,
        watch_metrics=metrics,
        events=events,
    )
    return MemoryPageFacts(
        query=normalized_query,
        now=now,
        profiles=profiles,
        selected_profile=selected_profile,
        selected_agent_id=selected_agent_id,
        records=records,
        selected_record=selected_record,
        selected_files=selected_files,
        filtered_files=filtered_files,
        visible_files=visible_files,
        events=events,
        search_hits=found_hits,
        watch_metrics=metrics,
        health=health,
    )


def normalize_memory_query(
    query: MemoryOperationsQuery | None,
) -> MemoryOperationsQuery:
    if query is None:
        return MemoryOperationsQuery()
    return MemoryOperationsQuery(
        agent_id=query.agent_id.strip() if isinstance(query.agent_id, str) else "",
        kind=normalized_filter(query.kind),
        search=query.search.strip() if isinstance(query.search, str) else "",
        limit=max(1, min(int(query.limit), 200)),
        offset=max(0, int(query.offset)),
    )
