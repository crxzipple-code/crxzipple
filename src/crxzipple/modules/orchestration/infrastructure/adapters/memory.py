from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.memory.application import (
    MemoryApplicationService,
    RecallMemoryEntriesInput,
)
from crxzipple.modules.memory.infrastructure import (
    inject_memory_tool_context,
    is_memory_tool_name,
    memory_lookup_instruction,
)
from crxzipple.modules.orchestration.application.ports import MemoryPort


@dataclass(slots=True)
class MemoryServiceAdapter(MemoryPort):
    service: MemoryApplicationService

    def recall_entries(
        self,
        *,
        agent_id: str,
        query_text: str,
        limit: int = 3,
        search_limit: int = 25,
    ):
        return self.service.recall_entries(
            RecallMemoryEntriesInput(
                agent_id=agent_id,
                query_text=query_text,
                limit=limit,
                search_limit=search_limit,
            ),
        )

    def create_candidate(self, data):
        return self.service.create_candidate(data)

    def record_flush_entry(self, data):
        return self.service.record_flush_entry(data)

    @staticmethod
    def memory_lookup_instruction() -> str:
        return memory_lookup_instruction()

    @staticmethod
    def is_memory_tool_name(name: str) -> bool:
        return is_memory_tool_name(name)

    @staticmethod
    def inject_tool_context(arguments, *, agent_id: str):
        return inject_memory_tool_context(arguments, agent_id=agent_id)
