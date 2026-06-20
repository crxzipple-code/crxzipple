from __future__ import annotations

from crxzipple.modules.llm.application.adapters import LlmAdapterRequest
from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmInputItem,
    LlmInputItemKind,
    LlmMessage,
    LlmMessageRole,
    LlmModelFamily,
    LlmProfile,
    LlmProviderKind,
    ToolSchema,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_responses_renderer import (
    OpenAIResponsesRenderer,
)
from crxzipple.modules.orchestration.application.ports import (
    RequestRenderSnapshotRecord,
)
from crxzipple.modules.orchestration.application.runtime_llm_request_draft import RuntimeLlmRequestDraft
from crxzipple.modules.llm.application.runtime_request_factory import (
    RuntimeLlmRequestBuilder,
)
from crxzipple.modules.orchestration.application.runtime_request_mode import RuntimeRequestMode
from crxzipple.modules.orchestration.application.runtime_request_report import RunSurfacePolicy
from crxzipple.modules.orchestration.application.tool_resolver import (
    ResolvedTool,
    ResolvedToolSet,
)
from crxzipple.modules.tool.domain import Tool, ToolExecutionTarget


def test_request_render_snapshot_refs_do_not_become_provider_debug_body() -> None:
    tree_body_marker = "<context_tree>full tree body must not enter provider</context_tree>"
    snapshot = RequestRenderSnapshotRecord(
        snapshot_id="ctxsnap-boundary",
        included_node_ids=("runtime.contract",),
        included_refs=(
            {
                "node_id": "runtime.contract",
                "kind": "runtime",
                "title": "Runtime Contract",
            },
        ),
        metadata={
            "tree_schema_version": "2026-06-11.context_tree.v2",
            "request_render_snapshot_included_node_count": 1,
        },
        tool_schemas=(ToolSchema(name="command.exec"),),
        tool_schema_refs=(_tool_schema_ref(ToolSchema(name="command.exec")),),
        projected_input_items=_projected_user_input_items(),
    )
    envelope = RuntimeLlmRequestBuilder().request_envelope(
        draft=_draft(),
        request_render_snapshot=snapshot,
        resolved_tools=ResolvedToolSet(
            tools=(_resolved_tool("tool.command.exec", schema_name="command.exec"),),
        ),
        snapshot_metadata=snapshot.metadata,
    )

    assert envelope.request_render_snapshot.snapshot_id == "ctxsnap-boundary"
    assert envelope.request_render_snapshot.included_refs[0]["node_id"] == "runtime.contract"
    assert tree_body_marker not in str(envelope.messages)
    assert tree_body_marker not in str(envelope.transcript.items)
    assert "debug_body" not in envelope.request_render_snapshot.to_payload()

    preview = OpenAIResponsesRenderer(
        default_base_url="https://api.openai.example/v1",
    ).preview(
        _profile(),
        LlmAdapterRequest(
            invocation_id="inv-context-boundary",
            messages=envelope.messages,
            input_items=envelope.transcript.items,
            tool_schemas=envelope.tool_schemas,
            response_format=envelope.response_format(),
            overrides=envelope.provider_options,
            request_metadata=envelope.request_metadata(),
            resolved_credential="token",
        ),
    )

    assert preview["preview_source"] == "provider_adapter"
    assert preview["request_render_snapshot_id"] == "ctxsnap-boundary"
    assert "request_render_snapshot_included_node_count" not in preview
    assert preview["request_render_snapshot_fingerprint"].startswith("sha256:")
    assert tree_body_marker not in str(preview)
    assert tree_body_marker not in str(preview["payload_preview"])


def test_request_render_snapshot_metadata_does_not_duplicate_formal_refs() -> None:
    snapshot = RequestRenderSnapshotRecord(
        snapshot_id="ctxsnap-boundary",
        included_refs=(
            {
                "owner_module": "session",
                "owner_kind": "session_item",
                "owner_id": "draft-user-item",
            },
        ),
        collapsed_refs=(
            {
                "owner_module": "session",
                "owner_kind": "session_item",
                "owner_id": "item-old-1",
            },
        ),
        protocol_required_refs=(
            {
                "owner_module": "session",
                "owner_kind": "session_item",
                "owner_id": "item-call-1",
                "tool_call_id": "call-1",
            },
        ),
        metadata={
            "snapshot_kind": "request_render",
            "draft_input_session_item_count": 1,
            "protocol_required_ref_count": 1,
            "collapsed_ref_count": 1,
            "draft_input_budget_summary": {
                "source": "session_items",
                "truncated": False,
            },
        },
        projected_input_items=_projected_user_input_items(),
    )

    envelope = RuntimeLlmRequestBuilder().request_envelope(
        draft=_draft(),
        request_render_snapshot=snapshot,
        resolved_tools=ResolvedToolSet(tools=()),
        snapshot_metadata=snapshot.metadata,
    )
    metadata = envelope.request_metadata()

    assert envelope.request_render_snapshot.included_refs == (
        {
            "owner_module": "session",
            "owner_kind": "session_item",
            "owner_id": "draft-user-item",
        },
    )
    assert envelope.request_render_snapshot.protocol_required_refs == (
        {
            "owner_module": "session",
            "owner_kind": "session_item",
            "owner_id": "item-call-1",
            "tool_call_id": "call-1",
        },
    )
    assert metadata["request_render_snapshot"]["included_ref_count"] == 1
    assert metadata["request_render_snapshot"]["protocol_required_ref_count"] == 1
    assert "draft_input_session_item_refs" not in metadata
    assert "protocol_required_refs" not in metadata
    assert "collapsed_refs" not in metadata


def _draft() -> RuntimeLlmRequestDraft:
    return RuntimeLlmRequestDraft(
        llm_id="llm.test",
        session_key="session:test",
        active_session_id="session-instance-1",
        messages=(
            LlmMessage(
                role=LlmMessageRole.SYSTEM,
                content="Runtime contract summary.",
            ),
            LlmMessage(
                role=LlmMessageRole.USER,
                content="hello",
                metadata={"session_item_id": "draft-user-item"},
            ),
        ),
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={"role": "user", "content": "hello"},
                source="session_item",
                metadata={"session_item_id": "draft-user-item"},
            ),
        ),
        mode=RuntimeRequestMode.NORMAL_TURN,
        report=None,
        tool_schemas=(ToolSchema(name="command.exec"),),
        surface_policy=RunSurfacePolicy(),
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


def _tool_schema_ref(schema: ToolSchema) -> dict[str, object]:
    return {
        "name": schema.name,
        "source": "context_slice",
        "schema": schema.to_payload(),
    }


def _projected_user_input_items() -> tuple[dict[str, object], ...]:
    return (
        {
            "kind": "message",
            "source": "context_slice",
            "payload": {"role": "user", "content": "hello"},
            "metadata": {
                "session_item_id": "draft-user-item",
                "node_id": "session.item.user",
            },
        },
    )


def _profile() -> LlmProfile:
    return LlmProfile(
        id="openai-profile",
        provider=LlmProviderKind.OPENAI,
        api_family=LlmApiFamily.OPENAI_RESPONSES,
        model_name="gpt-5",
        model_family=LlmModelFamily.GENERAL,
    )
