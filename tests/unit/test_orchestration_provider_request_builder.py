from __future__ import annotations

from crxzipple.app.integration.context_workspace_orchestration.snapshot_metadata import (
    browser_investigation_affordance_metadata,
)
from crxzipple.modules.llm.domain import LlmMessage, LlmMessageRole, ToolSchema
from crxzipple.modules.orchestration.application.ports import (
    ContextRenderSnapshotRecord,
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
                metadata={"session_message_id": "message-1", "sequence_no": 1},
            ),
        ),
        mode=PromptMode.NORMAL_TURN,
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
