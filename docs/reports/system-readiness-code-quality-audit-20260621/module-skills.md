# Module Audit: skills

## Verdict

Medium-high risk. Skills are important for long-term extensibility and should remain catalog/package owner. The filesystem, authoring, owner state, persistence, HTTP DTO, major CLI command group, runtime visibility, context render, and filesystem race surfaces are now cleaner; future source trust hardening remains the main hotspot before broader external skill installation.

## Evidence

- 74 Python files, about 11925 lines.
- Large files include `application/manager.py` (479), `application/authoring_service.py` (470), `infrastructure/filesystem/repository.py` (444), `infrastructure/persistence/repositories.py` (405), `application/runtime_request_resolver.py` (375), `application/package_service.py` (361), `interfaces/cli_skill_mutation_commands.py` (353), `application/models.py` (342), `application/ports.py` (328), and `interfaces/http_draft_models.py` (320).
- Filesystem package handling has been split in this remediation wave:
  - `infrastructure/filesystem/repository.py`: public filesystem repository orchestration, install/create/update/delete/read entrypoints, root selection.
  - `infrastructure/filesystem/path_safety.py`: root/path normalization and traversal prevention.
  - `infrastructure/filesystem/manifest_parser.py`: SKILL.md frontmatter, legacy manifest parsing, requirement normalization, markdown rendering.
  - `infrastructure/filesystem/package_files.py`: bounded text reads, legacy manifest file reads, resource discovery, fingerprinting.
  - `infrastructure/filesystem/package_loader.py`: directory-to-`SkillPackage` loading and discovery.
  - `infrastructure/filesystem/package_mutations.py`: writable-package guard, create/update manifest construction, instruction body restoration, and legacy manifest materialization.
- Authoring service has started splitting in this remediation wave:
  - `application/authoring_payloads.py`: draft event and audit payload projection.
  - `application/authoring_conversions.py`: draft-to-package/request/manifest conversion and requirement merge helpers.
  - `application/authoring_validation.py`: support-file, requirement, manifest, existing package, and readiness validation projection.
  - `application/authoring_diff.py`: draft diff construction and unified diff rendering.
  - `application/authoring_readiness.py`: draft requirement readiness resolution with and without tool readiness ports.
  - `application/authoring_apply.py`: draft mutability, apply target validation, invalid draft shaping, and applied draft shaping.
  - `application/authoring_observation.py`: draft audit record append, lifecycle event emission, and shared authoring time source.
  - `application/authoring_owner_state.py`: current package/instruction/support-file reads and draft-to-owner package writes.
- Package service observation has split in this remediation wave:
  - `application/package_service.py`: package create/update/read/delete/validate/install use-case coordination.
  - `application/package_observation.py`: package event payload projection, install/audit record writes, and duration measurement.
- Source service projection and observation have split in this remediation wave:
  - `application/source_service.py`: source create/update/delete/sync coordination and catalog snapshot sync.
  - `application/source_projection.py`: source list/app DTO projection from packages and persisted source records.
  - `application/source_observation.py`: source event payload projection and source install/sync record writes.
  - `application/source_validation.py`: source id/root normalization, reserved-source guard, and editable source-kind validation.
- Manager service graph construction has split in this remediation wave:
  - `application/manager.py`: public Skills application facade and typed delegation surface.
  - `application/manager_services.py`: default service graph construction and authoring draft repository capability detection.
- Owner state has started splitting in this remediation wave:
  - `application/owner_package_index.py`: source id policy helpers, source type mapping, package id/index/fingerprint/root projection.
  - `application/owner_readiness_projection.py`: readiness snapshot, prompt readiness checks, readiness semantic comparison, and readiness event payload projection.
  - `application/owner_catalog_snapshot.py`: source/package snapshot persistence, removed-package reconciliation, and removed readiness event emission.
- Persistence repository has started splitting in this remediation wave:
  - `infrastructure/persistence/repository_catalog_mappers.py`: source, package, policy, readiness, and installation SQLAlchemy/domain mapping helpers.
  - `infrastructure/persistence/repository_draft_mappers.py`: governed authoring draft/audit SQLAlchemy/application mapping and draft validation/diff payload conversion helpers.
  - `infrastructure/persistence/repository_payloads.py`: shared requirements and text tuple payload restoration helpers.
  - The former mixed `infrastructure/persistence/repository_mappers.py` file is retired instead of kept as a compatibility surface.
- Interface layer has started splitting in this remediation wave:
  - `interfaces/cli_options.py`: CLI CSV/JSON/text/support-file option parsing and manifest/requirements construction.
  - `interfaces/cli_payloads.py`: CLI entity-to-payload and draft/readiness payload projection.
  - `interfaces/cli_source_commands.py`: `skills source` command group.
  - `interfaces/cli_draft_commands.py`: 24-line governed draft command composition entrypoint.
  - `interfaces/cli_draft_query_commands.py`: draft list/show/audit commands.
  - `interfaces/cli_draft_authoring_commands.py`: draft create/update commands and option wiring.
  - `interfaces/cli_draft_lifecycle_commands.py`: draft validate/diff/apply/reject/delete lifecycle commands.
  - `interfaces/cli_skill_query_commands.py`: top-level list/readiness/show/get/read/validate commands.
  - `interfaces/cli_skill_mutation_commands.py`: top-level sync/install/create/update/write/enable/disable/delete commands.
  - `interfaces/cli_errors.py`: shared Typer error exit helper.
  - `interfaces/http.py`: 20-line HTTP route composition entrypoint.
  - `interfaces/http_errors.py`: shared HTTP error mapping.
  - `interfaces/http_skill_routes.py`: package/skill/readiness routes.
  - `interfaces/http_draft_routes.py`: governed authoring draft routes.
  - `interfaces/http_source_routes.py`: source, install, installation, and sync routes.
  - `interfaces/http_models.py`: 75-line public HTTP DTO export surface.
  - `interfaces/http_skill_models.py`: package/skill/readiness request and response DTOs.
  - `interfaces/http_draft_models.py`: draft create/update, validation, diff, and audit DTOs.
  - `interfaces/http_source_models.py`: source, install, installation, and sync DTOs.

## Findings

- Skills owner boundary is correct: package/catalog/resolution requirement belongs here.
- `interfaces/cli.py` is now a small Typer composition entrypoint after source/draft/query/mutation command extraction.
- `interfaces/http.py` is now a small route composition entrypoint after DTO and route grouping extraction.
- Authoring and package management are separated from runtime resolution at the application-helper level; `authoring_service.py` keeps draft lifecycle coordination.
- Skill usage should not become catalog truth.

## Launch Risks

- External skill installation can create security and trust concerns.
- Large interfaces make governance actions hard to audit.
- Runtime skill visibility can drift from Context Workspace/tool surface rules.

## Recommendations

- Split package install/read/validate, authoring, source, owner state, and runtime resolution surfaces.
- Add signed/trusted source policy before broader user installation.
- Keep Settings as governance entry only; Skills owns catalog facts.
- Add skill resolution golden tests against Context Workspace/tool surface rendering.

## Detailed Pass 1

### Files Reviewed

- `application/authoring_service.py`
- `application/owner_state.py`
- `application/manager.py`
- `application/package_service.py`
- `application/source_service.py`
- `application/runtime_request_resolver.py`
- `application/catalog_service.py`
- `application/readiness_service.py`
- `infrastructure/filesystem/repository.py`
- `infrastructure/persistence/repositories.py`
- `interfaces/http.py`
- `interfaces/cli.py`

### File-Level Assessment

`interfaces/cli.py` was 1420 lines and is now 21 lines after moving option parsing
and payload projection to `cli_options.py` and `cli_payloads.py`, moving the `source`
command group to `cli_source_commands.py`, splitting the governed draft surface behind
the 24-line `cli_draft_commands.py` composition entrypoint into query, authoring, and
lifecycle modules, and splitting top-level skill commands into
`cli_skill_query_commands.py` and `cli_skill_mutation_commands.py`. It now only
composes the Skills Typer app.

`interfaces/http.py` was 1329 lines and is now 20 lines after moving HTTP request and
response DTOs behind `http_models.py` and route groups into focused route modules.
The DTO implementation is split by HTTP concern: package/skill/readiness models in
`http_skill_models.py`, governed authoring draft models in `http_draft_models.py`,
and source/install/sync models in `http_source_models.py`. Route functions are split
the same way across `http_skill_routes.py`, `http_draft_routes.py`, and
`http_source_routes.py`, with `http_errors.py` owning shared HTTP exception mapping.
`http_models.py` remains only the narrow public export surface used by route modules.

`application/authoring_service.py` was 988 lines and is now 470 lines after moving
draft event/audit payloads, draft conversion helpers, requirement merge helpers, and
support-file/requirement validation rules into focused application helpers, plus draft
diff construction into `authoring_diff.py`, draft readiness into `authoring_readiness.py`,
apply lifecycle rules into `authoring_apply.py`, and audit/event side effects into
`authoring_observation.py`, plus current owner reads and draft owner writes into
`authoring_owner_state.py`. It still contains draft lifecycle and repository access;
that remaining coordination is the intended authoring use-case surface rather than a
separate owner.

`application/package_service.py` is now 361 lines after moving package event payload
construction, install/read/validate failure/success observation, installation record
writes, and duration calculation into `package_observation.py`, then consolidating
repeated source-sync and successful mutation record calls behind private service
helpers. It keeps package mutation/read/install orchestration and repository/source
sync calls.

`application/source_service.py` was 423 lines and is now 273 lines after moving source
list/app DTO projection to `source_projection.py`, source event/install-record
projection to `source_observation.py`, and source id/root/custom-source validation to
`source_validation.py`. It keeps source lifecycle coordination, catalog snapshot sync,
and owner repository access.

`application/manager.py` was 543 lines and is now 479 lines after moving default
service graph construction and authoring-draft repository detection into
`manager_services.py`. It remains the public application facade and delegates to the
focused package, source, catalog, governance, readiness, and authoring services.

`application/owner_state.py` was 733 lines and is now 310 lines after moving package
index/source helper rules to `owner_package_index.py`, readiness snapshot/event
projection rules to `owner_readiness_projection.py`, and catalog snapshot/removed
package reconciliation to `owner_catalog_snapshot.py`. It now coordinates owner state
persistence, readiness writes, installation records, and lifecycle events without
carrying projection and reconciliation helpers inline.

`infrastructure/filesystem/repository.py` was 1144 lines and is now 444 lines after
splitting path safety, manifest/frontmatter parsing, package file helpers, package
loading, and package mutation helper rules. It still owns root selection and the public
filesystem repository entrypoints, plus normalized domain errors for install/create
target races, but no longer carries duplicate low-level parsing, fingerprint, manifest
construction, or materialization logic.

`infrastructure/persistence/repositories.py` was 817 lines and is now 405 lines after
moving SQLAlchemy/application record mapping and JSON payload conversion to
`repository_catalog_mappers.py`, `repository_draft_mappers.py`, and
`repository_payloads.py`. It now reads as the transaction/query repository shell rather
than a mixed persistence and mapper collection, and the former mixed
`repository_mappers.py` file is retired instead of kept as a compatibility surface.

`runtime_request_resolver.py` is 375 lines and clearly expresses the runtime visibility
decision surface. This is the right place for model-facing skill availability, but it
must coordinate with Context Workspace render rules rather than bypass them.

### Boundary Cleanliness

Skills owns skill package/catalog/resolution/readiness facts. It should not own tool
run facts, orchestration run usage, or Settings truth except where Settings acts as a
governance entry.

Risk pattern:

- Skill usage observed during a run must not become catalog truth.
- Runtime request resolution should produce selected skill availability, not mutate
  context tree directly.
- Filesystem package state must be carefully isolated from user workspace writes.

### Lifecycle Clarity

Skill lifecycle should be:

1. source root/package discovered or installed
2. package manifest and instruction files validated
3. owner state/catalog index persisted
4. readiness evaluated against access/tool/auth requirements
5. runtime request resolver exposes eligible skills/slices
6. authoring flow updates drafts/packages with audit

The code has these parts, but interface and authoring layers are still broad.

### Persistence And Efficiency

Skills uses filesystem package repositories plus SQL persistence. That is appropriate,
but source scanning and package reads must be bounded. Runtime request resolution must
not repeatedly read large skill bodies unless selected by policy.

### Concurrency And Multi-User Readiness

Multi-user skill installation requires source trust, path isolation, normalized
filesystem race errors, package lock or transaction behavior for future shared package
stores, and predictable cache invalidation. Install/create target races now normalize to
`SkillValidationError`; authoring update conflicts are guarded by draft target
fingerprints.

### External Integration Readiness

Skills is the module most likely to integrate external ecosystems. It needs stable
source/package contracts, trusted source policy, and safe import/export behavior.

### Remediation Checklist

- [x] Split Source, Draft query, Draft authoring, Draft lifecycle, top-level query, and top-level mutation CLI command groups into focused command modules; keep `interfaces/cli.py` and `interfaces/cli_draft_commands.py` as composition only.
- [x] Split HTTP Pydantic DTOs and response conversion helpers out of `interfaces/http.py`.
- [x] Split HTTP routes into package/skill, draft, and source/install/sync route modules.
- [x] Split CLI option parsing and payload projection helpers out of `interfaces/cli.py`.
- [x] Split `authoring_service.py` helper concerns into focused payload, conversion, requirement merge, validation/readiness projection, diff builder, apply rule, audit/event observation, and owner-state IO helpers; keep draft lifecycle coordination in the service.
- [x] Split package service observation/event/install-record projection out of `package_service.py`; keep package use-case coordination in the service.
- [x] Split source service list projection, source event/install-record observation, and source validation helpers out of `source_service.py`; keep source lifecycle coordination in the service.
- [x] Split manager service graph construction out of `manager.py`; keep `SkillManager` as public facade and delegation surface.
- [x] Split `owner_state.py` into package index, readiness projection, and catalog snapshot reconciliation helpers.
- [x] Split persistence catalog, draft, and shared payload mapper helpers from `repositories.py`; retire the mixed `repository_mappers.py` file.
- [x] Split filesystem repository path safety, manifest/frontmatter parser, package file helpers, package loader, and package mutation helpers.
- [x] Preserve runtime skill resolution behavior with Skills and Context Workspace skill adapter tests.
- [x] Preserve manifest/frontmatter read/write behavior with Skills context, HTTP, CLI, authoring, and owner catalog tests.
- [x] Add write/delete support-file traversal tests so support-file endpoints cannot modify `SKILL.md` or escape through `..` segments.
- [x] Add source and skill runtime visibility policy tests.
- [x] Add trusted source signature/provenance policy before broader external install.
- [x] Add runtime skill resolution golden tests against Context Workspace rendered slices.
- [x] Add package install/create race normalization tests and preserve authoring update stale-fingerprint coverage.

### Remediation Verification

Commands passed after the current Skills split wave:

```bash
python -m ruff check src/crxzipple/modules/skills/application/owner_state.py src/crxzipple/modules/skills/application/owner_catalog_snapshot.py src/crxzipple/modules/skills/application/owner_package_index.py src/crxzipple/modules/skills/application/owner_readiness_projection.py src/crxzipple/modules/skills/application/authoring_apply.py src/crxzipple/modules/skills/application/authoring_service.py src/crxzipple/modules/skills/application/authoring_conversions.py src/crxzipple/modules/skills/application/authoring_diff.py src/crxzipple/modules/skills/application/authoring_observation.py src/crxzipple/modules/skills/application/authoring_owner_state.py src/crxzipple/modules/skills/application/authoring_payloads.py src/crxzipple/modules/skills/application/authoring_readiness.py src/crxzipple/modules/skills/application/authoring_validation.py src/crxzipple/modules/skills/infrastructure/filesystem/repository.py src/crxzipple/modules/skills/infrastructure/filesystem/path_safety.py src/crxzipple/modules/skills/infrastructure/filesystem/manifest_parser.py src/crxzipple/modules/skills/infrastructure/filesystem/package_files.py src/crxzipple/modules/skills/infrastructure/filesystem/package_loader.py src/crxzipple/modules/skills/infrastructure/filesystem/package_mutations.py src/crxzipple/modules/skills/infrastructure/persistence/repositories.py src/crxzipple/modules/skills/infrastructure/persistence/repository_catalog_mappers.py src/crxzipple/modules/skills/infrastructure/persistence/repository_draft_mappers.py src/crxzipple/modules/skills/infrastructure/persistence/repository_payloads.py src/crxzipple/modules/skills/interfaces/cli.py src/crxzipple/modules/skills/interfaces/cli_errors.py src/crxzipple/modules/skills/interfaces/cli_source_commands.py src/crxzipple/modules/skills/interfaces/cli_draft_commands.py src/crxzipple/modules/skills/interfaces/cli_options.py src/crxzipple/modules/skills/interfaces/cli_payloads.py src/crxzipple/modules/skills/interfaces/http.py src/crxzipple/modules/skills/interfaces/http_models.py tests/unit/test_skills_context.py
PYTHONPATH=src ruff check src/crxzipple/modules/skills/interfaces/cli.py src/crxzipple/modules/skills/interfaces/cli_skill_query_commands.py src/crxzipple/modules/skills/interfaces/cli_skill_mutation_commands.py src/crxzipple/modules/skills/interfaces/cli_source_commands.py src/crxzipple/modules/skills/interfaces/cli_draft_commands.py tests/unit/test_skills_cli.py --ignore F403,F405
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/skills/interfaces/cli.py src/crxzipple/modules/skills/interfaces/cli_skill_query_commands.py src/crxzipple/modules/skills/interfaces/cli_skill_mutation_commands.py src/crxzipple/modules/skills/interfaces/cli_source_commands.py src/crxzipple/modules/skills/interfaces/cli_draft_commands.py
PYTHONPATH=src ruff check src/crxzipple/modules/skills/interfaces/cli_draft_commands.py src/crxzipple/modules/skills/interfaces/cli_draft_query_commands.py src/crxzipple/modules/skills/interfaces/cli_draft_authoring_commands.py src/crxzipple/modules/skills/interfaces/cli_draft_lifecycle_commands.py src/crxzipple/modules/skills/interfaces/cli.py tests/unit/test_skills_cli.py --ignore F403,F405
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/skills/interfaces/cli_draft_commands.py src/crxzipple/modules/skills/interfaces/cli_draft_query_commands.py src/crxzipple/modules/skills/interfaces/cli_draft_authoring_commands.py src/crxzipple/modules/skills/interfaces/cli_draft_lifecycle_commands.py src/crxzipple/modules/skills/interfaces/cli.py
PYTHONPATH=src ruff check src/crxzipple/modules/skills/application/package_service.py src/crxzipple/modules/skills/application/package_observation.py tests/unit/test_skills_context.py tests/unit/test_skills_http.py tests/unit/test_skills_cli.py --ignore F403,F405
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/skills/application/package_service.py src/crxzipple/modules/skills/application/package_observation.py
PYTHONPATH=src ruff check src/crxzipple/modules/skills/application/source_service.py src/crxzipple/modules/skills/application/source_projection.py src/crxzipple/modules/skills/application/source_observation.py src/crxzipple/modules/skills/application/package_service.py src/crxzipple/modules/skills/application/package_observation.py tests/unit/test_skills_cli.py tests/unit/test_skills_http.py --ignore F403,F405
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/skills/application/source_service.py src/crxzipple/modules/skills/application/source_projection.py src/crxzipple/modules/skills/application/source_observation.py src/crxzipple/modules/skills/application/package_service.py src/crxzipple/modules/skills/application/package_observation.py
PYTHONPATH=src ruff check src/crxzipple/modules/skills/application/source_service.py src/crxzipple/modules/skills/application/source_validation.py tests/unit/test_skills_cli.py tests/unit/test_skills_context.py tests/unit/test_skills_http.py --ignore F403,F405
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/skills/application/source_service.py src/crxzipple/modules/skills/application/source_validation.py
PYTHONPATH=src ruff check src/crxzipple/modules/skills/application/manager.py src/crxzipple/modules/skills/application/manager_services.py src/crxzipple/modules/skills/application/source_service.py src/crxzipple/modules/skills/application/source_projection.py src/crxzipple/modules/skills/application/source_observation.py src/crxzipple/modules/skills/application/package_service.py src/crxzipple/modules/skills/application/package_observation.py tests/unit/test_skills_context.py tests/unit/test_skills_owner_catalog_persistence.py --ignore F403,F405
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/skills/application/manager.py src/crxzipple/modules/skills/application/manager_services.py src/crxzipple/modules/skills/application/source_service.py src/crxzipple/modules/skills/application/source_projection.py src/crxzipple/modules/skills/application/source_observation.py src/crxzipple/modules/skills/application/package_service.py src/crxzipple/modules/skills/application/package_observation.py
PYTHONPATH=src ruff check src/crxzipple/modules/skills/infrastructure/persistence/repositories.py src/crxzipple/modules/skills/infrastructure/persistence/repository_catalog_mappers.py src/crxzipple/modules/skills/infrastructure/persistence/repository_draft_mappers.py src/crxzipple/modules/skills/infrastructure/persistence/repository_payloads.py tests/unit/test_skills_owner_catalog_persistence.py
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/skills/infrastructure/persistence/repositories.py src/crxzipple/modules/skills/infrastructure/persistence/repository_catalog_mappers.py src/crxzipple/modules/skills/infrastructure/persistence/repository_draft_mappers.py src/crxzipple/modules/skills/infrastructure/persistence/repository_payloads.py
PYTHONPATH=src ruff check src/crxzipple/modules/skills/application/authoring_service.py src/crxzipple/modules/skills/application/authoring_owner_state.py tests/unit/test_skills_tool_authoring.py tests/unit/test_skills_authoring_http.py tests/unit/test_skills_context.py --ignore F403,F405
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/skills/application/authoring_service.py src/crxzipple/modules/skills/application/authoring_owner_state.py
PYTHONPATH=src ruff check src/crxzipple/modules/skills/infrastructure/filesystem/repository.py src/crxzipple/modules/skills/infrastructure/filesystem/package_mutations.py tests/unit/test_skills_context.py tests/unit/test_skills_cli.py tests/unit/test_skills_http.py --ignore F403,F405
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/skills/infrastructure/filesystem/repository.py src/crxzipple/modules/skills/infrastructure/filesystem/package_mutations.py
PYTHONPATH=src ruff check src/crxzipple/modules/skills/application/owner_state.py src/crxzipple/modules/skills/application/owner_catalog_snapshot.py tests/unit/test_skills_context.py tests/unit/test_skills_owner_catalog_persistence.py --ignore F403,F405
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/skills/application/owner_state.py src/crxzipple/modules/skills/application/owner_catalog_snapshot.py
PYTHONPATH=src ruff check src/crxzipple/modules/skills/interfaces/http_models.py src/crxzipple/modules/skills/interfaces/http_skill_models.py src/crxzipple/modules/skills/interfaces/http_draft_models.py src/crxzipple/modules/skills/interfaces/http_source_models.py src/crxzipple/modules/skills/interfaces/http.py
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/skills/interfaces/http_models.py src/crxzipple/modules/skills/interfaces/http_skill_models.py src/crxzipple/modules/skills/interfaces/http_draft_models.py src/crxzipple/modules/skills/interfaces/http_source_models.py src/crxzipple/modules/skills/interfaces/http.py
PYTHONPATH=src ruff check src/crxzipple/modules/skills/interfaces/http.py src/crxzipple/modules/skills/interfaces/http_errors.py src/crxzipple/modules/skills/interfaces/http_skill_routes.py src/crxzipple/modules/skills/interfaces/http_draft_routes.py src/crxzipple/modules/skills/interfaces/http_source_routes.py
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/skills/interfaces/http.py src/crxzipple/modules/skills/interfaces/http_errors.py src/crxzipple/modules/skills/interfaces/http_skill_routes.py src/crxzipple/modules/skills/interfaces/http_draft_routes.py src/crxzipple/modules/skills/interfaces/http_source_routes.py
PYTHONPATH=src pytest -q tests/unit/test_skills_context.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_skill_adapter.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_skills_cli.py tests/unit/test_skills_http.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_skills_cli.py tests/unit/test_skills_context.py tests/unit/test_skills_http.py tests/unit/test_skills_tool_authoring.py tests/unit/test_skills_authoring_http.py tests/unit/test_skills_owner_catalog_persistence.py tests/unit/test_context_workspace_skill_adapter.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_skills_http.py tests/unit/test_skills_authoring_http.py tests/unit/test_skills_tool_authoring.py tests/unit/test_skills_context.py tests/unit/test_skills_owner_catalog_persistence.py --tb=short --maxfail=1
```

Results:

- `ruff`: passed
- `test_skills_context.py`: 37 passed
- `test_context_workspace_skill_adapter.py`: 3 passed
- `test_skills_cli.py`: 2 passed
- `test_skills_cli.py test_skills_http.py`: 3 passed
- `test_skills_authoring_http.py`: 2 passed
- full targeted Skills set: 57 passed
- HTTP DTO split ruff/compileall: passed
- HTTP route split ruff/compileall: passed
- CLI query/mutation route split ruff/compileall: passed
- Draft CLI query/authoring/lifecycle split ruff/compileall: passed
- Package service observation split ruff/compileall: passed
- Source service projection/observation split ruff/compileall: passed
- Manager service graph split ruff/compileall: passed
- Persistence mapper family split ruff/compileall: passed
- Skills owner catalog persistence: 8 passed
- Authoring owner-state IO split ruff/compileall: passed
- Filesystem package mutation helper split ruff/compileall: passed
- Owner catalog snapshot helper split ruff/compileall: passed
- HTTP and authoring HTTP routes: 3 passed
- HTTP DTO targeted Skills set: 52 passed

Trusted external source provenance and signature policy is documented in
`docs/skill-source-trust-policy.md`.
