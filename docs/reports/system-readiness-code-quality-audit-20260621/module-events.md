# Module Audit: events

## Verdict

Medium importance, low-medium risk. Events is a foundational infrastructure module and must remain business-meaning-neutral.

## Evidence

- 28 Python files, about 4615 lines.
- Large files include `infrastructure/redis_backed.py` (567), `infrastructure/file_backed.py` (531), `application/read_models/trace.py` (488), `interfaces/http.py` (381), `interfaces/http_console.py` (361), `application/contracts.py` (300), and `domain/value_objects.py` (289).

## Findings

- Events provides topic, cursor, contract, publish/read/wait primitives; this boundary is appropriate.
- Redis backend is the correct shared runtime path.
- File and in-memory backends are useful but must stay explicit fallback/test modes.
  Shared runtime entrypoints now reject file events unless
  `APP_ALLOW_FILE_EVENTS_RUNTIME_FALLBACK=1` is set.
- HTTP router has been reduced by moving event console stream filters, snapshot/recent record projection, payload filtering, cursor comparison, SSE formatting, and topic/subscription diagnostics payload shaping into focused interface helpers.
- Trace read model now scans concrete event topics recorded in the event service, not only registry-backed `events.named.*` topics, so session/live runtime events remain observable without giving Events business ownership. Relay and channel observe topics stay filtered as observation-channel noise.

## Launch Risks

- Hidden use of in-memory/file backend in multi-process mode would break runtime observation.
- Event contract drift can break Operations projections and external integrations.

## Recommendations

- Enforce Redis backend for shared runtime targets.
- Add event contract version/failure tests for projection consumers.
- Keep business interpretation out of Events.

## Detailed Pass 1

### Files Reviewed

- `application/services.py`
- `application/contracts.py`
- `application/routing.py`
- `application/ports.py`
- `application/read_models/trace.py`
- `domain/entities.py`
- `domain/value_objects.py`
- `infrastructure/redis_backed.py`
- `infrastructure/file_backed.py`
- `infrastructure/in_memory.py`
- `infrastructure/outbox_publisher.py`
- `infrastructure/persistence/repositories.py`
- `interfaces/http.py`
- `interfaces/worker_cli.py`

### File-Level Assessment

`application/services.py` is only 137 lines, which is healthy for a foundational
module. The main application service exposes publish/read/wait primitives rather than
business logic.

`infrastructure/redis_backed.py` is 567 lines and is the correct shared runtime
backend. `file_backed.py` and `in_memory.py` are useful for local/test/fallback modes
but must not be hidden multi-process defaults.

`application/read_models/trace.py` was 531 lines and is now 488 lines after moving
trace topic discovery, named/concrete topic normalization, relay/observe noise filtering,
and per-topic read limits into `trace_topics.py`. Trace read models are acceptable
here if they remain event-level views and do not become business projections owned by
Operations/Workbench. It now includes registry-backed named topics plus concrete
recorded topics from the event service, allowing `turn.session.*` and `turn.live.*`
events to participate in Trace UI without hard-coding business event families.

`interfaces/http.py` was 849 lines and is now 381 lines after moving event console
stream filters, source record projection, snapshot/recent record reads, topic refresh,
payload filters, cursor comparison, and SSE formatting into `interfaces/http_console.py`,
then moving topic record summaries, subscription cursor lag/stuck projection, consumer
summaries, and subscription diagnostic rows into `interfaces/http_diagnostics.py`. It
should stay focused on route parsing, service lookup, high-level diagnostics wiring, and
response streaming, not business-specific projection.

### Boundary Cleanliness

Events owns event topic/cursor/contract/publish/read/wait/outbox primitives. It must
not interpret business semantics, decide orchestration advancement, or own Operations
projection meaning.

Current boundary is largely correct.

### Lifecycle Clarity

Events lifecycle should be:

1. owner module emits event payload to topic
2. backend stores/publishes with cursor
3. consumers read/wait by topic/cursor
4. outbox retries failed publication
5. contract registry validates topic/payload expectations
6. Operations/Workbench/Trace interpret events outside Events owner logic

### Persistence And Efficiency

Redis is required for shared runtime. Postgres outbox is appropriate for reliable
publication. File/in-memory backend use must be explicit and visible in runtime
status. HTTP/daemon/worker entrypoints now call the shared runtime persistence
guard: Redis events pass by default; file events fail fast unless explicitly
authorized as a one-off fallback.

### Concurrency And Multi-User Readiness

Event ordering, cursor semantics, and consumer replay are foundational for multi-user
runtime. Redis connection errors and backpressure must be visible to daemon/operations.

### External Integration Readiness

External integrations need documented topic contracts and cursor semantics. Events
can expose these primitives, but business contracts should live with owner modules and
be registered into Events.

### Remediation Checklist

- [x] Add production-mode guard that rejects in-memory/file backend for shared runtime targets.
- [x] Add contract version tests for owner module event contracts consumed by Operations.
- [x] Add cursor replay/order tests for Redis backend.
- [x] Add outbox retry/failure visibility tests.
- [x] Keep event trace read model business-neutral while reading concrete recorded topics beyond `events.named.*`.
- [x] Split Trace topic discovery/source filtering out of `trace.py` while excluding relay/observe noise topics.
- [x] Split event console HTTP stream/read helpers out of `interfaces/http.py`.
- [x] Split event topic/subscription diagnostics payload helpers out of `interfaces/http.py`.

### Watchlist

- Split `interfaces/http.py` further if event admin/trace/contract endpoints keep growing.

### Remediation Verification

Command passed after the Trace topic split:

```bash
PYTHONPATH=src pytest -q tests/unit/test_events.py tests/unit/test_ui_operations_http.py tests/unit/test_ui_http.py --tb=short
```

Result:

- Events / UI Operations / UI HTTP Trace suite: 89 passed
- Events service suite after HTTP console split: 34 passed
- UI Operations / UI HTTP suite after HTTP console split: 55 passed
- Events service suite after HTTP diagnostics split: 34 passed
- UI Operations / UI HTTP suite after HTTP diagnostics split: 55 passed

Commands passed after the shared runtime events backend guard:

```bash
PYTHONPATH=src pytest -q tests/unit/test_config.py tests/unit/test_serve_cli.py --tb=short
python -m ruff check src/crxzipple/core/config.py src/crxzipple/interfaces/cli/crxzipple.py tests/unit/test_config.py tests/unit/cli_test_support.py tests/unit/test_channels_cli.py tests/unit/test_serve_cli.py
PYTHONPATH=src pytest -q tests/unit/test_events_http.py::EventsHttpTestCase::test_event_contracts_endpoint_lists_registered_topics_and_routes tests/unit/test_events.py --tb=short
python -m ruff check src/crxzipple/shared/event_contracts.py src/crxzipple/modules/events/application/contracts.py tests/unit/test_events_http.py --ignore F401,I001,E501
PYTHONPATH=src pytest -q tests/unit/test_events.py::EventsModuleTestCase::test_redis_events_backend_replays_after_cursor_in_publish_order tests/unit/test_events.py::EventsModuleTestCase::test_redis_events_backend_can_wait_and_read_topic_records tests/unit/test_events_http.py::EventsHttpTestCase::test_event_contracts_endpoint_lists_registered_topics_and_routes --tb=short
python -m ruff check tests/unit/test_events.py tests/unit/test_events_http.py src/crxzipple/modules/events/application/contracts.py src/crxzipple/shared/event_contracts.py --ignore F401,I001,E501
PYTHONPATH=src pytest -q tests/unit/test_event_outbox.py --tb=short
python -m ruff check tests/unit/test_event_outbox.py src/crxzipple/modules/events/infrastructure/outbox_publisher.py src/crxzipple/modules/events/infrastructure/persistence/repositories.py --ignore F401,I001,E501
```

Result:

- Config / Serve CLI guard suite: 32 passed
- Targeted ruff over changed config/CLI/test files: passed
- Events contract version suite: 35 passed
- Targeted ruff over event contract value objects and contract HTTP test: passed
- Redis cursor replay/order suite: 3 passed
- Targeted ruff over event cursor/contract tests: passed
- Event outbox retry/failure visibility suite: 6 passed
- Targeted ruff over event outbox paths: passed
