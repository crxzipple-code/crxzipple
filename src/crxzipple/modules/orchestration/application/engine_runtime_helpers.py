from __future__ import annotations

from collections.abc import Callable
from typing import Any

from crxzipple.modules.llm.application.runtime_request import RuntimeLlmRequest
from crxzipple.modules.orchestration.application.engine_models import AdvanceContext
from crxzipple.modules.orchestration.application.llm_request_policy import (
    EffectiveLlmRequestPolicy,
    resolve_effective_llm_request_policy,
)
from crxzipple.modules.orchestration.application.runtime_llm_request_draft import (
    RuntimeLlmRequestDraft,
)
from crxzipple.modules.orchestration.domain import OrchestrationRun


def llm_request_metadata(context: AdvanceContext) -> dict[str, object]:
    return context.request_envelope.request_metadata()


def response_format_from_output_contract(
    request_envelope: RuntimeLlmRequest,
) -> dict[str, object] | None:
    return request_envelope.response_format()


def llm_request_options_from_run_metadata(
    run: OrchestrationRun,
) -> dict[str, dict[str, object]]:
    raw_options = run.metadata.get("llm_request_options")
    if not isinstance(raw_options, dict):
        return {
            "provider_options": {},
            "reasoning_config": {},
            "output_contract": {},
        }
    provider_options = _dict_option(raw_options.get("provider_options"))
    reasoning_config = _dict_option(raw_options.get("reasoning_config"))
    output_contract = _dict_option(raw_options.get("output_contract"))
    response_format = _dict_option(raw_options.get("response_format"))
    if response_format:
        output_contract["response_format"] = response_format
    output_schema = _dict_option(raw_options.get("output_schema"))
    if output_schema:
        output_contract["output_schema"] = output_schema
    return {
        "provider_options": provider_options,
        "reasoning_config": reasoning_config,
        "output_contract": output_contract,
    }


def llm_request_options_from_run(
    run: OrchestrationRun,
    *,
    draft: RuntimeLlmRequestDraft,
) -> dict[str, object]:
    policy = resolve_effective_llm_request_policy(
        run,
        llm_capabilities=draft.llm_capabilities,
        llm_api_family=draft.llm_api_family,
        runtime_defaults=draft.runtime_llm_defaults,
        llm_defaults=draft.llm_defaults,
        agent_llm_policy=draft.llm_policy,
    )
    return llm_request_options_from_policy(policy)


def llm_request_options_from_policy(
    policy: EffectiveLlmRequestPolicy,
) -> dict[str, object]:
    return {
        "provider_options": dict(policy.provider_options),
        "reasoning_config": dict(policy.reasoning_config),
        "output_contract": dict(policy.output_contract),
        "policy": policy,
    }


def tool_surface_snapshot_builder(tool_execution_port: object) -> Callable[..., object] | None:
    builder = getattr(tool_execution_port, "build_tool_surface", None)
    return builder if callable(builder) else None


def llm_response_item_ids(invocation: Any) -> tuple[str, ...]:
    response_items = getattr(invocation, "response_items", None)
    if not isinstance(response_items, (list, tuple)) or not response_items:
        return ()
    item_ids: list[str] = []
    for item in response_items:
        item_id = getattr(item, "id", None)
        if isinstance(item_id, str) and item_id.strip():
            normalized = item_id.strip()
            if normalized not in item_ids:
                item_ids.append(normalized)
    return tuple(item_ids)


def continuation_needs_follow_up(invocation: Any) -> bool:
    continuation = getattr(invocation, "continuation", None)
    return bool(getattr(continuation, "needs_follow_up", False))


def continuation_reason(invocation: Any) -> str | None:
    continuation = getattr(invocation, "continuation", None)
    reason = getattr(continuation, "reason", None)
    text = _enum_value(reason)
    return text if text != "-" else None


def continuation_end_turn(invocation: Any) -> bool | None:
    continuation = getattr(invocation, "continuation", None)
    value = getattr(continuation, "end_turn", None)
    return value if isinstance(value, bool) else None


def provider_continuation_state_from_run(
    run: OrchestrationRun,
) -> dict[str, object] | None:
    raw_state = run.metadata.get("provider_continuation_state")
    if not isinstance(raw_state, dict):
        return None
    return dict(raw_state)


def unique_ids(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return tuple(unique)


def terminal_loop_diagnostic(invocation: Any) -> dict[str, object]:
    if continuation_needs_follow_up(invocation):
        return {}
    response_items = getattr(invocation, "response_items", None)
    if not isinstance(response_items, (list, tuple)) or not response_items:
        return {}
    item_kinds = tuple(_enum_value(getattr(item, "kind", None)) for item in response_items)
    item_phases = tuple(_enum_value(getattr(item, "phase", None)) for item in response_items)
    if "tool_call" in item_kinds or "provider_external_item" in item_kinds:
        return {}
    has_final_answer = any(
        kind == "assistant_message" and phase == "final_answer"
        for kind, phase in zip(item_kinds, item_phases, strict=False)
    )
    if has_final_answer:
        return {}
    commentary_or_reasoning_only = all(
        kind == "reasoning"
        or (kind == "assistant_message" and phase == "commentary")
        for kind, phase in zip(item_kinds, item_phases, strict=False)
    )
    if not commentary_or_reasoning_only:
        return {}
    return {
        "code": "llm_incomplete_terminal_response",
        "reason": "commentary_or_reasoning_without_final_answer_or_follow_up",
        "item_kinds": list(item_kinds),
        "item_phases": list(item_phases),
    }


def optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _dict_option(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _enum_value(value: Any) -> str:
    raw_value = getattr(value, "value", value)
    text = str(raw_value or "").strip()
    return text or "-"
