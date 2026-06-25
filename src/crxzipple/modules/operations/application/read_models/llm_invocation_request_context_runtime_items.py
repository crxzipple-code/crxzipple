from __future__ import annotations

from datetime import datetime, timezone

from crxzipple.modules.llm.domain import LlmInvocation
from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_detail_replay import (
    draft_input_sequence_label,
    replay_input_item_count_label,
    replay_input_item_kinds_label,
    replay_input_item_sources_label,
    replay_protocol_items_label,
    request_render_snapshot_label,
    tool_result_excerpt_count_label,
    tool_result_excerpt_sample_label,
    tool_result_omitted_label,
    tool_result_refs_label,
    tool_result_stat_label,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_facts import (
    metadata_int_label,
    metadata_text_label,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_labels import (
    stream_status_label,
    tool_protocol_issue_count,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
)


def runtime_request_context_items(
    invocation: LlmInvocation,
    *,
    events: tuple[OperationsObservedEvent, ...],
    streaming_ids: set[str],
) -> tuple[OperationsKeyValueItemModel, ...]:
    return (
        OperationsKeyValueItemModel(
            "Streaming",
            stream_status_label(
                invocation,
                events=events,
                now=datetime.now(timezone.utc),
            )
            if invocation.id in streaming_ids
            else "No",
        ),
        OperationsKeyValueItemModel("Messages", str(len(invocation.messages))),
        OperationsKeyValueItemModel("Tool Schemas", str(len(invocation.tool_schemas))),
        OperationsKeyValueItemModel(
            "Provider Wire Tokens",
            metadata_int_label(invocation, "estimated_provider_input_tokens"),
        ),
        OperationsKeyValueItemModel(
            "Draft Input Items",
            metadata_int_label(invocation, "draft_input_session_item_count"),
        ),
        OperationsKeyValueItemModel(
            "Draft Input Tokens",
            metadata_int_label(invocation, "draft_input_estimated_tokens"),
        ),
        OperationsKeyValueItemModel(
            "Tool Protocol Calls",
            str(tool_protocol_issue_count(invocation)),
        ),
    )


def replay_request_context_items(
    invocation: LlmInvocation,
) -> tuple[OperationsKeyValueItemModel, ...]:
    return (
        OperationsKeyValueItemModel(
            "Replay Input Items",
            replay_input_item_count_label(invocation),
        ),
        OperationsKeyValueItemModel(
            "Replay Input Mode",
            metadata_text_label(invocation, "input_mode"),
        ),
        OperationsKeyValueItemModel(
            "Replay Input Kinds",
            replay_input_item_kinds_label(invocation),
        ),
        OperationsKeyValueItemModel(
            "Replay Input Sources",
            replay_input_item_sources_label(invocation),
        ),
        OperationsKeyValueItemModel(
            "Replay Protocol Items",
            replay_protocol_items_label(invocation),
        ),
    )


def tool_result_request_context_items(
    invocation: LlmInvocation,
) -> tuple[OperationsKeyValueItemModel, ...]:
    return (
        OperationsKeyValueItemModel(
            "Tool Result Items",
            tool_result_stat_label(invocation, "tool_result_item_count"),
        ),
        OperationsKeyValueItemModel(
            "Tool Result Excerpts",
            tool_result_excerpt_count_label(invocation),
        ),
        OperationsKeyValueItemModel(
            "Tool Result Excerpt Sample",
            tool_result_excerpt_sample_label(invocation),
        ),
        OperationsKeyValueItemModel(
            "Tool Result Compacted",
            tool_result_stat_label(invocation, "compacted_result_count"),
        ),
        OperationsKeyValueItemModel(
            "Tool Result Omitted",
            tool_result_omitted_label(invocation),
        ),
        OperationsKeyValueItemModel(
            "Tool Result Refs",
            tool_result_refs_label(invocation),
        ),
    )


def artifact_request_context_items(
    invocation: LlmInvocation,
) -> tuple[OperationsKeyValueItemModel, ...]:
    return (
        OperationsKeyValueItemModel(
            "Artifact Tokens",
            metadata_int_label(invocation, "artifact_content_estimated_tokens"),
        ),
        OperationsKeyValueItemModel(
            "Artifact Blocks",
            metadata_int_label(invocation, "artifact_content_block_count"),
        ),
        OperationsKeyValueItemModel(
            "Artifact Omitted",
            metadata_int_label(invocation, "artifact_content_omitted_count"),
        ),
        OperationsKeyValueItemModel(
            "Draft Sequence Range",
            draft_input_sequence_label(invocation),
        ),
        OperationsKeyValueItemModel(
            "Request Render Snapshot",
            request_render_snapshot_label(invocation),
        ),
        OperationsKeyValueItemModel(
            "Response Format",
            "Configured" if invocation.response_format else "-",
        ),
        OperationsKeyValueItemModel(
            "Provider Request ID",
            invocation.provider_request_id or "-",
        ),
    )
