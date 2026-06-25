# Module Audit: settings

## Verdict

Medium-high risk. Settings is a governance surface, not owner of every module's truth. Current HTTP interface is very large and needs strict owner-source discipline.

## Evidence

- 23 Python files, about 7900 lines.
- Large files include `application/setup.py` (950), `application/services.py` (929), `domain/entities.py` (425), `application/materialization.py` (363), and `interfaces/http_actions.py` (475). `interfaces/http.py` is now a 149-line router.

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
- `infrastructure/persistence/models.py`

### File-Level Assessment

`interfaces/http.py` is now 149 lines and contains overview/list/detail endpoints,
kind/resource action entrypoints, and bootstrap import orchestration only. Settings
action request/response execution moved to `interfaces/http_actions.py`, while
container service lookup and kind normalization moved to `interfaces/http_common.py`.

`application/setup.py` is 950 lines and `application/services.py` is 929 lines. The
application layer is significant but understandable for Settings-owned resource
versioning, overrides, setup/bootstrap, and action services.

`application/materialization.py` is 363 lines and provides a useful effective config
materialization seam. It still contains legacy profile normalization helpers, which
must not blur owner truth: module-owned profiles belong to their owner modules.

Persistence repositories are large but appropriately placed in infrastructure.

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
audit. The risk is not storage size; it is UI endpoints doing too much composition
and action policy logic per request.

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

### Notes From Current Remediation

- `skill-catalog` now follows the same module-owned boundary as Agent/LLM/Channel profiles: Settings may present governance/readiness information, but write operations must go through Skills owner APIs.
- Settings write paths now accept `expected_active_version_id` for update/publish/rollback. Stale mutations fail with `SettingsConflictError`, return HTTP 409, record failed audit metadata, and do not create replacement versions.
