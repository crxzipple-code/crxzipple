from __future__ import annotations

from dataclasses import replace

from crxzipple.modules.llm.domain import LlmMessage, LlmMessageRole
from crxzipple.modules.orchestration.application.ports import (
    ContextRenderSnapshotRecord,
)
from crxzipple.modules.orchestration.application.prompt_input import (
    RunPromptInput,
)
from crxzipple.modules.orchestration.application.prompting import (
    ContextRenderReport,
)
from crxzipple.modules.orchestration.application.tool_resolver import ResolvedToolSet
from crxzipple.shared.content_blocks import text_content_block
from crxzipple.shared.context_render_budget import context_render_budget_metadata


class ProviderPromptRequestBuilder:
    """Build provider-facing prompt request pieces from a Context render snapshot.

    Orchestration owns run lifecycle. Context Workspace owns the prompt tree.
    This builder is the narrow translation layer between those facts and the
    provider message/tool-schema shape required by the LLM module.
    """

    def prompt_with_context_snapshot(
        self,
        prompt: RunPromptInput,
        context_render_snapshot: ContextRenderSnapshotRecord | None,
    ) -> RunPromptInput:
        prompt = self._prompt_with_context_render_report(
            prompt,
            context_render_snapshot,
        )
        prompt = self._prompt_with_context_provider_mirror(
            prompt,
            context_render_snapshot,
        )
        prompt = self._prompt_with_context_workspace_body(
            prompt,
            context_render_snapshot,
        )
        return self._prompt_with_context_artifact_mirror(
            prompt,
            context_render_snapshot,
        )

    def resolved_tools_for_prompt(
        self,
        resolved_tools: ResolvedToolSet,
        prompt: RunPromptInput,
        context_render_snapshot: ContextRenderSnapshotRecord | None,
    ) -> ResolvedToolSet:
        if prompt.surface_policy.surface != "interactive":
            return resolved_tools
        if context_render_snapshot is None or context_render_snapshot.tool_schemas is None:
            return ResolvedToolSet(
                tools=(),
                blocked_access=resolved_tools.blocked_access,
            )
        visible_tool_names = {
            schema.name for schema in prompt.tool_schemas if schema.name.strip()
        }
        return ResolvedToolSet(
            tools=tuple(
                item
                for item in resolved_tools.tools
                if item.schema.name in visible_tool_names
                or item.tool.id in visible_tool_names
            ),
            blocked_access=resolved_tools.blocked_access,
        )

    def request_metadata(
        self,
        *,
        prompt: RunPromptInput,
        context_render_snapshot_id: str | None,
        snapshot_metadata: dict[str, object],
    ) -> dict[str, object]:
        return build_llm_request_metadata(
            prompt=prompt,
            context_render_snapshot_id=context_render_snapshot_id,
            snapshot_metadata=snapshot_metadata,
        )

    @staticmethod
    def _prompt_with_context_render_report(
        prompt: RunPromptInput,
        context_render_snapshot: ContextRenderSnapshotRecord | None,
    ) -> RunPromptInput:
        if context_render_snapshot is None or prompt.report is None:
            return prompt
        return replace(
            prompt,
            report=replace(
                prompt.report,
                context_render=ContextRenderReport(
                    snapshot_id=context_render_snapshot.snapshot_id,
                    estimate=(
                        dict(context_render_snapshot.estimate)
                        if isinstance(context_render_snapshot.estimate, dict)
                        else {}
                    ),
                    included_node_ids=tuple(
                        context_render_snapshot.included_node_ids,
                    ),
                    mirrored_node_ids=tuple(
                        context_render_snapshot.mirrored_node_ids,
                    ),
                ),
            ),
        )

    @staticmethod
    def _prompt_with_context_provider_mirror(
        prompt: RunPromptInput,
        context_render_snapshot: ContextRenderSnapshotRecord | None,
    ) -> RunPromptInput:
        if prompt.surface_policy.surface != "interactive":
            return prompt
        if context_render_snapshot is None or context_render_snapshot.tool_schemas is None:
            return replace(prompt, tool_schemas=())
        return replace(
            prompt,
            tool_schemas=context_render_snapshot.tool_schemas,
        )

    @staticmethod
    def _prompt_with_context_workspace_body(
        prompt: RunPromptInput,
        context_render_snapshot: ContextRenderSnapshotRecord | None,
    ) -> RunPromptInput:
        if context_render_snapshot is None:
            return prompt
        prompt_body = (context_render_snapshot.prompt_body or "").strip()
        if not prompt_body:
            return prompt
        context_message = LlmMessage(
            role=LlmMessageRole.SYSTEM,
            content=prompt_body,
            metadata={
                "prompt_block_kind": "context_workspace",
                "context_render_snapshot_id": context_render_snapshot.snapshot_id,
            },
        )
        return replace(
            prompt,
            messages=_insert_after_system_prefix(prompt.messages, context_message),
        )

    @staticmethod
    def _prompt_with_context_artifact_mirror(
        prompt: RunPromptInput,
        context_render_snapshot: ContextRenderSnapshotRecord | None,
    ) -> RunPromptInput:
        if context_render_snapshot is None:
            return prompt
        artifact_blocks = tuple(context_render_snapshot.artifact_content_blocks)
        if not artifact_blocks:
            return prompt
        artifact_message = LlmMessage(
            role=LlmMessageRole.USER,
            content=[
                text_content_block(
                    "Opened context artifact attachments for this turn:",
                ),
                *artifact_blocks,
            ],
            metadata={
                "prompt_block_kind": "context_artifacts",
                "context_render_snapshot_id": context_render_snapshot.snapshot_id,
            },
        )
        return replace(
            prompt,
            messages=prompt.messages + (artifact_message,),
        )


def build_llm_request_metadata(
    *,
    prompt: RunPromptInput,
    context_render_snapshot_id: str | None,
    snapshot_metadata: dict[str, object],
) -> dict[str, object]:
    runtime_contract = snapshot_metadata.get("runtime_contract")
    metadata: dict[str, object] = {
        "prompt_mode": prompt.mode.value,
        "prompt_input": prompt.surface_policy.surface,
        "tree_schema_version": snapshot_metadata.get("tree_schema_version"),
        "context_render_snapshot_id": context_render_snapshot_id,
        "context_history_delivery": snapshot_metadata.get("history_delivery"),
        "mirrored_tool_schema_count": snapshot_metadata.get(
            "mirrored_tool_schema_count",
        ),
        "tool_schema_mirror_skipped_count": snapshot_metadata.get(
            "tool_schema_mirror_skipped_count",
        ),
        "tool_schema_mirror_default_schema_source": snapshot_metadata.get(
            "tool_schema_mirror_default_schema_source",
        ),
        "tool_schema_mirror_available_count": snapshot_metadata.get(
            "tool_schema_mirror_available_count",
        ),
        "tool_schema_mirror_enabled_candidate_count": snapshot_metadata.get(
            "tool_schema_mirror_enabled_candidate_count",
        ),
        "tool_schema_mirror_default_requested_count": snapshot_metadata.get(
            "tool_schema_mirror_default_requested_count",
        ),
        "tool_schema_mirror_default_candidate_count": snapshot_metadata.get(
            "tool_schema_mirror_default_candidate_count",
        ),
        "tool_schema_mirror_default_mirrored_count": snapshot_metadata.get(
            "tool_schema_mirror_default_mirrored_count",
        ),
        "tool_schema_mirror_duplicate_count": snapshot_metadata.get(
            "tool_schema_mirror_duplicate_count",
        ),
        "tool_schema_mirror_groups": snapshot_metadata.get(
            "tool_schema_mirror_groups",
        ),
        "tool_schema_mirror_group_count": snapshot_metadata.get(
            "tool_schema_mirror_group_count",
        ),
        "tool_schema_mirror_visible_group_count": snapshot_metadata.get(
            "tool_schema_mirror_visible_group_count",
        ),
        "tool_schema_mirror_collapsed_group_count": snapshot_metadata.get(
            "tool_schema_mirror_collapsed_group_count",
        ),
        "tool_schema_mirror_default_group_count": snapshot_metadata.get(
            "tool_schema_mirror_default_group_count",
        ),
        "tool_schema_mirror_default_group_refs": snapshot_metadata.get(
            "tool_schema_mirror_default_group_refs",
        ),
        "tool_schema_mirror_default_group_ref_count": snapshot_metadata.get(
            "tool_schema_mirror_default_group_ref_count",
        ),
        "tool_schema_mirror_default_group_matches": snapshot_metadata.get(
            "tool_schema_mirror_default_group_matches",
        ),
        "tool_schema_mirror_default_group_match_count": snapshot_metadata.get(
            "tool_schema_mirror_default_group_match_count",
        ),
        "tool_schema_mirror_default_schema_reasons": snapshot_metadata.get(
            "tool_schema_mirror_default_schema_reasons",
        ),
        "tool_schema_mirror_default_mirrored": snapshot_metadata.get(
            "tool_schema_mirror_default_mirrored",
        ),
        "tool_schema_mirror_skipped": snapshot_metadata.get(
            "tool_schema_mirror_skipped",
        ),
        "tool_schema_mirror_skipped_by_reason": snapshot_metadata.get(
            "tool_schema_mirror_skipped_by_reason",
        ),
        "tool_schema_mirror_max_count": snapshot_metadata.get(
            "tool_schema_mirror_max_count",
        ),
        "tool_schema_mirror_max_estimated_tokens": snapshot_metadata.get(
            "tool_schema_mirror_max_estimated_tokens",
        ),
        "browser_investigation_affordance_status": snapshot_metadata.get(
            "browser_investigation_affordance_status",
        ),
        "browser_investigation_route_bias": snapshot_metadata.get(
            "browser_investigation_route_bias",
        ),
        "browser_investigation_present_paths": snapshot_metadata.get(
            "browser_investigation_present_paths",
        ),
        "browser_investigation_missing_paths": snapshot_metadata.get(
            "browser_investigation_missing_paths",
        ),
        "browser_investigation_schema_names": snapshot_metadata.get(
            "browser_investigation_schema_names",
        ),
        "browser_investigation_runtime_code_schema_names": snapshot_metadata.get(
            "browser_investigation_runtime_code_schema_names",
        ),
        "browser_investigation_network_schema_names": snapshot_metadata.get(
            "browser_investigation_network_schema_names",
        ),
        "browser_investigation_stateful_schema_names": snapshot_metadata.get(
            "browser_investigation_stateful_schema_names",
        ),
        "artifact_content_block_count": snapshot_metadata.get(
            "artifact_content_block_count",
        ),
        "artifact_content_candidate_count": snapshot_metadata.get(
            "artifact_content_candidate_count",
        ),
        "artifact_content_image_count": snapshot_metadata.get(
            "artifact_content_image_count",
        ),
        "artifact_content_file_count": snapshot_metadata.get(
            "artifact_content_file_count",
        ),
        "artifact_content_omitted_count": snapshot_metadata.get(
            "artifact_content_omitted_count",
        ),
        "duplicate_tool_delivery_risk": snapshot_metadata.get(
            "duplicate_tool_delivery_risk",
        ),
        "session_budget_status": snapshot_metadata.get("session_budget_status"),
        "work_plan_status": snapshot_metadata.get("work_plan_status"),
        "work_plan_phase": snapshot_metadata.get("work_plan_phase"),
        "work_plan_update_reason": snapshot_metadata.get("work_plan_update_reason"),
        "work_plan_phase_changed": snapshot_metadata.get("work_plan_phase_changed"),
        "work_plan_update_count": snapshot_metadata.get("work_plan_update_count"),
        "final_response_requires_evidence_path": snapshot_metadata.get(
            "final_response_requires_evidence_path",
        ),
        "verified_evidence_path_count": snapshot_metadata.get(
            "verified_evidence_path_count",
        ),
        "verified_evidence_paths": snapshot_metadata.get("verified_evidence_paths"),
        "browser_verified_evidence_path_count": snapshot_metadata.get(
            "browser_verified_evidence_path_count",
        ),
        "browser_verified_evidence_paths": snapshot_metadata.get(
            "browser_verified_evidence_paths",
        ),
        "unverified_evidence_paths": snapshot_metadata.get(
            "unverified_evidence_paths",
        ),
        "mirrored_node_count": snapshot_metadata.get("mirrored_node_count"),
    }
    metadata.update(context_render_budget_metadata(snapshot_metadata))
    transcript_refs = _direct_transcript_message_refs(prompt.messages)
    tool_protocol_refs = _direct_tool_protocol_refs(prompt.messages)
    current_inbound_ref = _current_inbound_ref(
        transcript_refs,
        snapshot_metadata=snapshot_metadata,
    )
    if transcript_refs:
        metadata["direct_transcript_message_refs"] = transcript_refs
        metadata["direct_transcript_sequence_range"] = (
            _direct_transcript_sequence_range(transcript_refs)
        )
        metadata["direct_transcript_session_message_count"] = len(transcript_refs)
    if tool_protocol_refs:
        metadata["direct_tool_protocol_refs"] = tool_protocol_refs
        metadata["direct_tool_protocol_call_ids"] = _tool_protocol_call_ids(
            tool_protocol_refs,
        )
    if current_inbound_ref:
        metadata["current_inbound_ref"] = current_inbound_ref
    if isinstance(runtime_contract, dict):
        metadata["runtime_contract"] = dict(runtime_contract)
    if snapshot_metadata.get("runtime_contract_version") is not None:
        metadata["runtime_contract_version"] = snapshot_metadata.get(
            "runtime_contract_version",
        )
    if snapshot_metadata.get("runtime_contract_hash") is not None:
        metadata["runtime_contract_hash"] = snapshot_metadata.get(
            "runtime_contract_hash",
        )
    return {
        key: value
        for key, value in metadata.items()
        if value not in (None, "", {}, [])
    }


def _direct_transcript_message_refs(
    messages: tuple[LlmMessage, ...],
) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    for message in messages:
        ref = _session_message_ref(message)
        if ref is not None:
            refs.append(ref)
    return refs


def _direct_tool_protocol_refs(
    messages: tuple[LlmMessage, ...],
) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    for message in messages:
        ref = _session_message_ref(message)
        if ref is None:
            continue
        if message.tool_call_id:
            refs.append(ref)
            continue
        if message.role is LlmMessageRole.ASSISTANT and _is_function_call_content(
            message.content,
        ):
            refs.append(ref)
    return refs


def _session_message_ref(message: LlmMessage) -> dict[str, object] | None:
    metadata = message.metadata
    message_id = _metadata_text(metadata.get("session_message_id"))
    session_id = _metadata_text(metadata.get("session_id"))
    sequence_no = _metadata_int_or_none(metadata.get("sequence_no"))
    if message_id is None or session_id is None or sequence_no is None:
        return None
    ref: dict[str, object] = {
        "message_id": message_id,
        "session_id": session_id,
        "sequence_no": sequence_no,
        "role": message.role.value,
    }
    for source_key in ("kind", "source_kind", "source_id"):
        value = _metadata_text(metadata.get(source_key))
        if value is not None:
            ref[source_key] = value
    tool_call_id = _metadata_text(
        metadata.get("tool_call_id") or message.tool_call_id,
    )
    if tool_call_id is not None:
        ref["tool_call_id"] = tool_call_id
    tool_name = _metadata_text(metadata.get("tool_name") or message.name)
    if tool_name is not None:
        ref["tool_name"] = tool_name
    tool_status = _metadata_text(metadata.get("tool_status"))
    if tool_status is not None:
        ref["tool_status"] = tool_status
    if metadata.get("tool_error") is not None:
        ref["tool_error_present"] = True
    return ref


def _is_function_call_content(content: object) -> bool:
    return isinstance(content, dict) and content.get("type") == "function_call"


def _direct_transcript_sequence_range(
    refs: list[dict[str, object]],
) -> dict[str, object]:
    grouped: dict[str, list[int]] = {}
    for ref in refs:
        session_id = ref.get("session_id")
        sequence_no = ref.get("sequence_no")
        if not isinstance(session_id, str) or not isinstance(sequence_no, int):
            continue
        grouped.setdefault(session_id, []).append(sequence_no)
    if not grouped:
        return {}
    ranges = []
    for session_id, sequence_numbers in sorted(grouped.items()):
        ranges.append(
            {
                "session_id": session_id,
                "from_sequence_no": min(sequence_numbers),
                "to_sequence_no": max(sequence_numbers),
                "message_count": len(sequence_numbers),
            },
        )
    return {"sessions": ranges}


def _tool_protocol_call_ids(
    refs: list[dict[str, object]],
) -> list[str]:
    call_ids: list[str] = []
    for ref in refs:
        call_id = ref.get("tool_call_id")
        if not isinstance(call_id, str) or not call_id.strip():
            continue
        normalized = call_id.strip()
        if normalized not in call_ids:
            call_ids.append(normalized)
    return call_ids


def _current_inbound_ref(
    refs: list[dict[str, object]],
    *,
    snapshot_metadata: dict[str, object],
) -> dict[str, object] | None:
    current_message_id = _metadata_text(
        snapshot_metadata.get("current_inbound_message_id"),
    )
    if current_message_id is None:
        return None
    for ref in refs:
        if ref.get("message_id") == current_message_id:
            return dict(ref)
    return {"message_id": current_message_id}


def _metadata_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _metadata_int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _insert_after_system_prefix(
    messages: tuple[LlmMessage, ...],
    message: LlmMessage,
) -> tuple[LlmMessage, ...]:
    insert_at = 0
    for existing in messages:
        if existing.role is not LlmMessageRole.SYSTEM:
            break
        insert_at += 1
    return messages[:insert_at] + (message,) + messages[insert_at:]


__all__ = [
    "ProviderPromptRequestBuilder",
    "build_llm_request_metadata",
]
