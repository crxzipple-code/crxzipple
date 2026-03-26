from __future__ import annotations

from typing import Any, Protocol

from crxzipple.modules.memory.application import (
    CreateMemoryCandidateInput,
    RecordMemoryFlushInput,
)
from crxzipple.modules.memory.domain import MemoryCandidate, MemoryEntry


class MemoryPort(Protocol):
    def recall_entries(
        self,
        *,
        agent_id: str,
        query_text: str,
        limit: int = 3,
        search_limit: int = 25,
    ) -> list[MemoryEntry]:
        ...

    def create_candidate(
        self,
        data: CreateMemoryCandidateInput,
    ) -> MemoryCandidate:
        ...

    def record_flush_entry(
        self,
        data: RecordMemoryFlushInput,
    ) -> MemoryEntry:
        ...

    def memory_lookup_instruction(self) -> str:
        ...

    def is_memory_tool_name(self, name: str) -> bool:
        ...

    def inject_tool_context(
        self,
        arguments: dict[str, Any],
        *,
        agent_id: str,
    ) -> dict[str, Any]:
        ...
