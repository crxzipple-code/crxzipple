# Settings Governance Construction Checklist 2026-05-07

> 2026-05-08 corrective note: 本文档记录 2026-05-07 的施工事实，但关于
> Agent / LLM / Channel profile 是否迁入 Settings 作为最终真相源的判断已经部分过期。
> 当前 owner/truth-source 和整改任务以
> `docs/reports/settings-module-boundary-complexity-review-20260508.md` 为准。
> 不要继续扩展“Settings 写完整 profile，再同步回模块 runtime”的路径。

## Decision

Settings owns configuration governance truth. Modules keep their domain/runtime
models and consume effective configuration through shared contracts.

The target shape is:

- Settings owns config resources, versions, overrides, validation, publishing,
  rollback, and settings action audit.
- Shared owns config contracts consumed by modules.
- Modules own domain interpretation and runtime behavior.
- Access owns credential/runtime authorization lifecycle, readiness, setup
  sessions, grants, login/logout/revoke/refresh, and access audit.
- Operations owns runtime observation and operational actions. It must not own
  configuration truth.

## Non-Goals

- Do not move module domain entities into Settings.
- Do not make Settings call module private repositories as the source of truth.
- Do not keep UI-only aggregation as the final architecture.
- Do not add compatibility branches that preserve old governance flows forever.

## Current Status

2026-05-07 construction pass:

- Shared contracts, Settings core, persistence schema, HTTP wiring, container
  bootstrap, and LLM profile consumption are implemented.
- The Settings HTTP interface now uses the Settings application services from
  the container. It no longer owns an in-interface fallback/read model.
- Startup imports `core.config.Settings` as Settings-owned resources without
  creating operator audit noise. Explicit Settings actions still audit each
  attempt.
- Settings effective materialization is now the backend path for LLM, Agent,
  Tool, Skill, Access, Channel, Memory, Runtime, and authorization bootstrap
  consumption.
- Container build materializes Settings before module boot and exposes
  runtime bootstrap snapshots for module/runtime readers.
- Production code no longer directly consumes the scanned legacy
  `core.config.Settings` fields for agent/LLM/channel profiles, tool
  providers/roots/enablement, skill enablement, access config, memory defaults,
  authorization defaults, or orchestration/tool runtime defaults.
- LLM and Agent profile registration/enabled-state entrypoints now create or
  update Settings resources and then sync module runtime indexes.
- Access config-like actions now route through Settings actions; Access still
  owns runtime authorization lifecycle, readiness, setup, resolution, and audit.

2026-05-08 review correction:

- Agent profile full payload in Settings is now treated as extra complexity, not
  a target end state.
- Generic Settings actions must not bypass owner module application services for
  module-owned entities.
- Profile-related work should first classify the kind, then either keep it
  Settings-owned config or move it back to owner module truth with a Settings
  governance overlay.

## Stage S0: Guardrails

- [x] Add shared settings contracts before module integrations.
- [x] Keep module domain objects intact.
- [x] Keep current `core.config.Settings` as bootstrap/import source only.
- [x] All Settings HTTP writes go through Settings actions.
- [x] All Settings HTTP actions write audit records.
- [x] All effective config reads expose source and override trace.

Acceptance:

- [x] There is one documented settings ownership model.
- [x] No new module UI/API writes profile/provider/enablement truth directly.

## Stage S1: Shared Contracts

Files:

- `src/crxzipple/shared/settings.py`
- `tests/unit/test_settings_contracts.py`

Tasks:

- [x] Define `SettingsResourceRef`.
- [x] Define `ConfigSource`.
- [x] Define `ConfigResolution`.
- [x] Define `EffectiveSettingsProvider` protocol.
- [x] Define config DTOs:
  - [x] `LlmProfileConfig`
  - [x] `AgentProfileConfig`
  - [x] `ChannelProfileConfig`
  - [x] `ToolProviderConfig`
  - [x] `ToolRootConfig`
  - [x] `ToolEnablementConfig`
  - [x] `SkillEnablementConfig`
  - [x] `AccessConfig`
  - [x] `MemoryConfig`
  - [x] `RuntimeDefaultsConfig`
  - [x] `EnvironmentOverrideConfig`

Acceptance:

- [x] Contracts have no dependency on module domain entities.
- [x] DTOs can round-trip via payload helpers or simple dataclass construction.
- [x] Unit tests cover resource refs, resolution trace, and effective values.

## Stage S2: Settings Module Core

Files:

- `src/crxzipple/modules/settings/__init__.py`
- `src/crxzipple/modules/settings/domain/*`
- `src/crxzipple/modules/settings/application/*`
- `tests/unit/test_settings_module.py`

Tasks:

- [x] Add `SettingsResource`.
- [x] Add `SettingsResourceVersion`.
- [x] Add `SettingsOverride`.
- [x] Add `SettingsEffectiveSnapshot`.
- [x] Add `SettingsActionAudit`.
- [x] Add repository protocols.
- [x] Add `SettingsQueryService`.
- [x] Add `SettingsActionService`.
- [x] Add effective resolution service.
- [x] Add bootstrap importer interface for legacy `core.config.Settings`.

Acceptance:

- [x] Resources can be created, updated, enabled, disabled, published, and
  rolled back in memory.
- [x] Effective resolution returns a value plus sources and overrides.
- [x] Validation failures are represented without mutating published state.

## Stage S3: Persistence

Files:

- `src/crxzipple/modules/settings/infrastructure/persistence/*`
- `alembic/versions/0043_settings_governance.py`
- `tests/unit/test_settings_persistence.py`

Tables:

- [x] `settings_resources`
- [x] `settings_resource_versions`
- [x] `settings_effective_snapshots`
- [x] `settings_overrides`
- [x] `settings_validation_results`
- [x] `settings_action_audits`

Acceptance:

- [x] Alembic migration upgrades cleanly.
- [x] Repository stores versions and latest published snapshot.
- [x] Action audit persists reason, actor, risk, and redacted metadata.

## Stage S4: HTTP and Container Wiring

Files:

- `src/crxzipple/modules/settings/interfaces/http.py`
- `src/crxzipple/bootstrap/container.py`
- `src/crxzipple/interfaces/http/router.py`
- `tests/unit/test_settings_http.py`

Tasks:

- [x] Add Settings services to `AppContainer`.
- [x] Register Settings router under `/settings` and `/ui/settings`.
- [x] Add list/get/detail endpoints.
- [x] Add action endpoint with dry-run, validate, publish, rollback, enable,
  disable.
- [x] Add bootstrap import endpoint or startup importer hook.

Acceptance:

- [x] `GET /ui/settings` returns resource counts and health.
- [x] `GET /ui/settings/{kind}` returns resources with effective config.
- [x] Action endpoint audits every write attempt.

## Stage S5: Module Consumption

LLM:

- [x] Import `config/llm_profiles/*` into `LlmProfileConfig`.
- [x] Keep `llm_profiles` as runtime index/cache while Settings is truth.
- [x] Replace direct governance writes with Settings actions.
- [x] Keep `LlmProfile` as LLM runtime/domain object.
- [x] Sync Settings materialized LLM profiles into the LLM runtime index during
  container boot when the runtime schema is ready.
- [x] HTTP/CLI profile registration writes Settings-owned resources before
  syncing the LLM runtime index.

Agent:

- [x] Import `config/agent_profiles` and agent home config into
  `AgentProfileConfig`.
- [x] Keep agent home as runtime/materialized files.
- [x] Move profile enablement/routing/runtime preference writes to Settings.
- [x] Boot Agent runtime profiles from Settings materialization.
- [x] HTTP/CLI profile registration and enable/disable write Settings-owned
  resources before syncing Agent runtime state.

Channel:

- [x] Add Settings-backed materialization for channel profiles.
- [x] Keep runtime registry and interactions in Channels.
- [x] Move channel profile/account profile writes to Settings.
- [x] Boot channel profile runtime state from materialized Settings payloads.
- [x] No Channel HTTP/Operations config action writes channel profile truth
  directly; Channel service upserts are runtime materialization.

Tool:

- [x] Move OpenAPI/MCP provider config to `ToolProviderConfig`.
- [x] Move local roots to `ToolRootConfig`.
- [x] Add `ToolEnablementConfig`.
- [x] Apply enablement after discovery for local, OpenAPI, and MCP tools.
- [x] Boot local/OpenAPI/MCP discovery providers from materialized Settings
  config.
- [x] Tool HTTP/CLI root views read the materialized tool bootstrap snapshot.
- [x] Tool discovery/runtime gateways apply Settings enablement without owning
  enablement writes.

Skill:

- [x] Add `SkillEnablementConfig`.
- [x] Keep package discovery/validation/install/read in Skills.
- [x] Skill manager adapter filters availability from Settings enablement
  while package discovery/read/validate/install remain in Skills.

Memory:

- [x] Move retrieval/vector/watch defaults to `MemoryConfig`.
- [x] Inject effective memory config into memory services.

Runtime:

- [x] Move orchestration/tool worker defaults to `RuntimeDefaultsConfig`.
- [x] Inject effective runtime defaults during container build.
- [x] Operations source read model receives runtime lease/heartbeat from the
  materialized runtime bootstrap snapshot.

Acceptance:

- [x] No module has a new direct config governance write path.
- [x] All modules can boot from effective settings.
- [x] LLM, Tool, Channel, Memory, and Runtime can boot from effective settings.
- [x] Agent, Skill, Access, and authorization defaults can boot from effective
  settings.
- [x] Current bootstrap files/env still import as initial settings resources.

## Stage S6: Access Split

Settings-owned:

- [x] Access asset declarations.
- [x] Credential binding declarations.
- [x] Consumer binding declarations.
- [x] Authorization policy configuration.
- [x] Provider/scope/permission enablement.

Access-owned:

- [x] Credential resolution.
- [x] Secret material handling.
- [x] Setup session.
- [x] Runtime grant.
- [x] Login/logout/revoke/refresh.
- [x] Readiness and access audit.

Tasks:

- [x] Move config-like Access writes from Access actions to Settings actions.
- [x] Keep runtime lifecycle actions in Access.
- [x] Remove transitional `/ui/settings/access-assets` reuse once Settings
  resources cover access config.

Acceptance:

- [x] Access page can operate connection lifecycle without owning config truth.
- [x] Settings page can govern access config resources.
- [x] Operations page can observe both without writing config truth directly.

## Stage S7: Operations Boundary

Tasks:

- [x] Operations read models can show settings health and config drift.
- [x] Operations runtime actions remain cancel/retry/drain/prune/replay/setup.
- [x] Config change actions route to Settings action service.

Acceptance:

- [x] No operations action mutates settings resources except through Settings.
- [x] Operations audit and Settings audit stay separate.

## Verification

- [x] `PYTHONPATH=src pytest -q tests/unit/test_settings_contracts.py`
- [x] `PYTHONPATH=src pytest -q tests/unit/test_settings_module.py`
- [x] `PYTHONPATH=src pytest -q tests/unit/test_settings_persistence.py`
- [x] `PYTHONPATH=src pytest -q tests/unit/test_settings_http.py`
- [x] `PYTHONPATH=src pytest -q tests/unit/test_llm.py tests/unit/test_llm_http.py`
- [x] `PYTHONPATH=src pytest -q tests/unit/test_settings_contracts.py tests/unit/test_settings_module.py tests/unit/test_settings_materialization.py tests/unit/test_settings_persistence.py tests/unit/test_settings_http.py tests/unit/test_tool_settings_integration.py tests/unit/test_tool_providers.py tests/unit/test_tool_http.py tests/unit/test_tool_cli.py tests/unit/test_channel_memory_runtime_settings_integration.py tests/unit/test_channels.py tests/unit/test_llm.py tests/unit/test_llm_http.py tests/unit/test_llm_settings_integration.py tests/unit/test_ui_access_http.py tests/unit/test_http.py tests/unit/test_operations_observation.py`
- [x] `PYTHONPATH=src pytest -q tests/unit/test_tool_http.py tests/unit/test_tool_providers.py`
- [x] `PYTHONPATH=src pytest -q tests/unit/test_access_actions.py tests/unit/test_access_persistence.py`
- [x] `PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py`
- [x] `PYTHONPATH=src pytest -q tests/unit/test_settings_contracts.py tests/unit/test_settings_module.py tests/unit/test_settings_materialization.py tests/unit/test_settings_persistence.py tests/unit/test_settings_http.py tests/unit/test_agent_settings_integration.py tests/unit/test_agent_http.py tests/unit/test_agent_cli.py tests/unit/test_tool_settings_integration.py tests/unit/test_skill_settings_integration.py tests/unit/test_tool_providers.py tests/unit/test_tool_http.py tests/unit/test_tool_cli.py tests/unit/test_channel_memory_runtime_settings_integration.py tests/unit/test_channels.py tests/unit/test_llm.py tests/unit/test_llm_http.py tests/unit/test_llm_cli.py tests/unit/test_llm_settings_integration.py tests/unit/test_access_actions.py tests/unit/test_access_http.py tests/unit/test_ui_access_http.py tests/unit/test_access_policies.py tests/unit/test_access_persistence.py tests/unit/test_authorization.py tests/unit/test_operations_observation.py tests/unit/test_http.py`
- [x] `PYTHONPATH=src ruff check` for touched Settings/materializer/module
  integration/container/interface files.
- [x] `rg` scan confirms no production direct reads for migrated
  agent/LLM/channel/tool/skill/access/authorization/memory/runtime fields.

## Agent Work Split

Agent A owns:

- `src/crxzipple/shared/settings.py`
- `src/crxzipple/modules/settings/domain/*`
- `src/crxzipple/modules/settings/application/*`
- `tests/unit/test_settings_contracts.py`
- `tests/unit/test_settings_module.py`

Agent B owns:

- `src/crxzipple/modules/settings/infrastructure/persistence/*`
- `alembic/versions/0043_settings_governance.py`
- `tests/unit/test_settings_persistence.py`

Agent C owns:

- `src/crxzipple/modules/settings/interfaces/http.py`
- settings router registration
- settings container wiring
- `tests/unit/test_settings_http.py`

Agent D owns:

- first module integration report and minimal adapter patch for one module only,
  preferably LLM, without changing Tool/Agent/Channel files in the same pass.
