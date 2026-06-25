from __future__ import annotations

import unittest

from crxzipple.modules.event_relay.application import (
    EventRelayRuntimeService,
    EventRelaySubscription,
)
from crxzipple.modules.events import EventsApplicationService, InMemoryEventsBackend
from crxzipple.shared.domain.events import Event


class EventRelayRuntimeTestCase(unittest.TestCase):
    def test_first_run_without_replay_snapshots_existing_events(self) -> None:
        events_service = EventsApplicationService(InMemoryEventsBackend())
        events_service.publish(Event(topic="source.topic", payload={"value": "old"}))
        handled: list[str] = []
        runtime = EventRelayRuntimeService(
            events_service=events_service,
            subscriptions=(
                EventRelaySubscription(
                    subscription_id="relay.demo",
                    source_topic="source.topic",
                    handler=lambda event: handled.append(str(event.payload["value"])),
                ),
            ),
        )

        processed = runtime.process_available_events()

        self.assertEqual(processed, 0)
        self.assertEqual(handled, [])
        state = events_service.get_subscription_cursor(
            "relay.demo",
            source_topic="source.topic",
        )
        self.assertIsNotNone(state)
        self.assertEqual(state.cursor, "1")

        events_service.publish(Event(topic="source.topic", payload={"value": "new"}))

        processed = runtime.process_available_events()

        self.assertEqual(processed, 1)
        self.assertEqual(handled, ["new"])

    def test_first_run_with_replay_processes_existing_events(self) -> None:
        events_service = EventsApplicationService(InMemoryEventsBackend())
        events_service.publish(Event(topic="source.topic", payload={"value": "old"}))
        handled: list[str] = []
        runtime = EventRelayRuntimeService(
            events_service=events_service,
            subscriptions=(
                EventRelaySubscription(
                    subscription_id="relay.demo",
                    source_topic="source.topic",
                    handler=lambda event: handled.append(str(event.payload["value"])),
                    replay_existing_on_first_run=True,
                ),
            ),
        )

        processed = runtime.process_available_events()

        self.assertEqual(processed, 1)
        self.assertEqual(handled, ["old"])
        state = events_service.get_subscription_cursor(
            "relay.demo",
            source_topic="source.topic",
        )
        self.assertIsNotNone(state)
        self.assertEqual(state.cursor, "1")

    def test_handler_failure_commits_only_successful_cursor(self) -> None:
        events_service = EventsApplicationService(InMemoryEventsBackend())
        events_service.publish(Event(topic="source.topic", payload={"value": "ok"}))
        events_service.publish(Event(topic="source.topic", payload={"value": "retry"}))
        handled: list[str] = []
        should_fail = True

        def handler(event: Event) -> None:
            nonlocal should_fail
            value = str(event.payload["value"])
            if value == "retry" and should_fail:
                should_fail = False
                raise RuntimeError("transient relay failure")
            handled.append(value)

        runtime = EventRelayRuntimeService(
            events_service=events_service,
            subscriptions=(
                EventRelaySubscription(
                    subscription_id="relay.demo",
                    source_topic="source.topic",
                    handler=handler,
                    replay_existing_on_first_run=True,
                ),
            ),
        )

        processed = runtime.process_available_events()

        self.assertEqual(processed, 1)
        self.assertEqual(handled, ["ok"])
        state = events_service.get_subscription_cursor(
            "relay.demo",
            source_topic="source.topic",
        )
        self.assertIsNotNone(state)
        self.assertEqual(state.cursor, "1")

        processed = runtime.process_available_events()

        self.assertEqual(processed, 1)
        self.assertEqual(handled, ["ok", "retry"])


if __name__ == "__main__":
    unittest.main()
