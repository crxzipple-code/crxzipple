from __future__ import annotations

from datetime import datetime, timedelta, timezone

from crxzipple.modules.channels.domain import (
    ChannelConnectionBinding,
    ChannelRuntimeRegistration,
)
from crxzipple.modules.events import Event

from tests.unit.http_test_support import AppKey, HttpModuleTestCase


class UiOperationsActionsHttpTestCase(HttpModuleTestCase):
    def test_ui_operations_events_action_advances_subscription_cursor(self) -> None:
        container = self.client.app.state.container
        topic = "events.named.operations.events.action"
        container.require(AppKey.EVENTS_SERVICE).publish(
            Event(
                name="operations.events.action",
                topic=topic,
                kind="fact",
                payload={"event_name": "operations.events.action"},
            ),
        )
        container.require(AppKey.EVENTS_SERVICE).set_subscription_cursor(
            "operations.events.action.consumer",
            source_topic=topic,
            cursor="0",
        )

        missing_reason_response = self.client.post(
            "/operations/events/subscriptions/advance-to-head",
            json={
                "subscription_id": "operations.events.action.consumer",
                "source_topic": topic,
                "status": "lagging",
            },
        )
        self.assertEqual(missing_reason_response.status_code, 400)

        missing_confirmation_response = self.client.post(
            "/operations/events/subscriptions/advance-to-head",
            json={
                "subscription_id": "operations.events.action.consumer",
                "source_topic": topic,
                "status": "lagging",
                "reason": "unit test cursor maintenance",
                "risk_acknowledged": True,
            },
        )
        self.assertEqual(missing_confirmation_response.status_code, 400)
        self.assertIn(
            "confirmation",
            missing_confirmation_response.json()["detail"],
        )

        missing_risk_ack_response = self.client.post(
            "/operations/events/subscriptions/advance-to-head",
            json={
                "subscription_id": "operations.events.action.consumer",
                "source_topic": topic,
                "status": "lagging",
                "reason": "unit test cursor maintenance",
                "confirmation": "Advance cursor to head for unit test",
            },
        )
        self.assertEqual(missing_risk_ack_response.status_code, 400)
        self.assertIn(
            "risk acknowledgement",
            missing_risk_ack_response.json()["detail"],
        )

        response = self.client.post(
            "/operations/events/subscriptions/advance-to-head",
            json={
                "subscription_id": "operations.events.action.consumer",
                "source_topic": topic,
                "status": "lagging",
                "reason": "unit test cursor maintenance",
                "confirmation": "Advance cursor to head for unit test",
                "risk_acknowledged": True,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["matched_count"], 1)
        self.assertEqual(payload["advanced_count"], 1)
        self.assertEqual(payload["items"][0]["previous_cursor"], "0")
        self.assertEqual(payload["items"][0]["latest_cursor"], "1")
        state = container.require(AppKey.EVENTS_SERVICE).get_subscription_cursor(
            "operations.events.action.consumer",
            source_topic=topic,
        )
        self.assertIsNotNone(state)
        assert state is not None
        self.assertEqual(state.cursor, "1")
        audits_response = self.client.get("/operations/actions/audits")
        self.assertEqual(audits_response.status_code, 200)
        audits = audits_response.json()
        self.assertGreaterEqual(len(audits), 1)
        self.assertEqual(
            audits[0]["audit_event"],
            "events.subscriptions.advance_to_head",
        )
        self.assertEqual(audits[0]["action_type"], "events.subscriptions.advance_to_head")
        self.assertEqual(audits[0]["target_id"], "operations.events.action.consumer")
        self.assertEqual(audits[0]["reason"], "unit test cursor maintenance")
        self.assertTrue(audits[0]["dangerous"])
        self.assertEqual(audits[0]["risk"], "dangerous")
        self.assertTrue(audits[0]["confirmation"])
        self.assertTrue(audits[0]["risk_acknowledged"])
        self.assertEqual(audits[0]["status"], "succeeded")

    def test_ui_operations_events_action_advances_observer_cursor(self) -> None:
        container = self.client.app.state.container
        topic = "events.named.operations.events.observer.action"
        container.require(AppKey.EVENTS_SERVICE).publish(
            Event(
                name="operations.events.observer.action",
                topic=topic,
                kind="fact",
                payload={"event_name": "operations.events.observer.action"},
            ),
        )
        container.require(AppKey.EVENTS_SERVICE).set_subscription_cursor(
            "operations.observer.events.action",
            source_topic=topic,
            cursor="0",
        )

        response = self.client.post(
            "/operations/events/observers/advance-to-head",
            json={
                "subscription_id": "operations.observer.events.action",
                "source_topic": topic,
                "status": "lagging",
                "reason": "unit test observer maintenance",
                "confirmation": True,
                "risk_acknowledged": True,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["matched_count"], 1)
        self.assertEqual(payload["advanced_count"], 1)
        state = container.require(AppKey.EVENTS_SERVICE).get_subscription_cursor(
            "operations.observer.events.action",
            source_topic=topic,
        )
        self.assertIsNotNone(state)
        assert state is not None
        self.assertEqual(state.cursor, "1")

    def test_ui_operations_channels_action_prunes_stale_runtimes(self) -> None:
        container = self.client.app.state.container
        stale_at = datetime.now(timezone.utc) - timedelta(minutes=12)
        container.require(AppKey.CHANNEL_RUNTIME_MANAGER).register_runtime(
            ChannelRuntimeRegistration(
                runtime_id="web-runtime-stale-action",
                channel_type="web",
                service_key="channel:web",
                registered_at=stale_at,
                last_heartbeat_at=stale_at,
            ),
        )
        container.require(AppKey.CHANNEL_RUNTIME_MANAGER).bind_connection(
            ChannelConnectionBinding(
                channel_type="web",
                connection_id="web-connection-stale-action",
                runtime_id="web-runtime-stale-action",
                conversation_id="agent:assistant:stale-action",
            ),
        )

        missing_reason_response = self.client.post(
            "/operations/channels/runtimes/prune-stale",
            json={"runtime_id": "web-runtime-stale-action"},
        )
        self.assertEqual(missing_reason_response.status_code, 400)

        response = self.client.post(
            "/operations/channels/runtimes/prune-stale",
            json={
                "runtime_id": "web-runtime-stale-action",
                "reason": "unit test stale runtime cleanup",
                "confirmation": True,
                "risk_acknowledged": True,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["matched_count"], 1)
        self.assertEqual(payload["pruned_count"], 1)
        self.assertEqual(payload["items"][0]["runtime_id"], "web-runtime-stale-action")
        self.assertEqual(payload["items"][0]["connection_bindings_removed"], 1)
        self.assertIsNone(
            container.require(AppKey.CHANNEL_RUNTIME_MANAGER).get_runtime("web-runtime-stale-action"),
        )
        self.assertEqual(
            container.require(AppKey.CHANNEL_RUNTIME_MANAGER).list_connection_bindings(
                runtime_id="web-runtime-stale-action",
            ),
            (),
        )
        audits_response = self.client.get("/operations/actions/audits?limit=1")
        self.assertEqual(audits_response.status_code, 200)
        audits = audits_response.json()
        self.assertEqual(audits[0]["audit_event"], "channels.runtimes.prune_stale")
        self.assertEqual(audits[0]["action_type"], "channels.runtimes.prune_stale")
        self.assertEqual(audits[0]["target_id"], "web-runtime-stale-action")
        self.assertEqual(audits[0]["risk"], "dangerous")
        self.assertEqual(audits[0]["status"], "succeeded")
