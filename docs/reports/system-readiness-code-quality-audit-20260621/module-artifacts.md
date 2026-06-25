# Module Audit: artifacts

## Verdict

Low risk. Artifacts is small and has a clear storage/metadata boundary.

## Evidence

- 11 Python files, about 868 lines.
- Largest files: `application/services.py` (387), `interfaces/http.py` (148), `domain/entities.py` (131), `infrastructure/filesystem_store.py` (98).

## Findings

- Artifact metadata and filesystem storage are appropriately isolated.
- The module should not become a dump for large tool result payloads.
- Filesystem storage now enforces artifact-root containment and atomic binary
  writes; missing underlying files are surfaced as explicit artifact not found
  errors.
- Artifact lifecycle cleanup is now exposed by the owner service: metadata can be
  listed, storage usage can be measured, and old/over-quota artifacts can be
  pruned without external directory scanning.
- Tool large-result storage now uses artifact refs: Tool owner externalizes large
  text/raw output, Orchestration records provider replay payloads by ref, and LLM
  transcript replay ignores trace-only/debug bodies.

## Launch Risks

- Access control for metadata/preview/download is explicit through the
  Authorization owner. The default policy allows `artifact.read`; higher-priority
  deny policies block metadata, preview, original, and download endpoints.

## Recommendations

- Keep tool run details as refs to artifacts, not full large payload storage.
- Keep artifact metadata, preview, original, and download endpoints behind the
  Authorization owner contract as the HTTP subject/tenant model evolves.

## Detailed Pass 1

### Files Reviewed

- `application/services.py`
- `application/ports.py`
- `domain/entities.py`
- `infrastructure/filesystem_store.py`
- `interfaces/http.py`

### File-Level Assessment

`application/services.py` is 387 lines. It creates artifacts, variants,
preview/LLM variants, binary access, storage usage summaries, and cleanup policy.
This is still acceptable for a small owner module, but if more lifecycle policy is
added later it should split read/query and cleanup use cases.

`infrastructure/filesystem_store.py` provides root-contained binary writes,
metadata reads/listing, and artifact directory deletion. It deliberately does not
own retention decisions.

`interfaces/http.py` is 148 lines and remains thin.

### Boundary Cleanliness

Artifacts owns artifact metadata and filesystem-backed storage. Other modules should
store refs to artifacts instead of embedding large payloads in tool/session/LLM
records.

### Lifecycle Clarity

Artifact lifecycle should be:

1. binary/content stored
2. artifact metadata created
3. variants generated or registered
4. preview/download/read access served by ref
5. retention/quota/cleanup removes old content safely

All five lifecycle steps are now represented in the owner service.

### Persistence And Efficiency

Filesystem storage is appropriate for local artifact binaries. Multi-user
production still requires access controls; quota and retention pruning now have a
service-level entrypoint.

### Concurrency And Multi-User Readiness

Concurrent artifact writes use generated artifact ids and atomic binary writes.
Cleanup deletes whole artifact directories after resolving ids through the store.
Metadata, preview, original, and download reads now pass through the
Authorization owner. The current HTTP subject is still header-derived, so a future
shared deployment should replace that with the platform identity context instead
of bypassing artifact read authorization.

### Remediation Checklist

- [x] Add retention/quota/cleanup policy and tests.
- [x] Add missing-file behavior tests.
- [x] Add invariant: large Tool payloads are stored as artifact refs, not inline
  in model-visible replay.
- [x] Add preview/download authorization tests.
- [x] Define LLM invocation raw request/response externalization policy if raw
  provider payload retention grows beyond bounded snapshots.

### Remediation Verification

Commands passed after filesystem containment, missing-file hardening, and
retention/quota cleanup formalization:

```bash
PYTHONPATH=src pytest -q tests/unit/test_artifacts_service.py tests/unit/test_artifacts_http.py --tb=short
python -m ruff check src/crxzipple/modules/artifacts tests/unit/test_artifacts_service.py tests/unit/test_artifacts_http.py
```

Result:

- Artifacts service / HTTP suite: 13 passed
- Targeted ruff over artifact module and tests: passed

Additional invariant verification:

```bash
PYTHONPATH=src pytest -q tests/unit/test_runtime_transcript.py::RuntimeTranscriptTestCase::test_tool_result_envelope_renders_provider_visible_evidence_without_body tests/unit/test_tool_execution.py::ToolExecutionTestCase::test_execute_externalizes_large_text_result_to_artifact_ref_metadata tests/unit/test_tool_background.py::ToolBackgroundTestCase::test_background_run_externalizes_large_text_result_to_artifact_refs --tb=short
python -m ruff check tests/unit/test_runtime_transcript.py src/crxzipple/modules/llm/application/session_runtime_items.py src/crxzipple/modules/llm/application/tool_result_model_text.py src/crxzipple/modules/tool/application/tool_result_artifacts.py
PYTHONPATH=src pytest -q tests/unit/test_artifacts_http.py::ArtifactsHttpTestCase::test_upload_and_serve_artifact tests/unit/test_artifacts_http.py::ArtifactsHttpTestCase::test_artifact_preview_and_download_are_authorized tests/unit/test_authorization.py::AuthorizationTestCase::test_authorization_service_lists_policies_and_evaluates_allow_and_deny --tb=short
```

Result:

- Tool/artifact/model-visible replay invariant suite: 3 passed
- Targeted ruff over replay/externalization paths: passed
- Artifact read authorization focus suite: 3 passed

LLM raw provider request/response externalization policy is documented in
`docs/artifact-storage-policy.md#llm-raw-request-and-response-payloads`.
