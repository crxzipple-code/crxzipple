# Memory Rewrite Cutover

## Status

The memory rewrite cutover is complete for the current architecture.

The old product model based on automatic turn memory candidates, candidate
review queues, and business-entry persistence is not the target runtime shape.
Current memory is file-backed durable knowledge plus derived indexing and
explicit tool-based writes.

## Current Runtime Shape

The memory subsystem now centers on:

- file source of truth
- neutral `MemoryUseContext`
- per-space storage roots
- derived index data
- chunk-based search
- file excerpt reads
- explicit daily memory writes
- explicit long-term write helpers for local/API use
- neutral archive writes for archive-kind memory files

The memory subsystem does not own:

- agent identity
- run routing
- session transcript truth
- prompt assembly
- worker scheduling
- candidate review workflow
- memory approval queues
- business-entry persistence tables

## Slotting Model

Memory is physically separated by `space_id`.

Default routing:

- `space_id = agent_id`
- `storage_root = agent_home`

Optional orchestration binding override:

- `.state/memory-binding.json`
- may override `space_id`
- may later override `storage_root`

The memory subsystem only receives:

- `space_id`
- `storage_root`
- retrieval backend choice

## Orchestration-Facing Contract

The orchestration-facing memory port is read-oriented:

```python
class MemoryPort(Protocol):
    def resolve_context(self, *, space_id: str | None) -> MemoryUseContext | None:
        ...

    def warm_context(self, *, context: MemoryUseContext) -> bool:
        ...

    def search(
        self,
        *,
        context: MemoryUseContext,
        query: str,
        limit: int = 6,
    ) -> list[MemorySearchHit]:
        ...

    def get(
        self,
        *,
        context: MemoryUseContext,
        path: str,
        start_line: int | None = None,
        line_count: int | None = None,
    ) -> MemoryExcerpt | None:
        ...
```

Direct durable write methods are intentionally not part of this port.

Orchestration can still cause memory writes, but only by creating a normal
tool-using run such as memory flush. The write itself is performed by a memory
tool, which keeps the behavior visible in the run lifecycle.

## Removed Concepts

The following concepts are no longer part of the target runtime:

- automatic turn memory extraction
- candidate review status
- approve/reject memory endpoints
- memory entry database as business truth
- review queue UI
- memory drawer review workflow
- orchestration direct memory writes through its memory port

## Current Orchestration Integration

Current integration points:

- resolve memory context from the active run/profile
- optionally inject bounded bootstrap memory from `MEMORY.md` or `memory.md`
- expose file-oriented memory tools according to prompt mode and surface
- schedule memory flush maintenance before compaction when needed
- require memory flush runs to call either `memory_write_daily` or
  `memory_flush_skip`
- prevent memory flush runs from becoming normal assistant transcript replies

## Verification Focus

When changing this area, verify:

- normal runs do not implicitly write durable memory
- memory flush runs have restricted memory tool surface
- memory flush runs require a tool call
- session transcript archival remains in `session`, not `memory`
- orchestration memory port stays read-only
- memory files remain the durable source of truth
