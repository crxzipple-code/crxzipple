# Module Audit: authorization

## Verdict

Low-medium risk. Authorization is comparatively small and has a clear responsibility: internal ABAC policy, effects, approvals, grants, and audit.

## Evidence

- 18 Python files, about 2794 lines.
- Large files include `application/services.py` (972), `interfaces/http.py` (642), `infrastructure/evaluators.py` (205).

## Findings

- Boundary is cleaner than most modules.
- Application service is moderately large but still manageable.
- Must remain separate from Access credential truth.
- Approval/grant lifecycle is security-critical and should be tested as a state machine.
- Temporary run/session grants now apply only when the queried run/session scope
  matches and any recorded grant `agent_id` matches the current authorization
  context `agent_id`.
- Agent-managed tool/effect policies now have explicit allow/revoke state-machine
  coverage.
- Authorization audit payloads now redact sensitive nested keys before persistence
  and before read-model responses.

## Launch Risks

- Approval grants leaking across run/session/agent boundaries would be high severity;
  this is now covered by regression tests.
- Policy dry-run and audit must be reliable before external users. Grant
  state-machine, dry-run, impact preview, and audit redaction now have targeted
  coverage.

## Recommendations

- Add policy/grant invariant tests and audit redaction tests.
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

`application/services.py` is 972 lines and defines the main
`AuthorizationApplicationService`, evaluator protocol, grant payload, impact preview,
policy helpers, request/decision/grant payload helpers, and run/session grant id
construction. This is manageable but security-critical.

`interfaces/http.py` is 642 lines and currently large enough to hide DTO and preview
assembly logic. It should remain thin as policy/dry-run surfaces grow.

The infrastructure layer is compact: evaluator, YAML loader, and persistence
repositories are separated.

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
- [x] Document effect id and grant lifetime semantics.

### Watchlist

- Move HTTP preview/DTO assembly into application read helpers if `interfaces/http.py` grows further.

### Verification

- `PYTHONPATH=src pytest -q tests/unit/test_authorization.py tests/unit/test_module_architecture_guards.py::test_access_and_authorization_do_not_cross_own_truth_boundaries --tb=short` -> 22 passed.
- `python -m ruff check src/crxzipple/modules/authorization/application/services.py tests/unit/test_authorization.py` -> passed.
