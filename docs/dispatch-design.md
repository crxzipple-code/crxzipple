# Dispatch Subsystem Design

## Goal

Establish `dispatch` as an independent scheduling domain.

`dispatch` owns:

- queueing
- lane serialization
- claim and ownership
- wait and wake-up
- requeue and cancellation
- dispatch policy evaluation
- scheduling state transitions

`dispatch` does not own:

- prompt assembly
- session rules
- llm or tool execution semantics
- agent strategy
- outbound delivery

The key principle is:

`dispatch` schedules work; other subsystems interpret what that work means.

## Positioning

`dispatch` is not an orchestration helper.

It is a reusable supporting domain that can be consumed by:

- `orchestration`
- `tool`
- future `cron`
- future `hook`
- future channel or gateway workflows

Once extracted, `orchestration` becomes only one client of `dispatch`.

## Boundary

### Dispatch

Owns generic scheduling concepts:

- task identity
- task ownership reference
- lane identity
- dispatch policy
- claim lifecycle
- waiting and wake semantics

### Orchestration

Owns the agent run lifecycle:

- intake normalization
- route decision
- session bootstrap
- prompt assembly
- llm loop
- tool loop
- final result shaping

`orchestration` must not implement its own queue semantics once `dispatch` exists.

### Tool

Owns tool registration and tool execution lifecycle.

Tool execution may later choose to consume `dispatch`, but `dispatch` does not understand tool semantics.

## Naming

Use `dispatch` as the top-level module name.

Avoid `scheduler` as the bounded context name because it sounds narrower than the real scope.

Inside the subsystem, `scheduler` may still exist as an application service or policy engine.

## Target Package Layout

```text
src/crxzipple/modules/dispatch/
  domain/
    entities.py
    value_objects.py
    repositories.py
    exceptions.py
  application/
    services.py
    policies.py
    worker.py
  infrastructure/
    persistence/
  interfaces/
    http.py
    cli.py
    worker_cli.py
```

## Core Models

### DispatchTask

The aggregate root of the dispatch domain.

Suggested fields:

- `id`
- `owner_kind`
- `owner_id`
- `lane_key`
- `status`
- `policy`
- `priority`
- `payload_ref`
- `metadata`
- `claimed_by`
- `claim_token`
- `created_at`
- `updated_at`
- `queued_at`
- `claimed_at`
- `completed_at`

Notes:

- `owner_kind` identifies the consuming subsystem or work item kind, such as
  `orchestration_step`.
- `owner_id` is the foreign identifier inside that subsystem.
- `payload_ref` is opaque to `dispatch`; it can be a run id, URI, or storage pointer.

### DispatchPolicy

Dispatch policy is a domain concept, not a loose string.

Suggested first policies:

- `fifo`
- `lane_jump_queue`
- `jump_queue`
- `resume_first`

Semantics:

- `fifo`: normal queue ordering
- `lane_jump_queue`: move to the head of its own lane only
- `jump_queue`: outrank normal lane heads globally
- `resume_first`: outrank all non-resume tasks globally

### DispatchLane

Lane is the serialization boundary.

It may be represented only by `lane_key` in persistence at first, but it is still a first-class domain concept.

Lane responsibilities:

- isolate conflicting tasks
- define per-lane ordering
- provide the unit for "only one active task at a time"

### DispatchClaim

Optional explicit model for worker ownership.

Phase 1 can keep claim state on `DispatchTask`.

If lease and timeout semantics grow, `DispatchClaim` can become explicit.

## State Machine

`DispatchTask` owns its own scheduling state machine:

```text
created
  -> queued
  -> claimed
  -> waiting
  -> queued
  -> completed | cancelled | failed
```

Notes:

- `waiting` is dispatch-level waiting, not business execution waiting.
- `claimed` means a worker has ownership to progress the owner task.
- `completed` means dispatch work is done, not necessarily that the business operation succeeded semantically.
- `failed` means the dispatch task cannot progress under current scheduling rules.

## Dispatch Semantics

### Lane serialization

At most one active task can occupy a lane at a time.

Active means:

- `claimed`
- `waiting`

Queued tasks in the same lane compete only for that lane head position until the lane becomes available.

### Two-level ordering

Dispatch selection should use two levels:

1. choose the current head candidate for each lane
2. choose the next runnable task among lane heads globally

This is required to express:

- lane-local jump behavior
- global jump behavior
- resume-first behavior

without mixing unrelated lanes together.

### Worker ownership

Suggested worker fields:

- `claimed_by`
- `claim_token`
- `claimed_at`

Future extensions:

- `lease_expires_at`
- `heartbeat_at`

These belong to dispatch, not to orchestration.

## Contracts

`dispatch` must expose a narrow contract that does not depend on `OrchestrationRun`.

Suggested requests:

- `EnqueueDispatchTask`
- `ClaimNextDispatchTask`
- `WaitDispatchTask`
- `RequeueDispatchTask`
- `CompleteDispatchTask`
- `CancelDispatchTask`
- `FailDispatchTask`

Suggested query views:

- `DispatchTaskView`
- `DispatchLaneSnapshot`

## Consumer Contract

Consumers provide:

- `owner_kind`
- `owner_id`
- `lane_key`
- `policy`
- `priority`
- optional metadata

Consumers receive:

- task id
- status
- claim ownership
- wake/requeue outcomes

Consumers do not get to bypass dispatch state rules.

## Orchestration Integration

### Before extraction

Current orchestration behavior is implemented directly around `OrchestrationRun`.

That is acceptable only as a transition state.

### After extraction

`orchestration` should speak to `dispatch` like this:

- enqueue:
  `dispatch.enqueue(owner_kind="orchestration_step", owner_id=step_id, lane_key=..., policy=...)`
- claim:
  `dispatch.claim_next(worker_id=...)`
- wait:
  `dispatch.wait(task_id=..., reason=...)`
- resume:
  `dispatch.requeue(task_id=..., policy=resume_first)`
- complete:
  `dispatch.complete(task_id=...)`

Ingress and continuation tasks use their own owner kinds
(`orchestration_ingress`, `orchestration_continuation`) instead of overloading
run ownership.

`dispatch` must not know:

- what a prompt is
- what an llm invocation is
- what a tool call is
- what a session transcript is

## Why This Is a Domain

`dispatch` is a real domain because it has:

- its own language
- its own state machine
- its own invariants
- multiple consumers
- policy-driven behavior that is not reducible to raw storage

It is not just infrastructure glue.

It is a platform-level supporting domain.

## Migration Plan

### Phase 1

Keep scheduling inside `orchestration`, but formalize the language:

- `lane_key`
- `queue_policy`
- claim
- wait
- resume

This phase is already underway.

### Phase 2

Introduce `dispatch` domain objects and persistence:

- create `DispatchTask`
- create repository and UoW wiring
- move scheduling state and claim rules out of `OrchestrationRun`

During this phase, `orchestration` still remains the only consumer.

### Phase 3

Replace direct orchestration queue operations with dispatch contract calls.

At this point:

- `orchestration` no longer owns queue state
- `dispatch` owns all queue transitions

### Phase 4

Allow other subsystems to consume `dispatch`.

Candidates:

- background tool execution
- cron jobs
- webhook-driven jobs

## Non-Goals For First Extraction

Do not solve these in the first `dispatch` extraction:

- distributed queueing
- external brokers
- cross-process sharding
- tenant-level quota systems
- weighted fairness
- complex retry trees

The first goal is clear ownership and clean decoupling, not maximum sophistication.

## Design Rule

The extraction is only real if this statement becomes true:

`dispatch can schedule owner tasks without understanding orchestration internals.`
