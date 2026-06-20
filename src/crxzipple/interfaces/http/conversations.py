from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.orchestration.application.ports import OrchestrationRunQueryPort
from crxzipple.modules.orchestration.interfaces.dto import OrchestrationRunDTO
from crxzipple.modules.orchestration.interfaces.http_models import OrchestrationRunResponse
from crxzipple.modules.session.application import ListSessionItemsInput
from crxzipple.modules.session.domain import SessionNotFoundError
from crxzipple.modules.session.interfaces.dto import SessionItemDTO
from crxzipple.shared.content_blocks import content_blocks_from_payload, extract_text_content
from crxzipple.modules.session.interfaces.http_models import (
    SessionItemResponse,
    SessionRuntimeBindingPayload,
)
from crxzipple.shared.time import format_datetime_utc


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


def _humanize_source_label(value: str | None) -> str | None:
    normalized = _normalize_preview_text(value)
    if normalized is None:
        return None
    collapsed = re.sub(r"[_\-\s]+", " ", normalized).strip()
    if not collapsed:
        return None
    return " ".join(part[:1].upper() + part[1:] for part in collapsed.split())


def _is_substantive_title_candidate(value: str) -> bool:
    return value.casefold() not in _LOW_SIGNAL_TITLES and len(value) >= 3


@dataclass(frozen=True, slots=True)
class ConversationSummaryDTO:
    session_key: str
    active_session_id: str
    title: str
    runtime_binding: SessionRuntimeBindingPayload
    status: str
    source_label: str | None
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
    session_key: str
    active_session_id: str
    title: str
    runtime_binding: SessionRuntimeBindingPayload
    status: str
    source_label: str | None = None
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
            session_key=dto.session_key,
            active_session_id=dto.active_session_id,
            title=dto.title,
            runtime_binding=dto.runtime_binding,
            status=dto.status,
            source_label=dto.source_label,
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


def _run_query_port(container: AppContainer) -> OrchestrationRunQueryPort:
    return container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE)


def _latest_run_by_session_key(run_query: OrchestrationRunQueryPort) -> dict[str, object]:
    latest: dict[str, object] = {}
    for run in sorted(
        run_query.list_runs(),
        key=lambda item: item.updated_at,
        reverse=True,
    ):
        session_key = run.session_key
        if session_key is None or session_key in latest:
            continue
        latest[session_key] = run
    return latest


def _is_maintenance_run(run) -> bool:  # noqa: ANN001
    source = str(getattr(run.inbound_instruction, "source", "")).strip().lower()
    return source in {"compaction", "memory_flush", "heartbeat"}


def _display_run_by_session_key(run_query: OrchestrationRunQueryPort) -> dict[str, object]:
    display: dict[str, object] = {}
    for run in sorted(
        run_query.list_runs(),
        key=lambda item: item.updated_at,
        reverse=True,
    ):
        session_key = run.session_key
        if session_key is None or session_key in display:
            continue
        if _is_maintenance_run(run):
            continue
        display[session_key] = run
    return display


def _last_message_preview(container: AppContainer, *, session_key: str) -> str | None:
    try:
        items = container.require(AppKey.SESSION_SERVICE).list_items(
            ListSessionItemsInput(
                session_key=session_key,
            ),
        )
    except SessionNotFoundError:
        return None
    for item in reversed(items):
        preview = _item_preview_text(SessionItemDTO.from_entity(item))
        if preview is not None:
            return preview
    return None


def _item_preview_text(item: SessionItemDTO) -> str | None:
    maintenance_kind = item.metadata.get("maintenance_kind")
    if isinstance(maintenance_kind, str) and maintenance_kind.strip():
        return None
    blocks = content_blocks_from_payload(item.content_payload)
    text_content = extract_text_content(blocks if blocks else item.content_payload)
    if text_content is not None and text_content.strip():
        return _normalize_preview_text(text_content)
    return None


def _conversation_title(container: AppContainer, *, session_key: str) -> str | None:
    session = container.require(AppKey.SESSION_SERVICE).get_session(session_key)
    explicit_title = _normalize_preview_text(session.origin.label)
    if explicit_title is not None:
        return _truncate_title(explicit_title)
    metadata_title = session.metadata.get("thread_title")
    if isinstance(metadata_title, str):
        normalized_metadata_title = _normalize_preview_text(metadata_title)
        if normalized_metadata_title is not None:
            return _truncate_title(normalized_metadata_title)
    try:
        items = container.require(AppKey.SESSION_SERVICE).list_items(
            ListSessionItemsInput(
                session_key=session_key,
            ),
        )
    except SessionNotFoundError:
        return None
    fallback_title: str | None = None
    for item in items:
        if item.role != "user":
            continue
        text = _item_preview_text(SessionItemDTO.from_entity(item))
        if text is None:
            continue
        if fallback_title is None:
            fallback_title = text
        if _is_substantive_title_candidate(text):
            return _truncate_title(text)
    if fallback_title is not None:
        return _truncate_title(fallback_title)
    return None


def _conversation_source_label(session) -> str | None:  # noqa: ANN001
    if session.channel and session.channel.strip():
        return None
    label = _humanize_source_label(session.origin.label)
    if label is not None:
        return label
    surface = (session.origin.surface or "").strip().lower()
    if surface == "session_tool":
        return "Subagent"
    return _humanize_source_label(session.origin.surface)


def _build_conversation_summary(
    container: AppContainer,
    *,
    session_key: str,
    latest_run,  # noqa: ANN001
    display_run,  # noqa: ANN001
) -> ConversationSummaryDTO:
    session = container.require(AppKey.SESSION_SERVICE).get_session(session_key)
    binding = session.runtime_binding()
    return ConversationSummaryDTO(
        session_key=session_key,
        active_session_id=session.active_session_id,
        title=_conversation_title(container, session_key=session_key) or "New thread",
        runtime_binding=SessionRuntimeBindingPayload(
            agent_id=binding.agent_id,
        ),
        status=session.status,
        source_label=_conversation_source_label(session),
        channel=session.channel,
        chat_type=session.chat_type,
        latest_run_id=latest_run.id if latest_run is not None else None,
        latest_run_status=latest_run.status.value if latest_run is not None else None,
        latest_run_stage=latest_run.stage.value if latest_run is not None else None,
        display_run_id=display_run.id if display_run is not None else None,
        display_run_status=display_run.status.value if display_run is not None else None,
        display_run_stage=display_run.stage.value if display_run is not None else None,
        last_message_preview=_last_message_preview(container, session_key=session_key),
        created_at=format_datetime_utc(session.created_at),
        updated_at=format_datetime_utc(session.updated_at),
    )


def _list_conversation_summaries(
    container: AppContainer,
) -> list[ConversationSummaryDTO]:
    items: list[ConversationSummaryDTO] = []
    run_query = _run_query_port(container)
    latest_by_session = _latest_run_by_session_key(run_query)
    display_by_session = _display_run_by_session_key(run_query)
    for session_key, latest_run in latest_by_session.items():
        try:
            items.append(
                _build_conversation_summary(
                    container,
                    session_key=session_key,
                    latest_run=latest_run,
                    display_run=display_by_session.get(session_key),
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


@router.get("/conversations/{session_key}", response_model=ConversationResponse)
def get_conversation(
    session_key: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ConversationResponse:
    run_query = _run_query_port(container)
    latest_run = _latest_run_by_session_key(run_query).get(session_key)
    try:
        container.require(AppKey.SESSION_SERVICE).get_session(session_key)
        dto = _build_conversation_summary(
            container,
            session_key=session_key,
            latest_run=latest_run,
            display_run=_display_run_by_session_key(run_query).get(session_key),
        )
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return ConversationResponse.from_dto(dto)


@router.get(
    "/conversations/{session_key}/runs",
    response_model=list[OrchestrationRunResponse],
)
def list_conversation_runs(
    session_key: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[OrchestrationRunResponse]:
    try:
        container.require(AppKey.SESSION_SERVICE).get_session(session_key)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None

    runs = [
        run
        for run in _run_query_port(container).list_runs()
        if run.session_key == session_key
    ]
    runs.sort(key=lambda item: item.created_at, reverse=True)
    return [
        OrchestrationRunResponse.from_dto(OrchestrationRunDTO.from_entity(run))
        for run in runs
    ]


@router.get(
    "/conversations/{session_key}/messages",
    response_model=list[SessionItemResponse],
    response_model_exclude_none=True,
)
def list_conversation_messages(
    session_key: str,
    container: Annotated[AppContainer, Depends(get_container)],
    limit: Annotated[int | None, Query(ge=1)] = None,
    active_session_only: Annotated[bool, Query()] = False,
    include_archived: Annotated[bool, Query()] = False,
    after_sequence_no: Annotated[int | None, Query(ge=0)] = None,
    before_sequence_no: Annotated[int | None, Query(ge=1)] = None,
) -> list[SessionItemResponse]:
    try:
        items = container.require(AppKey.SESSION_SERVICE).list_items(
            ListSessionItemsInput(
                session_key=session_key,
                limit=limit,
                active_session_only=active_session_only,
                after_sequence_no=after_sequence_no,
                before_sequence_no=before_sequence_no,
            ),
        )
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    if not include_archived:
        items = tuple(item for item in items if not _session_item_is_archived(item))
    return [SessionItemResponse.from_dto(SessionItemDTO.from_entity(item)) for item in items]


def _session_item_is_archived(item) -> bool:  # noqa: ANN001
    return bool(item.metadata.get("archived_by_compaction_run_id"))
