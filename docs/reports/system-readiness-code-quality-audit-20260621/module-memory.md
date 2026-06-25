# Module Audit: memory

## Verdict

Medium risk. Memory has a good owner boundary, but mixed markdown/file storage, SQLite index, and runtime access require production-mode clarity.

## Evidence

- 35 Python files, about 6468 lines.
- Large files include `application/runtime.py` (642), `application/indexing.py` (502), `interfaces/http.py` (461), `interfaces/http_models.py` (444), `application/contracts.py` (244), `application/services.py` (198).
- Persistence includes Postgres models/repositories, SQLite index store, and markdown store.

## Findings

- Memory should own durable knowledge and retrieval, not session scheduling.
- Multiple storage forms are reasonable but need explicit contracts.
- HTTP interface is large relative to module size.
- Index sync and runtime retrieval should be measurable.
- Production runtime now refuses to start with the current local SQLite memory index
  unless `APP_ALLOW_SQLITE_MEMORY_INDEX_RUNTIME=1` explicitly acknowledges that
  storage mode.

## Launch Risks

- File/index inconsistency can degrade retrieval quality.
- SQLite index may not be appropriate for shared multi-user production unless scoped and documented.
- Retrieval latency can impact LLM request build time.

## Recommendations

- Define production storage mode: Postgres facts plus approved index backend.
- Add index freshness, stale chunk, and query latency metrics.
- Keep memory recall/write as tools/application services, not hidden orchestration behavior.
- Split HTTP DTO/read model assembly.

## Detailed Pass 1

### Files Reviewed

- `application/runtime.py`
- `application/indexing.py`
- `application/services.py`
- `application/query.py`
- `application/contracts.py`
- `application/policies.py`
- `domain/entities.py`
- `domain/services.py`
- `infrastructure/indexing/sqlite_index_store.py`
- `infrastructure/indexing/embeddings.py`
- `infrastructure/storage/markdown_store.py`
- `infrastructure/persistence/repositories.py`
- `interfaces/http.py`
- `interfaces/cli.py`

### File-Level Assessment

`application/runtime.py` is 642 lines and cleanly defines runtime request/response
records, scope/layer resolution, recall/remember flow, and citation helpers. This is
a reasonable size for a runtime application service, but it sits on top of several
storage/index backends that need explicit mode controls.

`application/indexing.py` is 502 lines and separates sync/search services. This is a
good split. It should gain more explicit index freshness and cost reporting.

`infrastructure/indexing/sqlite_index_store.py` is 696 lines and owns SQLite FTS,
schema initialization, chunk rows, search scoring, and fallback behavior. SQLite is
acceptable as local index infrastructure. Production mode now has a runtime guard:
the process must set `APP_ALLOW_SQLITE_MEMORY_INDEX_RUNTIME=1` to acknowledge the
current SQLite index mode, otherwise shared runtime entrypoints fail before service
startup.

`interfaces/http.py` is now 461 lines and only owns route handlers. DTOs and
entity-to-response mapping live in `interfaces/http_models.py`; context resolution,
runtime defaults loading, index count, and runtime actor construction live in
`interfaces/http_common.py`.

### Boundary Cleanliness

Memory boundary is healthy: Memory owns memory spaces, files, policies, index sync,
retrieval, and writes. Orchestration/LLM should consume Memory through tools or
approved application services, not directly modify stores or indexes.

Risk pattern:

- Settings integration can govern runtime defaults, but Memory remains owner of
  memory facts and index state.
- Context Workspace can reference memory search results/slices, not become memory
  storage.
- SQLite/markdown/file stores must not be hidden production truth without explicit
  runtime mode declaration.

### Lifecycle Clarity

Memory lifecycle should be:

1. memory space/policy exists
2. source files are scanned
3. index sync records chunks and freshness
4. runtime recall queries selected spaces/layers
5. runtime remember writes approved target
6. index refresh catches changed content

This is mostly present, but freshness and stale-index states should be surfaced.

### Persistence And Efficiency

The module mixes Postgres metadata, markdown file storage, SQLite index, and optional
embedding HTTP calls. That is fine for local runtime if explicit. For launch, the
system needs:

- index freshness metrics
- bounded recall result size
- query latency counters
- clear rebuild behavior
- production-mode gate for SQLite/file fallback assumptions

### Concurrency And Multi-User Readiness

Concurrent writes and index rebuilds can race with recall. Multi-user deployment
needs per-workspace/per-agent scoping and file path isolation.

### External Integration Readiness

Memory is suitable as an external capability if exposed through narrow recall/write
ports and tools. Direct filesystem/index access should stay internal.

### Remediation Checklist

- [x] Split `interfaces/http.py` into space/policy, runtime recall/remember, index maintenance, migration/export, and overview endpoints or helper modules.
- [x] Add index freshness and stale chunk tests.
- [x] Add recall latency and result-size budget tests.
- [x] Add production-mode documentation/guard for SQLite index.
- [x] Add production-mode documentation for markdown store path ownership and scoping.
- [x] Ensure Context Workspace renders memory as selected citations/slices only, not raw full stores.
- [x] Add concurrent write/rebuild/recall tests.

### Remediation Verification

Commands passed after the production Memory index guard:

```bash
PYTHONPATH=src pytest -q tests/unit/test_config.py tests/unit/test_serve_cli.py --tb=short
python -m ruff check src/crxzipple/core/config.py src/crxzipple/interfaces/cli/crxzipple.py tests/unit/test_config.py tests/unit/test_serve_cli.py
```

Result:

- Config / Serve CLI guard suite: 37 passed
- Targeted ruff over changed config/CLI/test files: passed

Commands passed after the Context Workspace memory slice guard:

```bash
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py::test_context_slice_builder_keeps_non_session_owner_refs_handle_only tests/unit/test_context_workspace_tree_service.py::test_memory_context_slice_does_not_inline_raw_store_body tests/unit/test_context_workspace_memory_adapter.py --tb=short
python -m ruff check tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_workspace_memory_adapter.py --ignore F401,I001,E501
```

Result:

- Context Workspace memory slice guard suite: 3 passed
- Targeted ruff over changed Context Workspace memory tests: passed

Production markdown store path ownership is documented in
`docs/memory-space-design.md#production-path-ownership`.

Commands passed for index freshness and stale chunk behavior:

```bash
PYTHONPATH=src pytest -q tests/unit/test_file_backed_memory.py::FileBackedMemoryTestCase::test_search_reindexes_after_file_changes tests/unit/test_file_backed_memory.py::FileBackedMemoryTestCase::test_dirty_path_sync_reindexes_changed_file_without_full_scan tests/unit/test_file_backed_memory.py::FileBackedMemoryTestCase::test_dirty_path_sync_deletes_removed_file_without_full_scan tests/unit/test_memory_watching.py::MemoryWatchingTestCase::test_watch_registry_warms_index_after_memory_file_change tests/unit/test_memory_watching.py::MemoryWatchingTestCase::test_watch_registry_rename_event_reindexes_old_and_new_paths --tb=short
python -m ruff check tests/unit/test_file_backed_memory.py tests/unit/test_memory_watching.py --ignore F401,I001,E501
```

Result:

- Memory index freshness/stale chunk suite: 5 passed
- Targeted ruff over Memory index/watch tests: passed

Commands passed for recall result-size and latency event budget:

```bash
PYTHONPATH=src pytest -q tests/unit/test_file_backed_memory.py::FileBackedMemoryTestCase::test_recall_result_limit_and_latency_metrics_are_reported tests/unit/test_file_backed_memory.py::FileBackedMemoryTestCase::test_search_reindexes_after_file_changes --tb=short

Commands passed after Memory HTTP interface split:

```bash
PYTHONPATH=src pytest -q tests/unit/test_memory_http.py tests/unit/test_memory_spaces.py tests/unit/test_memory_policies.py tests/unit/test_memory_runtime_service.py tests/unit/test_file_backed_memory.py --tb=short
python -m ruff check src/crxzipple/modules/memory/interfaces/http.py src/crxzipple/modules/memory/interfaces/http_models.py src/crxzipple/modules/memory/interfaces/http_common.py tests/unit/test_memory_http.py tests/unit/test_memory_spaces.py tests/unit/test_memory_policies.py tests/unit/test_memory_runtime_service.py tests/unit/test_file_backed_memory.py --ignore F401,I001,E501
```

Result:

- Memory HTTP/runtime/storage suite: 40 passed
- Targeted ruff over Memory interface split: passed
python -m ruff check tests/unit/test_file_backed_memory.py --ignore F401,I001,E501
```

Result:

- Memory recall budget suite: 2 passed
- Targeted ruff over Memory recall tests: passed

Commands passed for concurrent write/rebuild/recall:

```bash
PYTHONPATH=src pytest -q tests/unit/test_file_backed_memory.py::FileBackedMemoryTestCase::test_concurrent_write_rebuild_and_recall_do_not_corrupt_index tests/unit/test_file_backed_memory.py::FileBackedMemoryTestCase::test_recall_result_limit_and_latency_metrics_are_reported --tb=short
python -m ruff check tests/unit/test_file_backed_memory.py --ignore F401,I001,E501
```

Result:

- Memory concurrent write/rebuild/recall suite: 2 passed
- Targeted ruff over Memory concurrent tests: passed
