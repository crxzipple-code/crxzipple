from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.memory.application import (
    MemoryApplicationService,
    RecallMemoryEntriesInput,
)
from crxzipple.modules.memory.domain import MemoryEntry
from crxzipple.modules.orchestration.domain import OrchestrationRun


@dataclass(frozen=True, slots=True)
class RecalledMemory:
    id: str
    title: str
    summary: str
    content: str
    tags: tuple[str, ...]
    source_candidate_id: str | None


def recall_prompt_memories(
    memory_service: MemoryApplicationService,
    *,
    run: OrchestrationRun,
    limit: int = 3,
) -> tuple[RecalledMemory, ...]:
    if run.agent_id is None or not run.agent_id.strip():
        return ()
    query_text = (run.inbound_instruction.content or "").strip()
    if not query_text:
        return ()
    entries = memory_service.recall_entries(
        RecallMemoryEntriesInput(
            agent_id=run.agent_id,
            query_text=query_text,
            limit=limit,
        ),
    )
    return tuple(_to_recalled_memory(entry) for entry in entries)


def _to_recalled_memory(entry: MemoryEntry) -> RecalledMemory:
    return RecalledMemory(
        id=entry.id,
        title=entry.title,
        summary=entry.summary,
        content=entry.content,
        tags=entry.tags,
        source_candidate_id=entry.source_candidate_id,
    )
