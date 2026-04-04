from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from crxzipple.modules.memory.application import MemoryExcerpt
from crxzipple.modules.orchestration.application.ports import MemoryPort
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
    memory_service: MemoryPort,
    *,
    run: OrchestrationRun,
    limit: int = 3,
) -> tuple[RecalledMemory, ...]:
    if run.agent_id is None or not run.agent_id.strip():
        return ()
    context = memory_service.resolve_context(space_id=run.agent_id)
    if context is None:
        return ()
    memory_service.warm_context(context=context)
    del limit
    for path in ("MEMORY.md", "memory.md"):
        excerpt = memory_service.get(
            context=context,
            path=path,
        )
        if excerpt is None or not excerpt.text.strip():
            continue
        return (_to_recalled_memory(excerpt),)
    return ()


def _to_recalled_memory(excerpt: MemoryExcerpt) -> RecalledMemory:
    title = "Long-Term Memory"
    if excerpt.path.strip():
        title = Path(excerpt.path).name
    return RecalledMemory(
        id=excerpt.path,
        title=title,
        summary=f"Bootstrap memory from {excerpt.path}",
        content=excerpt.text,
        tags=(),
        source_candidate_id=None,
    )
