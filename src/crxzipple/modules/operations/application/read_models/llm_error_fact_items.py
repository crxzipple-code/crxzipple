from __future__ import annotations

import json
from typing import Any

from crxzipple.modules.llm.application.error_classification import (
    llm_error_retryable,
)
from crxzipple.modules.llm.domain import LlmInvocation
from crxzipple.modules.operations.application.read_models.llm_invocation_labels import (
    provider_request_preview,
)
from crxzipple.modules.operations.application.read_models.llm_provider_request_labels import (
    provider_continuation_fallback_label,
    provider_request_continuation_label,
    provider_request_input_delta_label,
    provider_request_transport_label,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
)
from crxzipple.modules.operations.application.read_models.presenters import (
    truncate_text,
)


def error_fact_items(
    invocation: LlmInvocation,
    *,
    category: str,
    error_code: str,
) -> tuple[OperationsKeyValueItemModel, ...]:
    retryable = llm_error_retryable(error_code)
    items: list[OperationsKeyValueItemModel] = [
        OperationsKeyValueItemModel(
            "Category",
            category,
            "danger" if category != "-" else "neutral",
        ),
        OperationsKeyValueItemModel(
            "Error Code",
            error_code,
            "danger" if error_code != "-" else "neutral",
        ),
        OperationsKeyValueItemModel(
            "Retryable",
            "Yes" if retryable else "No",
            "warning" if retryable else "neutral",
        ),
    ]
    if invocation.error is not None:
        items.append(
            OperationsKeyValueItemModel(
                "Provider Error Message",
                truncate_text(invocation.error.message, 240),
                "danger",
            ),
        )
        for key, value in sorted(invocation.error.details.items()):
            if value in (None, "", [], {}):
                continue
            items.append(
                OperationsKeyValueItemModel(
                    f"Error Detail: {key}",
                    truncate_text(_json_or_text(value), 240),
                    "danger",
                ),
            )
    _append_provider_diagnostics(invocation, items)
    return tuple(items)


def _append_provider_diagnostics(
    invocation: LlmInvocation,
    items: list[OperationsKeyValueItemModel],
) -> None:
    preview = provider_request_preview(invocation)
    preview_error = _text(preview.get("preview_error"))
    if preview_error:
        items.append(
            OperationsKeyValueItemModel(
                "Provider Preview Error",
                truncate_text(preview_error, 240),
                "danger",
            ),
        )
    provider_transport = provider_request_transport_label(invocation)
    if provider_transport != "-":
        items.append(
            OperationsKeyValueItemModel(
                "Provider Transport",
                provider_transport,
                "neutral",
            ),
        )
    provider_continuation = provider_request_continuation_label(invocation)
    if provider_continuation != "-":
        items.append(
            OperationsKeyValueItemModel(
                "Provider Continuation",
                provider_continuation,
                "neutral",
            ),
        )
    provider_input_delta = provider_request_input_delta_label(invocation)
    if provider_input_delta != "-":
        items.append(
            OperationsKeyValueItemModel(
                "Provider Input Delta",
                provider_input_delta,
                "neutral",
            ),
        )
    fallback_reason = provider_continuation_fallback_label(invocation)
    if fallback_reason != "-":
        items.append(
            OperationsKeyValueItemModel(
                "Provider Continuation Fallback",
                fallback_reason,
                "warning",
            ),
        )


def _json_or_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
