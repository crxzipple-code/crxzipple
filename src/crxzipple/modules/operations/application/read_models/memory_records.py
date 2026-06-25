from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.memory_common import (
    record_resolved,
)
from crxzipple.modules.operations.application.read_models.memory_file_helpers import (
    file_search_blob,
    file_size_bytes,
)
from crxzipple.modules.operations.application.read_models.memory_values import (
    normalized_filter,
    text,
)
from crxzipple.modules.operations.application.read_models.memory_models import (
    AdHocProfile,
    MemoryContextRecord,
    MemoryOperationsQuery,
)


def context_records(
    *,
    profiles: tuple[Any, ...],
    memory_query_service: Any | None,
    selected_agent_id: str,
) -> tuple[MemoryContextRecord, ...]:
    records: list[MemoryContextRecord] = []
    profile_ids = {text(getattr(profile, "id", ""), "") for profile in profiles}
    if selected_agent_id and selected_agent_id not in profile_ids:
        profiles = (
            *profiles,
            AdHocProfile(selected_agent_id),
        )
    for profile in profiles:
        agent_id = text(getattr(profile, "id", ""), "")
        if not agent_id:
            continue
        agent_name = text(getattr(profile, "name", None) or agent_id)
        enabled = bool(getattr(profile, "enabled", True))
        inventory = agent_scope_inventory(memory_query_service, agent_id)
        if inventory is None or text(getattr(inventory, "error", ""), ""):
            records.append(
                MemoryContextRecord(
                    agent_id=agent_id,
                    agent_name=agent_name,
                    enabled=enabled,
                    scope_ref=text(getattr(inventory, "scope_ref", ""), ""),
                    storage_root=text(getattr(inventory, "storage_root", ""), ""),
                    retrieval_backend=text(getattr(inventory, "retrieval_backend", ""), ""),
                    files=(),
                    indexed_file_count=0,
                    index_db_path=text(getattr(inventory, "index_db_path", "-"), "-"),
                    index_db_exists=False,
                    dirty=bool(getattr(inventory, "dirty", False)),
                    error=text(
                        getattr(inventory, "error", ""),
                        "memory context is not resolved",
                    ),
                )
            )
            continue
        records.append(
            MemoryContextRecord(
                agent_id=agent_id,
                agent_name=agent_name,
                enabled=enabled,
                scope_ref=text(getattr(inventory, "scope_ref", ""), ""),
                storage_root=text(getattr(inventory, "storage_root", ""), ""),
                retrieval_backend=text(getattr(inventory, "retrieval_backend", ""), ""),
                files=tuple(getattr(inventory, "files", ()) or ()),
                indexed_file_count=int(getattr(inventory, "indexed_file_count", 0) or 0),
                index_db_path=text(getattr(inventory, "index_db_path", "-"), "-"),
                index_db_exists=bool(getattr(inventory, "index_db_exists", False)),
                dirty=bool(getattr(inventory, "dirty", False)),
            )
        )
    return tuple(records)


def agent_scope_inventory(memory_query_service: Any | None, agent_id: str) -> Any | None:
    inventory = getattr(memory_query_service, "agent_scope_inventory", None)
    if not callable(inventory):
        return None
    try:
        return inventory(agent_id, file_limit=240)
    except Exception:
        return None


def search_hits(
    memory_query_service: Any | None,
    *,
    agent_id: str,
    query: str,
    limit: int,
) -> tuple[Any, ...]:
    if not agent_id or not query:
        return ()
    search = getattr(memory_query_service, "search_agent", None)
    if not callable(search):
        return ()
    try:
        return tuple(search(agent_id, query=query, limit=limit))
    except Exception:
        return ()


def watch_metrics(registry: Any | None) -> Any | None:
    snapshot_metrics = getattr(registry, "snapshot_metrics", None)
    if not callable(snapshot_metrics):
        return None
    try:
        return snapshot_metrics()
    except Exception:
        return None


def safe_tuple(service: Any | None, method_name: str) -> tuple[Any, ...]:
    method = getattr(service, method_name, None)
    if not callable(method):
        return ()
    try:
        return tuple(method() or ())
    except Exception:
        return ()


def filter_files(
    files: tuple[Any, ...],
    query: MemoryOperationsQuery,
) -> tuple[Any, ...]:
    needle = query.search.lower()
    filtered: list[Any] = []
    for item in files:
        kind = normalized_filter(getattr(item, "kind", ""))
        if query.kind != "all" and kind != query.kind:
            continue
        if needle and needle not in file_search_blob(item):
            continue
        filtered.append(item)
    filtered.sort(key=lambda item: (text(getattr(item, "updated_at", "")), text(getattr(item, "path", ""))), reverse=True)
    return tuple(filtered)


def usage_rows(
    files: tuple[Any, ...],
    *,
    record: MemoryContextRecord | None = None,
) -> tuple[dict[str, Any], ...]:
    by_kind: dict[str, dict[str, Any]] = {}
    for item in files:
        kind = text(getattr(item, "kind", ""), "unknown")
        row = by_kind.setdefault(kind, {"kind": kind, "files": 0, "bytes": 0, "latest_updated": "-"})
        row["files"] += 1
        row["bytes"] += file_size_bytes(record, item)
        updated_at = text(getattr(item, "updated_at", ""), "")
        if updated_at and (row["latest_updated"] == "-" or updated_at > row["latest_updated"]):
            row["latest_updated"] = updated_at
    return tuple(by_kind[key] for key in sorted(by_kind))


def record_for_agent(
    records: tuple[MemoryContextRecord, ...],
    agent_id: str,
) -> MemoryContextRecord | None:
    if agent_id:
        for record in records:
            if record.agent_id == agent_id or record.scope_ref == agent_id:
                return record
    return next((record for record in records if record_resolved(record)), records[0] if records else None)


def select_profile(profiles: tuple[Any, ...], agent_id: str) -> Any | None:
    if agent_id:
        return next((profile for profile in profiles if getattr(profile, "id", None) == agent_id), None)
    for preferred_id in ("crxzipple", "assistant"):
        for profile in profiles:
            if getattr(profile, "id", None) == preferred_id:
                return profile
    return next((profile for profile in profiles if getattr(profile, "enabled", True)), profiles[0] if profiles else None)
