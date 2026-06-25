# Module Audit: access

## Verdict

Medium-high importance, medium risk. Access owns external provider/account/credential readiness. Boundary with Authorization is clear in active docs and mostly reflected by the module structure, but application services are large.

## Evidence

- 72 Python files, about 13935 lines after the current OAuth/query/action/settings/service
  rule split.
- Large files include `application/oauth.py` (677), `application/services.py`
  (517), `infrastructure/persistence/repository_mappers.py` (479),
  `application/read_models.py` (471),
  `infrastructure/persistence/repositories.py` (471),
  `application/migration.py` (463), and `application/settings_integration.py`
  (450).

## Findings

- Access/Authorization separation is a strong architectural choice.
- OAuth is partially split: protocols/DTOs, redaction, token endpoint HTTP,
  setup-session payload shaping, Codex callback/browser opener logic, and
  Codex identity extraction, token payload/scope/subject normalization, PKCE,
  small text normalization helpers, provider/account record construction, token
  document construction, account status replacement, refresh account shaping, and
  Settings credential-binding request construction now live outside `oauth.py`;
  account lifecycle coordination still remains there.
- Query is now a small provider facade after result/assets/overview/record-model/
  requirements/record-collection/audit-window extraction. Actions is now a thin action coordinator after contracts,
  payload/redaction/change parsing, requirement-readiness helpers, setup/verify
  handlers, and OAuth handlers were split out.
  Settings integration is now a medium-sized adapter after settings action
  contracts, payload parsing, record mapping, credential binding conversion, and
  consumer binding conversion, and config view/provider extraction were split out.
  Read model payload timestamp/redaction/source-safety helpers are now split out.
  Inventory requirement check specs, labels, masking, and metadata redaction helpers
  are now split out.
  Migration legacy value extraction and migration requirement/credential payload
  rules are now split out.
  Persistence repository model/record mappers are now split out.
  Access service requirement/binding
  parsing rules, credential resolver IO, credential resolution audit/event payload
  rules, setup-flow object construction, and configured credential interpretation
  are now split out; services now mainly own requirement readiness, setup routing,
  credential resolution event publication, and public application-service methods.
- Settings integration must not turn Access into a generic settings owner.
- External credential lifecycle needs auditable state transitions.

## Launch Risks

- Credential readiness bugs can cause agent/tool/LLM failures that look like model failures.
- Multi-user deployments need tenant/account isolation, secret redaction, and lease tracking.
- OAuth refresh and revocation paths now have endpoint retry/redacted-error coverage
  plus storage-key locking for auto-refresh/revoke coordination; audit persistence
  hardening remains.

## Recommendations

- Split OAuth flow, credential binding, readiness query, lease, and audit operations.
- Add production checks for secret redaction in logs/events/projections.
- Keep Authorization imports out of Access.
- Add end-to-end readiness tests for LLM, Tool, Channel, Browser credential consumers.

## Detailed Pass 1

### Files Reviewed

- `application/oauth.py`
- `application/query.py`
- `application/settings_integration.py`
- `application/services.py`
- `application/actions.py`
- `application/inventory.py`
- `application/read_models.py`
- `application/setup.py`
- `application/migration.py`
- `infrastructure/persistence/repositories.py`
- `infrastructure/oauth_tokens.py`
- `interfaces/http.py`
- `interfaces/ui_http.py`
- `interfaces/inventory.py`

### File-Level Assessment

`application/oauth.py` is 677 lines after the current split. OAuth
repository/token-store contracts and result DTOs now live in
`application/oauth_contracts.py`; metadata redaction lives in
`application/oauth_redaction.py`; token endpoint HTTP behavior, retryable provider
HTTP/network failure handling, and redacted endpoint exceptions live in
`application/oauth_token_client.py`; setup-session record/result construction and
authorization/device-code payload shaping live in `application/oauth_setup_flows.py`;
local Codex callback/browser opener logic lives in
`application/oauth_callback_listener.py`; OpenAI Codex provider constants and
access-token identity extraction live in `application/oauth_codex.py`; token
payload expiry/scope/subject extraction, masking, PKCE challenge generation, and
small text normalization helpers live in `application/oauth_token_payloads.py`.
Provider/account record construction, token document construction, account status
replacement, refresh account shaping, and Settings credential-binding request
construction live in `application/oauth_account_records.py`. The file still owns
provider/account flow orchestration, account lifecycle coordination, token-store/
repository writes, and credential-binding registration side effects.

`application/query.py` is 273 lines after the query split. Query result DTOs now live
in `application/query_results.py`; synthetic asset summary/detail projection now
lives in `application/query_assets.py`; overview counts, empty overview, asset-list
projection, and readiness lookup now live in
`application/query_overview_assets.py`; read-model record shaping and consumer merge
rules now live in `application/query_record_models.py`; credential requirement rows
and grouped requirement payloads now live in `application/query_requirements.py`.
Settings/Access owner record collection and setup/OAuth/readiness model conversion
now live in `application/query_records.py`; Access/Settings audit pagination,
merge, and sorting now live in `application/query_audits.py`. The file now owns only
public query-service methods and endpoint payload composition.

`application/inventory.py` is 426 lines after the inventory rule split. Requirement
check-spec construction, credential binding labels, requirement masking, and
credential asset kind calculation now live in
`application/inventory_requirement_rules.py`. Metadata redaction now lives in
`application/inventory_redaction.py`. The file now owns read-model inventory grouping,
usage summarization, and inventory payload assembly.

`application/migration.py` is 463 lines after the migration helper split. Legacy
object value extraction/list/dedupe helpers live in
`application/migration_value_helpers.py`. Migration credential-source shaping,
channel metadata requirement extraction, requirement-set normalization/masking,
credential binding migration matching, slug/digest generation, and redaction policy
payloads live in `application/migration_requirement_payloads.py`. The file now owns
snapshot DTOs, plan DTOs, legacy container snapshot assembly, and migration plan
builder coordination.

`infrastructure/persistence/repositories.py` is 471 lines after the persistence mapper
split. SQLAlchemy model/application record conversion, timestamp coercion, and text
validation now live in `infrastructure/persistence/repository_mappers.py`. The file
now owns repository transactions, SQL query construction, upsert lifecycle, and audit
state transitions.

`application/settings_integration.py` is 450 lines after the Settings adapter split.
Settings action contracts live in `application/settings_action_contracts.py`;
payload/change parsing lives in `application/settings_payloads.py`; Settings payload
to Access record mapping lives in `application/settings_record_models.py`;
credential binding update/source-ref validation lives in
`application/settings_credential_bindings.py`; consumer binding slot/requirement
mapping lives in `application/settings_consumer_bindings.py`; Settings materialized
config view/provider lives in `application/settings_config_views.py`. The file now
adapts Settings-owned access configuration actions into Access records and Settings
resource writes. The boundary is correct only if Settings remains governance input
and Access remains external credential owner.

`application/actions.py` is 311 lines after the action helper and handler split.
Action request/result contracts live in `application/action_contracts.py`; change
parsing lives in `application/action_changes.py`; redaction and raw-secret rejection
live in `application/action_redaction.py`; audit/event/result payload shaping lives
in `application/action_payloads.py`; credential requirement readiness lives in
`application/action_readiness.py`; setup and requirement verification handlers live
in `application/action_setup_handlers.py`; OAuth provider/setup/account handlers live
in `application/action_oauth_handlers.py`. The file now owns action audit lifecycle,
event publication, intent routing, and dangerous-action confirmation checks.

`application/services.py` is 517 lines after the requirement rule, credential
resolver, credential resolution audit, setup-flow construction, and configured
credential interpretation split. Public
requirement parsing, credential binding canonicalization, expected-kind detection,
and binding/source compatibility checks now live in
`application/credential_requirement_rules.py`. Env/file/literal credential source
resolution now lives in `application/credential_resolver.py`. Credential resolution
audit context, event payload construction, safe source refs, trace redaction,
consumer audit payloads, and audit text truncation now live in
`application/credential_resolution_audit.py`. Setup-flow object construction now
lives in `application/credential_setup_flows.py`. Configured credential record
lookup, source derivation, OAuth provider lookup, and configured credential
resolution now live in `application/configured_credentials.py`. The file still
centralizes requirement readiness, setup routing, credential resolution events, and
public application-service methods.

### Boundary Cleanliness

Access/Authorization separation is one of the system's healthier architectural
decisions: Access owns external provider/account/credential readiness; Authorization
owns internal ABAC/grants.

Risk pattern:

- Settings integration can accidentally make Settings the owner of Access truth.
- Query synthetic assets can hide missing explicit Access records.
- OAuth helper code can leak raw secrets into logs/events if redaction invariants are
  not enforced everywhere.

### Lifecycle Clarity

Access lifecycle should be:

1. provider/account/asset/credential binding exists
2. setup or OAuth flow establishes credential material
3. readiness snapshot is recorded
4. consumer binds to credential or requirement
5. lease/resolution serves runtime consumer
6. refresh/revoke/rotation changes readiness
7. audit event records action and redacted context

The lifecycle exists but is split across large files and many synthetic read models.

### Persistence And Efficiency

Postgres persistence plus token document storage is appropriate, but production mode
must be explicit about token store location, encryption/redaction, and failure modes.
Control-plane queries should avoid repeatedly synthesizing large views for every UI
request.

### Concurrency And Multi-User Readiness

Access is multi-user sensitive:

- token refresh should be serialized per account/provider
- credential leases should be scoped and auditable
- setup sessions need expiry and cleanup
- account isolation is mandatory
- audit records must never expose raw secrets

### External Integration Readiness

External consumers need stable readiness and setup errors. Tool, LLM, Channel,
Browser, Memory, and Skills should consume Access through typed readiness/resolution
ports rather than parsing Access UI read models.

### Remediation Checklist

- [x] Split `oauth.py` into provider/account repository port usage, setup flow, token exchange/refresh/revoke, callback listener, browser opener, and redaction helpers.
  Current progress: contracts/DTOs, redaction, token exchange/refresh/revoke HTTP,
  setup-session payload shaping, callback/browser opener, Codex identity
  extraction, token payload/scope/subject normalization, PKCE, provider/account
  record shaping, token document shaping, account status/refresh record shaping,
  Settings credential-binding request construction, and account lifecycle
  coordination now live outside the public OAuth service. `oauth.py` remains the
  application flow coordinator.
- [x] Split `query.py` into public facade, record collection, audit window, projection helpers, and synthetic compatibility adapter.
  Current progress: query result DTOs, synthetic asset compatibility projection,
  overview/assets projection, read-model record shaping/merge rules, credential
  requirement projection, Settings/Access record collection, and Access/Settings
  audit pagination/merge/sort are split out; `query.py` now owns only public
  query-service methods and endpoint payload composition.
- [x] Split `actions.py` into command handlers by action intent.
  Current progress: action contracts, change parsing, redaction/raw-secret rejection,
  audit/event/result payload shaping, credential requirement readiness, setup/verify
  handlers, and OAuth provider/setup/account handlers are split out. The remaining
  action file is intentionally the audit/event/routing coordinator.
- [x] Split read model payload/redaction helpers out of `read_models.py`.
  Current progress: timestamp payload, requirement normalization, slot binding
  normalization, setup-flow hint payloads, requirements-by-consumer grouping,
  source-ref masking, masked preview handling, and sensitive-key redaction live in
  `application/read_model_payloads.py`; `read_models.py` now contains only read
  model DTOs and `to_payload` methods.

### Verification

- `PYTHONPATH=src pytest -q tests/unit/test_access_oauth.py --tb=short` -> 14 passed.
- `python -m ruff check src/crxzipple/modules/access/application/oauth.py src/crxzipple/modules/access/application/oauth_account_lifecycle.py --ignore F401,I001,E501` -> passed.
- [x] Split inventory requirement/redaction helpers out of `inventory.py`.
  Current progress: requirement check-spec construction, credential binding labels,
  requirement masking, and credential asset kind calculation live in
  `application/inventory_requirement_rules.py`; inventory metadata redaction lives in
  `application/inventory_redaction.py`; `inventory.py` now owns grouping,
  summarization, and payload assembly.
- [x] Split migration legacy/payload helpers out of `migration.py`.
  Current progress: legacy object value extraction, list collection, and dedupe live
  in `application/migration_value_helpers.py`; credential source shaping, channel
  metadata requirement extraction, requirement-set normalization/masking, digest/
  slug generation, and redaction policy payloads live in
  `application/migration_requirement_payloads.py`; `migration.py` now owns snapshot,
  plan, and builder coordination.
- [x] Split persistence model/record mappers out of `repositories.py`.
  Current progress: SQLAlchemy model/application record conversion, timestamp
  coercion, and text validation live in
  `infrastructure/persistence/repository_mappers.py`; `repositories.py` now owns
  repository transactions, query construction, upsert lifecycle, and audit state
  transitions.
- [x] Split `settings_integration.py` into adapter, contracts, payload parsing, record mapping, credential binding conversion, and consumer binding conversion.
  Current progress: `settings_integration.py` is now the Settings action adapter and
  resource-write coordinator; focused `settings_*` modules own the pure conversion
  helpers and materialized config view/provider.
- [x] Add no-raw-secret tests for logs, events, projections, and exceptions.
  Current progress: Access has no module-local logging sink; HTTP responses,
  credential-resolution events/audit context, action audit payloads, read model/
  inventory projections, OAuth setup payloads, and OAuth refresh endpoint errors are
  covered by no-raw-secret assertions.
- [x] Add OAuth refresh/revoke retry and concurrency tests.
  Current progress: refresh/revoke lifecycle tests exist; refresh provider request
  retry, revoke transient retry, storage-key locking, and locked auto-refresh
  second-read behavior are covered.
- [x] Add readiness tests for current runtime Access consumers.
  Current progress: LLM credential injection and kind mismatch are covered by
  `test_access_llm_integration.py`; Tool requirement import/inventory readiness is
  covered by `test_access_tool_integration.py`; Channel credential binding slots are
  covered by `test_access_channel_requirements.py`; Browser access-binding proxy
  consumer projection and host-runner credential resolution are covered by
  `test_browser_access_requirements.py` and `test_browser_cdp_control.py`; Memory
  vector credential binding resolution is covered by
  `test_memory_access_requirements.py`. Skills currently exposes `required_access`
  declarations/runtime-request projection rather than direct Access credential
  resolution, so no resolver e2e is required until Skills becomes a runtime
  credential consumer.
- [x] Add an architecture test that Access does not import Authorization.
  Current progress: `test_access_and_authorization_do_not_cross_own_truth_boundaries`
  guards both Access -> Authorization and Authorization -> Access imports.
