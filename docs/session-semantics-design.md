# Session Semantics Design

## Goal

Define the session model before continuing prompt tree, orchestration, and
session tooling work.

This document intentionally separates the current code names from the target
runtime concepts. The current code already works in broad strokes, but the
names `session`, `session instance`, `bulk`, `turn`, and `run` have drifted.
Further changes should make the model explicit instead of adding another layer
of ambiguous compatibility.

## Scope

This document is only about session and turn execution.

`memory` is outside this cleanup pass. Memory may later use agent-related
sessions as an information source for durable cross-session knowledge, but it
must not be used as a hidden backup layer for the current session scheduler,
segment rotation, or prompt compaction flow.

## Target Concepts

### Session

`Session` is the stable conversation container.

It answers:

- Which agent owns this conversation?
- Which channel/user/thread scope does this conversation correspond to?
- Which active segment is currently writable?
- Which segment history belongs to this same conversation?

The stable id is `session_key`.

`session_key` is resolved from channel/web/CLI context. The key is the idempotent
conversation bucket. Reusing the same key means the inbound request belongs to
the same conversation container.

Rules:

- A session belongs to one agent runtime binding.
- A session owns many segments over time.
- A session has exactly one active segment.
- A session is not a semantic memory store.

### Session Segment

`SessionSegment` is the writable message interval inside a session.

The current code calls this `SessionInstance` and stores the active segment id in
`Session.active_session_id`. Context Workspace projects these instances as
`session.segment.*` nodes. The old `session.bulk.*` prompt-tree label has been
retired.

It answers:

- Which exact messages are in the current active interval?
- Which old interval was compacted or closed?
- Which summary belongs to that old interval?
- Which raw message ranges can be expanded when the agent needs exact history?

Rules:

- New inbound messages are written to the active segment.
- Reset or compaction closes the current segment and opens a new one.
- Closed/compacted segments remain exact, addressable history under the same
  session.
- A compacted segment has a summary, but the raw ranges remain available through
  explicit session/context expansion.

### Turn

`Turn` is one inbound request to the runtime.

It answers:

- What did the user/system/channel ask the agent to do?
- Which session and active segment did the request bind to?
- Where should the final answer or delivery status be reported?
- What is the overall lifecycle of this request from accepted to terminal?

The current code does not have a separate `Turn` aggregate. Today
`OrchestrationRun` is carrying most of the turn responsibilities.

Target rules:

- A turn binds to one `session_key`.
- A turn starts against the active segment at intake time.
- A turn may pause for approval or background tools.
- Background tool completion should resume the same turn unless a deliberate new
  follow-up turn is created.
- Turn state is orchestration-owned; session only stores message facts.

### Execution Chain

`ExecutionChain` is the LLM/tool loop inside a turn.

It answers:

- Which LLM invocation happened first?
- Which tool calls did that invocation request?
- Which tool runs completed inline or in the background?
- Which later LLM invocation consumed those tool results?

The current code represents this with `OrchestrationRun.current_step`,
LLM invocation records, tool run ids, pending tool ids, and session messages.
There is no separate execution-chain entity yet.

Target rules:

- LLM invocation facts stay in the `llm` module.
- Tool run facts stay in the `tool` module.
- Session message facts stay in the `session` module.
- Orchestration owns the chain boundary and knows which invocation/tool facts
  belong to the current turn.
- Prompt assembly must use the execution-chain boundary, not a loose
  `sequence_no >= inbound_message.sequence_no` window, when provider-native
  protocol messages are needed.

### Lane

`Lane` is the scheduler serialization key.

It answers:

- Which turns must not run concurrently?
- Which worker may claim the next assignment?
- Which waiting turn should resume first?

The current default lane is derived from `session_key`.

Rules:

- Lane belongs to orchestration scheduling.
- Lane does not own session history.
- Lane does not decide memory visibility.

## Current Code Mapping

```text
Target Concept      Current Code
--------------      ------------
Session             session.domain.Session
session_key         Session.id and OrchestrationRun.metadata["session_key"]
SessionSegment      session.domain.SessionInstance
active segment id   Session.active_session_id / OrchestrationRun.active_session_id
Turn                mostly orchestration.domain.OrchestrationRun
ExecutionChain      OrchestrationRun + LLM invocations + ToolRuns + session messages
Lane                OrchestrationRun.lane_key / session_lane_key(session_key)
```

Important naming correction:

- `SessionInstance` should be understood as a segment.
- Context Workspace `session.segment.*` nodes are segment views.
- `bulk` is not an outer session container. Remaining `bulk` names belong to the
  older Session compaction use case/event vocabulary and should not leak into new
  Context Workspace node IDs or UI.

## Runtime Flow

The target flow is:

```text
channel/web/cli input
  -> resolve session_key
  -> resolve active SessionSegment
  -> create/bind Turn
  -> enqueue Turn on lane
  -> worker claims assignment
  -> build Context Workspace prompt tree
  -> invoke LLM
  -> run tools inline or background
  -> continue LLM/tool loop
  -> wait on approval/background tool when needed
  -> resume same Turn when wait completes
  -> complete/fail/cancel Turn
  -> maybe rotate SessionSegment by compaction/reset
```

The current runtime mostly follows this shape, except that `Turn` is still
represented by `OrchestrationRun`.

## Prompt Boundary

Context Workspace owns historical prompt delivery.

Normal provider-native messages should be limited to the current turn protocol:

- current inbound user content
- assistant tool-call messages needed by the provider protocol
- tool result messages needed to continue the current turn
- provider-specific attachment mirrors produced by Context Workspace rendering

Historical session content belongs in the Context Workspace XML tree:

- current active segment summary/ranges
- compacted segment summaries
- closed segment summaries
- expandable exact message ranges
- tool interaction nodes

This keeps one visible prompt body while preserving provider protocol
correctness.

## Segment Rotation

Compaction and reset both rotate the active segment, but they mean different
things.

### Compaction

Compaction closes the current segment, records a summary on that segment, archives
the selected old messages, and opens a new active segment under the same session.

The old segment remains visible in Context Workspace as a collapsed historical
segment. Raw ranges remain explicitly expandable under budget guards.

Compaction does not require a memory flush.

### Reset

Reset closes the current segment and opens a new active segment. It is a stronger
conversation boundary than compaction.

Reset must not silently migrate hidden context into the new segment. If handoff
is desired, it should be explicit and visible as a segment summary or requested
context node, not hidden memory injection.

## Session vs Memory

Session owns exact conversation facts:

- session container
- active segment pointer
- segment history
- user/assistant/tool/approval messages
- segment summary and raw ranges
- reset/compaction boundaries

Memory owns durable cross-session knowledge:

- user explicitly requested memories
- stable preferences and constraints
- long-term project facts
- public/shared/common knowledge scopes
- later, optional derived memories sourced from agent sessions

Memory must not be the mechanism that prevents current session history loss.
Session segment history already provides that exact trace.

## Required Cleanup

### Naming Cleanup

- Rename documentation and UI labels from `bulk` to `segment` where the concept
  is a `SessionInstance`.
- Keep storage fields such as `active_session_id` until a deliberate migration is
  scheduled, but document them as active segment ids.
- Avoid introducing new APIs that expose `bulk` as an architecture concept.

### Turn Boundary Cleanup

- Introduce an explicit turn concept in docs and read models before changing
  storage.
- Decide whether `OrchestrationRun` should be renamed/reframed as `Turn`, or
  whether a new `Turn` aggregate should wrap execution runs.
- Until then, treat `OrchestrationRun` as the current turn record, not a generic
  low-level execution attempt.

### Execution Chain Cleanup

- Make prompt assembly derive provider-native protocol messages from the current
  turn execution chain.
- Do not rely on session message sequence windows as the primary execution-chain
  boundary.
- Preserve existing LLM invocation ids and tool run ids as owner facts.
- Add orchestration query helpers that can answer: "which provider protocol
  messages are needed to continue this turn?"

### Maintenance Cleanup

- Remove memory flush as a mandatory pre-compaction step.
- Let compaction rotate session segments directly.
- Keep durable memory capture as an explicit memory/tool/policy action outside
  the session scheduling path.

### Context Workspace Cleanup

- Project `SessionInstance` as `session.segment.*` node ids.
- Do not reintroduce old `session.bulk.*` Context Workspace node ids.
- Session owner compaction APIs and events use segment vocabulary:
  `CompactSessionSegmentInput`, `compact_active_segment()`, and
  `session.segment.compacted`.
- Historical segment nodes should remain collapsed by default, with exact ranges
  expandable under budget guards.

## Acceptance Criteria

- A developer can explain the system without using `bulk` as an outer session
  term.
- Session history remains exact after compaction or reset.
- Memory is not required to preserve current session continuity.
- A normal turn prompt does not replay unrelated active-segment messages through
  provider-native transcript.
- Background tool completion resumes the same turn unless a new follow-up turn is
  explicitly created.
- Operations and Workbench can show session, segment, turn, execution chain, and
  lane as separate concepts.
