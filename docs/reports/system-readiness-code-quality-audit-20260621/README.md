# System Readiness Code Quality Audit

Date: 2026-06-21

This audit is a pre-launch architecture and code-quality review for CRXZipple. It focuses on module cleanliness, coupling, layering, lifecycle ownership, persistence efficiency, scalability, and integration readiness.

This is a static architecture review based on active project constraints, module inventory, code size/coupling scans, and selected source inspection. It is not a substitute for load testing, security review, or full production incident drills.

## Executive Verdict

CRXZipple has a sound target architecture: modular monolith, DDD-style module boundaries, event-driven runtime facts, Operations as sidecar projection, Context Workspace as context control plane, and frontend as a single full-screen console.

However, the system is not yet ready for broad multi-user production without addressing several P1 risks:

- Operations read models and HTTP surfaces are too large and too module-specific.
- Browser, Tool, Orchestration, LLM, Channels, Settings, Skills, and Session still contain large application/interface files that make lifecycle behavior hard to reason about.
- Persistence is mixed across Postgres, Redis, SQLite index, filesystem stores, and in-memory fallbacks; this is acceptable for local runtime, but it needs explicit production-mode constraints.
- Runtime lifecycle has been significantly improved, but long-chain behavior still depends on several recently split orchestration/LLM/session/context/tool seams that need invariant tests.
- Adapter/projector boundaries are improving, but there is still risk of redundant provider/UI/debug projections drifting apart.

Overall launch posture:

- Local single-user / controlled pilot: acceptable after current regression suite passes and Docker/Postgres/Redis boot is stable.
- Team or multi-user deployment: P1 items below should be addressed first.
- External system integration at scale: requires stable public application services, documented event contracts, and backpressure/tenant controls.

## Evidence Snapshot

Module scale from `src/crxzipple/modules`:

| Module | Python files | Approx lines | Coupling signal |
| --- | ---: | ---: | ---: |
| operations | 82 | 42698 | high |
| browser | 118 | 33860 | high |
| orchestration | 140 | 31602 | very high |
| tool | 131 | 27614 | very high |
| llm | 109 | 18519 | very high |
| access | 72 | 13935 | medium |
| skills | 52 | 11185 | medium-high |
| context_workspace | 57 | 9446 | medium-high |
| channels | 43 | 9150 | medium |
| settings | 69 | 9322 | medium |
| workbench | 27 | 7169 | high projection coupling |
| memory | 35 | 6468 | medium |
| session | 34 | 5151 | medium |
| agent | 57 | 5704 | medium |
| events | 28 | 4615 | medium |
| mobile | 24 | 4081 | low-medium |
| daemon | 17 | 3324 | low |
| authorization | 41 | 3807 | low-medium |
| dispatch | 22 | 2656 | medium |
| ocr | 18 | 1481 | low |
| process | 15 | 1324 | low |
| event_relay | 8 | 698 | low retained bridge |
| artifacts | 11 | 666 | low |
| delivery | 0 | 0 | retired placeholder |

Largest hotspots observed in the initial audit baseline:

- `operations/application/read_models/events.py`: 2459 lines
- `operations/application/read_models/daemon.py`: 2439 lines
- `operations/application/read_models/channels.py`: 2312 lines
- `operations/interfaces/http.py`: 2033 lines
- `operations/interfaces/http_models.py`: 1999 lines
- `operations/application/read_models/skills.py`: 1905 lines
- `tool/infrastructure/tool_packages.py`: 1857 lines baseline; now 589 after OpenAPI/access, manifest value, tool declaration, provider backend, and activation helper split
- `orchestration/domain/entities.py`: 1804 lines baseline; now 17-line export surface after execution, run, ingress, executor-lease, and payload-helper split
- `browser/infrastructure/script_insight.py`: 1712 lines baseline; now 668 after runtime expression, payload coercion, and source-analysis helper split
- `browser/infrastructure/action_engine_scripts.py`: 1603 lines baseline; now 59-line export surface after marker/expression-family split
- `browser/infrastructure/action_trace.py`: 1306 lines baseline; now 380-line trace service entrypoint after payload, snapshot, state, network, and envelope/recommendation helper split
- `browser/infrastructure/network_page_fetch.py`: 969 lines baseline; now 173-line service entrypoint after request, page-runtime, analysis, event, and common result helper split
- `browser/infrastructure/engines.py`: 1276 lines baseline; now 413-line control-engine surface after tab operations, tab/runtime-state, CDP IO, host/process lifecycle, and in-memory engine split
- `browser/domain/value_objects.py`: 1254 lines baseline; now 76-line export surface after type/helper/profile/tab/network/command value split
- `browser/application/observation.py`: 1256 lines baseline; now 354-line observation service entrypoint after value/page/runtime/interaction/projection helper split
- `browser/interfaces/cli.py`: 929 lines baseline; now 36-line Typer composition root after command group/helper split
- `browser/interfaces/profile_payloads.py`: 667 lines baseline; now 23-line export surface after diagnostics/entry/aggregate payload split
- `operations/application/read_models/orchestration.py`: 1597 lines baseline; now 574 after status/failure/metric/action/runtime-fact split
- `tool/infrastructure/persistence/repositories.py`: 1553 lines baseline; now 33-line export surface after source/function/provider/surface/runtime repository split
- `tool/domain/entities.py`: 1147 lines baseline; now 61-line export surface after catalog/runtime entity and normalization split
- `tool/application/catalog_models.py`: 943 lines baseline; now 37-line export surface after catalog type/helper/function/source model split
- `tool/application/worker_service.py`: 1713 lines baseline; now 762-line worker coordinator after run-loop, run-resolution, execution, completion, recovery, assignment, wakeup, heartbeat, tracking, artifact, validation, and error helpers were split out
- `tool/interfaces/http.py`: 1106 lines baseline; now 494-line route surface after Pydantic HTTP models and payload projection helpers were split to `http_models.py` and `http_payloads.py`

## Cross-Cutting Findings

### P1. Operations Projection Bulk

Operations is architecturally correct as a sidecar observer/projection layer, but implementation files are too large and too specialized per module. This raises risk for slow Workbench/Operations pages, drift from owner facts, and difficult onboarding for external observability.

Recommendation:

- Split read model builders by query source, materializer, DTO projection, and diagnostics.
- Keep `/operations/{module}` as the API contract, but reduce each module read model to smaller projection units.
- Add projection freshness and cost metrics per owner module.

### P1. Runtime Lifecycle Complexity

Orchestration, Tool, LLM, Session, and Context Workspace now have clearer boundaries, but the lifecycle is still distributed across many recent seams: response item parsing, session item recording, context render snapshots, tool execution records, workbench projections, and operations projections.

Recommendation:

- Define executable lifecycle invariants: one LLM invocation yields response items; tool calls become tool runs; tool results become session items; context render snapshots reference only selected facts; workbench/operations render from owner facts.
- Keep orchestration as coordinator, not owner of LLM/tool/session internals.
- Continue shrinking runner/engine files after each invariant has tests.

### P1. Persistence Mode Clarity

Postgres + Redis is the correct shared runtime baseline. SQLite, filesystem stores, and in-memory repositories are acceptable for tests, local indexes, or explicit fallback, but not as hidden multi-user production behavior.

Recommendation:

- Add a production-mode persistence gate that disables silent in-memory/file fallbacks.
- Document which modules may use filesystem truth: artifacts, skills filesystem packages, memory markdown store, browser/mobile local state.
- Add query-budget tests for projection builders and long-session request rendering.

### P1. Adapter And Projection Redundancy

The system has several translation layers: provider request renderers, session runtime projection, context workspace projection, workbench projection, operations projection, tool package/source adapters. This is necessary, but redundant fallback paths can create confusion.

Recommendation:

- Keep the rule: owner module stores facts; Context Workspace selects context; renderer/provider adapter translates to external protocol; Workbench/Operations are observation projections.
- Remove any fallback that sends uncertain/debug-only conclusions to LLM input.
- Require each projector to declare owner facts it consumes.

### P2. Domain Purity Is Mostly Healthy

Domain packages mostly import their own domain files, not FastAPI/SQLAlchemy/Redis/Playwright. This is a strong foundation.

Recommendation:

- Add a lightweight architecture test that fails if `modules/*/domain` imports infrastructure, FastAPI, SQLAlchemy, Redis, Playwright, or another module domain directly.

### P2. Interface Surfaces Are Too Fat

Several HTTP/CLI files contain too much mapping and decision logic, especially Settings, Operations, Channels, Tool, Browser, Agent, Memory, and Skills.

Recommendation:

- Move heavy DTO assembly into application read/query services.
- Keep interface modules as parse/authorize/call/serialize only.

## Audit Documents

Backlog and execution planning:

- [remediation backlog](remediation-backlog.md)
- [module boundary dependency matrix](module-boundary-dependency-matrix.md)
- [hotspot file audit pass 2](hotspot-file-audit-pass2.md)
- [PR-level remediation plan pass 3](pr-level-remediation-plan-pass3.md)

Detailed review status:

| Module | Status | Notes |
| --- | --- | --- |
| operations | Detailed pass 1 complete | Projection bloat and HTTP surface risk documented |
| orchestration | Detailed pass 1 remediation in progress | Lifecycle coordinator, worker CLI, benchmark runtime, executor benchmark command registration, engine model/helper/outcome split, execution-chain repository, coordinator payload-helper split, waiting approval recovery split, engine session tool-result projection split, run queue/session/worker/terminal lifecycle mixins, maintenance context-budget/compaction/classification split, and runtime request draft model/session/payload split covered; remaining tool-wait recovery breadth and long-chain invariants remain the main hotspots |
| tool | Detailed pass 1 remediation in progress | Worker/source/run-loop/run-resolution split covered; Tool package facade remediated; Tool persistence repository facade remediated; Tool domain entity, catalog model, and HTTP models/payload projection split |
| llm | Detailed pass 1 complete | Provider adapter/request rendering risks documented |
| session | Detailed pass 1 complete | Replay/window/service split risks documented; query/read window construction split into `SessionQueryReader` |
| context_workspace | Detailed pass 1 complete | Context control/render snapshot risks documented; workspace/tree/snapshot/slice services split behind a thin export surface |
| workbench | Detailed pass 1 complete | Timeline projector, fallback risks, and projection diagnostics documented |
| browser | Detailed pass 1 complete | Action engine/runtime split risks documented; execution lifecycle, primitive page actions, and locator/ref resolution are split from the action-engine dependency assembly |
| channels | Detailed pass 1 complete | Runtime transport/submission split and delivery lifecycle risks documented; profile, interaction, and runtime-registry services split behind a thin export surface |
| memory | Detailed pass 1 complete | Storage/index/runtime retrieval risks documented |
| skills | Detailed pass 1 complete | Package/catalog/runtime resolution risks documented |
| access | Detailed pass 1 complete | Credential/OAuth/readiness boundary risks documented |
| authorization | Detailed pass 1 complete | Grant state-machine, audit redaction, HTTP DTO/payload/service/agent-grant/policy-handler/decision-route split, agent-managed policy helper split, tool execution authorization helper split, policy impact helper split, temporary grant helper/use-case split, decision use-case split, audit record helper split, audit redaction helper split, policy lifecycle split, public service facade split, agent grant/revoke coordinator split, and persistence mapper split covered |
| settings | Detailed pass 1 remediation in progress | Governance truth-source and HTTP bulk risks documented; HTTP action models/helpers/responses/execution/mutation/validation helpers are split; setup resource collection/import/seed/result helpers, database URL summary, Access bootstrap resources, core bootstrap resource collectors, service bundle construction, action result helpers, resource definition/publication/action helpers, override action helper, action-audit helper, resource-versioning helper, effective resolution, query service, and shared service helpers are split; Settings domain aggregates are split behind an 18-line `domain/entities.py` export surface; materialization payload/profile/tool/access normalization is split from the effective config materializer; persistence record DTOs, SQLAlchemy model/record mappers, domain/repository mappers, and resource/version/override/snapshot/audit repository families are split from repository query classes; service-layer audit redaction now delegates to shared Settings redaction helper; application service/setup hotspots are reduced to facades |
| agent | Detailed pass 1 complete | Profile/home/context handoff risks documented; HTTP profile/home route split, request model/request mapper/response/service/error helper split, CLI payload and command split, profile sync/state CLI command split, profile factory/update helper, profile lifecycle use-case split, resolution response, application DTO/event payload, home runtime rule, home registry/config/file operations helper, home use-case orchestration split, Settings import rule, resolution DTO/helper split, source-specific resolution split, domain value-object split, and home-config IO/payload split covered |
| events | Detailed pass 1 complete | Backend mode and contract neutrality risks documented |
| dispatch | Detailed pass 1 complete | Queue/claim/lease concurrency risks documented |
| daemon | Detailed pass 1 complete | Service supervision and health surface risks documented |
| event_relay | Detailed pass 1 complete | Retained bridge boundary and cursor/retry behavior documented |
| artifacts | Detailed pass 1 complete | Filesystem lifecycle cleanup covered; access risk documented |
| mobile | Detailed pass 1 complete | Device isolation, bounded ADB diagnostics, and engine helper split covered |
| ocr | Detailed pass 1 complete | OCR adapter errors, result-size budgets, and host/application capacity policy covered |
| process | Detailed pass 1 complete | Bounded output/stale-session behavior documented |
| delivery | Detailed pass 1 complete | Placeholder retired |
| core config | Remediation pass in progress | Runtime guards, env coercion, browser profiles, mobile device config, Tool provider config, LLM profile config, Agent profile config, and Channel profile config split from global Settings entry |

Core runtime:

- [orchestration](module-orchestration.md)
- [llm](module-llm.md)
- [session](module-session.md)
- [context_workspace](module-context-workspace.md)
- [tool](module-tool.md)
- [operations](module-operations.md)
- [workbench](module-workbench.md)

Capability and integration modules:

- [browser](module-browser.md)
- [channels](module-channels.md)
- [memory](module-memory.md)
- [skills](module-skills.md)
- [access](module-access.md)
- [authorization](module-authorization.md)
- [settings](module-settings.md)
- [agent](module-agent.md)

Infrastructure/support modules:

- [events](module-events.md)
- [dispatch](module-dispatch.md)
- [daemon](module-daemon.md)
- [event_relay](module-event-relay.md)
- [artifacts](module-artifacts.md)
- [mobile](module-mobile.md)
- [ocr](module-ocr.md)
- [process](module-process.md)
- [delivery](module-delivery.md)

## Recommended Remediation Sequence

1. Operations: split large read model files and add projection cost/freshness checks.
2. Tool execution/orchestration: finish shrinking prepared execution and validation branches; add lifecycle invariant tests.
3. Browser: split action engines, script insight, trace, and application service responsibilities.
4. Tool: split source/package/runtime worker paths; define stable external integration contracts.
5. LLM: finish provider request/response adapter cleanup and protect against provider-specific logic leaking upward.
6. Persistence: production-mode gate for in-memory/file fallbacks and query-budget tests.
7. Interfaces: shrink HTTP/CLI files with application read model DTO services.
8. External integration: document stable application ports and event contracts per module.

## Detailed Pass 1 Rollup

Use this rollup to turn the per-module findings into implementation waves.

### P1 Before Broad Multi-User Launch

- `operations`: split projection builders and add freshness/cost metrics.
- `orchestration`: keep coordinator role narrow; add lifecycle invariant tests.
- `tool`: split source/package/worker/runtime paths and harden assignment/timeout behavior.
- `llm`: keep provider adapters symmetric request/response translators; prevent provider-specific structures from leaking upward.
- `session`: split append/replay/compaction/query services and preserve protocol-required replay items.
- `context_workspace`: keep tree as control plane refs/state; ensure provider input receives bounded selected slices only.
- `workbench`: split large projectors and remove fallback progress that hides missing owner facts.
- `browser`: split action engines/application services and add profile lease, cleanup, timeout, and retention tests.
- `channels`: split transport runtime complete; harden delivery/dead-letter/idempotency.
- `access`: split OAuth/query/action/readiness flows and enforce no-raw-secret invariants.
- `settings`: shrink HTTP governance surface and require owner/truth/write/apply metadata for every resource.

### P2 Hardening

- `memory`: add index freshness, recall latency, and storage-mode tests.
- `skills`: split interfaces/authoring/owner-state, add trusted source and runtime resolution tests.
- `authorization`: HTTP DTO/read-helper/decision-route split now covered after grant lifecycle, dry-run, Access-boundary, and audit-redaction coverage.
- `events`: enforce Redis for shared runtime and add contract/cursor/outbox tests.
- `dispatch`: add concurrent claim, lease expiry, and idempotency tests.
- `daemon`: add lifecycle smoke tests and host/workspace scope documentation.
- `agent`: test agent.home Context Workspace handoff and avoid hidden prompt input.
- `mobile`: split engine concerns and add screenshot/artifact retention budget tests.
- `artifacts`: subject-aware preview/download authorization remains after retention/quota cleanup coverage.
- `ocr`: host capacity/concurrency policy now covered after adapter error and result-size coverage.
- `process`: terminal-session retention/quota cleanup is covered after bounded output and stale-session tests.
- `event_relay`: retained as separate Workbench update bridge; add Operations health counters if needed.

### Ownership Decision

- `delivery`: retired placeholder. Reintroduce only after a future bounded-context design distinct from Channels and Events.
