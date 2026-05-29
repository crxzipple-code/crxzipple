# App Assembly / Container Target Refactor Checklist 2026-05-14

## Status

Current owner: runtime architecture / app assembly.

This checklist is the current construction entry for replacing the hand-wired
container with an explicit app assembly layer. It is not a minimal migration
plan. Do not keep compatibility tracks that preserve the old container assembly
path.

Current cutover note: `app/assembly/runtime.py` now assembles the runtime graph
used by HTTP, daemon/worker entrypoints and admin CLI commands. Tool worker,
Tool scheduler, Event relay worker, Operations observer, Orchestration worker,
Channel runtime, Daemon supervisor CLI, top-level `ask/chat`, HTTP API startup
and shared module admin CLI commands have been cut to explicit runtime targets.
Runtime entrypoints now share `interfaces/runtime_container.py` for target
container lifecycle, target-owned memory watcher policy and root Typer command
container reuse. The remaining old-container work is deletion of historical
references, not keeping a compatibility bridge alive.

Progress on 2026-05-14:

- Added app assembly primitives in `src/crxzipple/app`.
- Added explicit target/entrypoint metadata in `src/crxzipple/app/assembly`.
- Added the tool capability catalog model inside the Tool module.
- Added first module-local assembly factories for database/session, settings,
  events, access, authorization and LLM.
- Moved Agent home memory-binding ownership from Orchestration infrastructure
  to Agent infrastructure, then added Agent module-local assembly factories and
  bootstrap activation.
- Added Session, Dispatch and Memory module-local assembly factories backed by
  focused construction tests.
- Added Process and Daemon module-local assembly factories. Process owns only
  its process service/repository/supervisor construction; Daemon owns only
  service/spec/instance/lease management, while concrete runtime daemon specs
  remain an app-level activation concern.
- Added Artifacts and Skills module-local assembly factories. Artifacts owns
  filesystem artifact storage/service construction; Skills owns catalog/read/
  install manager construction plus the settings-backed enablement wrapper.
- Moved Browser, Mobile and OCR runtime construction into app assembly. The old
  bootstrap runtime infrastructure module has been removed; runtime code imports
  app assembly builders or assembled `AppKey` applications directly.
- Moved Channel profile/config/interaction/runtime-registry construction into
  app assembly, with Channel daemon control expressed as an explicit
  Channels + Daemon integration factory.
- Moved Tool execution service graph construction and execution-time capability
  bindings into app assembly. `runtime_plan()` now supplies orchestration
  ordering and delegates Tool + Access + Artifact + Browser + Mobile + Process
  + Session binding to `app/assembly/tool.py`.
- Moved Daemon manager construction into app assembly. Process service
  construction is now exposed by `app/assembly/process.py`; Daemon + Process
  manager integration lives in `app/assembly/daemon.py`.
- Moved Orchestration runtime graph construction into app assembly. Prompt
  assembly, tool resolution, orchestration engine creation and service graph
  construction now live in `app/assembly/orchestration.py`; `runtime_plan()`
  orders Tool execution, Orchestration runtime and Tool package activation.
- Hardened Orchestration HTTP/CLI tests against the new LLM credential boundary:
  tests now isolate repo-default LLM profile configs and register OpenAI profiles
  with explicit Access `credential_binding_id` values.
- Added Tool module-local assembly factories for bootstrap config, enablement,
  capability catalog, discovery/runtime registries and queue services. Built-in
  tool manifests now declare formal capability ids that are validated while
  package plans are loaded.
- Replaced free-form Tool package `services` injection with explicit
  `ToolDependencyBinding` values. App assembly now publishes initial Tool
  capability bindings, and package activation validates unavailable target
  capabilities, missing dependency bindings, credential-provider requirements
  and enforced external runtime requirements.
- Centralized runtime entrypoint container lifecycle in
  `interfaces/runtime_container.py`: process-scoped workers use
  `runtime_container(...)`, Typer root commands use
  `ensure_typer_runtime_container(...)`, and memory file watchers are enabled by
  explicit `AssemblyTarget` policy instead of ad hoc call-site defaults.
- Removed the obsolete HTTP `create_app(event_bus=...)` override surface. API
  startup now resolves the event backend only through app assembly.
- Added architecture checks that daemon service-set keys and runtime daemon
  specs resolve to known assembly targets, and that target-owned memory watcher
  policy stays explicit.
- Added `runtime.cleanup_tasks` as the single app-level lifecycle release
  surface. Cleanup tasks carry explicit order and failure isolation;
  `AppContainer.close()` no longer knows Tool, Browser, Process, Memory, Events
  or Database internals, and still attempts every task before surfacing an
  aggregate cleanup error. Current close order is Tool remote clients, Browser
  pools/control, Process supervisor, Memory watcher, Events backend, shared HTTP
  clients, then Database engine.
- Cleaned the dev Redis-stack shutdown script so it stops current runtime
  workers (`operations-observer`, `event-relay`, tool/orchestration/channel)
  without preserving retired orchestration observation and legacy API/supervisor
  cleanup paths.
- Added the app assembly Tool package activation task. Session tools no longer
  import or name Orchestration services; they depend on a Session-owned
  `session_runtime_control` port, with the current Orchestration-backed adapter
  assembled outside Tool.
- Added focused tests for dependency validation, target mapping and capability
  validation, plus first module-local factory construction.
- Added first-class `ToolRun` submission metadata. Orchestration now copies
  run/session/agent/tool-call/workspace correlation into ToolRun metadata at
  submission time, leaving invocation context as the cropped runtime capability
  context for handlers.
- Added `app/assembly/runtime.py` as the first full runtime assembly plan. It
  separates module-local factories, app-level integration factories and
  activation tasks, and the TEST target now builds executable Tool services,
  Orchestration scheduler/executor services, Session runtime control and Memory
  ports from the same plan.
- Split Tool assembly into core catalog/runtime-registry factories and an
  executable Tool service graph factory. Full runtime assembly now wires Tool
  execution with Daemon runtime readiness and Artifact persistence instead of
  using the lightweight module-local queue graph.
- 2026-05-18 update: Tool service graph construction remains an internal
  composer only. Runtime assembly now exposes explicit Tool surfaces through
  `tool.queue_services`, `tool.orchestration_queue_services` and
  `tool.execution_services`; `tool.service_graph` is no longer an `AppKey`, a
  factory key, or a container dependency.
- 2026-05-18 update: Daemon service spec bootstrap is target-scoped to
  `api`, `cli-admin`, `daemon-supervisor` and `test`. Worker containers no
  longer rewrite daemon specs as a side effect of starting.
- 2026-05-18 update: Agent profile bootstrap is target-scoped to
  `api`, `cli-admin`, `daemon-supervisor` and `test`. Worker containers read
  Agent profiles but no longer sync configured profiles or write Agent home
  files while starting.
- 2026-05-18 update: `orchestration.runtime` is no longer an `AppKey` or
  provided registry value. API/admin runtime assembly still builds the internal
  runtime composer, but only publishes named query/inspection/approval/
  cancellation/intake/submission/maintenance/executor-control surfaces. The
  worker-only `orchestration.scheduler_service` and
  `orchestration.executor_service` keys are no longer exposed by API/admin
  targets; the `test` target keeps a dedicated `orchestration.test_runtime`
  factory for integration-style unit tests.
- Tool package activation now derives dependency bindings from the final
  assembled registry, so package handlers receive Access, Artifact, Browser,
  Mobile, Memory, Process, Session and Skill ports when those applications are
  present in the selected target.
- Added Channel runtime services, Operations stores/projection materializer and
  scheduler/tool/event-relay/operations event runtime sidecars to app assembly.
  `runtime_plan()` now builds the event-driven runtime surface that worker
  entrypoints need without relying on the removed bootstrap event runtime module.
- Moved the first batch of background process entrypoints to the new app
  assembly runtime container: Tool worker, Tool scheduler, Event relay worker
  and Operations observer now use `interfaces.runtime_container` with explicit
  `AssemblyTarget` values.
- Moved Orchestration worker CLI to the same runtime container helper. Its
  executor/scheduler/query access now uses `AppKey` lookups from the assembled
  runtime registry, and the Tool IO benchmark scheduler loop is bounded by the
  benchmark run count instead of depending on an indefinite scheduler loop
  shutdown.
- Moved Channel runtime CLI to `AssemblyTarget.CHANNEL_RUNTIME`. Channel profile
  commands now read through `CHANNEL_INFRASTRUCTURE`, and lark/web/webhook
  runtimes are retrieved from explicit `AppKey` registrations instead of the old
  bootstrap container.
- Moved top-level `ask/chat` CLI commands to `AssemblyTarget.CLI_ADMIN` with
  explicit registry lookups for Agent, Daemon, Events and Orchestration ports.
  `serve` now delegates lifecycle to the HTTP API app, which builds
  `AssemblyTarget.API` directly.
- Moved Daemon CLI/supervisor commands to `AssemblyTarget.DAEMON_SUPERVISOR`.
  Daemon, Process and Channel control are now read by explicit `AppKey`
  lookups, and managed daemon spec sync now runs through the Channel control
  application instead of an implicit `daemon_spec_syncers` container field.
- Moved HTTP API construction to `AssemblyTarget.API`. `create_app()` now builds
  through `interfaces.runtime_container`, HTTP routes and guards use explicit
  `AppKey` lookups, and `crxzipple serve` no longer pre-constructs the legacy
  shared CLI container.
- API target now runs Tool package activation so `/tools/*` surfaces see the
  same catalog/readiness semantics as workers, without starting worker loops.
- Runtime daemon service specs are registered as an app assembly activation
  after Browser and runtime defaults exist. Daemon module-local service
  construction stays independent, while browser/tool/orchestration worker specs
  are contributed by the app assembly layer.
- Session assembly now composes the Agent-owned home lookup into Session through
  a workspace defaults callback, preserving runtime binding behavior without
  adding an Agent dependency to Session internals.
- Moved shared module admin CLI commands to `AssemblyTarget.CLI_ADMIN`.
  `interfaces/cli/context.py` now builds the runtime container, and Access,
  Agent, Authorization, Browser, Dispatch, LLM, Memory, Mobile, OCR,
  Orchestration, Process, Session, Skills and Tool CLI modules read services by
  explicit `AppKey` lookups instead of old container attributes.
- CLI_ADMIN now runs Tool package activation so admin `tool list/discover/run`
  uses the same built-in tool catalog semantics as API and workers without
  starting worker loops.
- Browser profile HTTP/CLI payload builders now read Browser infrastructure,
  settings and stores from explicit runtime keys.
- Operations module overview read models no longer consume a container-shaped
  Access inventory facade. Access overview now builds inventory from explicit
  Settings + Access ports inside the operations query set.
- Added production architecture guards covering the app assembly cutover:
  runtime entrypoints/modules cannot import the old bootstrap container, cannot
  call old `build_container()`, and cannot use arbitrary `container.xxx`
  service lookup outside the explicit AppKey runtime surface.
- Test support now has a `target="test"` runtime-container path for migrated
  tests. Access OAuth tests use it, which exposed and fixed the new assembly
  gap where `ACCESS_OAUTH_SERVICE` lacked the Settings action adapter needed to
  persist credential bindings after OAuth completion.
- Additional unit/CLI coverage now uses the `target="test"` runtime container
  for Dispatch, LLM, Agent settings bootstrap, Access/Dispatch/LLM/Tool CLI
  seeding paths, Authorization, selected Daemon/Event runtime checks and
  selected Tool provider cases. Orchestration support and its queue/approval/
  memory/tool/context/executor lease suites now build through the runtime
  container with explicit `AppKey` lookups. Shared Tool test support and the
  catalog/execution/background/provider/workspace/session/image tool suites now
  use the same runtime container path. Channel module/CLI suites and legacy
  architecture guards have also been cut over; unit test helpers no longer call
  the old all-in-one container.

## Problem Statement

The old runtime used a large, manually ordered bootstrap container that created
module-local services, wired cross-module applications, activated tool packages,
registered daemon/runtime contributions and exposed a broad lookup surface.

That path has now been retired. The current runtime builds from
`app/assembly/runtime.py`, with module-local factories, app-level integration
factories and activation tasks resolved by target-specific `AppKey`
dependencies. Remaining work should extend that app assembly shape, not restore
the removed bootstrap container.

## Non-Negotiables

- [x] No compatibility dual path. Retire old `bootstrap.build_container()` usage
      instead of keeping parallel construction paths.
- [x] `src/crxzipple/modules/**` must not import `crxzipple.app`.
- [x] Module application classes must remain ordinary Python classes. Do not
      require lifecycle base classes, decorators, constructor signature scanning,
      or framework-specific method names.
- [x] Application dependencies must be declared by app assembly factories, not
      inferred from constructor signatures.
- [x] Factory `provides` entries must name runtime application surfaces, not
      internal composer objects. `ServiceGraph` classes may help a module wire
      its own use cases, but `AppKey` values and cross-target dependencies must
      stay on named query/control/runtime surfaces.
- [x] Runtime code and tool handlers must not fetch arbitrary services from a
      global container.
- [x] Target containers may differ in loaded capabilities, but the same
      capability must keep the same semantics across targets.
- [x] Unknown dependency, missing dependency and dependency cycle must fail
      during app container build.

## Target Shape

```text
src/crxzipple/modules/
  agent/
  llm/
  access/
  tool/
  orchestration/
  ...

src/crxzipple/app/
  container.py
  registry.py
  plan.py
  assembly/
    settings.py
    access.py
    authorization.py
    agent.py
    llm.py
    memory.py
    session.py
    dispatch.py
    daemon.py
    process.py
    tool.py
    orchestration.py
    channels.py
    operations.py
    runtime.py
```

Responsibility split:

```text
module
  owns its domain and module-local application/usecase classes

app/assembly
  knows how this app combines module applications for a target

container
  is runtime lookup for already-built applications
```

## Assembly Model

The assembly model belongs to `src/crxzipple/app`, not to module application
classes.

- [x] Define `AssemblyTarget`.
- [x] Define `AssemblyPlan`.
- [x] Define `ApplicationFactory` with explicit:
      `key`, `provides`, `requires`, `build`, `targets`.
- [x] Define `ActivationTask` with explicit:
      `key`, `requires`, `run`, `targets`, `idempotent=True`.
- [x] Define `ServiceRegistry` / `ApplicationRegistry` for runtime lookup.
- [x] Implement dependency validation before building integration factories.
- [x] Implement deterministic build order.
- [x] Implement cycle detection with useful diagnostics.
- [x] Support test overrides/fakes without changing module code.

Recommended plan buckets:

- `module_local_factories`: build applications that need only their own module
  repositories, stores, config and adapters.
- `integration_factories`: build cross-module applications/usecases after their
  declared requirements are available.
- `activation_tasks`: run idempotent setup such as settings seed, profile sync,
  tool activation, daemon spec registration and observer subscription
  registration.
- `runtime_host`: the process entry that starts HTTP or worker loops after the
  container is already built.

## Container Targets

Define explicit targets and update every entrypoint to request one.

- [x] `api`
- [x] `daemon-supervisor`
- [x] `orchestration-scheduler`
- [x] `orchestration-executor`
- [x] `tool-scheduler`
- [x] `tool-worker`
- [x] `operations-observer`
- [x] `event-relay-worker`
- [x] `channel-runtime`
- [x] `cli-admin`
- [x] `test`

Target requirements:

- [x] API target must not start or host worker loops.
- [x] API target may activate tool packages needed for API catalog/readiness and
      action handling, but must not start worker loops.
- [x] Worker targets must load only the applications needed by that worker.
      2026-05-15 update: sidecar runtime services are now target-scoped
      (`tool.runtime_event_service`, `event_relay.runtime_event_service`,
      `operations.observer_runtime_event_service`, scheduler runtime service).
      Tool services are split between queue-only targets and executable
      targets, so `tool-scheduler` no longer pulls Orchestration runtime or
      `session_runtime_control`. `daemon-supervisor` no longer pulls Tool or
      Orchestration runtime.
      2026-05-16 update: Orchestration exposes executor lease state through the
      read-only `orchestration.run_query_service`, and Operations observer now
      uses that query surface instead of `orchestration.executor_service`.
      Channel runtime services were also removed from the Operations observer
      target, so the observer no longer pulls scheduler/executor through channel
      runtime construction.
      Later 2026-05-16 update: Tool worker now receives a narrow
      `SessionRuntimeControlPort` backed by Orchestration ingress/intake/query
      operations, not the full Orchestration runtime. Channel runtime now uses a
      narrow `orchestration.submission_service` that only appends inbound turns
      to ingress; scheduler workers still own request processing. Tool worker,
      Channel runtime, Event relay and Operations observer no longer load
      Orchestration scheduler/executor services.
      2026-05-18 update: API/admin entrypoints also no longer receive
      `orchestration.scheduler_service` or `orchestration.executor_service`.
      They use `orchestration.submission_service`,
      `orchestration.scheduler_maintenance_service` and
      `orchestration.executor_control_service`; a static architecture guard
      prevents HTTP/admin/Operations entrypoints from taking the worker keys
      back.
- [x] Operations observer target must load event observation and projection
      dependencies, not full UI-only surfaces.
- [x] Event relay worker target must load event relay subscriptions and
      workbench/channel relay dependencies, not full operations projections.
- [x] Tool worker target must load executable tool capabilities; API may load
      catalog/readiness/action surfaces without hosting workers.
- [x] Test target must allow narrow module loading and explicit fake ports.
      Covered by registry override tests and runtime target build tests.

## Module-Local Applications

Move construction of these module-local applications out of the old container
and into corresponding `app/assembly/<module>.py` files.

- [x] Settings: resource, version, override, effective resolution, query/action.
- [x] Access: credential binding, OAuth provider/account/token, readiness,
      setup session and audit.
- [x] Authorization: policy management, ABAC evaluate and temporary grants.
- [x] Agent: profile management, home files, enable/disable/delete.
- [x] LLM: profile management, invocation record keeping and adapter registry.
- [x] Tool: catalog, run record, queue, scheduler/worker state and discovery.
- [x] Session: session lifecycle, messages and active session resolution.
- [x] Dispatch: task creation, queueing, claim, lease and recovery.
- [x] Daemon: service spec, instance and lease management.
- [x] Process: process session start/stop/output.
- [x] Memory: memory files, binding, indexing and search.
- [x] Skills: catalog, installation, read/inspection and enablement wrapper.
- [x] Artifacts: storage, preview and artifact metadata.
- [x] Browser / Mobile / OCR: profile/config, execution coordinator and result
      serialization.
- [x] Channels: profile/config stores, interaction registry, runtime registry,
      profile service and runtime planner/manager.

## Integration Applications

Construct these in `app/assembly`, because they require more than one module.

- [x] LLM invocation with Access credential provider.
- [x] Agent effective resolution using Agent + LLM + Tool + Access +
      Authorization query ports.
- [x] Tool execution using Tool + Access + Artifact + Browser + Mobile +
      Process + Session capability providers.
- [x] Orchestration runtime using Orchestration + Agent + LLM + Tool + Memory +
      Session + Authorization + Dispatch.
- [x] Session runtime control using Session + Orchestration query/submission/
      cancellation ports.
- [x] Channel runtime using Channels + Agent + Orchestration + Access + Events +
      Artifacts.
- [x] Channel daemon control using Channels + Daemon service spec registration.
- [x] Operations read model using Operations + module query/read ports.
- [x] Daemon manager using Daemon + Process.

Acceptance requirements:

- [x] Cross-module wiring appears in `src/crxzipple/app/assembly/**`, not in
      module application constructors.
- [x] Integration factories declare exactly which ports/applications they need.
- [x] Integration factories do not write business rules that belong to modules.
      `orchestration.submission_service` now constructs the orchestration-owned
      ingress submission application, and `session.ingress_runtime_control`
      delegates Session tool runtime semantics to orchestration application
      helpers. The app assembly side only wires ports for the selected target.

## Tool Capability System

Tool dynamic dependencies must be handled by a capability boundary, not by
passing the container to tool handlers.

- [x] Define `ToolCapabilityCatalog` as the maximum set of capabilities tools
      may request.
- [x] Ensure each tool package can only declare capabilities present in the
      catalog.
- [x] Parse concrete tool requirements from `tools/*/tool.yaml` or equivalent
      package metadata.
- [x] Define `ToolCapabilityBindings` in app assembly per target.
- [x] Support at least these capability classes where applicable:
      credential read, access readiness, artifact read/write, browser control,
      mobile control, process spawn, workspace read/write, memory read, session
      workspace lookup and bounded network access.
- [x] Tool package activation validates unknown capability, missing binding,
      missing credential and missing runtime readiness.
- [x] Tool handlers receive a cropped execution context based on declared
      requirements.
- [x] Tool handlers cannot fetch arbitrary applications from container/registry.
- [x] Tool packages and handlers must not depend back on orchestration. Session
      runtime behavior is exposed through `session_runtime_control`, and the
      Orchestration-backed adapter lives in app assembly.
- [x] Required run context must be copied into `ToolRun` metadata at submission
      time.
- [x] Remove tool second-pass registration. Service compatibility injection has
      been removed from package apply context; scanned package plans are applied
      once by the named app assembly activation task.

## Entrypoint Cutover

Replace old container construction at all process boundaries.

- [x] HTTP `serve` uses `build_app_container(target="api")` via `create_app()`.
- [x] Daemon supervisor uses `target="daemon-supervisor"`.
- [x] Orchestration scheduler uses `target="orchestration-scheduler"`.
- [x] Orchestration executor uses `target="orchestration-executor"`.
- [x] Tool scheduler uses `target="tool-scheduler"`.
- [x] Tool worker uses `target="tool-worker"`.
- [x] Operations observer uses `target="operations-observer"`.
- [x] Event relay uses `target="event-relay-worker"`.
- [x] Channel runtime uses `target="channel-runtime"`.
- [x] Admin CLI commands use `target="cli-admin"` or a narrower explicit
      target. Top-level `ask/chat`, shared CLI context and module admin commands
      now use explicit runtime containers.
- [x] Tests use `target="test"` with explicit overrides/fakes.
      Shared SQLite support now exposes only `build_runtime_container()` for
      assembled app containers. Access OAuth, Dispatch, LLM, Authorization,
      CLI seed paths, Daemon/Event runtime checks, Orchestration suites, Tool
      suites and Channel suites now run against the new runtime container.

## Old Path Removal

- [x] Remove the old all-in-one construction logic from
      `src/crxzipple/bootstrap/container.py`.
- [x] Remove migrated assembly functions from
      `src/crxzipple/bootstrap/application_runtime.py`.
- [x] Remove migrated runtime assembly functions from
      `src/crxzipple/bootstrap/runtime_infrastructure.py`.
- [x] Remove migrated event/app assembly functions from
      `src/crxzipple/bootstrap/event_runtime.py`.
- [x] Remove old import facade for `build_container`.
- [x] Replace every `from crxzipple.bootstrap import build_container`.
- [x] Replace test helpers that call the old container.
- [x] Delete compatibility aliases after all call sites are cut over.

## Validation Gates

Static checks:

```bash
rg -n "from crxzipple.app" src/crxzipple/modules || true
rg -n "from crxzipple.bootstrap import|build_container\\(" src/crxzipple/app src/crxzipple/interfaces src/crxzipple/modules || true
rg -n "container\\.(?!require|get|has|close|snapshot|target|registry)" --pcre2 src/crxzipple/interfaces src/crxzipple/modules || true
PYTHONPATH=src pytest -q tests/unit/test_app_assembly_architecture.py
```

Expected result:

- no module imports `crxzipple.app`;
- no production entrypoint/module imports the old bootstrap container or calls
  old `build_container`;
- no production runtime code fetches arbitrary services through
  `container.xxx`; only explicit `AppKey` lookup helpers remain;
- no module application or tool handler reaches into a global container;
- no new bootstrap facade path is introduced.
- no runtime target exposes `tool.service_graph` or
  `orchestration.service_graph` as an `AppKey` application.

Runtime checks:

- [x] `build_app_container(target="api")` succeeds and serves HTTP.
- [x] `build_app_container(target="daemon-supervisor")` can reconcile daemon
      specs.
- [x] `build_app_container(target="orchestration-executor")` processes runs.
- [x] `build_app_container(target="tool-worker")` executes tools.
- [x] `build_app_container(target="operations-observer")` consumes events and
      writes projections.
- [x] `build_app_container(target="test")` can build narrow containers with
      fakes and a dedicated integration test runtime when tests need scheduler
      and executor worker services together.

Behavior checks:

- [x] OpenAI image tool readiness and execution pass through Access credential
      binding.
- [x] OpenAI image local handlers now call the narrow `CredentialProvider` port
      with `CredentialBindingRef`/`AccessConsumerRef`; handler code no longer
      passes AccessService-only `workspace_dir`, `allow_literal`, or credential
      `trace_context` parameters.
- [x] Tool access readiness no longer derives credential readiness from a run
      workspace. Workspace context remains available to runtime readiness and
      workspace/file tools, but Access credential bindings must resolve from
      Access-owned binding truth.
- [x] Browser tools only receive browser/artifact capabilities when declared.
- [x] Workspace tools cannot access undeclared system capabilities.
- [x] Orchestration tool calls pass run/session/workspace context through
      `ToolRun` metadata instead of reverse-querying orchestration.
- [x] Operations pages continue to read `/operations/{module}` projections for
      the covered module overview/read-model paths.
- [x] API and worker targets resolve the same agent/LLM/tool semantics for the
      HTTP/tool/session paths covered by current tests.

Test suites:

- [x] Access HTTP tests.
- [x] Authorization HTTP tests.
- [x] Agent unit, HTTP and settings integration tests.
- [x] LLM HTTP tests.
- [x] Tool HTTP tests.
- [x] Orchestration unit, HTTP, CLI, approval, context and tool integration
      tests.
- [x] Operations read model/projection tests.
- [x] Channel runtime and HTTP tests.
- [x] CLI entrypoint tests for Access, Agent, Authorization, Browser, Dispatch,
      LLM, Memory, Mobile, OCR, Process, Session, Skills, Tool and hidden
      runtime help.
- [x] Frontend typecheck/build after API contract changes.
      `npm run typecheck` and `npm run build` pass. `npm run
      audit:operations-layout` still requires a running preview/dev server on
      `127.0.0.1:4174`; without it Playwright returns connection refused.

## Documentation Updates

- [x] Update `docs/agents/hosted-agent-operating-contract.md` with the new app
      assembly boundary.
- [x] Update `README.md` runtime section to describe target containers.
- [x] Update tool development docs with capability catalog and requirements.
- [x] Update operations data truth docs if projection construction moves.
- [x] Archive or mark obsolete any old lifecycle/tool loading plans that conflict
      with this checklist.

## Review Focus

Reviewers should reject changes that:

- keep the old and new container paths alive together;
- move cross-module wiring into module application constructors;
- make module classes inherit app assembly framework classes;
- introduce constructor-signature injection;
- let tool handlers access container or arbitrary registry values;
- solve cycles with lazy lookup instead of changing the boundary;
- make API and worker targets behave differently for the same capability.

## Post-Cutover Follow-Ups

These are architecture polish tasks after the target-container cutover. They are
not compatibility shims and should be implemented by moving ownership to the
right module/application boundary.

- [x] Continue with
      `docs/reports/port-usecase-boundary-remediation-checklist-20260516.md`.
      The Session tools control issue and the tool-worker-local ingress/intake
      chain are one root boundary problem: Session tool semantics need a clear
      use case owner and narrow ports instead of app assembly adapters.
      Follow-up checklist is complete as of 2026-05-21.
