# OpenClaw Memory Core Notes

## Goal

Capture the key facts about OpenClaw's default `memory-core` implementation and
contrast them with the current `crxzipple` memory subsystem.

This document is intentionally narrow:

- default `memory-core`, not `memory-lancedb`
- file-backed memory, not session history
- retrieval and indexing flow, not general session routing

## Core Model

OpenClaw's default memory model is:

- memory files are the source of truth
- search index is derived from those files
- retrieval returns chunk hits, then file slices

The canonical files are:

- `MEMORY.md`
- `memory.md`
- `memory/**/*.md`

The two main usage layers are:

- `MEMORY.md`: curated long-term memory
- `memory/YYYY-MM-DD.md`: append-only daily memory log

This means OpenClaw's default memory is best understood as file-backed RAG with
write-back into workspace Markdown.

## Search Sequence

### Runtime Sequence

1. `memory_search` resolves the active agent's memory config and obtains a
   `MemoryIndexManager`.
2. `manager.search(query)` starts.
3. It opportunistically triggers background sync:
   - `warmSession()` may schedule `sync(reason="session-start")`
   - dirty indexes may schedule `sync(reason="search")`
4. It immediately searches against the current index snapshot.
5. If no indexed content exists yet, it returns an empty result.
6. Otherwise it picks one of:
   - FTS-only
   - vector-only
   - hybrid
7. It returns chunk-level hits:
   - snippet
   - path
   - start/end line
   - score
8. If the caller needs more context, `memory_get(path, from, lines)` reads a
   file slice directly from disk.

### Important Property

Search does not wait for a full sync to complete. Index freshness is eventually
consistent, not strict.

## Indexing Sequence

### When Sync Runs

Sync can be triggered by:

- session start
- search while dirty
- memory file watcher events
- optional periodic interval

### What Sync Does

1. Enumerate default memory files under the workspace.
2. Build file entries with:
   - path
   - size
   - mtime
   - content hash
3. Compare file hashes against the `files` table.
4. For unchanged files:
   - skip
5. For changed files:
   - delete that file's existing chunk/vector/FTS rows
   - reread the whole file
   - rechunk the whole file
   - rebuild that file's index rows
6. For deleted files:
   - remove their index rows

### Full Reindex Triggers

OpenClaw resets and rebuilds the full store when index semantics change, for
example:

- embedding provider changed
- embedding model changed
- provider fingerprint changed
- sources changed
- chunking params changed
- vector dimension assumptions changed

## Chunking Model

Chunking is line-based sliding-window chunking.

- split file into lines
- approximate token budget as `tokens * 4` chars
- accumulate lines until `maxChars`
- flush a chunk
- carry trailing overlap into the next chunk

Defaults:

- `tokens = 400`
- `overlap = 80`

Long lines are split into segments, but line numbers are preserved.

## What SQLite Stores

The builtin SQLite store is an index, not a business memory database.

- `meta`
- `files`
- `chunks`
- `chunks_fts`
- `chunks_vec`
- `embedding_cache`

Important nuance:

- `files` stores file metadata only
- `chunks` stores chunk text plus line locations
- `chunks_fts` stores chunk text again for full-text search
- `chunks_vec` stores vector blobs only
- there is no durable `memory entry` business table in default `memory-core`

## Audit And Governance

OpenClaw has file-level traceability, but not review-style governance.

It supports:

- visible memory files
- path and line citations
- direct manual edits

It does not provide, by default:

- candidate queue
- approve/reject workflow
- reviewer attribution
- durable memory state transitions as a product feature

That makes it simpler and more local-first, but much weaker than
`crxzipple`'s current reviewable memory workflow when auditability matters.

## History vs Memory

OpenClaw distinguishes:

- session history: transcript and session store
- memory: workspace files intended to persist useful knowledge

`pre-compaction memory flush` is a bridge from history into memory:

- it reads current session context
- asks the model to write durable notes into `memory/YYYY-MM-DD.md`

That is not the same as treating history itself as memory.

## Pre-Compaction Flush

The flush behavior matters because it is easy to confuse it with automatic
structured memory capture.

What it is:

- a silent agentic turn near compaction
- aimed at writing durable notes into the daily memory file

What it is not:

- a candidate workflow
- a guaranteed deduplicated memory writer
- a full session archive

Current dedup protections are mostly execution-level:

- once per compaction cycle via `memoryFlushCompactionCount`

There are signs of planned or partial hash-based dedup in code and tests, but
the main runtime path is still centered on cycle-level gating.

## Difference From Current Crxzipple

Current `crxzipple` memory is still a mixed model:

- `MemoryCandidate` is DB truth
- workspace-backed entries are file truth
- non-workspace entries can still be DB-backed
- retrieval still merges DB entries with workspace entries

This means `crxzipple` is now closer to OpenClaw than before, but it is not yet
the same architecture.

### OpenClaw Default

- file truth for memory
- index-only SQLite
- chunk-level retrieval
- no candidate review product

### Crxzipple Current

- DB truth for candidates
- file truth for workspace-backed entries
- hybrid DB/file read path
- explicit candidate review workflow

## Practical Takeaway

If `crxzipple` wants to align more closely with OpenClaw's default memory model
without losing its product strengths, the likely target is:

- keep candidate/review state in DB
- make entries fully file-backed
- turn SQLite into pure derived indexing/cache
- keep orchestration responsible for space binding and policy

That would produce:

- OpenClaw-like file truth
- current review/audit strengths
- cleaner separation between memory storage and retrieval acceleration
