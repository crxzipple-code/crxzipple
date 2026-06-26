# Module Audit: authorization

## Verdict

Low-medium risk. Authorization is comparatively small and has a clear responsibility: internal ABAC policy, effects, approvals, grants, and audit.

## Evidence

- 41 Python files, about 3807 lines.
- Large files include `infrastructure/evaluators.py` (205), `interfaces/http_models.py` (194), `infrastructure/persistence/repository_mappers.py` (193), `application/policy_lifecycle.py` (191), `application/services.py` (173), `application/tool_execution_authorization.py` (166), `interfaces/http_payloads.py` (165), `interfaces/http.py` (165), and `infrastructure/persistence/repositories.py` (155). `interfaces/http_decision_routes.py` is a 97-line decision/audit route module, and `application/payloads.py` is now a 116-line payload projection module after audit redaction rules moved to `application/audit_redaction.py`.

## Findings

- Boundary is cleaner than most modules.
- Application service is now a compact public facade over focused policy, decision, grant, audit, lifecycle, and evaluator helpers.
- Must remain separate from Access credential truth.
- Approval/grant lifecycle is security-critical and should be tested as a state machine.
- Temporary run/session grants now apply only when the queried run/session scope
  matches and any recorded grant `agent_id` matches the current authorization
  context `agent_id`.
- Agent-managed tool/effect policies now have explicit allow/revoke state-machine
  coverage.
- Authorization audit payloads now redact sensitive nested keys before persistence
  and before read-model responses.
- HTTP request/response DTOs, request/domain/response payload mapping, service
  lookup, agent-grant response handling, and policy CRUD/import/export handlers are
  now split out of the route file, keeping `interfaces/http.py` focused on endpoint
  orchestration.
- Dry-run, impact-preview, audit listing, and check endpoints now live in
  `interfaces/http_decision_routes.py`, so the main Authorization route file keeps
  policy and agent-grant route composition.
- Application-level grant id/matching helpers, agent-managed policy construction,
  and audit/policy/request/decision payload helpers are now split out of
  `AuthorizationApplicationService`.
- Audit redaction rules now live in `application/audit_redaction.py`; payload
  projection helpers remain in `application/payloads.py`.
- Tool execution authorization decision flow now lives in
  `application/tool_execution_authorization.py`; `AuthorizationApplicationService`
  owns repository access, temporary grant aggregation, evaluator access, and audit.
- Policy impact preview DTO and pure before/after policy projection now live in
  `application/policy_impact.py`; the application service records the audit outcome.
- Temporary run/session grant construction and scoped grant aggregation now live in
  `application/temporary_grants.py`.
- Temporary run/session grant creation, persistence, and audit coordination now live
  in `application/temporary_grant_service.py`.
- Dry-run and impact-preview decision use cases now live in
  `application/decision_use_cases.py`; the public service remains the facade.
- Audit record construction, timestamp/id creation, text normalization, and audit
  payload redaction now live in `application/audit_records.py`.
- Policy create/update/enable/delete/import coordination now lives in
  `application/policy_lifecycle.py`; the public service delegates lifecycle writes
  while remaining the public authorization facade.
- Agent-managed effect/tool grant and revoke coordination now lives in
  `application/agent_grants.py`; managed policy construction remains pure in
  `application/agent_managed_policies.py`.
- Public Authorization service entry methods are grouped into focused facade mixins:
  `service_policy_facade.py`, `service_decision_facade.py`,
  `service_grant_facade.py`, and `service_audit_facade.py`. The main
  `AuthorizationApplicationService` now keeps only service composition, core
  check/authorize behavior, tool-execution handoff, policy snapshot cache, and audit
  recording.
- SQLAlchemy policy, temporary grant, and audit model/entity mapping now lives in
  `infrastructure/persistence/repository_mappers.py`; persistence repositories keep
  query, commit, bootstrap, and pagination behavior.

## Launch Risks

- Approval grants leaking across run/session/agent boundaries would be high severity;
  this is now covered by regression tests.
- Policy dry-run and audit must be reliable before external users. Grant
  state-machine, dry-run, impact preview, and audit redaction now have targeted
  coverage.

## Recommendations

- Keep policy/grant invariant and audit redaction tests in the focused
  Authorization suite as lifecycle changes continue.
- Keep HTTP layer thin; move impact preview/dry-run assembly into application read services if it grows.
- Document effect ids and approval grant lifetime semantics.

## Detailed Pass 1

### Files Reviewed

- `application/services.py`
- `domain/entities.py`
- `domain/value_objects.py`
- `domain/repositories.py`
- `infrastructure/evaluators.py`
- `infrastructure/loaders/yaml_loader.py`
- `infrastructure/persistence/repositories.py`
- `interfaces/http.py`
- `interfaces/cli.py`

### File-Level Assessment

`application/services.py` was 781 lines and is now 173 lines. It defines the main
`AuthorizationApplicationService`, evaluator protocol, core check/authorize
behavior, tool-execution handoff, service helper construction, policy snapshot cache,
and audit recording. Policy CRUD/import/export facade methods live in
`application/service_policy_facade.py`; dry-run and impact-preview facade methods live
in `application/service_decision_facade.py`; temporary and agent-managed grant facade
methods live in `application/service_grant_facade.py`; audit query facade methods live
in `application/service_audit_facade.py`. Grant id/matching helpers live in
`application/grant_helpers.py`; agent-managed tool/effect policy construction and
local-managed source validation live in `application/agent_managed_policies.py`;
audit redaction rules live in `application/audit_redaction.py`, and
policy/request/decision/grant payload helpers live in `application/payloads.py`.
Tool execution authorization decision flow and granted authorization payload live in
`application/tool_execution_authorization.py`. Impact preview DTO/projection logic live
in `application/policy_impact.py`. Temporary grant construction and aggregation live in
`application/temporary_grants.py`; temporary grant persistence/audit coordination lives
in `application/temporary_grant_service.py`. Dry-run and impact-preview use-case
coordination lives in `application/decision_use_cases.py`. Audit record construction
lives in `application/audit_records.py`. Policy lifecycle write coordination lives in
`application/policy_lifecycle.py`. Agent-managed grant/revoke coordination lives in
`application/agent_grants.py`. The remaining service is still security-critical, but
the public entry points and helper branches are now small enough to reason about by
lifecycle.

`interfaces/http.py` is 165 lines after extracting Pydantic DTOs into
`interfaces/http_models.py`, request/domain/response conversion helpers into
`interfaces/http_payloads.py`, and check/dry-run/impact/audit endpoints into
`interfaces/http_decision_routes.py`. Service lookup lives in
`interfaces/http_services.py`; agent-grant response/status handling lives in
`interfaces/http_agent_grants.py`; policy CRUD/import/export handlers live in
`interfaces/http_policy_handlers.py`. It now remains focused on policy and
agent-grant route composition.

The infrastructure layer is compact: evaluator, YAML loader, persistence repositories,
and SQLAlchemy/domain mappers are separated.

### Boundary Cleanliness

Authorization owns internal ABAC policy, decisions, effects, approvals, temporary
grants, and authorization audit. It must not own external provider/account/credential
truth, which belongs to Access.

The current import scan did not show Access imports from Authorization application
logic. That is the right direction.

### Lifecycle Clarity

Authorization lifecycle should be:

1. policy/effect exists
2. authorization request is evaluated
3. decision is emitted/audited
4. approval may create a scoped temporary grant
5. grant is consumed by run/session/agent context
6. grant expires or is revoked

The service has these concepts, and the current grant state-machine semantics are:

- run grant: applies to the exact `run_id`; if the grant records `agent_id`, the
  current context must carry the same `agent_id`
- session grant: applies to the exact `session_key` across turns/runs in that
  session; if the grant records `agent_id`, the current context must carry the same
  `agent_id`
- agent-managed tool/effect grant: persisted as managed allow policy and applies
  until explicitly revoked
- effect id: the tool request declares `required_effect_ids`; each required effect
  must be satisfied by temporary grant, request-local grant, or an allow policy
  matching the tool resource `authorization_effect_ids`
- temporary grants currently do not expire by timestamp; expiry/revocation is a
  future lifecycle extension

### Persistence And Efficiency

Policy/grant persistence is small. The main risk is correctness rather than query
cost. Audit queries should remain paginated as usage grows.

### Concurrency And Multi-User Readiness

Grant creation and consumption must be scoped by run/session/agent and should be
idempotent under retry. Cross-user leakage would be high severity.

### External Integration Readiness

External integrations should call Authorization through explicit check/dry-run/grant
ports. They should not parse UI read models or inspect policy storage.

### Remediation Checklist

- [x] Add state-machine tests for run/session/agent grant lifecycle.
- [x] Add architecture test that Authorization does not import Access.
- [x] Add policy dry-run and impact preview tests.
- [x] Add audit redaction tests.
- [x] Split audit redaction rules from Authorization payload projection helpers.
- [x] Document effect id and grant lifetime semantics.
- [x] Split HTTP DTO and read/payload helpers out of the route file.
- [x] Split tool execution authorization decision flow out of the application service.
- [x] Split policy impact preview projection out of the application service.
- [x] Split temporary grant construction and aggregation out of the application service.
- [x] Split temporary grant persistence/audit use case out of the application service.
- [x] Split dry-run and impact-preview use cases out of the application service.
- [x] Split audit record construction out of the application service.
- [x] Split policy lifecycle write coordination out of the application service.
- [x] Split agent-managed grant/revoke coordination out of the application service.
- [x] Split public Authorization service policy, decision, grant, and audit facade entry points out of the application service.
- [x] Split Authorization HTTP service lookup, agent-grant handling, and policy handlers out of the route file.
- [x] Split Authorization HTTP decision/audit routes out of the policy/grant route file.
- [x] Split Authorization SQLAlchemy/domain persistence mappers out of repository behavior.

### Watchlist

- Keep HTTP route additions thin; new request/response DTOs should go into
  `interfaces/http_models.py`, and pure mapping helpers should go into
  `interfaces/http_payloads.py`.

### Verification

- `PYTHONPATH=src pytest -q tests/unit/test_authorization.py tests/unit/test_module_architecture_guards.py::test_access_and_authorization_do_not_cross_own_truth_boundaries --tb=short` -> 22 passed.
- `python -m ruff check src/crxzipple/modules/authorization/application/services.py tests/unit/test_authorization.py` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py tests/unit/test_module_architecture_guards.py::test_access_and_authorization_do_not_cross_own_truth_boundaries --tb=short --maxfail=1` -> 29 passed.
- `python -m ruff check src/crxzipple/modules/authorization/interfaces/http.py src/crxzipple/modules/authorization/interfaces/http_models.py src/crxzipple/modules/authorization/interfaces/http_payloads.py src/crxzipple/modules/authorization/application/services.py tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py` -> passed.
- `python -m ruff check src/crxzipple/modules/authorization/application/services.py src/crxzipple/modules/authorization/application/grant_helpers.py src/crxzipple/modules/authorization/application/payloads.py src/crxzipple/modules/authorization/interfaces/http.py src/crxzipple/modules/authorization/interfaces/http_models.py src/crxzipple/modules/authorization/interfaces/http_payloads.py tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py` -> passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/authorization/application/services.py src/crxzipple/modules/authorization/application/grant_helpers.py src/crxzipple/modules/authorization/application/payloads.py src/crxzipple/modules/authorization/application/agent_managed_policies.py src/crxzipple/modules/authorization/interfaces/http.py src/crxzipple/modules/authorization/interfaces/http_models.py src/crxzipple/modules/authorization/interfaces/http_payloads.py tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/authorization/application/services.py src/crxzipple/modules/authorization/application/grant_helpers.py src/crxzipple/modules/authorization/application/payloads.py src/crxzipple/modules/authorization/application/agent_managed_policies.py` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py tests/unit/test_module_architecture_guards.py::test_access_and_authorization_do_not_cross_own_truth_boundaries --tb=short --maxfail=1` -> 29 passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/authorization/application src/crxzipple/modules/authorization/interfaces tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/authorization/application src/crxzipple/modules/authorization/interfaces` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py tests/unit/test_module_architecture_guards.py::test_access_and_authorization_do_not_cross_own_truth_boundaries --tb=short --maxfail=1` -> 29 passed.
- 2026-06-26 HTTP decision/audit route split:
  `PYTHONPATH=src ruff check src/crxzipple/modules/authorization/interfaces/http.py src/crxzipple/modules/authorization/interfaces/http_decision_routes.py src/crxzipple/modules/authorization/interfaces/http_models.py src/crxzipple/modules/authorization/interfaces/http_payloads.py`
  -> passed.
  `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/authorization/interfaces/http.py src/crxzipple/modules/authorization/interfaces/http_decision_routes.py`
  -> passed.
  `PYTHONPATH=src pytest -q tests/unit/test_auth_http.py tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py tests/unit/test_module_architecture_guards.py::test_access_and_authorization_do_not_cross_own_truth_boundaries --tb=short --maxfail=1`
  -> 33 passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/authorization/application src/crxzipple/modules/authorization/interfaces tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py --ignore F403,F405` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/authorization/application src/crxzipple/modules/authorization/interfaces` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py --tb=short --maxfail=1` -> 28 passed.
- `PYTHONPATH=src pytest -q tests/unit/test_agent_cli.py tests/unit/test_agent_home_persistence.py tests/unit/test_agent_home_scaffold.py tests/unit/test_agent_http.py tests/unit/test_agent_settings_integration.py tests/unit/test_context_workspace_agent_adapter.py --tb=short --maxfail=1` -> 35 passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/authorization/application src/crxzipple/modules/authorization/infrastructure src/crxzipple/modules/authorization/interfaces tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/authorization/application src/crxzipple/modules/authorization/infrastructure src/crxzipple/modules/authorization/interfaces` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py tests/unit/test_module_architecture_guards.py::test_access_and_authorization_do_not_cross_own_truth_boundaries --tb=short --maxfail=1` -> 29 passed.
- 2026-06-26 audit redaction split:
  `PYTHONPATH=src ruff check src/crxzipple/modules/authorization/application src/crxzipple/modules/authorization/interfaces tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py`
  -> passed.
  `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/authorization/application src/crxzipple/modules/authorization/interfaces`
  -> passed.
  `PYTHONPATH=src pytest -q tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py tests/unit/test_module_architecture_guards.py::test_access_and_authorization_do_not_cross_own_truth_boundaries --tb=short --maxfail=1`
  -> 29 passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/authorization/application src/crxzipple/modules/authorization/interfaces tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/authorization/application src/crxzipple/modules/authorization/interfaces` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py tests/unit/test_module_architecture_guards.py::test_access_and_authorization_do_not_cross_own_truth_boundaries --tb=short --maxfail=1` -> 29 passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/authorization/application src/crxzipple/modules/authorization/interfaces tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/authorization/application src/crxzipple/modules/authorization/interfaces` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py tests/unit/test_module_architecture_guards.py::test_access_and_authorization_do_not_cross_own_truth_boundaries --tb=short --maxfail=1` -> 29 passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/authorization/application src/crxzipple/modules/authorization/interfaces tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/authorization/application src/crxzipple/modules/authorization/interfaces` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py tests/unit/test_module_architecture_guards.py::test_access_and_authorization_do_not_cross_own_truth_boundaries --tb=short --maxfail=1` -> 29 passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/authorization/application src/crxzipple/modules/authorization/interfaces tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/authorization/application src/crxzipple/modules/authorization/interfaces` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py tests/unit/test_module_architecture_guards.py::test_access_and_authorization_do_not_cross_own_truth_boundaries --tb=short --maxfail=1` -> 29 passed.
- `PYTHONPATH=src ruff check src/crxzipple/modules/authorization/application src/crxzipple/modules/authorization/interfaces tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py` -> passed.
- `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/authorization/application src/crxzipple/modules/authorization/interfaces` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_authorization.py tests/unit/test_authorization_access_boundary.py tests/unit/test_module_architecture_guards.py::test_access_and_authorization_do_not_cross_own_truth_boundaries --tb=short --maxfail=1` -> 29 passed.
