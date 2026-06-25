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
- large-output policy

Adapters should only report capabilities they can explicitly support. Unknown
features should stay absent instead of being inferred from provider names.

## Capacity

OCR does not currently own an internal multi-tenant queue. Capacity is controlled by
the caller side:

- daemon service supervision owns the OCR host process lifecycle
- Tool/Orchestration worker limits own concurrent run pressure
- OCR application service enforces timeout/error mapping through adapters and rejects
  oversized results before they reach model-visible context

Until OCR needs its own scheduler, do not add hidden concurrency state inside OCR.
If host-level contention becomes visible, add an explicit OCR host lease/semaphore
and expose it as OCR runtime metadata before enabling higher concurrency.

## Large Output

Large OCR output is rejected by result-size budgets today. Full extracted text,
layout dumps, or provider raw payloads must not be inlined into runtime events,
LLM request context, or UI read models.

When large-output externalization is implemented, store large OCR output as
Artifact-owned refs and update OCR tests to assert artifact refs instead of inline
payloads.
