# Module Audit: skills

## Verdict

Medium-high risk. Skills are important for long-term extensibility and should remain catalog/package owner. The filesystem, authoring, owner state, persistence, HTTP DTO, major CLI command group, runtime visibility, context render, and filesystem race surfaces are now cleaner; future source trust hardening remains the main hotspot before broader external skill installation.

## Evidence

- 52 Python files, about 11185 lines.
- Large files include `interfaces/http_models.py` (775), `interfaces/http.py` (584), `infrastructure/filesystem/repository.py` (558), `application/manager.py` (543), `application/authoring_service.py` (528), `interfaces/cli.py` (516), `application/package_service.py` (472), `infrastructure/persistence/repository_mappers.py` (459), `interfaces/cli_draft_commands.py` (433), `application/owner_state.py` (430), `application/source_service.py` (423), `infrastructure/persistence/repositories.py` (403).
- Filesystem package handling has been split in this remediation wave:
  - `infrastructure/filesystem/repository.py`: public filesystem repository orchestration, install/create/update/delete/read entrypoints, root selection.
  - `infrastructure/filesystem/path_safety.py`: root/path normalization and traversal prevention.
  - `infrastructure/filesystem/manifest_parser.py`: SKILL.md frontmatter, legacy manifest parsing, requirement normalization, markdown rendering.
  - `infrastructure/filesystem/package_files.py`: bounded text reads, legacy manifest file reads, resource discovery, fingerprinting.
  - `infrastructure/filesystem/package_loader.py`: directory-to-`SkillPackage` loading and discovery.
- Authoring service has started splitting in this remediation wave:
  - `application/authoring_payloads.py`: draft event and audit payload projection.
  - `application/authoring_conversions.py`: draft-to-package/request/manifest conversion and requirement merge helpers.
  - `application/authoring_validation.py`: support-file, requirement, manifest, existing package, and readiness validation projection.
  - `application/authoring_diff.py`: draft diff construction and unified diff rendering.
  - `application/authoring_readiness.py`: draft requirement readiness resolution with and without tool readiness ports.
  - `application/authoring_apply.py`: draft mutability, apply target validation, invalid draft shaping, and applied draft shaping.
  - `application/authoring_observation.py`: draft audit record append, lifecycle event emission, and shared authoring time source.
- Owner state has started splitting in this remediation wave:
  - `application/owner_package_index.py`: source id policy helpers, source type mapping, package id/index/fingerprint/root projection.
  - `application/owner_readiness_projection.py`: readiness snapshot, prompt readiness checks, readiness semantic comparison, and readiness event payload projection.
- Persistence repository has started splitting in this remediation wave:
  - `infrastructure/persistence/repository_mappers.py`: SQLAlchemy model/application record mapping, payload conversion, and draft/readiness/package mapping helpers.
- Interface layer has started splitting in this remediation wave:
  - `interfaces/cli_options.py`: CLI CSV/JSON/text/support-file option parsing and manifest/requirements construction.
  - `interfaces/cli_payloads.py`: CLI entity-to-payload and draft/readiness payload projection.
  - `interfaces/cli_source_commands.py`: `skills source` command group.
  - `interfaces/cli_draft_commands.py`: governed authoring draft command group.
  - `interfaces/cli_errors.py`: shared Typer error exit helper.
  - `interfaces/http_models.py`: HTTP Pydantic request/response DTOs and response conversion helpers.

## Findings

- Skills owner boundary is correct: package/catalog/resolution requirement belongs here.
- `interfaces/cli.py` is now moderate after source/draft command group extraction; root command growth should still be watched.
- `interfaces/http.py` is now moderate after DTO extraction, but route grouping should remain watched as the surface grows.
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

`interfaces/cli.py` was 1420 lines and is now 516 lines after moving option parsing
and payload projection to `cli_options.py` and `cli_payloads.py`, and moving the
`source` and `draft` command groups to `cli_source_commands.py` and
`cli_draft_commands.py`. It now acts as root command registration and the remaining
top-level skill command surface.

`interfaces/http.py` was 1329 lines and is now 584 lines after moving HTTP request and
response DTOs to `http_models.py`. The route module is now moderate and mostly acts as
dependency lookup, application-service call, exception mapping, and serialization glue.

`application/authoring_service.py` was 988 lines and is now 528 lines after moving
draft event/audit payloads, draft conversion helpers, requirement merge helpers, and
support-file/requirement validation rules into focused application helpers, plus draft
diff construction into `authoring_diff.py`, draft readiness into `authoring_readiness.py`,
apply lifecycle rules into `authoring_apply.py`, and audit/event side effects into
`authoring_observation.py`. It still contains draft lifecycle, repository access, and
package-service writes; that remaining coordination is the intended authoring use-case
surface rather than a separate owner.

`application/owner_state.py` was 733 lines and is now 430 lines after moving package
index/source helper rules to `owner_package_index.py` and readiness snapshot/event
projection rules to `owner_readiness_projection.py`. It now coordinates owner state
persistence, readiness writes, installation records, and lifecycle events without
carrying projection helpers inline.

`infrastructure/filesystem/repository.py` was 1144 lines and is now 558 lines after
splitting path safety, manifest/frontmatter parsing, package file helpers, and package
loading. It still owns the public filesystem repository orchestration and mutation
entrypoints, plus normalized domain errors for install/create target races, but no
longer carries duplicate low-level parsing and fingerprint logic.

`infrastructure/persistence/repositories.py` was 817 lines and is now 403 lines after
moving SQLAlchemy/application record mapping and JSON payload conversion to
`repository_mappers.py`. It now reads as the transaction/query repository shell rather
than a mixed persistence and mapper collection.

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

- [x] Split Source and Draft CLI command groups into focused command modules; keep `interfaces/cli.py` as root registration/top-level command glue.
- [x] Split HTTP Pydantic DTOs and response conversion helpers out of `interfaces/http.py`.
- [x] Split CLI option parsing and payload projection helpers out of `interfaces/cli.py`.
- [x] Split `authoring_service.py` helper concerns into focused payload, conversion, requirement merge, validation/readiness projection, diff builder, apply rule, and audit/event observation helpers; keep draft lifecycle coordination in the service.
- [x] Split `owner_state.py` into package index service and readiness projection service.
- [x] Split persistence repository mapper/payload conversion helpers from `repositories.py`.
- [x] Split filesystem repository path safety, manifest/frontmatter parser, package file helpers, and package loader.
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
python -m ruff check src/crxzipple/modules/skills/application/owner_state.py src/crxzipple/modules/skills/application/owner_package_index.py src/crxzipple/modules/skills/application/owner_readiness_projection.py src/crxzipple/modules/skills/application/authoring_apply.py src/crxzipple/modules/skills/application/authoring_service.py src/crxzipple/modules/skills/application/authoring_conversions.py src/crxzipple/modules/skills/application/authoring_diff.py src/crxzipple/modules/skills/application/authoring_observation.py src/crxzipple/modules/skills/application/authoring_payloads.py src/crxzipple/modules/skills/application/authoring_readiness.py src/crxzipple/modules/skills/application/authoring_validation.py src/crxzipple/modules/skills/infrastructure/filesystem/repository.py src/crxzipple/modules/skills/infrastructure/filesystem/path_safety.py src/crxzipple/modules/skills/infrastructure/filesystem/manifest_parser.py src/crxzipple/modules/skills/infrastructure/filesystem/package_files.py src/crxzipple/modules/skills/infrastructure/filesystem/package_loader.py src/crxzipple/modules/skills/infrastructure/persistence/repositories.py src/crxzipple/modules/skills/infrastructure/persistence/repository_mappers.py src/crxzipple/modules/skills/interfaces/cli.py src/crxzipple/modules/skills/interfaces/cli_errors.py src/crxzipple/modules/skills/interfaces/cli_source_commands.py src/crxzipple/modules/skills/interfaces/cli_draft_commands.py src/crxzipple/modules/skills/interfaces/cli_options.py src/crxzipple/modules/skills/interfaces/cli_payloads.py src/crxzipple/modules/skills/interfaces/http.py src/crxzipple/modules/skills/interfaces/http_models.py tests/unit/test_skills_context.py
PYTHONPATH=src pytest -q tests/unit/test_skills_context.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_skill_adapter.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_skills_cli.py tests/unit/test_skills_http.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_skills_cli.py tests/unit/test_skills_context.py tests/unit/test_skills_http.py tests/unit/test_skills_tool_authoring.py tests/unit/test_skills_authoring_http.py tests/unit/test_skills_owner_catalog_persistence.py tests/unit/test_context_workspace_skill_adapter.py --tb=short
```

Results:

- `ruff`: passed
- `test_skills_context.py`: 37 passed
- `test_context_workspace_skill_adapter.py`: 3 passed
- `test_skills_cli.py`: 2 passed
- `test_skills_cli.py test_skills_http.py`: 3 passed
- `test_skills_authoring_http.py`: 2 passed
- full targeted Skills set: 57 passed

Trusted external source provenance and signature policy is documented in
`docs/skill-source-trust-policy.md`.
