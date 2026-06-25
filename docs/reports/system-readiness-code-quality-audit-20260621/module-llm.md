# Module Audit: llm

## Verdict

High importance, medium-high risk. The module owns a critical provider boundary and has recently moved toward response-item fidelity and provider-specific rendering. The direction is correct, but provider adapter complexity and runtime request structures still need strong guardrails.

## Evidence

- 109 Python files, about 18519 lines.
- Cross-module import signal: very high.
- Large files include `interfaces/cli.py` (381), `application/runtime_request_factory.py` (381), `infrastructure/adapters/openai_codex_responses.py` (378), `infrastructure/adapters/openai_codex_responses_renderer.py` (364), `infrastructure/adapters/openai_responses.py` (347), and `infrastructure/adapters/gemini_generate_content.py` (340).

## Findings

- Provider-specific rendering belongs here, and that boundary is aligned with the current architecture.
- The module has many projection concepts: runtime request, transcript, provider preview, adapter request, invocation events, streaming runners. These are valid, but naming and ownership must remain crisp.
- Provider adapters are large; this can hide provider-specific fallback behavior or subtle protocol mismatches.
- Domain value objects have been split into focused value modules; remaining structural pressure is now concentrated in provider adapters, request factory assembly, and interface command surfaces.
- Core runtime request, Codex renderer, adapter, settings, and Access/LLM integration tests already provide a useful regression baseline; the remaining work is structural split and broader provider golden parity, not an absence of tests.

## Launch Risks

- Provider drift can create behavior differences that are hard to observe unless request/response snapshots are retained consistently.
- Streaming and non-streaming invocation paths can diverge.
- Multi-provider support may degrade if OpenAI/Codex assumptions leak into neutral application objects.

## Recommendations

- Keep a strict adapter symmetry: provider request renderer and provider response parser both stay in LLM adapter layer.
- Add provider golden tests comparing provider-neutral input items to actual wire payload for each supported transport.
- Split large provider adapters by request render, event parse, response item map, continuation metadata, and error mapping.
- Keep provider request preview as observation only; do not let preview become execution truth.

## Detailed Pass 1

### Files Reviewed

- `application/runtime_request.py`
- `application/session_runtime_transcript.py`
- `application/runtime_request_factory.py`
- `application/llm_invocation_runner.py`
- `application/llm_streaming_invocation_runner.py`
- `application/services.py`
- `infrastructure/adapters/openai_codex_responses.py`
- `infrastructure/adapters/openai_chat_compatible.py`
- `infrastructure/adapters/provider_router.py`
- `infrastructure/adapters/*_renderer.py`
- `interfaces/http.py`
- `domain/*_values.py`

### File-Level Assessment

`application/runtime_request.py` was 1154 lines and is now 242 lines after moving
request metadata preview, request-render snapshot preview, estimate summary, and
snapshot diagnostics into `runtime_request_preview.py`, then moving runtime Tool Surface
refs, schema ref projection, Tool Surface request metadata, schema de-duplication, and
request-time Tool Surface uniqueness into `runtime_tool_surface.py`, then moving runtime
input item projection, message fallback conversion, provider context message extraction,
vision-capability sanitization, transcript input fallback, and input mode metadata into
`runtime_input_items.py`, then moving request render snapshot models, metadata builders,
and renderer context projection into `runtime_request_snapshot.py`. It now contains the
neutral request shell, route, render policy, transcript wrapper, request metadata merge,
provider override merge, and payload conversion.

`application/session_runtime_transcript.py` was 965 lines and is now 289 lines after
moving protocol-required item classification, session budget refs, tool protocol
diagnostics, and protocol normalization diagnostics into `session_runtime_protocol.py`;
SessionItem to LLM message/input item mapping, replayable-content checks, assistant
progress de-duplication, and tool-result model text rendering into
`session_runtime_items.py`; content char/token estimates and item truncation into
`session_runtime_item_metrics.py`; tool-result stats into
`session_runtime_tool_result_stats.py`; and recent-window budget truncation, budget
report, protocol preservation diagnostics, and replay frontier into
`session_runtime_budget.py`. It now owns the replay window builder, current inbound
transcript construction, current-turn protocol filtering, and paired tool call/result
normalization.

`application/session_runtime_items.py` was 427 lines and is now 283 lines after moving
content char/token metrics and recent-text truncation into
`session_runtime_item_metrics.py`, and tool-result compaction/read-handle/artifact stats
into `session_runtime_tool_result_stats.py`. It now owns only SessionItem to neutral LLM
message/input item projection, content extraction, replayability checks, assistant
progress de-duplication, and compact tool-result payload rendering.

`application/runtime_request_factory.py` was 698 lines and is now 480 lines after
moving request-render snapshot Tool Surface schema extraction and resolved-tool
projection into `runtime_request_tool_surface_builder.py`, then moving request-render
projected input restoration, orphan function-call filtering, and request-context source
lookup into `runtime_request_input_filter.py`. It still owns the draft to runtime request
envelope assembly, validation, request-render snapshot report stitching, tool-surface
snapshot persistence, and runtime context metadata projection.

`application/llm_profile_service.py` was 410 lines and is now 337 lines after moving
provider/api-family credential expectation, Access credential metadata kind matching,
binding type labels, and optional string normalization into `llm_profile_credentials.py`.
The service now keeps profile lifecycle, persistence, and event recording as its primary
responsibility. Its credential provider is now an explicit mutable property so the outer
application service can keep profile validation aligned with runtime credential changes.

`application/services.py` was 406 lines and is now 338 lines after moving LLM profile
warmup lifecycle, adapter warmup capability checks, resolved-credential warmup dispatch,
and profile warmup event recording into `llm_profile_warmup.py`. The application service
now remains a thinner facade over profile, invocation, streaming, warmup, and query
surfaces. Reassigning `credential_provider` on the facade now synchronizes the profile
service and adapter request builder, preventing profile validation and invocation
credential resolution from diverging.

`application/llm_streaming_invocation_runner.py` was 419 lines and is now 278 lines
after moving stream event normalization, response-event persistence, completed-event
projection to response items/continuation, and streaming failure event construction into
`llm_streaming_event_recorder.py`. The runner now owns only sync/async stream loop
control, request building, provider preview recording, concurrency limiting, and sync
iterator bridging.

`application/tool_result_model_text.py` was 361 lines and is now 156 lines after moving
bounded field extraction, artifact/ref list normalization, optional primitive parsing,
detail fact extraction, result excerpt selection, and content-block excerpt parsing into
`tool_result_replay_fields.py` and `tool_result_replay_excerpt.py`. The main module now
owns only the model-visible tool-result replay text envelope.

`infrastructure/persistence/repositories.py` was 353 lines and is now 119 lines after
moving LLM profile, invocation, response item, and response event SQLAlchemy/domain
mapping into `repository_mappers.py`. Repository classes now own only add/get/list/query
operations and delegate all record shaping to the mapper module.

`application/llm_invocation_events.py` was 342 lines and is now 116 lines after moving
runtime request summary construction into `llm_invocation_runtime_summary.py`, terminal
succeeded/failed payload builders and result summarization into
`llm_invocation_terminal_events.py`, and streaming completed-payload response-item /
continuation extraction into `llm_completed_payload.py`. The events module now owns only
started, provider-request-prepared, and profile-warmup event payloads.

`application/runtime_request_factory.py` was 480 lines and is now 381 lines after moving
request metadata construction, request-render snapshot report construction, mode
classification, validation error creation, runtime-context metadata projection, and
request-render snapshot DTO projection into `runtime_request_factory_helpers.py`. The
factory now stays focused on request-envelope orchestration, tool surface selection,
runtime input filtering, and final `RuntimeLlmRequest` assembly.

`domain/value_objects.py` was 930 lines and has been retired. Provider/profile enums now
live in `enums.py`; profile defaults and provider config values live in
`profile_values.py`; messages, input items, tool schemas, and request payload values live
in `message_values.py`; invocation result, usage, and tool-call intent values live in
`result_values.py`; response items, response events, and `utcnow` live in
`response_values.py`; continuation metadata lives in `continuation_values.py`; and error
payloads live in `error_values.py`. The domain package still exports the stable public
names through `domain/__init__.py`, while domain internals import focused concrete modules
to avoid circular package dependencies.

Provider adapters and renderers are numerous and appropriately located under LLM infrastructure. File size indicates provider complexity, especially OpenAI/Codex and chat-compatible adapters.

`infrastructure/adapters/openai_codex_responses.py` was 1102 lines and is now 378
lines after moving Codex SSE/WebSocket event parsing, completed-event response item
projection, continuation extraction, response.completed output reconstruction, and
websocket continuation-fallback metadata shaping into `openai_codex_streaming.py`, then
moving WebSocket pool management, endpoint/header construction, connection close checks,
and retryable WebSocket exception classification into `openai_codex_websocket_transport.py`,
then moving HTTP SSE request headers, sync POST stream dispatch, and async stream
connection construction into `openai_codex_http_transport.py`, then moving completed-event
adapter response projection into `openai_codex_completion.py`, and HTTP SSE retry/dispatch
plus HTTP wire request construction into `openai_codex_http_dispatch.py`. The adapter now
owns provider selection, WebSocket dispatch/pool lifecycle, warmup, preview, and wire
wrappers; focused streaming, completion, HTTP dispatch, HTTP transport, and WebSocket
transport modules own provider response parsing and connection mechanics.

`infrastructure/adapters/openai_codex_streaming.py` is now 200 lines after moving Codex
provider event projection, completed-event response item extraction, continuation
extraction, WebSocket continuation fallback metadata shaping, and response.completed
result construction into `openai_codex_event_projection.py`. The streaming module now
only owns sync SSE, async SSE, and WebSocket stream reading loops.

`infrastructure/adapters/openai_codex_responses_renderer.py` was 517 lines and is now
365 lines after moving runtime context prompt item construction into
`openai_codex_runtime_context.py` and provider-native WebSocket continuation delta
selection into `openai_codex_continuation.py`. `provider_router.py` no longer imports a
private renderer helper for WebSocket endpoint conversion; it uses the Codex WebSocket
transport endpoint helper.

`infrastructure/adapters/openai_chat_compatible.py` was 1008 lines and is now 280
lines after moving OpenAI-compatible JSON response projection, SSE parsing, JSON fallback
stream projection, XML-ish tool call fallback parsing, streamed tool-call chunk merging,
and response-item construction into `openai_chat_compatible_projection.py`. The adapter
now owns only profile credential headers, wire request construction, HTTP dispatch, and
stream dispatch.

`infrastructure/adapters/openai_chat_compatible_projection.py` was 729 lines and is now
319 lines after moving chat completed-event construction, JSON fallback result
projection, streamed tool-call chunk merging, XML-ish tool-call fallback parsing, and
response-item construction into `openai_chat_compatible_events.py`. The projection
module now owns only sync/async SSE parsing and non-SSE fallback detection, while keeping
the previous public import surface explicit through `__all__`.

`infrastructure/adapters/openai_chat_compatible_events.py` is now 269 lines after
moving Chat message/tool-call normalization, XML-ish fallback tool-call parsing, stripped
assistant text construction, and Chat response item projection into
`openai_chat_compatible_response_items.py`. The events module now owns completed-event
construction, usage/result projection, stream tool-call chunk merging, and adapter
response assembly.

`infrastructure/adapters/openai_responses.py` was 701 lines and is now 345 lines after
moving OpenAI Responses SSE parsing, completed-event response item projection,
continuation extraction, response.completed output reconstruction, and retryable error
event mapping into `openai_responses_streaming.py`. The adapter now owns request retry
flow, credential headers, HTTP dispatch, provider wire request construction, and payload
preview helpers.

`infrastructure/adapters/openai_responses_streaming.py` is now 162 lines after moving
OpenAI Responses provider event projection, completed-event response item extraction,
continuation extraction, retryable error-event mapping, and response.completed result
construction into `openai_responses_event_projection.py`. The streaming module now only
owns sync and async SSE stream reading loops.

`infrastructure/adapters/provider_message_projection.py` was retired after moving
neutral message-to-input-item conversion and shared content-block helpers into
`provider_message_common.py`, OpenAI Chat/Responses input projection into
`provider_openai_message_projection.py`, Anthropic Messages input projection into
`provider_anthropic_message_projection.py`, and Gemini content/system part projection
into `provider_gemini_message_projection.py`. Provider renderers and tests now import
the focused modules directly, leaving no compatibility facade.

`interfaces/http.py` was 808 lines and is now 299 lines after moving HTTP request and
response Pydantic models into `interfaces/http_models.py`, HTTP-to-application request
mapping into `interfaces/http_request_mapping.py`, domain-to-HTTP response projection
and runtime request preview projection into `interfaces/http_response_mapping.py`, and
SSE event formatting into `interfaces/http_sse.py`. The previous mixed
`interfaces/http_mapping.py` module has been retired; Workbench imports the explicit
response mapper directly.

`interfaces/cli.py` was 561 lines and is now 381 lines after moving JSON option parsing,
CLI profile input construction, tool schema/message parsing, and invocation request
preview reporting into `interfaces/cli_payloads.py`. The Typer module now stays focused
on command declarations, authorization, service calls, and output formatting.

`infrastructure/adapters/provider_request_preview.py` was 613 lines and is now 333
lines after moving provider payload fingerprinting, safe preview truncation, and payload
type helpers into `provider_request_preview_utils.py`, and tool-surface/tool-protocol
render-report projection into `provider_request_tool_preview.py`. The remaining module
owns provider preview assembly, runtime preview, input-item mapping, and request metadata
preview merging.

### Boundary Cleanliness

The main boundary is correct:

- LLM owns provider profiles, invocation records, request rendering, response parsing, and provider-specific protocol details.
- Orchestration should pass a neutral envelope/request, not construct provider wire payloads.
- Session/Context Workspace provide facts and selected slices; LLM renderer translates them.

Risk pattern:

- `runtime_request.py` and `session_runtime_transcript.py` are now small enough to serve
  as facades for neutral request and replay-window assembly; the remaining large-file
  pressure has shifted to provider adapters, provider message projection, and request
  factory validation/assembly.
- Provider preview must not become a source of runtime truth.
- Chat-compatible fallbacks must not weaken item-level protocol guarantees for providers that support structured input.

### Lifecycle Clarity

LLM lifecycle includes profile resolution, request build, concurrency gating, provider invocation, streaming/non-streaming response item capture, persistence, event publishing, and response summary derivation.

Potential lifecycle confusion:

- streaming and non-streaming runners must produce equivalent invocation/result facts.
- provider response event retention policy must remain observation/persistence policy, not runtime decision logic.

### Persistence And Efficiency

LLM invocation persistence is correct. Efficiency risk lies in storing large request previews/response events and rendering large transcript windows.

Production requirement:

- Persist durable response items and compact summaries.
- Keep full debug payload retention bounded.
- Avoid rendering large provider previews on every Operations page request.

### Concurrency And Multi-User Readiness

Concurrency limiter and profile-level config are essential. Additional pressure points:

- provider rate limits
- streaming connection cleanup
- retry/error mapping
- warmup connections
- tenant/profile isolation

### External Integration Readiness

External provider integration is a strength if adapter boundaries stay clean. Each provider should have:

- model/profile capabilities
- request renderer golden fixtures
- response parser golden fixtures
- error mapping
- streaming behavior contract

### Remediation Checklist

- [x] Split `runtime_request.py` into focused preview, Tool Surface, input item, render snapshot, and neutral request-shell modules.
- [x] Split runtime request preview/diagnostics helpers out of `runtime_request.py`.
- [x] Split runtime Tool Surface structures and metadata projection out of `runtime_request.py`.
- [x] Split runtime input item projection and capability sanitization out of `runtime_request.py`.
- [x] Split request factory Tool Surface snapshot projection out of `runtime_request_factory.py`.
- [x] Split request factory request-render input restoration and orphan tool-call filtering out of `runtime_request_factory.py`.
- [x] Split LLM profile credential expectation and Access binding metadata rules out of `llm_profile_service.py`.
- [x] Split LLM profile warmup lifecycle and warmup event recording out of `services.py`.
- [x] Split streaming event normalization, completion projection, and failure recording out of `llm_streaming_invocation_runner.py`.
- [x] Split `session_runtime_transcript.py` into replay window facade, item mapping, protocol normalization, and budget/truncation modules.
- [x] Split session runtime protocol diagnostics and budget refs out of `session_runtime_transcript.py`.
- [x] Split session runtime content metrics/truncation and tool-result stats out of `session_runtime_items.py`.
- [x] Split tool-result replay field/excerpt helpers out of `tool_result_model_text.py`.
- [x] Split LLM persistence SQLAlchemy/domain mappers out of `infrastructure/persistence/repositories.py`.
- [x] Split runtime request summary, terminal payloads, and completed-payload extraction out of `llm_invocation_events.py`.
- [x] Split request factory metadata/snapshot/mode/validation helpers out of `runtime_request_factory.py`.
- [x] Split Codex Responses stream parsing and completed-event projection out of `openai_codex_responses.py`.
- [x] Split Chat Compatible JSON/SSE response projection out of `openai_chat_compatible.py`.
- [x] Split OpenAI Responses stream parsing and completed-event projection out of `openai_responses.py`.
- [x] Split OpenAI Responses provider event projection out of `openai_responses_streaming.py`.
- [x] Split provider message projection into common, OpenAI, Anthropic, and Gemini modules.
- [x] Retire provider message projection compatibility facade and import focused projection modules directly.
- [x] Split LLM HTTP router models and mapping out of `interfaces/http.py`.
- [x] Retire mixed LLM HTTP mapping module by splitting request mapping, response mapping, and SSE formatting into focused interface modules.
- [x] Split LLM CLI payload parsing and request-preview reporting out of `interfaces/cli.py`.
- [x] Retire monolithic LLM `domain/value_objects.py` into focused value modules and remove direct old-path imports.
- [x] Split provider request preview utility and tool-report projection out of `provider_request_preview.py`.
- [x] Split Chat Compatible completed-event and response-item projection out of `openai_chat_compatible_projection.py`.
- [x] Split Chat Compatible response item projection and XML-ish fallback tool-call parsing out of `openai_chat_compatible_events.py`.
- [x] Split Codex WebSocket pool and transport helpers out of `openai_codex_responses.py`.
- [x] Split Codex HTTP SSE transport helpers out of `openai_codex_responses.py`.
- [x] Split Codex renderer runtime-context and provider-native continuation helpers out of `openai_codex_responses_renderer.py`.
- [x] Split Codex completed-event adapter response projection out of `openai_codex_responses.py`.
- [x] Split Codex HTTP SSE retry/dispatch and HTTP wire request construction out of `openai_codex_responses.py`.
- [x] Split Codex provider event projection out of `openai_codex_streaming.py`.
- [x] Add provider golden tests for OpenAI Responses, Codex Responses, Chat Compatible, Anthropic Messages, Gemini Generate Content.
- [x] Ensure streaming and non-streaming paths emit equivalent response item facts.
- [x] Add request render budget tests for long sessions.
- [x] Keep provider-specific fields out of neutral application/domain objects unless explicitly modeled.

### Current Verification Baseline

Command passed during this audit wave:

```bash
python -m ruff check src/crxzipple/modules/llm/application/runtime_request.py src/crxzipple/modules/llm/application/runtime_request_preview.py src/crxzipple/modules/llm/application/llm_invocation_events.py src/crxzipple/modules/llm/application/provider_request_input_preview.py src/crxzipple/modules/llm/interfaces/http.py src/crxzipple/modules/operations/application/read_models/llm_provider_request_diagnostics.py
python -m ruff check tests/unit/test_runtime_llm_request.py
python -m ruff check src/crxzipple/modules/llm/application/session_runtime_transcript.py src/crxzipple/modules/llm/application/session_runtime_protocol.py
python -m ruff check src/crxzipple/modules/llm/application/session_runtime_transcript.py src/crxzipple/modules/llm/application/session_runtime_items.py src/crxzipple/modules/llm/application/session_runtime_budget.py tests/unit/test_runtime_transcript.py
python -m ruff check src/crxzipple/modules/llm/application/runtime_request.py src/crxzipple/modules/llm/application/runtime_request_snapshot.py src/crxzipple/modules/llm/application/runtime_input_items.py src/crxzipple/modules/llm/application/runtime_tool_surface.py src/crxzipple/modules/llm/application/runtime_request_factory.py src/crxzipple/modules/llm/application/llm_adapter_request_builder.py src/crxzipple/modules/llm/application/__init__.py tests/unit/test_runtime_llm_request.py
python -m ruff check src/crxzipple/modules/llm/application/runtime_request_factory.py src/crxzipple/modules/llm/application/runtime_request_tool_surface_builder.py tests/unit/test_runtime_llm_request.py tests/unit/test_llm_runtime_request_factory.py tests/unit/test_llm_runtime_request_factory_builder.py
python -m ruff check src/crxzipple/modules/llm/application/runtime_request_factory.py src/crxzipple/modules/llm/application/runtime_request_input_filter.py tests/unit/test_runtime_llm_request.py tests/unit/test_llm_runtime_request_factory.py tests/unit/test_llm_runtime_request_factory_builder.py
python -m ruff check tests/unit/test_llm_runtime_request_factory.py
python -m ruff check src/crxzipple/modules/llm/application/llm_profile_service.py src/crxzipple/modules/llm/application/llm_profile_credentials.py tests/unit/test_llm.py tests/unit/test_access_llm_integration.py tests/unit/test_llm_http.py
python -m ruff check src/crxzipple/modules/llm/application/services.py src/crxzipple/modules/llm/application/llm_profile_warmup.py tests/unit/test_llm.py tests/unit/test_llm_http.py tests/unit/test_operations_llm_read_model.py
python -m ruff check src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_responses.py src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_streaming.py
python -m ruff check src/crxzipple/modules/llm/infrastructure/adapters/openai_chat_compatible.py src/crxzipple/modules/llm/infrastructure/adapters/openai_chat_compatible_projection.py
python -m ruff check src/crxzipple/modules/llm/infrastructure/adapters/openai_responses.py src/crxzipple/modules/llm/infrastructure/adapters/openai_responses_streaming.py
python -m ruff check src/crxzipple/modules/llm/infrastructure/adapters/openai_responses.py src/crxzipple/modules/llm/infrastructure/adapters/openai_responses_streaming.py src/crxzipple/modules/llm/infrastructure/adapters/openai_responses_event_projection.py tests/unit/test_llm_adapters.py tests/unit/test_llm_http.py
python -m ruff check src/crxzipple/modules/llm/infrastructure/adapters/provider_message_common.py src/crxzipple/modules/llm/infrastructure/adapters/provider_openai_message_projection.py src/crxzipple/modules/llm/infrastructure/adapters/provider_anthropic_message_projection.py src/crxzipple/modules/llm/infrastructure/adapters/provider_gemini_message_projection.py src/crxzipple/modules/llm/infrastructure/adapters/anthropic_messages_renderer.py src/crxzipple/modules/llm/infrastructure/adapters/gemini_generate_content_renderer.py src/crxzipple/modules/llm/infrastructure/adapters/openai_chat_compatible_renderer.py src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_responses_renderer.py src/crxzipple/modules/llm/infrastructure/adapters/openai_responses_renderer.py
python -m ruff check src/crxzipple/modules/llm/interfaces/http.py src/crxzipple/modules/llm/interfaces/http_models.py src/crxzipple/modules/llm/interfaces/http_request_mapping.py src/crxzipple/modules/llm/interfaces/http_response_mapping.py src/crxzipple/modules/llm/interfaces/http_sse.py src/crxzipple/modules/workbench/interfaces/http.py
python -m ruff check src/crxzipple/modules/llm/interfaces/cli.py src/crxzipple/modules/llm/interfaces/cli_payloads.py
python -m ruff check src/crxzipple/modules/llm/infrastructure/adapters/provider_request_preview.py src/crxzipple/modules/llm/infrastructure/adapters/provider_request_preview_utils.py src/crxzipple/modules/llm/infrastructure/adapters/provider_request_tool_preview.py
python -m ruff check src/crxzipple/modules/llm/infrastructure/adapters/openai_chat_compatible_projection.py src/crxzipple/modules/llm/infrastructure/adapters/openai_chat_compatible_events.py src/crxzipple/modules/llm/infrastructure/adapters/openai_chat_compatible.py
python -m ruff check src/crxzipple/modules/llm/infrastructure/adapters/openai_chat_compatible_events.py src/crxzipple/modules/llm/infrastructure/adapters/openai_chat_compatible_response_items.py src/crxzipple/modules/llm/infrastructure/adapters/openai_chat_compatible_projection.py src/crxzipple/modules/llm/infrastructure/adapters/openai_chat_compatible.py tests/unit/test_llm_adapters.py
python -m ruff check tests/unit/test_provider_request_renderer_protocol.py
python -m ruff check tests/unit/test_llm_adapters.py
python -m ruff check src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_responses.py src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_websocket_transport.py tests/unit/test_llm_adapters.py tests/unit/test_openai_codex_transport_wire_contract.py
python -m ruff check src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_responses.py src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_http_transport.py src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_websocket_transport.py tests/unit/test_llm_adapters.py tests/unit/test_openai_codex_transport_wire_contract.py tests/unit/test_llm_http.py
python -m ruff check src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_responses_renderer.py src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_continuation.py src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_runtime_context.py src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_responses.py src/crxzipple/modules/llm/infrastructure/adapters/provider_router.py
python -m ruff check src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_responses.py src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_http_dispatch.py tests/unit/test_llm_adapters.py
python -m ruff check src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_streaming.py src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_event_projection.py src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_completion.py src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_responses.py tests/unit/test_llm_adapters.py tests/unit/test_openai_codex_transport_wire_contract.py
PYTHONPATH=src pytest -q tests/unit/test_runtime_llm_request.py tests/unit/test_operations_llm_provider_request_diagnostics.py tests/unit/test_llm_http.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_runtime_llm_request.py::test_llm_request_keeps_provider_wire_fields_inside_provider_options tests/unit/test_runtime_llm_request.py::test_llm_request_metadata_keeps_runtime_refs_separate_from_wire_payload tests/unit/test_runtime_llm_request.py::test_llm_request_provider_overrides_merge_reasoning_config --tb=short
PYTHONPATH=src pytest -q tests/unit/test_runtime_transcript.py tests/unit/test_runtime_llm_request_draft_collector.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_runtime_llm_request.py tests/unit/test_llm_runtime_request_factory.py tests/unit/test_llm_runtime_request_factory_builder.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_runtime_llm_request.py tests/unit/test_llm_runtime_request_factory.py tests/unit/test_llm_runtime_request_factory_builder.py tests/unit/test_openai_codex_renderer.py tests/unit/test_llm_adapters.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_runtime_llm_request.py tests/unit/test_llm_runtime_request_factory.py tests/unit/test_llm_runtime_request_factory_builder.py tests/unit/test_openai_codex_renderer.py tests/unit/test_llm_adapters.py tests/unit/test_llm.py tests/unit/test_llm_settings_integration.py tests/unit/test_access_llm_integration.py tests/unit/test_runtime_transcript.py tests/unit/test_runtime_llm_request_draft_collector.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_runtime_llm_request.py tests/unit/test_llm_runtime_request_factory.py tests/unit/test_llm_runtime_request_factory_builder.py tests/unit/test_openai_codex_renderer.py tests/unit/test_llm_adapters.py tests/unit/test_llm.py tests/unit/test_llm_settings_integration.py tests/unit/test_access_llm_integration.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_llm_runtime_request_factory.py::test_long_request_render_snapshot_uses_projected_items_not_collapsed_tree_body tests/unit/test_llm_runtime_request_factory.py::test_orchestration_builds_runtime_request_refs_not_provider_wire_input tests/unit/test_llm_runtime_request_factory.py::test_context_slice_runtime_control_items_do_not_become_llm_input --tb=short
PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py tests/unit/test_openai_codex_transport_wire_contract.py tests/unit/test_openai_codex_renderer.py tests/unit/test_provider_protocol_render_router.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py tests/unit/test_llm.py tests/unit/test_llm_settings_integration.py tests/unit/test_access_llm_integration.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_runtime_llm_request.py tests/unit/test_llm_runtime_request_factory.py tests/unit/test_llm_runtime_request_factory_builder.py tests/unit/test_openai_codex_renderer.py tests/unit/test_llm_adapters.py tests/unit/test_llm.py tests/unit/test_llm_settings_integration.py tests/unit/test_access_llm_integration.py tests/unit/test_runtime_transcript.py tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_openai_codex_transport_wire_contract.py tests/unit/test_provider_protocol_render_router.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py tests/unit/test_openai_codex_renderer.py tests/unit/test_openai_codex_transport_wire_contract.py tests/unit/test_provider_request_renderer_protocol.py tests/unit/test_provider_protocol_render_router.py tests/unit/test_anthropic_renderer.py tests/unit/test_provider_renderer_canonical_request_integration.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_runtime_llm_request.py tests/unit/test_llm_runtime_request_factory.py tests/unit/test_llm_runtime_request_factory_builder.py tests/unit/test_openai_codex_renderer.py tests/unit/test_llm_adapters.py tests/unit/test_llm.py tests/unit/test_llm_settings_integration.py tests/unit/test_access_llm_integration.py tests/unit/test_runtime_transcript.py tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_openai_codex_transport_wire_contract.py tests/unit/test_provider_protocol_render_router.py tests/unit/test_provider_request_renderer_protocol.py tests/unit/test_anthropic_renderer.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_llm_http.py tests/unit/test_llm.py tests/unit/test_llm_settings_integration.py tests/unit/test_access_llm_integration.py tests/unit/test_ui_http.py tests/unit/test_workbench_read_model.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_cli.py tests/unit/test_session_cli.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_openai_codex_renderer.py tests/unit/test_openai_codex_transport_wire_contract.py tests/unit/test_provider_request_trace_fixtures.py tests/unit/test_provider_request_renderer_protocol.py tests/unit/test_provider_protocol_render_router.py tests/unit/test_llm_adapters.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py -k 'chat_compatible' --tb=short
PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py tests/unit/test_openai_codex_renderer.py tests/unit/test_openai_codex_transport_wire_contract.py tests/unit/test_provider_request_renderer_protocol.py tests/unit/test_provider_protocol_render_router.py tests/unit/test_anthropic_renderer.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py tests/unit/test_openai_codex_renderer.py tests/unit/test_openai_codex_transport_wire_contract.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py tests/unit/test_openai_codex_renderer.py tests/unit/test_openai_codex_transport_wire_contract.py tests/unit/test_llm_http.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_openai_codex_renderer.py tests/unit/test_provider_renderer_canonical_request_integration.py tests/unit/test_provider_request_renderer_protocol.py tests/unit/test_provider_request_trace_fixtures.py tests/unit/test_provider_protocol_render_router.py tests/unit/test_llm_adapters.py tests/unit/test_openai_codex_transport_wire_contract.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_provider_request_renderer_protocol.py::test_provider_renderers_keep_canonical_request_wire_shapes_golden tests/unit/test_provider_request_renderer_protocol.py::test_renderers_translate_neutral_require_tool_call_policy tests/unit/test_provider_renderer_canonical_request_integration.py::test_same_canonical_request_renders_codex_native_and_anthropic_downgraded_reasoning --tb=short
PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py::LlmAdapterTestCase::test_openai_chat_compatible_stream_and_non_stream_emit_equivalent_response_items tests/unit/test_llm_adapters.py::LlmAdapterTestCase::test_openai_chat_compatible_adapter_shapes_request_and_result tests/unit/test_llm_adapters.py::LlmAdapterTestCase::test_openai_chat_compatible_adapter_stream_invoke_emits_text_delta_and_completed --tb=short
```

Result:

- `ruff`: passed
- Runtime request / Operations provider diagnostics / LLM HTTP preview suite: 32 passed
- Runtime request provider wire-field isolation suite: 3 passed
- Runtime request / request factory / request factory builder suite: 62 passed
- Runtime request factory / Codex renderer / LLM adapter suite after input-filter split: 149 passed
- Runtime request factory long-history budget suite: 3 passed
- LLM profile / Access credential / HTTP suite after profile credential split: 40 passed
- LLM profile warmup / HTTP / Operations read-model suite after warmup split: 39 passed
- Runtime transcript / runtime request draft suite: 29 passed
- `test_runtime_llm_request.py`: 21 passed
- Codex adapter / transport wire / renderer / provider render router suite: 102 passed
- LLM adapter / service / settings / Access integration suite: 114 passed
- Codex adapter / renderer / transport wire suite after WebSocket transport split: 89 passed
- Codex adapter / renderer / transport wire / LLM HTTP suite after HTTP transport split: 98 passed
- Codex renderer / router / adapter / trace fixture suite after renderer helper split: 116 passed
- Codex adapter / renderer / transport wire / LLM HTTP suite after HTTP dispatch split: 98 passed
- Codex adapter / renderer / transport wire / LLM HTTP suite after Codex event projection split: 98 passed
- LLM adapter / HTTP suite after OpenAI Responses event projection split: 86 passed
- Provider renderer/router suite after OpenAI Responses event projection split: 24 passed
- LLM request/render/provider combined suite after OpenAI Responses event projection split: 187 passed
- LLM runtime request / provider adapter / transcript / provider router combined suite: 230 passed
- Provider renderer / adapter projection suite: 117 passed
- LLM runtime request / provider adapter / transcript / provider renderer combined suite: 242 passed
- LLM runtime request / provider adapter / Codex renderer targeted suite: 186 passed
- LLM runtime request / provider adapter / transcript targeted suite: 215 passed
- LLM HTTP / UI HTTP / Workbench read-model suite: 87 passed
- LLM HTTP / UI HTTP / UI Operations trace suite after HTTP mapping split and trace source cleanup: 64 passed
- Runtime request / provider renderer / adapter / transcript suite after HTTP mapping split: 201 passed
- Provider renderer / adapter suite after provider message facade retirement: 114 passed
- LLM domain value split / service / adapter / settings integration suite: 123 passed
- Runtime request / provider renderer / Codex transport suite after domain value split: 127 passed
- Runtime request / provider renderer / adapter / transcript suite after domain value split: 201 passed
- CLI smoke/session CLI suite: 7 passed
- Provider request preview / renderer / adapter suite: 113 passed
- Provider canonical wire-shape golden suite: 3 passed
- Chat Compatible streaming/non-streaming response-item equivalence suite: 3 passed
- Chat Compatible adapter targeted suite: 14 passed
- Chat Compatible adapter targeted suite after response item split: 14 passed
- Provider adapter / renderer suite: 114 passed
