from __future__ import annotations

import pytest
from sqlalchemy import Index
from sqlalchemy.exc import IntegrityError

from crxzipple.app.keys import AppKey
from crxzipple.modules.session.application import (
    AppendSessionItemInput,
    EnsureSessionInput,
    SessionApplicationService,
)
from crxzipple.modules.session.domain import (
    SessionInstance,
    SessionItem,
    SessionItemKind,
    SessionKind,
)
from crxzipple.modules.session.infrastructure.persistence.models import (
    SessionInstanceModel,
    SessionItemModel,
)
from tests.unit.support import SqliteTestHarness


def _index_by_name(indexes: set[Index], name: str) -> Index:
    for index in indexes:
        if index.name == name:
            return index
    raise AssertionError(f"Expected index {name!r} to exist.")


def test_session_item_sequence_index_is_unique_per_segment() -> None:
    index = _index_by_name(
        SessionItemModel.__table__.indexes,
        "ix_session_items_session_sequence",
    )

    assert index.unique is True
    assert [column.name for column in index.columns] == [
        "session_key",
        "session_id",
        "sequence_no",
    ]


def test_session_instance_sequence_index_is_unique_per_session() -> None:
    index = _index_by_name(
        SessionInstanceModel.__table__.indexes,
        "ix_session_instances_session_sequence",
    )

    assert index.unique is True
    assert [column.name for column in index.columns] == [
        "session_key",
        "sequence_no",
    ]


def test_sqlite_rejects_duplicate_session_item_sequence_in_segment() -> None:
    harness = SqliteTestHarness()
    try:
        container = harness.build_runtime_container()
        service: SessionApplicationService = container.require(AppKey.SESSION_SERVICE)
        uow_factory = container.require(AppKey.UNIT_OF_WORK_FACTORY)
        session = service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
                workspace="/tmp/session-sequence-contract",
            ),
        )
        first = service.append_item(
            AppendSessionItemInput(
                session_key=session.id,
                kind=SessionItemKind.USER_MESSAGE,
                role="user",
                content_payload={"text": "first"},
            ),
        )
        duplicate = SessionItem(
            id="duplicate-session-item-sequence",
            session_key=session.id,
            session_id=session.active_session_id,
            sequence_no=first.sequence_no,
            kind=SessionItemKind.USER_MESSAGE,
            role="user",
            content_payload={"text": "duplicate"},
        )

        with uow_factory() as uow:
            uow.session_items.add(duplicate)
            with pytest.raises(IntegrityError):
                uow.commit()
            uow.rollback()
    finally:
        harness.close()


def test_sqlite_rejects_stale_concurrent_append_sequence_race() -> None:
    harness = SqliteTestHarness()
    try:
        container = harness.build_runtime_container()
        service: SessionApplicationService = container.require(AppKey.SESSION_SERVICE)
        uow_factory = container.require(AppKey.UNIT_OF_WORK_FACTORY)
        session = service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
                workspace="/tmp/session-concurrent-sequence-contract",
            ),
        )

        with uow_factory() as first_uow, uow_factory() as second_uow:
            first_next_sequence = (
                first_uow.session_items.max_sequence_no(
                    session_key=session.id,
                    session_id=session.active_session_id,
                )
                + 1
            )
            second_next_sequence = (
                second_uow.session_items.max_sequence_no(
                    session_key=session.id,
                    session_id=session.active_session_id,
                )
                + 1
            )
            assert first_next_sequence == second_next_sequence == 1

            first_uow.session_items.add(
                SessionItem(
                    id="concurrent-first-session-item",
                    session_key=session.id,
                    session_id=session.active_session_id,
                    sequence_no=first_next_sequence,
                    kind=SessionItemKind.USER_MESSAGE,
                    role="user",
                    content_payload={"text": "first"},
                ),
            )
            second_uow.session_items.add(
                SessionItem(
                    id="concurrent-second-session-item",
                    session_key=session.id,
                    session_id=session.active_session_id,
                    sequence_no=second_next_sequence,
                    kind=SessionItemKind.USER_MESSAGE,
                    role="user",
                    content_payload={"text": "second"},
                ),
            )

            first_uow.commit()
            with pytest.raises(IntegrityError):
                second_uow.commit()
            second_uow.rollback()
    finally:
        harness.close()


def test_sqlite_rejects_duplicate_session_instance_sequence() -> None:
    harness = SqliteTestHarness()
    try:
        container = harness.build_runtime_container()
        service: SessionApplicationService = container.require(AppKey.SESSION_SERVICE)
        uow_factory = container.require(AppKey.UNIT_OF_WORK_FACTORY)
        session = service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
                workspace="/tmp/session-instance-sequence-contract",
            ),
        )
        duplicate = SessionInstance(
            id="duplicate-session-instance-sequence",
            session_key=session.id,
            sequence_no=1,
            kind=SessionKind.MAIN,
        )

        with uow_factory() as uow:
            uow.session_instances.add(duplicate)
            with pytest.raises(IntegrityError):
                uow.commit()
            uow.rollback()
    finally:
        harness.close()


def test_sqlite_rejects_stale_concurrent_segment_rotation_sequence_race() -> None:
    harness = SqliteTestHarness()
    try:
        container = harness.build_runtime_container()
        service: SessionApplicationService = container.require(AppKey.SESSION_SERVICE)
        uow_factory = container.require(AppKey.UNIT_OF_WORK_FACTORY)
        session = service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
                workspace="/tmp/session-segment-rotation-contract",
            ),
        )

        with uow_factory() as first_uow, uow_factory() as second_uow:
            first_next_sequence = (
                first_uow.session_instances.max_sequence_no(session_key=session.id) + 1
            )
            second_next_sequence = (
                second_uow.session_instances.max_sequence_no(session_key=session.id) + 1
            )
            assert first_next_sequence == second_next_sequence == 2

            first_uow.session_instances.add(
                SessionInstance(
                    id="concurrent-first-next-segment",
                    session_key=session.id,
                    sequence_no=first_next_sequence,
                    kind=SessionKind.MAIN,
                ),
            )
            second_uow.session_instances.add(
                SessionInstance(
                    id="concurrent-second-next-segment",
                    session_key=session.id,
                    sequence_no=second_next_sequence,
                    kind=SessionKind.MAIN,
                ),
            )

            first_uow.commit()
            with pytest.raises(IntegrityError):
                second_uow.commit()
            second_uow.rollback()
    finally:
        harness.close()
