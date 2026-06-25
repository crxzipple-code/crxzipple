from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from crxzipple.modules.session.domain.value_objects import (
    SessionItem,
    SessionItemKind,
    SessionItemPhase,
)


@dataclass(frozen=True, slots=True)
class AppendSessionItemInput:
    session_key: str
    kind: SessionItemKind
    content_payload: dict[str, object] = field(default_factory=dict)
    role: str | None = None
    phase: SessionItemPhase = SessionItemPhase.UNKNOWN
    source_module: str | None = None
    source_kind: str | None = None
    source_id: str | None = None
    provider_item_id: str | None = None
    provider_item_type: str | None = None
    call_id: str | None = None
    tool_name: str | None = None
    model_visible: bool = True
    user_visible: bool = True
    chat_visible: bool = True
    trace_visible: bool = True
    metadata: dict[str, object] = field(default_factory=dict)
    session_id: str | None = None


@dataclass(frozen=True, slots=True)
class AppendSessionItemsInput:
    items: tuple[AppendSessionItemInput, ...] = field(default_factory=tuple)


def build_session_item(
    data: AppendSessionItemInput,
    *,
    session_key: str,
    session_id: str,
    sequence_no: int,
) -> SessionItem:
    return SessionItem(
        id=str(uuid4()),
        session_key=session_key,
        session_id=session_id,
        sequence_no=sequence_no,
        kind=data.kind,
        role=data.role,
        phase=data.phase,
        content_payload=dict(data.content_payload),
        source_module=data.source_module,
        source_kind=data.source_kind,
        source_id=data.source_id,
        provider_item_id=data.provider_item_id,
        provider_item_type=data.provider_item_type,
        call_id=data.call_id,
        tool_name=data.tool_name,
        model_visible=data.model_visible,
        user_visible=data.user_visible,
        chat_visible=data.chat_visible,
        trace_visible=data.trace_visible,
        metadata=dict(data.metadata),
    )
