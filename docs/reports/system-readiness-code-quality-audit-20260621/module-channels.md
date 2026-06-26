# Module Audit: channels

## Verdict

Medium-high risk. Channels own external ingress/egress and delivery semantics. Runtime implementation is large and needs lifecycle clarity before multi-user production.

## Evidence

- 43 Python files, about 9150 lines.
- Large files include `application/webhook_runtime.py` (705), `domain/value_objects.py` (607), `application/runtime_manager.py` (490), `application/lark_runtime.py` (489), and `application/web_runtime.py` (479). `application/services.py` is now a 15-line public export surface.
- Dead-letter query/replay HTTP shaping is isolated in `interfaces/http_dead_letters.py`.

## Findings

- Channels as owner of channel profile, binding, runtime, delivery/dead-letter, and transport interaction is correct.
- Runtime file is too large and may mix transport handling, binding, delivery, retry, and event emission.
- HTTP interface has been reduced to a thinner route composition surface: shared
  request/response DTOs now live in `interfaces/http_models.py`, shared account/access
  helpers in `interfaces/http_channel_helpers.py`, Lark event verification/decryption in
  `interfaces/http_lark_events.py`, Webhook inbound signature/route handling in
  `interfaces/http_webhook_inbound.py`, and the Web SSE channel stream endpoint plus
  stream-only DTOs in `interfaces/http_web_events.py`; dead-letter query/replay route
  projection now lives in `interfaces/http_dead_letters.py`.
- A duplicate, unused Lark message-normalization implementation was removed from the HTTP
  layer; the runtime uses the canonical `application/lark_messages.py` implementation.
- The Web channel runtime class now lives in `application/web_runtime.py`, and Webhook
  runtime lives in `application/webhook_runtime.py`; Lark runtime lives in
  `application/lark_runtime.py`; `runtime.py` now keeps only the shared bootstrap
  service.
- Lark/Webhook observe state helpers now live in `application/runtime_observation.py`; Lark session-message observation payload projection now lives in `application/lark_runtime_observation.py`; Lark outbound observe delivery payload building, artifact upload, and send calls now live in `application/lark_runtime_delivery.py`; Lark tenant-token and bot identity lookup/cache now live in `application/lark_runtime_identity.py`; Lark long-connection thread/SDK ingress now lives in `application/lark_runtime_long_connection.py`; Lark message-to-run submission now lives in `application/lark_runtime_submission.py`.
- Webhook inbound message-to-run submission, idempotency lookup, reply-address construction, interaction upsert, and orchestration turn submission now live in `application/webhook_runtime_submission.py`.
- Channel profile, interaction, and runtime registry management now live in focused
  `application/profile_service.py`, `application/interaction_service.py`, and
  `application/runtime_manager.py`; shared normalization/time helpers live in
  `application/service_helpers.py`; `application/services.py` is a stable export surface.
- Credential/access boundary must stay delegated to Access.

## Launch Risks

- Inbound/outbound delivery under concurrency may be hard to reason about.
- Dead-letter and replay semantics can drift if legacy behavior remains mixed with current runtime.
- External system onboarding requires stable webhook/inbox/lark contracts.

## Recommendations

- Split runtime by inbound, outbound, delivery state, dead-letter, retry, and transport adapter.
- Add delivery idempotency and retry invariant tests.
- Move DTO assembly out of `interfaces/http.py`.
- Document stable event contracts for external channel integrations.

## Detailed Pass 1

### Files Reviewed

- `application/runtime.py`
- `application/runtime_helpers.py`
- `application/runtime_observation.py`
- `application/lark_runtime_observation.py`
- `application/lark_runtime_delivery.py`
- `application/lark_runtime_identity.py`
- `application/lark_runtime_long_connection.py`
- `application/lark_runtime_submission.py`
- `application/payload_redaction.py`
- `application/webhook_runtime_submission.py`
- `application/lark_runtime.py`
- `application/web_runtime.py`
- `application/webhook_runtime.py`
- `application/services.py`
- `application/profile_service.py`
- `application/interaction_service.py`
- `application/runtime_manager.py`
- `application/service_helpers.py`
- `application/bindings.py`
- `application/control.py`
- `application/lark_messages.py`
- `application/event_contracts.py`
- `domain/entities.py`
- `domain/value_objects.py`
- `infrastructure/stores.py`
- `infrastructure/state_root.py`
- `interfaces/http.py`
- `interfaces/cli.py`

### File-Level Assessment

`application/runtime.py` is 263 lines and now defines only
`ChannelRuntimeBootstrapService`. Common runtime helpers live in
`application/runtime_helpers.py`, `WebChannelRuntimeService` lives in
`application/web_runtime.py`, `WebhookChannelRuntimeService` lives in
`application/webhook_runtime.py`, and `LarkChannelRuntimeService` lives in
`application/lark_runtime.py`. Lark runtime has been reduced to the transport service
facade and observe loop; it is no longer the largest Channels file.
Session-message observation payload projection has been extracted to
`application/lark_runtime_observation.py`, outbound observe delivery projection,
artifact upload, and send calls have been extracted to `application/lark_runtime_delivery.py`,
tenant-token/bot identity lookup plus caching have been extracted to
`application/lark_runtime_identity.py`, and long-connection thread/SDK ingress has been
extracted to `application/lark_runtime_long_connection.py`. Lark message-to-run
submission, reply-address construction, interaction upsert, and orchestration turn
submission have been extracted to `application/lark_runtime_submission.py`.

`application/runtime_observation.py` owns transport-neutral observe helpers for cursor
tracking, settled-state detection, and run-status projection. Lark/Webhook runtime files
reuse these helpers instead of duplicating observe state rules.

`application/webhook_runtime_submission.py` owns Webhook inbound submission into
orchestration. This mirrors the Lark submission split: transport runtime owns lifecycle,
observe delivery, and dead-letter behavior, while the submission helper owns profile
resolution, idempotency lookup, interaction binding, and `submit_turn` coordination.

`interfaces/http.py` was 1547 lines and is now 322 lines after moving shared HTTP
request/response DTOs into `interfaces/http_models.py`, shared account/profile/access
helpers into `interfaces/http_channel_helpers.py`, Lark event verification/decryption and
route handling into `interfaces/http_lark_events.py`, Webhook inbound signature and route
handling into `interfaces/http_webhook_inbound.py`, and the `/web/events` SSE endpoint,
stream event DTOs, direct live/observe projection, broadcast target matching, and SSE
formatting into `interfaces/http_web_events.py`, plus dead-letter query/replay projection
into `interfaces/http_dead_letters.py`. The main HTTP router now keeps profile, runtime,
and subscription route control flow.

`application/services.py` is now a thin export surface over profile, interaction, and
runtime-registry services. `application/profile_service.py` owns Channel profile config
use cases, `application/interaction_service.py` owns interaction/run/session binding
mutation, and `application/runtime_manager.py` owns runtime registration plus account and
connection bindings. `bindings.py` and `control.py` remain moderate in size and represent
the intended domain/application split.

### Boundary Cleanliness

The owner boundary is correct: Channels owns channel profile, binding, runtime,
delivery/dead-letter, and transport interaction. It should not own orchestration run
state or session item truth.

Current boundary pattern:

- Lark and Webhook message submission import orchestration/session concepts to submit
  turns and bind direct session scope. This is acceptable as application orchestration
  because both paths now stay behind focused submission runtimes instead of leaking into
  transport ingress/delivery loops.
- Web/Webhook/Lark runtimes still import session topic helpers to watch owner session
  events for outbound delivery. That is a runtime observation dependency, not a turn
  submission path; replacing it with another wrapper would add indirection without
  reducing owner coupling.
- Credential readiness must remain delegated to Access. Channel runtime can consume
  readiness/results, not infer credential truth.
- Lark/Web/Webhook-specific parsing should stay behind transport adapters.

### Lifecycle Clarity

The channel lifecycle should be explicit:

1. profile/binding exists
2. inbound message received or outbound delivery requested
3. channel runtime normalizes transport payload
4. application service submits or delivers through a narrow port
5. delivery/dead-letter/retry facts are persisted/emitted
6. Operations observes channel health and failures

This lifecycle exists but is hard to audit while concentrated in one runtime file.

### Persistence And Efficiency

Channel state uses local state root/store code plus event emission. Multi-user
production needs clear persistence rules for delivery state, dead-letter queues,
and idempotency keys. HTTP endpoints should not perform repeated wide scans to build
channel dashboards.

### Concurrency And Multi-User Readiness

Channels is externally-facing, so it needs stronger invariants than ordinary local
runtime code:

- inbound webhook idempotency
- outbound delivery idempotency
- retry/backoff and dead-letter ordering
- per-account/profile isolation
- bounded payload retention and redaction
- reliable event emission after delivery state changes

### External Integration Readiness

External channel consumers need stable contracts: webhook request shape, Lark message
normalization, outbound delivery result shape, dead-letter replay semantics, and
setup/readiness errors.

### Operations Event Contract Surface

Channels declares its current Operations-observable event surface in
`application/event_contracts.py`. Operations may read these contracts and the related
event records, but it must not infer missing channel truth from arbitrary topic names.

The stable channel-owned topic contracts are:

- `channel.broadcast` and `channel.broadcast.account`: broadcast topics for active Web
  channel/SSE clients. These are live delivery topics, not durable channel health truth.
- `channel.dead_letter` and `channel.dead_letter.runtime`: persistent failure facts for
  channel observation delivery. These are the primary event records Operations can use for
  channel dead-letter rows and failure summaries.
- `channel.connection.control`: transient per-connection control wakeups for active
  streams. These can explain live stream refresh behavior, but they are not historical
  delivery facts.

The stable channel-owned event definitions are:

- `channel.observation.dead_lettered`: terminal observation delivery failure after
  retries. Operations can display `outbound_id`, `conversation_id`, `session_key`,
  `status`, `attempt_count`, `created_at`, and routing fields as redacted diagnostics.
- `channel.connection.subscription_updated`: transient subscription refresh signal for
  active channel streams.

Projection rules:

- Operations Channels page may present the registered topic/definition/surface contracts
  from the event registries as read-only governance state.
- Operations Channels page may read `channel.dead_letter.*` event records as retained
  failure facts.
- HTTP dead-letter listing and Operations projections must redact callback URLs, webhook
  callback URLs, tokens, secrets, authorization, cookies, and nested sensitive values via
  `application/payload_redaction.py`.
- Raw event payloads remain event-store truth for owner/runtime replay; redaction is an
  observation/read-model concern and must not mutate replay inputs.
- Session/orchestration events are correlated through explicit owner references only; they
  are not Channels-owned event contracts.

### Dead-Letter Replay Semantics

Webhook dead-letter replay is an explicit operator action. Each replay request attempts to
POST the retained outbound payload directly to the recorded callback URL, or to the
callback URL embedded in the retained reply address. Replay does not requeue a generic
legacy outbound event and does not suppress repeated operator requests through hidden
idempotency. A repeated replay request is a deliberate resend and should be visible as
another callback attempt at the external receiver. Automatic runtime retry/dead-letter
loops remain protected against duplicate emission by settled-state checks; manual replay
is intentionally separate from automatic retry.

### Remediation Checklist

- [x] Reduce `application/runtime.py` to shared bootstrap and split Web, Webhook, and Lark runtime ownership into transport-specific files.
- [x] Replace inline orchestration/session imports in transport code with narrow application ports where practical.
- [x] Move shared HTTP request/response DTOs out of `interfaces/http.py`.
- [x] Move shared profile/account/access helpers out of `interfaces/http.py`.
- [x] Move Lark event verification/decryption route out of `interfaces/http.py`.
- [x] Move Webhook inbound signature validation and route out of `interfaces/http.py`.
- [x] Remove duplicate unused Lark message normalization from HTTP layer.
- [x] Move Web SSE stream endpoint, stream DTOs, and SSE formatting out of `interfaces/http.py`.
- [x] Move Web channel runtime class out of `application/runtime.py`.
- [x] Move Webhook channel runtime class out of `application/runtime.py`.
- [x] Move Lark channel runtime class out of `application/runtime.py`.
- [x] Move Lark session-message observation payload projection out of `application/lark_runtime.py`.
- [x] Move Lark outbound observe delivery payload building, artifact upload, and send calls out of `application/lark_runtime.py`.
- [x] Move Lark tenant-token and bot identity lookup/cache out of `application/lark_runtime.py`.
- [x] Move Lark long-connection thread/SDK ingress out of `application/lark_runtime.py`.
- [x] Move Lark message-to-run submission out of `application/lark_runtime.py`.
- [x] Move Webhook inbound message-to-run submission out of `application/webhook_runtime.py`.
- [x] Move dead-letter replay response shaping out of `interfaces/http.py`.
- [x] Add Lark observe delivery regression coverage for duplicate successful message skips.
- [x] Add webhook inbound idempotency key support and duplicate submission regression coverage.
- [x] Add webhook automatic outbound retry/dead-letter duplicate-loop regression coverage.
- [x] Decide and document explicit dead-letter replay semantics: replay every request vs replay idempotency key.
- [x] Add payload redaction helper and tests for channel dead-letter HTTP and Operations projections.
- [x] Document channel event contracts consumed by Operations.

### Verification

```bash
python -m ruff check src/crxzipple/modules/channels/application/runtime.py src/crxzipple/modules/channels/application/lark_runtime.py src/crxzipple/modules/channels/application/lark_runtime_delivery.py src/crxzipple/modules/channels/application/lark_runtime_identity.py src/crxzipple/modules/channels/application/lark_runtime_long_connection.py src/crxzipple/modules/channels/application/lark_runtime_observation.py src/crxzipple/modules/channels/application/lark_runtime_submission.py src/crxzipple/modules/channels/application/payload_redaction.py src/crxzipple/modules/channels/application/runtime_helpers.py src/crxzipple/modules/channels/application/runtime_observation.py src/crxzipple/modules/channels/application/web_runtime.py src/crxzipple/modules/channels/application/webhook_runtime.py src/crxzipple/modules/channels/application/webhook_runtime_submission.py src/crxzipple/modules/channels/application/__init__.py src/crxzipple/modules/channels/interfaces/http.py src/crxzipple/modules/channels/interfaces/http_channel_helpers.py src/crxzipple/modules/channels/interfaces/http_dead_letters.py src/crxzipple/modules/channels/interfaces/http_lark_events.py src/crxzipple/modules/channels/interfaces/http_models.py src/crxzipple/modules/channels/interfaces/http_web_events.py src/crxzipple/modules/channels/interfaces/http_webhook_inbound.py
python -m py_compile src/crxzipple/modules/channels/application/runtime.py src/crxzipple/modules/channels/application/lark_runtime.py src/crxzipple/modules/channels/application/lark_runtime_delivery.py src/crxzipple/modules/channels/application/lark_runtime_identity.py src/crxzipple/modules/channels/application/lark_runtime_long_connection.py src/crxzipple/modules/channels/application/lark_runtime_observation.py src/crxzipple/modules/channels/application/lark_runtime_submission.py src/crxzipple/modules/channels/application/payload_redaction.py src/crxzipple/modules/channels/application/runtime_helpers.py src/crxzipple/modules/channels/application/runtime_observation.py src/crxzipple/modules/channels/application/web_runtime.py src/crxzipple/modules/channels/application/webhook_runtime.py src/crxzipple/modules/channels/application/webhook_runtime_submission.py src/crxzipple/modules/channels/application/__init__.py src/crxzipple/modules/channels/interfaces/http.py src/crxzipple/modules/channels/interfaces/http_channel_helpers.py src/crxzipple/modules/channels/interfaces/http_dead_letters.py src/crxzipple/modules/channels/interfaces/http_lark_events.py src/crxzipple/modules/channels/interfaces/http_models.py src/crxzipple/modules/channels/interfaces/http_web_events.py src/crxzipple/modules/channels/interfaces/http_webhook_inbound.py
PYTHONPATH=src pytest -q tests/unit/test_channels.py::ChannelsModuleTestCase::test_lark_observe_delivery_skips_duplicate_successful_message --tb=short
PYTHONPATH=src pytest -q tests/unit/test_channels.py::ChannelsModuleTestCase::test_webhook_observe_delivery_retries_and_dead_letters_failed_callback --tb=short
PYTHONPATH=src pytest -q tests/unit/test_channels_http.py::ChannelsHttpTestCase::test_webhook_inbound_endpoint_reuses_idempotent_submission --tb=short
PYTHONPATH=src pytest -q tests/unit/test_channels_http.py::ChannelsHttpTestCase::test_channel_dead_letters_endpoint_lists_runtime_dead_letters tests/unit/test_ui_operations_http.py::UiOperationsHttpTestCase::test_ui_operations_channels_page_uses_runtime_and_event_state --tb=short
PYTHONPATH=src pytest -q tests/unit/test_channels.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_channels_http.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_channels.py tests/unit/test_channels_http.py tests/unit/test_channel_bindings.py tests/unit/test_access_channel_requirements.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_channel_memory_runtime_settings_integration.py tests/unit/test_channel_bindings.py tests/unit/test_access_channel_requirements.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_ui_access_http.py tests/unit/test_ui_operations_actions_http.py --tb=short
```
