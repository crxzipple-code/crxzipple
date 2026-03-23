# Orchestration Subsystem Design

## Goal

Establish a single orchestration center for all cross-subsystem coordination.

The orchestration subsystem owns:

- intake normalization
- routing
- agent selection
- session bulk resolution and bootstrap
- queueing and wake-up
- engine advancement
- prompt assembly
- tool availability resolution
- outbound delivery

The orchestration subsystem does not own:

- session persistence rules
- llm provider integration
- tool registration or tool execution internals
- authorization policy storage or evaluation internals

## Boundary

### Orchestration

Owns all multi-subsystem coordination.

### Session

Owns only persistent conversation context:

- `SessionBulk`
- `Session`
- `SessionMessage`

Session does not understand interfaces, agent selection, routing, queueing, or prompt assembly.

### Agent

Owns profile and strategy:

- system prompt defaults
- model routing defaults
- execution policy
- workspace and sandbox preferences

### LLM

Owns:

- llm profiles
- llm invocations
- provider adapters
- streaming normalization

### Tool

Owns:

- tool catalog
- tool schemas
- tool execution
- `ToolRun` lifecycle

### Authorization

Owns authorization decisions only.

## Naming

Use `orchestration` as the top-level module name.

Avoid `runtime` as the module name because the codebase already uses `runtime` in:

- `ToolRuntimeRegistry`
- `ToolRuntimeRouter`
- `AgentRuntimePreferences`

## Target Package Layout

```text
src/crxzipple/modules/orchestration/
  domain/
    entities.py
    value_objects.py
    repositories.py
    exceptions.py
  application/
    services.py
    router.py
    session_resolver.py
    scheduler.py
    worker.py
    engine.py
    prompt_assembler.py
    model_selector.py
    tool_resolver.py
    outbound.py
    event_handlers.py
  infrastructure/
    persistence/
    queue/
  interfaces/
    http.py
    cli.py
    worker_cli.py
```

## Core Models

### OrchestrationRun

The single outer run aggregate.

Suggested fields:

- `id`
- `status`
- `stage`
- `bulk_key`
- `active_session_id`
- `agent_id`
- `delivery_target`
- `lane_key`
- `priority`
- `current_step`
- `max_steps`
- `pending_tool_run_ids`
- `waiting_reason`
- `inbound_payload`
- `result_payload`
- `error_payload`
- `created_at`
- `started_at`
- `completed_at`

### RouteDecision

Application-level routing result.

Suggested fields:

- `agent_id`
- `bulk_key`
- `lane_key`
- `priority`
- `queue_policy`
  Suggested values: `fifo`, `lane_jump_queue`, `jump_queue`, `resume_first`
- `delivery_target`
- `metadata`

### SessionBundle

Application DTO returned by orchestration-owned session resolution.

Suggested fields:

- `bulk`
- `active_session`
- `recent_messages`
- `resolution`

This is not a new session aggregate.

### PromptEnvelope

The final payload passed into the llm subsystem.

Suggested fields:

- `llm_id`
- `messages`
- `tool_schemas`
- `response_format`
- `overrides`
- `metadata`

### ResolvedToolSet

The effective tool view for one run step.

Suggested fields:

- `schemas`
- `execution_targets_by_tool`
- `background_allowed_tools`
- `confirmation_required_tools`
- `hidden_policy_metadata`

## State Machine

`OrchestrationRun` owns the outer state machine:

```text
accepted
  -> routed
  -> bulk_ready
  -> queued
  -> running
  -> llm
  -> tool
  -> waiting_on_tool
  -> finalizing
  -> completed | failed | cancelled
```

Notes:

- `queued` belongs to orchestration, not session.
- `llm` means the engine is currently in model execution.
- `tool` means the engine is currently handling tool execution logic.
- `waiting_on_tool` is used only when background tool execution creates an async wait point.
- `inline` tool execution does not end the engine step.

Inner state machines remain where they already belong:

- `LlmInvocation`: `created -> running -> succeeded/failed`
- `ToolRun`: `created -> queued -> dispatching -> running -> ...`

## Components

### Router

Responsibilities:

- normalize inbound instruction
- select agent
- compute `bulk_key`
- compute `lane_key`
- choose priority and queue policy
- build `RouteDecision`

### SessionResolver

Responsibilities:

- find or create `SessionBulk`
- get or create active `Session`
- perform session bootstrap
- append session-level system events when needed
- return `SessionBundle`

Session bootstrap means conversation bootstrap, not llm prompt assembly.

### Scheduler

Responsibilities:

- enqueue run
- claim next runnable run
- cancel queued run
- requeue run
- wake suspended run
- enforce per-lane serialization

It does not invoke llm or tools.

### Worker

The queue consumer.

Responsibilities:

- poll or claim queued orchestration runs
- call `engine.advance(run_id)`
- commit state transitions

### Engine

Responsibilities:

- advance a run until the next wait point or terminal state
- call prompt assembler
- call model selector
- invoke llm
- inspect llm output
- invoke inline tools
- start background tool runs
- finalize assistant output

The engine does not own queue consumption.

### PromptAssembler

Dedicated component used by engine before every llm call.

Responsibilities:

- read session history
- include current inbound message
- include tool results from prior steps
- include agent prompt policy
- load workspace/bootstrap files
- inject resolved tool schemas
- build `PromptEnvelope`

This is distinct from session bootstrap.

### ModelSelector

Responsibilities:

- choose effective `llm_id`
- apply agent model policy
- apply per-run hints
- support future fallback policy

### ToolResolver

Responsibilities:

- read tool catalog
- evaluate authorization
- apply agent policy
- apply environment and sandbox constraints
- return `ResolvedToolSet`

Tool exposure is orchestration-owned because it requires coordination between:

- tool
- authorization
- agent
- environment
- session or inbound metadata

### OutboundDispatcher

Responsibilities:

- send final or partial output back to the originating surface
- translate orchestration results into surface-specific delivery requests

## Background Tool Flow

Only background tool execution should break the engine into multiple advances.

Flow:

1. Engine receives llm output containing tool calls.
2. For inline tools, engine executes and continues the loop.
3. For background tools, engine creates `ToolRun` entries and records `pending_tool_run_ids`.
4. Engine marks the orchestration run as `waiting_on_tool` and returns.
5. Orchestration event handlers listen for `tool.run.succeeded`, `tool.run.failed`, and `tool.run.cancelled`.
6. When all pending tool runs reach terminal state, orchestration wakes the run.
7. Worker claims the run again and re-enters engine advancement.

Session never drives this wake-up. It is only updated with resulting facts.

## Session Boundary Changes

Current session code contains routing logic and agent-shaped data. The target state is smaller.

Target session primitives:

- `get_bulk(bulk_key)`
- `create_bulk(bulk_key, metadata)`
- `get_active_session(bulk_key)`
- `activate_new_session(bulk_key, reason, metadata)`
- `append_messages(session_id, messages)`
- `list_messages(session_id, limit, before)`

Target `SessionBulk` should prefer fields like:

- `id`
- `active_session_id`
- `status`
- `metadata`
- `created_at`
- `updated_at`

Agent selection and interface-derived routing should move out of session and into orchestration.

## Suggested Interfaces

```python
class OrchestrationService:
    def accept(self, instruction: InboundInstruction) -> OrchestrationRun: ...
    def wake(self, run_id: str, *, reason: str) -> OrchestrationRun: ...
    def cancel(self, run_id: str) -> OrchestrationRun: ...


class Router:
    def route(self, instruction: InboundInstruction) -> RouteDecision: ...


class SessionResolver:
    def resolve(self, decision: RouteDecision, instruction: InboundInstruction) -> SessionBundle: ...


class Scheduler:
    def enqueue(self, run: OrchestrationRun) -> None: ...
    def claim_next(self, *, worker_id: str) -> OrchestrationRun | None: ...
    def wake(self, run_id: str) -> None: ...


class Engine:
    def advance(self, run_id: str) -> OrchestrationRun: ...


class PromptAssembler:
    def assemble(self, run: OrchestrationRun, bundle: SessionBundle) -> PromptEnvelope: ...


class ToolResolver:
    def resolve(self, run: OrchestrationRun, bundle: SessionBundle) -> ResolvedToolSet: ...
```

## Event Integration

The existing event bus is sufficient for the first version.

Orchestration should subscribe to:

- `tool.run.succeeded`
- `tool.run.failed`
- `tool.run.cancelled`
- optionally `tool.run.requeued`

This lets orchestration wake suspended runs after background tool completion.

## Implementation Plan

### Phase 1

Create orchestration skeleton:

- new module
- `OrchestrationRun`
- repository and persistence
- scheduler and worker skeleton

### Phase 2

Extract routing out of session:

- move session key computation into orchestration router
- keep session API primitive

### Phase 3

Add `SessionResolver` and session bootstrap:

- find or create bulk
- activate current session
- return `SessionBundle`

### Phase 4

Add minimal engine:

- prompt assembler
- model selector
- llm invoke
- write final reply back to session

### Phase 5

Add tool coordination:

- `ToolResolver`
- inline tool loop
- max-step guard

### Phase 6

Add background tool wait and wake:

- pending tool ids
- event-driven wake-up
- worker resume path

### Phase 7

Migrate interfaces:

- CLI entry uses orchestration
- HTTP entry uses orchestration
- future channels use orchestration

## Migration Rule

Any logic that needs more than one subsystem at the same time should move toward orchestration.

Examples:

- route to agent plus session bulk
- session bootstrap plus inbound source handling
- tool availability plus authorization plus environment
- workspace files plus session history plus system prompt
- background tool completion plus run resume

If the logic can be explained entirely inside one subsystem, keep it there.
