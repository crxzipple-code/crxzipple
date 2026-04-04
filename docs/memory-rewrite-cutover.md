# Memory Rewrite Cutover

## Decision

`memory` will be rewritten as a new subsystem.

We will not preserve the current memory product model as the target shape.
Other modules should adapt to the new memory contract instead of forcing the
new memory implementation to preserve legacy `candidate / review / entry`
semantics.

This means:

- the current `modules/memory` implementation is legacy
- the new target is OpenClaw-style file-backed memory
- orchestration, HTTP, and frontend must follow the new memory interface

## Target Shape

The new `memory` subsystem should have these properties:

- file source of truth
- per-space storage roots
- per-space derived SQLite index
- chunk-based search
- file-slice reads
- daily memory writes
- long-term memory writes
- session archive writes

It should **not** own:

- agent identity
- candidate review workflow
- memory approval queue
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

## New Runtime Contract

The new orchestration-facing contract should be centered on:

```python
@dataclass(frozen=True, slots=True)
class MemoryUseContext:
    space_id: str
    storage_root: str
    retrieval_backend: Literal["keyword", "hybrid", "vector"] = "hybrid"
```

The new memory port should look like:

```python
class MemoryPort(Protocol):
    def resolve_context(self, *, space_id: str | None) -> MemoryUseContext | None:
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
    ) -> MemoryExcerpt:
        ...

    def append_daily(
        self,
        *,
        context: MemoryUseContext,
        content: str,
        title: str | None = None,
    ) -> MemoryWriteResult:
        ...

    def write_long_term(
        self,
        *,
        context: MemoryUseContext,
        content: str,
    ) -> MemoryWriteResult:
        ...

    def archive_session(
        self,
        *,
        context: MemoryUseContext,
        content: str,
        slug: str | None = None,
    ) -> MemoryWriteResult:
        ...
```

## What Gets Removed

The following concepts are legacy and should be removed from the new memory
subsystem:

- `MemoryCandidate`
- candidate review status
- approve / reject endpoints
- `memory_entries` as a business truth store
- turn-completion candidate extraction
- review queue UI
- memory drawer review workflow

They may survive temporarily during cutover, but they are not part of the new
target design.

## What Orchestration Must Change

Orchestration should adapt to the new memory model in these ways:

1. Resolve memory context for each run.
2. Auto-inject root `MEMORY.md` only.
3. Expose file-oriented memory tools.
4. Stop creating turn-based memory candidates.
5. Use pre-compaction flush to append daily memory.
6. Use `/new` and `/reset` hooks or orchestration-side archive flow for
   session summaries.

The current orchestration integration points that must be rewritten are:

- prompt recall
- tool execution context injection
- post-turn memory capture
- memory flush path
- HTTP memory APIs

## What Frontend Must Change

The current memory UI is shaped around the legacy workflow:

- pending candidates
- approvals
- rejections
- approved entry list

The new UI should instead be shaped around:

- recent daily memory
- long-term memory
- memory search results
- file citations
- optional manual pin / write actions

## Cutover Plan

### Phase 1

- freeze legacy memory behavior
- stop rebuilding domain abstractions around it
- treat current implementation as transitional only

### Phase 2

- build new file-first memory core
- add search/get/daily-write/session-archive APIs
- keep old memory routes available only if needed for transition

### Phase 3

- update orchestration to use the new port
- remove turn-based candidate creation
- rewire flush and recall to file-backed memory

### Phase 4

- remove review-oriented HTTP and frontend flows
- remove legacy DB-backed memory tables from active code paths

### Phase 5

- delete legacy memory implementation

## Rule For Future Work

Until cutover completes:

- do not add new product behavior to legacy candidate/review memory
- do not deepen the current memory application service
- do not introduce new UI that depends on candidate approval semantics

New work should move the codebase toward the file-backed memory contract.
