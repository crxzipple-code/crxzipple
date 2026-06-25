from __future__ import annotations

from datetime import datetime, timezone

from crxzipple.modules.llm.domain import (
    LlmErrorPayload,
    LlmInputItem,
    LlmInputItemKind,
    LlmInvocation,
    LlmInvocationStatus,
    LlmMessage,
    LlmMessageRole,
    LlmResult,
)
from crxzipple.modules.llm.application.error_classification import (
    llm_error_family,
    llm_error_retryable,
)
from crxzipple.modules.operations.application.read_models.llm_error_fact_items import (
    error_fact_items,
)
from crxzipple.modules.operations.application.read_models.llm_error_sections import (
    error_summary_section,
)


def _failed_invocation(
    invocation_id: str,
    *,
    code: str,
    message: str = "failed",
    completed_at: datetime | None = None,
) -> LlmInvocation:
    now = datetime(2026, 6, 21, 12, tzinfo=timezone.utc)
    return LlmInvocation(
        id=invocation_id,
        llm_id="openai.gpt",
        status=LlmInvocationStatus.FAILED,
        messages=(LlmMessage(role=LlmMessageRole.USER, content="hello"),),
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={"role": "user", "content": "hello"},
            ),
        ),
        error=LlmErrorPayload(code=code, message=message),
        created_at=now,
        completed_at=completed_at,
    )


def test_error_family_and_retryable_error_classify_common_provider_failures() -> None:
    assert llm_error_family("rate_limit_429") == "rate_limit"
    assert llm_error_family("invalid_auth_401") == "auth"
    assert llm_error_family("context_length_exceeded") == "context_length"
    assert llm_error_family("provider_unavailable_503") == "provider_down"
    assert llm_error_family("validation_400") == "bad_request"
    assert llm_error_retryable("rate_limit_429") is True
    assert llm_error_retryable("temporarily_unavailable") is True
    assert llm_error_retryable("invalid_auth_401") is False


def test_error_summary_section_groups_failures_by_category_and_code() -> None:
    latest = datetime(2026, 6, 21, 12, 5, tzinfo=timezone.utc)
    invocations = [
        _failed_invocation("old", code="rate_limit_429", completed_at=latest.replace(minute=1)),
        _failed_invocation("new", code="rate_limit_429", message="quota", completed_at=latest),
        _failed_invocation("auth", code="invalid_auth_401", completed_at=latest),
    ]

    section = error_summary_section(invocations)

    assert section.id == "error_summary"
    assert section.total == 2
    rows = {row.id: row for row in section.rows}
    assert rows["rate_limit:rate_limit_429"].cells["count"] == "2"
    assert rows["rate_limit:rate_limit_429"].cells["retryable"] == "Yes"
    assert rows["rate_limit:rate_limit_429"].cells["last_invocation"] == "new"
    assert rows["auth:invalid_auth_401"].tone == "danger"


def test_error_fact_items_include_provider_request_diagnostics() -> None:
    invocation = _failed_invocation(
        "failed-detail",
        code="provider_unavailable_503",
        message="provider down",
    )
    invocation.error = LlmErrorPayload(
        code="provider_unavailable_503",
        message="provider down",
        details={"request_id": "req-1"},
    )
    invocation.result = LlmResult(
        metadata={
            "provider_continuation_fallback": True,
            "provider_continuation_fallback_reason": "websocket_failed",
        },
    )
    invocation.provider_request_payload_preview = {
        "preview_error": "could not serialize request",
        "transport": "websocket",
        "has_previous_response_id": True,
        "previous_response_id": "resp-prev",
        "input_delta_mode": True,
        "input_delta_count": 1,
        "input_baseline_count": 3,
    }

    items = error_fact_items(
        invocation,
        category=llm_error_family(invocation.error.code),
        error_code=invocation.error.code,
    )
    values = {item.label: item.value for item in items}
    tones = {item.label: item.tone for item in items}

    assert values["Category"] == "provider_down"
    assert values["Retryable"] == "Yes"
    assert values["Provider Error Message"] == "provider down"
    assert values["Error Detail: request_id"] == "req-1"
    assert values["Provider Preview Error"] == "could not serialize request"
    assert values["Provider Transport"] == "websocket"
    assert values["Provider Continuation"] == "previous_response_id=resp-prev"
    assert values["Provider Input Delta"] == "mode=true; delta=1; baseline=3"
    assert values["Provider Continuation Fallback"] == "websocket_failed"
    assert tones["Provider Preview Error"] == "danger"
