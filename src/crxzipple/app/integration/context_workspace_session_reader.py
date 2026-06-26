"""Session owner read helpers for Context Workspace adapters."""

from __future__ import annotations

from typing import Any, Protocol

from crxzipple.app.integration.context_workspace_session_segment_values import (
    is_archived_transcript_entry as _is_archived_transcript_entry,
)
from crxzipple.modules.session.application import (
    ListSessionInstancesInput,
    ListSessionItemsInput,
)
from crxzipple.modules.session.domain import Session, SessionInstance, SessionItem


class SessionContextService(Protocol):
    def get_session(self, session_key: str) -> Session:
        ...

    def list_instances(
        self,
        data: ListSessionInstancesInput,
    ) -> list[SessionInstance]:
        ...

    def list_items(
        self,
        data: ListSessionItemsInput,
    ) -> list[SessionItem]:
        ...


def get_session_and_instances(
    service: SessionContextService,
    session_key: str,
) -> tuple[Session, list[SessionInstance]]:
    return (
        service.get_session(session_key),
        service.list_instances(ListSessionInstancesInput(session_key=session_key)),
    )


def find_session_instance(
    instances: list[SessionInstance],
    instance_id: str | None,
) -> SessionInstance | None:
    if instance_id is None:
        return None
    return next((item for item in instances if item.id == instance_id), None)


def active_transcript_items_or_messages(
    service: SessionContextService,
    session_key: str,
) -> list[Any]:
    return active_transcript_range_items_or_messages(
        service,
        session_key,
        after_sequence_no=None,
        before_sequence_no=None,
    )


def active_transcript_range_items_or_messages(
    service: SessionContextService,
    session_key: str,
    *,
    after_sequence_no: int | None,
    before_sequence_no: int | None,
) -> list[Any]:
    list_items = getattr(service, "list_items", None)
    if list_items is None:
        return []
    return list(
        item
        for item in list_items(
            ListSessionItemsInput(
                session_key=session_key,
                active_session_only=True,
                after_sequence_no=(
                    after_sequence_no - 1 if after_sequence_no is not None else None
                ),
                before_sequence_no=(
                    before_sequence_no + 1 if before_sequence_no is not None else None
                ),
            ),
        )
        if not _is_archived_transcript_entry(item)
    )


def transcript_items_or_messages(
    service: SessionContextService,
    session_key: str,
    *,
    active_session_only: bool,
    after_sequence_no: int | None = None,
    before_sequence_no: int | None = None,
) -> list[Any]:
    list_items = getattr(service, "list_items", None)
    if list_items is None:
        return []
    return list(
        list_items(
            ListSessionItemsInput(
                session_key=session_key,
                active_session_only=active_session_only,
                after_sequence_no=after_sequence_no,
                before_sequence_no=before_sequence_no,
            ),
        ),
    )


__all__ = [
    "SessionContextService",
    "active_transcript_items_or_messages",
    "active_transcript_range_items_or_messages",
    "find_session_instance",
    "get_session_and_instances",
    "transcript_items_or_messages",
]
