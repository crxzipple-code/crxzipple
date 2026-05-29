# Port / Use Case Boundary Remediation Checklist 2026-05-16

## Status

Current owner: runtime architecture / module application boundaries.

This checklist follows the App Assembly / Container Target cutover. The
previous upgrade removed the old hand-wired container path and introduced
explicit target containers. This checklist is the next pass: make module
application boundaries stricter so ports, use cases and adapters stop being
mixed together.

This is not a compatibility plan. Do not add shims that keep both old and new
call paths alive. Each task should move ownership to the intended module or
integration application and delete the old assembly-side behavior in the same
change.

## Boundary Rules

Use these definitions for this repository:

- Use case / application service: owns a business action and its workflow.
- Inbound port: the callable contract a module exposes for a use case.
- Outbound port: the dependency contract a use case needs from another module
  or external system.
- Adapter: implements a port by calling a concrete service, repository or
  external API.
- App assembly: binds concrete implementations to ports for a runtime target.
  It must not own business translation, run lifecycle decisions or fallback
  behavior.

Rules for new work:

- A module application may expose an inbound port implemented by its application
  service.
- A module application may depend on outbound ports, not concrete services from
  another module.
- Cross-module use cases must have an explicit owner. If a workflow spans
  modules, create a named integration application/use case and inject narrow
  ports into it.
- App assembly may construct the use case and adapters, but must not construct
  domain/application command payloads as a substitute for a use case.
- Tool handlers may expose module capabilities as tools, but they do not own
  the module business semantics behind those capabilities.

## Current Boundary State

- Session tools (`sessions_send`, `sessions_spawn`, `sessions_cancel`) expose
  Tool handlers, but their business semantics are Session/Orchestration control
  actions. The translation now lives in the app-level integration use case
  `app/integration/session_runtime_control.py`; it is no longer exported from
  Orchestration as a module-owned application surface.
- `tool-worker` does have its own Tool scheduler/worker services. The Session
  tools still require `session_runtime_control`; the tool-worker and
  orchestration-executor targets now receive an app-integration ingress-backed
  implementation that depends on Orchestration's narrow
  submission/ingress-processing/cancellation ports. The ingress/intake chain is
  owned by `OrchestrationIngressRuntimeService`, not rebuilt in app integration
  or Tool worker.
- Orchestration submission and ingress processing now have separate ports:
  `OrchestrationSubmissionPort` and `OrchestrationIngressProcessingPort`.
  Continue checking target wiring so submission-only targets never regain
  scheduler processing access.
- Tool queue/execution surfaces now expose narrower runtime keys:
  `TOOL_QUERY_SERVICE`, `TOOL_RUN_CONTROL_SERVICE`,
  `TOOL_ORCHESTRATION_PORT` and `TOOL_WORKER_REGISTRY_SERVICE`.
  Queue-only targets no longer receive `TOOL_SERVICE` or
  `TOOL_WORKER_SERVICE`.
- Module application services are guarded by static tests against direct
  concrete imports from other owner modules in the audited paths. New
  cross-module workflows should extend those guards instead of relying on
  review memory.
- Tool and Orchestration still keep module-internal `ServiceGraph` composers.
  That is acceptable only while the graphs stay internal and external callers
  consume explicit inbound surfaces.
- Tool `ServiceGraph` is no longer part of the public app registry. The runtime
  plan exposes Tool through `tool.queue_services`,
  `tool.orchestration_queue_services` and `tool.execution_services`, which
  publish only query/run-control/orchestration/scheduler/worker/registry
  surfaces.
- Orchestration `ServiceGraph` no longer proxies request/recovery/scheduler
  owner methods through private pass-through functions. Scheduler and
  maintenance services are wired directly to the request coordinator, lease
  manager, wait coordinator and recovery coordinator where those owners already
  expose the required application method.
- Orchestration assignment lifecycle behavior now lives in
  `RunAssignmentLifecycleService`. This named application service owns the
  non-trivial side effects around progress, wait, heartbeat, lease release,
  prompt-flow cleanup and session-spawn follow-up signaling. `ServiceGraph`
  wires it but does not implement those actions itself.
- Orchestration recovery no longer depends on the concrete
  `RunWaitCoordinator`. It receives the narrow `continue_recovery_contract`
  callable it needs to continue stalled waiting runs.
- Orchestration runtime assembly no longer exposes `service_graph` as a
  returned field. The graph remains an internal constructor for explicit
  surfaces only.
- API/admin Orchestration assembly no longer publishes the worker-owned
  `ORCHESTRATION_SCHEDULER_SERVICE` or `ORCHESTRATION_EXECUTOR_SERVICE` keys.
  HTTP, admin CLI and Operations action entrypoints consume
  `ORCHESTRATION_SUBMISSION_SERVICE`,
  `ORCHESTRATION_SCHEDULER_MAINTENANCE_SERVICE` and
  `ORCHESTRATION_EXECUTOR_CONTROL_SERVICE`; the broad scheduler/executor keys
  remain limited to worker targets and the dedicated `test` runtime.

## Checklist

### 1. Session Tool Control Ownership

- [x] Define the owner use case for Session tool control. The target shape is a
      Session-owned or Session+Orchestration integration application that owns:
      send-to-session, spawn-child-session, cancel-session-tree and runtime run
      listing semantics. Current implementation:
      `app/integration/session_runtime_control.py`.
- [x] Define a narrow inbound contract for Tool handlers, for example
      `SessionControlPort` or `SessionToolControlPort`. It should accept
      Session-level commands, not Orchestration command objects. The existing
      `SessionRuntimeControlPort` is retained as that contract for this pass.
- [x] Define outbound ports needed by that use case, such as:
      session query/tree lookup, session run submission, orchestration run query,
      orchestration run cancellation and tool-run cancellation.
      Current pass moved those contracts into
      `orchestration/application/ports/context.py`, uses the existing
      orchestration run query/submission/ingress-processing/cancellation ports,
      and keeps only the Session-to-Orchestration command translation under
      `app/integration`.
- [x] Move construction of `SubmitOrchestrationTurnInput`,
      `SubmitBoundOrchestrationTurnInput`, `AcceptOrchestrationRunInput`,
      `InboundInstruction`, `SessionRouteContext`, `DirectSessionScope` and
      session-tool metadata out of `app/assembly/session_runtime.py`.
- [x] Update `tools/sessions/local.py` to call the new Session control inbound
      contract. The Tool package should remain responsible only for tool
      argument parsing, validation, rendering and capability exposure. The
      handler contract did not need to change; the implementation behind the
      port moved.
- [x] Remove `ToolWorkerSessionRuntimeControl` after the new use case is wired.
      Tool worker must not construct `RunIngressCoordinator`,
      `RunIntakeCoordinator` or `RunCancellationService` locally.
- [x] Move lightweight ingress/intake construction out of
      `app/integration/session_runtime_control.py`. Orchestration now exposes
      `OrchestrationIngressRuntimeService` for executor/tool-worker targets;
      the integration layer only calls ports and maps Session inputs to
      Orchestration submit inputs.
- [x] Keep target behavior equivalent for `sessions_send`, `sessions_spawn`,
      `sessions_cancel` and session read/wait tools.

### 2. Orchestration Port Split

- [x] Split the former scheduler submit port into a submission-only port and a
      processing/runtime port: `OrchestrationSubmissionPort` and
      `OrchestrationIngressProcessingPort`.
- [x] Move `process_run_request()` out of any submission-only contract.
- [x] Delete fail-fast `process_run_request()` from
      `OrchestrationIngressSubmissionService` once no caller expects it.
- [x] Make channel runtime depend on the submission-only port.
- [x] Make scheduler/executor targets depend on processing/runtime ports only
      where they actually process requests or assignments.
      `orchestration.runtime` was split into admin, test, scheduler and
      executor factories. The worker CLI now selects scheduler, executor or
      admin containers per command: pure scheduler commands no longer receive
      the executor surface, pure executor commands no longer receive the
      scheduler surface, linked scheduler/executor benchmarks open both target
      containers explicitly, and daemon-runtime benchmark/admin commands use the
      admin target. HTTP/admin/Operations entrypoints use only submission,
      maintenance and executor-control keys. Executor session tools use the
      ingress-backed `session_runtime_control` so they do not import scheduler
      control.
- [x] Add architecture tests proving submission-only targets cannot access
      scheduler processing methods.

### 3. Tool Surface Split

- [x] Inventory `TOOL_SERVICE`, `TOOL_SCHEDULER_SERVICE` and
      `TOOL_WORKER_SERVICE` call sites by target.
- [x] Introduce narrower Tool application surfaces where needed, for example:
      catalog/query, queue submission, scheduler control, worker execution,
      worker state/readiness and runtime event handling.
- [x] Stop `tool_queue_factories()` from providing `TOOL_WORKER_SERVICE` to
      targets that do not execute tool runs.
- [x] Add a narrow worker registration surface for scheduler-only use:
      `TOOL_WORKER_REGISTRY_SERVICE`.
- [x] Update Operations/Event Relay/Channel runtime to consume Tool query or
      event ports instead of the worker service where possible.
      Operations Tool read models now type against
      `OperationsToolQueryPort`; Event Relay uses event publish/stream ports
      instead of concrete Events service types.
- [x] Keep Tool's own scheduler/worker lifecycle inside the Tool module.
      Orchestration may observe Tool lifecycle facts and wait on terminal tool
      events, but it does not own Tool scheduling.
- [x] Add target assembly tests proving non-worker targets do not receive
      worker execution capabilities.

### 4. Cross-Module Concrete Dependency Reduction

- [x] Audit module application constructors for direct concrete imports from
      other modules. Start with Orchestration, Channels, Tool, Mobile/OCR and
      Operations read models.
      Orchestration application constructors, Channel runtime and Tool service
      support were scanned and cleaned in this pass. Follow-up cleanup also
      covered Operations source read models/runtime/projection materializer,
      OCR artifact reads, Channel daemon spec sync, Dispatch wakeup, Event
      Relay, Daemon process control, and Access settings integration/import.
- [x] Replace Orchestration dependencies on concrete Agent, Session, Artifact,
      Tool, LLM, Authorization and Events services with narrow application
      ports where the dependency is not already expressed as a port.
      Current pass added Orchestration outbound ports for agent profile lookup,
      artifact variant reads, event publish/wait/subscription streams, session
      transcript/message/metadata/query surfaces and session resolution. The
      production Orchestration application package no longer contains
      `AgentApplicationService`, `ArtifactApplicationService`,
      `EventsApplicationService`, `SessionApplicationService` or the old local
      `SessionTreeLookupPort` type.
- [x] Replace Channel runtime dependencies on concrete Agent, Access,
      Artifacts and Events services with narrow ports where practical.
      Current pass added Channel outbound ports for access readiness, agent
      profile lookup, artifact reads and event stream read/write.
- [x] Replace Tool service support dependencies on concrete Artifacts/Events
      services with explicit artifact/event ports.
      Current pass added `ToolArtifactWritePort`, `ToolEventWaitPort` and
      `ToolEventSubscriptionStreamPort`.
- [x] Continue replacing Operations read model concrete owner services with
      read/query ports. `LlmOperationsReadModelProvider` now uses
      `OperationsLlmQueryPort`; factory context and module overview read models
      now use Operations-owned read/query ports. Tool read models now use
      `OperationsToolQueryPort`.
- [x] Keep direct concrete dependencies only when they are module-internal or
      explicitly documented as a temporary exception in this checklist.
- [x] Add static architecture tests for forbidden cross-module concrete service
      imports from `modules/*/application`.
      Current guards:
      `tests/unit/test_orchestration_service_surface.py::test_orchestration_application_does_not_type_against_owner_services`,
      `tests/unit/test_operations_read_model_boundaries.py`, and
      `tests/unit/test_application_port_boundaries.py`.

### 5. ServiceGraph Shape

- [x] Decide which `ServiceGraph` classes are allowed as module-internal
      composers and which should be split into named use cases.
      Current decision: Tool and Orchestration service graphs may remain as
      module-internal composers, but they are not public module APIs.
- [x] Keep allowed service graphs internal to their module application package;
      do not expose them as the primary cross-module API.
      `OrchestrationServiceGraph` was removed from the public orchestration
      application surface and from container `AppKey` exposure.
      `ToolServiceGraph` was also removed from container `AppKey` exposure on
      2026-05-18; assembly factories now return only named Tool surfaces.
- [x] Convert broad service graph outputs into explicit inbound surfaces.
      External callers should not need the whole graph to perform one action.
      Orchestration now exposes named surfaces from assembly:
      query/inspection/approval/cancellation/intake/submission/maintenance/
      executor-control, with scheduler/executor worker services scoped to
      worker targets.
      Tool exposes query/run-control/orchestration/scheduler/worker/registry
      surfaces instead of requiring callers to grab the full graph.
- [x] For Orchestration, identify scheduler, executor, approval, cancellation,
      inspection, submission and ingress processing as separate surfaces.
- [x] For Tool, identify catalog/query, submission, scheduler, worker and
      readiness/event surfaces separately.
- [x] Remove trivial request/recovery/scheduler pass-through methods from
      `OrchestrationServiceGraph`. The graph must not pretend to own
      `request_compaction`, `request_heartbeat`, lease assignment, recovery or
      terminal tool-run handling when those are already coordinator/service
      methods.
- [x] Continue shrinking the remaining Orchestration executor assignment
      callback mesh. The remaining graph-owned methods should either become a
      named Orchestration application service for assignment lifecycle
      semantics or be wired directly to the owning coordinator when no release
      / follow-up side effect is needed.
      Current implementation:
      `orchestration/application/assignment_lifecycle.py`.
- [x] Break the concrete recovery-to-wait coordinator dependency. Recovery
      should depend on a continuation callable, not the full wait coordinator
      type.
- [x] Stop returning the full `OrchestrationServiceGraph` from the app-level
      `OrchestrationRuntimeAssembly`; only named surfaces are returned to app
      assembly callers.

### 6. App Assembly Enforcement

- [x] App assembly factories may instantiate use cases and adapters, but must
      not construct business command payloads except for pure adapter wiring.
      Guarded by
      `tests/unit/test_app_assembly_architecture.py::test_app_assembly_does_not_construct_cross_module_orchestration_commands`.
- [x] App assembly factories must declare exact `AppKey` dependencies matching
      the narrow ports needed by the target.
      Existing target-scoping tests cover query-only, submission-only,
      queue-only and worker-only capabilities.
- [x] Activation tasks must remain idempotent setup steps, not hidden business
      workflows.
      Guarded by
      `tests/unit/test_app_assembly_architecture.py::test_activation_tasks_are_declared_idempotent`.
      Daemon spec bootstrap is additionally scoped to control-plane targets so
      worker startup does not mutate daemon configuration.
      Agent profile bootstrap is also scoped to control-plane targets so
      worker startup does not sync profile config or write Agent home files.
- [x] Target containers must remain selective. `api`, `tool-worker`,
      `orchestration-scheduler`, `orchestration-executor`,
      `operations-observer`, `event-relay-worker` and `channel-runtime` should
      only receive the capabilities they need.
      Tool/query/submission/read-model targets are guarded today. Scheduler and
      executor targets are now also guarded against cross-leaking
      `ORCHESTRATION_SCHEDULER_SERVICE`,
      `ORCHESTRATION_EXECUTOR_SERVICE`, `ORCHESTRATION_RUNTIME` and the
      scheduler runtime event surface. Executor/tool-worker session tools now
      receive only `ORCHESTRATION_SUBMISSION_SERVICE`,
      `ORCHESTRATION_INGRESS_PROCESSING_SERVICE`,
      `ORCHESTRATION_CANCELLATION_SERVICE` and
      `ORCHESTRATION_RUN_QUERY_SERVICE`.
      API/admin targets are guarded against regaining
      `ORCHESTRATION_SCHEDULER_SERVICE` or `ORCHESTRATION_EXECUTOR_SERVICE`;
      `test` keeps its explicit integration runtime for unit suites that need
      both worker services in one process.
- [x] Add review guards for app assembly files that instantiate cross-module
      command/input objects such as Orchestration turn inputs from Session tool
      semantics.
- [x] Add review guards preventing `app/integration/session_runtime_control.py`
      from importing Orchestration coordinators, processing functions or
      cancellation service internals.

## Validation Gates

Static checks:

```bash
rg -n "from crxzipple\\.app|import crxzipple\\.app" src/crxzipple/modules -g '*.py'
rg -n "container\\.(?!require\\(|has\\(|get\\(|close\\(|close\\b|snapshot\\(|target\\b|registry\\b)[A-Za-z_]" src/crxzipple -g '*.py' --pcre2
rg -n "SubmitOrchestrationTurnInput|SubmitBoundOrchestrationTurnInput|SessionRouteContext|InboundInstruction" src/crxzipple/app/assembly -g '*.py'
rg -n "RunIngressCoordinator|RunIntakeCoordinator|RunCancellationService|process_ingress_request|fail_ingress_backed_run_record|OrchestrationScheduler\\(" src/crxzipple/app/integration/session_runtime_control.py
rg -n "def _assign_next_assignment|def _process_next_assigned_assignment|def _next_assigned_assignment|def _process_assigned_assignment|def _process_assigned_assignment_async|def _advance_assignment|def _wait_assignment_on_tool|def _wait_for_confirmation|def _heartbeat_assignment|def _complete_assignment|def _fail_assignment|def _admit_assignment|def _clear_prompt_flow_hint|def _request_compaction|def _request_heartbeat|def _request_memory_flush|def _request_due_heartbeats|def _recover_abandoned_runs|def _expire_executor_leases|def _handle_recovered_dispatch_task|def _handle_terminal_tool_run|def _continue_recovery_contract" src/crxzipple/modules/orchestration/application/service_graph.py
rg -n "RunWaitCoordinator|wait_coordinator" src/crxzipple/modules/orchestration/application/coordinators/recovery.py
```

Expected result after this checklist:

- no module imports `crxzipple.app`;
- no production service locator access returns;
- app assembly no longer builds Session tool semantics into Orchestration turn
  commands;
- submission-only ports do not expose processing methods;
- non-worker targets do not receive worker execution capabilities.
- queue-only targets do not receive the full `TOOL_SERVICE` surface.
- Session runtime integration does not rebuild Orchestration ingress/intake or
  cancellation internals.
- Orchestration `ServiceGraph` does not reintroduce private pass-through
  methods for request/recovery/scheduler owners or assignment lifecycle
  actions.
- Orchestration recovery does not regain a concrete dependency on
  `RunWaitCoordinator`.
- App-level orchestration runtime assembly does not expose `service_graph`.
- App-level orchestration runtime assembly does not expose the broad
  `orchestration.runtime` registry value; callers consume named surfaces only.
- API/admin entrypoints do not require the Orchestration scheduler/executor
  worker keys directly.
- App-level Tool runtime assembly does not expose `tool.service_graph` or
  `tool.execution_service_graph`.

Behavior suites to keep green:

- `PYTHONPATH=src pytest -q tests/unit/test_sessions_tool_http.py`
- `PYTHONPATH=src pytest -q tests/unit/test_orchestration_queue.py`
- `PYTHONPATH=src pytest -q tests/unit/test_tool_background.py tests/unit/test_tool_providers.py`
- `PYTHONPATH=src pytest -q tests/unit/test_app_assembly_targets.py tests/unit/test_app_assembly_architecture.py`
- `PYTHONPATH=src pytest -q tests/unit/test_turns_http.py tests/unit/test_orchestration_http.py tests/unit/test_orchestration_cli.py`
- `PYTHONPATH=src pytest -q tests/unit/test_channels.py tests/unit/test_channel_runtime.py`
- `PYTHONPATH=src pytest -q tests/unit/test_application_port_boundaries.py tests/unit/test_operations_read_model_boundaries.py`

Frontend validation is required only if API contracts or Operations/Settings
read models change:

```bash
cd frontend
npm run typecheck
npm run build
```

## Reviewer Rejection Rules

Reject changes that:

- rename a broad service to a port without reducing its responsibility;
- move business workflow from one assembly file to another assembly file;
- make Tool worker depend on full Orchestration scheduler/executor runtime;
- make Orchestration own Tool scheduling;
- leave old and new Session control paths both active;
- add generic resolver/container access to solve a missing dependency;
- add compatibility facades for old `session_runtime_control` behavior without
  deleting the old implementation.
