# Module Audit: agent

## Verdict

Medium-low risk. Agent owns profile and home/workspace config. The module is relatively compact, and the former large HTTP surface plus the application input/event payload bulk, profile lifecycle orchestration, and home use-case orchestration are now split into focused modules.

## Evidence

- 57 Python files, about 5704 lines.
- Large files include `interfaces/http_resolution_models.py` (224), `application/profile_use_cases.py` (221), `interfaces/http_models.py` (217), `application/home_use_cases.py` (216), `interfaces/cli_profile_commands.py` (215), `application/home_operations.py` (215), and `interfaces/http_requests.py` (209). `interfaces/http.py` is now a 165-line profile route surface and home routes live in `interfaces/http_home_routes.py`. `application/services.py` is now a 174-line public facade. `application/models.py` is now a 36-line public model export surface over focused profile/home model modules. `interfaces/cli.py` is now a 17-line Typer composition root. `infrastructure/home_config.py` is now a 43-line entrypoint over focused IO and payload projection helpers. `application/resolution.py` is now a 138-line orchestration layer over focused LLM, Tool, Access, and Authorization resolution helpers. `domain/value_objects.py` is now a 26-line export surface over focused value-object modules.

## Findings

- Agent should own profile/home registry facts and expose resolution services.
- HTTP route surface is now split by profile/home route families; request-to-application conversion, response presentation, Agent service lookup, resolution service construction, and Agent error-to-HTTP mapping live in focused interface helpers.
- Application profile DTOs, home DTOs, profile event payload construction,
  resolution DTOs, resolution value/policy helpers, and pure home/runtime
  preference rules live outside `AgentApplicationService` and the main
  resolution query service.
- Agent application models are now split by role: profile command/action DTOs
  live in `application/profile_models.py`, home migrate/sync/export/snapshot DTOs
  live in `application/home_models.py`, and `application/models.py` remains a
  stable public export surface.
- Agent resolution now keeps source-specific projection logic in focused helpers:
  `resolution_llm.py`, `resolution_tools.py`, `resolution_access.py`, and
  `resolution_authorization_query.py`.
- Agent domain value objects now live in focused identity/instruction, LLM,
  execution, memory, runtime-preference, and common-helper modules behind a thin
  `domain/value_objects.py` export surface.
- Agent CLI command registration is split into profile command and home command
  modules; profile sync and profile state commands are split from the main profile
  command registration module. `interfaces/cli.py` only composes the Typer
  application.
- Agent home config infrastructure is split into entrypoint, atomic IO, payload
  projection, and migration-aware payload helper modules.
- Agent home use-case orchestration is split from `AgentApplicationService`;
  `application/home_use_cases.py` coordinates home migrate, sync, export,
  inspect, and file update flows.
- Agent profile lifecycle orchestration is split from `AgentApplicationService`;
  `application/profile_use_cases.py` coordinates profile register, sync, update,
  enable, disable, delete, list, and home-registry resolution flows.
- Agent must not directly execute runs or mutate runtime queues.
- Agent home file integration with Context Workspace must remain via owner adapter.

## Launch Risks

- Profile mutation can affect runtime prompt/context behavior unexpectedly.
- Workspace/home config loading can become a hidden source of model-visible input.

## Recommendations

- Keep profile CRUD, home registry resolution, and workspace config resolution as explicit service boundaries.
- Add tests for Context Workspace agent.home node generation from Agent owner facts.
- Keep request/input conversion and response presentation out of route modules as profile/home behavior grows.

## Detailed Pass 1

### Files Reviewed

- `application/services.py`
- `application/models.py`
- `application/profile_models.py`
- `application/home_models.py`
- `application/resolution.py`
- `application/settings_integration.py`
- `domain/entities.py`
- `domain/value_objects.py`
- `infrastructure/home_config.py`
- `infrastructure/home_registry.py`
- `infrastructure/home_files.py`
- `infrastructure/home_migration.py`
- `infrastructure/home_scaffold.py`
- `interfaces/http.py`
- `interfaces/cli.py`
- `interfaces/dto.py`

### File-Level Assessment

`interfaces/http.py` was 914 lines and is now 249 lines after moving response
presenters to `interfaces/http_models.py` and request models/input conversion to
`interfaces/http_requests.py`. Agent profile/home response DTOs remain in
`interfaces/http_models.py`, resolution endpoint response DTOs and presenters live in
`interfaces/http_resolution_models.py`, and HTTP request DTOs now live in
`interfaces/http_request_models.py`. `interfaces/http_requests.py` owns only
request-to-application input mapping and the stable re-export surface for existing route
imports. Agent service lookup, resolution service construction, and Agent
error-to-HTTP mapping live in `interfaces/http_services.py`. Home migration/config
response projection and profile-list projection live in `interfaces/http_models.py`.
The route file owns route parsing and owner service calls.

`interfaces/cli.py` is now 17 lines after moving profile command registration to
`interfaces/cli_profile_commands.py` and home command registration to
`interfaces/cli_home_commands.py`. Profile sync command registration lives in
`interfaces/cli_profile_sync_commands.py`; enable/disable/delete command registration
lives in `interfaces/cli_profile_state_commands.py`. Register/update payload
construction and profile-settings sync conversion live in `interfaces/cli_payloads.py`.
HTTP and CLI settings sync both delegate to `application/settings_integration.py`, so
the Settings-to-Agent import rule has one application-level source.

`application/services.py` is now 174 lines after moving application model DTOs behind
the `application/models.py` export surface, profile event/action payload helpers to
`application/event_payloads.py`, pure home/runtime preference rules to
`application/home_runtime.py`, and home registry/config/scaffold/migration/file
operations to `application/home_operations.py`. Registration input to `AgentProfile`
construction now lives in `application/profile_factory.py`; update input to domain
update kwargs translation lives in `application/profile_updates.py`. Profile lifecycle
orchestration now lives in `application/profile_use_cases.py`; home migrate, sync,
export, inspect, and file-update orchestration now lives in
`application/home_use_cases.py`; the shared Unit of Work protocol lives in
`application/unit_of_work.py`. The service is now a public facade and dependency
composition point for profile and home use cases.

`application/models.py` is now a thin export surface. Profile registration/update/action
DTOs and the `UNSET_FIELD` sentinel live in `application/profile_models.py`; home
migration/sync/export/snapshot/update-file DTOs live in `application/home_models.py`.
Agent application and interface modules import the narrower model module when they own
only one side of the profile/home boundary.

`application/resolution.py` is now 138 lines after moving resolution DTOs to
`application/resolution_models.py`, value coercion helpers to
`application/resolution_values.py`, and authorization policy-to-grant projection rules
to `application/resolution_authorization.py`. Source-specific resolution now lives in
`application/resolution_llm.py`, `application/resolution_tools.py`,
`application/resolution_access.py`, and
`application/resolution_authorization_query.py`. The query service remains important
because it determines which agent profile/home/workspace facts are selected for
runtime. This must stay explicit and test-covered because it influences model-visible
context through Context Workspace.

`domain/value_objects.py` is now a 26-line export surface. Identity/instruction
policy values live in `domain/identity_policy.py`; LLM routing/runtime policy values
live in `domain/llm_policies.py`; execution policy, memory binding, runtime
preferences, and shared normalization helpers live in focused domain modules. This
keeps public imports stable while making each value-object lifecycle independently
readable.

`infrastructure/home_config.py` is now a 43-line entrypoint. JSON load/atomic write
details live in `infrastructure/home_config_io.py`; profile payload projection lives
in `infrastructure/home_config_payloads.py`; migration-aware payload helpers,
runtime merge, and timestamp parsing live in
`infrastructure/home_config_payload_helpers.py`. `home_registry.py`, `home_files.py`,
`home_migration.py`, and `home_scaffold.py` remain focused infrastructure concerns.
`home_config.py` preserves the old `home_config.os.replace` test injection seam while
delegating writes to the IO helper.

### Boundary Cleanliness

Agent owns profile and home/workspace configuration. It does not execute runs,
schedule queues, or mutate orchestration runtime state.

Risk pattern:

- Agent home files can become hidden model-visible prompt input unless Context
  Workspace explicitly selects/render them.
- Settings integration must remain governance/entry-point integration; Agent remains
  owner of agent profile facts.
- Route modules no longer assemble profile value objects directly; low-level home file
  mutation still must stay behind Agent application invariants.
- CLI commands no longer assemble profile value objects directly; they parse arguments,
  call the application service, and format DTO output.
- Profile application DTOs are now importable without loading the service coordinator.
  This keeps Settings integration and HTTP request mapping from depending on service
  implementation details.
- Register/sync profile construction now has one application-level factory, preventing
  created-at preservation and runtime preference normalization from drifting.
- Update input field presence handling now lives in one application helper, preventing
  `UNSET_FIELD` semantics from being duplicated in service logic.

### Lifecycle Clarity

Agent lifecycle should be:

1. profile created/registered
2. home directory/config scaffolded or migrated
3. profile/home files synchronized
4. resolution service selects active agent/workspace config
5. Context Workspace references selected `agent.home.*` nodes
6. run submission consumes resolved agent context through orchestration inputs

This lifecycle exists but needs tests around the handoff to Context Workspace.

### Persistence And Efficiency

Agent uses filesystem home config/registry. This is acceptable for local runtime, but
shared production mode needs explicit isolation and no unbounded home file reads in
request render hot paths.

### Concurrency And Multi-User Readiness

Concurrent profile/home updates require atomic file writes and clear owner scoping.
The local registry now preserves existing entries on replacement failure and
serializes concurrent agent registrations. Multi-user use still needs per-user or
tenant agent home roots at deployment boundary.

### External Integration Readiness

External systems should treat Agent as the profile/home owner and call application
services. They should not write agent home files directly.

### Remediation Checklist

- [x] Split HTTP presenter/DTO code from profile/home command endpoints.
- [x] Split HTTP request models and request-to-application input conversion from route endpoints.
- [x] Split Agent HTTP service lookup, resolution construction, and error mapping from route endpoints.
- [x] Split CLI payload construction from command wiring and reuse the application Settings import rule.
- [x] Split CLI command registration into profile and home command modules.
- [x] Split profile sync and profile state CLI command groups from the main profile CLI command module.
- [x] Split registration input to AgentProfile construction from the application service.
- [x] Split update input to domain update kwargs conversion from the application service.
- [x] Split Agent application model DTOs by profile lifecycle and home lifecycle behind a thin export surface.
- [x] Split home registry/config/file operations from the application service.
- [x] Split Agent profile resolution by LLM, Tool, Access, and Authorization source.
- [x] Split Agent domain value objects behind a thin export surface.
- [x] Split Agent home config IO and payload projection behind a thin entrypoint.
- [x] Split Agent profile lifecycle orchestration from the public application facade.
- [x] Split Agent home use-case orchestration from the profile application facade.
- [x] Retire Agent runtime preference compatibility alias and legacy-shaped helper naming.
- [x] Add Context Workspace agent.home node generation tests from Agent owner facts.
- [x] Add no-hidden-prompt-input test for agent home files: only selected nodes enter LLM request.
- [x] Add atomic write/isolation tests for home config and registry updates.

### Watchlist

- Watch `AgentHomeUseCases` for accumulation of unrelated home IO adapter details.
  Home IO remains in `application/home_operations.py`; profile lifecycle remains in
  `application/profile_use_cases.py`; `AgentApplicationService` remains the public
  facade.

### Verification

- `PYTHONPATH=src pytest -q tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short` -> 11 passed.
- `python -m ruff check src/crxzipple/modules/agent/infrastructure/home_config.py src/crxzipple/modules/agent/infrastructure/home_registry.py tests/unit/test_agent_home_persistence.py --ignore F401,I001,E501` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_agent_home_scaffold.py tests/unit/test_agent_home_persistence.py tests/unit/test_context_workspace_agent_adapter.py tests/unit/test_agent_http.py --tb=short` -> 23 passed.
- `python -m ruff check src/crxzipple/modules/agent/interfaces/http.py src/crxzipple/modules/agent/interfaces/http_models.py src/crxzipple/modules/agent/interfaces/http_requests.py` -> passed.
- `python -m ruff check src/crxzipple/modules/agent/application src/crxzipple/modules/agent/interfaces/http.py src/crxzipple/modules/agent/interfaces/http_models.py src/crxzipple/modules/agent/interfaces/http_requests.py src/crxzipple/modules/agent/__init__.py` -> passed.
- `python -m ruff check tests/unit/test_agent_http.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --ignore F403,F405` -> passed.
- `python -m compileall -q src/crxzipple/modules/agent` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_agent_http.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1` -> 23 passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/agent/application/services.py src/crxzipple/modules/agent/application/home_runtime.py src/crxzipple/modules/agent/application/models.py src/crxzipple/modules/agent/application/event_payloads.py src/crxzipple/modules/agent/interfaces/http.py src/crxzipple/modules/agent/interfaces/http_models.py src/crxzipple/modules/agent/interfaces/http_requests.py` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/application/services.py src/crxzipple/modules/agent/application/home_runtime.py src/crxzipple/modules/agent/application/models.py src/crxzipple/modules/agent/application/event_payloads.py` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_agent_http.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1` -> 23 passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/agent/application/resolution.py src/crxzipple/modules/agent/application/resolution_models.py src/crxzipple/modules/agent/application/resolution_values.py src/crxzipple/modules/agent/application/resolution_authorization.py src/crxzipple/modules/agent/application/services.py src/crxzipple/modules/agent/application/home_runtime.py src/crxzipple/modules/agent/application/models.py src/crxzipple/modules/agent/application/event_payloads.py src/crxzipple/modules/agent/interfaces/http.py src/crxzipple/modules/agent/interfaces/http_models.py src/crxzipple/modules/agent/interfaces/http_requests.py` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/application/resolution.py src/crxzipple/modules/agent/application/resolution_models.py src/crxzipple/modules/agent/application/resolution_values.py src/crxzipple/modules/agent/application/resolution_authorization.py src/crxzipple/modules/agent/application/services.py src/crxzipple/modules/agent/application/home_runtime.py src/crxzipple/modules/agent/application/models.py src/crxzipple/modules/agent/application/event_payloads.py` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_agent_http.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1` -> 23 passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/agent/application/resolution.py src/crxzipple/modules/agent/application/resolution_models.py src/crxzipple/modules/agent/application/resolution_values.py src/crxzipple/modules/agent/application/resolution_authorization.py src/crxzipple/modules/agent/application/services.py src/crxzipple/modules/agent/application/home_runtime.py src/crxzipple/modules/agent/application/models.py src/crxzipple/modules/agent/application/event_payloads.py src/crxzipple/modules/agent/interfaces/http.py src/crxzipple/modules/agent/interfaces/http_models.py src/crxzipple/modules/agent/interfaces/http_resolution_models.py src/crxzipple/modules/agent/interfaces/http_requests.py` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/application/resolution.py src/crxzipple/modules/agent/application/resolution_models.py src/crxzipple/modules/agent/application/resolution_values.py src/crxzipple/modules/agent/application/resolution_authorization.py src/crxzipple/modules/agent/application/services.py src/crxzipple/modules/agent/application/home_runtime.py src/crxzipple/modules/agent/application/models.py src/crxzipple/modules/agent/application/event_payloads.py src/crxzipple/modules/agent/interfaces/http.py src/crxzipple/modules/agent/interfaces/http_models.py src/crxzipple/modules/agent/interfaces/http_resolution_models.py src/crxzipple/modules/agent/interfaces/http_requests.py` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_agent_http.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1` -> 23 passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/agent/application src/crxzipple/modules/agent/interfaces` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/application src/crxzipple/modules/agent/interfaces` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_agent_http.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1` -> 23 passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/agent/application src/crxzipple/modules/agent/interfaces` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/application src/crxzipple/modules/agent/interfaces` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_agent_cli.py tests/unit/test_agent_http.py tests/unit/test_agent_settings_integration.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1` -> 35 passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/agent/domain src/crxzipple/modules/agent/application src/crxzipple/modules/agent/interfaces` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/domain src/crxzipple/modules/agent/application src/crxzipple/modules/agent/interfaces` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_agent_cli.py tests/unit/test_agent_http.py tests/unit/test_agent_settings_integration.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1` -> 35 passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/agent/domain src/crxzipple/modules/agent/application src/crxzipple/modules/agent/infrastructure src/crxzipple/modules/agent/interfaces` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/domain src/crxzipple/modules/agent/application src/crxzipple/modules/agent/infrastructure src/crxzipple/modules/agent/interfaces` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_agent_cli.py tests/unit/test_agent_http.py tests/unit/test_agent_settings_integration.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1` -> 35 passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/agent/interfaces/cli_profile_commands.py src/crxzipple/modules/agent/interfaces/cli_profile_sync_commands.py src/crxzipple/modules/agent/interfaces/cli_profile_state_commands.py src/crxzipple/modules/agent/interfaces/cli.py` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/interfaces/cli_profile_commands.py src/crxzipple/modules/agent/interfaces/cli_profile_sync_commands.py src/crxzipple/modules/agent/interfaces/cli_profile_state_commands.py src/crxzipple/modules/agent/interfaces/cli.py` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_agent_cli.py tests/unit/test_agent_http.py tests/unit/test_agent_settings_integration.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1` -> 35 passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/agent/domain src/crxzipple/modules/agent/application src/crxzipple/modules/agent/infrastructure src/crxzipple/modules/agent/interfaces` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/domain src/crxzipple/modules/agent/application src/crxzipple/modules/agent/infrastructure src/crxzipple/modules/agent/interfaces` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_agent_cli.py tests/unit/test_agent_http.py tests/unit/test_agent_settings_integration.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1` -> 35 passed.
- `PYTHONPATH=src pytest -q tests/unit/test_module_architecture_guards.py --tb=short --maxfail=1` -> 18 passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/agent/domain src/crxzipple/modules/agent/application src/crxzipple/modules/agent/infrastructure src/crxzipple/modules/agent/interfaces` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/domain src/crxzipple/modules/agent/application src/crxzipple/modules/agent/infrastructure src/crxzipple/modules/agent/interfaces` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_agent_cli.py tests/unit/test_agent_http.py tests/unit/test_agent_settings_integration.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1` -> 35 passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/agent/application src/crxzipple/modules/agent/interfaces` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/application src/crxzipple/modules/agent/interfaces` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_agent_cli.py tests/unit/test_agent_http.py tests/unit/test_agent_settings_integration.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1` -> 35 passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/agent/application src/crxzipple/modules/agent/interfaces` -> passed.
- `PYTHONPATH=src ruff check tests/unit/test_agent_cli.py tests/unit/test_agent_http.py tests/unit/test_agent_settings_integration.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --ignore F403,F405` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/application src/crxzipple/modules/agent/interfaces` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_agent_cli.py tests/unit/test_agent_http.py tests/unit/test_agent_settings_integration.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1` -> 35 passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/agent/application src/crxzipple/modules/agent/interfaces` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/application src/crxzipple/modules/agent/interfaces` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_agent_cli.py tests/unit/test_agent_http.py tests/unit/test_agent_settings_integration.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1` -> 35 passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/agent/application src/crxzipple/modules/agent/interfaces` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/application src/crxzipple/modules/agent/interfaces` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_agent_cli.py tests/unit/test_agent_http.py tests/unit/test_agent_settings_integration.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1` -> 35 passed.
- 2026-06-26 profile/home model split:
  `PYTHONPATH=src ruff check src/crxzipple/modules/agent/application src/crxzipple/modules/agent/interfaces`
  -> passed.
  `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/application src/crxzipple/modules/agent/interfaces`
  -> passed.
  `PYTHONPATH=src pytest -q tests/unit/test_agent_cli.py tests/unit/test_agent_http.py tests/unit/test_agent_settings_integration.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1`
  -> 35 passed.
- 2026-06-26 runtime preference compatibility cleanup:
  `PYTHONPATH=src ruff check src/crxzipple/modules/agent/domain/runtime_preferences.py src/crxzipple/modules/agent/interfaces/dto.py src/crxzipple/modules/agent/infrastructure/home_config_payload_helpers.py src/crxzipple/modules/agent/infrastructure/home_config_payloads.py`
  -> passed.
  `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/agent/domain/runtime_preferences.py src/crxzipple/modules/agent/interfaces/dto.py src/crxzipple/modules/agent/infrastructure/home_config_payload_helpers.py src/crxzipple/modules/agent/infrastructure/home_config_payloads.py`
  -> passed.
  `PYTHONPATH=src pytest -q tests/unit/test_agent_cli.py tests/unit/test_agent_http.py tests/unit/test_agent_settings_integration.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1`
  -> 35 passed.

### Notes From Current Remediation

- `interfaces/http.py` keeps profile routes, container lookup, service calls, and HTTP status mapping; `interfaces/http_home_routes.py` owns profile-home migration/sync/export/inspect/update endpoints.
- `interfaces/cli.py` keeps Typer app composition only; profile command registration
  lives in `interfaces/cli_profile_commands.py`, and home command registration lives
  in `interfaces/cli_home_commands.py`.
- Response DTOs and presenter functions live in `interfaces/http_models.py`.
- Resolution endpoint response DTOs and presenter functions live in `interfaces/http_resolution_models.py`.
- Request DTOs live in `interfaces/http_request_models.py`.
- Request-to-application input mapping lives in `interfaces/http_requests.py`, with shared private value mappers for register/update paths.
- CLI payload construction lives in `interfaces/cli_payloads.py`, and both CLI/HTTP profile sync paths delegate Settings profile import to `application/settings_integration.py`.
- Registration input to `AgentProfile` construction lives in `application/profile_factory.py`.
- Update input to domain update kwargs conversion lives in `application/profile_updates.py`.
- Application DTOs are split into `application/profile_models.py` and
  `application/home_models.py`; `application/models.py` remains the public export
  surface.
- Profile event payload/action coercion helpers live in `application/event_payloads.py`.
- Home root/default directory and runtime preference normalization rules live in `application/home_runtime.py`.
- Home registry/config/scaffold/migration/file operations live in `application/home_operations.py`.
- Resolution DTOs live in `application/resolution_models.py`.
- Resolution value coercion helpers live in `application/resolution_values.py`.
- Authorization policy-to-agent/tool grant projection rules live in `application/resolution_authorization.py`.
- LLM route resolution lives in `application/resolution_llm.py`.
- Tool catalog resolution lives in `application/resolution_tools.py`.
- Access readiness resolution lives in `application/resolution_access.py`.
- Authorization policy query coordination lives in `application/resolution_authorization_query.py`.
- Agent domain value object implementation modules are `domain/identity_policy.py`,
  `domain/llm_policies.py`, `domain/execution_policy.py`,
  `domain/memory_binding.py`, `domain/runtime_preferences.py`, and
  `domain/value_common.py`; `domain/value_objects.py` remains the public export surface.
- Agent home config implementation modules are `infrastructure/home_config_io.py`,
  `infrastructure/home_config_payloads.py`, and
  `infrastructure/home_config_payload_helpers.py`; `infrastructure/home_config.py`
  remains the public entrypoint.
