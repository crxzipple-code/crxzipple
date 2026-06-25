# Module Audit: agent

## Verdict

Medium risk. Agent owns profile and home/workspace config. The module is relatively compact but has a large HTTP surface for its size.

## Evidence

- 19 Python files, about 4613 lines.
- Large files include `interfaces/http.py` (914), `application/services.py` (833), `application/resolution.py` (708), `interfaces/cli.py` (391).

## Findings

- Agent should own profile/home registry facts and expose resolution services.
- HTTP interface is heavy and may include application decisions.
- Agent must not directly execute runs or mutate runtime queues.
- Agent home file integration with Context Workspace must remain via owner adapter.

## Launch Risks

- Profile mutation can affect runtime prompt/context behavior unexpectedly.
- Workspace/home config loading can become a hidden source of model-visible input.

## Recommendations

- Split profile CRUD, home registry resolution, and workspace config resolution.
- Add tests for Context Workspace agent.home node generation from Agent owner facts.
- Move DTO assembly out of HTTP if it continues to grow.

## Detailed Pass 1

### Files Reviewed

- `application/services.py`
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

`interfaces/http.py` is 914 lines and `application/services.py` is 833 lines. For a
medium-sized module, the HTTP surface is large and likely mixes DTO presentation with
application behavior.

`application/resolution.py` is 708 lines and is important because it determines which
agent profile/home/workspace facts are selected for runtime. This must stay explicit
and test-covered because it influences model-visible context through Context
Workspace.

`infrastructure/home_config.py`, `home_registry.py`, `home_files.py`,
`home_migration.py`, and `home_scaffold.py` are well-scoped infrastructure concerns.
`home_config.py` and `home_registry.py` now write through same-directory temporary
files and atomic replacement; registry read-modify-write paths are guarded by a file
lock.

### Boundary Cleanliness

Agent owns profile and home/workspace configuration. It does not execute runs,
schedule queues, or mutate orchestration runtime state.

Risk pattern:

- Agent home files can become hidden model-visible prompt input unless Context
  Workspace explicitly selects/render them.
- Settings integration must remain governance/entry-point integration; Agent remains
  owner of agent profile facts.
- HTTP can accidentally expose low-level home file mutation without application
  invariants.

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
- [x] Add Context Workspace agent.home node generation tests from Agent owner facts.
- [x] Add no-hidden-prompt-input test for agent home files: only selected nodes enter LLM request.
- [x] Add atomic write/isolation tests for home config and registry updates.

### Watchlist

- Split `AgentApplicationService` if profile CRUD, home sync, export, migration, and file update paths continue growing.

### Verification

- `PYTHONPATH=src pytest -q tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_context_workspace_agent_adapter.py --tb=short` -> 11 passed.
- `python -m ruff check src/crxzipple/modules/agent/infrastructure/home_config.py src/crxzipple/modules/agent/infrastructure/home_registry.py tests/unit/test_agent_home_persistence.py --ignore F401,I001,E501` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_agent_home_scaffold.py tests/unit/test_agent_home_persistence.py tests/unit/test_context_workspace_agent_adapter.py tests/unit/test_agent_http.py --tb=short` -> 23 passed.
- `python -m ruff check src/crxzipple/modules/agent/interfaces/http.py src/crxzipple/modules/agent/interfaces/http_models.py src/crxzipple/modules/agent/interfaces/dto.py --ignore F401,I001,E501` -> passed.

### Notes From Current Remediation

- `interfaces/http.py` now keeps request models, routes, container lookup, and request-to-application input mapping.
- Response DTOs and presenter functions moved to `interfaces/http_models.py`; `interfaces/http.py` dropped from 914 lines to 549 lines.
