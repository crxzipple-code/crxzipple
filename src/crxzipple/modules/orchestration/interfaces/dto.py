from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from crxzipple.modules.llm.interfaces.dto import LlmMessageDTO, ToolSchemaDTO
from crxzipple.modules.orchestration.application import RuntimeLlmRequestPreview
from crxzipple.modules.orchestration.domain import (
    InboundInstruction,
    OrchestrationErrorPayload,
    OrchestrationExecutorLease,
    OrchestrationRun,
    ReplyTarget,
)


@dataclass(frozen=True, slots=True)
class InboundInstructionDTO:
    source: str
    content: Any | None
    metadata: dict[str, object]

    @classmethod
    def from_value_object(
        cls,
        instruction: InboundInstruction,
    ) -> "InboundInstructionDTO":
        return cls(
            source=instruction.source,
            content=instruction.content,
            metadata=dict(instruction.metadata),
        )


@dataclass(frozen=True, slots=True)
class ReplyTargetDTO:
    interface_name: str
    address: str | None
    reply_to: str | None
    metadata: dict[str, object]

    @classmethod
    def from_value_object(cls, target: ReplyTarget) -> "ReplyTargetDTO":
        return cls(
            interface_name=target.interface_name,
            address=target.address,
            reply_to=target.reply_to,
            metadata=dict(target.metadata),
        )

@dataclass(frozen=True, slots=True)
class OrchestrationErrorDTO:
    message: str
    code: str
    details: dict[str, object]

    @classmethod
    def from_value_object(
        cls,
        payload: OrchestrationErrorPayload,
    ) -> "OrchestrationErrorDTO":
        return cls(
            message=payload.message,
            code=payload.code,
            details=dict(payload.details),
        )


@dataclass(frozen=True, slots=True)
class OrchestrationRunDTO:
    id: str
    status: str
    stage: str
    session_key: str | None
    active_session_id: str | None
    agent_id: str | None
    lane_key: str | None
    queue_policy: str
    priority: int
    current_step: int
    max_steps: int
    pending_tool_run_ids: tuple[str, ...]
    waiting_reason: str | None
    pending_approval_request: dict[str, object] | None
    last_approval_resolution: dict[str, object] | None
    recovery_contract: dict[str, object] | None
    inbound_instruction: InboundInstructionDTO
    reply_target: ReplyTargetDTO | None
    result_payload: dict[str, object] | None
    error: OrchestrationErrorDTO | None
    worker_id: str | None
    metadata: dict[str, object]
    created_at: datetime
    updated_at: datetime
    queued_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None

    @classmethod
    def from_entity(cls, run: OrchestrationRun) -> "OrchestrationRunDTO":
        return cls(
            id=run.id,
            status=run.status.value,
            stage=run.stage.value,
            session_key=run.session_key,
            active_session_id=run.active_session_id,
            agent_id=run.agent_id,
            lane_key=run.lane_key,
            queue_policy=run.queue_policy.value,
            priority=run.priority,
            current_step=run.current_step,
            max_steps=run.max_steps,
            pending_tool_run_ids=tuple(run.pending_tool_run_ids),
            waiting_reason=run.waiting_reason,
            pending_approval_request=(
                dict(run.pending_approval_request_payload)
                if run.pending_approval_request_payload is not None
                else None
            ),
            last_approval_resolution=(
                dict(run.last_approval_resolution_payload)
                if run.last_approval_resolution_payload is not None
                else None
            ),
            recovery_contract=(
                dict(run.recovery_contract_payload)
                if run.recovery_contract_payload is not None
                else None
            ),
            inbound_instruction=InboundInstructionDTO.from_value_object(
                run.inbound_instruction,
            ),
            reply_target=(
                ReplyTargetDTO.from_value_object(run.reply_target)
                if run.reply_target is not None
                else None
            ),
            result_payload=(
                dict(run.result_payload)
                if run.result_payload is not None
                else None
            ),
            error=(
                OrchestrationErrorDTO.from_value_object(run.error)
                if run.error is not None
                else None
            ),
            worker_id=run.worker_id,
            metadata=dict(run.metadata),
            created_at=run.created_at,
            updated_at=run.updated_at,
            queued_at=run.queued_at,
            started_at=run.started_at,
            completed_at=run.completed_at,
        )


@dataclass(frozen=True, slots=True)
class OrchestrationExecutorLeaseDTO:
    worker_id: str
    status: str
    effective_status: str
    expired: bool
    counts_toward_capacity: bool
    max_inflight_assignments: int
    inflight_assignment_count: int
    available_assignment_slots: int
    metadata: dict[str, object]
    created_at: datetime
    updated_at: datetime
    last_heartbeat_at: datetime
    lease_expires_at: datetime | None

    @classmethod
    def from_entity(
        cls,
        lease: OrchestrationExecutorLease,
    ) -> "OrchestrationExecutorLeaseDTO":
        expired = lease.is_expired()
        effective_status = lease.effective_status().value
        counts_toward_capacity = lease.counts_toward_capacity()
        return cls(
            worker_id=lease.worker_id,
            status=lease.status.value,
            effective_status=effective_status,
            expired=expired,
            counts_toward_capacity=counts_toward_capacity,
            max_inflight_assignments=lease.max_inflight_assignments,
            inflight_assignment_count=lease.inflight_assignment_count,
            available_assignment_slots=lease.available_assignment_slots(),
            metadata=dict(lease.metadata),
            created_at=lease.created_at,
            updated_at=lease.updated_at,
            last_heartbeat_at=lease.last_heartbeat_at,
            lease_expires_at=lease.lease_expires_at,
        )


@dataclass(frozen=True, slots=True)
class RuntimeLlmRequestPreviewDTO:
    run_id: str
    llm_id: str
    mode: str
    messages: tuple[LlmMessageDTO, ...]
    input_items: tuple[dict[str, object], ...]
    tool_schemas: tuple[ToolSchemaDTO, ...]
    runtime_request_report: dict[str, object] | None
    request_render_snapshot_id: str | None
    request_render_snapshot: dict[str, object] | None
    request_render_snapshot_metadata: dict[str, object]
    tool_surface: dict[str, object]
    runtime_context: dict[str, object]
    provider_request_options: dict[str, object]

    @classmethod
    def from_value(
        cls,
        *,
        run_id: str,
        preview: RuntimeLlmRequestPreview,
    ) -> "RuntimeLlmRequestPreviewDTO":
        return cls(
            run_id=run_id,
            llm_id=preview.llm_id,
            mode=preview.mode.value,
            messages=tuple(
                LlmMessageDTO.from_value(message)
                for message in preview.messages
            ),
            input_items=tuple(dict(item) for item in preview.input_items),
            tool_schemas=tuple(
                ToolSchemaDTO.from_value(schema)
                for schema in preview.tool_schemas
            ),
            runtime_request_report=(
                preview.runtime_request_report.to_payload()
                if preview.runtime_request_report is not None
                else None
            ),
            request_render_snapshot_id=preview.request_render_snapshot_id,
            request_render_snapshot=dict(preview.request_render_snapshot),
            request_render_snapshot_metadata=_request_render_snapshot_metadata_preview(
                preview.request_render_snapshot_metadata,
            ),
            tool_surface=dict(preview.tool_surface),
            runtime_context=dict(preview.runtime_context),
            provider_request_options=dict(preview.provider_request_options),
        )


def _request_render_snapshot_metadata_preview(
    metadata: dict[str, object],
) -> dict[str, object]:
    allowed_keys = {
        "snapshot_kind",
        "tree_schema_version",
        "runtime_contract_version",
        "runtime_contract_hash",
        "history_delivery",
        "session_budget_status",
        "duplicate_tool_delivery_risk",
        "draft_input_message_count",
        "draft_input_session_item_count",
        "draft_input_roles",
        "draft_input_budget_summary",
        "protocol_required_ref_count",
        "collapsed_ref_count",
        "mirrored_tool_schema_count",
        "provider_tool_schema_names",
        "visible_input_summary",
        "request_render_timings",
        "runtime_request_snapshot",
        "request_render_snapshot",
        "tool_schema_mirror_budget",
        "tool_schema_mirror_default_schema_source",
        "tool_schema_mirror_skipped_count",
        "tool_schema_mirror_duplicate_count",
        "tool_schema_mirror_skipped_by_reason",
        "artifact_content_budget",
        "artifact_content_block_count",
        "artifact_content_candidate_count",
        "artifact_content_image_count",
        "artifact_content_file_count",
        "artifact_content_omitted_count",
    }
    preview: dict[str, object] = {}
    for key in sorted(allowed_keys):
        value = metadata.get(key)
        if value in (None, "", {}, []):
            continue
        if isinstance(value, dict):
            preview[key] = _metadata_dict_summary(value)
        elif isinstance(value, list | tuple):
            preview[key] = _metadata_list_summary(value)
        else:
            preview[key] = value
    return preview


def _metadata_dict_summary(value: dict[str, object]) -> dict[str, object]:
    omitted_keys = {
        "content",
        "debug_body",
        "input",
        "messages",
        "node_estimate_breakdown",
        "provider_attachment_mirror",
        "provider_attachments",
        "raw_tree_body",
        "rendered_prompt",
        "text",
        "tool_schemas",
        "top_rendered_nodes",
    }
    result: dict[str, object] = {}
    for key, item in value.items():
        if key in omitted_keys or item in (None, "", {}, []):
            continue
        if isinstance(item, str | int | float | bool):
            result[key] = item
        elif isinstance(item, dict):
            result[key] = {"field_count": len(item)}
        elif isinstance(item, list | tuple):
            result[key] = {"item_count": len(item)}
    return result


def _metadata_list_summary(value: list[object] | tuple[object, ...]) -> dict[str, object]:
    scalar_items = [
        item for item in value if isinstance(item, str | int | float | bool)
    ]
    if len(scalar_items) == len(value):
        return {
            "item_count": len(value),
            "items": list(scalar_items[:50]),
        }
    return {"item_count": len(value)}
