# Hotspot File Audit Pass 2

Date: 2026-06-21

This pass drills into the largest and highest-risk files identified by the module audit. It is not a rewrite plan for every function. It names the responsibility clusters, the architectural risk, the target split, and the tests that should guard the split.

## Scope

| File | Current lines | Status | Risk Shape |
| --- | ---: | --- | --- |
| `channels/application/lark_runtime.py` | 489 | remediated | Lark service facade and observe loop after observation, outbound delivery, identity, long-connection, and submission splits |
| `operations/application/read_models/events.py` | 442 | remediated | Thin Events Operations facade after query/view models, filters, overview sections, event details, observer/subscription sections, topic-contract-route projection, and state collection split |
| `operations/application/read_models/daemon.py` | 643 | remediated | Thin Daemon Operations facade after view models, shared formatting/status helpers, event collection/table projection, primary table sections, detail projections, and health/metric/chart sections split |
| `operations/application/read_models/channels.py` | 348 | remediated | Thin Channels Operations facade after page models, shared display/status helpers, event collection, table/contract sections, detail projections, and health/chart sections split |
| `operations/interfaces/http.py` | 129 | remediated | Thin route composition surface after runtime/SSE, projection read, projection helper, action service, and controlled-action route splits |
| `operations/interfaces/http_models.py` | 141 | remediated | Thin Operations HTTP DTO export module after core response primitives, action request/result DTOs, support page responses, runtime page responses, and execution page responses split |
| `operations/application/read_models/skills.py` | 349 | remediated | Thin Skills Operations facade after page models, shared display/status helpers, event/authoring projection, health/chart/actions, table projection, and detail projection split |
| `operations/application/read_models/browser.py` | 251 | remediated | Thin Browser Operations facade after page models, shared runtime/proxy helpers, event row projection, profile/pool/allocation/page/daemon row projection, table sections, and health/metric/action sections split |
| `operations/application/read_models/memory.py` | 203 | remediated | Thin Memory Operations facade after page models, shared status/format helpers, event collection/projection, context record/query helpers, health/chart/actions, table projection, and file detail projection split |
| `operations/application/read_models/access.py` | 211 | remediated | Thin Access Operations facade after page models, shared target/status helpers, inventory collection/filtering, access event collection, health/chart/actions, table projection, and target detail projection split |
| `tool/infrastructure/tool_packages.py` | 589 | remediated | Thin package facade after OpenAPI/access parsing, common manifest value parsing, local tool declaration mapping, provider backend parsing, and activation helper split |
| `orchestration/domain/entities.py` | 17 | remediated | Thin entity export surface after execution, run, ingress, executor-lease, and payload-helper split |
| `browser/infrastructure/script_insight.py` | 668 | remediated | Browser script insight action facade after runtime expression, payload coercion, and source-analysis split |
| `browser/infrastructure/action_engine_scripts.py` | 59 | remediated | Thin expression export surface after marker, snapshot, bulk-selection, overlay/picker, target/text script split |
| `browser/infrastructure/action_trace.py` | 380 | remediated | Browser action trace service entrypoint after payload, snapshot, state, network, and envelope/recommendation helper split |
| `browser/infrastructure/network_page_fetch.py` | 173 | remediated | Browser page-network fetch service entrypoint after request normalization, page-runtime execution, safety/diff analysis, event payload, and common result helper split |
| `browser/infrastructure/engines.py` | 413 | remediated | Browser control-engine surface after tab operation orchestration, tab/runtime-state metadata, CDP wire IO, host/process lifecycle, and in-memory engine split |
| `browser/domain/value_objects.py` | 76 | remediated | Thin domain value export surface after type alias, validation helper, profile, tab/ref, network, and command/result value split |
| `browser/interfaces/http.py` | 556 | improved | Browser route surface after request model, profile helper, proxy egress, and update payload rule split |
| `browser/interfaces/profile_payloads.py` | 23 | remediated | Thin profile payload export surface after diagnostics, entry, and aggregate payload split |
| `browser/interfaces/cli.py` | 36 | remediated | Thin Typer composition root after profile, pool, allocation, host, action, and helper command split |
| `browser/application/observation.py` | 354 | remediated | Browser observation service entrypoint after value, page/snapshot, runtime/code/network, interaction/guidance, and final projection split |
| `operations/application/read_models/orchestration.py` | 574 | remediated | Public facade after Orchestration Operations status/failure/metric/action/runtime-fact split |
| `tool/infrastructure/persistence/repositories.py` | 33 | remediated | Thin export surface after source, function/catalog, provider backend, surface, runtime, and payload mapper split |
| `channels/interfaces/http.py` | 322 | remediated | Thin route composition surface after DTO/helper/Lark/Webhook/Web/dead-letter route split |
| `channels/application/lark_runtime_submission.py` | 317 | remediated | Focused Lark message-to-run submission service |
| `operations/application/read_models/llm.py` | 460 | remediated | Public facade after LLM Operations model/run-context/detail split |
| `operations/application/read_models/tool.py` | 719 | remediated | Public facade after Tool Operations helper split |
| `orchestration/interfaces/worker_cli.py` | 37 | remediated | Thin export layer after worker CLI split |
| `tool/infrastructure/cli_source.py` | 61 | remediated | Thin export layer after CLI source split |
| `orchestration/application/execution_chain_lifecycle.py` | 62 | remediated | Thin export layer after execution chain lifecycle split |
| `workbench/application/timeline_projector.py` | 189 | remediated | Thin/medium facade after timeline projection split |
| `workbench/application/step_projector.py` | 427 | improved | Medium step facade after support/LLM/tool projections split |
| `context_workspace/application/root_nodes.py` | 123 | remediated | Thin bootstrap facade after root-node family split |

## Pass 2 Findings

### 1. Operations Read Models Are Page Applications

Files:

- `operations/application/read_models/tool.py`
- `operations/application/read_models/llm.py`
- `operations/application/read_models/orchestration.py`

Current responsibility clusters:

- query normalization and pagination
- health/metric card calculation
- overview/action model generation
- table section construction
- row formatting and tone/status mapping
- detail payload storage and retrieval helpers
- event topic scanning and observed event projection
- owner fact lookup and defensive fallback
- route/path generation for Workbench/Trace
- error/root-cause classification
- provider/tool/runtime diagnostic summaries

Architectural risk:

Operations is intended to be a sidecar projection layer. These files have become page-specific applications. They are not business owners, but their size makes them likely to drift into hidden runtime interpretation and expensive request-time scans.

Target split:

- `query_inputs.py`: query/filter/pagination models and normalization.
- `health_projection.py`: health, metrics, status/tone labels.
- `tables/*.py`: table section/row builders by topic.
- `details/*.py`: detail payloads and drill-down projections.
- `events_projection.py`: event topic reads and event row formatting.
- `diagnostics/*.py`: provider/tool/orchestration risk and error classification.
- `routes.py`: Workbench/Trace route helpers.
- `presenters.py`: display/tone/truncation/formatting helpers.

Required tests:

- golden projection tests per module page
- projection cost tests: owner calls, events scanned, items processed
- freshness tests: projection updated_at and observer cursor surfaced
- no owner mutation from read model builders
- no generic fallback progress/health when owner facts are missing

### 2. Browser Runtime Has Two Different Hotspots

Current remediation status: complete for the Pass 2 Browser hotspot scope.
`application/services.py` is now a thin export layer over focused application
services. `infrastructure/action_engines.py` is now the action-engine
envelope/router; batch execution, raw CDP execution, action-trace coordination,
interaction primitives, ref/overlay handling, and wait actions are split into
focused infrastructure modules. `infrastructure/script_insight.py` is now the
script-insight action facade; runtime inspection JavaScript, payload coercion,
and source-analysis/search/extraction helpers live in focused modules.
`infrastructure/action_engine_scripts.py` is now a thin expression export surface;
marker constants, interactive snapshot, bulk-selection, overlay/picker, and
target/text scripts live in focused modules.
`infrastructure/action_trace.py` is now the action-trace service entrypoint;
payload coercion, snapshot command/diff helpers, storage/lifecycle state diffs,
network causality projection, and action envelope/recommendation logic live in
focused helper modules.
`domain/value_objects.py` is now a thin export surface; type aliases, validation
helpers, profile/system/pool values, tab/ref values, network capture/request
values, and command/result values are split by domain responsibility.
`interfaces/http.py` is now a route surface; request DTOs, profile/pool payload
helpers, proxy egress checks, and update-clear payload rules are split into
focused interface helper modules.
`interfaces/profile_payloads.py` is now a thin export surface over profile
diagnostics, row/entry payload, and aggregate payload helpers. `interfaces/cli.py`
is now a thin Typer composition root over profile, pool, allocation, host,
action, and shared helper modules.
`application/observation.py` is now the Browser observation service entrypoint;
section payload primitives, page/snapshot projection, runtime/code/network
projection, interaction/form/overlay guidance, and final assembly are split into
focused application helpers.

Files:

- `browser/infrastructure/action_engines.py`
- `browser/application/services.py`
- `browser/infrastructure/script_insight.py`
- `browser/infrastructure/action_trace.py`
- `browser/domain/value_objects.py`

Current `action_engines.py` clusters:

- CDP/Playwright execution entry
- page/context selection
- locator/ref resolution
- overlay and protected ref restoration
- text input/editability handling
- click/coordinate action execution
- snapshot/ref persistence
- wait/retry behavior
- error mapping

Current `services.py` clusters:

- profile resolution
- capability resolution
- command/page action assembly
- execution planning
- tab operations
- selection operations
- allocation target recycling/inspection
- execution coordination
- profile admin
- pool admin
- allocator service

Architectural risk:

Browser is powerful and stateful. A giant engine class makes it hard to prove profile isolation, cleanup, timeout behavior, and absence of task-specific navigation logic.

Target split:

- `application/profile_admin.py`
- `application/profile_pool.py`
- `application/profile_allocator.py`
- `application/execution_coordinator.py`
- `application/tab_ops.py`
- `application/selection_ops.py`
- `infrastructure/cdp_session.py`
- `infrastructure/action_executor.py`
- `infrastructure/locator_resolution.py`
- `infrastructure/snapshot_capture.py`
- `infrastructure/overlay_refs.py`
- `infrastructure/browser_errors.py`

Required tests:

- profile lease/isolation tests
- CDP session cleanup tests
- action timeout/cancellation tests
- snapshot/trace size budget tests
- no site-specific logic in Browser core

### 3. Tool Runtime Still Concentrates Worker And Source Complexity

Files:

- `tool/application/worker_service.py`
- `tool/application/source_service.py`
- `tool/infrastructure/cli_source.py`
- `tool/infrastructure/tool_packages.py`

Current `worker_service.py` clusters:

- worker registration/staleness
- assignment reconciliation
- worker loop and async scheduling
- assignment launching/reaping
- run heartbeat
- prepared runtime execution
- result completion
- artifact externalization
- validation
- recovery/failure/retry
- runtime registry snapshot

Current `source_service.py` clusters:

- source query service
- source command service
- function command service
- runtime request bundle generation
- source/function event payloads
- provider backend candidate conversion
- source/function record conversion
- credential/runtime requirement parsing

Current `cli_source.py` clusters:

- CLI source config parsing
- credential binding config
- guided/promoted tool discovery
- runtime process launch/wait/read
- process output observation
- result/help envelopes
- redaction and credential temp file injection
- promoted function parameter parsing
- path and executable validation

Current `tool_packages.py` clusters:

- namespace/package manifest orchestration
- local/runtime/openapi binding selection
- activation registration dispatch

Current remediation status:

- OpenAPI provider manifest parsing and credential binding validation now live in
  `tool_package_access.py`.
- Access credential requirement set parsing now lives in
  `tool_package_access.py`.
- Runtime request metadata, dependency requirements, capability ids, common
  string/enum/mapping payload parsing, and runtime requirement set derivation now
  live in `tool_package_manifest_values.py`.
- Local tool domain declaration construction and parameter parsing now live in
  `tool_package_tool_declarations.py`.
- Provider backend plan parsing now lives in `tool_package_provider_backends.py`.
- Handler/runtime entrypoint resolution, typed dependency injection, and activation
  construction now live in `tool_package_activation.py`.
- `tool_packages.py` is now a package-load/apply facade; remaining Tool hotspots
  are persistence repositories and any future package facade growth.
- Tool persistence generic payload mapping now lives in
  `persistence/repository_payloads.py`; Tool Surface payload restoration now lives in
  `persistence/repository_surface_payloads.py`; Tool Surface persistence now lives in
  `persistence/surface_repository.py`; Tool source and discovery-run persistence now
  lives in `persistence/source_repositories.py`; Tool function and catalog-record
  persistence now lives in `persistence/function_repositories.py`; provider backend
  persistence now lives in `persistence/provider_backend_repository.py`; Tool run,
  assignment, and worker repositories now live in `persistence/runtime_repositories.py`.
  The public
  `persistence.repositories` module remains the narrow import surface for the
  SQLAlchemy unit of work while the implementation is split by lifecycle cluster.

Architectural risk:

Tool owns tool catalog and tool run lifecycle, but these files combine lifecycle, runtime execution, source discovery, output shaping, credential injection, and artifact externalization. This makes failure behavior hard to reason about and can cause hidden coupling to Access/Process/Artifacts.

Target split:

- `worker/registration.py`
- `worker/assignment_loop.py`
- `worker/run_executor.py`
- `worker/result_completion.py`
- `worker/artifact_externalization.py`
- `worker/recovery.py`
- `catalog/source_query.py`
- `catalog/source_commands.py`
- `catalog/function_commands.py`
- `runtime_request/bundle_builder.py`
- `runtime_request/requirements.py`
- `cli/config.py`
- `cli/discovery.py`
- `cli/runtime.py`
- `cli/envelopes.py`
- `cli/redaction.py`
- `cli/credential_injection.py`
- `tool_package_access.py`
- `tool_package_manifest_values.py`
- `tool_package_tool_declarations.py`
- `tool_package_provider_backends.py`
- `tool_package_activation.py`

Required tests:

- worker assignment/heartbeat/recovery tests
- result externalization tests for large text/image/file blocks
- CLI credential redaction tests
- runtime request bundle golden tests
- source/function command idempotency tests

### 4. Orchestration Runtime Logic Is Better Than Its CLI Surface

Files:

- `orchestration/application/execution_chain_lifecycle.py`
- `orchestration/interfaces/worker_cli.py`

Current `execution_chain_lifecycle.py` clusters:

- chain bootstrap
- dispatch step preparation
- LLM step start/complete/fail
- tool batch materialization
- approval materialization
- resume/final response materialization
- tool run/result/session item execution items
- continuation decision items
- correlation/id generation
- terminal step completion rules

Current `worker_cli.py` clusters:

- executor/scheduler/admin container construction
- executor loop/probe
- benchmark run creation and waiting
- synthetic tool IO LLM adapter
- tool IO benchmark runtime registration
- daemon runtime benchmark
- scheduler loop
- CLI command registration

Architectural risk:

The execution chain lifecycle is a real state machine but is currently represented as many free functions. The worker CLI mixes production worker entrypoints with benchmark and synthetic adapter code. CLI complexity can hide runtime assumptions and makes it harder to reason about daemon-managed long services.

Target split:

- `execution_chain/bootstrap.py`
- `execution_chain/llm_steps.py`
- `execution_chain/tool_steps.py`
- `execution_chain/approval_steps.py`
- `execution_chain/session_items.py`
- `execution_chain/continuation.py`
- `execution_chain/ids.py`
- `interfaces/worker_cli/executor_commands.py`
- `interfaces/worker_cli/scheduler_commands.py`
- `interfaces/worker_cli/admin_commands.py`
- `interfaces/worker_cli/benchmarks.py`
- `interfaces/worker_cli/synthetic_adapters.py`

Required tests:

- state-machine tests for chain/step/item transitions
- late tool result tests
- continuation decision item tests
- benchmark code isolation test: production CLI can run without synthetic adapter imports
- daemon-managed worker smoke tests

### 5. Session Needs Service-Level Decomposition

File:

- `session/application/services.py`

Current responsibility clusters:

- ensure/sync routed session
- session and instance query
- metadata mutation
- item range/list/query
- context frontier
- item append/build
- active segment compaction
- replay/maintenance windows
- session reset
- runtime binding metadata
- workspace/default resolution
- reset policy evaluation

Architectural risk:

Session is the conversation ledger and therefore central to provider replay correctness. One service currently carries command, query, replay, compaction, and routing behavior. That increases the chance that request rendering, compaction, and UI projection drift.

Target split:

- `SessionCommandService`
- `SessionQueryService`
- `SessionItemAppendService`
- `SessionReplayWindowService`
- `SessionCompactionService`
- `SessionMetadataService`
- `SessionRoutingService`
- `SessionResetPolicyService`

Required tests:

- concurrent append/replay/compaction tests
- replay preserves provider protocol-required items
- compaction does not delete owner facts required by Workbench/Operations
- LLM request builders use replay service, not repositories

### 6. Settings HTTP Is Doing Governance Application Work

File:

- `settings/interfaces/http.py`

Current responsibility clusters:

- overview/list/detail endpoints
- kind/resource action execution
- bootstrap import
- overview/resource payload presenters
- audit pagination and table construction
- action policy and rejection rules
- runtime defaults read model
- runtime defaults validation
- impact/effective configuration/danger zone payloads
- redaction and URL password masking

Architectural risk:

Settings is a governance surface, not universal owner truth. A 2082-line HTTP file makes it too easy for routing/presentation/action policy to drift from owner module services.

Target split:

- `interfaces/http/routes.py`
- `interfaces/http/actions.py`
- `interfaces/http/runtime_defaults.py`
- `interfaces/http/audit.py`
- `application/read_models/overview.py`
- `application/read_models/resource_detail.py`
- `application/read_models/runtime_defaults.py`
- `application/action_policy.py`
- `application/redaction.py`

Required tests:

- every resource declares owner/truth/write/apply metadata
- module-owned actions dispatch to owner services
- env is seed/import only, not live truth
- redaction tests for secrets/database URLs

### 7. Workbench Projectors Need Family Split

Files:

- `workbench/application/timeline_projector.py`
- `workbench/application/step_projector.py`

Current `timeline_projector.py` clusters:

- execution step timeline projection
- LLM response item timeline projection
- tool execution item timeline projection
- content visibility policy
- tool lifecycle merge
- diagnostic items
- timeline sorting
- debug/loop-control suppression

Current `step_projector.py` clusters:

- chain step views
- LLM step views
- continuation decision views
- assistant progress views
- missing access views
- tool step views
- approval views
- generic execution step views

Architectural risk:

Workbench should show the user what happened, not invent missing runtime truth. Large projectors make fallback/suppression logic difficult to audit and can produce timeline jumping or misleading progress.

Target split:

- `timeline/response_items.py`
- `timeline/tool_interactions.py`
- `timeline/execution_steps.py`
- `timeline/visibility_policy.py`
- `timeline/lifecycle_merge.py`
- `timeline/sorting.py`
- `steps/llm.py`
- `steps/tool.py`
- `steps/approval.py`
- `steps/continuation.py`
- `steps/missing_access.py`

Required tests:

- golden timeline fixtures from recorded long-chain runs
- no placeholder progress when owner facts are missing
- stable ordering under active run updates
- debug-only items stay out of primary timeline

### 8. Context Workspace Root Bootstrap Has Been Split

File:

- `context_workspace/application/root_nodes.py`

Current remediation status: complete for this audit wave. `root_nodes.py` is now
a small bootstrap facade preserving seed order and public constants. Root-node
families live in focused `root_node_*` modules.

Former responsibility clusters:

- root section seeds
- runtime contract seed
- execution guide seed
- agent identity/home seeds
- context priority/usage seeds
- execution current/run flow/goal/environment/permissions/provider/budget/constraints seeds
- working plan and continuation seeds
- payload helpers and estimates

Retained architectural risk:

This file is large but lower risk than runtime hot path files. It is bootstrap/static seed generation, not owner fact mutation. The main risk is accidental duplication of runtime contract or owner facts.

Target split:

- `root_nodes/instructions.py`
- `root_nodes/agent.py`
- `root_nodes/run.py`
- `root_nodes/execution.py`
- `root_nodes/planning.py`
- `root_nodes/estimates.py`

Required tests:

- stable root ids and parent ids
- runtime contract hash/version consistency
- root payloads do not duplicate owner facts as durable truth

### 9. Access OAuth And Skills Filesystem Are Integration Hotspots

Files:

- `access/application/oauth.py`
- `skills/infrastructure/filesystem/repository.py`

Current Access OAuth split:

- `access/application/oauth.py`: provider/account flow orchestration, account
  lifecycle coordination, token-store/repository writes, and credential-binding
  registration side effects.
- `access/application/oauth_contracts.py`: repository/token-store protocols and
  OAuth result DTOs.
- `access/application/oauth_redaction.py`: OAuth payload redaction helper.
- `access/application/oauth_token_client.py`: token endpoint HTTP behavior for
  authorization-code, device-code, refresh, and revoke, including retryable
  provider failure handling and redacted endpoint exceptions.
- `access/application/oauth_setup_flows.py`: setup-session record/result
  construction, authorization URL shaping, and device-code payload shaping.
- `access/application/oauth_callback_listener.py`: local Codex callback listener
  lifecycle and browser opener.
- `access/application/oauth_codex.py`: OpenAI Codex OAuth constants and
  access-token identity extraction.
- `access/application/oauth_token_payloads.py`: token payload expiry/scope/subject
  extraction, token masking, default account id, PKCE challenge, scope diff payload,
  and small text normalization helpers.
- `access/application/oauth_account_records.py`: OAuth provider/account record
  construction, token document construction, account status replacement, refresh
  account shaping, and Settings credential-binding request construction.

Remaining `access/oauth.py` clusters:

- provider/account CRUD
- browser/device flow orchestration
- account binding registration
- account refresh/revoke coordination

Current Access query split:

- `access/application/query.py`: control-plane query provider facade, owner record
  endpoint payload composition, and public query-service methods.
- `access/application/query_results.py`: Access query result/degraded DTOs.
- `access/application/query_assets.py`: synthetic asset summary/detail projection
  for credential bindings without explicit Access asset records.
- `access/application/query_overview_assets.py`: overview counts, empty overview,
  asset-list projection, and readiness lookup.
- `access/application/query_record_models.py`: credential/consumer/readiness/setup/
  OAuth/audit read-model record shaping and consumer binding merge rules.
- `access/application/query_requirements.py`: credential requirement rows,
  requirement status/hints, and requirements-by-consumer payloads.
- `access/application/query_records.py`: Settings/Access owner record collection,
  external consumer merge, and setup/OAuth/readiness model conversion.
- `access/application/query_audits.py`: Access/Settings audit pagination, merge,
  and sorting.

Current Access read-model payload split:

- `access/application/read_models.py`: Access application read-model DTOs and
  `to_payload` methods.
- `access/application/read_model_payloads.py`: timestamp payloads, requirement
  normalization, slot binding normalization, setup-flow hint payloads,
  requirements-by-consumer grouping, source-ref masking, masked preview handling,
  and sensitive-key redaction.

Current Access action split:

- `access/application/actions.py`: action intent routing, audit attempt lifecycle,
  event publication, Settings action delegation, dry-run handling, and dangerous
  action confirmation checks.
- `access/application/action_contracts.py`: Access action request/result DTOs.
- `access/application/action_changes.py`: typed change extraction and required text
  parsing.
- `access/application/action_redaction.py`: sensitive payload redaction and raw-secret
  input rejection.
- `access/application/action_payloads.py`: action event-name mapping, audit result
  payloads, Settings action result conversion, and default decision payload.
- `access/application/action_readiness.py`: consumer credential requirement readiness
  calculation and compatibility checks.
- `access/application/action_setup_handlers.py`: setup-session and credential
  requirement verification handlers.
- `access/application/action_oauth_handlers.py`: OAuth provider registration, setup
  session, Codex login, refresh, rotation, and status-change handlers.

Current Access Settings adapter split:

- `access/application/settings_integration.py`: Settings action adapter and Settings
  resource upsert coordinator.
- `access/application/settings_config_views.py`: materialized Access config
  view/provider over Settings effective config.
- `access/application/settings_action_contracts.py`: Settings action request protocol
  and result DTO.
- `access/application/settings_payloads.py`: change/payload parsing and normalization.
- `access/application/settings_record_models.py`: Settings payload to Access
  asset/credential/consumer record mapping and record-to-payload conversion.
- `access/application/settings_credential_bindings.py`: credential binding update,
  source-ref normalization, public redacted metadata, and validation metadata.
- `access/application/settings_consumer_bindings.py`: consumer binding id, slot,
  requirement, expected-kind, and result payload conversion.

Current Access service rule split:

- `access/application/services.py`: requirement readiness, setup routing,
  credential-resolution event publication, and public application-service methods.
- `access/application/configured_credentials.py`: configured credential record
  lookup, source derivation, OAuth provider lookup, OAuth account token resolution,
  and configured credential resolution.
- `access/application/credential_requirement_rules.py`: requirement parsing, credential
  binding canonicalization, expected-kind detection, binding/source compatibility
  errors, and readiness mismatch status mapping.
- `access/application/credential_resolver.py`: env/file/literal credential source
  resolution and source readiness probing.
- `access/application/credential_resolution_audit.py`: credential resolution audit
  context construction, event payloads, safe source refs, trace redaction, consumer
  audit payloads, sensitive key detection, and audit text truncation.
- `access/application/credential_setup_flows.py`: Access setup-flow object
  construction for env/file/OAuth/app-credential/unsupported credential paths.

Current Access inventory split:

- `access/application/inventory.py`: read-model inventory grouping, usage
  summarization, and inventory payload assembly.
- `access/application/inventory_requirement_rules.py`: readiness check-spec
  construction, credential binding labels, requirement masking, and credential
  asset kind calculation.
- `access/application/inventory_redaction.py`: inventory metadata redaction.

Current Access migration split:

- `access/application/migration.py`: snapshot DTOs, migration plan DTOs, legacy
  container snapshot assembly, and migration plan builder coordination.
- `access/application/migration_value_helpers.py`: legacy object/mapping value
  extraction, boolean/string normalization, service-list extraction, and dedupe.
- `access/application/migration_requirement_payloads.py`: migration credential
  source shaping, channel metadata requirement extraction, requirement-set
  normalization/masking, credential binding migration matching, slug/digest
  generation, and redaction policy payloads.

Current Access persistence split:

- `access/infrastructure/persistence/repositories.py`: repository transactions,
  query construction, upsert lifecycle, and audit state transitions.
- `access/infrastructure/persistence/repository_mappers.py`: SQLAlchemy model to
  application record conversion, record to model conversion, timestamp coercion, and
  text validation.
- `access/infrastructure/oauth_tokens.py`: file-backed OAuth token storage, atomic
  writes/deletes, and storage-key locks used by refresh/revoke coordination.

Current Skills filesystem split:

- `skills/infrastructure/filesystem/repository.py` (548 lines): public filesystem repository orchestration, install/create/update/delete/read entrypoints, source root selection.
- `skills/infrastructure/filesystem/path_safety.py`: skill root normalization, package path resolution, support-file path normalization, traversal prevention.
- `skills/infrastructure/filesystem/manifest_parser.py`: SKILL.md frontmatter parsing, legacy manifest parsing, requirement normalization, markdown/frontmatter rendering.
- `skills/infrastructure/filesystem/package_files.py`: bounded file reads, legacy manifest file reads, resource discovery, fingerprinting.
- `skills/infrastructure/filesystem/package_loader.py`: root discovery and directory-to-`SkillPackage` loading.

Architectural risk:

Both files touch external or user-controlled surfaces: tokens and local files. They need clearer safety seams and concentrated tests.

Target split:

- `access/application/oauth_account_lifecycle.py`
- `access/application/oauth_account_binding.py`
- `access/application/oauth_payloads.py`
- `access/application/oauth_refresh_policy.py`
- Skills filesystem repository split is complete for this audit wave. Authoring payload/conversion/validation/readiness/apply helpers and draft diff building have also been split out of `application/authoring_service.py`, and draft audit/event side effects have moved to `authoring_observation.py`, reducing it to lifecycle, repository, and package-service coordination. Owner package/source index and readiness projection helpers have been split out of `application/owner_state.py`, reducing it to a coordination service. SQLAlchemy/application record mapping has been split out of `infrastructure/persistence/repositories.py` into `repository_mappers.py`, reducing the repository to a transaction/query shell. HTTP request/response DTOs have moved to `interfaces/http_models.py`, reducing `interfaces/http.py` to a moderate route layer. CLI option parsing and CLI payload projection have moved to `interfaces/cli_options.py` and `interfaces/cli_payloads.py`; Source and Draft command groups have moved to `interfaces/cli_source_commands.py` and `interfaces/cli_draft_commands.py`, reducing `interfaces/cli.py` to a moderate root command layer. Source/skill runtime visibility, Context Workspace runtime-resolution golden coverage, and install/create race normalization are covered. Remaining Skills hardening is no longer a large-file split issue; it is trusted source/provenance policy before broader external installation.

Required tests:

- OAuth no-raw-secret logs/events/errors
- refresh/revoke retry and storage-key concurrency
- callback listener cleanup
- skill path traversal prevention
- trusted source/install root isolation
- skill manifest/frontmatter compatibility tests

## Implementation Guidance

Do not split all files mechanically. Split in this order:

1. Add tests and architecture guards around the current behavior.
2. Extract pure presenter/formatting helpers first where safe.
3. Extract owner-fact query and command services before changing behavior.
4. Move runtime side effects last, behind tests.
5. Delete old paths in the same change. Do not leave old/new double tracks.

## Immediate Next Actions

1. Add architecture guard tests from `remediation-backlog.md` Gate A.
2. Start with `operations/application/read_models/tool.py` because it is the largest and has mostly pure projection functions.
3. Then split `settings/interfaces/http.py` and Workbench projectors because these are high UI correctness risk with lower runtime side-effect risk.
4. Then split Browser/Tool runtime engines only after lifecycle tests are in place.
