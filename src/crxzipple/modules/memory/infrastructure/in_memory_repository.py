from __future__ import annotations

from crxzipple.modules.memory.domain.entities import MemoryCandidate, MemoryEntry
from crxzipple.modules.memory.domain.value_objects import MemoryCandidateStatus


class InMemoryMemoryCandidateRepository:
    def __init__(self) -> None:
        self._items: dict[str, MemoryCandidate] = {}

    def add(self, candidate: MemoryCandidate) -> None:
        self._items[candidate.id] = candidate

    def get(self, candidate_id: str) -> MemoryCandidate | None:
        return self._items.get(candidate_id)

    def list(
        self,
        *,
        agent_id: str | None = None,
        session_key: str | None = None,
        run_id: str | None = None,
        status: MemoryCandidateStatus | None = None,
        limit: int | None = None,
    ) -> list[MemoryCandidate]:
        items = sorted(
            self._items.values(),
            key=lambda item: (item.created_at, item.id),
            reverse=True,
        )
        if agent_id is not None:
            items = [item for item in items if item.agent_id == agent_id.strip()]
        if session_key is not None:
            items = [item for item in items if item.session_key == session_key.strip()]
        if run_id is not None:
            items = [item for item in items if item.run_id == run_id.strip()]
        if status is not None:
            items = [item for item in items if item.status is status]
        if limit is not None and limit > 0:
            items = items[:limit]
        return items


class InMemoryMemoryEntryRepository:
    def __init__(self) -> None:
        self._items: dict[str, MemoryEntry] = {}

    def add(self, entry: MemoryEntry) -> None:
        self._items[entry.id] = entry

    def delete(self, entry_id: str) -> None:
        self._items.pop(entry_id, None)

    def get(self, entry_id: str) -> MemoryEntry | None:
        return self._items.get(entry_id)

    def list(
        self,
        *,
        agent_id: str | None = None,
        query: str | None = None,
        limit: int | None = None,
    ) -> list[MemoryEntry]:
        items = sorted(
            self._items.values(),
            key=lambda item: (item.created_at, item.id),
            reverse=True,
        )
        if agent_id is not None:
            items = [item for item in items if item.agent_id == agent_id.strip()]
        if query is not None and query.strip():
            normalized_query = query.strip().casefold()
            items = [
                item
                for item in items
                if normalized_query in item.title.casefold()
                or normalized_query in item.content.casefold()
                or normalized_query in item.summary.casefold()
            ]
        if limit is not None and limit > 0:
            items = items[:limit]
        return items
