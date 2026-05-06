from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from datetime import datetime, timezone
from threading import Condition
import tempfile
import time
import unittest
from types import SimpleNamespace

from crxzipple.modules.events import (
    EventAddress,
    EventContractRegistry,
    EventSelector,
    EventRouteContract,
    EventRouteSubscription,
    EventRoutingApplicationService,
    EventTarget,
    EventTopicContract,
    EventTopicWatch,
    FileBackedEventsBackend,
    EventsApplicationService,
    InMemoryEventsBackend,
    RedisEventsBackend,
)
from crxzipple.modules.dispatch.application import (
    CreateDispatchTaskInput,
    DispatchWakeupObserver,
    EnqueueDispatchTaskInput,
    dispatch_event_observers,
    dispatch_wakeup_topic,
)
from crxzipple.modules.orchestration.application import (
    RUN_OBSERVATION_EVENT_NAMES,
    RunObservationObserver,
    RuntimeObservationObserver,
    SessionMessageObservationObserver,
    ToolRunObservationObserver,
    orchestration_event_definitions,
    orchestration_event_observers,
    orchestration_runtime_observation_topic,
    turn_session_topic,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    OrchestrationExecutorLeaseStatus,
    OrchestrationQueuePolicy,
    OrchestrationRunStatus,
)
from crxzipple.shared import (
    EventDefinition,
    EventDefinitionField,
    EventDefinitionRegistry,
    EventObserver,
    ORCHESTRATION_RUN_LLM_TEXT_DELTA_EVENT,
    EventSurface,
    ORCHESTRATION_RUN_MESSAGE_APPENDED_EVENT,
    ORCHESTRATION_RUN_TOOL_UPDATED_EVENT,
    ORCHESTRATION_RUNTIME_OBSERVATION_SOURCE_EVENT_NAMES,
    ORCHESTRATION_RUNTIME_STATUS_EVENT,
    SESSION_MESSAGE_APPENDED_SOURCE_EVENT,
    TOOL_RUN_OBSERVATION_SOURCE_EVENT_NAMES,
)
from crxzipple.modules.session.domain import (
    SessionMessage,
    SessionMessageKind,
    SessionMessageVisibility,
)
from crxzipple.shared.domain.events import Event, named_event_topic
from crxzipple.shared.event_contracts import TOOL_LLM_EVENT_NAMES
from crxzipple.shared.infrastructure.event_bus import InMemoryEventBus
from tests.unit.support import SqliteTestHarness


def _published_named_events(backend: object) -> tuple[Event, ...]:
    return tuple(
        event
        for event in getattr(backend, "published_events", ())
        if isinstance(event, Event) and bool(event.name)
    )


def _published_topic_events(backend: object) -> tuple[Event, ...]:
    return tuple(
        event
        for event in getattr(backend, "published_events", ())
        if isinstance(event, Event) and not event.name
    )


class FakeRedisClient:
    def __init__(self) -> None:
        self._streams: dict[str, list[tuple[str, dict[str, str]]]] = defaultdict(list)
        self._stream_counters: dict[str, int] = defaultdict(int)
        self._values: dict[str, tuple[str, float | None]] = {}
        self._condition = Condition()

    def xadd(
        self,
        name: str,
        fields: dict[str, str],
        id: str = "*",
    ) -> str:
        del id
        with self._condition:
            self._stream_counters[name] += 1
            cursor = f"{self._stream_counters[name]}-0"
            self._streams[name].append((cursor, dict(fields)))
            self._condition.notify_all()
            return cursor

    def xread(
        self,
        streams: dict[str, str],
        count: int | None = None,
        block: int | None = None,
    ) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        deadline = (
            time.monotonic() + max(block or 0, 0) / 1000.0
            if block is not None
            else None
        )
        with self._condition:
            while True:
                matches: list[tuple[str, list[tuple[str, dict[str, str]]]]] = []
                for name, last_cursor in streams.items():
                    records = [
                        (cursor, dict(fields))
                        for cursor, fields in self._streams[name]
                        if self._compare_cursors(cursor, last_cursor) > 0
                    ]
                    if count is not None:
                        records = records[:count]
                    if records:
                        matches.append((name, records))
                if matches:
                    return matches
                if deadline is None:
                    return []
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return []
                self._condition.wait(timeout=remaining)

    def xrange(
        self,
        name: str,
        *,
        min: str = "-",
        max: str = "+",
        count: int | None = None,
    ) -> list[tuple[str, dict[str, str]]]:
        with self._condition:
            records = [
                (cursor, dict(fields))
                for cursor, fields in self._streams[name]
                if self._matches_min(cursor, min) and self._matches_max(cursor, max)
            ]
        if count is not None:
            records = records[:count]
        return records

    def xrevrange(
        self,
        name: str,
        *,
        max: str = "+",
        min: str = "-",
        count: int | None = None,
    ) -> list[tuple[str, dict[str, str]]]:
        records = list(reversed(self.xrange(name, min=min, max=max, count=None)))
        if count is not None:
            records = records[:count]
        return records

    def set(
        self,
        name: str,
        value: str,
        *,
        nx: bool = False,
        ex: int | None = None,
    ) -> bool:
        with self._condition:
            self._expire_values()
            if nx and name in self._values:
                return False
            expiry = time.monotonic() + ex if ex is not None else None
            self._values[name] = (value, expiry)
            return True

    def get(self, name: str) -> str | None:
        with self._condition:
            self._expire_values()
            value = self._values.get(name)
            if value is None:
                return None
            return value[0]

    def _expire_values(self) -> None:
        now = time.monotonic()
        expired = [
            key
            for key, (_, expiry) in self._values.items()
            if expiry is not None and expiry <= now
        ]
        for key in expired:
            self._values.pop(key, None)

    @staticmethod
    def _parse_cursor(cursor: str) -> tuple[int, int]:
        if not cursor or "-" not in cursor:
            return (0, 0)
        left, right = cursor.split("-", 1)
        return (int(left), int(right))

    @classmethod
    def _compare_cursors(cls, left: str, right: str) -> int:
        left_cursor = cls._parse_cursor(left)
        right_cursor = cls._parse_cursor(right)
        if left_cursor == right_cursor:
            return 0
        return 1 if left_cursor > right_cursor else -1

    @classmethod
    def _matches_min(cls, cursor: str, minimum: str) -> bool:
        if minimum == "-":
            return True
        if minimum.startswith("("):
            return cls._compare_cursors(cursor, minimum[1:]) > 0
        return cls._compare_cursors(cursor, minimum) >= 0

    @classmethod
    def _matches_max(cls, cursor: str, maximum: str) -> bool:
        if maximum == "+":
            return True
        if maximum.startswith("("):
            return cls._compare_cursors(cursor, maximum[1:]) < 0
        return cls._compare_cursors(cursor, maximum) <= 0


def _wait_until(predicate, *, timeout_seconds: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


class EventsModuleTestCase(unittest.TestCase):
    def test_event_definition_registry_describes_registered_events(self) -> None:
        registry = EventDefinitionRegistry(
            definitions=(
                EventDefinition(
                    definition_id="demo.event",
                    owner="demo",
                    event_name="demo.event",
                    description="Demo event definition.",
                    topics=("demo.topic.{id}",),
                    fields=(
                        EventDefinitionField(
                            "event_name",
                            "Stable event name.",
                            "string",
                            True,
                        ),
                        EventDefinitionField(
                            "run_id",
                            "Owning run identifier.",
                            "string",
                        ),
                    ),
                ),
            ),
            surfaces=(
                EventSurface(
                    surface_id="demo.surface",
                    owner="demo",
                    description="Demo surface.",
                    definition_ids=("demo.event",),
                    topics=("demo.topic.{id}",),
                    consumers=("demo consumer",),
                ),
            ),
            observers=(
                EventObserver(
                    observer_id="demo.observer",
                    owner="demo",
                    description="Demo observer.",
                    source_event_names=("demo.source",),
                    output_definition_ids=("demo.event",),
                    handlers=("DemoObserver.handle",),
                ),
            ),
        )

        payload = registry.to_payload()

        self.assertEqual(payload["definition_count"], 1)
        self.assertEqual(payload["surface_count"], 1)
        self.assertEqual(payload["observer_count"], 1)
        self.assertEqual(payload["definitions"][0]["definition_id"], "demo.event")
        self.assertEqual(payload["definitions"][0]["durability"], "persistent")
        self.assertEqual(payload["definitions"][0]["publication_mode"], "direct")
        self.assertEqual(payload["definitions"][0]["source_event_names"], [])
        self.assertEqual(payload["definitions"][0]["fields"][0]["field_path"], "event_name")
        self.assertEqual(payload["surfaces"][0]["surface_id"], "demo.surface")
        self.assertEqual(payload["surfaces"][0]["definition_ids"], ["demo.event"])
        self.assertEqual(payload["observers"][0]["observer_id"], "demo.observer")
        self.assertEqual(payload["observers"][0]["source_event_names"], ["demo.source"])
        self.assertEqual(payload["observers"][0]["output_definition_ids"], ["demo.event"])
        self.assertIsNotNone(registry.get("demo.event"))
        self.assertIsNotNone(registry.get_by_event_name("demo.event"))
        self.assertIsNotNone(registry.get_observer("demo.observer"))
        self.assertEqual(
            [surface.surface_id for surface in registry.list_surfaces_for_event_name("demo.event")],
            ["demo.surface"],
        )
        self.assertEqual(
            [observer.observer_id for observer in registry.list_observers_for_event_name("demo.source")],
            ["demo.observer"],
        )

    def test_event_definition_registry_covers_tool_and_llm_lifecycle_events(self) -> None:
        registry = EventDefinitionRegistry()
        expected_event_names = (
            "tool.run.created",
            "tool.run.queued",
            "tool.run.dispatching",
            "tool.run.started",
            "tool.run.succeeded",
            "tool.run.failed",
            "tool.run.requeued",
            "tool.run.cancel_requested",
            "tool.run.cancelled",
            "tool.run.timed_out",
            "tool.assignment.created",
            "tool.assignment.started",
            "tool.assignment.succeeded",
            "tool.assignment.failed",
            "tool.assignment.cancelled",
            "tool.assignment.expired",
            "tool.worker.registered",
            "tool.worker.recovered",
            "tool.worker.capabilities_updated",
            "tool.worker.stale",
            "tool.worker.pruned",
            "llm.invocation_started",
            "llm.invocation_succeeded",
            "llm.invocation_failed",
            "llm.profile_registered",
            "llm.profile_updated",
        )

        self.assertEqual(TOOL_LLM_EVENT_NAMES, expected_event_names)
        for event_name in expected_event_names:
            with self.subTest(event_name=event_name):
                definition = registry.get_by_event_name(event_name)
                self.assertIsNotNone(definition)
                assert definition is not None
                self.assertEqual(definition.definition_id, event_name)
                self.assertEqual(definition.event_name, event_name)
                self.assertEqual(definition.durability, "persistent")
                self.assertEqual(definition.publication_mode, "direct")
                self.assertEqual(definition.topics, (named_event_topic(event_name),))
                self.assertIn(definition.owner, {"tool", "llm"})
                field_paths = {field.field_path for field in definition.fields}
                self.assertIn("event_name", field_paths)
                if event_name.startswith("tool.run."):
                    self.assertEqual(definition.owner, "tool")
                    self.assertIn("run_id", field_paths)
                    self.assertIn("tool_id", field_paths)
                elif event_name.startswith("tool.assignment."):
                    self.assertEqual(definition.owner, "tool")
                    self.assertIn("assignment_id", field_paths)
                    self.assertIn("worker_id", field_paths)
                elif event_name.startswith("tool.worker."):
                    self.assertEqual(definition.owner, "tool")
                    self.assertIn("worker_id", field_paths)
                elif event_name.startswith("llm.invocation_"):
                    self.assertEqual(definition.owner, "llm")
                    self.assertIn("invocation_id", field_paths)
                    self.assertIn("llm_id", field_paths)
                elif event_name.startswith("llm.profile_"):
                    self.assertEqual(definition.owner, "llm")
                    self.assertIn("llm_id", field_paths)

    def test_event_contract_registry_describes_topics_and_routes(self) -> None:
        registry = EventContractRegistry(
            topic_contracts=(
                EventTopicContract(
                    contract_id="demo.source",
                    topic_pattern="demo.source.{id}",
                    owner="demo",
                    description="Demo source topic.",
                    kinds=("fact",),
                    producers=("producer",),
                    consumers=("router",),
                ),
            ),
            route_contracts=(
                EventRouteContract(
                    contract_id="demo.source.to.target",
                    source_topic_pattern="demo.source.{id}",
                    target_topic_pattern="demo.target.{id}",
                    owner="demo",
                    description="Demo route.",
                    observer="DemoRouter.route",
                    source_kinds=("fact",),
                    target_kind="observe",
                ),
            ),
        )

        payload = registry.to_payload()

        self.assertEqual(payload["topic_count"], 1)
        self.assertEqual(payload["route_count"], 1)
        self.assertEqual(payload["topics"][0]["contract_id"], "demo.source")
        self.assertEqual(payload["routes"][0]["target_kind"], "observe")
        self.assertIsNotNone(registry.get_topic_contract("demo.source"))
        self.assertIsNotNone(registry.get_route_contract("demo.source.to.target"))

    def test_event_contract_registry_matches_concrete_topics(self) -> None:
        registry = EventContractRegistry(
            topic_contracts=(
                EventTopicContract(
                    contract_id="turn.session",
                    topic_pattern="turn.session.{session_key}",
                    owner="orchestration",
                    description="Session topic.",
                ),
            ),
            route_contracts=(
                EventRouteContract(
                    contract_id="turn.session.to.web.observe",
                    source_topic_pattern="turn.session.{session_key}",
                    target_topic_pattern="channel.observe.web.connection.{connection_id}",
                    owner="web",
                    description="Route session observations to web.",
                    observer="WebChannelRuntimeService.route_pending_observe",
                ),
            ),
        )

        topic_matches = registry.match_topic_contracts(
            "turn.session.agent:assistant:deck-1",
        )
        source_matches = registry.match_route_contracts(
            "turn.session.agent:assistant:deck-1",
            direction="source",
        )
        target_matches = registry.match_route_contracts(
            "channel.observe.web.connection.conn-1",
            direction="target",
        )

        self.assertEqual(topic_matches[0].contract.contract_id, "turn.session")
        self.assertEqual(
            topic_matches[0].variables["session_key"],
            "agent:assistant:deck-1",
        )
        self.assertEqual(
            source_matches[0].contract.contract_id,
            "turn.session.to.web.observe",
        )
        self.assertEqual(target_matches[0].variables["connection_id"], "conn-1")

    def test_event_contract_registry_rejects_duplicate_contract_ids(self) -> None:
        registry = EventContractRegistry()
        contract = EventTopicContract(
            contract_id="demo.source",
            topic_pattern="demo.source",
            owner="demo",
            description="Demo source topic.",
        )

        registry.register_topic(contract)

        with self.assertRaises(ValueError):
            registry.register_topic(contract)

    def test_events_service_lists_subscription_cursors_by_source_topic(self) -> None:
        backend = InMemoryEventsBackend()
        service = EventsApplicationService(backend)

        service.set_subscription_cursor(
            "sub-a",
            source_topic="topic.a",
            cursor="7",
        )
        service.set_subscription_cursor(
            "sub-b",
            source_topic="topic.b",
            cursor="3",
        )

        states = service.list_subscription_cursors(source_topic="topic.a")

        self.assertEqual(len(states), 1)
        self.assertEqual(states[0].subscription_id, "sub-a")
        self.assertEqual(states[0].cursor, "7")

    def test_event_address_uses_generic_fields_with_legacy_aliases(self) -> None:
        target = EventAddress(
            address="conn-1",
            address_kind="connection",
            labels={"region": "local"},
            runtime="web-runtime-1",
            transport="web",
            account="default",
            conversation="conv-1",
            connection="conn-1",
        )

        self.assertEqual(target.runtime, "web-runtime-1")
        self.assertEqual(target.transport, "web")
        self.assertEqual(target.account, "default")
        self.assertEqual(target.conversation, "conv-1")
        self.assertEqual(target.connection, "conn-1")
        self.assertEqual(target.address, "conn-1")
        self.assertEqual(target.address_kind, "connection")
        self.assertEqual(target.labels["region"], "local")
        self.assertEqual(target.runtime_id, "web-runtime-1")
        self.assertEqual(target.channel_type, "web")
        self.assertEqual(target.channel_account_id, "default")
        self.assertEqual(target.conversation_id, "conv-1")
        self.assertEqual(target.connection_id, "conn-1")

        payload = target.to_payload()
        self.assertEqual(payload["address"], "conn-1")
        self.assertEqual(payload["address_kind"], "connection")
        self.assertEqual(payload["labels"]["transport"], "web")
        self.assertEqual(payload["runtime"], "web-runtime-1")
        self.assertEqual(payload["runtime_id"], "web-runtime-1")
        restored = EventAddress.from_payload(
            {
                "runtime_id": "lark-runtime-1",
                "channel_type": "lark",
                "channel_account_id": "default",
                "conversation_id": "chat-1",
                "connection_id": "conn-2",
            },
        )
        self.assertEqual(restored.runtime, "lark-runtime-1")
        self.assertEqual(restored.transport, "lark")
        self.assertEqual(restored.account, "default")
        self.assertEqual(restored.conversation, "chat-1")
        self.assertEqual(restored.connection, "conn-2")

    def test_named_and_topic_events_expose_common_event_name_and_time_accessors(self) -> None:
        source_event = Event(name="demo.source", payload={"ok": True})
        topic_event = Event(
            topic="runtime.demo",
            kind="fact",
            payload={"event_name": "demo.runtime", "ok": True},
        )
        unnamed_topic_event = Event(topic="runtime.unnamed", kind="fact")

        self.assertEqual(source_event.event_name, "demo.source")
        self.assertEqual(source_event.payload["ok"], True)
        self.assertEqual(source_event.occurred_at.tzinfo, timezone.utc)
        self.assertEqual(source_event.topic, named_event_topic("demo.source"))
        self.assertEqual(source_event.selector.topic, named_event_topic("demo.source"))

        self.assertEqual(topic_event.event_name, "demo.runtime")
        self.assertEqual(topic_event.payload["ok"], True)
        self.assertEqual(topic_event.occurred_at, topic_event.created_at)
        self.assertEqual(topic_event.selector.topic, "runtime.demo")

        self.assertIsNone(unnamed_topic_event.event_name)
        legacy = EventTarget(channel_type="web", connection_id="conn-legacy")
        self.assertEqual(legacy.transport, "web")
        self.assertEqual(legacy.connection, "conn-legacy")

    def test_in_memory_events_backend_supports_named_and_topic_events(self) -> None:
        backend = InMemoryEventsBackend()
        service = EventsApplicationService(backend)
        handled_domain: list[str] = []
        handled_topics: list[str] = []

        service.subscribe(
            EventSelector.topic_only(named_event_topic("demo.event")),
            lambda event: handled_domain.append(event.name),
        )
        service.subscribe(
            EventSelector.topic_only("runtime.demo"),
            lambda envelope: handled_topics.append(envelope.topic),
        )

        service.publish(Event(name="demo.event", payload={"ok": True}))
        service.publish(
            Event(
                topic="runtime.demo",
                kind="fact",
                target=EventTarget(channel_type="web", connection_id="conn-1"),
                payload={"ok": True},
            ),
        )

        self.assertEqual(handled_domain, ["demo.event"])
        self.assertEqual(handled_topics, ["runtime.demo"])
        self.assertEqual([event.name for event in _published_named_events(backend)], ["demo.event"])
        self.assertEqual([envelope.topic for envelope in _published_topic_events(backend)], ["runtime.demo"])

    def test_events_service_lists_visible_topics(self) -> None:
        backend = InMemoryEventsBackend()
        service = EventsApplicationService(backend)

        service.publish(
            Event(
                topic="runtime.demo",
                kind="fact",
                ordering_key="run-1",
                payload={
                    "event_name": "demo.event",
                    "value": 42,
                },
            ),
        )
        service.publish(
            Event(
                topic="turn.session.agent:demo:main",
                kind="fact",
                payload={"event_name": "orchestration.run.queued"},
            ),
        )

        self.assertEqual(
            service.list_event_topics(),
            ("runtime.demo", "turn.session.agent:demo:main"),
        )

    def test_events_service_reads_recent_topic_records(self) -> None:
        backend = InMemoryEventsBackend()
        service = EventsApplicationService(backend)

        for step in range(4):
            service.publish(
                Event(
                    topic="runtime.demo",
                    kind="fact",
                    payload={"event_name": "demo.event", "step": step},
                ),
            )

        self.assertEqual(
            [record.envelope.payload["step"] for record in service.read_recent_event_topic("runtime.demo", limit=2)],
            [2, 3],
        )

    def test_in_memory_events_backend_can_wait_for_topic_activity(self) -> None:
        backend = InMemoryEventsBackend()
        service = EventsApplicationService(backend)

        cursor = service.snapshot_event_topic("runtime.demo")
        service.publish(
            Event(topic="runtime.demo", payload={"ok": True}),
        )

        self.assertTrue(
            service.wait_for_event_topic(
                "runtime.demo",
                after_cursor=cursor,
                timeout_seconds=0.01,
            ),
        )
        matched = service.wait_for_event_topics(
            (
                EventTopicWatch("runtime.other", cursor),
                EventTopicWatch("runtime.demo", cursor),
            ),
            timeout_seconds=0.01,
        )
        self.assertEqual(matched, EventTopicWatch("runtime.demo", cursor))

    def test_in_memory_events_backend_can_read_topic_records_after_cursor(self) -> None:
        backend = InMemoryEventsBackend()
        service = EventsApplicationService(backend)

        cursor = service.snapshot_event_topic("runtime.demo")
        service.publish(
            Event(topic="runtime.demo", payload={"order": 1}),
        )
        service.publish(
            Event(topic="runtime.demo", payload={"order": 2}),
        )

        records = service.read_event_topic(
            "runtime.demo",
            after_cursor=cursor,
            limit=10,
        )
        self.assertEqual([record.cursor for record in records], ["1", "2"])
        self.assertEqual([record.envelope.payload["order"] for record in records], [1, 2])

    def test_event_routing_service_observes_source_topic_to_target_topic(self) -> None:
        backend = InMemoryEventsBackend()
        service = EventsApplicationService(backend)
        router = EventRoutingApplicationService(events_service=service)

        source_cursor = service.snapshot_event_topic("source.topic")
        service.publish(
            Event(
                topic="source.topic",
                kind="fact",
                payload={"event_name": "demo.source", "value": 42},
            ),
        )

        result = router.route_subscription(
            EventRouteSubscription(
                subscription_id="demo-subscription",
                source_topic="source.topic",
                after_cursor=source_cursor,
                limit=10,
            ),
            lambda record: Event(
                topic="target.topic",
                kind="observe",
                target=EventTarget(connection_id="conn-1"),
                ordering_key="conn-1",
                dedupe_key=f"{record.envelope.id}:conn-1",
                payload={
                    "event_name": record.envelope.payload["event_name"],
                    "source_topic": record.envelope.topic,
                    "source_cursor": record.cursor,
                    "fact": dict(record.envelope.payload),
                },
            ),
        )

        self.assertEqual(result.read_count, 1)
        self.assertEqual(result.published_count, 1)
        self.assertEqual(result.last_cursor, "1")
        self.assertEqual(result.last_event_name, "demo.source")
        target_records = service.read_event_topic("target.topic", limit=10)
        self.assertEqual(len(target_records), 1)
        self.assertEqual(target_records[0].envelope.kind, "observe")
        self.assertEqual(target_records[0].envelope.payload["fact"]["value"], 42)

    def test_event_routing_service_owns_managed_subscription_cursor(self) -> None:
        backend = InMemoryEventsBackend()
        service = EventsApplicationService(backend)
        router = EventRoutingApplicationService(events_service=service)

        router.seed_subscription(
            EventRouteSubscription(
                subscription_id="managed-subscription",
                source_topic="managed.source",
            ),
            cursor=service.snapshot_event_topic("managed.source"),
        )
        service.publish(
            Event(
                topic="managed.source",
                kind="live",
                payload={"event_name": "managed.one"},
            ),
        )

        subscription = EventRouteSubscription(
            subscription_id="managed-subscription",
            source_topic="managed.source",
            limit=10,
        )
        first = router.route_managed_subscription(
            subscription,
            lambda record: Event(
                topic="managed.target",
                kind="live",
                payload={
                    "event_name": record.envelope.payload["event_name"],
                    "source_cursor": record.cursor,
                },
            ),
        )
        second = router.route_managed_subscription(
            subscription,
            lambda record: Event(
                topic="managed.target",
                kind="live",
                payload={
                    "event_name": record.envelope.payload["event_name"],
                    "source_cursor": record.cursor,
                },
            ),
        )

        self.assertEqual(first.read_count, 1)
        self.assertEqual(first.published_count, 1)
        self.assertEqual(second.read_count, 0)
        state = service.get_subscription_cursor(
            "managed-subscription",
            source_topic="managed.source",
        )
        self.assertIsNotNone(state)
        assert state is not None
        self.assertEqual(state.cursor, "1")
        self.assertEqual(len(service.read_event_topic("managed.target", limit=10)), 1)

    def test_file_backed_events_backend_persists_subscription_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            service = EventsApplicationService(FileBackedEventsBackend(tempdir))

            service.set_subscription_cursor(
                "file-subscription",
                source_topic="file.source",
                cursor="12",
            )

            reopened = EventsApplicationService(FileBackedEventsBackend(tempdir))
            state = reopened.get_subscription_cursor(
                "file-subscription",
                source_topic="file.source",
            )
            self.assertIsNotNone(state)
            assert state is not None
            self.assertEqual(state.cursor, "12")
            self.assertIsNone(
                reopened.get_subscription_cursor(
                    "file-subscription",
                    source_topic="other.source",
                ),
            )

    def test_file_backed_events_backend_publish_many_batches_topic_records(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            service = EventsApplicationService(FileBackedEventsBackend(tempdir))
            handled_event_ids: list[str] = []
            service.subscribe(
                EventSelector.topic_only("runtime.demo"),
                lambda event: handled_event_ids.append(event.id),
            )
            first = Event(
                topic="runtime.demo",
                kind="fact",
                dedupe_key="tool-run-1:terminal",
                payload={"order": 1},
            )
            second = Event(
                topic="runtime.demo",
                kind="fact",
                payload={"order": 2},
            )
            duplicate = Event(
                topic="runtime.demo",
                kind="fact",
                dedupe_key="tool-run-1:terminal",
                payload={"order": 99},
            )

            service.publish_many((first, second, duplicate))

            records = service.read_event_topic("runtime.demo", limit=10)
            self.assertEqual([record.cursor for record in records], ["1", "2"])
            self.assertEqual(
                [record.envelope.payload["order"] for record in records],
                [1, 2],
            )
            self.assertEqual(handled_event_ids, [first.id, second.id])

            reopened = EventsApplicationService(FileBackedEventsBackend(tempdir))
            reopened_records = reopened.read_event_topic("runtime.demo", limit=10)
            self.assertEqual(
                [record.envelope.payload["order"] for record in reopened_records],
                [1, 2],
            )

    def test_redis_events_backend_supports_local_named_and_topic_events(self) -> None:
        backend = RedisEventsBackend(
            client=FakeRedisClient(),
            key_prefix="test:events",
            block_ms=20,
        )
        service = EventsApplicationService(backend)
        handled_domain: list[str] = []
        handled_topics: list[str] = []

        service.subscribe(
            EventSelector.topic_only(named_event_topic("demo.event")),
            lambda event: handled_domain.append(event.name),
        )
        service.subscribe(
            EventSelector.topic_only("runtime.demo"),
            lambda envelope: handled_topics.append(envelope.topic),
        )

        service.publish(Event(name="demo.event", payload={"ok": True}))
        service.publish(
            Event(
                topic="runtime.demo",
                kind="fact",
                target=EventTarget(channel_type="web", connection_id="conn-1"),
                payload={"ok": True},
            ),
        )

        self.assertEqual(handled_domain, ["demo.event"])
        self.assertEqual(handled_topics, ["runtime.demo"])
        self.assertEqual([event.name for event in _published_named_events(backend)], ["demo.event"])
        self.assertEqual([envelope.topic for envelope in _published_topic_events(backend)], ["runtime.demo"])

    def test_redis_events_backend_can_wait_and_read_topic_records(self) -> None:
        backend = RedisEventsBackend(
            client=FakeRedisClient(),
            key_prefix="test:events",
            block_ms=20,
        )
        service = EventsApplicationService(backend)

        cursor = service.snapshot_event_topic("runtime.demo")
        service.publish(
            Event(topic="runtime.demo", payload={"order": 1}),
        )
        service.publish(
            Event(topic="runtime.demo", payload={"order": 2}),
        )

        self.assertTrue(
            service.wait_for_event_topic(
                "runtime.demo",
                after_cursor=cursor,
                timeout_seconds=0.1,
            ),
        )
        matched = service.wait_for_event_topics(
            (
                EventTopicWatch("runtime.other", "0-0"),
                EventTopicWatch("runtime.demo", cursor),
            ),
            timeout_seconds=0.1,
        )
        self.assertEqual(matched, EventTopicWatch("runtime.demo", cursor))
        records = service.read_event_topic(
            "runtime.demo",
            after_cursor=cursor,
            limit=10,
        )
        self.assertEqual([record.cursor for record in records], ["1-0", "2-0"])
        self.assertEqual([record.envelope.payload["order"] for record in records], [1, 2])

    def test_redis_events_backend_persists_subscription_cursor(self) -> None:
        service = EventsApplicationService(
            RedisEventsBackend(
                client=FakeRedisClient(),
                key_prefix="test:events",
                block_ms=20,
            ),
        )

        service.set_subscription_cursor(
            "redis-subscription",
            source_topic="redis.source",
            cursor="2-0",
        )

        state = service.get_subscription_cursor(
            "redis-subscription",
            source_topic="redis.source",
        )
        self.assertIsNotNone(state)
        assert state is not None
        self.assertEqual(state.cursor, "2-0")
        self.assertIsNone(
            service.get_subscription_cursor(
                "redis-subscription",
                source_topic="other.source",
            ),
        )

    def test_redis_events_backend_propagates_source_and_topic_events_across_backends(self) -> None:
        client = FakeRedisClient()
        publisher = EventsApplicationService(
            RedisEventsBackend(client=client, key_prefix="test:events", block_ms=20),
        )
        subscriber = EventsApplicationService(
            RedisEventsBackend(client=client, key_prefix="test:events", block_ms=20),
        )
        handled_domain: list[str] = []
        handled_topics: list[str] = []

        subscriber.subscribe(
            EventSelector.topic_only(named_event_topic("demo.event")),
            lambda event: handled_domain.append(event.name),
        )
        subscriber.subscribe(
            EventSelector.topic_only("runtime.demo"),
            lambda envelope: handled_topics.append(envelope.topic),
        )

        publisher.publish(Event(name="demo.event", payload={"ok": True}))
        publisher.publish(
            Event(
                topic="runtime.demo",
                kind="broadcast",
                payload={"ok": True},
            ),
        )

        self.assertTrue(_wait_until(lambda: handled_domain == ["demo.event"]))
        self.assertTrue(_wait_until(lambda: handled_topics == ["runtime.demo"]))

    def test_dispatch_wake_subscriber_publishes_runtime_wakeup_envelope(self) -> None:
        backend = InMemoryEventsBackend()
        service = EventsApplicationService(backend)
        subscriber = DispatchWakeupObserver(events_service=service)

        subscriber.observe_task_queued(
            Event(
                name="dispatch.task.queued",
                payload={
                    "task_id": "task-1",
                    "owner_kind": "orchestration_run",
                    "owner_id": "run-1",
                    "lane_key": "agent:main",
                },
            ),
        )

        published_envelopes = _published_topic_events(backend)
        self.assertEqual(len(published_envelopes), 1)
        envelope = published_envelopes[0]
        self.assertEqual(envelope.topic, dispatch_wakeup_topic("orchestration_run"))
        self.assertEqual(envelope.kind, "command")
        self.assertEqual(envelope.payload["owner_id"], "run-1")

    def test_turn_event_subscriber_publishes_run_and_session_topics(self) -> None:
        backend = InMemoryEventsBackend()
        service = EventsApplicationService(backend)

        class _FakeOrchestrationService:
            def get_run(self, run_id: str):
                self.last_run_id = run_id
                return SimpleNamespace(
                    id=run_id,
                    session_key="agent:demo:main",
                    active_session_id="sess-1",
                    status=SimpleNamespace(value="running"),
                    stage=SimpleNamespace(value="llm"),
                    current_step=2,
                    waiting_reason=None,
                    pending_tool_run_ids=(),
                    metadata={
                        "pending_approval_request": {
                            "request_id": "req-1",
                            "effect_id": "effect-1",
                            "label": "Need approval",
                            "reason": "network",
                            "tool_ids": ["tool-1"],
                            "created_at": "2026-04-13T00:00:00+00:00",
                        },
                        "last_approval_resolution": {
                            "request_id": "req-1",
                            "decision": "approved",
                            "resolved_at": "2026-04-13T00:00:01+00:00",
                        },
                    },
                    updated_at=SimpleNamespace(isoformat=lambda: "2026-04-13T00:00:00+00:00"),
                )

        run_observer = RunObservationObserver(
            events_service=service,
            run_lookup=_FakeOrchestrationService(),
        )
        message_observer = SessionMessageObservationObserver(events_service=service)
        tool_observer = ToolRunObservationObserver(
            events_service=service,
            run_lookup=_FakeOrchestrationService(),
            tool_execution_port=SimpleNamespace(
                get_tool_run=lambda run_id: SimpleNamespace(
                    id=run_id,
                    tool_id="weather.forecast",
                    status=SimpleNamespace(value="succeeded"),
                    target=SimpleNamespace(
                        mode=SimpleNamespace(value="background"),
                        strategy=SimpleNamespace(value="async"),
                        environment=SimpleNamespace(value="remote"),
                    ),
                    attempt_count=1,
                    max_attempts=3,
                    output_payload="sunny",
                    error_message=None,
                    created_at=SimpleNamespace(
                        isoformat=lambda: "2026-04-13T00:00:02+00:00"
                    ),
                    started_at=SimpleNamespace(
                        isoformat=lambda: "2026-04-13T00:00:03+00:00"
                    ),
                    completed_at=SimpleNamespace(
                        isoformat=lambda: "2026-04-13T00:00:04+00:00"
                    ),
                    invocation_context=SimpleNamespace(
                        get_str=lambda key: {
                            "run_id": "run-1",
                            "session_key": "agent:demo:main",
                        }.get(key)
                    ),
                )
            ),
        )

        run_observer.observe_run_event(
            Event(
                name="orchestration.run.completed",
                payload={"run_id": "run-1"},
            ),
        )
        message_observer.observe_message_appended(
            Event(
                name=SESSION_MESSAGE_APPENDED_SOURCE_EVENT,
                payload={
                    "message_id": "msg-1",
                    "session_key": "agent:demo:main",
                    "session_id": "sess-1",
                    "role": "user",
                    "kind": "message",
                    "source_kind": "orchestration_run",
                    "source_id": "run-1",
                    "message": {
                        "id": "msg-1",
                        "session_key": "agent:demo:main",
                        "session_id": "sess-1",
                        "sequence_no": 1,
                        "role": "user",
                        "kind": "message",
                        "content_payload": {"blocks": [{"type": "text", "text": "hello"}]},
                        "source_kind": "orchestration_run",
                        "source_id": "run-1",
                        "visibility": "default",
                        "metadata": {},
                        "created_at": "2026-04-13T00:00:00+00:00",
                    },
                },
            ),
        )
        tool_observer.observe_tool_event(
            Event(
                name="tool.run.succeeded",
                payload={"run_id": "tool-run-1", "tool_id": "weather.forecast"},
            ),
        )

        published_envelopes = _published_topic_events(backend)
        topics = [envelope.topic for envelope in published_envelopes]
        self.assertIn(turn_session_topic("agent:demo:main"), topics)
        run_envelope = next(
            item
            for item in published_envelopes
            if item.topic == turn_session_topic("agent:demo:main")
            and item.payload.get("event_name") == "orchestration.run.completed"
        )
        self.assertNotIn("llm_stream_invocation_id", run_envelope.payload)
        self.assertNotIn("llm_stream_text", run_envelope.payload)
        self.assertEqual(
            run_envelope.payload["pending_approval_request"]["request_id"],
            "req-1",
        )
        self.assertEqual(
            run_envelope.payload["last_approval_resolution"]["decision"],
            "approved",
        )
        definitions = {
            definition.event_name: definition
            for definition in orchestration_event_definitions()
        }
        observers = {
            observer.observer_id: observer
            for observer in orchestration_event_observers()
        }
        dispatch_observers = {
            observer.observer_id: observer
            for observer in dispatch_event_observers()
        }
        self.assertEqual(
            definitions["orchestration.run.completed"].publication_mode,
            "reduced",
        )
        self.assertEqual(
            definitions["orchestration.run.completed"].source_event_names,
            ("orchestration.run.completed",),
        )
        self.assertEqual(
            definitions[ORCHESTRATION_RUN_MESSAGE_APPENDED_EVENT].publication_mode,
            "translated",
        )
        self.assertEqual(
            definitions[ORCHESTRATION_RUN_LLM_TEXT_DELTA_EVENT].publication_mode,
            "direct",
        )
        self.assertEqual(
            definitions[ORCHESTRATION_RUN_TOOL_UPDATED_EVENT].publication_mode,
            "translated",
        )
        self.assertEqual(
            definitions[ORCHESTRATION_RUNTIME_STATUS_EVENT].publication_mode,
            "hydrated",
        )
        self.assertEqual(
            definitions[ORCHESTRATION_RUNTIME_STATUS_EVENT].source_event_names,
            ORCHESTRATION_RUNTIME_OBSERVATION_SOURCE_EVENT_NAMES,
        )
        self.assertEqual(
            observers["orchestration.run.observation"].output_definition_ids,
            RUN_OBSERVATION_EVENT_NAMES,
        )
        self.assertEqual(
            observers["orchestration.session.message_observation"].source_event_names,
            (SESSION_MESSAGE_APPENDED_SOURCE_EVENT,),
        )
        self.assertEqual(
            observers["orchestration.tool.observation"].source_event_names,
            TOOL_RUN_OBSERVATION_SOURCE_EVENT_NAMES,
        )
        self.assertEqual(
            observers["orchestration.runtime.observation"].source_event_names,
            ORCHESTRATION_RUNTIME_OBSERVATION_SOURCE_EVENT_NAMES,
        )
        self.assertEqual(
            dispatch_observers["dispatch.wakeup"].source_event_names,
            (
                "dispatch.task.queued",
                "dispatch.task.requeued",
                "dispatch.task.recovered",
            ),
        )
        message_envelope = next(
            item
            for item in published_envelopes
            if item.topic == turn_session_topic("agent:demo:main")
            and item.payload.get("event_name") == ORCHESTRATION_RUN_MESSAGE_APPENDED_EVENT
        )
        self.assertEqual(message_envelope.payload["message"]["id"], "msg-1")
        self.assertEqual(
            message_envelope.payload["message"]["content_payload"]["blocks"][0]["text"],
            "hello",
        )
        self.assertTrue(
            str(message_envelope.payload["message"]["created_at"]).endswith("+00:00")
        )
        tool_envelope = next(
            item
            for item in published_envelopes
            if item.topic == turn_session_topic("agent:demo:main")
            and item.payload.get("event_name") == ORCHESTRATION_RUN_TOOL_UPDATED_EVENT
        )
        self.assertEqual(tool_envelope.payload["tool_run_id"], "tool-run-1")
        self.assertEqual(tool_envelope.payload["tool_status"], "succeeded")
        self.assertEqual(tool_envelope.payload["output_payload"], "sunny")
        self.assertEqual(
            tool_envelope.payload["source_event_name"],
            "tool.run.succeeded",
        )

    def test_runtime_observation_observer_publishes_scheduler_health_snapshot(self) -> None:
        backend = InMemoryEventsBackend()
        service = EventsApplicationService(backend)

        queued_run = SimpleNamespace(
            lane_key="agent:demo:main",
            queue_policy=OrchestrationQueuePolicy.FIFO,
            priority=100,
            queued_at=datetime(2026, 4, 13, tzinfo=timezone.utc),
        )
        running_run = SimpleNamespace(lane_key="agent:demo:main")
        waiting_run = SimpleNamespace(
            lane_key=None,
            waiting_reason="waiting_on_tool",
        )

        class _FakeOrchestrationControl:
            def list_runs(self, *, status=None):
                return {
                    OrchestrationRunStatus.QUEUED: [queued_run],
                    OrchestrationRunStatus.RUNNING: [running_run],
                    OrchestrationRunStatus.WAITING: [waiting_run],
                }.get(status, [])

        class _FakeLease:
            worker_id = "executor-1"
            status = OrchestrationExecutorLeaseStatus.ONLINE
            max_inflight_assignments = 4
            inflight_assignment_count = 1
            last_heartbeat_at = datetime(2026, 4, 13, tzinfo=timezone.utc)
            lease_expires_at = datetime(2026, 4, 13, 0, 1, tzinfo=timezone.utc)
            metadata = {
                "runtime_state": {"active_assignment_count": 1},
                "runtime_metrics": {
                    "counters": [],
                    "gauges": [
                        {
                            "name": "llm.profile_limiter.active",
                            "labels": {"llm_id": "vllm.qwen3.5-35b"},
                            "value": 1.0,
                        },
                    ],
                    "timings": [],
                },
            }

            def is_expired(self, *, now=None) -> bool:
                return False

        class _ExpiredLease:
            worker_id = "executor-expired"
            status = OrchestrationExecutorLeaseStatus.ONLINE
            max_inflight_assignments = 4
            inflight_assignment_count = 0
            last_heartbeat_at = datetime(2026, 4, 12, tzinfo=timezone.utc)
            lease_expires_at = datetime(2026, 4, 12, 0, 1, tzinfo=timezone.utc)
            metadata = {
                "runtime_metrics": {
                    "counters": [],
                    "gauges": [
                        {
                            "name": "llm.profile_limiter.active",
                            "labels": {"llm_id": "stale"},
                            "value": 99.0,
                        },
                    ],
                    "timings": [],
                },
            }

            def is_expired(self, *, now=None) -> bool:
                return True

        runtime_observer = RuntimeObservationObserver(
            events_service=service,
            run_query=_FakeOrchestrationControl(),
            executor_control=SimpleNamespace(
                list_executor_leases=lambda status=None: [_ExpiredLease(), _FakeLease()]
            ),
        )

        runtime_observer.observe_runtime_event(
            Event(
                name="orchestration.executor.lease.heartbeated",
                payload={"worker_id": "executor-1"},
            ),
        )

        published_envelopes = _published_topic_events(backend)
        self.assertEqual(len(published_envelopes), 1)
        envelope = published_envelopes[0]
        self.assertEqual(envelope.topic, orchestration_runtime_observation_topic())
        self.assertEqual(envelope.payload["event_name"], ORCHESTRATION_RUNTIME_STATUS_EVENT)
        self.assertEqual(envelope.payload["source_event_name"], "orchestration.executor.lease.heartbeated")
        self.assertEqual(envelope.payload["queue"]["queued_run_count"], 1)
        self.assertEqual(envelope.payload["queue"]["running_run_count"], 1)
        self.assertEqual(envelope.payload["queue"]["waiting_run_count"], 1)
        self.assertEqual(envelope.payload["lanes"]["blocked_lane_count"], 1)
        self.assertEqual(envelope.payload["lanes"]["unlanned_active_run_count"], 1)
        self.assertEqual(envelope.payload["executor"]["lease_count"], 2)
        self.assertEqual(envelope.payload["executor"]["visible_lease_count"], 1)
        self.assertEqual(envelope.payload["executor"]["expired_lease_count"], 1)
        self.assertEqual(envelope.payload["executor"]["capacity_executor_count"], 1)
        self.assertEqual(envelope.payload["executor"]["total_available_assignment_slots"], 3)
        self.assertEqual(
            [lease["worker_id"] for lease in envelope.payload["executor"]["leases"]],
            ["executor-1"],
        )
        llm_gauges = envelope.payload["llm"]["profile_limiter_metrics"]["gauges"]
        self.assertEqual(len(llm_gauges), 1)
        self.assertEqual(llm_gauges[0]["name"], "llm.profile_limiter.active")
        self.assertEqual(llm_gauges[0]["worker_id"], "executor-1")

    def test_legacy_in_memory_event_bus_delegates_to_events_service(self) -> None:
        backend = InMemoryEventsBackend()
        service = EventsApplicationService(backend)
        bus = InMemoryEventBus(service=service)
        handled: list[str] = []

        bus.subscribe(
            EventSelector.topic_only(named_event_topic("legacy.event")),
            lambda event: handled.append(event.name),
        )
        bus.publish(Event(name="legacy.event", payload={"ok": True}))

        self.assertEqual(handled, ["legacy.event"])
        self.assertIs(bus.events_service, service)
        self.assertEqual(
            [event.event_name for event in bus.published_events if event.event_name],
            ["legacy.event"],
        )

    def test_container_exposes_events_service(self) -> None:
        harness = SqliteTestHarness()
        container = harness.build_container()
        try:
            self.assertIsNotNone(container.events_service)
            self.assertIs(container.event_bus.events_service, container.events_service)
            self.assertIsInstance(container.events_service.backend, FileBackedEventsBackend)
        finally:
            container.close()
            harness.close()

    def test_container_operations_observer_records_dispatch_enqueue_event(self) -> None:
        harness = SqliteTestHarness()
        container = harness.build_container()
        try:
            self.assertIsNotNone(container.events_service)
            container.dispatch_service.create_task(
                CreateDispatchTaskInput(
                    task_id="task-1",
                    owner_kind="orchestration_run",
                    owner_id="run-1",
                    lane_key="agent:main",
                ),
            )
            container.dispatch_service.enqueue_task(
                EnqueueDispatchTaskInput(task_id="task-1"),
            )
            assert container.operations_observer_runtime_event_service is not None
            processed_events = (
                container.operations_observer_runtime_event_service.process_available_events(
                    limit_per_subscription=10,
                )
            )
            dispatch_observation = container.operations_observation_store.get_module_observation(
                "dispatch",
            )

            self.assertGreaterEqual(processed_events, 1)
            self.assertIsNotNone(dispatch_observation)
            assert dispatch_observation is not None
            self.assertTrue(
                any(
                    event.event_name == "dispatch.task.queued"
                    and event.payload.get("owner_id") == "run-1"
                    for event in dispatch_observation.recent_events
                ),
            )
        finally:
            container.close()
            harness.close()

    def test_container_scheduler_runtime_publishes_dispatch_wakeup_envelope(self) -> None:
        harness = SqliteTestHarness()
        container = harness.build_container()
        try:
            self.assertIsNotNone(container.events_service)
            backend = container.events_service.backend
            container.dispatch_service.create_task(
                CreateDispatchTaskInput(
                    task_id="task-1",
                    owner_kind="orchestration_run",
                    owner_id="run-1",
                    lane_key="agent:main",
                ),
            )
            container.dispatch_service.enqueue_task(
                EnqueueDispatchTaskInput(task_id="task-1"),
            )
            assert container.orchestration_scheduler_runtime_event_service is not None
            container.orchestration_scheduler_runtime_event_service.process_available_events(
                limit_per_subscription=10,
            )
            published = _published_topic_events(backend)
            self.assertTrue(
                any(
                    envelope.topic == dispatch_wakeup_topic("orchestration_run")
                    and envelope.payload.get("owner_id") == "run-1"
                    for envelope in published
                ),
            )
        finally:
            container.close()
            harness.close()

    def test_file_backed_events_backend_supports_cross_container_wakeup_wait(self) -> None:
        harness = SqliteTestHarness()
        waiter = harness.build_container()
        publisher = harness.build_container()
        try:
            self.assertIsNotNone(waiter.events_service)
            self.assertIsNotNone(publisher.events_service)
            cursor = waiter.events_service.snapshot_event_topic("runtime.cross-process")
            publisher.events_service.publish(
                Event(
                    topic="runtime.cross-process",
                    kind="command",
                    payload={"ok": True},
                ),
            )
            self.assertEqual(
                waiter.events_service.wait_for_event_topics(
                    (
                        EventTopicWatch("runtime.other-cross-process", cursor),
                        EventTopicWatch("runtime.cross-process", cursor),
                    ),
                    timeout_seconds=0.5,
                ),
                EventTopicWatch("runtime.cross-process", cursor),
            )
        finally:
            waiter.close()
            publisher.close()

    def test_file_backed_events_backend_serializes_cross_backend_topic_writes(self) -> None:
        harness = SqliteTestHarness()
        first = harness.build_container()
        second = harness.build_container()
        try:
            self.assertIsNotNone(first.events_service)
            self.assertIsNotNone(second.events_service)

            def _publish(index: int) -> None:
                service = first.events_service if index % 2 == 0 else second.events_service
                assert service is not None
                service.publish(
                    Event(
                        topic="runtime.concurrent",
                        kind="fact",
                        payload={"index": index},
                    ),
                )

            with ThreadPoolExecutor(max_workers=8) as executor:
                list(executor.map(_publish, range(40)))

            records = first.events_service.read_event_topic(
                "runtime.concurrent",
                after_cursor=None,
                limit=100,
            )
            self.assertEqual(len(records), 40)
            self.assertEqual(
                [record.cursor for record in records],
                [str(index) for index in range(1, 41)],
            )
            self.assertEqual(
                sorted(int(record.envelope.payload["index"]) for record in records),
                list(range(40)),
            )
        finally:
            first.close()
            second.close()
            harness.close()
            harness.close()

    def test_file_backed_events_backend_can_replay_topic_records_across_containers(self) -> None:
        harness = SqliteTestHarness()
        reader = harness.build_container()
        writer = harness.build_container()
        try:
            self.assertIsNotNone(reader.events_service)
            self.assertIsNotNone(writer.events_service)
            cursor = reader.events_service.snapshot_event_topic("runtime.replay")
            writer.events_service.publish(
                Event(
                    topic="runtime.replay",
                    kind="fact",
                    payload={"step": 1},
                ),
            )
            writer.events_service.publish(
                Event(
                    topic="runtime.replay",
                    kind="fact",
                    payload={"step": 2},
                ),
            )

            records = reader.events_service.read_event_topic(
                "runtime.replay",
                after_cursor=cursor,
                limit=10,
            )
            self.assertEqual([record.cursor for record in records], ["1", "2"])
            self.assertEqual([record.envelope.payload["step"] for record in records], [1, 2])
        finally:
            reader.close()
            writer.close()
            harness.close()


if __name__ == "__main__":
    unittest.main()
