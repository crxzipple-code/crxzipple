from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmContinuationReason,
    LlmContinuationSignal,
    LlmInputItem,
    LlmInputItemKind,
    LlmInvocation,
    LlmInvocationStatus,
    LlmMessage,
    LlmMessagePhase,
    LlmMessageRole,
    LlmProfile,
    LlmProviderKind,
    LlmResponseEvent,
    LlmResponseEventType,
    LlmResponseItem,
    LlmResponseItemKind,
    LlmResult,
    ToolCallIntent,
)
from crxzipple.modules.operations.application.observation import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.llm import (
    LlmOperationsReadModelProvider,
)


def test_llm_operations_page_exposes_runtime_transcript_budget_metadata() -> None:
    profile = LlmProfile(
        id="openai.gpt-budget",
        provider=LlmProviderKind.OPENAI,
        api_family=LlmApiFamily.OPENAI_RESPONSES,
        model_name="gpt-5",
        context_window_tokens=2_000,
        credential_binding_id="openai-api-key",
    )
    invocation = LlmInvocation(
        id="llm-invocation-budget",
        llm_id=profile.id,
        messages=(
            LlmMessage(
                role=LlmMessageRole.USER,
                content="continue",
            ),
        ),
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={"role": "user", "content": "continue"},
                source="session_item",
            ),
            LlmInputItem(
                kind=LlmInputItemKind.REASONING,
                payload={"summary": "Need inspect page state."},
                source="session_item",
            ),
            LlmInputItem(
                kind=LlmInputItemKind.FUNCTION_CALL,
                payload={"call_id": "call-weather-1", "name": "weather.lookup"},
                source="session_item",
            ),
            LlmInputItem(
                kind=LlmInputItemKind.FUNCTION_CALL_OUTPUT,
                payload={
                    "call_id": "call-weather-1",
                    "output": [
                        {
                            "type": "text",
                            "text": "tool_result:\nstdout_excerpt: KMG SHA available",
                        },
                    ],
                },
                source="session_item",
            ),
        ),
            request_metadata={
                "request_render_snapshot_id": "ctxsnap-budget",
                "request_render_snapshot_kind": "request_render",
            "request_render_snapshot": {
                "snapshot_id": "ctxsnap-budget",
                "tree_schema_version": "2026-06-11.context_tree.v2",
                "included_node_ids": ["runtime.contract", "tools.available"],
                "diagnostics": {
                    "request_render_timings": {
                        "ensure_workspace_ms": 1.0,
                        "record_context_snapshot_ms": 2.0,
                    },
                },
                "raw_tree_body": "full tree body must stay out of summary",
            },
            "request_context_source": "context_slice",
            "context_slice_id": "ctxslice-budget",
            "context_slice_item_count": 3,
            "context_slice_included_node_count": 2,
            "context_slice_omitted_node_count": 4,
            "context_slice_active_tool_count": 1,
            "context_slice_projected_input_item_count": 3,
            "context_slice_archived_ref_count": 1,
            "context_slice_redacted_ref_count": 0,
            "context_slice_unresolved_ref_count": 1,
            "context_slice_loss": {
                "omitted_node_count": 4,
                "unresolved_ref_count": 1,
            },
            "visible_input_summary": {
                "input_item_ref_count": 3,
                "tool_schema_count": 1,
            },
            "estimated_provider_input_tokens": 1_800,
            "draft_input_session_item_count": 3,
            "draft_input_estimated_tokens": 120,
            "artifact_content_estimated_tokens": 40,
            "artifact_content_block_count": 2,
            "artifact_content_omitted_count": 1,
            "input_mode": "runtime_transcript",
            "tool_surface": {
                "id": "tool_surface:ctxsnap-budget",
                "functions": [{"name": "browser.snapshot"}],
                "mirrored_schema_names": ["browser.snapshot"],
            },
            "draft_input_sequence_range": {
                "sessions": [
                    {
                        "session_id": "session-budget",
                        "from_sequence_no": 5,
                        "to_sequence_no": 9,
                        "item_count": 3,
                    },
                ],
            },
            "draft_input_budget_summary": {
                "tool_result_stats": {
                    "tool_result_item_count": 2,
                    "compacted_result_count": 1,
                    "omitted_count": 3,
                    "omitted_chars": 1024,
                    "artifact_ref_count": 1,
                    "read_handle_count": 2,
                },
            },
            "llm_request_policy": {
                "resolution_trace": [
                    {
                        "field": "provider_options.max_output_tokens",
                        "source": "settings.llm_request_defaults",
                        "status": "applied",
                        "value": 800,
                    },
                    {
                        "field": "reasoning_config.summary",
                        "source": "agent_profile.llm_policy",
                        "status": "downgraded",
                        "value": "auto",
                        "reason": "llm_capability_not_supported",
                    },
                ],
            },
        },
        status=LlmInvocationStatus.SUCCEEDED,
        result=LlmResult(
            text="我先检查页面状态。",
            tool_calls=(
                ToolCallIntent(
                    id="call-browser",
                    name="browser.snapshot",
                    arguments={},
                ),
            ),
            finish_reason="tool_calls",
            metadata={
                "provider_continuation_fallback": True,
                "provider_continuation_fallback_reason": (
                    "websocket_continuation_failed_before_output"
                ),
            },
        ),
        response_items=(
            LlmResponseItem(
                id="item-response-message",
                invocation_id="llm-invocation-budget",
                sequence_no=1,
                kind=LlmResponseItemKind.ASSISTANT_MESSAGE,
                role=LlmMessageRole.ASSISTANT,
                phase=LlmMessagePhase.COMMENTARY,
                content_payload={"text": "我先检查页面状态。"},
                provider_payload={"type": "message"},
                provider_item_type="message",
                provider_replay_candidate=True,
                user_timeline_candidate=True,
            ),
            LlmResponseItem(
                id="item-response-tool",
                invocation_id="llm-invocation-budget",
                sequence_no=2,
                kind=LlmResponseItemKind.TOOL_CALL,
                role=LlmMessageRole.ASSISTANT,
                content_payload={"tool_name": "browser.snapshot"},
                provider_payload={"type": "function_call"},
                provider_item_type="function_call",
                call_id="call-browser",
                tool_name="browser.snapshot",
                provider_replay_candidate=True,
                user_timeline_candidate=False,
            ),
        ),
        continuation=LlmContinuationSignal(
            end_turn=False,
            needs_follow_up=True,
            reason=LlmContinuationReason.TOOL_CALL,
            provider_payload={"status": "requires_action"},
        ),
        provider_request_payload_preview={
            "transport": "http",
            "renderer_id": "openai_codex_responses",
            "render_strategy": "provider_native_delta",
            "render_report": {
                "renderer_id": "openai_codex_responses",
                "transport": "http",
                "render_strategy": "provider_native_delta",
                "loss_report": {},
                "input_item_mapping": [
                    {
                        "provider_payload_index": 0,
                        "input_item_index": 0,
                        "input_item_kind": "message",
                        "input_item_source": "session_item",
                        "session_item_id": "session-item-user",
                        "trace_status": "runtime_input_item",
                    },
                ],
                "input_item_mapping_coverage": {
                    "provider_input_item_count": 1,
                    "canonical_input_item_count": 1,
                    "traced_input_item_count": 1,
                    "untraced_input_item_count": 0,
                    "provider_generated_or_unattributed": [],
                },
                "tool_protocol": {
                    "schema_version": "2026-06-19.runtime_input_filter.v1",
                    "replay_has_protocol_breaks": False,
                    "source_had_protocol_breaks": False,
                    "replay_orphan_tool_output_count": 0,
                    "replay_missing_tool_output_count": 0,
                    "replay_duplicate_tool_call_id_count": 0,
                    "replay_duplicate_tool_output_id_count": 0,
                    "dropped_orphan_tool_output_count": 0,
                    "dropped_missing_tool_output_count": 1,
                    "dropped_duplicate_tool_call_id_count": 0,
                    "dropped_duplicate_tool_output_id_count": 0,
                },
            },
            "has_previous_response_id": True,
            "previous_response_id": "resp_previous",
            "input_delta_mode": True,
            "input_baseline_count": 3,
            "input_delta_count": 1,
            "input_item_types": ["function_call_output"],
            "tool_count": 3,
            "option_summary": {
                "parallel_tool_calls": True,
                "prompt_cache_key": "crxzipple:assistant:session:budget",
                "service_tier": "priority",
                "text": {"verbosity": "low"},
            },
        },
    )
    response_events = (
        LlmResponseEvent(
            id="event-response-item-started",
            invocation_id=invocation.id,
            sequence_no=1,
            type=LlmResponseEventType.ITEM_STARTED,
            item_id="item-response-tool",
            delta_payload={"provider_event_type": "response.output_item.added"},
            provider_payload={"type": "response.output_item.added"},
        ),
        LlmResponseEvent(
            id="event-response-tool-delta",
            invocation_id=invocation.id,
            sequence_no=2,
            type=LlmResponseEventType.TOOL_ARGUMENT_DELTA,
            item_id="item-response-tool",
            delta_payload={"delta": "{}"},
            provider_payload={"type": "response.function_call_arguments.delta"},
        ),
    )
    provider = LlmOperationsReadModelProvider(
        llm_service=_FakeLlmQueryService(profile, invocation, response_events),
        run_query=_FakeRunQuery(invocation.id),
        operations_observation=_FakeOperationsObservation(
            OperationsObservedEvent(
                id="observed-prepared",
                cursor="1",
                topic="events.named.llm.invocation_provider_request_prepared",
                event_name="llm.invocation_provider_request_prepared",
                module="llm",
                owner="llm",
                kind="fact",
                level="info",
                status="prepared",
                entity_id=invocation.id,
                run_id="run-1",
                trace_id="trace-1",
                source_event_name="llm.invocation_provider_request_prepared",
                occurred_at=datetime.now(timezone.utc),
                payload={
                    "invocation_id": invocation.id,
                    "transport": "websocket",
                    "has_previous_response_id": True,
                    "previous_response_id": "resp_previous",
                    "input_delta_mode": True,
                    "input_delta_count": 1,
                    "input_baseline_count": 3,
                    "provider_request_payload_preview": {
                        "transport": "websocket",
                        "message_type": "response.create",
                    },
                },
            ),
            OperationsObservedEvent(
                id="observed-warmup",
                cursor="2",
                topic="events.named.llm.profile_warmup_succeeded",
                event_name="llm.profile_warmup_succeeded",
                module="llm",
                owner="llm",
                kind="fact",
                level="info",
                status="warmed",
                entity_id=profile.id,
                run_id=None,
                trace_id=None,
                source_event_name="llm.profile_warmup_succeeded",
                occurred_at=datetime.now(timezone.utc),
                payload={
                    "llm_id": profile.id,
                    "provider": "openai",
                    "api_family": "openai_responses",
                    "status": "warmed",
                    "transport": "websocket",
                    "endpoint": "wss://example.test/backend-api/codex/responses",
                    "reused_connection": False,
                },
            ),
        ),
    )

    page = provider.page()

    row = page.recent_invocations.rows[0].cells
    assert row["provider_input_tokens"] == "1800"
    assert row["draft_input_items"] == "3"
    assert row["draft_input_tokens"] == "120"
    assert row["tool_protocol"] == "1"
    assert row["response_text"] == "9 chars"
    assert row["tool_calls"] == "1"
    assert row["response_items"] == "2"
    assert row["continuation"] == "tool_call"
    assert row["end_turn"] == "No"
    assert row["progress"] == "1"

    detail = page.invocation_details[0]
    summary = {item.label: item.value for item in detail.summary}
    assert summary["Response Text"] == "9 chars"
    assert summary["Tool Calls"] == "1"
    assert summary["Response Items"] == "2"
    assert summary["Response Events"] == "2"
    assert summary["Continuation"] == "tool_call"
    assert summary["End Turn"] == "No"
    assert summary["Assistant Progress Items"] == "1"
    assert summary["Assistant Progress IDs"] == "item-progress"
    request_context = {item.label: item.value for item in detail.request_context}
    assert request_context["Provider Wire Tokens"] == "1800"
    assert request_context["Draft Input Items"] == "3"
    assert request_context["Draft Input Tokens"] == "120"
    assert request_context["Tool Protocol Calls"] == "1"
    assert request_context["Replay Input Items"] == "4"
    assert request_context["Replay Input Mode"] == "runtime_transcript"
    assert request_context["Replay Input Kinds"] == (
        "message, reasoning, function_call, function_call_output"
    )
    assert request_context["Replay Input Sources"] == "session_item"
    assert request_context["Replay Protocol Items"] == (
        "reasoning=1; calls=1; outputs=1; provider_external=0"
    )
    assert request_context["Tool Result Items"] == "2"
    assert request_context["Tool Result Excerpts"] == "1"
    assert request_context["Tool Result Excerpt Sample"] == (
        "tool_result: stdout_excerpt: KMG SHA available"
    )
    assert request_context["Tool Result Compacted"] == "1"
    assert request_context["Tool Result Omitted"] == "count=3; chars=1024"
    assert request_context["Tool Result Refs"] == "artifact_refs=1; read_handles=2"
    assert request_context["Artifact Tokens"] == "40"
    assert request_context["Artifact Blocks"] == "2"
    assert request_context["Artifact Omitted"] == "1"
    assert request_context["Draft Sequence Range"] == "session-budget:5-9 (3)"
    assert request_context["Request Render Snapshot"] == "ctxsnap-budget"
    assert request_context["Provider Continuation"] == (
        "previous_response_id=resp_previous"
    )
    assert request_context["Provider Transport"] == "http"
    assert request_context["Provider Renderer"] == "openai_codex_responses"
    assert request_context["Provider Render Strategy"] == "provider_native_delta"
    assert request_context["Provider Render Report"] == (
        "renderer=openai_codex_responses; transport=http; "
        "strategy=provider_native_delta; loss=none"
    )
    assert request_context["Provider Input Delta"] == "mode=true; delta=1; baseline=3"
    assert request_context["Provider Continuation Fallback"] == (
        "websocket_continuation_failed_before_output"
    )
    assert request_context["Provider Input Items"] == "function_call_output"
    assert request_context["Provider Tool Count"] == "3"
    assert request_context["Provider Options"] == (
        "parallel_tool_calls, prompt_cache_key, service_tier, text"
    )
    assert detail.provider_render_report == {
        "renderer_id": "openai_codex_responses",
        "transport": "http",
        "render_strategy": "provider_native_delta",
        "loss_report": {},
        "input_item_mapping": [
            {
                "provider_payload_index": 0,
                "input_item_index": 0,
                "input_item_kind": "message",
                "input_item_source": "session_item",
                "session_item_id": "session-item-user",
                "trace_status": "runtime_input_item",
            },
        ],
        "input_item_mapping_coverage": {
            "provider_input_item_count": 1,
            "canonical_input_item_count": 1,
            "traced_input_item_count": 1,
            "untraced_input_item_count": 0,
            "provider_generated_or_unattributed": [],
        },
        "tool_protocol": {
            "schema_version": "2026-06-19.runtime_input_filter.v1",
            "replay_has_protocol_breaks": False,
            "source_had_protocol_breaks": False,
            "replay_orphan_tool_output_count": 0,
            "replay_missing_tool_output_count": 0,
            "replay_duplicate_tool_call_id_count": 0,
            "replay_duplicate_tool_output_id_count": 0,
            "dropped_orphan_tool_output_count": 0,
            "dropped_missing_tool_output_count": 1,
            "dropped_duplicate_tool_call_id_count": 0,
            "dropped_duplicate_tool_output_id_count": 0,
        },
    }
    assert detail.provider_wire_preview["renderer_id"] == "openai_codex_responses"
    assert detail.provider_wire_preview["transport"] == "http"
    assert "render_report" not in detail.provider_wire_preview
    assert detail.provider_context_mapping.title == "Provider Context Mapping"
    assert detail.provider_context_mapping.rows[0].cells["source"] == "session_item"
    assert "slice_item" not in detail.provider_context_mapping.rows[0].cells
    assert detail.provider_context_mapping.rows[0].cells["session_item"] == (
        "session-item-user"
    )
    assert detail.provider_context_mapping.rows[0].cells["input_kind"] == "message"
    assert detail.provider_context_mapping.rows[0].cells["trace_status"] == (
        "runtime_input_item"
    )
    assert detail.runtime_request_summary["request_render_snapshot_id"] == (
        "ctxsnap-budget"
    )
    assert "context_snapshot_id" not in detail.runtime_request_summary
    assert detail.runtime_request_summary["request_render_snapshot_id"] == (
        "ctxsnap-budget"
    )
    assert detail.runtime_request_summary["request_render_snapshot_kind"] == (
        "request_render"
    )
    assert detail.runtime_request_summary["request_context_source"] == "context_slice"
    assert detail.runtime_request_summary["context_slice_id"] == "ctxslice-budget"
    assert detail.runtime_request_summary["context_slice_item_count"] == 3
    assert detail.runtime_request_summary["context_slice_included_node_count"] == 2
    assert detail.runtime_request_summary["context_slice_omitted_node_count"] == 4
    assert detail.runtime_request_summary["context_slice_active_tool_count"] == 1
    assert detail.runtime_request_summary["context_slice_projected_input_item_count"] == 3
    assert detail.runtime_request_summary["context_slice_unresolved_ref_count"] == 1
    assert detail.runtime_request_summary["context_slice_loss"] == {
        "omitted_node_count": 4,
        "unresolved_ref_count": 1,
    }
    assert detail.runtime_request_summary["input_mode"] == "runtime_transcript"
    assert detail.runtime_request_summary["visible_input_summary"] == {
        "input_item_ref_count": 3,
        "tool_schema_count": 1,
    }
    assert detail.runtime_request_summary["request_render_timings"] == {
        "ensure_workspace_ms": 1.0,
        "record_context_snapshot_ms": 2.0,
    }
    assert "llm_request_slice_id" not in detail.runtime_request_summary
    assert detail.runtime_request_summary["request_render_snapshot"]["snapshot_id"] == (
        "ctxsnap-budget"
    )
    assert "raw_tree_body" not in detail.runtime_request_summary["request_render_snapshot"]
    assert detail.runtime_request_summary["tool_surface"] == {
        "id": "tool_surface:ctxsnap-budget",
        "function_count": 1,
        "mirrored_schema_count": 1,
    }
    assert detail.runtime_request_summary["provider_input_item_mapping_coverage"] == {
        "provider_input_item_count": 1,
        "canonical_input_item_count": 1,
        "traced_input_item_count": 1,
        "untraced_input_item_count": 0,
        "provider_generated_or_unattributed": [],
    }
    assert "context_slice_summary" not in detail.runtime_request_summary
    assert "context_slice" not in detail.runtime_request_summary
    runtime_observations = {item.label: item.value for item in detail.runtime_observations.items}
    assert detail.runtime_observations.title == "Runtime Observations"
    assert runtime_observations["Runtime observations"] == "1"
    assert runtime_observations["Tool protocol replay"] == "clean"
    assert runtime_observations["Tool protocol source"] == "clean"
    assert runtime_observations["Tool protocol filtered"] == (
        "filtered=1; orphan=0; missing=1; dup_call=0; dup_output=0"
    )
    assert runtime_observations["Response event window"] == "1d"
    assert runtime_observations["Response event detail limit"] == "100"
    assert runtime_observations["Response event durable fact"] == "completed_response_items"
    assert runtime_observations["Response event overflow action"] == (
        "prefer_response_items_and_request_preview"
    )
    access_row = page.provider_access_health.rows[0].cells
    assert access_row["profile"] == profile.id
    assert access_row["warmup"] == "Warmed (websocket)"
    assert access_row["next_action"] == "Open Access"
    blocked_row = page.provider_auth_blocked.rows[0].cells
    assert blocked_row["profile"] == profile.id
    assert blocked_row["warmup"] == "Warmed (websocket)"
    assert detail.policy_trace.total == 2
    assert detail.policy_trace.rows[0].cells["source"] == (
        "settings.llm_request_defaults"
    )
    assert detail.policy_trace.rows[1].tone == "warning"
    assert detail.policy_trace.rows[1].cells["reason"] == (
        "llm_capability_not_supported"
    )
    assert detail.response_items.total == 2
    assert detail.response_items.rows[1].cells["tool"] == "browser.snapshot"
    assert detail.response_items.rows[1].cells["provider_payload"] == (
        '{"type": "function_call"}'
    )
    assert detail.response_runtime_mapping.total == 2
    mapping_row = detail.response_runtime_mapping.rows[1].cells
    assert mapping_row["provider_type"] == "function_call"
    assert mapping_row["response_item"] == "item-response-tool"
    assert mapping_row["runtime_semantic"] == "runtime.assistant_tool_call"
    assert mapping_row["tool"] == "browser.snapshot"
    assert detail.response_events.total == 2
    assert detail.response_events.rows[1].cells["provider_event"] == (
        "response.function_call_arguments.delta"
    )
    lifecycle_by_event = {
        row.cells["event"]: row.cells
        for row in page.llm_lifecycle_events.rows
    }
    lifecycle_row = lifecycle_by_event["llm.invocation_provider_request_prepared"]
    assert lifecycle_row["transport"] == "websocket"
    assert lifecycle_row["continuation"] == "previous_response_id=resp_previous"
    assert lifecycle_row["input_delta"] == "mode=true; delta=1; baseline=3"
    assert lifecycle_by_event["llm.profile_warmup_succeeded"]["entity"] == profile.id
    assert lifecycle_by_event["llm.profile_warmup_succeeded"]["transport"] == "websocket"
    assert lifecycle_by_event["llm.profile_warmup_succeeded"]["details"]

    assert page.context_pressure.total == 1
    pressure = {segment.id: segment.value for segment in page.context_pressure.segments}
    assert pressure["high"] == 1


class _FakeLlmQueryService:
    def __init__(
        self,
        profile: LlmProfile,
        invocation: LlmInvocation,
        response_events: tuple[LlmResponseEvent, ...] = (),
    ) -> None:
        self._profile = profile
        self._invocation = invocation
        self._response_events = response_events

    def list_profiles(self) -> list[LlmProfile]:
        return [self._profile]

    def list_invocations(
        self,
        *,
        llm_id: str | None = None,
        limit: int = 50,
    ) -> list[LlmInvocation]:
        if llm_id is not None and llm_id != self._profile.id:
            return []
        return [self._invocation][:limit]

    def list_response_events(
        self,
        invocation_id: str,
        *,
        limit: int | None = None,
        after_sequence: int | None = None,
    ) -> list[LlmResponseEvent]:
        if invocation_id != self._invocation.id:
            return []
        events = list(self._response_events)
        if after_sequence is not None:
            events = [event for event in events if event.sequence_no > after_sequence]
        if limit is not None:
            events = events[:limit]
        return events

    def response_event_retention_policy(self) -> dict[str, object]:
        return {
            "full_event_window_seconds": 86_400,
            "detail_event_limit": 100,
            "durable_fact": "completed_response_items",
            "overflow_action": "prefer_response_items_and_request_preview",
        }


class _FakeRunQuery:
    def __init__(self, invocation_id: str) -> None:
        self._invocation_id = invocation_id

    def find_execution_step_items_by_owner(self, owner):  # noqa: ANN001, ANN201
        if owner.owner_id != self._invocation_id:
            return []
        return [
            SimpleNamespace(
                id="item-llm",
                step_id="step-llm",
                chain_id="chain-1",
                turn_id="run-1",
                status=SimpleNamespace(value="completed"),
                updated_at=None,
                summary_payload={
                    "assistant_progress_item_ids": ["item-progress"],
                    "assistant_progress_text": "我先检查页面状态。",
                    "tool_call_names": ["browser.snapshot"],
                },
            ),
        ]

    def get_execution_step(self, step_id: str):  # noqa: ANN201
        return SimpleNamespace(
            id=step_id,
            kind=SimpleNamespace(value="llm"),
            status=SimpleNamespace(value="completed"),
        )

    def get_run(self, run_id: str):  # noqa: ANN201
        return SimpleNamespace(
            id=run_id,
            metadata={
                "trace_id": "trace-1",
                "session_key": "agent:assistant:main",
            },
        )


class _FakeOperationsObservation:
    def __init__(self, *events: OperationsObservedEvent) -> None:
        self._events = events

    def get_module_observation(self, module_name: str):  # noqa: ANN201
        if module_name != "llm":
            return None
        return SimpleNamespace(recent_events=self._events)
