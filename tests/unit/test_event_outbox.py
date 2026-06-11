from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from crxzipple.core.db import Base
from crxzipple.modules.events.domain import EventOutboxRecord, EventOutboxStatus
from crxzipple.modules.events.infrastructure.outbox_publisher import (
    EventOutboxPublisherService,
)
from crxzipple.modules.events.infrastructure.persistence.models import (
    EventOutboxRecordModel,
)
from crxzipple.modules.events.infrastructure.persistence.repositories import (
    SqlAlchemyEventOutboxRepository,
)
from crxzipple.shared.domain import AggregateRoot, Event
from crxzipple.shared.infrastructure.event_bus import InMemoryEventBus
from crxzipple.shared.infrastructure.sqlalchemy_uow import SqlAlchemyUnitOfWork


@dataclass(kw_only=True)
class DummyAggregate(AggregateRoot[str]):
    pass


class FailingEventBus:
    def publish(self, _event: Event) -> None:
        raise RuntimeError("publisher unavailable")


def _session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[EventOutboxRecordModel.__table__])
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def test_uow_writes_domain_events_to_outbox_in_transaction() -> None:
    session_factory = _session_factory()
    aggregate = DummyAggregate(id="aggregate-1")
    event = Event(
        name="dummy.fact.recorded",
        payload={"aggregate_id": aggregate.id},
        trace={"trace_id": "trace-1"},
    )
    aggregate.record_event(event)

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.collect(aggregate)
        uow.commit()

    assert aggregate.pending_events() == []
    with session_factory() as session:
        repo = SqlAlchemyEventOutboxRepository(session)
        record = repo.get(event.id)

    assert record is not None
    assert record.status is EventOutboxStatus.PENDING
    assert record.event_name == "dummy.fact.recorded"
    assert record.topic == event.topic
    assert record.to_event() == event


def test_outbox_repository_lists_failed_records_when_retry_is_due() -> None:
    session_factory = _session_factory()
    event = Event(name="dummy.retry.requested", payload={"value": 1})

    with session_factory() as session:
        repo = SqlAlchemyEventOutboxRepository(session)
        record = repo.get(event.id)
        assert record is None
        record = EventOutboxRecord.from_event(event)
        record.mark_failed("temporary failure", retry_delay_seconds=0)
        repo.add(record)
        session.commit()

    with session_factory() as session:
        repo = SqlAlchemyEventOutboxRepository(session)
        due = repo.list_publishable(limit=10)

    assert [record.id for record in due] == [event.id]
    assert due[0].status is EventOutboxStatus.FAILED
    assert due[0].attempts == 1


def test_outbox_repository_claims_publishable_records_with_expiring_lease() -> None:
    session_factory = _session_factory()
    event = Event(name="dummy.claim.requested", payload={"value": 4})

    with session_factory() as session:
        repo = SqlAlchemyEventOutboxRepository(session)
        repo.add(EventOutboxRecord.from_event(event))
        session.commit()

    now = datetime.now(timezone.utc)
    with session_factory() as session:
        repo = SqlAlchemyEventOutboxRepository(session)
        claimed = repo.claim_publishable(
            publisher_id="publisher-a",
            claim_seconds=30,
            now=now,
        )
        session.commit()

    assert [record.id for record in claimed] == [event.id]
    assert claimed[0].status is EventOutboxStatus.PUBLISHING
    assert claimed[0].publisher_id == "publisher-a"
    assert claimed[0].claim_expires_at == now + timedelta(seconds=30)

    with session_factory() as session:
        repo = SqlAlchemyEventOutboxRepository(session)
        assert (
            repo.claim_publishable(
                publisher_id="publisher-b",
                claim_seconds=30,
                now=now,
            )
            == []
        )

    with session_factory() as session:
        repo = SqlAlchemyEventOutboxRepository(session)
        reclaimed = repo.claim_publishable(
            publisher_id="publisher-b",
            claim_seconds=30,
            now=now + timedelta(seconds=31),
        )
        session.commit()

    assert [record.id for record in reclaimed] == [event.id]
    assert reclaimed[0].status is EventOutboxStatus.PUBLISHING
    assert reclaimed[0].publisher_id == "publisher-b"


def test_event_outbox_publisher_publishes_and_marks_records_delivered() -> None:
    session_factory = _session_factory()
    event_bus = InMemoryEventBus()
    event = Event(name="dummy.publish.requested", payload={"value": 2})

    with session_factory() as session:
        repo = SqlAlchemyEventOutboxRepository(session)
        repo.add(EventOutboxRecord.from_event(event))
        session.commit()

    result = EventOutboxPublisherService(
        session_factory=session_factory,
        event_bus=event_bus,
    ).publish_available(limit=10)

    assert result.published == 1
    assert result.failed == 0
    assert event_bus.published_events == [event]
    with session_factory() as session:
        repo = SqlAlchemyEventOutboxRepository(session)
        record = repo.get(event.id)

    assert record is not None
    assert record.status is EventOutboxStatus.DELIVERED
    assert record.delivered_at is not None
    assert record.publisher_id is None
    assert record.claim_expires_at is None


def test_event_outbox_publisher_restart_retries_failed_records() -> None:
    session_factory = _session_factory()
    event = Event(name="dummy.restart.requested", payload={"value": 3})

    with session_factory() as session:
        repo = SqlAlchemyEventOutboxRepository(session)
        repo.add(EventOutboxRecord.from_event(event))
        session.commit()

    failed_result = EventOutboxPublisherService(
        session_factory=session_factory,
        event_bus=FailingEventBus(),
        retry_base_delay_seconds=0,
    ).publish_available(limit=10)

    assert failed_result.published == 0
    assert failed_result.failed == 1
    with session_factory() as session:
        repo = SqlAlchemyEventOutboxRepository(session)
        failed_record = repo.get(event.id)

    assert failed_record is not None
    assert failed_record.status is EventOutboxStatus.FAILED
    assert failed_record.attempts == 1

    restarted_bus = InMemoryEventBus()
    restarted_result = EventOutboxPublisherService(
        session_factory=session_factory,
        event_bus=restarted_bus,
    ).publish_available(limit=10)

    assert restarted_result.published == 1
    assert restarted_result.failed == 0
    assert restarted_bus.published_events == [event]
    with session_factory() as session:
        repo = SqlAlchemyEventOutboxRepository(session)
        delivered_record = repo.get(event.id)

    assert delivered_record is not None
    assert delivered_record.status is EventOutboxStatus.DELIVERED
    assert delivered_record.attempts == 1
