# Session Semantics Design

## Goal

Define a clean session model for the upgraded system before exposing session capabilities as tools.

This design intentionally favors a clear target model over backward compatibility.

The key principle is:

`session` owns conversation continuity, not semantic recall.

## Upgrade Stance

This is a new system.

We do not preserve ambiguous behavior for compatibility if that behavior weakens the model.

We prefer:

- fresh resets over implicit carry-over
- explicit agent switches over silent rebinding
- low coupling between `session`, `memory`, `orchestration`, and `frontend`

## Core Model

### Session Key

`session_key` is the stable conversation bucket.

It is agent-owned.

That means:

- a session bucket belongs to exactly one agent
- changing agent means selecting a different bucket
- an existing bucket is never rebound to another agent

### Session Instance

`active_session_id` identifies the active instance inside a bucket.

The system keeps:

- one stable `session_key`
- one active `session_id`
- zero or more archived instances under the same key

This preserves a clean separation:

- bucket identity
- active transcript identity
- run identity

### Run

Runs are orchestration-level execution records.

Runs bind to the active session instance at the moment they are created.

Runs do not redefine session ownership or session continuity rules.

## Reset Semantics

`reset` is a fresh reset.

When a session resets:

- `session_key` stays the same
- a new `active_session_id` is created
- subsequent messages write to the new instance
- old instance history remains exact and addressable under the old instance

Reset does not:

- inherit the previous instance transcript
- inherit the previous compaction summary into prompt context
- auto-handoff semantic context into the new instance

This is intentional.

If we later need handoff behavior, it should be added as a new explicit feature, not hidden inside reset.

## Compaction Semantics

Compaction is instance-local.

Its purpose is:

- reduce prompt cost
- preserve continuity inside the current active instance

Compaction is not a cross-reset continuity mechanism.

That means:

- a compaction summary belongs to the active instance that produced it
- a fresh reset does not import the old summary into the new instance
- session-level metadata may record compaction state for observability, but not for implicit prompt injection

## Agent Switching

Agent switching always creates or selects a different session bucket.

The frontend must not allow this ambiguous state:

- the UI still shows old history
- the next turn silently routes to a different agent

So the rule is:

- if the user switches agent while viewing an existing conversation, the UI must move to a fresh draft
- existing conversation history remains attached to its original agent-owned bucket

## Session vs Memory

`session` and `memory` are different systems.

### Session

Owns:

- exact conversation history
- active/archived instances
- message visibility and message metadata
- reset boundaries
- transcript-oriented continuity

### Memory

Owns:

- semantic recall
- embedding-backed retrieval
- long-term cross-session knowledge

Session history tools should use exact retrieval plus strict trimming.

They should not use embedding search.

## Tooling Direction

Session tools should be introduced in phases.

### Phase 1

Read-only tools:

- `session_status`
- `sessions_list`
- `sessions_history`

### Phase 2

Controlled write tools:

- `sessions_send`
- `sessions_yield`

### Phase 3

Subagent tools:

- `sessions_spawn`
- `subagents`
- `sessions_stop`

Subagent behavior should build on the semantics above rather than redefining them.

Requester-facing observability should stay exact and transcript-oriented:

- `session_status` may expose requester-tree and follow-up scheduling state
- `subagents` may expose spawned child-session tree state and current/latest run status
- these remain exact session-tree views, not memory recall

Operationally, the preferred inspection order is:

1. use `session_status` first for requester-wide state
2. use `subagents` only when you need per-child bucket or run details
3. use `sessions_history` only when you need exact transcript content from a chosen bucket or instance

The first `sessions_spawn` shape should stay narrow:

- create a fresh child session bucket under the current agent
- seed the child run with exact kickoff text
- enqueue the child run in the background
- return an accepted result immediately

It should not:

- implicitly carry over the parent transcript
- implicitly yield the parent run
- pretend the child result is available inline

`sessions_stop` should operate at requester-session tree scope:

- stop non-terminal runs in the requester session bucket
- recursively stop spawned child session buckets under that requester
- cascade into pending background tool runs owned by cancelled orchestration runs

## Design Consequences

This model keeps coupling low:

- `session` does not become `memory`
- `reset` does not become hidden handoff orchestration
- frontend routing does not mutate session ownership
- orchestration consumes session state through session services but does not own
  session storage rules
- compaction timing belongs to orchestration, while transcript archival and
  compaction-summary message metadata updates belong to `session`

This is the target model for the next session/tooling upgrade.
