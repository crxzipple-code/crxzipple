# Module Audit: settings

## Verdict

Medium-high risk. Settings is a governance surface, not owner of every module's truth. Current HTTP interface is very large and needs strict owner-source discipline.

## Evidence

- 61 Python files, about 9170 lines.
- Large files include `application/materialization.py` (205). `application/setup.py` is now a 35-line public setup entrypoint over focused resource collection, import, seed, result, database, Access seed, and core seed modules. `domain/entities.py` is now an 18-line export surface over focused resource/version/override/snapshot/audit aggregate modules. `application/materialization.py` now delegates warning DTOs and payload/profile/tool/access normalization to focused modules. `interfaces/http_actions.py` is now a 55-line HTTP boundary over focused execution/mutation/validation helpers. `application/services.py` is now a 192-line action-service facade, `application/resource_actions.py` is now a 126-line resource-action facade, and `interfaces/http.py` is now a 147-line router.

## Findings

- Settings-owned config vs module-owned entity boundary is well documented, but large HTTP/application files increase drift risk.
- Materialization is a valuable pattern and should remain typed.
- Settings must not write Agent/LLM/Channel/Tool facts directly unless the resource is explicitly Settings-owned.

## Launch Risks

- Misclassified Settings actions can corrupt owner module truth.
- UI may expose fake or stale module health if Settings tries to become an overview.
- Runtime defaults need safe apply/restart semantics.

## Recommendations

- Split HTTP router by resource family and action type.
- Require every settings resource to declare owner, truth source, write path, and runtime apply behavior.
- Add tests ensuring module-owned actions dispatch to owner services.
- Keep env as seed/import only, not live truth.

## Detailed Pass 1

### Files Reviewed

- `interfaces/http.py`
- `application/services.py`
- `application/setup.py`
- `application/materialization.py`
- `application/in_memory.py`
- `domain/entities.py`
- `domain/value_objects.py`
- `infrastructure/persistence/repositories.py`
- `infrastructure/persistence/domain_repositories.py`
- `infrastructure/persistence/domain_resource_repository.py`
- `infrastructure/persistence/domain_version_repository.py`
- `infrastructure/persistence/domain_override_repository.py`
- `infrastructure/persistence/domain_snapshot_repository.py`
- `infrastructure/persistence/domain_action_audit_repository.py`
- `infrastructure/persistence/models.py`

### File-Level Assessment

`interfaces/http.py` is now 147 lines and contains overview/list/detail endpoints,
kind/resource action entrypoints, and bootstrap import orchestration only. Settings
action request DTOs now live in `interfaces/http_action_models.py`, response projection
in `interfaces/http_action_responses.py`, request helper/validation/error-audit helpers
in `interfaces/http_action_helpers.py`, and action request execution in
`interfaces/http_action_execution.py`. Create/update mutation handlers live in
`interfaces/http_action_mutations.py`, dry-run/validation handling lives in
`interfaces/http_action_validation.py`, and `interfaces/http_actions.py` is now the
HTTP boundary plus error mapping. Container service lookup and kind normalization moved
to `interfaces/http_common.py`.

`application/setup.py` is 35 lines and `application/services.py` is 192 lines. The
application layer is still significant but now more clearly separated between
Settings-owned resource action orchestration, effective resolution, query/read
operations, setup/bootstrap, and shared service helpers.
Bootstrap resource collection, explicit Settings import, startup seed, bootstrap
result DTOs, and seed payload comparison now live in focused setup modules.
Database URL summary, fingerprinting, query-key extraction, and URL redaction for
environment bootstrap now live in `application/setup_database.py`, keeping setup
resource collection separate from URL parsing and secret redaction details.
Access bootstrap credential resource declarations now live in
`application/setup_access_resources.py`, keeping setup/import orchestration separate
from large static resource payloads.
Tool catalog, memory config, runtime defaults, and environment bootstrap resource
collectors now live in `application/setup_core_resources.py`, keeping setup/import
orchestration separate from Settings resource seed construction. In-memory settings
service bundle construction now lives in `application/service_bundle.py`, so bootstrap
setup no longer owns application service assembly details.
`application/services.py` no longer owns a private redaction implementation; audit
request metadata now delegates to the shared `application/redaction.py` helper used by
HTTP and read models, preventing Settings audit redaction rules from drifting across
surfaces.
Settings action result construction now lives in `application/action_results.py`.
Override create/update/enable/disable lifecycle now lives in
`application/override_actions.py`, and Settings action-attempt audit construction now
lives in `application/action_audit.py`. The main action service keeps the stable public
API and delegates the override sub-lifecycle instead of owning both resource-version
and override mutation branches.
Resource-version construction, publish/supersede sequencing, resource publish state,
snapshot creation, and snapshot persistence now live in
`application/resource_versioning.py`, keeping version mechanics out of the action
service coordinator.
Resource create/update orchestration now lives in
`application/resource_definition_actions.py`, publish/rollback orchestration now lives
in `application/resource_publication_actions.py`, and resource enable/disable plus
sub-action delegation live in `application/resource_actions.py`. `SettingsActionService`
is the stable public facade for resource actions, override actions, and operator audit
helpers.
Effective config resolution now lives in `application/resolution_service.py`,
query/read operations live in `application/query_service.py`, and shared resource
lookup/version/merge helpers live in `application/service_common.py`. `services.py`
remains the stable import surface for `SettingsActionService`,
`SettingsEffectiveResolutionService`, and `SettingsQueryService`, but no longer owns
all three implementations.

`domain/entities.py` is now only the stable public export surface for Settings
domain aggregates. Resource lifecycle, resource version lifecycle, environment
override lifecycle, effective snapshot projection, action audit lifecycle, and shared
entity normalization/status coercion now live in focused domain modules. This keeps
the Settings domain model aligned with the owner-truth boundary without forcing
application/infrastructure imports to churn.

`application/materialization.py` is 205 lines and provides a useful effective config
materialization seam. Materialization warnings live in
`application/materialization_models.py`; legacy profile payload normalization,
Tool provider/root normalization, Access declaration normalization, and shared default
id helpers live in `application/materialization_payloads.py`. The legacy profile
helpers remain quarantined as materialization payload adapters and must not blur owner
truth: module-owned profiles belong to their owner modules.

Settings governance persistence is now split between record DTOs, SQLAlchemy
model/record mappers, domain/repository mappers, and repository query/transaction
classes.
`infrastructure/persistence/repositories.py` is reduced to 459 lines and no longer
owns the mapping helpers used by the domain repository layer.
`domain_repositories.py` is reduced to a 74-line service assembly surface.
Concrete domain repositories now live by family in resource, version, override,
snapshot, and action-audit repository modules.

### Boundary Cleanliness

Settings is a governance surface and owner of explicitly Settings-owned config. It is
not the owner of Agent, LLM, Channel, Tool, Access, or Skill entity truth unless a
resource is explicitly classified as Settings-owned.

Risk pattern:

- HTTP action routing can bypass owner services if resource ownership is unclear.
- Runtime defaults can become hidden live truth if env/config/runtime apply rules are
  not explicit.
- Materialization can preserve legacy payloads in a way that obscures current owner
  boundaries.

### Lifecycle Clarity

Settings lifecycle should be:

1. resource declaration identifies owner/truth/write path/apply behavior
2. settings resource version or override is created
3. effective config materializer computes typed config
4. owner module consumes config through assembly/application injection
5. action audit records reason/result
6. runtime apply/restart behavior is explicit

This is documented, but HTTP/application structure makes it hard to prove.

### Persistence And Efficiency

Settings persistence appears structured around resource versions, overrides, and
audit. The mapper and repository-family splits reduce infrastructure coupling. The
remaining maintainability risk is query-budget coverage for bulk resource/version
lookups under larger Settings catalogs.

### Concurrency And Multi-User Readiness

Settings writes require optimistic versioning and audit. Multi-user configuration
changes need conflict visibility and safe rollback semantics.

### External Integration Readiness

External systems should consume typed effective config or owner module APIs. They
should not call generic Settings actions for module-owned entity mutation.

### Remediation Checklist

- [x] Split `interfaces/http.py` into overview/detail, action execution, runtime defaults, audit, and presenter modules.
- [x] Add invariant test: every resource declares owner, truth source, write path, and runtime apply behavior.
- [x] Add tests that module-owned actions are directed to owner APIs and cannot mutate owner truth through Settings.
- [x] Add concurrent update/version conflict tests.
- [x] Keep env as seed/import only and test that it is not live runtime truth.

### Watchlist

- Remove or quarantine legacy materialization helpers after owner modules expose stable config ports for every remaining Settings-governed resource.

### Verification

- `PYTHONPATH=src pytest -q tests/unit/test_settings_application_read_models.py --tb=short` -> 4 passed.
- `python -m ruff check tests/unit/test_settings_application_read_models.py src/crxzipple/modules/settings/application/action_policy.py --ignore F401,I001,E501` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_settings_application_read_models.py tests/unit/test_settings_materialization.py::SettingsMaterializationTestCase::test_environment_snapshot_is_seeded_not_live_runtime_truth tests/unit/test_settings_http.py::SettingsHttpTestCase::test_module_owned_profile_actions_only_expose_non_write_operations --tb=short` -> 7 passed.
- `python -m ruff check src/crxzipple/modules/settings/application/action_policy.py tests/unit/test_settings_application_read_models.py tests/unit/test_settings_materialization.py --ignore F401,I001,E501` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_settings_module.py tests/unit/test_settings_http.py tests/unit/test_settings_application_read_models.py tests/unit/test_settings_materialization.py --tb=short` -> 39 passed.
- `python -m ruff check src/crxzipple/modules/settings/application/models.py src/crxzipple/modules/settings/application/services.py src/crxzipple/modules/settings/domain src/crxzipple/modules/settings/interfaces/http.py src/crxzipple/modules/settings/interfaces/http_actions.py src/crxzipple/modules/settings/interfaces/http_common.py tests/unit/test_settings_module.py tests/unit/test_settings_http.py tests/unit/test_settings_application_read_models.py tests/unit/test_settings_materialization.py --ignore F401,I001,E501` -> passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/settings/application/services.py src/crxzipple/modules/settings/application/redaction.py` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/settings/application/services.py src/crxzipple/modules/settings/application/redaction.py` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_settings_application_read_models.py tests/unit/test_settings_http.py tests/unit/test_settings_module.py tests/unit/test_settings_persistence.py` -> 34 passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/settings/application/setup.py src/crxzipple/modules/settings/application/setup_database.py tests/unit/test_settings_environment_setup.py` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/settings/application/setup.py src/crxzipple/modules/settings/application/setup_database.py` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_settings_environment_setup.py tests/unit/test_settings_module.py tests/unit/test_settings_materialization.py` -> 15 passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/settings/application/services.py src/crxzipple/modules/settings/application/action_results.py` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/settings/application/services.py src/crxzipple/modules/settings/application/action_results.py` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_settings_module.py tests/unit/test_settings_http.py tests/unit/test_settings_application_read_models.py tests/unit/test_settings_persistence.py tests/unit/test_settings_environment_setup.py tests/unit/test_settings_materialization.py` -> 44 passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/settings/application/services.py src/crxzipple/modules/settings/application/action_results.py src/crxzipple/modules/settings/application/service_common.py src/crxzipple/modules/settings/application/resolution_service.py src/crxzipple/modules/settings/application/query_service.py` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/settings/application/services.py src/crxzipple/modules/settings/application/action_results.py src/crxzipple/modules/settings/application/service_common.py src/crxzipple/modules/settings/application/resolution_service.py src/crxzipple/modules/settings/application/query_service.py` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_settings_module.py tests/unit/test_settings_http.py tests/unit/test_settings_application_read_models.py tests/unit/test_settings_persistence.py tests/unit/test_settings_environment_setup.py tests/unit/test_settings_materialization.py` -> 44 passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/settings/application/services.py src/crxzipple/modules/settings/application/action_results.py src/crxzipple/modules/settings/application/service_common.py src/crxzipple/modules/settings/application/resolution_service.py src/crxzipple/modules/settings/application/query_service.py src/crxzipple/modules/settings/application/setup.py src/crxzipple/modules/settings/application/setup_database.py src/crxzipple/modules/settings/application/setup_access_resources.py` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/settings/application/services.py src/crxzipple/modules/settings/application/action_results.py src/crxzipple/modules/settings/application/service_common.py src/crxzipple/modules/settings/application/resolution_service.py src/crxzipple/modules/settings/application/query_service.py src/crxzipple/modules/settings/application/setup.py src/crxzipple/modules/settings/application/setup_database.py src/crxzipple/modules/settings/application/setup_access_resources.py` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_settings_module.py tests/unit/test_settings_http.py tests/unit/test_settings_application_read_models.py tests/unit/test_settings_persistence.py tests/unit/test_settings_environment_setup.py tests/unit/test_settings_materialization.py` -> 44 passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/settings/application src/crxzipple/modules/settings/infrastructure/persistence/domain_repositories.py src/crxzipple/modules/settings/interfaces tests/unit/test_settings_module.py tests/unit/test_settings_http.py tests/unit/test_settings_application_read_models.py tests/unit/test_settings_persistence.py tests/unit/test_settings_environment_setup.py tests/unit/test_settings_materialization.py` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/settings/application src/crxzipple/modules/settings/infrastructure/persistence/domain_repositories.py src/crxzipple/modules/settings/interfaces` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_settings_module.py tests/unit/test_settings_http.py tests/unit/test_settings_application_read_models.py tests/unit/test_settings_persistence.py tests/unit/test_settings_environment_setup.py tests/unit/test_settings_materialization.py --tb=short --maxfail=1` -> 44 passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/settings/domain src/crxzipple/modules/settings/application src/crxzipple/modules/settings/infrastructure/persistence/domain_repositories.py src/crxzipple/modules/settings/interfaces tests/unit/test_settings_module.py tests/unit/test_settings_http.py tests/unit/test_settings_application_read_models.py tests/unit/test_settings_persistence.py tests/unit/test_settings_environment_setup.py tests/unit/test_settings_materialization.py` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/settings/domain src/crxzipple/modules/settings/application src/crxzipple/modules/settings/infrastructure/persistence/domain_repositories.py src/crxzipple/modules/settings/interfaces` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_settings_module.py tests/unit/test_settings_http.py tests/unit/test_settings_application_read_models.py tests/unit/test_settings_persistence.py tests/unit/test_settings_environment_setup.py tests/unit/test_settings_materialization.py --tb=short --maxfail=1` -> 44 passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/settings/application src/crxzipple/modules/settings/infrastructure/persistence/domain_repositories.py src/crxzipple/modules/settings/interfaces tests/unit/test_settings_module.py tests/unit/test_settings_http.py tests/unit/test_settings_application_read_models.py tests/unit/test_settings_persistence.py tests/unit/test_settings_environment_setup.py tests/unit/test_settings_materialization.py` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/settings/application src/crxzipple/modules/settings/infrastructure/persistence/domain_repositories.py src/crxzipple/modules/settings/interfaces` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_settings_module.py tests/unit/test_settings_http.py tests/unit/test_settings_application_read_models.py tests/unit/test_settings_persistence.py tests/unit/test_settings_environment_setup.py tests/unit/test_settings_materialization.py --tb=short --maxfail=1` -> 44 passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/settings/application src/crxzipple/modules/settings/infrastructure/persistence/domain_repositories.py src/crxzipple/modules/settings/interfaces tests/unit/test_settings_module.py tests/unit/test_settings_http.py tests/unit/test_settings_application_read_models.py tests/unit/test_settings_persistence.py tests/unit/test_settings_environment_setup.py tests/unit/test_settings_materialization.py` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/settings/application src/crxzipple/modules/settings/infrastructure/persistence/domain_repositories.py src/crxzipple/modules/settings/interfaces` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_settings_module.py tests/unit/test_settings_http.py tests/unit/test_settings_application_read_models.py tests/unit/test_settings_persistence.py tests/unit/test_settings_environment_setup.py tests/unit/test_settings_materialization.py --tb=short --maxfail=1` -> 44 passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/settings/domain src/crxzipple/modules/settings/application src/crxzipple/modules/settings/infrastructure/persistence src/crxzipple/modules/settings/interfaces tests/unit/test_settings_module.py tests/unit/test_settings_http.py tests/unit/test_settings_application_read_models.py tests/unit/test_settings_persistence.py tests/unit/test_settings_environment_setup.py tests/unit/test_settings_materialization.py` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/settings/domain src/crxzipple/modules/settings/application src/crxzipple/modules/settings/infrastructure/persistence src/crxzipple/modules/settings/interfaces` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_settings_module.py tests/unit/test_settings_http.py tests/unit/test_settings_application_read_models.py tests/unit/test_settings_persistence.py tests/unit/test_settings_environment_setup.py tests/unit/test_settings_materialization.py --tb=short --maxfail=1` -> 44 passed.

### Notes From Current Remediation

- `skill-catalog` now follows the same module-owned boundary as Agent/LLM/Channel profiles: Settings may present governance/readiness information, but write operations must go through Skills owner APIs.
- Settings write paths now accept `expected_active_version_id` for update/publish/rollback. Stale mutations fail with `SettingsConflictError`, return HTTP 409, record failed audit metadata, and do not create replacement versions.
- Settings persistence record DTOs now live in `infrastructure/persistence/records.py`, SQLAlchemy model/record mapping plus timestamp/text normalization live in `infrastructure/persistence/repository_mappers.py`, and domain aggregate conversion lives in `infrastructure/persistence/domain_repository_mappers.py`. Domain repository classes are split by resource/version/override/snapshot/audit family and own only query and transaction behavior.
