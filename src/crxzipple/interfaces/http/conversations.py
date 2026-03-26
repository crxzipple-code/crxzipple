from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from crxzipple.bootstrap import AppContainer
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.session.application import ListSessionMessagesInput
from crxzipple.modules.session.domain import SessionNotFoundError
from crxzipple.modules.session.interfaces.dto import SessionMessageDTO
from crxzipple.modules.session.interfaces.http_models import (
    SessionMessageResponse,
    SessionRuntimeBindingPayload,
)


router = APIRouter()

_TITLE_MAX_CHARS = 72
_LOW_SIGNAL_TITLES = {
    "hi",
    "hello",
    "hey",
    "嗨",
    "你好",
    "您好",
    "在吗",
    "早上好",
    "晚上好",
}

_MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MARKDOWN_AUTOLINK_RE = re.compile(r"<(https?://[^>]+)>")
_MARKDOWN_PREFIX_RE = re.compile(r"(?m)^\s{0,3}(?:#{1,6}\s*|>\s+|[-+*]\s+|\d+\.\s+)")
_MARKDOWN_INLINE_HEADING_RE = re.compile(r"(?:(?<=^)|(?<=\s))#{2,6}\s*(?=[^\s#])")
_MARKDOWN_INLINE_LIST_RE = re.compile(r"(?:(?<=^)|(?<=\s))(?:[-*]\s+|\d+\.\s+)(?=\S)")
_MARKDOWN_TABLE_RULE_RE = re.compile(r"(?m)^\s*\|?[-: ]+\|[-|: ]*$")
_MARKDOWN_HORIZONTAL_RULE_RE = re.compile(r"(?m)^\s{0,3}(?:[-*_]\s*){3,}$")
_MARKDOWN_TASK_MARK_RE = re.compile(r"(?<!\w)\[(?: |x|X)\]\s*")
_LATEX_BLOCK_RE = re.compile(r"\$\$(.*?)\$\$", re.S)
_LATEX_PAREN_RE = re.compile(r"\\\((.*?)\\\)")
_LATEX_BRACKET_RE = re.compile(r"\\\[(.*?)\\\]")
_LATEX_INLINE_RE = re.compile(r"(?<!\$)\$(?!\s)(.+?)(?<!\s)\$(?!\$)")
_ESCAPED_MARKUP_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|>~])")
_HTML_TAG_RE = re.compile(r"</?[^>]+>")
_MARKDOWN_EMPHASIS_PATTERNS = (
    (re.compile(r"\*\*(.*?)\*\*"), r"\1"),
    (re.compile(r"__(.*?)__"), r"\1"),
    (re.compile(r"~~(.*?)~~"), r"\1"),
    (re.compile(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)"), r"\1"),
    (re.compile(r"(?<!_)_(?!\s)(.+?)(?<!\s)_(?!_)"), r"\1"),
)


def _strip_inline_markdown_markers(value: str) -> str:
    stripped = value
    inline_heading_count = len(_MARKDOWN_INLINE_HEADING_RE.findall(stripped))
    if inline_heading_count:
        stripped = _MARKDOWN_INLINE_HEADING_RE.sub("", stripped)
    inline_list_count = len(_MARKDOWN_INLINE_LIST_RE.findall(stripped))
    if inline_list_count >= 2 or (inline_heading_count and inline_list_count >= 1):
        stripped = _MARKDOWN_INLINE_LIST_RE.sub("", stripped)
    return stripped


def _strip_preview_markup(value: str) -> str:
    stripped = value.replace("```", " ").replace("~~~", " ").replace("`", "")
    stripped = _MARKDOWN_IMAGE_RE.sub(r"\1", stripped)
    stripped = _MARKDOWN_LINK_RE.sub(r"\1", stripped)
    stripped = _MARKDOWN_AUTOLINK_RE.sub(r"\1", stripped)
    stripped = _MARKDOWN_TABLE_RULE_RE.sub(" ", stripped)
    stripped = _MARKDOWN_HORIZONTAL_RULE_RE.sub(" ", stripped)
    stripped = _LATEX_BLOCK_RE.sub(r"\1", stripped)
    stripped = _LATEX_PAREN_RE.sub(r"\1", stripped)
    stripped = _LATEX_BRACKET_RE.sub(r"\1", stripped)
    stripped = _LATEX_INLINE_RE.sub(r"\1", stripped)
    stripped = _MARKDOWN_PREFIX_RE.sub("", stripped)
    stripped = _strip_inline_markdown_markers(stripped)
    stripped = _MARKDOWN_TASK_MARK_RE.sub("", stripped)
    stripped = _ESCAPED_MARKUP_RE.sub(r"\1", stripped)
    for pattern, replacement in _MARKDOWN_EMPHASIS_PATTERNS:
        stripped = pattern.sub(replacement, stripped)
    stripped = _HTML_TAG_RE.sub(" ", stripped)
    stripped = stripped.replace("|", " ")
    return stripped


def _normalize_preview_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"\s+", " ", _strip_preview_markup(value)).strip()
    return normalized or None


def _truncate_title(value: str) -> str:
    if len(value) <= _TITLE_MAX_CHARS:
        return value
    return f"{value[: _TITLE_MAX_CHARS - 3].rstrip()}..."


def _is_substantive_title_candidate(value: str) -> bool:
    return value.casefold() not in _LOW_SIGNAL_TITLES and len(value) >= 3


@dataclass(frozen=True, slots=True)
class ConversationSummaryDTO:
    bulk_key: str
    session_key: str
    active_session_id: str
    title: str
    runtime_binding: SessionRuntimeBindingPayload
    status: str
    channel: str | None
    chat_type: str | None
    latest_run_id: str | None
    latest_run_status: str | None
    latest_run_stage: str | None
    display_run_id: str | None
    display_run_status: str | None
    display_run_stage: str | None
    last_message_preview: str | None
    created_at: str
    updated_at: str


class ConversationResponse(BaseModel):
    bulk_key: str
    session_key: str
    active_session_id: str
    title: str
    runtime_binding: SessionRuntimeBindingPayload
    status: str
    channel: str | None = None
    chat_type: str | None = None
    latest_run_id: str | None = None
    latest_run_status: str | None = None
    latest_run_stage: str | None = None
    display_run_id: str | None = None
    display_run_status: str | None = None
    display_run_stage: str | None = None
    last_message_preview: str | None = None
    created_at: str
    updated_at: str

    @classmethod
    def from_dto(cls, dto: ConversationSummaryDTO) -> "ConversationResponse":
        return cls(
            bulk_key=dto.bulk_key,
            session_key=dto.session_key,
            active_session_id=dto.active_session_id,
            title=dto.title,
            runtime_binding=dto.runtime_binding,
            status=dto.status,
            channel=dto.channel,
            chat_type=dto.chat_type,
            latest_run_id=dto.latest_run_id,
            latest_run_status=dto.latest_run_status,
            latest_run_stage=dto.latest_run_stage,
            display_run_id=dto.display_run_id,
            display_run_status=dto.display_run_status,
            display_run_stage=dto.display_run_stage,
            last_message_preview=dto.last_message_preview,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
        )


def _resolve_session_key_for_bulk(
    container: AppContainer,
    *,
    bulk_key: str,
) -> str:
    runs = container.orchestration_service.list_runs()
    for run in sorted(runs, key=lambda item: item.created_at, reverse=True):
        if run.bulk_key != bulk_key:
            continue
        session_key = str(run.metadata.get("session_key", "")).strip()
        if session_key:
            return session_key
    raise HTTPException(
        status_code=404,
        detail=f"No conversation session was found for bulk_key '{bulk_key}'.",
    )


def _latest_run_by_bulk_key(container: AppContainer) -> dict[str, object]:
    latest: dict[str, object] = {}
    for run in sorted(
        container.orchestration_service.list_runs(),
        key=lambda item: item.updated_at,
        reverse=True,
    ):
        if run.bulk_key is None or run.bulk_key in latest:
            continue
        latest[run.bulk_key] = run
    return latest


def _is_maintenance_run(run) -> bool:  # noqa: ANN001
    source = str(getattr(run.inbound_instruction, "source", "")).strip().lower()
    return source in {"compaction", "memory_flush", "heartbeat"}


def _display_run_by_bulk_key(container: AppContainer) -> dict[str, object]:
    display: dict[str, object] = {}
    for run in sorted(
        container.orchestration_service.list_runs(),
        key=lambda item: item.updated_at,
        reverse=True,
    ):
        if run.bulk_key is None or run.bulk_key in display:
            continue
        if _is_maintenance_run(run):
            continue
        display[run.bulk_key] = run
    return display


def _last_message_preview(container: AppContainer, *, session_key: str) -> str | None:
    try:
        items = container.session_service.list_messages(
            ListSessionMessagesInput(
                session_key=session_key,
                include_archived=False,
            ),
        )
    except SessionNotFoundError:
        return None
    for item in reversed(items):
        preview = _message_preview_text(SessionMessageDTO.from_entity(item))
        if preview is not None:
            return preview
    try:
        all_items = container.session_service.list_messages(
            ListSessionMessagesInput(
                session_key=session_key,
                include_archived=True,
            ),
        )
    except SessionNotFoundError:
        return None
    for item in reversed(all_items):
        preview = _message_preview_text(SessionMessageDTO.from_entity(item))
        if preview is not None:
            return preview
    return None


def _message_preview_text(message: SessionMessageDTO) -> str | None:
    maintenance_kind = message.metadata.get("maintenance_kind")
    if isinstance(maintenance_kind, str) and maintenance_kind.strip():
        return None
    if message.content is not None and message.content.strip():
        return _normalize_preview_text(message.content)
    text_payload = message.content_payload.get("text")
    if isinstance(text_payload, str) and text_payload.strip():
        return _normalize_preview_text(text_payload)
    return None


def _conversation_title(container: AppContainer, *, session_key: str) -> str | None:
    session = container.session_service.get_session(session_key)
    explicit_title = _normalize_preview_text(session.origin.label)
    if explicit_title is not None:
        return _truncate_title(explicit_title)
    metadata_title = session.metadata.get("thread_title")
    if isinstance(metadata_title, str):
        normalized_metadata_title = _normalize_preview_text(metadata_title)
        if normalized_metadata_title is not None:
            return _truncate_title(normalized_metadata_title)
    try:
        items = container.session_service.list_messages(
            ListSessionMessagesInput(
                session_key=session_key,
                include_archived=True,
            ),
        )
    except SessionNotFoundError:
        return None
    fallback_title: str | None = None
    for item in items:
        if item.role != "user":
            continue
        text = _message_preview_text(SessionMessageDTO.from_entity(item))
        if text is None:
            continue
        if fallback_title is None:
            fallback_title = text
        if _is_substantive_title_candidate(text):
            return _truncate_title(text)
    if fallback_title is not None:
        return _truncate_title(fallback_title)
    return None


def _build_conversation_summary(
    container: AppContainer,
    *,
    bulk_key: str,
    session_key: str,
    latest_run,  # noqa: ANN001
    display_run,  # noqa: ANN001
) -> ConversationSummaryDTO:
    session = container.session_service.get_session(session_key)
    binding = session.runtime_binding()
    return ConversationSummaryDTO(
        bulk_key=bulk_key,
        session_key=session_key,
        active_session_id=session.active_session_id,
        title=_conversation_title(container, session_key=session_key) or "New thread",
        runtime_binding=SessionRuntimeBindingPayload(
            agent_id=binding.agent_id,
            llm_id=binding.llm_id,
        ),
        status=session.status,
        channel=session.channel,
        chat_type=session.chat_type,
        latest_run_id=latest_run.id if latest_run is not None else None,
        latest_run_status=latest_run.status.value if latest_run is not None else None,
        latest_run_stage=latest_run.stage.value if latest_run is not None else None,
        display_run_id=display_run.id if display_run is not None else None,
        display_run_status=display_run.status.value if display_run is not None else None,
        display_run_stage=display_run.stage.value if display_run is not None else None,
        last_message_preview=_last_message_preview(container, session_key=session_key),
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
    )


def _list_conversation_summaries(
    container: AppContainer,
) -> list[ConversationSummaryDTO]:
    items: list[ConversationSummaryDTO] = []
    latest_by_bulk = _latest_run_by_bulk_key(container)
    display_by_bulk = _display_run_by_bulk_key(container)
    for bulk_key, latest_run in latest_by_bulk.items():
        session_key = str(latest_run.metadata.get("session_key", "")).strip()
        if not session_key:
            continue
        try:
            items.append(
                _build_conversation_summary(
                    container,
                    bulk_key=bulk_key,
                    session_key=session_key,
                    latest_run=latest_run,
                    display_run=display_by_bulk.get(bulk_key),
                ),
            )
        except SessionNotFoundError:
            continue
    items.sort(key=lambda item: item.updated_at, reverse=True)
    return items


@router.get("/conversations", response_model=list[ConversationResponse])
def list_conversations(
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[ConversationResponse]:
    return [ConversationResponse.from_dto(item) for item in _list_conversation_summaries(container)]


@router.get("/conversations/{bulk_key}", response_model=ConversationResponse)
def get_conversation(
    bulk_key: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ConversationResponse:
    session_key = _resolve_session_key_for_bulk(container, bulk_key=bulk_key)
    latest_run = _latest_run_by_bulk_key(container).get(bulk_key)
    try:
        dto = _build_conversation_summary(
            container,
            bulk_key=bulk_key,
            session_key=session_key,
            latest_run=latest_run,
            display_run=_display_run_by_bulk_key(container).get(bulk_key),
        )
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return ConversationResponse.from_dto(dto)


@router.get(
    "/conversations/{bulk_key}/messages",
    response_model=list[SessionMessageResponse],
)
def list_conversation_messages(
    bulk_key: str,
    container: Annotated[AppContainer, Depends(get_container)],
    limit: Annotated[int | None, Query(ge=1)] = None,
    active_session_only: Annotated[bool, Query()] = False,
    include_archived: Annotated[bool, Query()] = False,
) -> list[SessionMessageResponse]:
    session_key = _resolve_session_key_for_bulk(container, bulk_key=bulk_key)
    try:
        items = container.session_service.list_messages(
            ListSessionMessagesInput(
                session_key=session_key,
                limit=limit,
                active_session_only=active_session_only,
                include_archived=include_archived,
            ),
        )
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return [SessionMessageResponse.from_dto(SessionMessageDTO.from_entity(item)) for item in items]
