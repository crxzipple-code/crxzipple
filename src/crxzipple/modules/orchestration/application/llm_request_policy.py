from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from crxzipple.modules.llm.domain import LlmCapability
from crxzipple.modules.orchestration.domain import OrchestrationRun


@dataclass(frozen=True, slots=True)
class EffectiveLlmRequestPolicy:
    reasoning_config: dict[str, object] = field(default_factory=dict)
    output_contract: dict[str, object] = field(default_factory=dict)
    provider_options: dict[str, object] = field(default_factory=dict)
    resolution_trace: tuple[dict[str, object], ...] = ()

    def to_payload(self) -> dict[str, object]:
        return {
            "reasoning_config": dict(self.reasoning_config),
            "output_contract": dict(self.output_contract),
            "provider_options": dict(self.provider_options),
            "resolution_trace": [dict(item) for item in self.resolution_trace],
        }


def resolve_effective_llm_request_policy(
    run: OrchestrationRun,
    *,
    llm_capabilities: tuple[LlmCapability, ...] = (),
    llm_api_family: str | None = None,
    runtime_defaults: dict[str, object] | None = None,
    llm_defaults: dict[str, object] | None = None,
    agent_llm_policy: dict[str, object] | None = None,
) -> EffectiveLlmRequestPolicy:
    deployment_defaults = dict(runtime_defaults or {})
    defaults = dict(llm_defaults or {})
    capabilities = set(llm_capabilities)
    provider_options: dict[str, object] = {}
    reasoning_config: dict[str, object] = {}
    output_contract: dict[str, object] = {}
    trace: list[dict[str, object]] = []

    _apply_default_request_params(
        provider_options=provider_options,
        reasoning_config=reasoning_config,
        output_contract=output_contract,
        trace=trace,
        capabilities=capabilities,
        defaults=deployment_defaults,
        source_name="settings.llm_request_defaults",
    )
    _apply_default_request_params(
        provider_options=provider_options,
        reasoning_config=reasoning_config,
        output_contract=output_contract,
        trace=trace,
        capabilities=capabilities,
        defaults=defaults,
        source_name="model_profile.default_params",
    )

    raw_options = run.metadata.get("llm_request_options")
    if isinstance(raw_options, dict):
        _merge_provider_options(
            target=provider_options,
            source=_dict_option(raw_options.get("provider_options")),
            trace=trace,
            source_name="run.metadata.llm_request_options.provider_options",
        )
        _merge_reasoning_config(
            target=reasoning_config,
            source=_dict_option(raw_options.get("reasoning_config")),
            trace=trace,
            capabilities=capabilities,
            source_name="run.metadata.llm_request_options.reasoning_config",
        )
        _merge_output_contract(
            target=output_contract,
            source=_dict_option(raw_options.get("output_contract")),
            trace=trace,
            source_name="run.metadata.llm_request_options.output_contract",
        )
        response_format = _dict_option(raw_options.get("response_format"))
        if response_format:
            output_contract["response_format"] = response_format
            trace.append(
                _trace(
                    field="output_contract.response_format",
                    source="run.metadata.llm_request_options.response_format",
                    value="configured",
                ),
            )
        output_schema = _dict_option(raw_options.get("output_schema"))
        if output_schema:
            output_contract["output_schema"] = output_schema
            trace.append(
                _trace(
                    field="output_contract.output_schema",
                    source="run.metadata.llm_request_options.output_schema",
                    value="configured",
                ),
            )

    _apply_agent_llm_policy(
        provider_options=provider_options,
        reasoning_config=reasoning_config,
        output_contract=output_contract,
        trace=trace,
        capabilities=capabilities,
        agent_llm_policy=dict(agent_llm_policy or {}),
    )
    _apply_prompt_cache_key(
        run=run,
        provider_options=provider_options,
        trace=trace,
    )
    _filter_provider_options_for_api_family(
        provider_options=provider_options,
        trace=trace,
        llm_api_family=llm_api_family,
    )

    return EffectiveLlmRequestPolicy(
        reasoning_config=reasoning_config,
        output_contract=output_contract,
        provider_options=provider_options,
        resolution_trace=tuple(trace),
    )


def _apply_default_request_params(
    *,
    provider_options: dict[str, object],
    reasoning_config: dict[str, object],
    output_contract: dict[str, object],
    trace: list[dict[str, object]],
    capabilities: set[LlmCapability],
    defaults: dict[str, object],
    source_name: str,
) -> None:
    max_output_tokens = _positive_int(defaults.get("max_output_tokens"))
    if max_output_tokens is not None:
        provider_options["max_output_tokens"] = max_output_tokens
        trace.append(
            _trace(
                field="provider_options.max_output_tokens",
                source=source_name,
                value=max_output_tokens,
            ),
        )
    reasoning_effort = _optional_text(defaults.get("reasoning_effort"))
    if reasoning_effort is not None:
        if LlmCapability.REASONING in capabilities:
            reasoning_config["effort"] = reasoning_effort
            trace.append(
                _trace(
                    field="reasoning_config.effort",
                    source=source_name,
                    value=reasoning_effort,
                ),
            )
        else:
            trace.append(
                _trace(
                    field="reasoning_config.effort",
                    source=source_name,
                    value=reasoning_effort,
                    status="downgraded",
                    reason="llm_capability_not_supported",
                ),
            )
    service_tier = _optional_text(defaults.get("service_tier"))
    if service_tier is not None:
        provider_options["service_tier"] = service_tier
        trace.append(
            _trace(
                field="provider_options.service_tier",
                source=source_name,
                value=service_tier,
            ),
        )
    prompt_cache_enabled = defaults.get("prompt_cache_enabled")
    if isinstance(prompt_cache_enabled, bool):
        provider_options["prompt_cache_enabled"] = prompt_cache_enabled
        trace.append(
            _trace(
                field="provider_options.prompt_cache_enabled",
                source=source_name,
                value=prompt_cache_enabled,
            ),
        )
    response_verbosity = _optional_text(defaults.get("response_verbosity"))
    if response_verbosity is not None:
        text_options = dict(_dict_option(provider_options.get("text")))
        text_options["verbosity"] = response_verbosity
        provider_options["text"] = text_options
        trace.append(
            _trace(
                field="provider_options.text.verbosity",
                source=source_name,
                value=response_verbosity,
            ),
        )
    text_options = _dict_option(defaults.get("text"))
    if text_options:
        provider_options["text"] = text_options
        trace.append(
            _trace(
                field="provider_options.text",
                source=source_name,
                value="configured",
            ),
        )
    include_values = _text_tuple(defaults.get("include"))
    if include_values:
        provider_options["include"] = list(include_values)
        trace.append(
            _trace(
                field="provider_options.include",
                source=source_name,
                value="configured",
            ),
        )
    include_reasoning_encrypted = defaults.get("include_reasoning_encrypted_content")
    if isinstance(include_reasoning_encrypted, bool):
        include = _text_tuple(provider_options.get("include"))
        include_list = list(include)
        marker = "reasoning.encrypted_content"
        if include_reasoning_encrypted and marker not in include_list:
            include_list.append(marker)
        if not include_reasoning_encrypted:
            include_list = [item for item in include_list if item != marker]
        provider_options["include"] = include_list
        trace.append(
            _trace(
                field="provider_options.include.reasoning.encrypted_content",
                source=source_name,
                value=include_reasoning_encrypted,
            ),
        )
    parallel_tool_calls = defaults.get("parallel_tool_calls")
    if isinstance(parallel_tool_calls, bool):
        provider_options["parallel_tool_calls"] = parallel_tool_calls
        trace.append(
            _trace(
                field="provider_options.parallel_tool_calls",
                source=source_name,
                value=parallel_tool_calls,
            ),
        )
    reasoning_summary_default_visibility = _optional_text(
        defaults.get("reasoning_summary_default_visibility"),
    )
    if reasoning_summary_default_visibility is not None:
        output_contract["reasoning_summary_default_visibility"] = (
            reasoning_summary_default_visibility
        )
        trace.append(
            _trace(
                field="output_contract.reasoning_summary_default_visibility",
                source=source_name,
                value=reasoning_summary_default_visibility,
            ),
        )
    trace_raw_provider_payload = defaults.get("trace_raw_provider_payload")
    if isinstance(trace_raw_provider_payload, bool):
        provider_options["trace_raw_provider_payload"] = trace_raw_provider_payload
        trace.append(
            _trace(
                field="provider_options.trace_raw_provider_payload",
                source=source_name,
                value=trace_raw_provider_payload,
            ),
        )
    extra_body = defaults.get("extra_body")
    if isinstance(extra_body, dict) and extra_body:
        provider_options["extra_body"] = dict(extra_body)
        trace.append(
            _trace(
                field="provider_options.extra_body",
                source=source_name,
                value="configured",
            ),
        )


def _apply_agent_llm_policy(
    *,
    provider_options: dict[str, object],
    reasoning_config: dict[str, object],
    output_contract: dict[str, object],
    trace: list[dict[str, object]],
    capabilities: set[LlmCapability],
    agent_llm_policy: dict[str, object],
) -> None:
    if not agent_llm_policy:
        return

    source_name = "agent_profile.llm_policy"
    reasoning_summary_policy = _optional_text(
        agent_llm_policy.get("reasoning_summary_policy"),
    )
    if reasoning_summary_policy == "visible_and_replay_when_provider_supports":
        if LlmCapability.REASONING in capabilities:
            reasoning_config.setdefault("summary", "auto")
            trace.append(
                _trace(
                    field="reasoning_config.summary",
                    source=source_name,
                    value=reasoning_config["summary"],
                ),
            )
        else:
            trace.append(
                _trace(
                    field="reasoning_config.summary",
                    source=source_name,
                    value=reasoning_summary_policy,
                    status="downgraded",
                    reason="llm_capability_not_supported",
                ),
            )

    final_answer_policy = _optional_text(agent_llm_policy.get("final_answer_policy"))
    if final_answer_policy is not None:
        output_contract["final_answer_policy"] = final_answer_policy
        trace.append(
            _trace(
                field="output_contract.final_answer_policy",
                source=source_name,
                value=final_answer_policy,
            ),
        )

    tool_use_policy = _optional_text(agent_llm_policy.get("tool_use_policy"))
    if tool_use_policy is not None:
        output_contract["tool_use_policy"] = tool_use_policy
        trace.append(
            _trace(
                field="output_contract.tool_use_policy",
                source=source_name,
                value=tool_use_policy,
            ),
        )

    parallel_tool_calls_policy = _optional_text(
        agent_llm_policy.get("parallel_tool_calls_policy"),
    )
    if parallel_tool_calls_policy in {"enabled", "disabled"}:
        provider_options["parallel_tool_calls"] = (
            parallel_tool_calls_policy == "enabled"
        )
        trace.append(
            _trace(
                field="provider_options.parallel_tool_calls",
                source=source_name,
                value=provider_options["parallel_tool_calls"],
            ),
        )


def _merge_provider_options(
    *,
    target: dict[str, object],
    source: dict[str, object],
    trace: list[dict[str, object]],
    source_name: str,
) -> None:
    for key, value in source.items():
        target[key] = value
        trace.append(_trace(field=f"provider_options.{key}", source=source_name, value="configured"))


def _apply_prompt_cache_key(
    *,
    run: OrchestrationRun,
    provider_options: dict[str, object],
    trace: list[dict[str, object]],
) -> None:
    if provider_options.get("prompt_cache_key") is not None:
        return
    if provider_options.get("prompt_cache_enabled") is not True:
        return
    cache_key = _prompt_cache_key_for_run(run)
    if cache_key is None:
        trace.append(
            _trace(
                field="provider_options.prompt_cache_key",
                source="derived.run_context",
                value="missing",
                status="downgraded",
                reason="stable_session_key_not_available",
            ),
        )
        return
    provider_options["prompt_cache_key"] = cache_key
    trace.append(
        _trace(
            field="provider_options.prompt_cache_key",
            source="derived.run_context",
            value=cache_key,
        ),
    )


def _prompt_cache_key_for_run(run: OrchestrationRun) -> str | None:
    session_key = _optional_text(run.metadata.get("session_key"))
    active_session_id = _optional_text(run.active_session_id)
    lane_key = _optional_text(run.lane_key)
    stable = session_key or active_session_id or lane_key
    if stable is None:
        return None
    agent_id = _optional_text(run.agent_id) or "agent"
    return f"crxzipple:{agent_id}:{stable}"


_RESPONSES_API_FAMILIES = frozenset(
    {
        "openai_responses",
        "openai_codex_responses",
    },
)

_RESPONSES_ONLY_PROVIDER_OPTIONS = frozenset(
    {
        "include",
        "parallel_tool_calls",
        "prompt_cache_enabled",
        "prompt_cache_key",
        "text",
    },
)


def _filter_provider_options_for_api_family(
    *,
    provider_options: dict[str, object],
    trace: list[dict[str, object]],
    llm_api_family: str | None,
) -> None:
    api_family = _optional_text(llm_api_family)
    if api_family is None or api_family in _RESPONSES_API_FAMILIES:
        return
    for key in tuple(provider_options):
        if key not in _RESPONSES_ONLY_PROVIDER_OPTIONS:
            continue
        provider_options.pop(key, None)
        trace.append(
            _trace(
                field=f"provider_options.{key}",
                source="provider_capability_filter",
                value="removed",
                status="downgraded",
                reason=f"unsupported_api_family:{api_family}",
            ),
        )


def _merge_reasoning_config(
    *,
    target: dict[str, object],
    source: dict[str, object],
    trace: list[dict[str, object]],
    capabilities: set[LlmCapability],
    source_name: str,
) -> None:
    if not source:
        return
    if LlmCapability.REASONING not in capabilities:
        for key, value in source.items():
            trace.append(
                _trace(
                    field=f"reasoning_config.{key}",
                    source=source_name,
                    value=value,
                    status="downgraded",
                    reason="llm_capability_not_supported",
                ),
            )
        return
    for key, value in source.items():
        target[key] = value
        trace.append(_trace(field=f"reasoning_config.{key}", source=source_name, value=value))


def _merge_output_contract(
    *,
    target: dict[str, object],
    source: dict[str, object],
    trace: list[dict[str, object]],
    source_name: str,
) -> None:
    for key, value in source.items():
        target[key] = value
        trace.append(_trace(field=f"output_contract.{key}", source=source_name, value="configured"))


def _trace(
    *,
    field: str,
    source: str,
    value: object,
    status: str = "applied",
    reason: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "field": field,
        "source": source,
        "status": status,
        "value": value,
    }
    if reason is not None:
        payload["reason"] = reason
    return payload


def _dict_option(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _text_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        normalized = value.strip()
        return (normalized,) if normalized else ()
    if not isinstance(value, (list, tuple)):
        return ()
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if normalized and normalized not in items:
            items.append(normalized)
    return tuple(items)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _positive_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return None
    return resolved if resolved > 0 else None
