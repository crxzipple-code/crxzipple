# Orchestration Subsystem Design

## Goal

`orchestration` is the application center for agent run coordination.

It owns the run lifecycle that spans multiple modules:

- intake normalization
- agent and model selection
- session resolution and session bootstrap planning
- lane-aware scheduling
- executor assignment and recovery
- engine advancement
- prompt assembly
- tool availability resolution
- approval and wait-state recovery
- run observation publishing

It does not own the internals of the modules it coordinates:

- `session` owns conversation persistence and session message mutation.
- `agent` owns profile data and agent policy.
- `llm` owns provider profiles, provider adapters, and invocation details.
- `tool` owns tool catalog, tool run records, tool workers, and tool execution details.
- `skills` owns skill catalog, source governance, read access, and run prompt readiness.
- `access` owns external credential readiness; `authorization` owns internal
  ABAC policy and grant decisions.
- `channels` own transport-facing runtime state and delivery.
- `events` owns topic publish/read/wait/cursor primitives.

The rule is simple: orchestration may coordinate a run across modules, but it must not absorb those modules' domain logic.

## Current Shape

The current orchestration package is organized around an application service graph, thin public surfaces, and explicit coordinators.

```text
src/crxzipple/modules/orchestration/
  domain/
    entities.py
    value_objects.py
    repositories.py
    exceptions.py
  application/
    service_graph.py
    scheduler_service.py
    intake_service.py
    execution.py
    worker.py
    engine.py
    engine_llm_invoker.py
    engine_session_recorder.py
    engine_tool_executor.py
    prompt_assembler.py
    llm_resolver.py
    tool_resolver.py
    # skill prompt readiness is delegated to modules/skills.application.prompt_resolver
    maintenance.py
    approval.py
    cancellation.py
    query.py
    runtime_events.py
    turn_submission.py
    coordinators/
      ingress.py
      intake.py
      requesting.py
      progress.py
      waiting.py
      recovery.py
      scheduler_signals.py
    observers/
      observation.py
    reactions/
      dispatch_recovery.py
      tool_terminal.py
    ports/
      access.py
      authorization.py
      dispatch.py
      llm.py
      memory.py
      runtime.py
      skill.py
      tool.py
  infrastructure/
    adapters/
    dispatchers/
    persistence/
  interfaces/
    http.py
    cli.py
    worker_cli.py
    shared.py
```

Important cleanup state:

- There is no `OrchestrationControlService`.
- There is no old `application/services.py` facade.
- There is no old `application/router.py` route center.
- There is no old `application/session_resolver.py`; session resolution is provided by the session module and used through orchestration workflows.
- Skill prompt readiness is not computed in orchestration. `PromptAssembler` passes run
  context and resolved tool ids into `SkillCatalogPort.resolve_prompt_catalog(...)`;
  Skills resolves tool/access/authorization/surface readiness and returns the catalog.
- Public API/CLI/channel turn submission helpers live in `application/turn_submission.py`, not in a top-level interface helper.

## Core Runtime Roles

### OrchestrationServiceGraph

`OrchestrationServiceGraph` wires the orchestration application. It is a composition root for orchestration services, not the old facade service.

It creates and connects:

- `OrchestrationRunQueryService`
- `OrchestrationIntakeService`
- `OrchestrationSchedulerService`
- `OrchestrationExecutorService`
- `RunExecutionService`
- `OrchestrationMaintenanceService`
- `RunCancellationService`
- `ApprovalResolutionService`
- `ApprovalControlService`
- run coordinators, recovery coordinators, and follow-up services

The graph may expose convenience methods for composition, but the primary runtime surfaces are the scheduler, executor, query, approval, cancellation, maintenance, and inspection services.

### Scheduler Service

`OrchestrationSchedulerService` is the scheduler-facing application surface.

It accepts high-level scheduling commands and cross-process scheduler signals. It delegates actual state transitions to coordinators and publishes wake-up events when work should move forward.

It owns scheduling flow, not execution internals.

### Executor Service

`OrchestrationExecutorService` is the executor-worker facing application surface.

It owns executor lease heartbeat, assignment admission, assignment processing, async assignment advancement, and executor runtime metrics. It does not decide lane semantics alone; lane safety is coordinated through scheduler/progress/lease state.

The executor exists to isolate run execution from scheduler intake and to prevent CPU-heavy work from blocking scheduler throughput. Concurrency is primarily a scheduler/executor design property, not a worker-process identity property.

### Engine

`OrchestrationEngine` advances one run until the next wait point or terminal state.

It coordinates:

- prompt assembly
- LLM invocation
- inline tool execution
- background tool submission
- session message recording
- result finalization

The engine does not claim queued work and does not own executor leases.

### Coordinators

Coordinators are the small application units that keep the service graph readable:

- `RunIngressCoordinator` records incoming run requests.
- `RunIntakeCoordinator` routes, binds sessions, and enqueues runs.
- `RunRequestCoordinator` creates scheduler-side requests such as heartbeats, compaction, and memory flushes.
- `RunProgressCoordinator` moves assigned runs through running states.
- `RunWaitCoordinator` handles approval waits, tool waits, and resume semantics.
- `RunRecoveryCoordinator` reconciles abandoned leases and terminal tool events.
- `RunSchedulerSignalCoordinator` records and consumes scheduler signal requests.

These are not independent domain owners. They are orchestration application components.

### Observers

Observers convert module-local facts into orchestration-facing observation facts.

Examples:

- run lifecycle facts become `orchestration.run.*` observation records
- session message facts become run/session observation records
- tool run facts become run-level tool observation records
- executor/runtime facts become runtime observation records

This is the key reason observation belongs in orchestration: tool and LLM modules should describe their own lifecycle, while orchestration observes and translates those details into the run lifecycle seen by external callers.

## Run Lifecycle

The outer run state machine is owned by `OrchestrationRun`.

```text
accepted
  -> routed
  -> bulk_ready
  -> queued
  -> running
  -> llm
  -> tool
  -> waiting_on_tool | waiting_confirmation
  -> finalizing
  -> completed | failed | cancelled
```

Notes:

- `queued` belongs to orchestration, not session.
- `llm` means the engine is waiting on or processing model execution.
- `tool` means the engine is handling tool execution logic.
- `waiting_on_tool` is used when background tool execution creates an async wait point.
- `waiting_confirmation` is used for approval or confirmation gates.
- Inline tool execution does not end the engine step.
- Background tool completion wakes orchestration through scheduler/runtime events, not by directly mutating the run from inside the tool module.

Inner lifecycles stay in their owning modules:

- LLM invocations remain LLM-owned.
- Tool run lifecycle remains tool-owned.
- Session messages remain session-owned.
- Channel connection and delivery state remains channel-owned.

## Submission Flow

API, CLI, and channel runtimes normalize inbound work and submit it to orchestration through application submission helpers or scheduler ports.

Typical flow:

1. Interface or channel runtime builds normalized turn submission options.
2. `turn_submission.py` builds orchestration input DTOs.
3. `OrchestrationSchedulerService` records the ingress request.
4. Intake routes the run, resolves session binding, and enqueues assignment work.
5. Scheduler dispatch wakes available executors.
6. Executor claims an assignment and asks the engine to advance the run.
7. Engine advances until terminal state or a wait point.
8. Observers publish run observation records for external listeners.

The interface layer should not create `ChannelInteraction`, bind runs, or call engine internals. Channel-specific inbound and replay behavior belongs in channel runtimes.

## Tool And Approval Flow

Tool execution follows the same boundary rule.

Inline tools may execute inside the engine step if they are safe and synchronous enough for that path.

Background tools are submitted to the tool module. The orchestration run records pending tool run ids and enters a wait state. Tool workers update tool-owned records and emit tool lifecycle events. Orchestration listens for terminal tool facts, reconciles pending waits, and wakes the run.

Approval is orchestration-facing but authorization-owned:

- orchestration detects a run is waiting for approval
- authorization decides and persists internal approval grants; access only
  participates when the action also needs external credential readiness
- `ApprovalControlService` is a narrow approval resolution surface, not a general control facade
- resolving approval resumes orchestration through wait/recovery coordinators

## Event Integration

Events are the cross-runtime coordination substrate.

Orchestration publishes or consumes:

- ingress request events
- scheduler signal request events
- executor assignment request events
- dispatch wake-up events
- tool terminal events
- run observation events
- runtime observation events

The `events` module remains generic. It does not know orchestration business semantics beyond registered contracts and surfaces.

## Boundaries

Allowed dependencies:

- orchestration application may call explicit ports for session, LLM, tool, skill, access, authorization, dispatch, and memory.
- interface layers may call orchestration public application services and DTO builders.
- channel runtimes may submit normalized inbound work to orchestration.
- observers may translate external module lifecycle facts into orchestration observation facts.

Disallowed dependencies:

- session must not route agents, tools, channels, or queue policy.
- tool must not claim to complete an orchestration run.
- LLM must not claim to complete an orchestration run.
- events must not perform orchestration decisions.
- channel HTTP endpoints must not create orchestration runs directly when a channel runtime owns the behavior.
- executor workers must not be the only lane safety authority; lane safety is scheduler/lease state.

## Acceptance Checks

Healthy orchestration structure should satisfy these checks:

- `OrchestrationControlService` is absent from public surfaces.
- old facade files such as `application/services.py`, `application/router.py`, and `application/session_resolver.py` do not return.
- run submission goes through `application/turn_submission.py` and scheduler services.
- worker execution goes through `OrchestrationExecutorService`.
- runtime observation is observed by orchestration observers.
- channel delivery remains channel-owned.
- session mutation happens through session application services.
- memory writes remain memory-owned; orchestration uses memory through a narrow context/port.

This document describes the current target direction. If implementation and this document disagree, prefer updating code toward the boundary rules rather than adding compatibility shims.
