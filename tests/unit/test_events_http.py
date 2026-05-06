from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import threading
import time

from crxzipple.modules.events import Event, EventSubscriptionCursor
from crxzipple.modules.orchestration.application import RUN_OBSERVATION_EVENT_NAMES
from crxzipple.shared import (
    ORCHESTRATION_RUN_MESSAGE_APPENDED_EVENT,
    ORCHESTRATION_RUN_TOOL_UPDATED_EVENT,
    ORCHESTRATION_RUNTIME_STATUS_EVENT,
)

from tests.unit.http_test_support import HttpModuleTestCase


class EventsHttpTestCase(HttpModuleTestCase):
    def test_event_contracts_endpoint_lists_registered_topics_and_routes(self) -> None:
        response = self.client.get("/events/contracts")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        topic_ids = {
            item["contract_id"]
            for item in payload["topics"]
        }
        route_ids = {
            item["contract_id"]
            for item in payload["routes"]
        }
        definition_ids = {
            item["definition_id"]
            for item in payload["definitions"]
        }
        definitions_by_id = {
            item["definition_id"]: item
            for item in payload["definitions"]
        }
        observer_ids = {
            item["observer_id"]
            for item in payload["observers"]
        }
        observers_by_id = {
            item["observer_id"]: item
            for item in payload["observers"]
        }
        surface_ids = {
            item["surface_id"]
            for item in payload["surfaces"]
        }
        self.assertIn("turn.session", topic_ids)
        self.assertNotIn("turn.run", topic_ids)
        self.assertNotIn("channel.connection.observe", topic_ids)
        self.assertIn("dispatch.wakeup", topic_ids)
        self.assertNotIn("delivery.runtime", topic_ids)
        self.assertNotIn("turn.session.to.web.connection.observe", route_ids)
        self.assertIn("dispatch.task.queued", definition_ids)
        self.assertIn("channel.observation.dead_lettered", definition_ids)
        self.assertIn("orchestration.run.completed", definition_ids)
        self.assertIn("orchestration.run.llm_text_delta", definition_ids)
        self.assertIn(ORCHESTRATION_RUN_MESSAGE_APPENDED_EVENT, definition_ids)
        self.assertIn(ORCHESTRATION_RUN_TOOL_UPDATED_EVENT, definition_ids)
        self.assertIn(ORCHESTRATION_RUNTIME_STATUS_EVENT, definition_ids)
        self.assertIn("dispatch.wakeup", observer_ids)
        self.assertIn("orchestration.run.observation", observer_ids)
        self.assertIn("orchestration.session.message_observation", observer_ids)
        self.assertIn("orchestration.tool.observation", observer_ids)
        self.assertIn("orchestration.runtime.observation", observer_ids)
        self.assertEqual(
            definitions_by_id["dispatch.task.queued"]["publication_mode"],
            "reduced",
        )
        self.assertEqual(
            definitions_by_id["dispatch.task.queued"]["source_event_names"],
            ["dispatch.task.queued"],
        )
        self.assertEqual(
            definitions_by_id["channel.observation.dead_lettered"]["publication_mode"],
            "direct",
        )
        self.assertEqual(
            definitions_by_id["orchestration.run.completed"]["publication_mode"],
            "reduced",
        )
        self.assertEqual(
            definitions_by_id["orchestration.run.completed"]["source_event_names"],
            ["orchestration.run.completed"],
        )
        self.assertEqual(
            definitions_by_id[ORCHESTRATION_RUN_MESSAGE_APPENDED_EVENT]["publication_mode"],
            "translated",
        )
        self.assertEqual(
            definitions_by_id[ORCHESTRATION_RUN_TOOL_UPDATED_EVENT]["publication_mode"],
            "translated",
        )
        self.assertEqual(
            definitions_by_id[ORCHESTRATION_RUNTIME_STATUS_EVENT]["publication_mode"],
            "hydrated",
        )
        self.assertEqual(
            observers_by_id["dispatch.wakeup"]["source_event_names"],
            [
                "dispatch.task.queued",
                "dispatch.task.requeued",
                "dispatch.task.recovered",
            ],
        )
        self.assertEqual(
            observers_by_id["orchestration.run.observation"]["output_definition_ids"],
            list(RUN_OBSERVATION_EVENT_NAMES),
        )
        self.assertEqual(
            observers_by_id["orchestration.session.message_observation"]["handlers"],
            ["SessionMessageObservationObserver.observe_message_appended"],
        )
        self.assertEqual(
            observers_by_id["orchestration.tool.observation"]["handlers"],
            ["ToolRunObservationObserver.observe_tool_event"],
        )
        self.assertEqual(
            observers_by_id["orchestration.runtime.observation"]["handlers"],
            ["RuntimeObservationObserver.observe_runtime_event"],
        )
        self.assertIn("dispatch.wakeup", surface_ids)
        self.assertIn("channels.dead_letter", surface_ids)
        self.assertIn("orchestration.observation", surface_ids)
        self.assertIn("orchestration.runtime_observation", surface_ids)
        self.assertGreaterEqual(payload["topic_count"], 6)
        self.assertEqual(payload["route_count"], 0)
        self.assertGreaterEqual(payload["definition_count"], 14)
        self.assertGreaterEqual(payload["surface_count"], 3)
        self.assertGreaterEqual(payload["observer_count"], 4)

    def test_event_stream_endpoint_bootstraps_snapshot_and_streams_new_records(self) -> None:
        container = self.client.app.state.container
        container.events_service.publish(
            Event(
                topic="turn.session.agent:assistant:deck-console",
                kind="fact",
                payload={
                    "event_name": "orchestration.run.queued",
                    "run_id": "run-console-1",
                    "session_key": "agent:assistant:deck-console",
                    "status": "queued",
                    "stage": "queued",
                },
            ),
        )

        def _publish_later() -> None:
            time.sleep(0.1)
            container.events_service.publish(
                Event(
                    topic="turn.live.session.agent:assistant:deck-console",
                    kind="live",
                    payload={
                        "event_name": "orchestration.run.llm_text_delta",
                        "run_id": "run-console-1",
                        "session_key": "agent:assistant:deck-console",
                        "text_delta": "hello console",
                    },
                ),
            )

        sender = threading.Thread(target=_publish_later)
        sender.start()
        try:
            with self.client.stream(
                "GET",
                "/events/stream",
                params={
                    "snapshot_limit": 5,
                    "timeout_seconds": 1.0,
                },
            ) as response:
                body = response.read().decode("utf-8")
                content_type = response.headers["content-type"]
                status_code = response.status_code
        finally:
            sender.join(timeout=1.0)

        self.assertEqual(status_code, 200)
        self.assertIn("text/event-stream", content_type)
        self.assertEqual(response.headers["x-crx-stream-role"], "primary")
        self.assertEqual(response.headers["x-crx-stream-scope"], "bus")
        self.assertIn("event: connected", body)
        self.assertIn("event: snapshot", body)
        self.assertIn('"topic_count": 1', body)
        self.assertIn('"filters": {}', body)
        self.assertIn("orchestration.run.queued", body)
        self.assertIn('"source_publication_mode": "reduced"', body)
        self.assertIn("event: event", body)
        self.assertIn("orchestration.run.llm_text_delta", body)
        self.assertIn('"source_publication_mode": "direct"', body)
        self.assertIn("hello console", body)
        self.assertIn("event: timeout", body)

    def test_event_stream_endpoint_filters_by_session_and_owner(self) -> None:
        container = self.client.app.state.container
        container.events_service.publish(
            Event(
                topic="turn.session.agent:assistant:deck-filtered",
                kind="fact",
                payload={
                    "event_name": "orchestration.run.queued",
                    "run_id": "run-filtered-1",
                    "session_key": "agent:assistant:deck-filtered",
                    "status": "queued",
                    "stage": "queued",
                },
            ),
        )
        container.events_service.publish(
            Event(
                topic="channel.observe.web.connection.conn-other",
                kind="observe",
                payload={
                    "event_name": "channel.connection.observed",
                    "session_key": "agent:assistant:deck-other",
                    "channel_type": "web",
                },
            ),
        )

        response = self.client.get(
            "/events/stream",
            params={
                "snapshot_limit": 10,
                "timeout_seconds": 0.01,
                "session_key": "agent:assistant:deck-filtered",
                "owner": "orchestration",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertIn('"session_key": "agent:assistant:deck-filtered"', body)
        self.assertIn('"owner": "orchestration"', body)
        self.assertIn("orchestration.run.queued", body)
        self.assertNotIn("channel.connection.observed", body)

    def test_event_topic_diagnostics_reports_contracts_cursors_and_records(self) -> None:
        container = self.client.app.state.container
        topic = "turn.session.agent:assistant:deck-diagnostics"
        container.events_service.publish(
            Event(
                topic=topic,
                kind="fact",
                ordering_key="run-diagnostics-1",
                payload={
                    "event_name": "orchestration.run.completed",
                    "run_id": "run-diagnostics-1",
                },
            ),
        )
        container.events_service.set_subscription_cursor(
            "channel.web.connection.conn-diagnostics.observe",
            source_topic=topic,
            cursor="1",
        )

        response = self.client.get(f"/events/topics/{topic}/diagnostics")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        contract_ids = {
            item["contract"]["contract_id"]
            for item in payload["contract_matches"]
        }
        source_route_ids = {
            item["contract"]["contract_id"]
            for item in payload["routes_as_source"]
        }
        subscription_ids = {
            item["subscription_id"]
            for item in payload["subscription_cursors"]
        }
        self.assertEqual(payload["topic"], topic)
        self.assertEqual(payload["latest_cursor"], "1")
        self.assertEqual(payload["consumer_summary"]["total_count"], 1)
        self.assertEqual(payload["consumer_summary"]["at_head_count"], 1)
        self.assertEqual(payload["consumer_summary"]["lagging_count"], 0)
        self.assertEqual(payload["consumer_summary"]["stuck_count"], 0)
        self.assertIn("turn.session", contract_ids)
        self.assertEqual(source_route_ids, set())
        self.assertIn("channel.web.connection.conn-diagnostics.observe", subscription_ids)
        self.assertTrue(payload["subscription_cursors"][0]["at_head"])
        self.assertFalse(payload["subscription_cursors"][0]["lagging"])
        self.assertFalse(payload["subscription_cursors"][0]["stuck"])
        self.assertEqual(payload["records"][0]["cursor"], "1")
        self.assertEqual(
            payload["records"][0]["event_name"],
            "orchestration.run.completed",
        )

    def test_subscription_diagnostics_lists_and_filters_subscribers(self) -> None:
        container = self.client.app.state.container
        healthy_topic = "turn.session.agent:assistant:deck-subscriptions-healthy"
        lagging_topic = "turn.session.agent:assistant:deck-subscriptions-lagging"

        container.events_service.publish(
            Event(
                topic=healthy_topic,
                kind="fact",
                payload={"event_name": "orchestration.run.completed"},
            ),
        )
        container.events_service.publish(
            Event(
                topic=lagging_topic,
                kind="fact",
                payload={"event_name": "orchestration.run.queued"},
            ),
        )
        container.events_service.publish(
            Event(
                topic=lagging_topic,
                kind="fact",
                payload={"event_name": "orchestration.run.claimed"},
            ),
        )

        healthy_subscription = "channel.web.connection.conn-healthy.observe"
        lagging_subscription = "channel.web.connection.conn-lagging.observe"
        stuck_subscription = "channel.web.connection.conn-stuck.observe"
        container.events_service.set_subscription_cursor(
            healthy_subscription,
            source_topic=healthy_topic,
            cursor="1",
        )
        container.events_service.set_subscription_cursor(
            lagging_subscription,
            source_topic=lagging_topic,
            cursor="1",
        )
        container.events_service.set_subscription_cursor(
            stuck_subscription,
            source_topic=lagging_topic,
            cursor="1",
        )
        backend = container.events_service.backend
        stale_state = EventSubscriptionCursor(
            subscription_id=stuck_subscription,
            source_topic=lagging_topic,
            cursor="1",
            updated_at=datetime.now(timezone.utc) - timedelta(seconds=30),
        )
        if hasattr(backend, "_subscription_cursors"):
            backend._subscription_cursors[stuck_subscription] = stale_state
        else:
            state_path = backend._subscription_state_path(stuck_subscription)
            state_path.write_text(
                json.dumps(stale_state.to_payload(), ensure_ascii=True),
                encoding="utf-8",
            )

        response = self.client.get(
            "/events/subscriptions/diagnostics",
            params={"source_topic_prefix": "turn.session.", "limit": 10},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["filters"]["source_topic_prefix"], "turn.session.")
        self.assertEqual(payload["summary"]["total_count"], 3)
        self.assertEqual(payload["summary"]["visible_count"], 3)
        self.assertEqual(payload["summary"]["source_topic_count"], 2)
        self.assertEqual(payload["summary"]["at_head_count"], 1)
        self.assertEqual(payload["summary"]["lagging_count"], 2)
        self.assertEqual(payload["summary"]["stuck_count"], 1)
        self.assertEqual(payload["items"][0]["subscription_id"], stuck_subscription)
        self.assertTrue(payload["items"][0]["stuck"])
        self.assertTrue(payload["items"][0]["lagging"])
        self.assertEqual(payload["items"][0]["latest_cursor"], "2")
        self.assertGreaterEqual(payload["items"][0]["seconds_since_update"], 30.0)
        contract_ids = {
            item["contract"]["contract_id"]
            for item in payload["items"][0]["contract_matches"]
        }
        self.assertIn("turn.session", contract_ids)
        route_ids = {
            item["contract"]["contract_id"]
            for item in payload["items"][0]["routes_as_source"]
        }
        self.assertEqual(route_ids, set())

        lagging_only = self.client.get(
            "/events/subscriptions/diagnostics",
            params={"status": "stuck"},
        )
        self.assertEqual(lagging_only.status_code, 200)
        stuck_payload = lagging_only.json()
        self.assertEqual(stuck_payload["summary"]["visible_count"], 1)
        self.assertEqual(stuck_payload["items"][0]["subscription_id"], stuck_subscription)

    def test_subscription_diagnostics_rejects_invalid_status(self) -> None:
        response = self.client.get(
            "/events/subscriptions/diagnostics",
            params={"status": "broken"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("status must be one of", response.json()["detail"])
