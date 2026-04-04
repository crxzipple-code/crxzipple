# Memory Space Design

## Goal

Define `memory` as a standalone durable-knowledge subsystem that is scoped by
`memory_space`, not by `agent`.

The design goal is:

- keep candidate and entry lifecycle inside `memory`
- keep retrieval, storage projection, and embedding details inside `memory`
- move agent-specific resolution and usage policy into `orchestration`
- let future callers use memory without introducing an `agent` dependency

## Problem In The Current Shape

Today the memory subsystem is logically scoped by `agent_id`, but that
`agent_id` has leaked into places that should stay generic:

- domain entities use `agent_id` as a core identity field
- application inputs accept `agent_id` instead of a neutral scope id
- `MemoryApplicationService` resolves workspace, review mode, and retrieval
  backend from `agent_id`
- orchestration tools inject hidden `agent_id` into `memory_search` and
  `memory_get`

This works, but it makes `memory` harder to reuse for:

- workspace-scoped memory
- project-scoped memory
- team-scoped memory
- session overlays
- non-agent callers

## Design Principles

### 1. Memory Owns Durable Knowledge, Not Runtime Identity

`memory` should understand:

- spaces
- candidates
- entries
- search and recall
- durable storage and projection
- review and forgetting

`memory` should not understand:

- agent profile selection
- run routing
- prompt assembly timing
- tool exposure policy

### 2. Orchestration Owns Usage Decisions

`orchestration` should decide:

- which memory space a run uses
- whether auto recall is enabled
- whether turn completion creates a candidate
- whether flush is enabled
- which memory tools are exposed for this run
- which review mode or retrieval backend applies to this run

### 3. Policy Is Not Identity

`review_required`, `auto_approve`, `keyword`, `hybrid`, `vector`, and
`workspace_root` are usage policy. They should be resolved outside the memory
domain and then passed into memory in a neutral form.

### 4. File Projection Stays In Memory

Workspace Markdown projection is still a memory concern. It is a storage view
of memory entries, not an orchestration rule.

## Target Boundary

### Memory Core Owns

- `MemorySpaceId`
- `MemoryCandidate`
- `MemoryEntry`
- candidate review lifecycle
- durable entry lifecycle
- retrieval backend selection and execution
- workspace and database projection
- citations and provenance
- forget and delete

### Orchestration Owns

- `agent/session/run -> memory_space` resolution
- prompt-time recall policy
- tool exposure policy
- post-turn candidate extraction timing
- memory flush timing
- agent-profile defaults that influence memory use

### Agent Owns

- default memory preferences in profile data
- no direct ownership of memory identifiers

## Core Types

### Value Objects

```python
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class MemorySpaceId:
    value: str


MemoryReviewMode = Literal["review_required", "auto_approve"]
MemoryRetrievalBackendName = Literal["keyword", "hybrid", "vector"]
```

### Memory Policy

This is not domain identity. It is caller-resolved usage policy.

```python
@dataclass(frozen=True, slots=True)
class MemoryPolicy:
    review_mode: MemoryReviewMode = "review_required"
    retrieval_backend: MemoryRetrievalBackendName = "keyword"
    workspace_root: str | None = None
    auto_recall: bool = False
    auto_capture: bool = True
```

### Memory Use Context

This is the contract between orchestration and memory.

```python
@dataclass(frozen=True, slots=True)
class MemoryUseContext:
    space_id: MemorySpaceId
    policy: MemoryPolicy
    session_key: str | None = None
    run_id: str | None = None
```

### Draft Inputs

```python
@dataclass(frozen=True, slots=True)
class MemoryCandidateDraft:
    title: str
    content: str
    summary: str = ""
    tags: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MemoryEntryDraft:
    title: str
    content: str
    summary: str = ""
    tags: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)
```

## Domain Model

### MemoryEntry

Target shape:

- `id`
- `space_id`
- `title`
- `content`
- `summary`
- `session_key`
- `run_id`
- `source_candidate_id`
- `tags`
- `metadata`
- `created_at`
- `updated_at`

### MemoryCandidate

Target shape:

- `id`
- `space_id`
- `title`
- `content`
- `summary`
- `session_key`
- `run_id`
- `tags`
- `metadata`
- `status`
- `created_at`
- `reviewed_at`
- `review_reason`
- `approved_entry_id`

The memory domain should be able to answer:

- which space owns this entry
- which candidate produced this entry
- whether this candidate is pending, approved, rejected, or forgotten

It should not need to answer:

- which agent profile produced this memory
- which run policy enabled this memory

Those belong in provenance metadata if needed.

## Application Ports

### Read Port

```python
from typing import Protocol


class MemoryReadPort(Protocol):
    def get_entry(
        self,
        *,
        context: MemoryUseContext,
        entry_id: str,
    ) -> MemoryEntry:
        ...

    def list_entries(
        self,
        *,
        context: MemoryUseContext,
        query: str | None = None,
        limit: int | None = None,
    ) -> list[MemoryEntry]:
        ...

    def recall_entries(
        self,
        *,
        context: MemoryUseContext,
        query_text: str,
        limit: int = 3,
        search_limit: int = 25,
    ) -> list[MemoryEntry]:
        ...
```

### Write Port

```python
class MemoryWritePort(Protocol):
    def propose_candidate(
        self,
        *,
        context: MemoryUseContext,
        draft: MemoryCandidateDraft,
        candidate_id: str | None = None,
    ) -> MemoryCandidate:
        ...

    def approve_candidate(
        self,
        *,
        candidate_id: str,
        entry_id: str | None = None,
    ) -> MemoryEntry:
        ...

    def reject_candidate(
        self,
        *,
        candidate_id: str,
        reason: str = "rejected",
    ) -> MemoryCandidate:
        ...

    def store_entry(
        self,
        *,
        context: MemoryUseContext,
        draft: MemoryEntryDraft,
        entry_id: str | None = None,
    ) -> MemoryEntry:
        ...

    def forget_entry(
        self,
        *,
        context: MemoryUseContext,
        entry_id: str,
        reason: str = "forgotten",
    ) -> MemoryEntry:
        ...
```

### Why `context` Belongs On Read And Write Calls

The same memory service can serve many spaces. Passing `MemoryUseContext` keeps
the service generic while still allowing:

- space selection
- per-space review mode
- per-space retrieval backend
- optional workspace projection
- session and run provenance

The context should be resolved before entering memory, not inside memory from an
`agent_id`.

## Infrastructure Inside Memory

The following stay inside `memory.infrastructure`:

- database repositories
- workspace Markdown projection
- FTS and keyword indexing
- vector and hybrid retrieval
- embedding providers
- citation and file-locator helpers

Suggested interfaces:

```python
class MemoryProjectionStore(Protocol):
    def append_entry(
        self,
        *,
        workspace_root: str,
        entry: MemoryEntry,
    ) -> MemoryEntry:
        ...

    def get_entry(
        self,
        *,
        workspace_root: str,
        entry_id: str,
        space_id: MemorySpaceId | None = None,
    ) -> MemoryEntry | None:
        ...

    def remove_entry(
        self,
        *,
        workspace_root: str,
        entry_id: str,
    ) -> None:
        ...
```

This keeps file-backed memory generic. It can serve agent homes today and any
other workspace-backed memory space later.

## Orchestration Integration

### Memory Space Resolver

Orchestration should own a resolver that turns runtime state into a neutral
memory context.

```python
class MemoryContextResolver(Protocol):
    def resolve_for_run(self, run: OrchestrationRun) -> MemoryUseContext | None:
        ...
```

Typical inputs to this resolver:

- `run.agent_id`
- agent profile preferences
- workspace configuration
- session metadata
- future project or team scope rules

Typical output:

```python
MemoryUseContext(
    space_id=MemorySpaceId("agent:planner"),
    policy=MemoryPolicy(
        review_mode="review_required",
        retrieval_backend="hybrid",
        workspace_root="/path/to/agent-home",
        auto_recall=True,
        auto_capture=True,
    ),
    session_key="bulk:abc",
    run_id="run_123",
)
```

### Prompt Recall Flow

Prompt assembly should look like this:

1. orchestration resolves `MemoryUseContext`
2. orchestration checks `context.policy.auto_recall`
3. orchestration calls `memory.recall_entries(context=..., query_text=...)`
4. orchestration injects the results into the prompt

Memory does not decide recall timing. It only performs recall.

### Tool Exposure Flow

Tool availability remains an orchestration concern.

Recommended shape:

1. orchestration decides whether memory tools are enabled
2. orchestration binds the resolved `MemoryUseContext` to the tool session
3. tools call memory with the bound context

Avoid hidden tool arguments such as `__agent_id`.

Prefer one of these approaches:

- bind `MemoryUseContext` in the tool runtime session
- bind an opaque `memory_scope_token` that orchestration resolves back to
  `MemoryUseContext`

This keeps tool payloads generic and avoids exposing agent identity as memory
identity.

### Turn Completion Capture Flow

When a turn finishes:

1. orchestration decides whether this turn should generate memory
2. orchestration builds `MemoryCandidateDraft`
3. orchestration calls `memory.propose_candidate(context=..., draft=...)`
4. memory applies review mode from `context.policy.review_mode`

This preserves the current candidate workflow while moving the capture decision
out of memory.

### Flush Flow

When flush is triggered:

1. orchestration resolves `MemoryUseContext`
2. orchestration builds `MemoryEntryDraft`
3. orchestration calls `memory.store_entry(context=..., draft=...)`

Flush timing belongs to orchestration. Durable storage belongs to memory.

## Recommended Package Split

### Memory

```text
modules/memory/
  domain/
    entities.py
    value_objects.py
    repositories.py
    exceptions.py
  application/
    ports.py
    services.py
    dto.py
  infrastructure/
    retrieval.py
    embeddings.py
    workspace_store.py
    persistence/
```

### Orchestration

```text
modules/orchestration/
  application/
    memory_context.py
    memory_candidates.py
    prompt_assembler.py
    tool_resolver.py
  infrastructure/
    adapters/
      memory.py
    memory_context_resolver.py
```

The orchestration adapter should be narrow. It translates orchestration runtime
state into `MemoryUseContext` and then forwards calls to the memory read and
write ports.

## Migration From The Current Code

### Phase 1: Neutral Naming In Memory Core

Replace `agent_id` with `space_id` in:

- `MemoryEntry`
- `MemoryCandidate`
- memory DTOs such as `CreateMemoryCandidateInput`
- repository filters and persistence models

Keep orchestration passing `run.agent_id` through a trivial mapping during this
phase.

### Phase 2: Pull Resolvers Out Of Memory Service

Remove these from `MemoryApplicationService`:

- `candidate_review_mode_resolver`
- `workspace_resolver`
- `retrieval_backend_resolver`

Replace them with explicit `MemoryUseContext` on public calls.

This is the biggest boundary cleanup. It makes memory deterministic and easier
to test.

### Phase 3: Move Tool Context Binding To Orchestration

Replace the current hidden tool argument injection with a bound memory context
owned by orchestration.

Memory tool implementations should receive either:

- `MemoryUseContext` directly, or
- a resolved `space_id` plus policy derived by orchestration

### Phase 4: Trim The Adapter

Replace the current orchestration `MemoryPort` with narrower read and write
ports that are `space_id`-aware.

Suggested target:

```python
class OrchestrationMemoryPort(MemoryReadPort, MemoryWritePort, Protocol):
    def memory_lookup_instruction(self) -> str:
        ...

    def is_memory_tool_name(self, name: str) -> bool:
        ...
```

The important difference is that this port should no longer mention `agent_id`.

### Phase 5: Optional Multi-Space Features

After the boundary is clean, future extensions become simpler:

- project-level shared memory spaces
- session overlay spaces
- team knowledge spaces
- composite recall across multiple spaces
- cross-space write policies

## Current-To-Target Mapping

### Current Concept: `agent_id`

Target equivalent: `MemorySpaceId`

Example transitional mapping:

- `agent:planner`
- `agent:researcher`
- `workspace:/repo/foo`
- `project:alpha`

### Current Concept: Agent Runtime Preferences

Target equivalent: orchestration-resolved `MemoryPolicy`

The profile still stores defaults, but memory does not read the profile
directly.

### Current Concept: `WorkspaceMemoryStore`

Target equivalent: still valid, but keyed by `workspace_root` and `space_id`
instead of assuming `agent_id`.

## Decision Summary

The long-term shape should be:

- `memory` is a generic, space-scoped durable knowledge subsystem
- `orchestration` is the caller that resolves space and policy for each run
- `agent` is only one possible source of defaults, not the identity model of
  memory itself

That keeps the current review workflow and retrieval features, while removing
the architectural coupling that currently makes memory agent-aware.
