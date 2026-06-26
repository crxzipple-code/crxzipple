from __future__ import annotations


def llm_step_summary(
    payload: dict[str, object],
    *,
    include_invocation_id: bool = False,
    include_progress_text: bool = False,
) -> dict[str, object]:
    keys = [
        "assistant_progress_item_ids",
        "llm_id",
        "llm_request_input",
        "llm_response_item_ids",
        "llm_loop_diagnostic",
        "llm_transcript_consumption",
        "request_render_snapshot_id",
        "runtime_request_mode",
        "session_item_ids",
        "tool_call_session_item_ids",
        "tool_call_names",
        "tool_result_session_item_ids",
        "user_session_item_id",
    ]
    if include_invocation_id:
        keys.insert(2, "llm_invocation_id")
    summary: dict[str, object] = {}
    for key in keys:
        value = payload.get(key)
        if value is not None:
            summary[key] = value
    if include_progress_text:
        progress_text = payload.get("assistant_progress_text")
        if isinstance(progress_text, str) and progress_text.strip():
            summary["assistant_progress_text"] = progress_text
            summary["assistant_progress_text_chars"] = len(progress_text)
    return summary


def failed_llm_execution_payload(
    details: dict[str, object] | None,
) -> dict[str, object]:
    if not isinstance(details, dict):
        return {}
    execution_payload = details.get("execution_payload")
    if not isinstance(execution_payload, dict):
        return {}
    return dict(execution_payload)


def continuation_payload(
    payload: dict[str, object],
    *,
    include_provider_state: bool = False,
) -> dict[str, object] | None:
    reason = first_present(
        payload,
        "llm_continuation_reason",
        "continuation_reason",
    )
    end_turn = first_present(
        payload,
        "llm_continuation_end_turn",
        "continuation_end_turn",
    )
    follow_up = payload.get("llm_continuation_follow_up")
    provider_continuation_state = payload.get("provider_continuation_state")
    if (
        reason is None
        and end_turn is None
        and follow_up is None
        and (
            not include_provider_state
            or not isinstance(provider_continuation_state, dict)
        )
    ):
        return None
    result: dict[str, object] = {}
    if reason is not None:
        result["reason"] = reason
    if end_turn is not None:
        result["end_turn"] = end_turn
    if follow_up is not None:
        result["needs_follow_up"] = bool(follow_up)
    if include_provider_state and isinstance(provider_continuation_state, dict):
        result["provider_continuation_state"] = dict(provider_continuation_state)
    return result


def first_present(payload: dict[str, object], *keys: str) -> object | None:
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return None


def tool_run_links(payload: dict[str, object]) -> tuple[dict[str, object], ...]:
    raw_links = payload.get("tool_run_links")
    if not isinstance(raw_links, (list, tuple)):
        return ()
    links: list[dict[str, object]] = []
    for raw_link in raw_links:
        if isinstance(raw_link, dict):
            links.append(dict(raw_link))
    return tuple(links)


def assistant_progress_item_ids(payload: dict[str, object]) -> tuple[str, ...]:
    return _deduplicated_string_ids(payload.get("assistant_progress_item_ids"))


def assistant_session_item_ids(payload: dict[str, object]) -> tuple[str, ...]:
    return _deduplicated_string_ids(payload.get("session_item_ids"))


def final_response_summary(payload: dict[str, object]) -> dict[str, object]:
    summary: dict[str, object] = {}
    for key in (
        "llm_id",
        "llm_invocation_id",
        "request_render_snapshot_id",
        "runtime_request_mode",
        "session_item_ids",
        "tool_result_session_item_ids",
        "user_session_item_id",
    ):
        value = payload.get(key)
        if value is not None:
            summary[key] = value
    output_text = payload.get("output_text")
    if isinstance(output_text, str):
        summary["output_text_chars"] = len(output_text)
    return summary


def _deduplicated_string_ids(value: object) -> tuple[str, ...]:
    item_ids: list[str] = []
    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, str) and item.strip():
                normalized = item.strip()
                if normalized not in item_ids:
                    item_ids.append(normalized)
    return tuple(item_ids)
