from __future__ import annotations

from typing import Protocol

from crxzipple.modules.memory.domain.entities import MemoryCandidate, MemoryEntry
from crxzipple.modules.memory.domain.value_objects import MemoryCandidateStatus


class MemoryCandidateRepository(Protocol):
    def add(self, candidate: MemoryCandidate) -> None:
        ...

    def get(self, candidate_id: str) -> MemoryCandidate | None:
        ...

    def list(
        self,
        *,
        agent_id: str | None = None,
        session_key: str | None = None,
        run_id: str | None = None,
        status: MemoryCandidateStatus | None = None,
        limit: int | None = None,
    ) -> list[MemoryCandidate]:
        ...


class MemoryEntryRepository(Protocol):
    def add(self, entry: MemoryEntry) -> None:
        ...

    def delete(self, entry_id: str) -> None:
        ...

    def get(self, entry_id: str) -> MemoryEntry | None:
        ...

    def list(
        self,
        *,
        agent_id: str | None = None,
        query: str | None = None,
        limit: int | None = None,
    ) -> list[MemoryEntry]:
        ...
