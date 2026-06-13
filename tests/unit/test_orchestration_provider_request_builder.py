from __future__ import annotations

from crxzipple.app.integration.context_workspace_orchestration.snapshot_metadata import (
    browser_investigation_affordance_metadata,
)
from crxzipple.modules.llm.domain import LlmMessage, LlmMessageRole, ToolSchema
from crxzipple.modules.llm.domain import LlmCapability
from crxzipple.modules.orchestration.application.ports import (
    ContextRenderSnapshotRecord,
)
from crxzipple.modules.orchestration.application.engine import (
    _llm_request_options_from_run,
    _llm_request_options_from_run_metadata,
)
from crxzipple.modules.orchestration.application.prompt_input import RunPromptInput
from crxzipple.modules.orchestration.application.provider_request import (
    ProviderPromptRequestBuilder,
)
from crxzipple.modules.orchestration.application.prompting import (
    PromptMode,
    RunSurfacePolicy,
)
from crxzipple.modules.orchestration.application.tool_resolver import (
    ResolvedTool,
    ResolvedToolSet,
)
from crxzipple.modules.orchestration.domain import InboundInstruction, OrchestrationRun
from crxzipple.modules.tool.domain import Tool, ToolExecutionTarget


def test_prompt_with_context_snapshot_inserts_tree_after_system_prefix() -> None:
    builder = ProviderPromptRequestBuilder()
    prompt = _prompt(
        messages=(
            LlmMessage(role=LlmMessageRole.SYSTEM, content="system one"),
            LlmMessage(role=LlmMessageRole.SYSTEM, content="system two"),
            LlmMessage(role=LlmMessageRole.USER, content="hello"),
        ),
        tool_schemas=(ToolSchema(name="old.tool"),),
    )
    snapshot = ContextRenderSnapshotRecord(
        snapshot_id="ctxsnap_1",
        prompt_body="<context_tree><node id=\"run.flow\" /></context_tree>",
        tool_schemas=(ToolSchema(name="weather.lookup"),),
        artifact_content_blocks=(
            {
                "type": "image_ref",
                "image_ref": {"artifact_id": "artifact-1"},
            },
        ),
    )

    result = builder.prompt_with_context_snapshot(prompt, snapshot)

    assert tuple(message.role for message in result.messages) == (
        LlmMessageRole.SYSTEM,
        LlmMessageRole.SYSTEM,
        LlmMessageRole.SYSTEM,
        LlmMessageRole.USER,
        LlmMessageRole.USER,
    )
    assert result.messages[2].content == snapshot.prompt_body
    assert result.messages[2].metadata["prompt_block_kind"] == "context_workspace"
    assert result.messages[-1].metadata["prompt_block_kind"] == "context_artifacts"
    assert result.tool_schemas == snapshot.tool_schemas


def test_request_envelope_can_use_snapshot_without_replaying_context_messages() -> None:
    builder = ProviderPromptRequestBuilder()
    prompt = _prompt(
        messages=(
            LlmMessage(role=LlmMessageRole.SYSTEM, content="system"),
            LlmMessage(role=LlmMessageRole.USER, content="hello"),
        ),
        tool_schemas=(ToolSchema(name="old.tool"),),
    )
    snapshot = ContextRenderSnapshotRecord(
        snapshot_id="ctxsnap_delta",
        prompt_body="<context_tree><node id=\"session.current\" /></context_tree>",
        included_node_ids=("session.current",),
        provider_attachments={"tool_schemas": [{"name": "weather.lookup"}]},
        tool_schemas=(ToolSchema(name="weather.lookup"),),
        artifact_content_blocks=(
            {
                "type": "image_ref",
                "image_ref": {"artifact_id": "artifact-1"},
            },
        ),
    )
    resolved_tools = ResolvedToolSet(
        tools=(_resolved_tool("tool.weather", schema_name="weather.lookup"),),
    )

    envelope = builder.request_envelope(
        prompt=prompt,
        context_render_snapshot=snapshot,
        resolved_tools=resolved_tools,
        snapshot_metadata=snapshot.metadata,
        include_context_messages=False,
    )

    assert tuple(message.content for message in envelope.messages) == (
        "system",
        "hello",
    )
    assert all(
        message.metadata.get("prompt_block_kind") != "context_workspace"
        for message in envelope.messages
    )
    assert envelope.tool_schemas == snapshot.tool_schemas
    assert envelope.context_surface.snapshot_id == "ctxsnap_delta"
    assert envelope.context_surface.rendered_context == snapshot.prompt_body
    assert envelope.tool_surface.functions[0].name == "weather.lookup"
    assert envelope.metadata["context_render_snapshot_id"] == "ctxsnap_delta"


def test_resolved_tools_for_prompt_filters_to_mirrored_interactive_schemas() -> None:
    builder = ProviderPromptRequestBuilder()
    weather = _resolved_tool("tool.weather", schema_name="weather.lookup")
    search = _resolved_tool("tool.search", schema_name="search.web")
    prompt = _prompt(tool_schemas=(ToolSchema(name="weather.lookup"),))
    snapshot = ContextRenderSnapshotRecord(
        snapshot_id="ctxsnap_1",
        tool_schemas=(ToolSchema(name="weather.lookup"),),
    )

    result = builder.resolved_tools_for_prompt(
        ResolvedToolSet(tools=(weather, search)),
        prompt,
        snapshot,
    )

    assert tuple(item.schema.name for item in result.tools) == ("weather.lookup",)


def test_resolved_tools_for_prompt_clears_interactive_tools_without_snapshot_schema() -> None:
    builder = ProviderPromptRequestBuilder()
    prompt = _prompt(tool_schemas=(ToolSchema(name="weather.lookup"),))

    result = builder.resolved_tools_for_prompt(
        ResolvedToolSet(tools=(_resolved_tool("tool.weather", schema_name="weather.lookup"),)),
        prompt,
        ContextRenderSnapshotRecord(snapshot_id="ctxsnap_1", tool_schemas=None),
    )

    assert result.tools == ()


def test_request_envelope_carries_context_and_tool_surface() -> None:
    builder = ProviderPromptRequestBuilder()
    prompt = _prompt(
        messages=(
            LlmMessage(role=LlmMessageRole.SYSTEM, content="system"),
            LlmMessage(
                role=LlmMessageRole.USER,
                content="hello",
                metadata={
                    "session_item_id": "item-user-1",
                    "session_id": "session-instance-1",
                    "sequence_no": 3,
                    "kind": "user_message",
                },
            ),
        ),
        tool_schemas=(ToolSchema(name="browser.network.inspect"),),
    )
    snapshot = ContextRenderSnapshotRecord(
        snapshot_id="ctxsnap-envelope-1",
        prompt_body="<context_tree><node id=\"tools\" /></context_tree>",
        estimate={"estimated_tokens": 42},
        included_node_ids=("runtime.contract",),
        mirrored_node_ids=("tools.browser.network",),
        included_refs=({"node_id": "runtime.contract", "kind": "runtime"},),
        collapsed_refs=({"node_id": "history.old", "kind": "history"},),
        protocol_required_refs=(
            {"item_id": "item-tool-result-1", "call_id": "call-1"},
        ),
        metadata={
            "tree_schema_version": "2026-06-11",
            "tool_schema_mirror_budget_status": "ok",
            "tool_schema_mirror_default_group_matches": [
                {
                    "source_id": "configured.browser",
                    "group_key": "network",
                    "matched_schema_names": ["browser.network.inspect"],
                },
            ],
        },
        provider_attachments={"files": [{"artifact_id": "artifact-1"}]},
        tool_schemas=(ToolSchema(name="browser.network.inspect"),),
    )
    resolved_tools = ResolvedToolSet(
        tools=(
            _resolved_tool(
                "tool.browser.network.inspect",
                schema_name="browser.network.inspect",
            ),
        ),
    )

    envelope = builder.request_envelope(
        prompt=prompt,
        context_render_snapshot=snapshot,
        resolved_tools=resolved_tools,
        snapshot_metadata=snapshot.metadata,
        provider_options={"service_tier": "default"},
        reasoning_config={"summary": "auto"},
        output_contract={"final_answer": "required"},
    )

    assert envelope.context_surface.snapshot_id == "ctxsnap-envelope-1"
    assert envelope.context_surface.included_refs[0]["node_id"] == "runtime.contract"
    assert envelope.context_surface.protocol_required_refs[0]["call_id"] == "call-1"
    assert envelope.context_surface.diagnostics["tool_schema_mirror_budget_status"] == "ok"
    assert envelope.tool_surface.id == "tool_surface:ctxsnap-envelope-1"
    assert envelope.tool_surface.functions[0].source_id == "configured.browser"
    assert envelope.tool_surface.functions[0].group_key == "network"
    assert envelope.tool_surface.metadata["function_count"] == 1
    assert envelope.tool_surface.metadata["source_refs"] == [
        {
            "tool_id": "tool.browser.network.inspect",
            "name": "browser.network.inspect",
            "enabled": True,
            "always_visible": True,
            "source_id": "configured.browser",
            "group_key": "network",
        }
    ]
    assert envelope.metadata["context_render_snapshot_id"] == "ctxsnap-envelope-1"
    assert envelope.metadata["tool_surface_id"] == "tool_surface:ctxsnap-envelope-1"
    assert envelope.metadata["direct_session_item_refs"][0]["item_id"] == "item-user-1"
    payload = envelope.to_payload()
    assert payload["context_surface"]["provider_attachment_mirror"] == {
        "files": [{"artifact_id": "artifact-1"}],
    }
    assert payload["tool_surface"]["functions"][0]["schema"]["name"] == (
        "browser.network.inspect"
    )
    assert payload["provider_options"]["service_tier"] == "default"
    assert payload["reasoning_config"]["summary"] == "auto"
    assert payload["output_contract"]["final_answer"] == "required"


def test_request_envelope_persists_visible_tool_surface_snapshot() -> None:
    calls: list[dict[str, object]] = []

    def build_tool_surface(**kwargs: object) -> dict[str, object]:
        calls.append(dict(kwargs))
        return {"surface_id": str(kwargs["surface_id"])}

    builder = ProviderPromptRequestBuilder(
        tool_surface_snapshot_builder=build_tool_surface,
    )
    prompt = _prompt(
        tool_schemas=(
            ToolSchema(name="browser.network.inspect"),
            ToolSchema(name="browser.form.fill"),
        ),
    )
    snapshot = ContextRenderSnapshotRecord(
        snapshot_id="ctxsnap-visible-tools",
        tool_schemas=(ToolSchema(name="browser.network.inspect"),),
    )
    network = _resolved_tool(
        "tool.browser.network.inspect",
        schema_name="browser.network.inspect",
    )
    form = _resolved_tool("tool.browser.form.fill", schema_name="browser.form.fill")

    envelope = builder.request_envelope(
        prompt=prompt,
        context_render_snapshot=snapshot,
        resolved_tools=ResolvedToolSet(tools=(network, form)),
        snapshot_metadata={},
        run_id="run-visible-tools",
        agent_id="assistant",
    )

    assert len(calls) == 1
    assert str(calls[0]["surface_id"]).startswith(
        "tool_surface:ctxsnap-visible-tools:",
    )
    assert calls[0]["session_id"] == "session-instance-1"
    assert calls[0]["run_id"] == "run-visible-tools"
    assert calls[0]["agent_id"] == "assistant"
    assert calls[0]["tool_ids"] == ("tool.browser.network.inspect",)
    assert calls[0]["persist"] is True
    assert calls[0]["runtime_context"] == {
        "agent_id": "assistant",
        "run_id": "run-visible-tools",
        "session_key": "session:test",
        "active_session_id": "session-instance-1",
        "context_render_snapshot_id": "ctxsnap-visible-tools",
        "provider_visible_tool_count": 1,
    }
    assert envelope.metadata["tool_surface_snapshot_persisted"] is True
    assert str(envelope.metadata["tool_surface_snapshot_id"]).startswith(
        "tool_surface:ctxsnap-visible-tools:",
    )
    assert str(envelope.metadata["tool_surface_id"]).startswith(
        "tool_surface:ctxsnap-visible-tools:",
    )
    assert envelope.tool_surface.metadata["base_tool_surface_id"] == (
        "tool_surface:ctxsnap-visible-tools"
    )
    assert [function.tool_id for function in envelope.tool_surface.functions] == [
        "tool.browser.network.inspect",
    ]


def test_request_envelope_can_skip_tool_surface_snapshot_persistence() -> None:
    calls: list[dict[str, object]] = []
    builder = ProviderPromptRequestBuilder(
        tool_surface_snapshot_builder=lambda **kwargs: calls.append(dict(kwargs)),
    )

    envelope = builder.request_envelope(
        prompt=_prompt(tool_schemas=(ToolSchema(name="browser.network.inspect"),)),
        context_render_snapshot=ContextRenderSnapshotRecord(
            snapshot_id="ctxsnap-preview",
            tool_schemas=(ToolSchema(name="browser.network.inspect"),),
        ),
        resolved_tools=ResolvedToolSet(
            tools=(
                _resolved_tool(
                    "tool.browser.network.inspect",
                    schema_name="browser.network.inspect",
                ),
            ),
        ),
        snapshot_metadata={},
        persist_tool_surface_snapshot=False,
    )

    assert calls == []
    assert "tool_surface_snapshot_persisted" not in envelope.metadata
    assert envelope.metadata["tool_surface_id"] == "tool_surface:ctxsnap-preview"


def test_run_metadata_llm_request_options_split_provider_reasoning_and_output() -> None:
    run = OrchestrationRun(
        id="run-request-options",
        inbound_instruction=InboundInstruction(source="web", content="hello"),
        metadata={
            "llm_request_options": {
                "provider_options": {
                    "service_tier": "default",
                    "max_output_tokens": 1200,
                },
                "reasoning_config": {"effort": "medium", "summary": "auto"},
                "output_contract": {"final_answer": "required"},
                "response_format": {"type": "json_object"},
                "output_schema": {"name": "flight_answer"},
            },
        },
    )

    options = _llm_request_options_from_run_metadata(run)

    assert options["provider_options"]["service_tier"] == "default"
    assert options["provider_options"]["max_output_tokens"] == 1200
    assert options["reasoning_config"] == {"effort": "medium", "summary": "auto"}
    assert options["output_contract"]["final_answer"] == "required"
    assert options["output_contract"]["response_format"] == {"type": "json_object"}
    assert options["output_contract"]["output_schema"] == {"name": "flight_answer"}


def test_effective_llm_request_policy_merges_model_defaults_and_run_override() -> None:
    run = OrchestrationRun(
        id="run-effective-policy",
        inbound_instruction=InboundInstruction(source="web", content="hello"),
        metadata={
            "llm_request_options": {
                "provider_options": {"service_tier": "default"},
                "reasoning_config": {"summary": "auto"},
            },
        },
    )
    prompt = _prompt(
        llm_capabilities=(LlmCapability.REASONING,),
        llm_defaults={
            "max_output_tokens": 800,
            "reasoning_effort": "medium",
        },
    )

    options = _llm_request_options_from_run(run, prompt=prompt)

    assert options["provider_options"] == {
        "max_output_tokens": 800,
        "service_tier": "default",
    }
    assert options["reasoning_config"] == {
        "effort": "medium",
        "summary": "auto",
    }
    policy_payload = options["policy"].to_payload()
    assert policy_payload["resolution_trace"][0]["source"] == (
        "model_profile.default_params"
    )
    assert {
        item["field"]
        for item in policy_payload["resolution_trace"]
    } >= {
        "provider_options.max_output_tokens",
        "provider_options.service_tier",
        "reasoning_config.effort",
        "reasoning_config.summary",
    }


def test_effective_llm_request_policy_applies_runtime_defaults_before_model_and_run() -> None:
    run = OrchestrationRun(
        id="run-effective-runtime-defaults",
        inbound_instruction=InboundInstruction(source="web", content="hello"),
        metadata={
            "llm_request_options": {
                "provider_options": {"service_tier": "run-tier"},
            },
        },
    )
    prompt = _prompt(
        llm_capabilities=(LlmCapability.REASONING,),
        runtime_llm_defaults={
            "max_output_tokens": 400,
            "reasoning_effort": "low",
            "service_tier": "runtime-tier",
            "parallel_tool_calls": True,
            "trace_raw_provider_payload": True,
        },
        llm_defaults={
            "max_output_tokens": 800,
            "reasoning_effort": "medium",
        },
    )

    options = _llm_request_options_from_run(run, prompt=prompt)

    assert options["provider_options"] == {
        "max_output_tokens": 800,
        "service_tier": "run-tier",
        "parallel_tool_calls": True,
        "trace_raw_provider_payload": True,
    }
    assert options["reasoning_config"] == {"effort": "medium"}
    trace = options["policy"].to_payload()["resolution_trace"]
    assert any(
        item["source"] == "settings.llm_request_defaults"
        and item["field"] == "provider_options.max_output_tokens"
        for item in trace
    )
    assert trace[-1] == {
        "field": "provider_options.service_tier",
        "source": "run.metadata.llm_request_options.provider_options",
        "status": "applied",
        "value": "configured",
    }


def test_effective_llm_request_policy_applies_codex_style_provider_options() -> None:
    run = OrchestrationRun(
        id="run-effective-codex-options",
        inbound_instruction=InboundInstruction(source="web", content="hello"),
        agent_id="assistant",
        metadata={"session_key": "session:codex-like"},
    )
    prompt = _prompt(
        llm_capabilities=(LlmCapability.REASONING,),
        llm_api_family="openai_codex_responses",
        runtime_llm_defaults={
            "service_tier": "priority",
        },
        llm_defaults={
            "parallel_tool_calls": True,
            "prompt_cache_enabled": True,
            "response_verbosity": "low",
            "include_reasoning_encrypted_content": True,
            "include": ["other.provider.item"],
        },
    )

    options = _llm_request_options_from_run(run, prompt=prompt)

    assert options["provider_options"] == {
        "service_tier": "priority",
        "parallel_tool_calls": True,
        "prompt_cache_enabled": True,
        "text": {"verbosity": "low"},
        "include": ["other.provider.item", "reasoning.encrypted_content"],
        "prompt_cache_key": "crxzipple:assistant:session:codex-like",
    }
    trace = options["policy"].to_payload()["resolution_trace"]
    assert {
        item["field"]
        for item in trace
    } >= {
        "provider_options.parallel_tool_calls",
        "provider_options.prompt_cache_enabled",
        "provider_options.text.verbosity",
        "provider_options.include.reasoning.encrypted_content",
        "provider_options.include",
        "provider_options.prompt_cache_key",
    }


def test_effective_llm_request_policy_filters_responses_only_options_for_non_responses_provider() -> None:
    run = OrchestrationRun(
        id="run-effective-non-responses-options",
        inbound_instruction=InboundInstruction(source="web", content="hello"),
        agent_id="assistant",
        metadata={"session_key": "session:anthropic"},
    )
    prompt = _prompt(
        llm_capabilities=(LlmCapability.REASONING,),
        llm_api_family="anthropic_messages",
        runtime_llm_defaults={
            "service_tier": "default",
            "parallel_tool_calls": True,
            "prompt_cache_enabled": True,
            "response_verbosity": "low",
            "include_reasoning_encrypted_content": True,
        },
        llm_defaults={"max_output_tokens": 1000},
    )

    options = _llm_request_options_from_run(run, prompt=prompt)

    assert options["provider_options"] == {
        "service_tier": "default",
        "max_output_tokens": 1000,
    }
    trace = options["policy"].to_payload()["resolution_trace"]
    downgraded = [
        item
        for item in trace
        if item["source"] == "provider_capability_filter"
    ]
    assert {
        item["field"]
        for item in downgraded
    } == {
        "provider_options.parallel_tool_calls",
        "provider_options.prompt_cache_enabled",
        "provider_options.prompt_cache_key",
        "provider_options.text",
        "provider_options.include",
    }
    assert all(item["status"] == "downgraded" for item in downgraded)


def test_effective_llm_request_policy_applies_agent_llm_policy() -> None:
    run = OrchestrationRun(
        id="run-effective-agent-policy",
        inbound_instruction=InboundInstruction(source="web", content="hello"),
    )
    prompt = _prompt(
        llm_capabilities=(LlmCapability.REASONING,),
        llm_policy={
            "reasoning_summary_policy": "visible_and_replay_when_provider_supports",
            "final_answer_policy": "phase_or_codex_unknown_fallback",
            "tool_use_policy": "auto",
            "parallel_tool_calls_policy": "disabled",
        },
    )

    options = _llm_request_options_from_run(run, prompt=prompt)

    assert options["reasoning_config"] == {"summary": "auto"}
    assert options["provider_options"] == {"parallel_tool_calls": False}
    assert options["output_contract"] == {
        "final_answer_policy": "phase_or_codex_unknown_fallback",
        "tool_use_policy": "auto",
    }
    trace = options["policy"].to_payload()["resolution_trace"]
    assert {
        item["field"]
        for item in trace
        if item["source"] == "agent_profile.llm_policy"
    } == {
        "reasoning_config.summary",
        "output_contract.final_answer_policy",
        "output_contract.tool_use_policy",
        "provider_options.parallel_tool_calls",
    }


def test_effective_llm_request_policy_downgrades_unsupported_reasoning() -> None:
    run = OrchestrationRun(
        id="run-effective-policy-downgrade",
        inbound_instruction=InboundInstruction(source="web", content="hello"),
        metadata={
            "llm_request_options": {
                "reasoning_config": {"summary": "auto"},
            },
        },
    )
    prompt = _prompt(
        llm_capabilities=(),
        llm_defaults={"reasoning_effort": "high"},
    )

    options = _llm_request_options_from_run(run, prompt=prompt)

    assert options["reasoning_config"] == {}
    trace = options["policy"].to_payload()["resolution_trace"]
    downgraded = [item for item in trace if item["status"] == "downgraded"]
    assert [item["field"] for item in downgraded] == [
        "reasoning_config.effort",
        "reasoning_config.summary",
    ]
    assert all(
        item["reason"] == "llm_capability_not_supported"
        for item in downgraded
    )


def test_request_metadata_carries_budget_fields_from_snapshot_metadata() -> None:
    builder = ProviderPromptRequestBuilder()
    prompt = _prompt()

    metadata = builder.request_metadata(
        prompt=prompt,
        context_render_snapshot_id="ctxsnap_1",
        snapshot_metadata={
            "tree_schema_version": "2026-06-05",
            "rendered_prompt_estimated_tokens": 10,
            "direct_transcript_estimated_tokens": 2,
            "mirrored_tool_schema_estimated_tokens": 3,
            "artifact_content_estimated_tokens": 4,
            "estimated_provider_prompt_tokens": 19,
            "tool_schema_mirror_budget_status": "ok",
            "tool_schema_mirror_default_schema_source": "source_prompt.default",
            "tool_schema_mirror_default_group_refs": [
                {
                    "source_id": "bundled.local_package.browser",
                    "group_key": "network",
                    "reason": "browser_starter_network",
                },
            ],
            "tool_schema_mirror_default_group_ref_count": 1,
            "tool_schema_mirror_default_schema_reasons": {
                "browser.network.inspect": "browser_starter_network",
            },
            "tool_schema_mirror_default_mirrored": [
                {
                    "node_id": "tools.tool.browser.network.inspect",
                    "name": "browser.network.inspect",
                    "priority": 200,
                    "bootstrap_reason": "browser_starter_network",
                },
            ],
            "tool_schema_mirror_skipped": [
                {
                    "node_id": "tools.tool.browser.form.fill",
                    "name": "browser.form.fill",
                    "reason": "count_limit",
                    "selection": "default",
                    "priority": 900,
                    "bootstrap_reason": "forms_on_demand",
                },
            ],
            "tool_schema_mirror_skipped_by_reason": {"count_limit": 1},
            "browser_investigation_affordance_status": "ok",
            "browser_investigation_route_bias": "runtime_network_visible",
            "browser_investigation_present_paths": [
                "runtime_and_code",
                "network_truth",
                "stateful_interaction",
            ],
            "browser_investigation_missing_paths": [],
            "browser_investigation_schema_names": [
                "browser.runtime.inspect",
                "browser.network.inspect",
                "browser.action.trace",
            ],
            "browser_investigation_runtime_code_schema_names": [
                "browser.runtime.inspect",
            ],
            "browser_investigation_network_schema_names": [
                "browser.network.inspect",
            ],
            "browser_investigation_stateful_schema_names": [
                "browser.action.trace",
            ],
            "work_plan_status": "in_progress",
            "work_plan_phase": "in_progress:Inspect runtime",
            "work_plan_update_reason": "verified_fact",
            "work_plan_phase_changed": False,
            "work_plan_update_count": 3,
            "final_response_requires_evidence_path": True,
            "verified_evidence_path_count": 1,
            "verified_evidence_paths": ["network_truth"],
            "browser_verified_evidence_path_count": 1,
            "browser_verified_evidence_paths": ["network_truth"],
            "unverified_evidence_paths": [],
            "artifact_content_budget": {"status": "ok"},
            "top_rendered_nodes": [{"node_id": "runtime.contract"}],
            "mirrored_node_count": 1,
        },
    )

    assert metadata["prompt_input"] == "interactive"
    assert metadata["context_render_snapshot_id"] == "ctxsnap_1"
    assert metadata["rendered_prompt_estimated_tokens"] == 10
    assert metadata["direct_transcript_estimated_tokens"] == 2
    assert metadata["mirrored_tool_schema_estimated_tokens"] == 3
    assert metadata["artifact_content_estimated_tokens"] == 4
    assert metadata["estimated_provider_prompt_tokens"] == 19
    assert metadata["tool_schema_mirror_budget_status"] == "ok"
    assert metadata["tool_schema_mirror_default_schema_source"] == (
        "source_prompt.default"
    )
    assert metadata["tool_schema_mirror_default_group_ref_count"] == 1
    assert metadata["tool_schema_mirror_default_group_refs"][0]["reason"] == (
        "browser_starter_network"
    )
    assert metadata["tool_schema_mirror_default_schema_reasons"] == {
        "browser.network.inspect": "browser_starter_network",
    }
    assert metadata["tool_schema_mirror_default_mirrored"][0]["name"] == (
        "browser.network.inspect"
    )
    assert metadata["tool_schema_mirror_skipped"] == [
        {
            "node_id": "tools.tool.browser.form.fill",
            "name": "browser.form.fill",
            "reason": "count_limit",
            "selection": "default",
            "priority": 900,
            "bootstrap_reason": "forms_on_demand",
        },
    ]
    assert metadata["tool_schema_mirror_skipped_by_reason"] == {"count_limit": 1}
    assert metadata["browser_investigation_affordance_status"] == "ok"
    assert metadata["browser_investigation_route_bias"] == "runtime_network_visible"
    assert metadata["browser_investigation_present_paths"] == [
        "runtime_and_code",
        "network_truth",
        "stateful_interaction",
    ]
    assert "browser_investigation_missing_paths" not in metadata
    assert metadata["browser_investigation_runtime_code_schema_names"] == [
        "browser.runtime.inspect",
    ]
    assert metadata["browser_investigation_network_schema_names"] == [
        "browser.network.inspect",
    ]
    assert metadata["browser_investigation_stateful_schema_names"] == [
        "browser.action.trace",
    ]
    assert metadata["work_plan_status"] == "in_progress"
    assert metadata["work_plan_phase"] == "in_progress:Inspect runtime"
    assert metadata["work_plan_update_reason"] == "verified_fact"
    assert metadata["work_plan_phase_changed"] is False
    assert metadata["work_plan_update_count"] == 3
    assert metadata["final_response_requires_evidence_path"] is True
    assert metadata["verified_evidence_path_count"] == 1
    assert metadata["verified_evidence_paths"] == ["network_truth"]
    assert metadata["browser_verified_evidence_path_count"] == 1
    assert metadata["browser_verified_evidence_paths"] == ["network_truth"]
    assert "unverified_evidence_paths" not in metadata
    assert metadata["artifact_content_budget"] == {"status": "ok"}
    assert metadata["top_rendered_nodes"] == [{"node_id": "runtime.contract"}]
    assert metadata["mirrored_node_count"] == 1


def test_browser_investigation_affordance_flags_dom_form_only_schema_surface() -> None:
    metadata = browser_investigation_affordance_metadata(
        {
            "tool_schemas": [
                {"name": "browser.navigate"},
                {"name": "browser.form.fill"},
                {"name": "browser.overlay.select"},
                {"name": "browser.action.trace"},
            ],
        },
    )

    assert metadata["browser_investigation_affordance_status"] == "dom_form_only"
    assert metadata["browser_investigation_route_bias"] == "dom_form_click_bias"
    assert metadata["browser_investigation_present_paths"] == [
        "stateful_interaction",
    ]
    assert metadata["browser_investigation_missing_paths"] == [
        "runtime_and_code",
        "network_truth",
    ]
    assert metadata["browser_investigation_runtime_code_schema_names"] == []
    assert metadata["browser_investigation_network_schema_names"] == []
    assert metadata["browser_investigation_stateful_schema_names"] == [
        "browser.form.fill",
        "browser.overlay.select",
        "browser.action.trace",
    ]


def test_browser_investigation_affordance_accepts_runtime_network_schema_surface() -> None:
    metadata = browser_investigation_affordance_metadata(
        {
            "tool_schemas": [
                {"name": "browser.navigate"},
                {"name": "browser.observe"},
                {"name": "browser.runtime.inspect"},
                {"name": "browser.script.find_request"},
                {"name": "browser.network.inspect"},
                {"name": "browser.network.replay_request"},
                {"name": "browser.action.trace"},
            ],
        },
    )

    assert metadata["browser_investigation_affordance_status"] == "ok"
    assert metadata["browser_investigation_route_bias"] == "runtime_network_visible"
    assert metadata["browser_investigation_present_paths"] == [
        "runtime_and_code",
        "network_truth",
        "stateful_interaction",
    ]
    assert metadata["browser_investigation_missing_paths"] == []


def _prompt(
    *,
    messages: tuple[LlmMessage, ...] | None = None,
    tool_schemas: tuple[ToolSchema, ...] = (),
    surface_policy: RunSurfacePolicy | None = None,
    llm_capabilities: tuple[LlmCapability, ...] = (),
    llm_api_family: str | None = None,
    runtime_llm_defaults: dict[str, object] | None = None,
    llm_defaults: dict[str, object] | None = None,
    llm_policy: dict[str, object] | None = None,
) -> RunPromptInput:
    return RunPromptInput(
        llm_id="llm.test",
        session_key="session:test",
        active_session_id="session-instance-1",
        messages=messages
        or (
            LlmMessage(
                role=LlmMessageRole.USER,
                content="hello",
                metadata={
                    "session_item_id": "item-1",
                    "session_id": "session-instance-1",
                    "sequence_no": 1,
                },
            ),
        ),
        mode=PromptMode.NORMAL_TURN,
        llm_capabilities=llm_capabilities,
        llm_api_family=llm_api_family,
        runtime_llm_defaults=dict(runtime_llm_defaults or {}),
        llm_defaults=dict(llm_defaults or {}),
        llm_policy=dict(llm_policy or {}),
        tool_schemas=tool_schemas,
        surface_policy=surface_policy or RunSurfacePolicy(),
    )


def _resolved_tool(tool_id: str, *, schema_name: str) -> ResolvedTool:
    return ResolvedTool(
        tool=Tool(
            id=tool_id,
            name=schema_name,
            description=f"{schema_name} description.",
        ),
        schema=ToolSchema(name=schema_name, description=f"{schema_name} description."),
        target=ToolExecutionTarget(),
    )
