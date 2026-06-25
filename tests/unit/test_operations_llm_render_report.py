from __future__ import annotations

from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmInputItem,
    LlmInputItemKind,
    LlmInvocation,
    LlmMessage,
    LlmMessageRole,
    LlmProfile,
    LlmProviderKind,
)
from crxzipple.modules.operations.application.read_models.llm import (
    LlmOperationsReadModelProvider,
)


def test_operations_llm_detail_separates_render_report_from_wire_preview() -> None:
    profile = LlmProfile(
        id="codex-profile",
        provider=LlmProviderKind.OPENAI_CODEX,
        api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
        model_name="gpt-5.5",
    )
    invocation = LlmInvocation(
        id="inv-render-report",
        llm_id=profile.id,
        messages=(LlmMessage(role=LlmMessageRole.USER, content="hello"),),
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={"role": "user", "content": "hello"},
            ),
        ),
        provider_request_payload_preview={
            "preview_source": "provider_adapter",
            "renderer_id": "openai_codex_responses",
            "transport": "websocket",
            "render_strategy": "provider_native_delta",
            "input_delta_mode": True,
            "input_delta_count": 1,
            "input_baseline_count": 3,
            "payload_preview": {
                "type": "response.create",
                "previous_response_id": "resp_previous",
                "input": [{"type": "function_call_output"}],
            },
            "render_report": {
                "renderer_id": "openai_codex_responses",
                "transport": "websocket",
                "render_strategy": "provider_native_delta",
                "loss_report": {},
                "tool_surface": {
                    "provider_visible_tool_count": 1,
                    "provider_visible_tool_names": ("command_exec",),
                    "provider_tool_mapping": [
                        {
                            "provider_name": "command_exec",
                            "runtime_tool_name": "command.exec",
                            "tool_id": "tool.command.exec",
                            "trace_status": "runtime_tool_surface",
                            "source_id": "configured.command",
                            "source": "context_slice",
                            "node_id": "tools.tool.command.exec",
                            "tool_ref_id": "tools.tool.command.exec",
                        },
                    ],
                },
            },
        },
    )
    provider = LlmOperationsReadModelProvider(
        llm_service=_FakeLlmQueryService(profile, invocation),
    )

    detail = provider.page().invocation_details[0]
    request_context = {item.label: item.value for item in detail.request_context}

    assert detail.provider_render_report == {
        "renderer_id": "openai_codex_responses",
        "transport": "websocket",
        "render_strategy": "provider_native_delta",
        "loss_report": {},
        "tool_surface": {
            "provider_visible_tool_count": 1,
            "provider_visible_tool_names": ("command_exec",),
            "provider_tool_mapping": [
                {
                    "provider_name": "command_exec",
                    "runtime_tool_name": "command.exec",
                    "tool_id": "tool.command.exec",
                    "trace_status": "runtime_tool_surface",
                    "source_id": "configured.command",
                    "source": "context_slice",
                    "node_id": "tools.tool.command.exec",
                    "tool_ref_id": "tools.tool.command.exec",
                },
            ],
        },
    }
    assert detail.provider_wire_preview["renderer_id"] == "openai_codex_responses"
    assert detail.provider_wire_preview["transport"] == "websocket"
    assert detail.provider_wire_preview["payload_preview"] == {
        "type": "response.create",
        "previous_response_id": "resp_previous",
        "input": [{"type": "function_call_output"}],
    }
    assert "render_report" not in detail.provider_wire_preview
    assert request_context["Provider Renderer"] == "openai_codex_responses"
    assert request_context["Provider Render Strategy"] == "provider_native_delta"
    assert request_context["Provider Render Report"] == (
        "renderer=openai_codex_responses; transport=websocket; "
        "strategy=provider_native_delta; loss=none"
    )
    assert request_context["Provider Tool Mapping"] == (
        "traced=1; untraced=0; sample=command_exec->tools.tool.command.exec"
    )
    assert request_context["Provider Input Delta"] == "mode=true; delta=1; baseline=3"


class _FakeLlmQueryService:
    def __init__(self, profile: LlmProfile, invocation: LlmInvocation) -> None:
        self._profile = profile
        self._invocation = invocation

    def list_profiles(self) -> list[LlmProfile]:
        return [self._profile]

    def list_invocations(
        self,
        *,
        llm_id: str | None = None,
        run_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[LlmInvocation]:
        if llm_id is not None and llm_id != self._profile.id:
            return []
        if run_id is not None and run_id != self._invocation.run_id:
            return []
        return [self._invocation][offset:][:limit]

    def list_response_events(
        self,
        invocation_id: str,
        *,
        limit: int | None = None,
        after_sequence: int | None = None,
    ) -> list[object]:
        return []

    def response_event_retention_policy(self) -> dict[str, object]:
        return {
            "full_event_window_seconds": 86_400,
            "detail_event_limit": 100,
            "durable_fact": "completed_response_items",
            "overflow_action": "prefer_response_items_and_request_preview",
        }
