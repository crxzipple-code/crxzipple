# Module Audit: session

## Verdict

Medium importance, medium risk. Session is conceptually clean as the conversation ledger and has improved materially in this split wave. Append, lifecycle, query/read windows, compaction, metadata, reset policy, events, and Unit of Work seams are now separated. `SessionApplicationService` remains the write/lifecycle coordinator, while read/query window construction now lives in `SessionQueryReader`; replay/compaction correctness is still launch-critical.

## Evidence

- 34 Python files, about 5151 lines.
- Large files include `application/services.py` (728), `interfaces/cli.py` (374), `infrastructure/persistence/repositories.py` (360), `interfaces/http_models.py` (319), `application/runtime_response_projection.py` (307), `domain/value_objects.py` (301), `application/session_reader.py` (295), `application/session_windows.py` (199), `interfaces/http.py` (195), and `interfaces/dto.py` (179).

## Findings

- Current direction is good: Session owns conversation/session item facts, not UI timeline decisions and not provider rendering.
- `services.py` remains the write/lifecycle facade, but append, query/read, replay, compaction, metadata, reset, event, UoW, and session instance/runtime binding lifecycle helpers have been extracted. `SessionQueryReader` owns pure reads, item ranges, segment handles, context frontier, replay windows, and source-item lookup.
- Runtime response projection belongs as a read/projection surface, but it should not become a second source of truth.

## Launch Risks

- Replay correctness is critical for long-chain reliability. Any drift between SessionItem, Context Workspace selection, and provider rendering can weaken model behavior.
- Large service surface can make compaction and lifecycle state changes hard to reason about.

## Recommendations

- Continue shrinking `SessionApplicationService` only where it removes real coordination bulk; the most important split seams are now present.
- Add architecture tests ensuring LLM request rendering reads Session through approved replay/query surfaces only.
- Add long-session budget tests with required tool protocol item preservation.

## Detailed Pass 1

### Files Reviewed

- `application/services.py`
- `application/runtime_response_projection.py`
- `application/resolution.py`
- `domain/entities.py`
- `domain/value_objects.py`
- `infrastructure/persistence/repositories.py`
- `interfaces/http.py`
- `interfaces/http_models.py`
- `interfaces/cli.py`

### File-Level Assessment

`application/services.py` was 1474 lines and is now 728 lines after moving item
append helpers, item events, session lifecycle, query DTOs, replay/context windows,
segment compaction helpers, metadata merge helpers, reset policy, and Unit of Work
ports into focused modules, then moving session/entity construction, session instance
construction, runtime binding payload/metadata projection, instance binding sync,
instance existence checks, sequence calculation, and session-kind inference into
`session_instance_lifecycle.py`, then moving read/query/window construction into
`session_reader.py`. It still coordinates ensure session, routed sync, append,
metadata mutation, compaction, and reset, so it remains the main Session write
governance hotspot.

`runtime_response_projection.py` is a healthy sign: runtime-facing projection is separated from core domain facts. It must remain a projection, not a second source of truth.

### Boundary Cleanliness

Session boundary is clean in concept:

- Session owns session/segment/item facts.
- LLM request building consumes replay windows.
- Workbench/Operations project session items.
- Context Workspace references session facts rather than copying them.

The practical risk is that `SessionApplicationService` becomes the universal API for every session concern.

### Lifecycle Clarity

The module must make these lifecycle states explicit:

- session instance/segment creation
- item append
- item lifecycle active/archived/compacted
- replay window selection
- maintenance/compaction frontier
- metadata mutation

These are present with clearer helper seams, though orchestration still flows through the
main application service.

### Persistence And Efficiency

Session persistence is central to LLM replay. Long sessions require bounded replay and indexed item lookup. Persistence risk is not the repository shape itself; it is accidental unbounded reads through replay/list APIs.

### Concurrency And Multi-User Readiness

Concurrent item appends, compaction, and replay window reads need careful ordering. Multi-user production requires:

- monotonic item sequence guarantees
- idempotent append paths for tool/LLM result recovery
- replay windows that preserve protocol-required tool items
- compaction that does not delete facts needed by Workbench/Operations

### Remediation Checklist

- [x] Split `SessionApplicationService` helper concerns into item append/event, lifecycle, query DTO, replay/window, compaction, metadata, reset policy, and Unit of Work modules.
- [x] Split Session entity/instance construction, runtime binding sync, instance sequencing, and session-kind inference out of `SessionApplicationService`.
- [x] Split pure Session read/query/window construction into `SessionQueryReader`, leaving `SessionApplicationService` as the write/lifecycle facade.
- [x] Add architecture test: LLM request builders cannot read session repositories directly.
- [x] Add concurrent append/replay/compaction boundary tests.
- [x] Add replay-window tests that preserve required protocol/tool-call items after compaction.
- [x] Keep runtime response projection read-only.

### Watchlist

- Continue reducing `SessionApplicationService` if future changes add new lifecycle branches.

### Remediation Verification

Command passed after the current Session split wave:

```bash
PYTHONPATH=src pytest -q tests/unit/test_session_reset_policy.py tests/unit/test_session.py tests/unit/test_session_segment_compaction.py tests/unit/test_session_persistence_contracts.py tests/unit/test_session_http.py tests/unit/test_session_cli.py tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_module_architecture_guards.py --tb=short
```

Result:

- Session/runtime-request/architecture targeted suite: 67 passed
- Session service / compaction / persistence / reset / CLI suite after instance lifecycle split: 41 passed
- Runtime transcript / runtime request / orchestration context suite after instance lifecycle split: 54 passed
