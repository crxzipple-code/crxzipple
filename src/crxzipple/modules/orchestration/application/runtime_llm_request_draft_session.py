from __future__ import annotations

from crxzipple.modules.llm.application.session_runtime_transcript import (
    RuntimeReplayWindowBuilder,
    RuntimeTranscript,
    RuntimeTranscriptReport,
    build_current_inbound_runtime_transcript,
)
from crxzipple.modules.orchestration.application.ports import SessionTranscriptPort
from crxzipple.modules.orchestration.application.runtime_llm_request_draft_models import (
    SessionDraftContext,
)
from crxzipple.modules.orchestration.application.runtime_request_mode import (
    RuntimeRequestMode,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationRun,
    OrchestrationValidationError,
)
from crxzipple.modules.session.application import (
    GetSessionItemBySourceInput,
    ListSessionItemsInput,
    SessionReplayWindow,
)
from crxzipple.modules.session.domain import Session, SessionItem


def build_session_draft_context(
    session_service: SessionTranscriptPort,
    *,
    run: OrchestrationRun,
    session_key: str,
    mode: RuntimeRequestMode,
) -> SessionDraftContext:
    if mode is RuntimeRequestMode.MEMORY_FLUSH or mode_includes_direct_history(mode):
        bundle = session_service.get_session_with_items(
            ListSessionItemsInput(
                session_key=session_key,
                active_session_only=True,
            ),
        )
        replay_window = session_replay_window_from_items(
            session=bundle.session,
            items=tuple(bundle.items),
            active_session_only=True,
        )
        return SessionDraftContext(
            session=replay_window.session,
            replay_window=replay_window,
        )
    current_item = get_current_inbound_session_item(
        session_service,
        run=run,
        session_key=session_key,
    )
    if current_item is not None:
        bundle = session_service.get_session_with_items(
            ListSessionItemsInput(
                session_key=session_key,
                active_session_only=True,
                limit=0,
            ),
        )
        return SessionDraftContext(
            session=bundle.session,
            lightweight_items=(current_item,),
        )
    bundle = session_service.get_session_with_items(
        ListSessionItemsInput(
            session_key=session_key,
            active_session_only=True,
            limit=1,
        ),
    )
    return SessionDraftContext(
        session=bundle.session,
        lightweight_items=tuple(bundle.items),
    )


def build_runtime_replay_window(
    replay_window_builder: RuntimeReplayWindowBuilder,
    run: OrchestrationRun,
    *,
    session_items: tuple[SessionItem, ...] = (),
    mode: RuntimeRequestMode,
    memory_flush_transcript_max_chars: int,
    session_item_transcript_max_chars: int,
) -> RuntimeTranscript:
    if mode is RuntimeRequestMode.MEMORY_FLUSH:
        return replay_window_builder.build_from_session_items(
            session_items,
            max_chars=memory_flush_transcript_max_chars,
            include_non_protocol_history=True,
        )
    if mode in {
        RuntimeRequestMode.NORMAL_TURN,
        RuntimeRequestMode.SESSION_START,
    }:
        return current_inbound_transcript(run)
    if session_items:
        transcript = replay_window_builder.build_from_session_items(
            session_items,
            max_chars=session_item_transcript_max_chars,
            include_non_protocol_history=mode_includes_direct_history(mode),
        )
        if transcript.input_items or transcript.messages:
            return transcript
        if mode in {
            RuntimeRequestMode.NORMAL_TURN,
            RuntimeRequestMode.SESSION_START,
        }:
            return current_inbound_transcript(run)
        return transcript
    if mode not in {
        RuntimeRequestMode.NORMAL_TURN,
        RuntimeRequestMode.SESSION_START,
    }:
        return RuntimeTranscript(
            messages=(),
            report=RuntimeTranscriptReport(
                message_count=0,
                chars=0,
                estimated_tokens=0,
                tool_result_stats={},
            ),
        )
    return current_inbound_transcript(run)


def get_current_inbound_session_item(
    session_service: object,
    *,
    run: OrchestrationRun,
    session_key: str,
) -> SessionItem | None:
    lookup = getattr(session_service, "get_item_by_source", None)
    if not callable(lookup):
        return None
    active_session_id = optional_text(run.active_session_id)
    if active_session_id is None:
        return None
    try:
        item = lookup(
            GetSessionItemBySourceInput(
                session_key=session_key,
                session_id=active_session_id,
                source_module="orchestration",
                source_kind="orchestration_run",
                source_id=run.id,
            ),
        )
    except Exception:
        return None
    if isinstance(item, SessionItem) and item.role == "user":
        return item
    return None


def current_inbound_transcript(run: OrchestrationRun) -> RuntimeTranscript:
    try:
        return build_current_inbound_runtime_transcript(
            run.inbound_instruction.content,
            source=run.inbound_instruction.source,
            source_id=run.id,
        )
    except ValueError as exc:
        raise OrchestrationValidationError(
            "Current inbound instruction content must be structured content blocks.",
        ) from exc


def session_replay_window_from_items(
    *,
    session: Session,
    items: tuple[SessionItem, ...],
    active_session_only: bool,
) -> SessionReplayWindow:
    return SessionReplayWindow(
        session=session,
        items=items,
        active_session_only=active_session_only,
        from_sequence_no=items[0].sequence_no if items else None,
        to_sequence_no=items[-1].sequence_no if items else None,
        item_count=len(items),
        protocol_call_ids=tuple(
            dict.fromkeys(item.call_id for item in items if item.call_id),
        ),
    )


def mode_includes_direct_history(mode: RuntimeRequestMode) -> bool:
    return mode in {
        RuntimeRequestMode.COMPACTION,
        RuntimeRequestMode.MEMORY_FLUSH,
    }


def optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None
