# Memory Space Design

## Goal

Define `memory` as a standalone durable-knowledge subsystem scoped by a neutral
`memory_space`, not by `agent`, `session`, or `run`.

The current design goal is:

- keep durable knowledge storage, indexing, retrieval, and citations inside
  `memory`
- let orchestration resolve which memory space a run may use
- keep session transcript truth inside `session`
- keep prompt assembly, maintenance timing, and tool exposure policy inside
  `orchestration`
- avoid hidden automatic post-turn memory mutation

## Current Position

Memory is not a second runtime. It is a durable knowledge service.

Normal run execution should not silently write durable memory. Durable writes
happen through explicit memory tools or a standardized maintenance run that
invokes those tools.

The current capture paths are:

- `memory_write_daily` for an explicit daily durable note
- future explicit long-term write tools, if we decide to expose them
- orchestration-triggered memory flush runs, which are still normal tool-using
  runs and must call a memory write or skip tool

The current recall paths are:

- `memory_search` for relevant durable knowledge
- `memory_read` for cited excerpts
- bounded prompt bootstrap from `MEMORY.md` or `memory.md` when the run surface
  allows automatic recall

## Boundaries

### Memory Owns

- `MemoryUseContext`
- memory files such as `MEMORY.md`, `memory.md`, and `memory/*.md`
- file classification
- safe file excerpt reads
- durable write helpers
- index warmup and dirty marking
- keyword/vector search
- retrieval backend selection once the caller has supplied context

### Memory Does Not Own

- agent profile selection
- run routing
- worker scheduling
- session transcript truth
- prompt assembly policy
- tool exposure policy
- final authorization decisions
- compaction timing

### Orchestration Owns

- resolving the active profile and session route
- mapping a run to a memory space
- deciding whether bounded bootstrap recall is enabled for the prompt surface
- exposing memory tools for the current prompt mode
- scheduling memory flush maintenance runs
- ensuring memory flush runs do not become normal assistant replies

### Session Owns

- exact user/assistant/tool transcript history
- message visibility and archival
- active session routing
- compaction replacement summaries

Session history is not memory. Compaction archives transcript state inside the
session module; memory only stores durable knowledge when explicitly written.

## Memory Space

A memory space is a neutral durable-knowledge scope.

Today, orchestration often resolves it from `run.agent_id` because an agent home
is the primary storage root. That mapping is an orchestration concern, not a
memory-domain identity rule.

Future callers may resolve memory spaces from:

- agent homes
- workspaces
- projects
- teams
- imported knowledge bases

The memory module should only receive the resolved context:

```python
MemoryUseContext(
    space_id="assistant",
    storage_root="/path/to/agent/home",
    retrieval_backend="keyword",
)
```

## Orchestration Memory Port

The orchestration-facing memory port is intentionally read-oriented:

- `resolve_context`
- `warm_context`
- `search`
- `get`

It does not expose direct durable write methods. This keeps orchestration from
becoming an alternate memory writer and makes the write path observable as a
normal tool/maintenance run.

The lower-level file-backed memory service may still have durable write helpers
for memory tools and memory HTTP/CLI surfaces.

## Prompt Bootstrap

Prompt bootstrap may include a small stable memory block from `MEMORY.md` or
`memory.md`.

This is intentionally not general retrieval:

- it reads only the stable bootstrap file
- it is controlled by prompt surface policy
- it does not create or update memory
- it is separate from `memory_search`

Heavy automatic recall should stay off by default. If a task needs deeper
recall, the model should use memory tools and cite the excerpts it read.

## Memory Flush

Memory flush is a maintenance run created by orchestration.

Its purpose is to let the model decide whether recent transcript content
contains durable knowledge worth recording.

Important constraints:

- a memory flush run uses prompt mode `memory_flush`
- exposed tools are restricted to memory flush tools
- tool choice is required
- a successful write must happen through a memory tool
- if there is nothing durable to record, the run must call `memory_flush_skip`
- a memory flush run must not append a normal assistant reply to the user

This preserves the principle that memory writes remain explicit and auditable.

## Storage View

The current file view is:

```text
agent-home/
  MEMORY.md
  memory/
    YYYY-MM-DD.md
    YYYY-MM-DD-slug.md
```

File kinds:

- `long_term`: `MEMORY.md` or `memory.md`
- `daily`: `memory/YYYY-MM-DD.md`
- `archive`: other markdown files under `memory/`

The `archive` kind is a durable memory file kind. It is not the source of truth
for session transcript history.

## Production Path Ownership

In local development, a memory space may resolve to an agent home or project
workspace. In production or shared deployments, `storage_root` must be treated as
an owner-module controlled path, not user-provided free text.

Required production constraints:

- each tenant/user/agent space receives a dedicated storage root under a
  configured Memory-owned base directory
- callers pass only a `space_id` or a previously authorized binding; they do not
  pass arbitrary filesystem paths into Memory runtime methods
- `.state/memory-binding.json` may select another authorized `space_id`, but it
  must not escape the configured Memory base directory
- markdown files remain Memory-owned durable knowledge, while Session remains
  the transcript source of truth
- Context Workspace and LLM request renderers may receive selected citations,
  excerpts, summaries, and handles; they must not receive a raw recursive dump of
  a memory storage root
- index files are derived artifacts and may be rebuilt; markdown files are the
  durable source

Shared writable directories are not a multi-user isolation boundary. A deployment
that serves multiple users must bind `MemoryUseContext.storage_root` through an
authenticated owner/tenant resolver before any recall, write, watch, or rebuild
operation.

## Migration Notes

Completed direction:

- memory context uses neutral `space_id`
- orchestration resolves memory context from agent/home bindings
- prompt recall is bounded bootstrap, not broad automatic retrieval
- memory writes are explicit tool calls or maintenance flush tool calls
- orchestration memory port no longer exposes direct write methods
- low-level archive helpers use a neutral archive-write name

Still worth improving:

- add a dedicated long-term write tool only if we want models to update
  `MEMORY.md` directly
- make memory space resolution available to non-agent callers without coupling
  them to agent profiles
