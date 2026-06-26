from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.llm.domain import (
    LlmResponseItem,
    ToolCallIntent,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationRun,
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.application.ports import SessionRecorderPort
from crxzipple.modules.orchestration.application.engine_session_tool_results import (
    ExecutionStepItemLookupPort,
    build_tool_result_session_item_input,
    resolve_background_tool_result_reference,
)
from crxzipple.modules.session.application.runtime_response_projection import (
    ProjectLlmResponseItemsInput,
    RuntimeResponseProjector,
)
from crxzipple.modules.session.application import (
    AppendSessionItemInput,
    AppendSessionItemsInput,
    GetSessionItemBySourceInput,
)
from crxzipple.modules.session.domain import (
    SessionItemKind,
    SessionItemPhase,
)
from crxzipple.modules.tool.domain import ToolRun
from crxzipple.shared.content_blocks import (
    normalize_content_blocks,
    text_content_block,
)


@dataclass(frozen=True, slots=True)
class InboundSessionRecord:
    user_session_item_id: str | None = None


@dataclass(frozen=True, slots=True)
class SessionProtocolRecord:
    message_ids: tuple[str, ...] = ()
    item_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RuntimeResponseRecord:
    item_ids: tuple[str, ...] = ()
    assistant_progress_item_ids: tuple[str, ...] = ()
    tool_calls: tuple[ToolCallIntent, ...] = ()
    tool_call_session_item_ids_by_call_id: dict[str, str] | None = None


@dataclass(slots=True)
class OrchestrationSessionRecorder:
    session_service: SessionRecorderPort
    execution_item_lookup: ExecutionStepItemLookupPort | None = None
    runtime_response_projector: RuntimeResponseProjector = RuntimeResponseProjector()

    def ensure_inbound_message(
        self,
        run: OrchestrationRun,
        *,
        session_key: str,
    ) -> InboundSessionRecord:
        cached_item_id = run.metadata.get("user_session_item_id")
        if isinstance(cached_item_id, str) and cached_item_id.strip():
            return InboundSessionRecord(
                user_session_item_id=cached_item_id.strip(),
            )
        existing_item = self.session_service.get_item_by_source(
            GetSessionItemBySourceInput(
                session_key=session_key,
                session_id=run.active_session_id,
                source_module="orchestration",
                source_kind="orchestration_run",
                source_id=run.id,
            ),
        )
        if existing_item is not None and existing_item.role == "user":
            return InboundSessionRecord(
                user_session_item_id=existing_item.id,
            )
        inbound_blocks = normalize_content_blocks(run.inbound_instruction.content)
        if not inbound_blocks:
            return InboundSessionRecord(
                user_session_item_id=(
                    existing_item.id if existing_item is not None else None
                ),
            )
        item = existing_item
        if item is None:
            item = self.session_service.append_items(
                AppendSessionItemsInput(
                    items=(
                        AppendSessionItemInput(
                            session_key=session_key,
                            session_id=run.active_session_id,
                            role="user",
                            kind=SessionItemKind.USER_MESSAGE,
                            phase=SessionItemPhase.COMMENTARY,
                            content_payload={"blocks": inbound_blocks},
                            source_module="orchestration",
                            source_kind="orchestration_run",
                            source_id=run.id,
                            metadata={
                                "source": run.inbound_instruction.source,
                                "inbound_metadata": dict(
                                    run.inbound_instruction.metadata,
                                ),
                            },
                        ),
                    ),
                ),
            )[0]
        return InboundSessionRecord(
            user_session_item_id=str(getattr(item, "id", "")) or None,
        )

    def append_assistant_response_message(
        self,
        *,
        session_key: str,
        active_session_id: str,
        invocation_id: str,
        response_text: str | None,
        structured_output: object | None,
        finish_reason: str | None,
        usage_payload: dict[str, object] | None,
    ) -> tuple[str, ...]:
        return self.append_assistant_response_item(
            session_key=session_key,
            active_session_id=active_session_id,
            invocation_id=invocation_id,
            response_text=response_text,
            structured_output=structured_output,
            finish_reason=finish_reason,
            usage_payload=usage_payload,
        )

    def append_assistant_response_item(
        self,
        *,
        session_key: str,
        active_session_id: str,
        invocation_id: str,
        response_text: str | None,
        structured_output: object | None,
        finish_reason: str | None,
        usage_payload: dict[str, object] | None,
    ) -> tuple[str, ...]:
        if response_text is None and structured_output is None:
            return ()
        content_payload = _assistant_response_content_payload(
            response_text=response_text,
            structured_output=structured_output,
            finish_reason=finish_reason,
            usage_payload=usage_payload,
        )
        items = self.session_service.append_items(
            AppendSessionItemsInput(
                items=(
                    AppendSessionItemInput(
                        session_key=session_key,
                        session_id=active_session_id,
                        role="assistant",
                        kind=SessionItemKind.ASSISTANT_MESSAGE,
                        phase=(
                            SessionItemPhase.COMMENTARY
                            if finish_reason == "tool_calls"
                            else SessionItemPhase.FINAL_ANSWER
                        ),
                        content_payload=content_payload,
                        source_module="llm",
                        source_kind="llm_invocation",
                        source_id=invocation_id,
                        metadata={
                            "finish_reason": finish_reason or "",
                        },
                    ),
                ),
            ),
        )
        return tuple(str(item.id) for item in items)

    def append_llm_response_items(
        self,
        *,
        session_key: str,
        active_session_id: str,
        invocation_id: str,
        response_items: tuple[LlmResponseItem, ...],
    ) -> RuntimeResponseRecord:
        projected = self.runtime_response_projector.project_llm_response_items(
            ProjectLlmResponseItemsInput(
                session_key=session_key,
                active_session_id=active_session_id,
                invocation_id=invocation_id,
                response_items=response_items,
            )
        )
        inputs = projected.items
        if not inputs:
            return RuntimeResponseRecord(tool_calls=projected.tool_calls)
        items = self.session_service.append_items(
            AppendSessionItemsInput(items=inputs),
        )
        assistant_progress_item_ids = tuple(
            str(item.id)
            for item in items
            if _is_assistant_progress_session_item(item)
        )
        tool_call_session_item_ids_by_call_id = {
            str(item.call_id): str(item.id)
            for item in items
            if _is_tool_call_session_item(item)
            and isinstance(getattr(item, "call_id", None), str)
            and getattr(item, "call_id").strip()
        }
        return RuntimeResponseRecord(
            item_ids=tuple(str(item.id) for item in items),
            assistant_progress_item_ids=assistant_progress_item_ids,
            tool_calls=projected.tool_calls,
            tool_call_session_item_ids_by_call_id=tool_call_session_item_ids_by_call_id,
        )

    def append_tool_call_messages(
        self,
        *,
        session_key: str,
        active_session_id: str,
        invocation_id: str,
        response_text: str | None,
        tool_calls: tuple[ToolCallIntent, ...],
        append_session_items: bool = False,
    ) -> tuple[str, ...]:
        return self.append_tool_call_records(
            session_key=session_key,
            active_session_id=active_session_id,
            invocation_id=invocation_id,
            response_text=response_text,
            tool_calls=tool_calls,
            append_session_items=append_session_items,
        ).message_ids

    def append_tool_call_records(
        self,
        *,
        session_key: str,
        active_session_id: str,
        invocation_id: str,
        response_text: str | None,
        tool_calls: tuple[ToolCallIntent, ...],
        append_session_items: bool = False,
    ) -> SessionProtocolRecord:
        items = ()
        item_inputs: list[AppendSessionItemInput] = []
        if append_session_items and response_text is not None and response_text.strip():
            item_inputs.append(
                AppendSessionItemInput(
                    session_key=session_key,
                    session_id=active_session_id,
                    role="assistant",
                    kind=SessionItemKind.ASSISTANT_MESSAGE,
                    phase=SessionItemPhase.COMMENTARY,
                    content_payload={
                        "blocks": [text_content_block(response_text)],
                        "text": response_text,
                        "finish_reason": "tool_calls",
                    },
                    source_module="llm",
                    source_kind="llm_invocation",
                    source_id=invocation_id or None,
                    metadata={"finish_reason": "tool_calls"},
                ),
            )
        if append_session_items and tool_calls:
            item_inputs.extend(
                AppendSessionItemInput(
                    session_key=session_key,
                    session_id=active_session_id,
                    role="assistant",
                    kind=SessionItemKind.TOOL_CALL,
                    phase=SessionItemPhase.COMMENTARY,
                    content_payload={
                        "type": "function_call",
                        "call_id": tool_call.id,
                        "tool_name": tool_call.name,
                        "arguments": dict(tool_call.arguments),
                    },
                    source_module="llm",
                    source_kind="llm_invocation",
                    source_id=invocation_id or None,
                    call_id=tool_call.id,
                    tool_name=tool_call.name,
                    metadata={
                        "tool_call_id": tool_call.id,
                        "tool_name": tool_call.name,
                    },
                )
                for tool_call in tool_calls
            )
        if item_inputs:
            items = self.session_service.append_items(
                AppendSessionItemsInput(items=tuple(item_inputs)),
            )
        return SessionProtocolRecord(
            message_ids=(),
            item_ids=tuple(item.id for item in items),
        )

    def append_tool_result_message(
        self,
        *,
        session_key: str,
        active_session_id: str,
        tool_call: ToolCallIntent,
        tool_run: ToolRun,
        source_kind: str,
        source_id: str,
    ) -> str:
        record = self.append_tool_result_records(
            session_key=session_key,
            active_session_id=active_session_id,
            items=((tool_call, tool_run, source_kind, source_id),),
        )
        if record.item_ids:
            return record.item_ids[0]
        return ""

    def append_tool_result_messages(
        self,
        *,
        session_key: str,
        active_session_id: str,
        items: tuple[tuple[ToolCallIntent, ToolRun, str, str], ...],
    ) -> tuple[str, ...]:
        return self.append_tool_result_records(
            session_key=session_key,
            active_session_id=active_session_id,
            items=items,
        ).item_ids

    def append_tool_result_records(
        self,
        *,
        session_key: str,
        active_session_id: str,
        items: tuple[tuple[ToolCallIntent, ToolRun, str, str], ...],
    ) -> SessionProtocolRecord:
        item_inputs = tuple(
            build_tool_result_session_item_input(
                session_key=session_key,
                active_session_id=active_session_id,
                tool_call=tool_call,
                tool_run=tool_run,
                source_kind=source_kind,
                source_id=source_id,
            )
            for tool_call, tool_run, source_kind, source_id in items
        )
        session_items = self.session_service.append_items(
            AppendSessionItemsInput(items=item_inputs),
        )
        return SessionProtocolRecord(
            message_ids=(),
            item_ids=tuple(item.id for item in session_items),
        )

    def append_completed_background_tool_results(
        self,
        run: OrchestrationRun,
        *,
        tool_runs: tuple[ToolRun, ...],
    ) -> tuple[str, ...]:
        session_key = str(run.metadata.get("session_key", "")).strip()
        if not session_key:
            raise OrchestrationValidationError(
                "Orchestration run metadata.session_key is required to append tool results.",
            )
        if run.active_session_id is None or not run.active_session_id.strip():
            raise OrchestrationValidationError(
                "Orchestration run active_session_id is required to append tool results.",
            )
        item_ids: list[str] = []
        for tool_run in tool_runs:
            existing = self.session_service.get_item_by_source(
                GetSessionItemBySourceInput(
                    session_key=session_key,
                    session_id=run.active_session_id,
                    source_module="tool",
                    source_kind="tool_run",
                    source_id=tool_run.id,
                ),
            )
            if existing is not None:
                item_ids.append(existing.id)
                continue
            tool_metadata = self._background_tool_result_reference(
                run=run,
                tool_run=tool_run,
            )
            record = self.append_tool_result_records(
                session_key=session_key,
                active_session_id=run.active_session_id,
                items=(
                    (
                        ToolCallIntent(
                            id=tool_metadata["tool_call_id"],
                            name=tool_metadata["tool_name"],
                            arguments={},
                        ),
                        tool_run,
                        "tool_run",
                        tool_run.id,
                    ),
                ),
            )
            item_ids.extend(record.item_ids)
        return tuple(item_ids)

    def _background_tool_result_reference(
        self,
        *,
        run: OrchestrationRun,
        tool_run: ToolRun,
    ) -> dict[str, str]:
        return self.background_tool_result_reference(run=run, tool_run=tool_run)

    def background_tool_result_reference(
        self,
        *,
        run: OrchestrationRun,
        tool_run: ToolRun,
    ) -> dict[str, str]:
        return resolve_background_tool_result_reference(
            execution_item_lookup=self.execution_item_lookup,
            run=run,
            tool_run=tool_run,
        )


def _assistant_response_content_payload(
    *,
    response_text: str | None,
    structured_output: object | None,
    finish_reason: str | None,
    usage_payload: dict[str, object] | None,
) -> dict[str, object]:
    content_payload: dict[str, object] = {}
    if response_text is not None:
        content_payload["blocks"] = [text_content_block(response_text)]
        content_payload["text"] = response_text
    if structured_output is not None:
        content_payload["structured_output"] = structured_output
    if finish_reason is not None:
        content_payload["finish_reason"] = finish_reason
    if usage_payload is not None:
        content_payload["usage"] = usage_payload
    return content_payload


def _is_assistant_progress_session_item(item: Any) -> bool:
    if item.kind is SessionItemKind.AGENT_PROGRESS:
        return True
    return (
        item.kind is SessionItemKind.ASSISTANT_MESSAGE
        and item.role == "assistant"
        and item.phase is SessionItemPhase.COMMENTARY
    )


def _is_tool_call_session_item(item: Any) -> bool:
    return item.kind is SessionItemKind.TOOL_CALL
