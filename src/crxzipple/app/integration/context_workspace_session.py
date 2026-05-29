"""Session context tree adapter.

This module lives in app integration because it maps Session-owned application
facts into Context Workspace node handles without making either module import
the other module's internals.
"""

from __future__ import annotations

from crxzipple.modules.context_workspace.application import (
    ContextChildrenRequest,
)
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextEstimate,
    ContextNodeSeed,
    ContextNodeState,
)
from crxzipple.modules.session.application import (
    ListSessionInstancesInput,
    ListSessionMessagesInput,
    SessionApplicationService,
)
from crxzipple.modules.session.domain import (
    SessionMessage,
    SessionMessageVisibility,
    SessionNotFoundError,
)
from crxzipple.shared.content_blocks import describe_content_for_text_fallback
from crxzipple.shared.time import format_datetime_utc


class SessionContextNodeProvider:
    owner = "session"

    def __init__(
        self,
        session_service: SessionApplicationService,
        *,
        recent_limit: int = 8,
    ) -> None:
        self._session_service = session_service
        self._recent_limit = max(int(recent_limit), 1)

    def children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        if request.node.id == "session.current":
            return self._current_session_children(request)
        if request.node.id == "session.messages.recent":
            return self._recent_message_children(request)
        if request.node.id.startswith("session.messages.older"):
            return self._older_message_children(request)
        if request.node.id == "session.history.folded":
            return self._archived_range_children(request)
        if request.node.id.startswith("session.history.archived."):
            return self._archived_message_children(request)
        return ()

    def _current_session_children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        session_key = request.workspace.session_key
        try:
            session = self._session_service.get_session(session_key)
            instances = self._session_service.list_instances(
                ListSessionInstancesInput(session_key=session_key),
            )
            recent_messages = self._session_service.list_messages(
                ListSessionMessagesInput(
                    session_key=session_key,
                    active_session_only=True,
                    include_archived=False,
                    limit=self._recent_limit,
                ),
            )
            active_messages = self._session_service.list_messages(
                ListSessionMessagesInput(
                    session_key=session_key,
                    active_session_only=True,
                    include_archived=False,
                ),
            )
            all_messages = self._session_service.list_messages(
                ListSessionMessagesInput(
                    session_key=session_key,
                    active_session_only=False,
                    include_archived=True,
                ),
            )
        except SessionNotFoundError:
            return ()

        active_message_count = len(active_messages)
        active_instance = next(
            (item for item in instances if item.id == session.active_session_id),
            None,
        )
        seeds: list[ContextNodeSeed] = []
        if active_instance is not None:
            seeds.append(
                ContextNodeSeed(
                    node_id="session.instance.current",
                    parent_id="session.current",
                    owner="session",
                    kind="session_instance",
                    title="Active Instance",
                    summary=(
                        f"{active_instance.kind.value} instance "
                        f"#{active_instance.sequence_no} is {active_instance.status}."
                    ),
                    state=ContextNodeState(collapsed=False, loaded=True),
                    actions=_BASIC_ACTIONS,
                    owner_ref={
                        "session_key": session_key,
                        "session_id": active_instance.id,
                        "sequence_no": active_instance.sequence_no,
                        "status": active_instance.status,
                    },
                    estimate=ContextEstimate(text_chars=96, text_tokens=24),
                    display_order=10,
                    metadata={
                        "opened_at": format_datetime_utc(active_instance.opened_at),
                        "closed_at": (
                            format_datetime_utc(active_instance.closed_at)
                            if active_instance.closed_at is not None
                            else None
                        ),
                    },
                ),
            )

        if recent_messages:
            first_sequence = recent_messages[0].sequence_no
            last_sequence = recent_messages[-1].sequence_no
            seeds.append(
                ContextNodeSeed(
                    node_id="session.messages.recent",
                    parent_id="session.current",
                    owner="session",
                    kind="session_message_range",
                    title="Recent Messages",
                    summary=(
                        f"{len(recent_messages)} recent messages in the active "
                        f"instance, sequences {first_sequence}-{last_sequence}."
                    ),
                    actions=_BASIC_ACTIONS,
                    owner_ref={
                        "session_key": session_key,
                        "session_id": session.active_session_id,
                        "from_sequence_no": first_sequence,
                        "to_sequence_no": last_sequence,
                        "limit": self._recent_limit,
                    },
                    estimate=_messages_estimate(tuple(recent_messages)),
                    display_order=20,
                    metadata={"message_count": len(recent_messages)},
                ),
            )
            older_count = max(active_message_count - len(recent_messages), 0)
            if older_count > 0:
                seeds.append(
                    _older_chunk_seed(
                        parent_id="session.current",
                        before_sequence_no=first_sequence,
                        count=older_count,
                        limit=self._recent_limit,
                        display_order=25,
                    ),
                )

        archived_count = sum(
            1
            for message in all_messages
            if message.visibility is SessionMessageVisibility.ARCHIVED
        )
        if archived_count > 0:
            seeds.append(
                ContextNodeSeed(
                    node_id="session.history.folded",
                    parent_id="session.current",
                    owner="session",
                    kind="session_history",
                    title="Folded History",
                    summary=(
                        f"{archived_count} archived messages are available "
                        "as folded history."
                    ),
                    actions=_BASIC_ACTIONS,
                    owner_ref={
                        "session_key": session_key,
                        "archived_count": archived_count,
                    },
                    estimate=ContextEstimate(text_chars=80, text_tokens=20),
                    display_order=30,
                ),
            )

        compaction_summary = _compaction_summary(session.metadata)
        if compaction_summary:
            seeds.append(
                ContextNodeSeed(
                    node_id="session.compaction.summary",
                    parent_id="session.current",
                    owner="session",
                    kind="session_summary",
                    title="Compaction Summary",
                    summary=_truncate(compaction_summary, 240),
                    state=ContextNodeState(collapsed=False, loaded=True),
                    actions=_BASIC_ACTIONS,
                    owner_ref={
                        "session_key": session_key,
                        "metadata_key": "compaction_summary",
                    },
                    estimate=_text_estimate(compaction_summary),
                    display_order=40,
                ),
            )
        return tuple(seeds)

    def _recent_message_children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        session_key = request.workspace.session_key
        owner_ref = request.node.owner_ref
        after_sequence_no = _optional_int(owner_ref.get("from_sequence_no"))
        before_sequence_no = _optional_int(owner_ref.get("to_sequence_no"))
        try:
            messages = self._session_service.list_messages(
                ListSessionMessagesInput(
                    session_key=session_key,
                    active_session_only=True,
                    include_archived=False,
                    after_sequence_no=(
                        after_sequence_no - 1 if after_sequence_no is not None else None
                    ),
                    before_sequence_no=(
                        before_sequence_no + 1 if before_sequence_no is not None else None
                    ),
                    limit=self._recent_limit,
                ),
            )
        except SessionNotFoundError:
            return ()
        return tuple(
            _message_node_seed(message, parent_id=request.node.id)
            for message in messages
        )

    def _older_message_children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        session_key = request.workspace.session_key
        owner_ref = request.node.owner_ref
        before_sequence_no = _optional_int(owner_ref.get("before_sequence_no"))
        limit = _optional_int(owner_ref.get("limit")) or self._recent_limit
        try:
            messages = self._session_service.list_messages(
                ListSessionMessagesInput(
                    session_key=session_key,
                    active_session_only=True,
                    include_archived=False,
                    before_sequence_no=before_sequence_no,
                    limit=limit,
                ),
            )
        except SessionNotFoundError:
            return ()
        seeds = [
            _message_node_seed(message, parent_id=request.node.id)
            for message in messages
        ]
        if messages:
            first_sequence_no = messages[0].sequence_no
            remaining_count = max(first_sequence_no - 1, 0)
            if remaining_count > 0:
                seeds.insert(
                    0,
                    _older_chunk_seed(
                        parent_id=request.node.id,
                        before_sequence_no=first_sequence_no,
                        count=remaining_count,
                        limit=limit,
                        display_order=first_sequence_no - 1,
                    ),
                )
        return tuple(seeds)

    def _archived_range_children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        session_key = request.workspace.session_key
        try:
            messages = self._session_service.list_messages(
                ListSessionMessagesInput(
                    session_key=session_key,
                    active_session_only=False,
                    include_archived=True,
                ),
            )
        except SessionNotFoundError:
            return ()
        archived_messages = tuple(
            message
            for message in messages
            if message.visibility is SessionMessageVisibility.ARCHIVED
        )
        ranges: list[ContextNodeSeed] = []
        display_order = 10
        for session_id, session_messages in _messages_by_session(archived_messages):
            for chunk in _chunks(session_messages, self._recent_limit):
                first_sequence_no = chunk[0].sequence_no
                last_sequence_no = chunk[-1].sequence_no
                ranges.append(
                    ContextNodeSeed(
                        node_id=(
                            "session.history.archived."
                            f"{_node_part(session_id)}."
                            f"{first_sequence_no}.{last_sequence_no}"
                        ),
                        parent_id=request.node.id,
                        owner="session",
                        kind="session_message_range",
                        title=(
                            "Archived Messages "
                            f"{first_sequence_no}-{last_sequence_no}"
                        ),
                        summary=(
                            f"{len(chunk)} archived messages from session "
                            f"{session_id}, sequences "
                            f"{first_sequence_no}-{last_sequence_no}."
                        ),
                        actions=_BASIC_ACTIONS,
                        owner_ref={
                            "session_key": session_key,
                            "session_id": session_id,
                            "from_sequence_no": first_sequence_no,
                            "to_sequence_no": last_sequence_no,
                            "message_count": len(chunk),
                            "visibility": SessionMessageVisibility.ARCHIVED.value,
                        },
                        estimate=_messages_estimate(chunk),
                        display_order=display_order,
                        metadata={
                            "message_count": len(chunk),
                            "visibility": SessionMessageVisibility.ARCHIVED.value,
                        },
                    ),
                )
                display_order += 10
        return tuple(ranges)

    def _archived_message_children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        session_key = request.workspace.session_key
        owner_ref = request.node.owner_ref
        session_id = _optional_text(owner_ref.get("session_id"))
        from_sequence_no = _optional_int(owner_ref.get("from_sequence_no"))
        to_sequence_no = _optional_int(owner_ref.get("to_sequence_no"))
        if session_id is None or from_sequence_no is None or to_sequence_no is None:
            return ()
        try:
            messages = self._session_service.list_messages(
                ListSessionMessagesInput(
                    session_key=session_key,
                    active_session_only=False,
                    include_archived=True,
                    after_sequence_no=from_sequence_no - 1,
                    before_sequence_no=to_sequence_no + 1,
                ),
            )
        except SessionNotFoundError:
            return ()
        return tuple(
            _message_node_seed(message, parent_id=request.node.id)
            for message in messages
            if message.session_id == session_id
            and message.visibility is SessionMessageVisibility.ARCHIVED
        )


_BASIC_ACTIONS = (
    ContextAction.EXPAND,
    ContextAction.COLLAPSE,
    ContextAction.PIN,
    ContextAction.UNPIN,
    ContextAction.ESTIMATE,
)


def _older_chunk_seed(
    *,
    parent_id: str,
    before_sequence_no: int,
    count: int,
    limit: int,
    display_order: int,
) -> ContextNodeSeed:
    return ContextNodeSeed(
        node_id=f"session.messages.older.before.{before_sequence_no}",
        parent_id=parent_id,
        owner="session",
        kind="session_message_range",
        title="Older Messages",
        summary=(
            f"{count} older messages are available before sequence "
            f"{before_sequence_no}."
        ),
        actions=_BASIC_ACTIONS,
        owner_ref={
            "before_sequence_no": before_sequence_no,
            "count": count,
            "limit": limit,
        },
        estimate=ContextEstimate(text_chars=80, text_tokens=20),
        display_order=display_order,
        metadata={"message_count": count},
    )


def _message_node_seed(message: SessionMessage, *, parent_id: str) -> ContextNodeSeed:
    preview = _message_preview(message)
    return ContextNodeSeed(
        node_id=f"session.message.{message.session_id}.{message.sequence_no}",
        parent_id=parent_id,
        owner="session",
        kind="session_message",
        title=f"{message.sequence_no}. {message.role}",
        summary=preview,
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=(ContextAction.PIN, ContextAction.UNPIN, ContextAction.ESTIMATE),
        owner_ref={
            "session_key": message.session_key,
            "session_id": message.session_id,
            "message_id": message.id,
            "sequence_no": message.sequence_no,
            "role": message.role,
            "kind": message.kind.value,
            "visibility": message.visibility.value,
        },
        estimate=_text_estimate(preview),
        display_order=message.sequence_no,
        metadata={
            "created_at": format_datetime_utc(message.created_at),
            "source_kind": message.source_kind,
            "source_id": message.source_id,
        },
    )


def _message_preview(message: SessionMessage) -> str:
    text = describe_content_for_text_fallback(message.content_payload)
    return _truncate(text.replace("\n", " "), 320)


def _messages_estimate(messages: tuple[SessionMessage, ...]) -> ContextEstimate:
    total = ContextEstimate()
    for message in messages:
        total = total.plus(_text_estimate(_message_preview(message)))
    return total


def _text_estimate(text: str) -> ContextEstimate:
    normalized = text or ""
    return ContextEstimate(
        text_chars=len(normalized),
        text_tokens=max((len(normalized) + 3) // 4, 1) if normalized else 0,
    )


def _truncate(value: str, limit: int) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)].rstrip() + "..."


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return None


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _messages_by_session(
    messages: tuple[SessionMessage, ...],
) -> tuple[tuple[str, tuple[SessionMessage, ...]], ...]:
    grouped: dict[str, list[SessionMessage]] = {}
    for message in messages:
        grouped.setdefault(message.session_id, []).append(message)
    return tuple(
        (
            session_id,
            tuple(sorted(items, key=lambda item: item.sequence_no)),
        )
        for session_id, items in sorted(grouped.items())
    )


def _chunks(
    messages: tuple[SessionMessage, ...],
    size: int,
) -> tuple[tuple[SessionMessage, ...], ...]:
    chunk_size = max(int(size), 1)
    return tuple(
        messages[index : index + chunk_size]
        for index in range(0, len(messages), chunk_size)
    )


def _node_part(value: str) -> str:
    return "".join(
        char if char.isalnum() or char in {"-", "_"} else "_"
        for char in value
    )


def _compaction_summary(metadata: dict[str, object]) -> str | None:
    candidates = (
        metadata.get("compaction_summary"),
        metadata.get("last_compaction_summary"),
        metadata.get("summary"),
    )
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


__all__ = ["SessionContextNodeProvider"]
