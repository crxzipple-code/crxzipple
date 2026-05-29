from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from crxzipple.modules.memory.application import (
    MemoryActorContext,
    MemoryRecallItem,
    MemoryRecallRequest,
    MemoryRuntimePort,
)
from crxzipple.modules.orchestration.domain import OrchestrationRun


@dataclass(frozen=True, slots=True)
class RecalledMemory:
    id: str
    title: str
    summary: str
    content: str
    tags: tuple[str, ...]


def recall_prompt_memories(
    memory_service: MemoryRuntimePort,
    *,
    run: OrchestrationRun,
    session_key: str | None = None,
    workspace_dir: str | None = None,
) -> tuple[RecalledMemory, ...]:
    if run.agent_id is None or not run.agent_id.strip():
        return ()
    try:
        result = memory_service.recall(
            MemoryRecallRequest(
                actor=MemoryActorContext(
                    agent_id=run.agent_id,
                    run_id=run.id,
                    session_key=session_key,
                    active_session_id=run.active_session_id,
                    workspace_dir=workspace_dir,
                ),
                query=run.inbound_instruction.content,
                max_items=6,
                metadata={"purpose": "prompt_bootstrap"},
            ),
        )
    except ValueError:
        return ()
    return tuple(
        _to_recalled_memory(item)
        for item in result.items
        if item.text.strip()
    )


def _to_recalled_memory(item: MemoryRecallItem) -> RecalledMemory:
    title = "Long-Term Memory"
    if item.path.strip():
        title = Path(item.path).name
    return RecalledMemory(
        id=item.citation,
        title=title,
        summary=f"Bootstrap memory from {item.path}",
        content=item.text,
        tags=(),
    )
