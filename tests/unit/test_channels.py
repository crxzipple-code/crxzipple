from __future__ import annotations

from base64 import b64decode
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import tempfile
import threading
import unittest
from unittest.mock import patch

from crxzipple.core.config import load_settings
from crxzipple.modules.llm.application.adapters import LlmAdapterResponse
from crxzipple.modules.llm.domain import LlmResult
from crxzipple.modules.orchestration.application.turn_submission import (
    build_submission_options,
    submit_turn,
)
from crxzipple.modules.agent.application import RegisterAgentProfileInput
from crxzipple.modules.agent.domain import (
    AgentInstructionPolicy,
    AgentLlmRoutingPolicy,
    AgentRuntimePreferences,
)
from crxzipple.modules.channels import (
    ChannelAccountProfile,
    ChannelAccountRuntimeBinding,
    ChannelCapabilities,
    ChannelConnectionBinding,
    ChannelInteraction,
    ChannelInteractionRegistry,
    ChannelProfile,
    ChannelRuntimePlanner,
    ChannelRuntimeRegistration,
    channel_dead_letter_topic,
    FileBackedChannelInteractionRegistryStore,
)
from crxzipple.modules.events import Event, EventTarget
from crxzipple.modules.llm.application import RegisterLlmProfileInput
from crxzipple.modules.llm.domain import LlmApiFamily, LlmProviderKind
from crxzipple.modules.orchestration.application import (
    turn_session_live_topic,
    turn_session_topic,
)
from crxzipple.modules.session.domain import DirectSessionScope
from crxzipple.shared import ReplyAddress
from tests.unit.orchestration_test_support import process_next_orchestration_assignment
from tests.unit.support import SqliteTestHarness


def _legacy_runtime_outbound_topic(runtime_id: str) -> str:
    return f"delivery.runtime.{runtime_id.strip()}"


class _CallbackCaptureServer:
    def __init__(
        self,
        *,
        response_status: int = 200,
        response_payload: dict[str, object] | None = None,
    ) -> None:
        self._server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            self._build_handler(),
        )
        self._server.payloads = []  # type: ignore[attr-defined]
        self._server.lock = threading.Lock()  # type: ignore[attr-defined]
        self._server.response_status = response_status  # type: ignore[attr-defined]
        self._server.response_payload = dict(response_payload or {"ok": True})  # type: ignore[attr-defined]
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="callback-capture-server",
            daemon=True,
        )

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    @property
    def payloads(self) -> list[dict[str, object]]:
        with self._server.lock:  # type: ignore[attr-defined]
            return list(self._server.payloads)  # type: ignore[attr-defined]

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)

    @staticmethod
    def _build_handler() -> type[BaseHTTPRequestHandler]:
        class _Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length).decode("utf-8") if length else "{}"
                payload = json.loads(body)
                with self.server.lock:  # type: ignore[attr-defined]
                    self.server.payloads.append(payload)  # type: ignore[attr-defined]
                response = json.dumps(self.server.response_payload).encode("utf-8")  # type: ignore[attr-defined]
                self.send_response(int(self.server.response_status))  # type: ignore[attr-defined]
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

            def log_message(self, format: str, *args: object) -> None:
                return

        return _Handler


class _SequentialTextAdapter:
    def __init__(self, *texts: str) -> None:
        self._texts = list(texts)
        self.requests: list[object] = []

    def invoke(self, _profile, request):  # noqa: ANN001
        self.requests.append(request)
        text = self._texts.pop(0) if self._texts else ""
        return LlmAdapterResponse(result=LlmResult(text=text))


class _FakeJsonResponse:
    def __init__(self, *, status_code: int, payload: dict[str, object]) -> None:
        self.status_code = status_code
        self._payload = dict(payload)

    def json(self) -> dict[str, object]:
        return dict(self._payload)


class ChannelsModuleTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = SqliteTestHarness()
        self.container = self.harness.build_container()

    def tearDown(self) -> None:
        self.harness.close()

    def test_channel_interaction_store_upgrades_delivery_metadata_shape(self) -> None:
        old_status = "projec" + "ted"
        old_delivered_term = "projec" + "ted"
        old_delivery_term = "projec" + "tion"
        old_keys = {
            "last_" + old_delivered_term + "_at": "2026-05-04T08:30:00Z",
            "last_" + old_delivered_term + "_message_id": "message-delivery-1",
            "last_" + old_delivered_term + "_message_kind": "message",
            "last_" + old_delivered_term + "_message_role": "assistant",
            "last_" + old_delivery_term + "_status": "ok",
            "last_" + old_delivery_term + "_error": None,
            "last_" + old_delivery_term + "_message_types": ["text"],
            old_delivered_term + "_artifact_ids": ["artifact-delivery-1"],
        }
        with tempfile.TemporaryDirectory() as tempdir:
            store = FileBackedChannelInteractionRegistryStore(
                tempdir,
                bootstrap_registry=ChannelInteractionRegistry(
                    interactions=(
                        ChannelInteraction(
                            interaction_id="webhook:default:event:delivery-state-1",
                            channel_type="webhook",
                            status=old_status,
                            metadata=old_keys,
                        ),
                    ),
                ),
            )

            interaction = store.load().interactions[0]

            self.assertEqual(interaction.status, "delivered")
            self.assertEqual(
                interaction.metadata["last_delivered_at"],
                "2026-05-04T08:30:00Z",
            )
            self.assertEqual(
                interaction.metadata["last_delivered_message_id"],
                "message-delivery-1",
            )
            self.assertEqual(interaction.metadata["last_delivery_status"], "ok")
            self.assertEqual(
                interaction.metadata["last_delivery_message_types"],
                ["text"],
            )
            self.assertEqual(
                interaction.metadata["delivered_artifact_ids"],
                ["artifact-delivery-1"],
            )
            for key in old_keys:
                self.assertNotIn(key, interaction.metadata)

    def test_channel_profile_service_persists_profiles_across_containers(self) -> None:
        saved = self.container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="web",
                capabilities=ChannelCapabilities(
                    supports_streaming=True,
                    supports_edit=True,
                ),
                accounts=(
                    ChannelAccountProfile(
                        account_id="default",
                        transport_mode="sse",
                    ),
                ),
            ),
        )

        self.assertEqual(saved.channel_type, "web")
        self.assertTrue(saved.capabilities.supports_streaming)
        self.assertEqual(len(saved.accounts), 1)

        reopened = self.harness.build_container()
        resolved = reopened.channel_profile_service.get_profile("WEB")
        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertTrue(resolved.capabilities.supports_edit)
        self.assertEqual(resolved.accounts[0].transport_mode, "sse")

    def test_channel_runtime_manager_tracks_runtime_account_and_connection_bindings(self) -> None:
        manager = self.container.channel_runtime_manager
        registered = manager.register_runtime(
            ChannelRuntimeRegistration(
                runtime_id="web-runtime-1",
                channel_type="web",
                service_key="channel:web",
                capabilities=ChannelCapabilities(supports_streaming=True),
            ),
        )

        self.assertEqual(registered.runtime_id, "web-runtime-1")
        old_heartbeat = registered.last_heartbeat_at
        heartbeat = manager.heartbeat_runtime("web-runtime-1")
        self.assertIsNotNone(heartbeat)
        assert heartbeat is not None
        self.assertGreaterEqual(heartbeat.last_heartbeat_at, old_heartbeat)

        account_binding = manager.bind_account(
            ChannelAccountRuntimeBinding(
                channel_type="web",
                channel_account_id="acc-1",
                runtime_id="web-runtime-1",
            ),
        )
        connection_binding = manager.bind_connection(
            ChannelConnectionBinding(
                channel_type="web",
                connection_id="conn-1",
                runtime_id="web-runtime-1",
                channel_account_id="acc-1",
                conversation_id="conv-1",
                supports_streaming=True,
            ),
        )

        self.assertEqual(account_binding.runtime_id, "web-runtime-1")
        self.assertEqual(connection_binding.channel_account_id, "acc-1")
        resolved_account = manager.resolve_account_runtime(
            channel_type="web",
            channel_account_id="acc-1",
        )
        resolved_connection = manager.resolve_connection_runtime(
            channel_type="web",
            connection_id="conn-1",
        )
        self.assertIsNotNone(resolved_account)
        self.assertIsNotNone(resolved_connection)
        assert resolved_account is not None
        assert resolved_connection is not None
        self.assertEqual(resolved_account.runtime_id, "web-runtime-1")
        self.assertEqual(resolved_connection.runtime_id, "web-runtime-1")
        self.assertEqual(len(manager.list_connection_bindings(runtime_id="web-runtime-1")), 1)

        reopened = self.harness.build_container()
        reopened_runtime = reopened.channel_runtime_manager.resolve_account_runtime(
            channel_type="web",
            channel_account_id="acc-1",
        )
        self.assertIsNotNone(reopened_runtime)
        assert reopened_runtime is not None
        self.assertEqual(reopened_runtime.service_key, "channel:web")
        registry_after_unregister = reopened.channel_runtime_manager.unregister_runtime(
            "web-runtime-1",
        )
        self.assertEqual(registry_after_unregister.runtimes, ())
        self.assertEqual(registry_after_unregister.account_bindings, ())
        self.assertEqual(registry_after_unregister.connection_bindings, ())

    def test_container_bootstraps_channel_profiles_from_settings(self) -> None:
        settings = replace(
            load_settings(),
            channel_profiles=(
                ChannelProfile(
                    channel_type="lark",
                    accounts=(
                        ChannelAccountProfile(
                            account_id="default",
                            transport_mode="webhook",
                            metadata={
                                "agent_id": "assistant-lark",
                                "lark_app_id": "cli_test",
                                "lark_app_secret": "secret_test",
                            },
                        ),
                    ),
                ),
            ),
            channels_state_dir=os.path.join(
                self.harness._tempdir.name,
                "channels-from-settings",
            ),
        )

        container = self.harness.build_container(settings=settings)

        profile = container.channel_profile_service.get_profile("lark")
        self.assertIsNotNone(profile)
        assert profile is not None
        self.assertEqual(profile.accounts[0].metadata["lark_app_id"], "cli_test")

    def test_channel_system_config_store_exposed_on_container(self) -> None:
        profile = ChannelProfile(channel_type="telegram")
        saved = self.container.channel_system_config_store.save(
            replace(
                self.container.channel_system_config_store.load(),
                profiles=(profile,),
            ),
        )

        self.assertEqual(saved.profiles[0].channel_type, "telegram")
        self.assertEqual(self.container.channel_state_root.root_dir.name, "channels")

    def test_channel_interaction_service_persists_interactions_and_binds_runs(self) -> None:
        created = self.container.channel_interaction_service.upsert_interaction(
            ChannelInteraction(
                interaction_id="lark-msg-1",
                channel_type="lark",
                channel_account_id="default",
                external_event_id="evt-1",
                external_message_id="om_1",
                external_conversation_id="oc_1",
                external_user_id="ou_1",
                reply_address={
                    "channel_type": "lark",
                    "channel_account_id": "default",
                    "external_conversation_id": "oc_1",
                    "external_user_id": "ou_1",
                },
                status="received",
                metadata={"source": "private_message"},
            ),
        )

        self.assertEqual(created.interaction_id, "lark-msg-1")
        self.assertEqual(created.status, "received")

        bound = self.container.channel_interaction_service.bind_run(
            "lark-msg-1",
            run_id="run-lark-1",
            session_key="agent:assistant:lark:dm:ou_1",
            agent_id="assistant",
            status="submitted",
            metadata={"submit_path": "channel_ingress"},
        )
        self.assertIsNotNone(bound)
        assert bound is not None
        self.assertEqual(bound.run_id, "run-lark-1")
        self.assertEqual(bound.session_key, "agent:assistant:lark:dm:ou_1")
        self.assertEqual(bound.agent_id, "assistant")
        self.assertEqual(bound.metadata["submit_path"], "channel_ingress")

        running = self.container.channel_interaction_service.mark_status(
            "lark-msg-1",
            status="running",
            metadata={"last_observed_event_name": "orchestration.run.advanced"},
        )
        self.assertIsNotNone(running)
        assert running is not None
        self.assertEqual(running.status, "running")
        self.assertEqual(
            running.metadata["last_observed_event_name"],
            "orchestration.run.advanced",
        )

        resolved = self.container.channel_interaction_service.get_interaction_by_run_id(
            "run-lark-1",
        )
        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual(resolved.interaction_id, "lark-msg-1")

        reopened = self.harness.build_container()
        reopened_interaction = reopened.channel_interaction_service.get_interaction(
            "lark-msg-1",
        )
        self.assertIsNotNone(reopened_interaction)
        assert reopened_interaction is not None
        self.assertEqual(reopened_interaction.run_id, "run-lark-1")
        self.assertEqual(reopened_interaction.status, "running")
        self.assertEqual(
            reopened_interaction.metadata["last_observed_event_name"],
            "orchestration.run.advanced",
        )

    def test_channel_interaction_service_binds_all_matching_interactions_by_run_id(self) -> None:
        first = self.container.channel_interaction_service.upsert_interaction(
            ChannelInteraction(
                interaction_id="webhook-run-bind-1",
                channel_type="webhook",
                run_id="run-bind-all-1",
                status="accepted",
            ),
        )
        second = self.container.channel_interaction_service.upsert_interaction(
            ChannelInteraction(
                interaction_id="webhook-run-bind-2",
                channel_type="webhook",
                run_id="run-bind-all-1",
                status="accepted",
            ),
        )

        bound = self.container.channel_interaction_service.bind_run_by_run_id(
            "run-bind-all-1",
            session_key="agent:assistant:webhook:dm:bind-all",
            agent_id="assistant",
            status="queued",
            metadata={"active_session_id": "session-bind-all-1"},
        )

        self.assertEqual(
            {item.interaction_id for item in bound},
            {first.interaction_id, second.interaction_id},
        )
        for interaction_id in ("webhook-run-bind-1", "webhook-run-bind-2"):
            interaction = self.container.channel_interaction_service.get_interaction(
                interaction_id,
            )
            self.assertIsNotNone(interaction)
            assert interaction is not None
            self.assertEqual(
                interaction.session_key,
                "agent:assistant:webhook:dm:bind-all",
            )
            self.assertEqual(interaction.agent_id, "assistant")
            self.assertEqual(interaction.status, "queued")
            self.assertEqual(
                interaction.metadata["active_session_id"],
                "session-bind-all-1",
            )

    def test_web_channel_runtime_registers_profile_accounts(self) -> None:
        self.container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="web",
                capabilities=ChannelCapabilities(
                    supports_streaming=True,
                    supports_edit=True,
                ),
                accounts=(
                    ChannelAccountProfile(account_id="default", transport_mode="sse"),
                ),
            ),
        )

        runtime = self.container.web_channel_runtime_service.ensure_registered(
            runtime_id="web-runtime-1",
        )
        self.assertEqual(runtime.service_key, "channel:web")
        bound_runtime = self.container.channel_runtime_manager.resolve_account_runtime(
            channel_type="web",
            channel_account_id="default",
        )
        self.assertIsNotNone(bound_runtime)
        assert bound_runtime is not None
        self.assertEqual(bound_runtime.runtime_id, "web-runtime-1")

    def test_web_channel_runtime_can_bind_and_unbind_connections(self) -> None:
        self.container.web_channel_runtime_service.ensure_registered(
            runtime_id="web-runtime-1",
        )

        binding = self.container.web_channel_runtime_service.bind_connection(
            connection_id="conn-sse-1",
            channel_account_id="default",
            conversation_id="agent:demo:main",
            metadata={"stream_path": "sse"},
        )

        self.assertEqual(binding.runtime_id, "web-runtime-1")
        self.assertEqual(binding.channel_account_id, "default")
        self.assertTrue(binding.supports_streaming)
        self.assertEqual(
            self.container.channel_runtime_manager.resolve_connection_binding(
                channel_type="web",
                connection_id="conn-sse-1",
            ).runtime_id,
            "web-runtime-1",
        )

        registry = self.container.web_channel_runtime_service.unbind_connection(
            "conn-sse-1",
        )
        self.assertEqual(registry.connection_bindings, ())

    def test_web_channel_runtime_loop_observes_session_events_and_updates_runtime_metadata(self) -> None:
        self.container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="web",
                accounts=(
                    ChannelAccountProfile(account_id="default", transport_mode="sse"),
                ),
            ),
        )

        self.container.web_channel_runtime_service.ensure_registered(
            runtime_id="web-runtime-loop-1",
        )
        self.container.web_channel_runtime_service.bind_connection(
            connection_id="conn-loop-1",
            channel_account_id="default",
            conversation_id="agent:demo:loop",
            runtime_id="web-runtime-loop-1",
        )
        self.container.events_service.publish(
            Event(
                topic=turn_session_live_topic("agent:demo:loop"),
                kind="live",
                ordering_key="run-loop-1",
                payload={
                    "event_name": "orchestration.run.llm_text_delta",
                    "run_id": "run-loop-1",
                    "session_key": "agent:demo:loop",
                    "invocation_id": "invoke-loop-1",
                    "text": "hello from loop",
                },
            ),
        )

        self.container.web_channel_runtime_service.run_runtime_loop(
            "web",
            runtime_id="web-runtime-loop-1",
            poll_interval_seconds=0.05,
            max_cycles=1,
        )

        runtime = self.container.channel_runtime_manager.get_runtime("web-runtime-loop-1")
        self.assertIsNotNone(runtime)
        assert runtime is not None
        self.assertNotIn("live_observed_count", runtime.metadata)
        self.assertNotIn("live_routed_count", runtime.metadata)
        self.assertNotIn("last_live_event_name", runtime.metadata)
        self.assertNotIn("stream_path", runtime.metadata)

    def test_web_channel_runtime_seeds_session_observe_source_cursor(self) -> None:
        self.container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="web",
                accounts=(ChannelAccountProfile(account_id="default", transport_mode="sse"),),
            ),
        )
        self.container.web_channel_runtime_service.ensure_registered(
            runtime_id="web-runtime-observe-1",
        )
        self.container.web_channel_runtime_service.bind_connection(
            connection_id="conn-observe-1",
            channel_account_id="default",
            conversation_id="agent:demo:observe",
            runtime_id="web-runtime-observe-1",
        )
        self.container.events_service.publish(
            Event(
                topic=turn_session_topic("agent:demo:observe"),
                kind="fact",
                ordering_key="agent:demo:observe",
                payload={
                    "event_name": "orchestration.run.advanced",
                    "run_id": "run-observe-1",
                    "session_key": "agent:demo:observe",
                    "status": "running",
                    "stage": "llm_generating",
                },
            ),
        )
        seeded_cursor = self.container.events_service.snapshot_event_topic(
            turn_session_topic("agent:demo:observe"),
        )
        seeded = self.container.web_channel_runtime_service.seed_connection_source_cursors(
            connection_id="conn-observe-1",
            conversation_id="agent:demo:observe",
        )
        self.assertEqual(seeded["observe_cursor"], seeded_cursor)
        binding = self.container.channel_runtime_manager.resolve_connection_binding(
            channel_type="web",
            connection_id="conn-observe-1",
        )
        self.assertIsNotNone(binding)
        assert binding is not None
        self.assertEqual(binding.metadata["observe_cursor"], seeded_cursor)
        self.assertEqual(
            self.container.web_channel_runtime_service.get_connection_observe_source_cursor(
                connection_id="conn-observe-1",
                conversation_id="agent:demo:observe",
            ),
            seeded_cursor,
        )

    def test_web_channel_runtime_routes_session_live_to_connection_topic(self) -> None:
        self.container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="web",
                accounts=(ChannelAccountProfile(account_id="default", transport_mode="sse"),),
            ),
        )
        self.container.web_channel_runtime_service.ensure_registered(
            runtime_id="web-runtime-live-1",
        )
        self.container.web_channel_runtime_service.bind_connection(
            connection_id="conn-live-1",
            channel_account_id="default",
            conversation_id="agent:demo:live",
            runtime_id="web-runtime-live-1",
        )
        self.container.events_service.publish(
            Event(
                topic=turn_session_live_topic("agent:demo:live"),
                kind="live",
                ordering_key="run-live-1",
                payload={
                    "event_name": "orchestration.run.llm_text_delta",
                    "run_id": "run-live-1",
                    "session_key": "agent:demo:live",
                    "invocation_id": "invoke-live-1",
                    "text": "hello live",
                },
            ),
        )

        binding = self.container.channel_runtime_manager.resolve_connection_binding(
            channel_type="web",
            connection_id="conn-live-1",
        )
        self.assertIsNotNone(binding)
        assert binding is not None
        self.container.channel_runtime_manager.merge_connection_metadata(
            channel_type="web",
            connection_id="conn-live-1",
            metadata={
                "live_cursor": self.container.events_service.snapshot_event_topic(
                    turn_session_live_topic("agent:demo:live"),
                ),
            },
        )
        self.assertEqual(
            self.container.web_channel_runtime_service.get_connection_live_source_cursor(
                connection_id="conn-live-1",
                conversation_id="agent:demo:live",
            ),
            "1",
        )

    def test_web_channel_runtime_waits_for_live_and_observe_source_activity(self) -> None:
        self.container.web_channel_runtime_service.ensure_registered(
            runtime_id="web-runtime-wait-activity-1",
        )
        self.container.web_channel_runtime_service.bind_connection(
            connection_id="conn-wait-activity-1",
            channel_account_id="default",
            conversation_id="agent:demo:wait-activity",
            runtime_id="web-runtime-wait-activity-1",
        )
        self.container.web_channel_runtime_service.seed_connection_source_cursors(
            connection_id="conn-wait-activity-1",
            conversation_id="agent:demo:wait-activity",
        )

        self.assertFalse(
            self.container.web_channel_runtime_service.wait_for_runtime_activity(
                "web-runtime-wait-activity-1",
                timeout_seconds=0.01,
            ),
        )

        self.container.events_service.publish(
            Event(
                topic=turn_session_live_topic("agent:demo:wait-activity"),
                kind="live",
                ordering_key="run-wait-activity-1",
                payload={
                    "event_name": "orchestration.run.llm_text_delta",
                    "run_id": "run-wait-activity-1",
                    "session_key": "agent:demo:wait-activity",
                    "text": "wake live",
                },
            ),
        )
        self.assertTrue(
            self.container.web_channel_runtime_service.wait_for_runtime_activity(
                "web-runtime-wait-activity-1",
                timeout_seconds=0.1,
            ),
        )
        self.container.channel_runtime_manager.merge_connection_metadata(
            channel_type="web",
            connection_id="conn-wait-activity-1",
            metadata={
                "live_cursor": self.container.events_service.snapshot_event_topic(
                    turn_session_live_topic("agent:demo:wait-activity"),
                ),
            },
        )

        self.container.events_service.publish(
            Event(
                topic=turn_session_topic("agent:demo:wait-activity"),
                kind="fact",
                ordering_key="agent:demo:wait-activity",
                payload={
                    "event_name": "orchestration.run.advanced",
                    "run_id": "run-wait-activity-1",
                    "session_key": "agent:demo:wait-activity",
                    "status": "running",
                },
            ),
        )
        self.assertTrue(
            self.container.web_channel_runtime_service.wait_for_runtime_activity(
                "web-runtime-wait-activity-1",
                timeout_seconds=0.1,
            ),
        )

    def test_webhook_dead_letter_replay_payload_posts_callback_directly(self) -> None:
        callback_server = _CallbackCaptureServer()
        callback_server.start()
        try:
            callback_status = (
                self.container.webhook_channel_runtime_service.replay_dead_letter_payload(
                    callback_payload={
                        "outbound_id": "out-replay-direct-1",
                        "mode": "event",
                        "conversation_id": "ext-conv-replay-direct-1",
                        "session_key": "agent:demo:webhook:replay-direct",
                        "message": {
                            "role": "assistant",
                            "type": "text",
                            "text": "hello from replay helper",
                        },
                        "reply_address": {
                            "channel_type": "webhook",
                            "channel_account_id": "default",
                            "webhook_callback_url": f"{callback_server.base_url}/callback",
                        },
                        "metadata": {"run_id": "run-replay-direct-1"},
                        "created_at": "2026-04-16T00:00:00+00:00",
                    },
                )
            )

            payloads = callback_server.payloads
            self.assertEqual(len(payloads), 1)
            self.assertEqual(payloads[0]["message"]["text"], "hello from replay helper")
            self.assertEqual(callback_status, "http_200")
        finally:
            callback_server.close()

    def test_completed_run_with_webhook_reply_target_skips_legacy_runtime_topic_publication(self) -> None:
        self.container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="webhook",
                accounts=(
                    ChannelAccountProfile(
                        account_id="default",
                        transport_mode="webhook",
                    ),
                ),
            ),
        )
        self.container.channel_runtime_manager.register_runtime(
            ChannelRuntimeRegistration(
                runtime_id="webhook-runtime-auto-1",
                channel_type="webhook",
                service_key="channel:webhook",
            ),
        )
        self.container.channel_runtime_manager.bind_account(
            ChannelAccountRuntimeBinding(
                channel_type="webhook",
                channel_account_id="default",
                runtime_id="webhook-runtime-auto-1",
            ),
        )
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            _SequentialTextAdapter("skip webhook legacy runtime topic"),
        )
        self.container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="test-llm-webhook-skip",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
            ),
        )
        self.container.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="assistant-webhook-skip",
                name="Assistant Webhook Skip",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Be helpful.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(
                    default_llm_id="test-llm-webhook-skip",
                ),
                runtime_preferences=AgentRuntimePreferences(),
            ),
        )
        profile = self.container.agent_service.get_profile("assistant-webhook-skip")
        run = submit_turn(
            self.container.orchestration_scheduler_service,
            content="hello webhook auto",
            options=build_submission_options(
                profile=profile,
                llm_id=None,
                channel="webhook",
                chat_type="direct",
                peer_id="ext-user-auto-1",
                conversation_id="ext-conv-auto-1",
                thread_id=None,
                account_id="default",
                main_key="main",
                direct_scope=DirectSessionScope.MAIN,
                source="webhook",
                queue_policy="jump_queue",
                priority=100,
                max_steps=None,
            ),
            inline_worker_id="scheduler-inline",
            reply_interface="webhook",
            reply_address="https://example.test/callback",
            reply_to="ext-conv-auto-1",
            reply_metadata={
                "reply_address": ReplyAddress(
                    channel_type="webhook",
                    channel_account_id="default",
                    webhook_callback_url="https://example.test/callback",
                    external_conversation_id="ext-conv-auto-1",
                    external_user_id="ext-user-auto-1",
                ).to_payload(),
            },
        )
        legacy_cursor = self.container.events_service.snapshot_event_topic(
            _legacy_runtime_outbound_topic("webhook-runtime-auto-1"),
        )

        processed = process_next_orchestration_assignment(self.container,
            worker_id="channels-test-worker",
        )
        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.id, run.id)

        legacy_records = self.container.events_service.read_event_topic(
            _legacy_runtime_outbound_topic("webhook-runtime-auto-1"),
            after_cursor=legacy_cursor,
            limit=10,
        )
        self.assertEqual(legacy_records, ())

    def test_completed_run_with_webhook_observation_enabled_emits_callback_from_observe(self) -> None:
        self.container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="webhook",
                accounts=(
                    ChannelAccountProfile(
                        account_id="default",
                        transport_mode="webhook",
                    ),
                ),
            ),
        )
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            _SequentialTextAdapter("observe callback answer"),
        )
        self.container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="test-llm-observe-webhook",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
            ),
        )
        self.container.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="assistant-observe-webhook",
                name="Assistant Observe Webhook",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Be helpful.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(
                    default_llm_id="test-llm-observe-webhook",
                ),
                runtime_preferences=AgentRuntimePreferences(),
            ),
        )
        self.container.webhook_channel_runtime_service.ensure_registered(
            runtime_id="webhook-runtime-observe-auto-1",
        )
        callback_server = _CallbackCaptureServer()
        callback_server.start()
        try:
            agent = self.container.agent_service.get_profile("assistant-observe-webhook")
            run = submit_turn(
                self.container.orchestration_scheduler_service,
                content={"blocks": [{"type": "text", "text": "hello webhook observe"}]},
                options=build_submission_options(
                    profile=agent,
                    llm_id=None,
                    channel="webhook",
                    chat_type="direct",
                    peer_id="ext-user-observe-1",
                    conversation_id="ext-conv-observe-1",
                    thread_id=None,
                    account_id="default",
                    main_key="main",
                    direct_scope=DirectSessionScope.MAIN,
                    source="webhook",
                    queue_policy="jump_queue",
                    priority=100,
                    max_steps=None,
                ),
                inline_worker_id="scheduler-inline",
                reply_interface="webhook",
                reply_address=f"{callback_server.base_url}/callback",
                reply_to="ext-conv-observe-1",
                reply_metadata={
                    "reply_address": ReplyAddress(
                        channel_type="webhook",
                        channel_account_id="default",
                        webhook_callback_url=f"{callback_server.base_url}/callback",
                        external_conversation_id="ext-conv-observe-1",
                        external_user_id="ext-user-observe-1",
                        metadata={"observation_enabled": True},
                    ).to_payload(),
                },
            )
            self.container.channel_interaction_service.upsert_interaction(
                ChannelInteraction(
                    interaction_id=f"webhook:default:run:{run.id}",
                    channel_type="webhook",
                    channel_account_id="default",
                    external_conversation_id="ext-conv-observe-1",
                    external_user_id="ext-user-observe-1",
                    reply_address={
                        "channel_type": "webhook",
                        "channel_account_id": "default",
                        "webhook_callback_url": f"{callback_server.base_url}/callback",
                        "external_conversation_id": "ext-conv-observe-1",
                        "external_user_id": "ext-user-observe-1",
                        "metadata": {"observation_enabled": True},
                    },
                    agent_id=agent.id,
                    session_key=run.session_key,
                    run_id=run.id,
                    status=run.status.value,
                    metadata={
                        "observe_cursor": self.container.events_service.snapshot_event_topic(
                            turn_session_topic(run.session_key),
                        ),
                    },
                ),
            )
            legacy_cursor = self.container.events_service.snapshot_event_topic(
                _legacy_runtime_outbound_topic("webhook-runtime-observe-auto-1"),
            )

            processed = process_next_orchestration_assignment(self.container,
                worker_id="channels-observe-worker",
            )
            self.assertIsNotNone(processed)
            assert processed is not None
            self.assertEqual(processed.id, run.id)

            assert self.container.event_relay_runtime_event_service is not None
            self.container.event_relay_runtime_event_service.process_available_events(
                limit_per_subscription=10,
            )
            self.container.webhook_channel_runtime_service.run_runtime_loop(
                "webhook",
                runtime_id="webhook-runtime-observe-auto-1",
                poll_interval_seconds=0.05,
                max_cycles=1,
            )

            payloads = callback_server.payloads
            self.assertEqual(len(payloads), 1)
            self.assertEqual(payloads[0]["message"]["content_payload"]["blocks"][0]["text"], "observe callback answer")
            self.assertEqual(payloads[0]["metadata"]["run_id"], run.id)
            self.assertEqual(payloads[0]["metadata"]["interaction_id"], f"webhook:default:run:{run.id}")
            legacy_records = self.container.events_service.read_event_topic(
                _legacy_runtime_outbound_topic("webhook-runtime-observe-auto-1"),
                after_cursor=legacy_cursor,
                limit=10,
            )
            self.assertEqual(legacy_records, ())
        finally:
            callback_server.close()

    def test_webhook_observe_delivery_retries_and_dead_letters_failed_callback(self) -> None:
        self.container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="webhook",
                accounts=(
                    ChannelAccountProfile(
                        account_id="default",
                        transport_mode="webhook",
                    ),
                ),
            ),
        )
        callback_server = _CallbackCaptureServer(response_status=503)
        callback_server.start()
        try:
            self.container.webhook_channel_runtime_service.ensure_registered(
                runtime_id="webhook-runtime-retry-1",
            )
            self.container.channel_runtime_manager.bind_account(
                ChannelAccountRuntimeBinding(
                    channel_type="webhook",
                    channel_account_id="default",
                    runtime_id="webhook-runtime-retry-1",
                ),
            )
            self.container.channel_interaction_service.upsert_interaction(
                ChannelInteraction(
                    interaction_id="webhook:default:run:retry-1",
                    channel_type="webhook",
                    channel_account_id="default",
                    external_conversation_id="ext-webhook-conv-retry-1",
                    reply_address={
                        "channel_type": "webhook",
                        "channel_account_id": "default",
                        "webhook_callback_url": f"{callback_server.base_url}/callback",
                        "external_conversation_id": "ext-webhook-conv-retry-1",
                    },
                    session_key="agent:demo:webhook-retry",
                    run_id="run-webhook-retry-1",
                    status="running",
                    metadata={
                        "observe_cursor": self.container.events_service.snapshot_event_topic(
                            turn_session_topic("agent:demo:webhook-retry"),
                        ),
                    },
                ),
            )
            self.container.events_service.publish(
                Event(
                    topic=turn_session_topic("agent:demo:webhook-retry"),
                    kind="fact",
                    payload={
                        "event_name": "orchestration.run.message.appended",
                        "run_id": "run-webhook-retry-1",
                        "session_key": "agent:demo:webhook-retry",
                        "message_id": "msg-webhook-retry-1",
                        "role": "assistant",
                        "kind": "message",
                        "message": {
                            "id": "msg-webhook-retry-1",
                            "content_payload": {
                                "blocks": [
                                    {"type": "text", "text": "please retry webhook runtime"},
                                ],
                            },
                            "created_at": "2026-04-16T00:00:00+00:00",
                        },
                    },
                ),
            )

            self.container.webhook_channel_runtime_service.run_runtime_loop(
                "webhook",
                runtime_id="webhook-runtime-retry-1",
                poll_interval_seconds=0.05,
                max_cycles=1,
            )

            self.assertEqual(len(callback_server.payloads), 3)
            runtime = self.container.channel_runtime_manager.get_runtime(
                "webhook-runtime-retry-1",
            )
            self.assertIsNotNone(runtime)
            assert runtime is not None
            self.assertEqual(runtime.metadata["observe_observed_count"], 1)
            self.assertEqual(runtime.metadata["observe_delivery_count"], 0)
            self.assertEqual(runtime.metadata["last_delivery_callback_status"], "http_503")

            dead_letters = self.container.events_service.read_event_topic(
                channel_dead_letter_topic(
                    "webhook",
                    runtime_id="webhook-runtime-retry-1",
                ),
            )
            self.assertEqual(len(dead_letters), 1)
            self.assertEqual(
                dead_letters[0].envelope.payload["event_name"],
                "channel.observation.dead_lettered",
            )
            self.assertEqual(dead_letters[0].envelope.payload["status"], "http_503")
            self.assertEqual(dead_letters[0].envelope.payload["attempt_count"], 3)
            self.assertEqual(
                dead_letters[0].envelope.payload["outbound_id"],
                "msg-webhook-retry-1",
            )
        finally:
            callback_server.close()

    def test_lark_channel_runtime_fetches_token_and_sends_text_message(self) -> None:
        self.container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="lark",
                accounts=(
                    ChannelAccountProfile(
                        account_id="default",
                        transport_mode="webhook",
                        metadata={
                            "lark_app_id": "cli_a",
                            "lark_app_secret": "secret_a",
                        },
                    ),
                ),
            ),
        )
        self.container.lark_channel_runtime_service.ensure_registered(
            runtime_id="lark-runtime-1",
        )
        self.container.channel_interaction_service.upsert_interaction(
            ChannelInteraction(
                interaction_id="lark:default:event:text-observe-1",
                channel_type="lark",
                channel_account_id="default",
                external_event_id="text-observe-1",
                external_conversation_id="oc_chat_1",
                external_user_id="ou_user_1",
                reply_address={
                    "channel_type": "lark",
                    "channel_account_id": "default",
                    "external_conversation_id": "oc_chat_1",
                    "external_user_id": "ou_user_1",
                    "metadata": {"receive_id_type": "chat_id"},
                },
                agent_id="assistant",
                session_key="agent:assistant:lark:dm:ou_user_1",
                run_id="run-lark-text-1",
                status="running",
            ),
        )
        self.container.events_service.publish(
            Event(
                topic=turn_session_topic("agent:assistant:lark:dm:ou_user_1"),
                kind="fact",
                ordering_key="run-lark-text-1",
                payload={
                    "event_name": "orchestration.run.message.appended",
                    "message_id": "msg-text-1",
                    "session_key": "agent:assistant:lark:dm:ou_user_1",
                    "session_id": "session-inst-text-1",
                    "role": "assistant",
                    "kind": "default",
                    "source_kind": "orchestration_run",
                    "source_id": "run-lark-text-1",
                    "message": {
                        "id": "msg-text-1",
                        "session_key": "agent:assistant:lark:dm:ou_user_1",
                        "session_id": "session-inst-text-1",
                        "sequence_no": 1,
                        "role": "assistant",
                        "kind": "default",
                        "content_payload": {
                            "blocks": [
                                {"type": "text", "text": "hello from lark runtime"},
                            ],
                        },
                        "source_kind": "orchestration_run",
                        "source_id": "run-lark-text-1",
                        "visibility": "default",
                        "metadata": {},
                        "created_at": "2026-04-16T00:00:00+00:00",
                    },
                },
            ),
        )
        calls: list[tuple[str, str, dict[str, object]]] = []

        def _fake_request(method: str, url: str, **kwargs):  # noqa: ANN001
            calls.append((method, url, dict(kwargs)))
            if url.endswith("/open-apis/auth/v3/tenant_access_token/internal"):
                return _FakeJsonResponse(
                    status_code=200,
                    payload={
                        "code": 0,
                        "tenant_access_token": "tenant-token-1",
                        "expire": 7200,
                    },
                )
            if url.endswith("/open-apis/im/v1/messages"):
                return _FakeJsonResponse(
                    status_code=200,
                    payload={"code": 0, "data": {"message_id": "om_msg_1"}},
                )
            raise AssertionError(f"unexpected lark url: {url}")

        with patch(
            "crxzipple.modules.channels.application.runtime.request_url",
            side_effect=_fake_request,
        ):
            self.container.lark_channel_runtime_service.run_runtime_loop(
                "lark",
                runtime_id="lark-runtime-1",
                poll_interval_seconds=0.05,
                max_cycles=1,
            )

        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0], "POST")
        self.assertTrue(
            calls[0][1].endswith("/open-apis/auth/v3/tenant_access_token/internal"),
        )
        self.assertEqual(
            calls[0][2]["json"],
            {"app_id": "cli_a", "app_secret": "secret_a"},
        )
        self.assertEqual(calls[1][0], "POST")
        self.assertTrue(calls[1][1].endswith("/open-apis/im/v1/messages"))
        self.assertEqual(calls[1][2]["params"], {"receive_id_type": "chat_id"})
        self.assertEqual(
            calls[1][2]["headers"]["Authorization"],
            "Bearer tenant-token-1",
        )
        self.assertEqual(calls[1][2]["json"]["receive_id"], "oc_chat_1")
        self.assertEqual(calls[1][2]["json"]["msg_type"], "text")
        self.assertEqual(
            json.loads(calls[1][2]["json"]["content"])["text"],
            "hello from lark runtime",
        )
        runtime = self.container.channel_runtime_manager.get_runtime("lark-runtime-1")
        self.assertIsNotNone(runtime)
        assert runtime is not None
        self.assertEqual(runtime.metadata["observe_observed_count"], 1)
        self.assertEqual(
            runtime.metadata["last_observe_event_name"],
            "orchestration.run.message.appended",
        )

    def test_lark_channel_runtime_delivers_text_and_artifacts_from_interaction_metadata(self) -> None:
        self.container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="lark",
                accounts=(
                    ChannelAccountProfile(
                        account_id="default",
                        transport_mode="webhook",
                        metadata={
                            "lark_app_id": "cli_a",
                            "lark_app_secret": "secret_a",
                        },
                    ),
                ),
            ),
        )
        self.container.lark_channel_runtime_service.ensure_registered(
            runtime_id="lark-runtime-artifact-1",
        )
        image_artifact = self.container.artifact_service.create_artifact(
            data=b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4////fwAJ+wP9KobjigAAAABJRU5ErkJggg==",
            ),
            mime_type="image/png",
            name="generated.png",
        )
        file_artifact = self.container.artifact_service.create_artifact(
            data=b"%PDF-1.4 test artifact\n",
            mime_type="application/pdf",
            name="report.pdf",
        )
        interaction = self.container.channel_interaction_service.upsert_interaction(
            ChannelInteraction(
                interaction_id="lark:default:event:artifact-delivery-1",
                channel_type="lark",
                channel_account_id="default",
                external_event_id="artifact-delivery-1",
                external_message_id="om_source_1",
                external_conversation_id="oc_chat_artifact_1",
                external_user_id="ou_artifact_1",
                reply_address={
                    "channel_type": "lark",
                    "channel_account_id": "default",
                    "external_conversation_id": "oc_chat_artifact_1",
                    "external_user_id": "ou_artifact_1",
                },
                agent_id="assistant",
                session_key="agent:assistant:lark:dm:ou_artifact_1",
                run_id="run-lark-artifact-1",
                status="running",
            ),
        )
        self.container.events_service.publish(
            Event(
                topic=turn_session_topic("agent:assistant:lark:dm:ou_artifact_1"),
                kind="fact",
                ordering_key="run-lark-artifact-1",
                payload={
                    "event_name": "orchestration.run.message.appended",
                    "message_id": "msg-artifact-observe-1",
                    "session_key": "agent:assistant:lark:dm:ou_artifact_1",
                    "session_id": "session-inst-artifact-1",
                    "role": "tool",
                    "kind": "tool_result",
                    "source_kind": "tool_run",
                    "source_id": "tool-run-artifact-1",
                    "message": {
                        "id": "msg-artifact-observe-1",
                        "session_key": "agent:assistant:lark:dm:ou_artifact_1",
                        "session_id": "session-inst-artifact-1",
                        "sequence_no": 2,
                        "role": "tool",
                        "kind": "tool_result",
                        "content_payload": {
                            "tool_name": "inline_media_tool",
                            "tool_run_id": "tool-run-artifact-1",
                            "status": "completed",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Here are the generated assets.",
                                },
                                {
                                    "type": "image_ref",
                                    "artifact_id": image_artifact.id,
                                    "mime_type": "image/png",
                                    "name": "generated.png",
                                },
                                {
                                    "type": "file_ref",
                                    "artifact_id": file_artifact.id,
                                    "mime_type": "application/pdf",
                                    "name": "report.pdf",
                                },
                            ],
                        },
                        "source_kind": "tool_run",
                        "source_id": "tool-run-artifact-1",
                        "visibility": "default",
                        "metadata": {"tool_name": "inline_media_tool"},
                        "created_at": "2026-04-16T00:00:00+00:00",
                    },
                },
            ),
        )
        calls: list[tuple[str, str, dict[str, object]]] = []

        def _fake_request(method: str, url: str, **kwargs):  # noqa: ANN001
            calls.append((method, url, dict(kwargs)))
            if url.endswith("/open-apis/auth/v3/tenant_access_token/internal"):
                return _FakeJsonResponse(
                    status_code=200,
                    payload={
                        "code": 0,
                        "tenant_access_token": "tenant-token-artifact-1",
                        "expire": 7200,
                    },
                )
            if url.endswith("/open-apis/im/v1/images"):
                self.assertEqual(kwargs["data"]["image_type"], "message")
                return _FakeJsonResponse(
                    status_code=200,
                    payload={"code": 0, "data": {"image_key": "img_v3_uploaded_1"}},
                )
            if url.endswith("/open-apis/im/v1/files"):
                self.assertEqual(kwargs["data"]["file_type"], "stream")
                self.assertEqual(kwargs["data"]["file_name"], "report.pdf")
                return _FakeJsonResponse(
                    status_code=200,
                    payload={"code": 0, "data": {"file_key": "file_v3_uploaded_1"}},
                )
            if url.endswith("/open-apis/im/v1/messages"):
                return _FakeJsonResponse(
                    status_code=200,
                    payload={"code": 0, "data": {"message_id": "om_msg_artifact_1"}},
                )
            raise AssertionError(f"unexpected lark url: {url}")

        with patch(
            "crxzipple.modules.channels.application.runtime.request_url",
            side_effect=_fake_request,
        ):
            self.container.lark_channel_runtime_service.run_runtime_loop(
                "lark",
                runtime_id="lark-runtime-artifact-1",
                poll_interval_seconds=0.05,
                max_cycles=1,
            )

        urls = [item[1] for item in calls]
        self.assertEqual(
            urls,
            [
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                "https://open.feishu.cn/open-apis/im/v1/images",
                "https://open.feishu.cn/open-apis/im/v1/files",
                "https://open.feishu.cn/open-apis/im/v1/messages",
                "https://open.feishu.cn/open-apis/im/v1/messages",
                "https://open.feishu.cn/open-apis/im/v1/messages",
            ],
        )
        message_payloads = [
            call[2]["json"]
            for call in calls
            if call[1].endswith("/open-apis/im/v1/messages")
        ]
        self.assertEqual(
            [payload["msg_type"] for payload in message_payloads],
            ["text", "image", "file"],
        )
        self.assertEqual(
            json.loads(message_payloads[0]["content"])["text"],
            "Here are the generated assets.",
        )
        self.assertEqual(
            json.loads(message_payloads[1]["content"])["image_key"],
            "img_v3_uploaded_1",
        )
        self.assertEqual(
            json.loads(message_payloads[2]["content"])["file_key"],
            "file_v3_uploaded_1",
        )

        refreshed = self.container.channel_interaction_service.get_interaction(
            interaction.interaction_id,
        )
        self.assertIsNotNone(refreshed)
        assert refreshed is not None
        self.assertEqual(refreshed.metadata["last_delivery_status"], "ok")
        self.assertEqual(
            refreshed.metadata["last_delivery_message_types"],
            ["text", "image", "file"],
        )
        self.assertEqual(
            refreshed.metadata["delivered_artifact_ids"],
            [image_artifact.id, file_artifact.id],
        )

    def test_lark_channel_runtime_preserves_thread_reply_context(self) -> None:
        self.container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="lark",
                accounts=(
                    ChannelAccountProfile(
                        account_id="default",
                        transport_mode="webhook",
                        metadata={
                            "lark_app_id": "cli_a",
                            "lark_app_secret": "secret_a",
                        },
                    ),
                ),
            ),
        )
        self.container.lark_channel_runtime_service.ensure_registered(
            runtime_id="lark-runtime-thread-1",
        )
        self.container.channel_interaction_service.upsert_interaction(
            ChannelInteraction(
                interaction_id="lark:default:event:thread-observe-1",
                channel_type="lark",
                channel_account_id="default",
                external_event_id="thread-observe-1",
                external_conversation_id="oc_chat_thread_1",
                external_user_id="ou_user_1",
                reply_address={
                    "channel_type": "lark",
                    "channel_account_id": "default",
                    "external_conversation_id": "oc_chat_thread_1",
                    "external_thread_id": "omt-thread-1",
                    "external_user_id": "ou_user_1",
                    "metadata": {
                        "receive_id_type": "chat_id",
                        "message_id": "om_msg_parent_1",
                        "reply_in_thread": True,
                    },
                },
                agent_id="assistant",
                session_key="agent:assistant:lark:thread:1",
                run_id="run-lark-thread-1",
                status="running",
            ),
        )
        self.container.events_service.publish(
            Event(
                topic=turn_session_topic("agent:assistant:lark:thread:1"),
                kind="fact",
                ordering_key="run-lark-thread-1",
                payload={
                    "event_name": "orchestration.run.message.appended",
                    "message_id": "msg-thread-1",
                    "session_key": "agent:assistant:lark:thread:1",
                    "session_id": "session-inst-thread-1",
                    "role": "assistant",
                    "kind": "default",
                    "source_kind": "orchestration_run",
                    "source_id": "run-lark-thread-1",
                    "message": {
                        "id": "msg-thread-1",
                        "session_key": "agent:assistant:lark:thread:1",
                        "session_id": "session-inst-thread-1",
                        "sequence_no": 1,
                        "role": "assistant",
                        "kind": "default",
                        "content_payload": {
                            "blocks": [
                                {"type": "text", "text": "thread reply from lark runtime"},
                            ],
                        },
                        "source_kind": "orchestration_run",
                        "source_id": "run-lark-thread-1",
                        "visibility": "default",
                        "metadata": {},
                        "created_at": "2026-04-16T00:00:00+00:00",
                    },
                },
            ),
        )
        calls: list[tuple[str, str, dict[str, object]]] = []

        def _fake_request(method: str, url: str, **kwargs):  # noqa: ANN001
            calls.append((method, url, dict(kwargs)))
            if url.endswith("/open-apis/auth/v3/tenant_access_token/internal"):
                return _FakeJsonResponse(
                    status_code=200,
                    payload={
                        "code": 0,
                        "tenant_access_token": "tenant-token-1",
                        "expire": 7200,
                    },
                )
            if url.endswith("/open-apis/im/v1/messages"):
                return _FakeJsonResponse(
                    status_code=200,
                    payload={"code": 0, "data": {"message_id": "om_msg_2"}},
                )
            raise AssertionError(f"unexpected lark url: {url}")

        with patch(
            "crxzipple.modules.channels.application.runtime.request_url",
            side_effect=_fake_request,
        ):
            self.container.lark_channel_runtime_service.run_runtime_loop(
                "lark",
                runtime_id="lark-runtime-thread-1",
                poll_interval_seconds=0.05,
                max_cycles=1,
            )

        self.assertEqual(len(calls), 2)
        send_payload = calls[1][2]["json"]
        self.assertEqual(send_payload["reply_in_thread"], True)
        self.assertEqual(send_payload["thread_id"], "omt-thread-1")
        self.assertEqual(send_payload["reply_message_id"], "om_msg_parent_1")

    def test_lark_channel_runtime_resolves_credentials_from_bindings(self) -> None:
        previous_app_id = os.environ.get("LARK_TEST_APP_ID")
        previous_app_secret = os.environ.get("LARK_TEST_APP_SECRET")
        os.environ["LARK_TEST_APP_ID"] = "cli_binding_a"
        os.environ["LARK_TEST_APP_SECRET"] = "secret_binding_a"
        try:
            self.container.channel_profile_service.upsert_profile(
                ChannelProfile(
                    channel_type="lark",
                    accounts=(
                        ChannelAccountProfile(
                            account_id="default",
                            transport_mode="webhook",
                            metadata={
                                "lark_app_id_binding": "env:LARK_TEST_APP_ID",
                                "lark_app_secret_binding": "env:LARK_TEST_APP_SECRET",
                            },
                        ),
                    ),
                ),
            )
            self.container.lark_channel_runtime_service.ensure_registered(
                runtime_id="lark-runtime-binding-1",
            )
            self.container.channel_interaction_service.upsert_interaction(
                ChannelInteraction(
                    interaction_id="lark:default:event:binding-observe-1",
                    channel_type="lark",
                    channel_account_id="default",
                    external_event_id="binding-observe-1",
                    external_conversation_id="oc_chat_binding_1",
                    external_user_id="ou_user_binding_1",
                    reply_address={
                        "channel_type": "lark",
                        "channel_account_id": "default",
                        "external_conversation_id": "oc_chat_binding_1",
                        "external_user_id": "ou_user_binding_1",
                        "metadata": {"receive_id_type": "chat_id"},
                    },
                    agent_id="assistant",
                    session_key="agent:assistant:lark:binding:1",
                    run_id="run-lark-binding-1",
                    status="running",
                ),
            )
            self.container.events_service.publish(
                Event(
                    topic=turn_session_topic("agent:assistant:lark:binding:1"),
                    kind="fact",
                    ordering_key="run-lark-binding-1",
                    payload={
                        "event_name": "orchestration.run.message.appended",
                        "message_id": "msg-binding-1",
                        "session_key": "agent:assistant:lark:binding:1",
                        "session_id": "session-inst-binding-1",
                        "role": "assistant",
                        "kind": "default",
                        "source_kind": "orchestration_run",
                        "source_id": "run-lark-binding-1",
                        "message": {
                            "id": "msg-binding-1",
                            "session_key": "agent:assistant:lark:binding:1",
                            "session_id": "session-inst-binding-1",
                            "sequence_no": 1,
                            "role": "assistant",
                            "kind": "default",
                            "content_payload": {
                                "blocks": [
                                    {
                                        "type": "text",
                                        "text": "hello from bound lark runtime",
                                    },
                                ],
                            },
                            "source_kind": "orchestration_run",
                            "source_id": "run-lark-binding-1",
                            "visibility": "default",
                            "metadata": {},
                            "created_at": "2026-04-16T00:00:00+00:00",
                        },
                    },
                ),
            )
            calls: list[tuple[str, str, dict[str, object]]] = []

            def _fake_request(method: str, url: str, **kwargs):  # noqa: ANN001
                calls.append((method, url, dict(kwargs)))
                if url.endswith("/open-apis/auth/v3/tenant_access_token/internal"):
                    return _FakeJsonResponse(
                        status_code=200,
                        payload={
                            "code": 0,
                            "tenant_access_token": "tenant-token-binding-1",
                            "expire": 7200,
                        },
                    )
                if url.endswith("/open-apis/im/v1/messages"):
                    return _FakeJsonResponse(
                        status_code=200,
                        payload={"code": 0, "data": {"message_id": "om_msg_binding_1"}},
                    )
                raise AssertionError(f"unexpected lark url: {url}")

            with patch(
                "crxzipple.modules.channels.application.runtime.request_url",
                side_effect=_fake_request,
            ):
                self.container.lark_channel_runtime_service.run_runtime_loop(
                    "lark",
                    runtime_id="lark-runtime-binding-1",
                    poll_interval_seconds=0.05,
                    max_cycles=1,
                )

            self.assertEqual(calls[0][2]["json"], {"app_id": "cli_binding_a", "app_secret": "secret_binding_a"})
        finally:
            if previous_app_id is None:
                os.environ.pop("LARK_TEST_APP_ID", None)
            else:
                os.environ["LARK_TEST_APP_ID"] = previous_app_id
            if previous_app_secret is None:
                os.environ.pop("LARK_TEST_APP_SECRET", None)
            else:
                os.environ["LARK_TEST_APP_SECRET"] = previous_app_secret

    def test_lark_submit_message_event_creates_interaction_and_defers_session_binding(self) -> None:
        self.container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="lark",
                accounts=(
                    ChannelAccountProfile(
                        account_id="default",
                        transport_mode="long_connection",
                        metadata={"agent_id": "assistant"},
                    ),
                ),
            ),
        )
        self.container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="test-llm",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
            ),
        )
        self.container.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="assistant",
                name="Assistant",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Be helpful.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(default_llm_id="test-llm"),
                runtime_preferences=AgentRuntimePreferences(),
            ),
        )

        result = self.container.lark_channel_runtime_service.submit_message_event(
            "default",
            event_id="evt_lark_1",
            sender_open_id="ou_sender_1",
            message={
                "chat_id": "oc_chat_direct_1",
                "chat_type": "p2p",
                "message_id": "om_lark_1",
                "content": json.dumps({"text": "hello from lark direct"}),
            },
        )

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(
            result["interaction_id"],
            "lark:default:event:evt_lark_1",
        )
        self.assertIsNone(result["session_key"])
        self.assertEqual(result["interaction_status"], "accepted")

        interaction = self.container.channel_interaction_service.get_interaction(
            "lark:default:event:evt_lark_1",
        )
        self.assertIsNotNone(interaction)
        assert interaction is not None
        self.assertEqual(interaction.channel_type, "lark")
        self.assertEqual(interaction.run_id, result["run_id"])
        self.assertEqual(interaction.session_key, result["session_key"])
        self.assertEqual(interaction.agent_id, "assistant")
        self.assertEqual(interaction.status, "accepted")
        self.assertEqual(interaction.external_user_id, "ou_sender_1")
        self.assertEqual(interaction.external_conversation_id, "oc_chat_direct_1")
        self.assertEqual(
            interaction.reply_address["external_user_id"],
            "ou_sender_1",
        )
        self.assertEqual(interaction.metadata["chat_type"], "direct")

        queued = self.container.orchestration_scheduler_service.process_run_request(
            run_id=result["run_id"],
            worker_id="scheduler-lark-direct-1",
        )
        self.assertIsNotNone(queued)
        assert queued is not None
        refreshed = self.container.channel_interaction_service.get_interaction(
            "lark:default:event:evt_lark_1",
        )
        self.assertIsNotNone(refreshed)
        assert refreshed is not None
        self.assertEqual(refreshed.session_key, queued.session_key)
        self.assertEqual(refreshed.status, "queued")
        self.assertEqual(
            refreshed.metadata["active_session_id"],
            queued.active_session_id,
        )

    def test_lark_runtime_observes_run_events_and_updates_interaction_status(self) -> None:
        self.container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="lark",
                accounts=(
                    ChannelAccountProfile(
                        account_id="default",
                        transport_mode="webhook",
                    ),
                ),
            ),
        )
        self.container.lark_channel_runtime_service.ensure_registered(
            runtime_id="lark-runtime-observe-1",
        )
        interaction = self.container.channel_interaction_service.upsert_interaction(
            ChannelInteraction(
                interaction_id="lark:default:event:observe-1",
                channel_type="lark",
                channel_account_id="default",
                external_event_id="observe-1",
                external_conversation_id="oc_chat_observe_1",
                external_user_id="ou_observe_1",
                reply_address={
                    "channel_type": "lark",
                    "channel_account_id": "default",
                    "external_conversation_id": "oc_chat_observe_1",
                    "external_user_id": "ou_observe_1",
                },
                agent_id="assistant",
                session_key="agent:assistant:lark:dm:ou_observe_1",
                run_id="run-lark-observe-1",
                status="submitted",
            ),
        )
        self.container.events_service.publish(
            Event(
                topic=turn_session_topic("agent:assistant:lark:dm:ou_observe_1"),
                kind="fact",
                ordering_key="run-lark-observe-1",
                payload={
                    "event_name": "orchestration.run.advanced",
                    "run_id": "run-lark-observe-1",
                    "session_key": "agent:assistant:lark:dm:ou_observe_1",
                    "status": "running",
                    "stage": "llm_generating",
                    "current_step": 1,
                    "active_session_id": "session-inst-1",
                },
            ),
        )
        self.container.events_service.publish(
            Event(
                topic=turn_session_topic("agent:assistant:lark:dm:ou_observe_1"),
                kind="fact",
                ordering_key="run-lark-observe-1",
                payload={
                    "event_name": "orchestration.run.completed",
                    "run_id": "run-lark-observe-1",
                    "session_key": "agent:assistant:lark:dm:ou_observe_1",
                    "status": "completed",
                    "stage": "completed",
                    "current_step": 1,
                    "active_session_id": "session-inst-1",
                },
            ),
        )

        self.container.lark_channel_runtime_service.run_runtime_loop(
            "lark",
            runtime_id="lark-runtime-observe-1",
            poll_interval_seconds=0.05,
            max_cycles=1,
        )

        refreshed = self.container.channel_interaction_service.get_interaction(
            interaction.interaction_id,
        )
        self.assertIsNotNone(refreshed)
        assert refreshed is not None
        self.assertEqual(refreshed.status, "completed")
        self.assertEqual(
            refreshed.metadata["last_run_event_name"],
            "orchestration.run.completed",
        )
        self.assertEqual(
            refreshed.metadata["last_observed_event_name"],
            "orchestration.run.completed",
        )
        self.assertEqual(refreshed.metadata["stage"], "completed")
        self.assertEqual(refreshed.metadata["current_step"], 1)
        self.assertTrue(str(refreshed.metadata["observe_cursor"]).strip())

        runtime = self.container.channel_runtime_manager.get_runtime(
            "lark-runtime-observe-1",
        )
        self.assertIsNotNone(runtime)
        assert runtime is not None
        self.assertEqual(runtime.metadata["observe_observed_count"], 2)
        self.assertEqual(runtime.metadata["observe_transition_count"], 2)
        self.assertEqual(
            runtime.metadata["last_observe_event_name"],
            "orchestration.run.completed",
        )
        self.assertEqual(
            runtime.metadata["last_observe_interaction_id"],
            interaction.interaction_id,
        )

    def test_lark_runtime_projects_tool_result_artifacts_into_interaction_metadata(self) -> None:
        self.container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="lark",
                accounts=(
                    ChannelAccountProfile(
                        account_id="default",
                        transport_mode="webhook",
                    ),
                ),
            ),
        )
        self.container.lark_channel_runtime_service.ensure_registered(
            runtime_id="lark-runtime-message-1",
        )
        interaction = self.container.channel_interaction_service.upsert_interaction(
            ChannelInteraction(
                interaction_id="lark:default:event:message-1",
                channel_type="lark",
                channel_account_id="default",
                external_event_id="message-1",
                external_conversation_id="oc_chat_message_1",
                external_user_id="ou_message_1",
                reply_address={
                    "channel_type": "lark",
                    "channel_account_id": "default",
                    "external_conversation_id": "oc_chat_message_1",
                    "external_user_id": "ou_message_1",
                },
                agent_id="assistant",
                session_key="agent:assistant:lark:dm:ou_message_1",
                run_id="run-lark-message-1",
                status="running",
                metadata={"active_session_id": "session-inst-msg-1"},
            ),
        )
        self.container.events_service.publish(
            Event(
                topic=turn_session_topic("agent:assistant:lark:dm:ou_message_1"),
                kind="fact",
                ordering_key="run-lark-message-1",
                payload={
                    "event_name": "orchestration.run.message.appended",
                    "message_id": "msg-tool-1",
                    "session_key": "agent:assistant:lark:dm:ou_message_1",
                    "session_id": "session-inst-msg-1",
                    "role": "tool",
                    "kind": "tool_result",
                    "source_kind": "tool_run",
                    "source_id": "tool-run-1",
                    "message": {
                        "id": "msg-tool-1",
                        "session_key": "agent:assistant:lark:dm:ou_message_1",
                        "session_id": "session-inst-msg-1",
                        "sequence_no": 3,
                        "role": "tool",
                        "kind": "tool_result",
                        "content_payload": {
                            "tool_name": "inline_image_tool",
                            "tool_call_id": "call-inline-1",
                            "tool_run_id": "tool-run-1",
                            "status": "completed",
                            "content": [
                                {"type": "text", "text": "Generated image."},
                                {
                                    "type": "image_ref",
                                    "artifact_id": "artifact-inline-1",
                                    "mime_type": "image/png",
                                    "name": "generated.png",
                                    "preview_url": "/artifacts/artifact-inline-1/preview",
                                    "original_url": "/artifacts/artifact-inline-1/original",
                                },
                            ],
                        },
                        "source_kind": "tool_run",
                        "source_id": "tool-run-1",
                        "visibility": "default",
                        "metadata": {"tool_name": "inline_image_tool"},
                        "created_at": "2026-04-16T00:00:00+00:00",
                    },
                },
            ),
        )

        self.container.lark_channel_runtime_service.run_runtime_loop(
            "lark",
            runtime_id="lark-runtime-message-1",
            poll_interval_seconds=0.05,
            max_cycles=1,
        )

        refreshed = self.container.channel_interaction_service.get_interaction(
            interaction.interaction_id,
        )
        self.assertIsNotNone(refreshed)
        assert refreshed is not None
        self.assertEqual(refreshed.status, "running")
        self.assertEqual(refreshed.metadata["last_message_id"], "msg-tool-1")
        self.assertEqual(refreshed.metadata["last_message_kind"], "tool_result")
        self.assertEqual(refreshed.metadata["last_message_summary"], "Generated image.")
        self.assertEqual(
            refreshed.metadata["last_message_block_types"],
            ["text", "image_ref"],
        )
        self.assertEqual(
            refreshed.metadata["last_tool_result"]["tool_name"],
            "inline_image_tool",
        )
        self.assertEqual(
            refreshed.metadata["last_tool_result"]["tool_run_id"],
            "tool-run-1",
        )
        self.assertEqual(
            refreshed.metadata["last_tool_result"]["summary"],
            "Generated image.",
        )
        self.assertEqual(
            refreshed.metadata["last_message_artifact_refs"][0]["artifact_id"],
            "artifact-inline-1",
        )
        self.assertEqual(
            refreshed.metadata["last_message_artifact_refs"][0]["type"],
            "image_ref",
        )
        self.assertTrue(refreshed.metadata["last_message_has_image_artifacts"])
        self.assertFalse(refreshed.metadata["last_message_has_file_artifacts"])
        self.assertEqual(
            refreshed.metadata["last_observed_event_name"],
            "orchestration.run.message.appended",
        )

    def test_lark_runtime_projects_assistant_message_directly_from_observe(self) -> None:
        self.container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="lark",
                accounts=(
                    ChannelAccountProfile(
                        account_id="default",
                        transport_mode="webhook",
                        metadata={
                            "lark_app_id": "cli_a",
                            "lark_app_secret": "secret_a",
                        },
                    ),
                ),
            ),
        )
        self.container.lark_channel_runtime_service.ensure_registered(
            runtime_id="lark-runtime-observe-send-1",
        )
        interaction = self.container.channel_interaction_service.upsert_interaction(
            ChannelInteraction(
                interaction_id="lark:default:event:assistant-observe-1",
                channel_type="lark",
                channel_account_id="default",
                external_event_id="assistant-observe-1",
                external_conversation_id="oc_chat_assistant_1",
                external_user_id="ou_assistant_1",
                reply_address={
                    "channel_type": "lark",
                    "channel_account_id": "default",
                    "external_conversation_id": "oc_chat_assistant_1",
                    "external_user_id": "ou_assistant_1",
                    "metadata": {
                        "receive_id_type": "chat_id",
                    },
                },
                agent_id="assistant",
                session_key="agent:assistant:lark:dm:ou_assistant_1",
                run_id="run-lark-assistant-1",
                status="running",
            ),
        )
        legacy_cursor = self.container.events_service.snapshot_event_topic(
            _legacy_runtime_outbound_topic("lark-runtime-observe-send-1"),
        )
        self.container.events_service.publish(
            Event(
                topic=turn_session_topic("agent:assistant:lark:dm:ou_assistant_1"),
                kind="fact",
                ordering_key="run-lark-assistant-1",
                payload={
                    "event_name": "orchestration.run.message.appended",
                    "message_id": "msg-assistant-1",
                    "session_key": "agent:assistant:lark:dm:ou_assistant_1",
                    "session_id": "session-inst-assistant-1",
                    "role": "assistant",
                    "kind": "default",
                    "source_kind": "orchestration_run",
                    "source_id": "run-lark-assistant-1",
                    "message": {
                        "id": "msg-assistant-1",
                        "session_key": "agent:assistant:lark:dm:ou_assistant_1",
                        "session_id": "session-inst-assistant-1",
                        "sequence_no": 4,
                        "role": "assistant",
                        "kind": "default",
                        "content_payload": {
                            "blocks": [
                                {
                                    "type": "text",
                                    "text": "assistant result from observe",
                                },
                            ],
                        },
                        "source_kind": "orchestration_run",
                        "source_id": "run-lark-assistant-1",
                        "visibility": "default",
                        "metadata": {},
                        "created_at": "2026-04-16T00:01:00+00:00",
                    },
                },
            ),
        )
        calls: list[tuple[str, str, dict[str, object]]] = []

        def _fake_request(method: str, url: str, **kwargs):  # noqa: ANN001
            calls.append((method, url, dict(kwargs)))
            if url.endswith("/open-apis/auth/v3/tenant_access_token/internal"):
                return _FakeJsonResponse(
                    status_code=200,
                    payload={
                        "code": 0,
                        "tenant_access_token": "tenant-token-observe-1",
                        "expire": 7200,
                    },
                )
            if url.endswith("/open-apis/im/v1/messages"):
                return _FakeJsonResponse(
                    status_code=200,
                    payload={"code": 0, "data": {"message_id": "om_msg_observe_1"}},
                )
            raise AssertionError(f"unexpected lark url: {url}")

        with patch(
            "crxzipple.modules.channels.application.runtime.request_url",
            side_effect=_fake_request,
        ):
            self.container.lark_channel_runtime_service.run_runtime_loop(
                "lark",
                runtime_id="lark-runtime-observe-send-1",
                poll_interval_seconds=0.05,
                max_cycles=1,
            )

        self.assertEqual(len(calls), 2)
        self.assertTrue(
            calls[0][1].endswith("/open-apis/auth/v3/tenant_access_token/internal"),
        )
        self.assertTrue(calls[1][1].endswith("/open-apis/im/v1/messages"))
        self.assertEqual(calls[1][2]["params"], {"receive_id_type": "chat_id"})
        self.assertEqual(
            json.loads(calls[1][2]["json"]["content"])["text"],
            "assistant result from observe",
        )
        legacy_records = self.container.events_service.read_event_topic(
            _legacy_runtime_outbound_topic("lark-runtime-observe-send-1"),
            after_cursor=legacy_cursor,
            limit=10,
        )
        self.assertEqual(legacy_records, ())
        refreshed = self.container.channel_interaction_service.get_interaction(
            interaction.interaction_id,
        )
        self.assertIsNotNone(refreshed)
        assert refreshed is not None
        self.assertEqual(refreshed.metadata["last_delivered_message_id"], "msg-assistant-1")
        self.assertEqual(refreshed.metadata["last_delivery_status"], "ok")
        self.assertEqual(
            refreshed.metadata["last_delivery_message_types"],
            ["text"],
        )

    def test_lark_runtime_projects_tool_result_to_lark_without_legacy_runtime_topic(self) -> None:
        self.container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="lark",
                accounts=(
                    ChannelAccountProfile(
                        account_id="default",
                        transport_mode="webhook",
                        metadata={
                            "lark_app_id": "cli_a",
                            "lark_app_secret": "secret_a",
                        },
                    ),
                ),
            ),
        )
        self.container.lark_channel_runtime_service.ensure_registered(
            runtime_id="lark-runtime-observe-tool-1",
        )
        image_artifact = self.container.artifact_service.create_artifact(
            data=b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4////fwAJ+wP9KobjigAAAABJRU5ErkJggg==",
            ),
            mime_type="image/png",
            name="generated-observe.png",
        )
        interaction = self.container.channel_interaction_service.upsert_interaction(
            ChannelInteraction(
                interaction_id="lark:default:event:tool-observe-1",
                channel_type="lark",
                channel_account_id="default",
                external_event_id="tool-observe-1",
                external_conversation_id="oc_chat_tool_observe_1",
                external_user_id="ou_tool_observe_1",
                reply_address={
                    "channel_type": "lark",
                    "channel_account_id": "default",
                    "external_conversation_id": "oc_chat_tool_observe_1",
                    "external_user_id": "ou_tool_observe_1",
                    "metadata": {
                        "receive_id_type": "chat_id",
                    },
                },
                agent_id="assistant",
                session_key="agent:assistant:lark:dm:ou_tool_observe_1",
                run_id="run-lark-tool-observe-1",
                status="running",
            ),
        )
        self.container.events_service.publish(
            Event(
                topic=turn_session_topic("agent:assistant:lark:dm:ou_tool_observe_1"),
                kind="fact",
                ordering_key="run-lark-tool-observe-1",
                payload={
                    "event_name": "orchestration.run.message.appended",
                    "message_id": "msg-tool-observe-1",
                    "session_key": "agent:assistant:lark:dm:ou_tool_observe_1",
                    "session_id": "session-inst-tool-observe-1",
                    "role": "tool",
                    "kind": "tool_result",
                    "source_kind": "tool_run",
                    "source_id": "tool-run-observe-1",
                    "message": {
                        "id": "msg-tool-observe-1",
                        "session_key": "agent:assistant:lark:dm:ou_tool_observe_1",
                        "session_id": "session-inst-tool-observe-1",
                        "sequence_no": 5,
                        "role": "tool",
                        "kind": "tool_result",
                        "content_payload": {
                            "tool_name": "inline_image_tool",
                            "tool_run_id": "tool-run-observe-1",
                            "status": "completed",
                            "content": [
                                {"type": "text", "text": "Generated image from observe."},
                                {
                                    "type": "image_ref",
                                    "artifact_id": image_artifact.id,
                                    "mime_type": "image/png",
                                    "name": "generated-observe.png",
                                },
                            ],
                        },
                        "source_kind": "tool_run",
                        "source_id": "tool-run-observe-1",
                        "visibility": "default",
                        "metadata": {"tool_name": "inline_image_tool"},
                        "created_at": "2026-04-16T00:02:00+00:00",
                    },
                },
            ),
        )
        calls: list[tuple[str, str, dict[str, object]]] = []

        def _fake_request(method: str, url: str, **kwargs):  # noqa: ANN001
            calls.append((method, url, dict(kwargs)))
            if url.endswith("/open-apis/auth/v3/tenant_access_token/internal"):
                return _FakeJsonResponse(
                    status_code=200,
                    payload={
                        "code": 0,
                        "tenant_access_token": "tenant-token-tool-observe-1",
                        "expire": 7200,
                    },
                )
            if url.endswith("/open-apis/im/v1/images"):
                return _FakeJsonResponse(
                    status_code=200,
                    payload={"code": 0, "data": {"image_key": "img_v3_observe_1"}},
                )
            if url.endswith("/open-apis/im/v1/messages"):
                return _FakeJsonResponse(
                    status_code=200,
                    payload={"code": 0, "data": {"message_id": "om_msg_tool_observe_1"}},
                )
            raise AssertionError(f"unexpected lark url: {url}")

        with patch(
            "crxzipple.modules.channels.application.runtime.request_url",
            side_effect=_fake_request,
        ):
            self.container.lark_channel_runtime_service.run_runtime_loop(
                "lark",
                runtime_id="lark-runtime-observe-tool-1",
                poll_interval_seconds=0.05,
                max_cycles=1,
            )

        urls = [item[1] for item in calls]
        self.assertEqual(
            urls,
            [
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                "https://open.feishu.cn/open-apis/im/v1/images",
                "https://open.feishu.cn/open-apis/im/v1/messages",
                "https://open.feishu.cn/open-apis/im/v1/messages",
            ],
        )
        message_payloads = [
            call[2]["json"]
            for call in calls
            if call[1].endswith("/open-apis/im/v1/messages")
        ]
        self.assertEqual(
            [payload["msg_type"] for payload in message_payloads],
            ["text", "image"],
        )
        self.assertEqual(
            json.loads(message_payloads[0]["content"])["text"],
            "Generated image from observe.",
        )
        self.assertEqual(
            json.loads(message_payloads[1]["content"])["image_key"],
            "img_v3_observe_1",
        )
        refreshed = self.container.channel_interaction_service.get_interaction(
            interaction.interaction_id,
        )
        self.assertIsNotNone(refreshed)
        assert refreshed is not None
        self.assertEqual(refreshed.metadata["last_delivered_message_id"], "msg-tool-observe-1")
        self.assertEqual(
            refreshed.metadata["delivered_artifact_ids"],
            [image_artifact.id],
        )

    def test_lark_channel_runtime_uses_open_id_for_direct_replies_by_default(self) -> None:
        self.container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="lark",
                accounts=(
                    ChannelAccountProfile(
                        account_id="default",
                        transport_mode="webhook",
                        metadata={
                            "lark_app_id": "cli_a",
                            "lark_app_secret": "secret_a",
                        },
                    ),
                ),
            ),
        )
        self.container.lark_channel_runtime_service.ensure_registered(
            runtime_id="lark-runtime-direct-1",
        )
        self.container.channel_interaction_service.upsert_interaction(
            ChannelInteraction(
                interaction_id="lark:default:event:direct-observe-1",
                channel_type="lark",
                channel_account_id="default",
                external_event_id="direct-observe-1",
                external_conversation_id="oc_chat_direct_1",
                external_user_id="ou_user_direct_1",
                reply_address={
                    "channel_type": "lark",
                    "channel_account_id": "default",
                    "external_conversation_id": "oc_chat_direct_1",
                    "external_user_id": "ou_user_direct_1",
                    "metadata": {"chat_type": "direct"},
                },
                agent_id="assistant",
                session_key="agent:assistant:lark:dm:ou_user_direct_1",
                run_id="run-lark-direct-1",
                status="running",
            ),
        )
        self.container.events_service.publish(
            Event(
                topic=turn_session_topic("agent:assistant:lark:dm:ou_user_direct_1"),
                kind="fact",
                ordering_key="run-lark-direct-1",
                payload={
                    "event_name": "orchestration.run.message.appended",
                    "message_id": "msg-direct-1",
                    "session_key": "agent:assistant:lark:dm:ou_user_direct_1",
                    "session_id": "session-inst-direct-1",
                    "role": "assistant",
                    "kind": "default",
                    "source_kind": "orchestration_run",
                    "source_id": "run-lark-direct-1",
                    "message": {
                        "id": "msg-direct-1",
                        "session_key": "agent:assistant:lark:dm:ou_user_direct_1",
                        "session_id": "session-inst-direct-1",
                        "sequence_no": 1,
                        "role": "assistant",
                        "kind": "default",
                        "content_payload": {
                            "blocks": [
                                {"type": "text", "text": "direct reply from lark runtime"},
                            ],
                        },
                        "source_kind": "orchestration_run",
                        "source_id": "run-lark-direct-1",
                        "visibility": "default",
                        "metadata": {},
                        "created_at": "2026-04-16T00:00:00+00:00",
                    },
                },
            ),
        )
        calls: list[tuple[str, str, dict[str, object]]] = []

        def _fake_request(method: str, url: str, **kwargs):  # noqa: ANN001
            calls.append((method, url, dict(kwargs)))
            if url.endswith("/open-apis/auth/v3/tenant_access_token/internal"):
                return _FakeJsonResponse(
                    status_code=200,
                    payload={
                        "code": 0,
                        "tenant_access_token": "tenant-token-1",
                        "expire": 7200,
                    },
                )
            if url.endswith("/open-apis/im/v1/messages"):
                return _FakeJsonResponse(
                    status_code=200,
                    payload={"code": 0, "data": {"message_id": "om_msg_3"}},
                )
            raise AssertionError(f"unexpected lark url: {url}")

        with patch(
            "crxzipple.modules.channels.application.runtime.request_url",
            side_effect=_fake_request,
        ):
            self.container.lark_channel_runtime_service.run_runtime_loop(
                "lark",
                runtime_id="lark-runtime-direct-1",
                poll_interval_seconds=0.05,
                max_cycles=1,
            )

        self.assertEqual(len(calls), 2)
        send_call = calls[1]
        self.assertEqual(send_call[2]["params"], {"receive_id_type": "open_id"})
        self.assertEqual(send_call[2]["json"]["receive_id"], "ou_user_direct_1")

    def test_lark_channel_runtime_allows_account_receive_id_override(self) -> None:
        self.container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="lark",
                accounts=(
                    ChannelAccountProfile(
                        account_id="default",
                        transport_mode="webhook",
                        metadata={
                            "lark_app_id": "cli_a",
                            "lark_app_secret": "secret_a",
                            "lark_receive_id_type": "chat_id",
                        },
                    ),
                ),
            ),
        )
        self.container.lark_channel_runtime_service.ensure_registered(
            runtime_id="lark-runtime-override-1",
        )
        self.container.channel_interaction_service.upsert_interaction(
            ChannelInteraction(
                interaction_id="lark:default:event:override-observe-1",
                channel_type="lark",
                channel_account_id="default",
                external_event_id="override-observe-1",
                external_conversation_id="oc_chat_override_1",
                external_user_id="ou_user_override_1",
                reply_address={
                    "channel_type": "lark",
                    "channel_account_id": "default",
                    "external_conversation_id": "oc_chat_override_1",
                    "external_user_id": "ou_user_override_1",
                    "metadata": {"chat_type": "direct"},
                },
                agent_id="assistant",
                session_key="agent:assistant:lark:dm:ou_user_override_1",
                run_id="run-lark-override-1",
                status="running",
            ),
        )
        self.container.events_service.publish(
            Event(
                topic=turn_session_topic("agent:assistant:lark:dm:ou_user_override_1"),
                kind="fact",
                ordering_key="run-lark-override-1",
                payload={
                    "event_name": "orchestration.run.message.appended",
                    "message_id": "msg-override-1",
                    "session_key": "agent:assistant:lark:dm:ou_user_override_1",
                    "session_id": "session-inst-override-1",
                    "role": "assistant",
                    "kind": "default",
                    "source_kind": "orchestration_run",
                    "source_id": "run-lark-override-1",
                    "message": {
                        "id": "msg-override-1",
                        "session_key": "agent:assistant:lark:dm:ou_user_override_1",
                        "session_id": "session-inst-override-1",
                        "sequence_no": 1,
                        "role": "assistant",
                        "kind": "default",
                        "content_payload": {
                            "blocks": [
                                {"type": "text", "text": "override reply from lark runtime"},
                            ],
                        },
                        "source_kind": "orchestration_run",
                        "source_id": "run-lark-override-1",
                        "visibility": "default",
                        "metadata": {},
                        "created_at": "2026-04-16T00:00:00+00:00",
                    },
                },
            ),
        )
        calls: list[tuple[str, str, dict[str, object]]] = []

        def _fake_request(method: str, url: str, **kwargs):  # noqa: ANN001
            calls.append((method, url, dict(kwargs)))
            if url.endswith("/open-apis/auth/v3/tenant_access_token/internal"):
                return _FakeJsonResponse(
                    status_code=200,
                    payload={
                        "code": 0,
                        "tenant_access_token": "tenant-token-1",
                        "expire": 7200,
                    },
                )
            if url.endswith("/open-apis/im/v1/messages"):
                return _FakeJsonResponse(
                    status_code=200,
                    payload={"code": 0, "data": {"message_id": "om_msg_4"}},
                )
            raise AssertionError(f"unexpected lark url: {url}")

        with patch(
            "crxzipple.modules.channels.application.runtime.request_url",
            side_effect=_fake_request,
        ):
            self.container.lark_channel_runtime_service.run_runtime_loop(
                "lark",
                runtime_id="lark-runtime-override-1",
                poll_interval_seconds=0.05,
                max_cycles=1,
            )

        self.assertEqual(len(calls), 2)
        send_call = calls[1]
        self.assertEqual(send_call[2]["params"], {"receive_id_type": "chat_id"})
        self.assertEqual(send_call[2]["json"]["receive_id"], "oc_chat_override_1")

    def test_lark_channel_runtime_resolves_bot_open_id_via_bot_info(self) -> None:
        self.container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="lark",
                accounts=(
                    ChannelAccountProfile(
                        account_id="default",
                        transport_mode="webhook",
                        metadata={
                            "lark_app_id": "cli_a",
                            "lark_app_secret": "secret_a",
                        },
                    ),
                ),
            ),
        )
        calls: list[tuple[str, str, dict[str, object]]] = []

        def _fake_request(method: str, url: str, **kwargs):  # noqa: ANN001
            calls.append((method, url, dict(kwargs)))
            if url.endswith("/open-apis/auth/v3/tenant_access_token/internal"):
                return _FakeJsonResponse(
                    status_code=200,
                    payload={
                        "code": 0,
                        "tenant_access_token": "tenant-token-1",
                        "expire": 7200,
                    },
                )
            if url.endswith("/open-apis/bot/v3/info"):
                return _FakeJsonResponse(
                    status_code=200,
                    payload={
                        "code": 0,
                        "msg": "ok",
                        "bot": {
                            "open_id": "ou_bot_resolved_1",
                        },
                    },
                )
            raise AssertionError(f"unexpected lark url: {url}")

        with patch(
            "crxzipple.modules.channels.application.runtime.request_url",
            side_effect=_fake_request,
        ):
            open_id = self.container.lark_channel_runtime_service.resolve_bot_open_id_for_account(
                "default",
            )
            second_open_id = self.container.lark_channel_runtime_service.resolve_bot_open_id_for_account(
                "default",
            )

        self.assertEqual(open_id, "ou_bot_resolved_1")
        self.assertEqual(second_open_id, "ou_bot_resolved_1")
        self.assertEqual(len(calls), 2)
        self.assertTrue(
            calls[0][1].endswith("/open-apis/auth/v3/tenant_access_token/internal"),
        )
        self.assertTrue(calls[1][1].endswith("/open-apis/bot/v3/info"))

    def test_lark_channel_runtime_starts_long_connection_ingress_for_long_connection_account(
        self,
    ) -> None:
        self.container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="lark",
                enabled=True,
                accounts=(
                    ChannelAccountProfile(
                        account_id="default",
                        enabled=True,
                        transport_mode="long_connection",
                        metadata={
                            "lark_app_id_binding": "env:LARK_TEST_APP_ID",
                            "lark_app_secret_binding": "env:LARK_TEST_APP_SECRET",
                        },
                    ),
                ),
            ),
        )
        previous_app_id = os.environ.get("LARK_TEST_APP_ID")
        previous_app_secret = os.environ.get("LARK_TEST_APP_SECRET")
        os.environ["LARK_TEST_APP_ID"] = "cli_long_connection"
        os.environ["LARK_TEST_APP_SECRET"] = "secret_long_connection"
        started: list[dict[str, object]] = []

        class _FakeThread:
            def __init__(self, *, target, kwargs=None, name=None, daemon=None):  # noqa: ANN001
                self._target = target
                self._kwargs = dict(kwargs or {})
                self._alive = False

            def start(self) -> None:
                started.append(dict(self._kwargs))
                self._alive = True

            def is_alive(self) -> bool:
                return self._alive

        try:
            with patch(
                "crxzipple.modules.channels.application.runtime.Thread",
                _FakeThread,
            ):
                self.container.lark_channel_runtime_service.run_runtime_loop(
                    "lark",
                    runtime_id="lark-runtime-long-1",
                    poll_interval_seconds=0.05,
                    max_cycles=1,
                )
        finally:
            if previous_app_id is None:
                os.environ.pop("LARK_TEST_APP_ID", None)
            else:
                os.environ["LARK_TEST_APP_ID"] = previous_app_id
            if previous_app_secret is None:
                os.environ.pop("LARK_TEST_APP_SECRET", None)
            else:
                os.environ["LARK_TEST_APP_SECRET"] = previous_app_secret

        self.assertEqual(len(started), 1)
        self.assertEqual(started[0]["channel_account_id"], "default")
        self.assertEqual(started[0]["runtime_id"], "lark-runtime-long-1")

    def test_channel_runtime_planner_builds_daemon_specs_from_enabled_profiles(self) -> None:
        self.container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="web",
                capabilities=ChannelCapabilities(
                    supports_streaming=True,
                    supports_edit=True,
                ),
                accounts=(
                    ChannelAccountProfile(account_id="default", transport_mode="sse"),
                ),
            ),
        )
        self.container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="telegram",
                enabled=False,
                accounts=(ChannelAccountProfile(account_id="bot-1"),),
            ),
        )
        self.container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="inbox",
                accounts=(ChannelAccountProfile(account_id="default", transport_mode="poll"),),
            ),
        )

        plans = self.container.channel_runtime_planner.build_plan(
            self.container.channel_profile_service.get_system_config(),
        )

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0].service_key, "channel:web")
        self.assertEqual(plans[0].spec.role, "host")
        self.assertEqual(plans[0].spec.start_policy, "eager")
        self.assertEqual(
            plans[0].spec.metadata["cli_args"],
            [
                "channel-runtime",
                "run",
                "--channel",
                "web",
                "--service-key",
                "channel:web",
            ],
        )
        self.assertEqual(plans[0].spec.metadata["env_keys"], [])

    def test_channel_runtime_planner_collects_env_keys_from_binding_metadata(self) -> None:
        self.container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="lark",
                accounts=(
                    ChannelAccountProfile(
                        account_id="default",
                        transport_mode="long_connection",
                        metadata={
                            "lark_app_id_binding": "env:LARK_APP_ID",
                            "lark_app_secret_binding": "env:LARK_APP_SECRET",
                            "lark_encrypt_key_binding": "env:LARK_ENCRYPT_KEY",
                            "lark_verification_token_binding": "env:LARK_VERIFICATION_TOKEN",
                            "lark_bot_open_id_binding": "env:LARK_BOT_OPEN_ID",
                        },
                    ),
                ),
            ),
        )

        plans = self.container.channel_runtime_planner.build_plan(
            self.container.channel_profile_service.get_system_config(),
        )

        lark_plan = next(plan for plan in plans if plan.service_key == "channel:lark")
        self.assertEqual(
            lark_plan.spec.metadata["env_keys"],
            [
                "LARK_APP_ID",
                "LARK_APP_SECRET",
                "LARK_BOT_OPEN_ID",
                "LARK_ENCRYPT_KEY",
                "LARK_VERIFICATION_TOKEN",
            ],
        )

    def test_channel_control_service_syncs_managed_daemon_specs(self) -> None:
        self.container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="web",
                accounts=(ChannelAccountProfile(account_id="default", transport_mode="sse"),),
            ),
        )
        self.container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="telegram",
                accounts=(ChannelAccountProfile(account_id="bot-1", transport_mode="poll"),),
            ),
        )

        planned = self.container.channel_control_service.sync_daemon_specs()
        self.assertEqual({spec.key for spec in planned}, {"channel:web", "channel:telegram"})

        daemon_specs = self.container.daemon_service.list_service_specs(service_group="channels")
        self.assertEqual({spec.key for spec in daemon_specs}, {"channel:web", "channel:telegram"})

        self.container.channel_profile_service.remove_profile("telegram")
        planned_after_removal = self.container.channel_control_service.sync_daemon_specs()

        self.assertEqual({spec.key for spec in planned_after_removal}, {"channel:web"})
        daemon_specs_after_removal = self.container.daemon_service.list_service_specs(service_group="channels")
        self.assertEqual({spec.key for spec in daemon_specs_after_removal}, {"channel:web"})


if __name__ == "__main__":
    unittest.main()
