# OCR Capability Runtime Policy

## Boundary

OCR owns image analysis capability, engine integration, normalized result shape, and
result-size enforcement. It does not own Browser, Mobile, Tool, Orchestration, or
task-specific document understanding workflows.

## Capability Metadata

`OcrApplicationService.capability_metadata()` exposes a stable application-level
metadata payload for runtime/read-model consumers:

- engine health source: `backend`, `status`, explicit engine `capabilities`
- supported languages and features, when the engine reports them
- service-level result budgets: `max_result_blocks`, `max_result_text_chars`
- service-level capacity budget: `max_concurrent_requests`
- current capacity snapshot: `max_concurrent_requests`, `in_flight_requests`,
  `available_requests`
- large-output policy

Adapters should only report capabilities they can explicitly support. Unknown
features should stay absent instead of being inferred from provider names.

## Capacity

OCR does not own an internal multi-tenant queue. It owns an explicit request
capacity limiter that rejects excess concurrent OCR work instead of buffering it
silently:

- daemon service supervision owns the OCR host process lifecycle
- Tool/Orchestration worker limits own concurrent run pressure
- OCR application service enforces timeout/error mapping through adapters and rejects
  oversized results before they reach model-visible context
- OCR application service and OCR host enforce `APP_OCR_MAX_CONCURRENT_REQUESTS`
  using a semaphore-style limiter
- capacity exhaustion raises `OcrCapacityExceededError`; HTTP surfaces this as 503

Until OCR needs its own scheduler, do not add hidden queues or retry loops inside
OCR. If host-level contention becomes visible, tune the explicit capacity limit or
move scheduling to Tool/Orchestration worker policy instead of hiding contention in
the OCR module.

## Large Output

Large OCR output is rejected by result-size budgets today. Full extracted text,
layout dumps, or provider raw payloads must not be inlined into runtime events,
LLM request context, or UI read models.

When large-output externalization is implemented, store large OCR output as
Artifact-owned refs and update OCR tests to assert artifact refs instead of inline
payloads.
