from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from crxzipple.modules.session.domain.entities import Session, SessionInstance
from crxzipple.modules.session.domain.value_objects import SessionItem, SessionItemKind
from crxzipple.shared.time import format_datetime_utc as _format_datetime_utc


@dataclass(frozen=True, slots=True)
class SessionItemsBundle:
    session: Session
    items: tuple[SessionItem, ...]


@dataclass(frozen=True, slots=True)
class SessionReplayWindow:
    session: Session
    items: tuple[SessionItem, ...]
    active_session_only: bool = False
    from_sequence_no: int | None = None
    to_sequence_no: int | None = None
    item_count: int = 0
    protocol_call_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SessionItemRange:
    session: Session
    session_id: str
    items: tuple[SessionItem, ...]
    from_sequence_no: int | None = None
    to_sequence_no: int | None = None
    item_count: int = 0


@dataclass(frozen=True, slots=True)
class SessionSegmentHandle:
    session_id: str
    sequence_no: int
    kind: str
    status: str
    summary_text: str | None = None
    summary_item_id: str | None = None
    archived_item_count: int | None = None
    archived_through_item_sequence_no: int | None = None
    opened_at: str | None = None
    closed_at: str | None = None


@dataclass(frozen=True, slots=True)
class SessionSegmentHandles:
    session: Session
    active_session_id: str
    handles: tuple[SessionSegmentHandle, ...]


@dataclass(frozen=True, slots=True)
class SessionContextFrontier:
    session: Session
    active_instance: SessionInstance
    instances: tuple[SessionInstance, ...]
    active_items: tuple[SessionItem, ...]
    from_sequence_no: int | None = None
    to_sequence_no: int | None = None
    active_item_count: int = 0
    protocol_call_ids: tuple[str, ...] = ()
    segment_handles: tuple[SessionSegmentHandle, ...] = ()


def build_replay_window(
    bundle: SessionItemsBundle,
    *,
    active_session_only: bool,
) -> SessionReplayWindow:
    items = tuple(bundle.items)
    from_sequence_no, to_sequence_no = sequence_bounds(items)
    return SessionReplayWindow(
        session=bundle.session,
        items=items,
        active_session_only=active_session_only,
        from_sequence_no=from_sequence_no,
        to_sequence_no=to_sequence_no,
        item_count=len(items),
        protocol_call_ids=session_protocol_call_ids(items),
    )


def build_item_range(
    *,
    session: Session,
    session_id: str,
    items: Iterable[SessionItem],
    from_sequence_no: int | None,
    to_sequence_no: int | None,
) -> SessionItemRange:
    item_tuple = tuple(items)
    actual_from_sequence_no, actual_to_sequence_no = sequence_bounds(item_tuple)
    return SessionItemRange(
        session=session,
        session_id=session_id,
        items=item_tuple,
        from_sequence_no=actual_from_sequence_no
        if actual_from_sequence_no is not None
        else from_sequence_no,
        to_sequence_no=actual_to_sequence_no
        if actual_to_sequence_no is not None
        else to_sequence_no,
        item_count=len(item_tuple),
    )


def build_context_frontier(
    *,
    session: Session,
    active_instance: SessionInstance,
    instances: Iterable[SessionInstance],
    active_items: Iterable[SessionItem],
    historical_instance_limit: int | None,
) -> SessionContextFrontier:
    instance_tuple = tuple(instances)
    active_item_tuple = tuple(active_items)
    from_sequence_no, to_sequence_no = sequence_bounds(active_item_tuple)
    historical_instances = tuple(
        instance for instance in instance_tuple if instance.id != active_instance.id
    )
    if historical_instance_limit is not None:
        historical_instances = historical_instances[-historical_instance_limit:]
    return SessionContextFrontier(
        session=session,
        active_instance=active_instance,
        instances=instance_tuple,
        active_items=active_item_tuple,
        from_sequence_no=from_sequence_no,
        to_sequence_no=to_sequence_no,
        active_item_count=len(active_item_tuple),
        protocol_call_ids=session_protocol_call_ids(active_item_tuple),
        segment_handles=tuple(
            build_segment_handle(instance)
            for instance in (*historical_instances, active_instance)
        ),
    )


def build_segment_handle(instance: SessionInstance) -> SessionSegmentHandle:
    segment = instance.metadata.get("segment")
    segment_payload = segment if isinstance(segment, dict) else {}
    return SessionSegmentHandle(
        session_id=instance.id,
        sequence_no=instance.sequence_no,
        kind=str(segment_payload.get("kind") or instance.kind.value),
        status=instance.status,
        summary_text=_optional_str(segment_payload.get("summary_text")),
        summary_item_id=_optional_str(segment_payload.get("summary_item_id")),
        archived_item_count=_optional_int(segment_payload.get("archived_item_count")),
        archived_through_item_sequence_no=_optional_int(
            segment_payload.get("archived_through_item_sequence_no"),
        ),
        opened_at=_format_datetime_utc(instance.opened_at),
        closed_at=(
            _format_datetime_utc(instance.closed_at)
            if instance.closed_at is not None
            else None
        ),
    )


def sequence_bounds(items: Iterable[SessionItem]) -> tuple[int | None, int | None]:
    sequence_numbers = [item.sequence_no for item in items]
    if not sequence_numbers:
        return None, None
    return min(sequence_numbers), max(sequence_numbers)


def session_protocol_call_ids(items: Iterable[SessionItem]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            item.call_id
            for item in items
            if item.call_id
            and item.kind in {SessionItemKind.TOOL_CALL, SessionItemKind.TOOL_RESULT}
        ),
    )


def _optional_str(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
