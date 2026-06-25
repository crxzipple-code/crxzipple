from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.event_buckets import (
    recent_event_buckets,
)
from crxzipple.modules.operations.application.read_models.skills_common import (
    normalized_filter,
    text,
)
from crxzipple.modules.operations.application.read_models.skills_event_sources import (
    latest_readiness_events_by_skill,
    recent_skill_events,
)
from crxzipple.modules.operations.application.read_models.skills_health import (
    health as skills_health,
)
from crxzipple.modules.operations.application.read_models.skills_models import (
    SkillRecord,
    SkillsOperationsQuery,
)
from crxzipple.modules.operations.application.read_models.skills_page_records import (
    filter_skill_records,
    skill_records_for_packages,
)


@dataclass(frozen=True, slots=True)
class SkillsPageFacts:
    now: datetime
    query: SkillsOperationsQuery
    packages: tuple[Any, ...]
    tools: tuple[Any, ...]
    tool_ids: set[str]
    events: tuple[OperationsObservedEvent, ...]
    event_buckets: tuple[dict[str, Any], ...]
    records: tuple[SkillRecord, ...]
    filtered_records: tuple[SkillRecord, ...]
    visible_records: tuple[SkillRecord, ...]
    health: str


def collect_skills_page_facts(
    *,
    skill_manager: Any | None,
    tool_service: Any | None,
    access_service: Any | None,
    events_service: Any | None,
    event_definition_registry: Any | None,
    operations_observation: Any | None,
    query: SkillsOperationsQuery | None,
) -> SkillsPageFacts:
    normalized_query = normalize_skills_query(query)
    now = datetime.now(timezone.utc)
    packages = _safe_list_skills(skill_manager, surface=normalized_query.surface)
    tools = _safe_list_tools(tool_service)
    tool_ids = {
        text(getattr(tool, "id", ""))
        for tool in tools
        if text(getattr(tool, "id", ""), "")
    }
    events = recent_skill_events(
        operations_observation=operations_observation,
        events_service=events_service,
        definition_registry=event_definition_registry,
    )
    event_buckets = recent_event_buckets(
        operations_observation,
        module="skills",
        hours=24,
        limit=1000,
    )
    readiness_events = latest_readiness_events_by_skill(events)
    records = skill_records_for_packages(
        packages,
        tool_ids=tool_ids,
        access_service=access_service,
        readiness_events_by_skill=readiness_events,
    )
    filtered_records = filter_skill_records(records, normalized_query)
    return SkillsPageFacts(
        now=now,
        query=normalized_query,
        packages=packages,
        tools=tools,
        tool_ids=tool_ids,
        events=events,
        event_buckets=event_buckets,
        records=records,
        filtered_records=filtered_records,
        visible_records=filtered_records[
            normalized_query.offset : normalized_query.offset + normalized_query.limit
        ],
        health=skills_health(
            skill_manager_available=skill_manager is not None,
            records=records,
            events=events,
        ),
    )


def normalize_skills_query(query: SkillsOperationsQuery | None) -> SkillsOperationsQuery:
    if query is None:
        return SkillsOperationsQuery()
    return SkillsOperationsQuery(
        surface=text(query.surface, "interactive").strip() or "interactive",
        source=normalized_filter(query.source),
        status=normalized_filter(query.status),
        search=query.search.strip() if isinstance(query.search, str) else "",
        limit=max(1, min(int(query.limit), 200)),
        offset=max(0, int(query.offset)),
    )


def _safe_list_skills(skill_manager: Any | None, *, surface: str) -> tuple[Any, ...]:
    list_available = getattr(skill_manager, "list_available", None)
    if not callable(list_available):
        return ()
    try:
        return tuple(list_available(workspace_dir=None, surface=surface) or ())
    except Exception:
        return ()


def _safe_list_tools(tool_service: Any | None) -> tuple[Any, ...]:
    list_enabled_tools = getattr(tool_service, "list_enabled_tools", None)
    if not callable(list_enabled_tools):
        list_enabled_tools = getattr(tool_service, "list_tools", None)
    if not callable(list_enabled_tools):
        return ()
    try:
        return tuple(list_enabled_tools() or ())
    except Exception:
        return ()

