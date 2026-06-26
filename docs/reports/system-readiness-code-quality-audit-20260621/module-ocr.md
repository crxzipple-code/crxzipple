# Module Audit: ocr

## Verdict

Low risk. OCR is compact and primarily an infrastructure capability adapter.

## Evidence

- 18 Python files, about 1481 lines.
- Large files include `infrastructure/ppstructure_client.py`, `infrastructure/http_client.py`, `infrastructure/paddle_engine.py`, and `application/services.py`.

## Findings

- Boundaries are clear: application service wraps OCR engines/adapters.
- Module should remain capability-focused and not own browser/mobile workflows.
- OCR HTTP adapters now map request failures, invalid JSON payloads, HTTP 4xx,
  HTTP 5xx, and PP-Structure provider errors into OCR domain errors.
- OCR application service now enforces bounded result shape: excessive block
  counts or extracted text length fail explicitly instead of silently truncating
  text that downstream agents might treat as complete evidence.
- OCR application service and host process now enforce an explicit concurrent
  request capacity limit. Capacity exhaustion is surfaced as an OCR domain error
  and HTTP 503, not as a generic validation or execution failure.

## Launch Risks

- External OCR engine availability, timeout behavior, and local host saturation can
  affect tool runs. Request/invalid-payload/error mapping, result-size budgets, and
  host/application capacity limits are now tested.

## Recommendations

- Keep timeout/error mapping tests for OCR host and PP-Structure adapters.
- Define model/engine capability metadata.
- Keep extracted text/image artifacts as refs when adding a formal large-output
  externalization path.

## Detailed Pass 1

### Files Reviewed

- `application/services.py`
- `application/ports.py`
- `domain/value_objects.py`
- `infrastructure/ppstructure_client.py`
- `infrastructure/http_client.py`
- `infrastructure/paddle_engine.py`
- `infrastructure/host_app.py`
- `interfaces/http.py`
- `interfaces/cli.py`
- `interfaces/serializers.py`

### File-Level Assessment

`application/services.py` is 93 lines and correctly acts as a narrow wrapper over
OCR engine/adapters. It also owns result budget enforcement because result shape is
part of the OCR application contract.

`infrastructure/ppstructure_client.py` is 432 lines and is the primary integration
hotspot. HTTP and Paddle engines are correctly isolated in infrastructure.

The host app is also infrastructure, which is appropriate because it exists to expose
an engine process, not to define core OCR business rules.

### Boundary Cleanliness

OCR owns OCR analysis capability and result normalization. It should not own Browser
or Mobile workflows; those modules can consume OCR as a capability.

### Lifecycle Clarity

OCR lifecycle should be:

1. input artifact/image is referenced
2. engine request is built
3. OCR adapter executes with timeout
4. result blocks are normalized
5. result size is validated before leaving OCR
6. large extracted output remains artifact/ref-backed when a formal externalization
   path is added

### Persistence And Efficiency

OCR has little direct persistence. The main efficiency concerns are input artifact
size, external engine latency, result payload size, and future large-output
externalization.

### Concurrency And Multi-User Readiness

OCR host/engine calls require timeout, concurrency, and capacity limits if used by
many tool runs. The current policy is an explicit semaphore-style limiter with
capacity metadata exposed through service capability metadata and host health.

### Remediation Checklist

- [x] Add adapter timeout/retry/error mapping tests.
- [x] Add OCR result size tests.
- [x] Add engine capability metadata.
- [x] Add concurrency/capacity test or documented limit for OCR host usage.

### Watchlist

- Add OCR large-output artifact ref tests after the formal large-output externalization path is designed.

### Verification

- `PYTHONPATH=src pytest -q tests/unit/test_ocr_service.py tests/unit/test_ocr_host_http.py tests/unit/test_ocr_http.py tests/unit/test_ocr_infrastructure.py tests/unit/test_config.py --tb=short --maxfail=1` -> 49 passed.
- `python -m ruff check src/crxzipple/modules/ocr src/crxzipple/app/assembly/ocr.py src/crxzipple/app/assembly/daemon.py src/crxzipple/core/config.py tests/unit/test_ocr_service.py tests/unit/test_ocr_host_http.py tests/unit/test_ocr_http.py tests/unit/test_ocr_infrastructure.py tests/unit/test_config.py` -> passed.
- `PYTHONPATH=src pytest -q tests/unit/test_ocr_service.py::OcrApplicationServiceTestCase::test_capability_metadata_reports_engine_features_and_service_budgets tests/unit/test_ocr_service.py::OcrApplicationServiceTestCase::test_analyze_artifact_rejects_results_that_exceed_text_budget --tb=short` -> 2 passed.
- `python -m ruff check src/crxzipple/modules/ocr/application/services.py tests/unit/test_ocr_service.py --ignore F401,I001,E501` -> passed.

### Capacity Policy

- OCR capacity is documented in [docs/ocr-capability-runtime-policy.md](../../ocr-capability-runtime-policy.md). OCR does not own a hidden internal queue; it owns an explicit request limiter whose limit is configured by `APP_OCR_MAX_CONCURRENT_REQUESTS`.
