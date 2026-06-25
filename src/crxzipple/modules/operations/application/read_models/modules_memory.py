from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsModuleOverview,
    RuntimeActionModel,
)
from crxzipple.modules.operations.application.read_models.modules_helpers import (
    health_metric,
    now,
    overview,
    s,
    short,
)
from crxzipple.shared.time import format_datetime_utc


def memory_operations_overview(query: Any) -> OperationsModuleOverview:
    current_time = now()
    profiles = query.agent_service.list_profiles()
    selected_profile = _select_memory_profile(profiles)
    recent_files: list[Any] = []
    long_term = None
    inventory = None
    if selected_profile is not None:
        inventory = query.memory_query_service.agent_scope_inventory(
            selected_profile.id,
            file_limit=12,
        )
    if inventory is not None and not getattr(inventory, "error", ""):
        long_term = query.memory_query_service.get_agent_long_term_excerpt(
            selected_profile.id,
        )
        recent_files = list(getattr(inventory, "files", ()) or ())

    health = "healthy" if inventory is not None and not getattr(inventory, "error", "") else "warning"
    memory_available = health == "healthy"
    store_count = len(recent_files) + (1 if long_term is not None else 0)
    agent_id = getattr(selected_profile, "id", None) or "-"
    return overview(
        module="memory",
        title="Memory",
        subtitle="聚合文件存储记忆空间、长期记忆与最近记忆文件。",
        health=health,
        updated_at=format_datetime_utc(current_time),
        metrics=(
            health_metric(health, "Loaded from memory read model"),
            MetricCardModel(
                "memory_stores",
                "Memory Stores",
                str(store_count),
                f"agent {agent_id}",
                "info",
            ),
            MetricCardModel(
                "agents",
                "Agents",
                str(len(profiles)),
                "registered agent homes",
                "neutral",
            ),
            MetricCardModel(
                "source_documents",
                "Source Documents",
                str(len(recent_files)),
                "recent memory files",
                "info",
            ),
            MetricCardModel(
                "index_health",
                "Index Health",
                "N/A",
                "index metric not exposed",
                "neutral",
            ),
            MetricCardModel(
                "errors",
                "0" if memory_available else "1",
                "memory context availability",
                "success" if memory_available else "warning",
            ),
        ),
        queue=tuple(
            [_memory_long_term_row(agent_id, long_term)]
            if long_term is not None
            else [],
        )
        + tuple(_memory_file_row(agent_id, item) for item in recent_files),
        lane_locks=tuple(_memory_agent_row(profile) for profile in profiles[:20]),
        executor=tuple(_memory_file_row(agent_id, item) for item in recent_files),
        actions=(
            RuntimeActionModel(id="open_memory", label="Open Memory", owner="memory"),
            RuntimeActionModel(
                id="refresh_memory", label="Refresh Memory", owner="memory"
            ),
        ),
    )


def _select_memory_profile(profiles: list[Any]) -> Any | None:
    for preferred_id in ("crxzipple", "assistant"):
        for profile in profiles:
            if getattr(profile, "id", None) == preferred_id:
                return profile
    return next(
        (profile for profile in profiles if getattr(profile, "enabled", True)),
        profiles[0] if profiles else None,
    )


def _memory_long_term_row(agent_id: str, long_term: Any) -> dict[str, str]:
    return {
        "path": s(getattr(long_term, "path", "-")),
        "title": s(getattr(long_term, "path", "-")),
        "kind": s(getattr(long_term, "kind", "long_term")),
        "preview": short(getattr(long_term, "text", ""), 120),
        "updated_at": "-",
        "agent_id": agent_id,
        "status": "Ready",
    }


def _memory_file_row(agent_id: str, item: Any) -> dict[str, str]:
    return {
        "path": s(getattr(item, "path", None)),
        "title": s(getattr(item, "title", None) or getattr(item, "path", None)),
        "kind": s(getattr(item, "kind", None)),
        "preview": short(getattr(item, "preview", ""), 120),
        "updated_at": s(getattr(item, "updated_at", None)),
        "agent_id": agent_id,
        "status": "Ready",
    }


def _memory_agent_row(profile: Any) -> dict[str, str]:
    preferences = getattr(profile, "runtime_preferences", None)
    return {
        "agent_id": s(getattr(profile, "id", None)),
        "name": s(getattr(profile, "name", None)),
        "status": "Enabled" if bool(getattr(profile, "enabled", True)) else "Disabled",
        "home_dir": short(getattr(preferences, "home_dir", None), 42),
    }
