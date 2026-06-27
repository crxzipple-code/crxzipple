# Module Audit Summary

Date: 2026-06-26

Scope: current CRXZipple runtime codebase after the latest code-quality
remediation wave. This report summarizes module cleanliness, coupling, lifecycle
ownership, persistence posture, and remaining launch risks. Detailed per-module
evidence remains in the sibling `module-*.md` reports.

## Executive Verdict

The runtime architecture is now substantially cleaner than the initial audit
baseline. The major direction is correct:

- owner modules keep facts
- Context Workspace controls LLM context selection/render snapshots
- Orchestration coordinates runtime progress without owning Tool/LLM/Session facts
- Operations is the sidecar projection/read-model surface
- Workbench is the user-facing projection, not a truth source
- provider/transport adapters translate between runtime contracts and external APIs

The current tree is acceptable for local single-user and controlled pilot use once
the targeted regression suite is green. It is not yet a broad multi-user production
posture. Remaining risk is concentrated in long-chain runtime invariants,
provider/runtime adapters, projection query budgets, production persistence gates,
and high-power Browser/Tool surfaces.

## Current Scale Snapshot

| Module | Python files | Approx lines | Risk |
| --- | ---: | ---: | --- |
| operations | 499 | 53212 | High projection/read-model risk |
| browser | 126 | 34191 | High live-runtime risk |
| orchestration | 140 | 31602 | High lifecycle/race risk |
| tool | 207 | 29598 | High external-runtime risk |
| llm | 110 | 18838 | Medium-high provider parity risk |
| access | 73 | 14029 | Medium credential/OAuth risk |
| skills | 74 | 11925 | Medium provenance/package risk |
| context_workspace | 57 | 9446 | Medium context-control risk |
| settings | 84 | 9600 | Medium governance risk |
| channels | 43 | 9150 | Medium transport/runtime risk |
| workbench | 68 | 7967 | Medium projection/pagination risk |
| memory | 37 | 6517 | Medium index/retrieval risk |
| agent | 57 | 5704 | Low-medium profile/home risk |
| session | 34 | 5151 | Medium replay/window risk |
| events | 28 | 4627 | Low-medium backend-mode risk |
| mobile | 28 | 4266 | Low-medium device isolation risk |
| authorization | 41 | 3807 | Low-medium security lifecycle risk |
| daemon | 17 | 3324 | Low supervisor risk |
| dispatch | 21 | 2507 | Low-medium lease/idempotency risk |
| ocr | 18 | 1481 | Low adapter risk |
| process | 15 | 1324 | Low process-output risk |
| artifacts | 11 | 937 | Low filesystem lifecycle risk |
| event_relay | 8 | 698 | Low retained bridge risk |

## Cross-Module Boundaries

### Owner Fact Modules

These modules should preserve complete domain truth and expose application/query
services. They must not carry UI/model/trace visibility policy.

| Module | Owns | Current Assessment |
| --- | --- | --- |
| session | session instances, segments, turns, items, replay windows | Boundary improved; replay/read windows and compaction are split, but long-session query budget remains important. |
| tool | catalog, source packages, tool runs, assignments, workers, runtime execution results | Much cleaner after worker/source/submission/settings/package-access/provider-backend/result-artifact/ToolSurface/domain/service-support/HTTP/OpenAPI/MCP/package-activation boundary splits; OpenAPI discovery now separates provider entry, models, parser, schema, security, and access projection; shared MCP stdio message/error projection is split, while live stdio lifecycle edge cases and worker backpressure remain high-risk. |
| llm | provider profiles, invocation facts, response items, provider adapters | Good provider-boundary direction; remaining work is adapter parity/golden coverage and large provider surfaces. |
| agent | agent profiles, home/workspace config, runtime preferences | Clean and compact; main risk is hidden home-file input, already controlled through Context Workspace selection. |
| access | credentials, OAuth accounts, readiness | Well split; keep no-raw-secret and OAuth lifecycle coverage as security guardrails. |
| authorization | ABAC policy, effects, grants, audit | Clean low-medium risk; security-critical state-machine tests must remain mandatory. |
| settings | Settings-owned config, versions, overrides, action audit | Better after HTTP/action/domain/persistence/read-model splits; must not become owner of other modules' facts. |
| skills | skill packages, sources, authoring state | Cleaner after package/authoring/HTTP/CLI splits; trusted-source and provenance policy are the next real risks. |
| memory | memory stores, indexes, retrieval runtime | Mostly clean; query/index budget and production SQLite fallback rules need continued guardrails. |
| browser | profiles, pools, allocations, CDP/Playwright runtime, traces | High-power module; recent allocator/action-engine splits helped, but live process/CDP/storage access remains a launch-sensitive area. |
| mobile | devices, leases, ADB-backed actions/snapshots | Compact after engine/action/control splits; enforce device isolation and bounded diagnostics. |
| artifacts | artifact refs and filesystem-backed payloads | Low risk, but filesystem cleanup and ref ownership must stay explicit. |

### Control And Coordination Modules

| Module | Role | Current Assessment |
| --- | --- | --- |
| orchestration | runtime coordinator over LLM, Session, Tool, Context Workspace | Moving in the right direction. Remaining risk is long-chain performance, wait/recovery breadth, and race invariants. |
| context_workspace | context control plane, tree/slice/render snapshot owner | Good target boundary. Keep tree as control plane, not duplicate data truth. |
| dispatch | generic queue/claim/lease/terminal state | Smaller and guarded; production Redis/Postgres mode must remain explicit. |
| daemon | long-running service supervision | Structurally modest; continue smoke/concurrency coverage for managed workers. |
| events | event backend contracts, topics, cursors | Should stay neutral infrastructure; production must use Redis rather than silent in-memory fallback. |

### Projection And Interface Modules

| Module | Role | Current Assessment |
| --- | --- | --- |
| operations | sidecar observer and durable read models | Architecturally correct but still the largest area. Risk is query budget, fallback policy, and oversized page helpers. |
| workbench | user-facing runtime projection | Cleaner after projector/route splits; remaining risks are long-session pagination and debug/fallback leakage. |
| event_relay | retained Workbench bridge | Acceptable as narrow bridge; do not grow it into a second event/projection owner. |
| channels | external message ingress/egress runtime | Better split; runtime transport and delivery semantics need continued backpressure/error coverage. |
| process | process session/output capability | Low risk if output bounds and stale-session cleanup remain enforced. |
| ocr | OCR adapter capability | Low risk; keep result-size budgets and adapter error projection bounded. |

## Current Remediation State

### Recently Stabilized

- Core config is now a thin public entrypoint with focused config modules for
  agent, browser, channel, LLM, mobile, tool, events, memory, authorization,
  sandbox, paths, logging, and runtime budgets.
- Context Workspace session integration has been split into reader, execution
  facts, segment ranges, item nodes, and segment helpers.
- Tool app assembly moved service-graph adapter logic out of the main assembly
  file.
- Tool app assembly now also moves runtime infrastructure construction out of the
  main assembly file.
- Tool package access now separates OpenAPI provider manifest parsing from local
  package credential requirement parsing behind a small export surface.
- Tool package credential parsing now separates requirement-set assembly,
  credential declaration parsing, and forbidden direct-source policy.
- Tool package OpenAPI provider manifest parsing now separates provider manifest
  field loading from OpenAPI credential binding validation and legacy source
  rejection.
- Tool daemon runtime readiness adapter now separates daemon metadata/status
  projection and Browser proxy credential readiness projection from requirement
  evaluation flow.
- Tool runtime SQLAlchemy persistence now separates ToolRun, ToolRunAssignment,
  and ToolWorker repositories instead of mixing three lifecycle fact mappings in
  one persistence file.
- Tool function SQLAlchemy persistence now separates ToolFunction facts from the
  ToolFunctionCatalog record adapter instead of keeping both in one repository
  file.
- Tool package discovery/apply now separates the public export surface, namespace
  compatibility model, manifest loader, activation resolution/validation, and
  registry apply policy.
- Tool package activation now separates entrypoint import/validation and typed
  local handler dependency injection from activation registration.
- Tool package manifest parsing now separates generic YAML value parsers from
  package manifest dependency/capability/runtime-request semantics.
- Tool package catalog projection now separates the public discovery adapter,
  source record/config projection, function/provider-backend candidate projection,
  and stable payload helpers.
- Tool worker in-flight assignment launch/reap, assigned-run failover, in-flight
  heartbeat, and runnable-run selection now live outside the worker service facade.
- Tool worker in-flight launch now defensively ignores duplicate/already-running
  run ids and never starts more tasks than the caller's available slot budget.
- Tool worker in-flight reap now treats cancelled child tasks as cleanup-complete
  entries instead of letting child cancellation abort worker shutdown cleanup.
- Tool worker registration/admin operations and cancel/recovered-dispatch control
  now live outside the worker service facade.
- Tool worker now delegates run persistence and heartbeat persistence to focused
  helpers.
- Tool provider backend logic now separates DTOs/constants, policy parsing,
  backend resolution, readiness aggregation, and execution-context payload projection.
- Tool result artifact handling now separates result externalization orchestration from
  artifact writes and artifact envelope merge policy.
- ToolSurface query construction now separates persisted/public DTOs from
  source/function/group projection policy.
- Tool submission now separates public batch orchestration from request preparation,
  ToolRun construction, dispatch enqueue, and execution context/id helpers.
- Tool Settings bootstrap now separates provider/root scanning from config
  lookup/coercion, OpenAPI credential binding validation, and provider settings
  projection.
- Tool MCP client now separates the builder/export surface, stdio facade,
  stdio sync lifecycle, stdio async lifecycle, HTTP transport, and JSON-RPC
  protocol payload/response validation.
- Tool MCP stdio sessions now share message encoding, response id validation,
  timeout/EOF/send error projection, and session-unavailable text through a
  focused helper instead of duplicating those semantics in sync and async
  process lifecycle classes.
- Tool MCP async stdio loop startup/shutdown now lives in a focused loop helper,
  leaving the async session to own request serialization, process lifecycle, and
  protocol IO.
- Tool MCP stdio process start/close and start-failure projection now live in a
  focused process helper shared by sync and async sessions.
- Tool MCP client lifecycle coverage now verifies HTTP session-header propagation
  without local socket binds, plus sync timeout cleanup and async EOF cleanup for
  stdio sessions.
- Tool MCP adapter diagnostics now redact HTTP transport exceptions, JSON-RPC
  error messages, stdio stderr details, and stdio command startup failures before
  surfacing `ToolValidationError`; URL query and fragment token parameters share
  the same projection.
- Tool CLI source credential-bearing process output now stays raw in Process owner
  storage but is redacted in the ToolRun result details and provider replay payload
  returned by `cli_execute` / `cli_read_output`.
- Tool runtime-domain aggregates now separate ToolRun, ToolRunAssignment, and
  ToolWorkerRegistration lifecycle code behind a thin runtime export surface.
- Tool catalog function models now separate candidate normalization, catalog record
  lifecycle, and schema-hash construction behind a thin export surface.
- Tool CLI source config now separates command/path policy, credential binding
  parsing, and promoted function argument rendering.
- Tool CLI source discovery now separates candidate/spec assembly from guided
  action contract/policy and Access credential requirement projection.
- Tool CLI source runtime now separates guided runtime action routing from
  one-shot help subprocess execution and process-output display redaction.
- Tool application service support now separates service contracts,
  ToolFunction-to-Tool projection, credential requirement payload restoration, and
  attachment decoding; duplicate credential payload parsing was retired.
- Tool configured provider catalog now separates discovery/activation flow from
  provider source/config projection and OpenAPI/MCP metadata conversion.
- Tool OpenAPI discovery now separates the provider entrypoint from operation
  models, document parsing, schema projection, security parsing, and Access
  credential requirement projection.
- Tool OpenAPI remote runtime now separates HTTP invocation from request parameter
  construction, security/credential projection, request URL redaction, and
  response text/details projection.
- Tool provider OpenAPI remote execution coverage no longer requires binding a
  local sample server; the unit scope now patches the async HTTP transport while
  preserving source discovery, Access credential resolution, transport, and
  redaction assertions.
- Browser profile allocation now separates lifecycle from selection strategy and
  target lifecycle projection.
- Browser storage action results now project local/session storage values through
  the same storage redaction path used by cookies, IndexedDB, and CacheStorage,
  so sensitive browser state remains writable in the live page but is not echoed
  back into runtime/LLM/UI payloads; partial CDP storage errors are also
  projected through display-safe error messages before returning action results.
- Browser network inspection now shares a display-safe exception projector with
  CDP session errors, so page-performance and CDP partial failures stay
  actionable without leaking raw URL query strings or bearer/token values.
- Browser diagnostics and CDP network-capture controller errors now use the same
  display-safe projection for performance/lifecycle metrics, subscription setup,
  and response-body fallback failures.
- Browser action-trace partial errors now use the same display-safe projection
  for storage/lifecycle snapshots, network capture coordination, stabilize
  waits, and action failures.
- Browser network-list performance fallback errors now use the same display-safe
  projection before entering tool/action results.
- Browser script-insight source-read errors now use the same display-safe
  projection before entering tool/action results.
- Browser profile-probe diagnostics errors now use the same display-safe
  projection before entering profile readiness payloads.
- Browser DevTools adapter errors now delegate to the shared display-safe
  projection instead of maintaining a second redaction implementation.
- Browser profile proxy egress test failures now redact result reason and URL
  before returning profile readiness diagnostics.
- Mobile infrastructure now separates control engine, snapshot actions,
  interaction actions, and target resolution.
- Settings read models now separate overview, common section helpers, and audit
  pages.
- Settings action-audit persistence now redacts request metadata, trace context,
  and terminal result/error JSON before storage while preserving safe Access/
  Settings refs and token-count metrics.
- Settings persistence redaction is now a shared persistence helper instead of a
  private SQL record mapper function reused by domain repositories.
- Settings domain aggregate mapping is split by resource/version/override/
  snapshot/action-audit family; the former mixed domain repository mapper has
  been retired rather than kept as a compatibility surface.
- Settings SQL persistence mapping is now split by resource/version/snapshot/
  override/validation/action-audit family, with common timestamp/text value
  coercion isolated in a shared helper and no mixed SQL mapper compatibility
  surface retained.
- Settings record-level SQL persistence now separates governance resource/version/
  snapshot/override/validation transactions from action-audit lifecycle, and the
  former mixed SQL repository file is retired rather than kept as a compatibility
  layer.
- Skills HTTP DTOs are now split by package/skill/readiness, governed draft, and
  source/install/sync concerns; `interfaces/http_models.py` remains only the narrow
  public export surface for the route module.
- Skills HTTP routes are now split by package/skill/readiness, governed draft, and
  source/install/sync concerns; `interfaces/http.py` remains only the small
  composition entrypoint.
- Skills CLI source, draft query, draft authoring, draft lifecycle, top-level query,
  and top-level mutation commands are now split from composition entrypoints;
  `interfaces/cli.py` and `interfaces/cli_draft_commands.py` remain small
  composition surfaces.
- Skills authoring service now delegates current owner package/instruction/support-file
  reads and draft-to-owner package writes to `authoring_owner_state.py`, leaving
  draft lifecycle coordination in the service.
- Skills filesystem repository now delegates writable-package guards, create/update
  manifest construction, instruction body restoration, and legacy manifest
  materialization to `package_mutations.py`; the repository remains the public
  filesystem entrypoint.
- Skills owner state now delegates source/package snapshot persistence,
  removed-package reconciliation, and removed readiness events to
  `owner_catalog_snapshot.py`.
- Skills package service now keeps package use-case coordination while package
  event payloads, install/read/validate observation, and installation record writes
  live in `package_observation.py`; repeated source sync and successful mutation
  record calls are consolidated behind private service helpers.
- Skills source service now keeps source lifecycle coordination while source list
  DTO projection, source event/install-record observation, and source validation
  rules live in focused helpers.
- Skills manager service graph construction now lives in `manager_services.py`;
  `SkillManager` remains the public facade and typed delegation surface.
- Skills SQL persistence mapping is now split by catalog/package/readiness,
  governed draft/audit, and shared payload restoration families; the former mixed
  `repository_mappers.py` file is retired rather than kept as a compatibility
  surface.
- Operations observation persistence and projection persistence redaction have
  stronger no-raw-secret behavior while preserving structured metric/chart
  sections such as token usage and credential health.
- Operations and Workbench page-builder contracts now have executable checks for
  projection table query budgets, projection freshness, and Workbench optional
  owner-query diagnostics.
- Operations/Workbench frontend pages now have an architecture guard preventing
  direct owner API prefixes; runtime UI truth stays on `/operations/*` and
  `/ui/workbench/*` surfaces.
- LLM provider outbound request golden fixtures and inbound response-item golden
  fixtures now cover primary adapters: Codex, OpenAI Responses, OpenAI
  Chat-compatible, Anthropic, and Gemini.
- Production runtime persistence guard now rejects unsafe SQLite/file-events/local
  memory-index fallback unless explicitly acknowledged, and long-running CLI
  entrypoints are covered by an architecture guard.

### Still Not Complete

This refactor wave is commit-ready, but the overall code-quality program is not
finished. Remaining work is not broad "split files until small"; it is focused
on correctness and production readiness:

- Orchestration long-chain invariants: tool wait/recovery, approval, late tool
  result, compaction, resume, and terminal materialization must stay executable.
- Operations/Workbench scale budgets: current query-budget/freshness contracts
  are guarded, but large sessions and high-volume projections still need deeper
  load coverage, pagination pressure tests, and fallback discipline.
- Browser/Tool provider adapters: live CDP/Playwright/OpenAPI/MCP behavior needs
  timeout, cleanup, retention, sandbox rules, and socket-capable integration
  coverage outside this restricted harness.
- LLM provider parity: primary render and response-item golden coverage is in
  place; remaining risk is live provider drift, streaming edge cases, and fixture
  maintenance.
- Production persistence gates: Redis/Postgres are now guarded for shared runtime
  entrypoints, and file/in-memory/SQLite fallbacks require explicit
  acknowledgement where unsafe.
- Security review: Access, Authorization, Browser, Tool, Skills, and Settings
  still deserve a separate security-focused pass.

### Validation Pass 2026-06-27

Local executable readiness checks passed in the restricted harness:

- Orchestration/runtime invariant slice:
  `PYTHONPATH=src pytest -q tests/unit/test_orchestration_execution_chain.py tests/unit/test_orchestration_approval.py tests/unit/test_orchestration_tools.py tests/unit/test_orchestration_compaction_segment_rotation.py tests/unit/test_orchestration_queue.py tests/unit/test_orchestration_loop_regression_baseline.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_runtime_llm_request.py tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_turn_submission_runtime_request_bootstrap.py --tb=short --maxfail=1`
  passed once with 206 tests in 289.34 seconds, then passed three repeated
  long-chain runs with 206 tests each in 284.87 seconds, 269.26 seconds, and
  288.16 seconds.
- Browser/Tool adapter cleanup and runtime-boundary slice:
  `PYTHONPATH=src pytest -q tests/unit/test_browser_cdp_sessions.py tests/unit/test_browser_network_capture.py tests/unit/test_browser_playwright_actions.py tests/unit/test_browser_playwright_runtime_actions.py tests/unit/test_browser_devtools_adapter.py tests/unit/test_browser_profile_probe.py tests/unit/test_tool_mcp_client.py tests/unit/test_tool_source_service.py tests/unit/test_tool_runtime_readiness.py tests/unit/test_tool_worker_inflight.py --tb=short --maxfail=1`
  passed with 118 tests in 43.79 seconds.
- Access/Authorization security-boundary slice:
  `PYTHONPATH=src pytest -q tests/unit/test_access.py tests/unit/test_access_oauth.py tests/unit/test_access_policies.py tests/unit/test_access_governance_contracts.py tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py tests/unit/test_access_tool_integration.py tests/unit/test_openapi_access.py --tb=short --maxfail=1`
  passed with 72 tests in 22.44 seconds.

The Docker/Postgres/Redis and daemon-managed worker smoke is still open in this
harness. `docker info` can see the Docker client and Colima context, but cannot
access `/Users/crxzy/.colima/default/docker.sock` from this process, so the
socket-capable production smoke must be run from a host shell with Docker access.
This validation pass increases confidence in the split boundaries and local
runtime invariants. It satisfies the repeated local long-chain invariant item,
but it does not satisfy real Postgres/Redis/daemon smoke readiness.

## Module-by-Module Assessment

### Operations

Status: improved but still high-risk.

Operations is the correct owner for sidecar observation and durable read models.
Read-model facades and HTTP routes have been heavily split. Operations pages now
declare owner-call/cost metadata, expose projection freshness, and keep projection
table pagination covered by HTTP contract tests. The remaining issue is scale: the
module is large because it projects many owner modules. This is acceptable only if
each page keeps bounded owner queries, freshness metadata, and no fallback that
fabricates truth.

Next actions:

- deepen load coverage for per-page query budgets
- keep projection store reads first
- forbid frontends from bypassing `/operations/{module}`
- continue splitting oversized helper/table surfaces only where responsibilities
  are genuinely mixed

### Orchestration

Status: directionally correct, launch-sensitive.

Orchestration is the coordinator, not the owner of LLM/Tool/Session facts. The
engine, execution chain, worker CLI, maintenance, waiting recovery, and runtime
request draft have been split. Remaining risk is not just file size; it is runtime
correctness across long chains.

Next actions:

- add long-chain invariant tests across LLM response items, tool runs, session
  items, render snapshots, Workbench projection, and Operations projection
- continue shrinking wait/recovery branches after invariants are locked
- keep daemon-managed workers as the normal runtime path

### Tool

Status: much cleaner, still high-risk.

Tool owns catalog/source packages, tool runs, assignments, workers, execution
targets, and result artifacts. Worker and source services have been split into
focused helpers, including run persistence and heartbeat persistence. Service
support now has separate contracts/projection/payload helpers. OpenAPI
discovery/runtime and MCP HTTP/protocol/stdio-message boundaries are now split, with OpenAPI
discovery reduced to a provider entrypoint over focused parser/model/schema/security
helpers. Result artifact handling now keeps the worker entrypoint small while
artifact writes and provider replay envelope merge policy live in focused helpers. The largest
remaining risks are live MCP stdio/runtime lifecycle edge cases and worker backpressure.

Next actions:

- continue adapter-level tests for MCP stdio/local/runtime targets
- keep tool result replay bounded and artifact-backed
- add per-tool execution metrics and worker concurrency assertions

### LLM

Status: medium-high risk.

LLM has a sound direction: neutral runtime request, provider renderers/adapters, and
response-item normalization. The risk is provider drift: each provider/transport can
have different request and response shapes.

Next actions:

- maintain golden request/response fixtures as provider APIs drift
- keep provider adapters symmetric: render outbound, normalize inbound
- prevent debug/context diagnostics from leaking into model-visible input

### Context Workspace

Status: good control-plane direction.

Context Workspace owns Context Tree state, selected slices, render snapshots, and
provider attachment mirror. It should control visibility and selection, while owner
modules retain facts.

Next actions:

- keep tree nodes as references/control state, not duplicate facts
- ensure rendered LLM input is derived from selected slices only
- keep request-render cost reports bounded

### Session

Status: medium risk.

Session should remain the conversation ledger: instances, segments, turns, steps,
items, compaction outputs, and replay windows. It should not decide model/UI
visibility beyond preserving facts and replay protocol.

Next actions:

- keep segment rotation and compaction race tests
- ensure long-session replay remains active-segment bounded unless explicitly
  expanded by Context Workspace

### Browser

Status: high capability, high care.

Browser owns generic browser capability runtime. Recent splits separated allocator
selection, target lifecycle, control-engine helpers, action-engine pieces, trace,
network fetch, storage inspection, and observation helpers. It must never contain
airline/site-specific strategy.

Next actions:

- continue cleanup around live control operations and network inspection
- enforce trace/snapshot retention budgets
- keep raw CDP behind controlled tools and adapters

### Workbench

Status: medium-low risk after projector split.

Workbench is a projection module. It should not become a truth owner. Timeline and
entity-detail projections are cleaner, optional owner-query paths are guarded by
diagnostic tests, but large sessions can still stress query paths and pagination.

Next actions:

- lock long-session pagination
- keep debug/fallback leakage out of primary timeline
- expose source/cost metadata for projection troubleshooting

### Settings

Status: medium risk.

Settings is a governance/config module, not a universal owner. Resource actions,
domain aggregates, materialization, persistence, and page read models have been
split. Action-audit JSON is now redacted before persistence, not only at read-model
projection time. Remaining risk is misclassifying module-owned facts as
Settings-owned and letting Settings grow into a live owner of other modules.

Next actions:

- require owner/truth/write/apply metadata for every resource
- keep env as seed/import only
- quarantine legacy materialization adapters until owner config ports are stable

### Access

Status: medium risk.

Access owns credentials, OAuth flows, accounts, readiness, and sensitive payload
redaction. Splits are good, but the domain is security-sensitive.

Next actions:

- keep no-raw-secret tests mandatory
- harden OAuth failure/retry/revoke flows
- ensure Settings integration never exposes raw credential truth

### Authorization

Status: low-medium risk, security-critical.

Authorization owns ABAC policy, effects, temporary grants, agent-managed grants, and
audit. Structure is clean after service/facade/handler/persistence splits.

Next actions:

- keep grant state-machine tests
- add timestamp expiry semantics if temporary grants become long-lived
- maintain strict no Access imports in application logic

### Agent

Status: low-medium risk.

Agent owns profile/home/runtime preference facts. HTTP/CLI/application/domain/home
config paths are split and reasonably compact.

Next actions:

- keep hidden home-file input out of LLM requests unless Context Workspace selects it
- preserve atomic home writes and per-user home isolation in future deployments

### Skills

Status: medium risk.

Skills owns source packages, authoring state, package metadata, and runtime
visibility. The main remaining question is provenance and trust policy, not basic
file splitting.

Next actions:

- define trusted source rules
- keep path traversal/symlink isolation tests
- decide how dynamic skill discovery becomes provider-visible tool schemas

### Memory

Status: medium risk.

Memory owns indexes and retrieval state. Runtime retrieval and indexing are sizeable
but conceptually clear.

Next actions:

- enforce production SQLite fallback rules
- budget retrieval payloads and index scans
- keep Memory facts separate from Context Workspace visibility decisions

### Channels

Status: medium risk.

Channels owns transport profiles and runtime interactions. Service boundaries are
better, but webhook/runtime delivery remains failure-prone by nature.

Next actions:

- add delivery/backpressure/retry invariants
- keep channel runtime state observable through Operations only

### Mobile

Status: low-medium risk.

Mobile is now relatively clean: control engine, snapshot actions, interaction
actions, and target resolution are split. The biggest risk is device/session
isolation.

Next actions:

- keep bounded ADB output and screenshot artifacts
- enforce lease isolation for concurrent device use

### Events, Dispatch, Daemon

Status: low to medium.

These are infrastructure/control modules. Events should remain a neutral bus;
Dispatch owns queue/lease state; Daemon owns long-running service supervision.

Next actions:

- Redis backend for shared events
- Postgres-backed dispatch where needed
- daemon smoke tests for worker/scheduler/channel/browser services

### Artifacts, OCR, Process, Event Relay

Status: low risk.

These modules are small and scoped. Main risks are cleanup, bounded output, and not
letting bridge modules grow into second truth owners.

Next actions:

- keep artifact retention explicit
- keep process/OCR output bounded
- keep event_relay as a narrow Workbench bridge

## Launch Readiness Checklist

- [x] Long-chain runtime invariant suite passes repeatedly.
- [x] Operations and Workbench page builders have query-budget and freshness tests.
- [x] Provider render/response golden fixtures cover primary LLM adapters.
- [ ] Browser/Tool runtime adapters have cleanup, timeout, and retention tests.
- [x] Production mode rejects silent in-memory/file/SQLite fallback where unsafe.
- [ ] Security pass covers Access, Authorization, Browser, Tool, Skills, Settings.
- [x] Frontend consumes Operations/Workbench projection APIs only, not owner internals.
- [ ] Docker/Postgres/Redis boot and daemon-managed workers pass a clean smoke run.

## Conclusion

The code-quality refactor is materially effective but not globally complete. The
most important architectural boundary is now visible and mostly enforced: facts live
in owner modules, control lives in Context Workspace/Orchestration, and observation
lives in Operations/Workbench. The next phase should avoid broad mechanical
splitting and focus on executable invariants, production persistence gates, and
adapter/runtime hardening.
