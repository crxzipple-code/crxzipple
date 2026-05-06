from __future__ import annotations

import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import hashlib
import hmac
import json
import os
import threading
import time

from crxzipple.modules.agent.application import RegisterAgentProfileInput
from crxzipple.modules.agent.domain import (
    AgentInstructionPolicy,
    AgentLlmRoutingPolicy,
    AgentRuntimePreferences,
)
from crxzipple.modules.channels import (
    ChannelAccountProfile,
    ChannelProfile,
    channel_broadcast_topic,
    channel_dead_letter_topic,
)
from crxzipple.modules.llm.application import RegisterLlmProfileInput
from crxzipple.modules.llm.domain import LlmApiFamily, LlmProviderKind
from crxzipple.modules.events import Event, EventTarget
from crxzipple.modules.orchestration.application import (
    turn_session_live_topic,
    turn_session_topic,
)
from crxzipple.shared import ReplyAddress

from tests.unit.http_test_support import *
from tests.unit.test_channels import _CallbackCaptureServer


class _FakeJsonResponse:
    def __init__(self, *, status_code: int, payload: dict[str, object]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, object]:
        return dict(self._payload)


class ChannelsHttpTestCase(HttpModuleTestCase):
    @staticmethod
    def _webhook_signature(secret: str, payload: dict[str, object]) -> str:
        raw = json.dumps(payload).encode("utf-8")
        return hmac.new(
            secret.encode("utf-8"),
            raw,
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _encrypt_lark_payload(payload: dict[str, object], encrypt_key: str) -> str:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        padding = 16 - (len(raw) % 16)
        padded = raw + (b"\x00" * padding)
        key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
        iv = b"0123456789abcdef"
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(padded) + encryptor.finalize()
        return base64.b64encode(iv + ciphertext).decode("utf-8")

    @staticmethod
    def _lark_signature(
        *,
        timestamp: str,
        nonce: str,
        encrypt_key: str,
        body: str,
    ) -> str:
        return hashlib.sha256(
            f"{timestamp}{nonce}{encrypt_key}{body}".encode("utf-8"),
        ).hexdigest()

    def test_lark_events_endpoint_handles_url_verification(self) -> None:
        container = self.client.app.state.container
        container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="lark",
                accounts=(
                    ChannelAccountProfile(
                        account_id="default",
                        transport_mode="webhook",
                        metadata={"lark_verification_token": "token-123"},
                    ),
                ),
            ),
        )

        response = self.client.post(
            "/channels/lark/events/default",
            json={
                "type": "url_verification",
                "token": "token-123",
                "challenge": "challenge-value",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["challenge"], "challenge-value")

    def test_lark_events_endpoint_accepts_encrypted_url_verification(self) -> None:
        container = self.client.app.state.container
        container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="lark",
                accounts=(
                    ChannelAccountProfile(
                        account_id="default",
                        transport_mode="webhook",
                        metadata={
                            "lark_verification_token": "token-123",
                            "lark_encrypt_key": "encrypt-123",
                        },
                    ),
                ),
            ),
        )
        inner_payload = {
            "type": "url_verification",
            "token": "token-123",
            "challenge": "encrypted-challenge",
        }
        outer_payload = {
            "encrypt": self._encrypt_lark_payload(inner_payload, "encrypt-123"),
        }
        raw_body = json.dumps(outer_payload)
        response = self.client.post(
            "/channels/lark/events/default",
            content=raw_body,
            headers={
                "content-type": "application/json",
                "X-Lark-Request-Timestamp": "1710000000",
                "X-Lark-Request-Nonce": "nonce-1",
                "X-Lark-Signature": self._lark_signature(
                    timestamp="1710000000",
                    nonce="nonce-1",
                    encrypt_key="encrypt-123",
                    body=raw_body,
                ),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["challenge"], "encrypted-challenge")

    def test_lark_events_endpoint_accepts_encrypted_url_verification_with_bindings(
        self,
    ) -> None:
        previous_token = os.environ.get("LARK_TEST_VERIFICATION_TOKEN")
        previous_encrypt_key = os.environ.get("LARK_TEST_ENCRYPT_KEY")
        os.environ["LARK_TEST_VERIFICATION_TOKEN"] = "token-123-binding"
        os.environ["LARK_TEST_ENCRYPT_KEY"] = "encrypt-123-binding"
        try:
            container = self.client.app.state.container
            container.channel_profile_service.upsert_profile(
                ChannelProfile(
                    channel_type="lark",
                    accounts=(
                        ChannelAccountProfile(
                            account_id="default",
                            transport_mode="webhook",
                            metadata={
                                "lark_verification_token_binding": "env:LARK_TEST_VERIFICATION_TOKEN",
                                "lark_encrypt_key_binding": "env:LARK_TEST_ENCRYPT_KEY",
                            },
                        ),
                    ),
                ),
            )
            inner_payload = {
                "type": "url_verification",
                "token": "token-123-binding",
                "challenge": "encrypted-binding-challenge",
            }
            outer_payload = {
                "encrypt": self._encrypt_lark_payload(
                    inner_payload,
                    "encrypt-123-binding",
                ),
            }
            raw_body = json.dumps(outer_payload)
            timestamp = "1710000000"
            nonce = "nonce-binding"
            signature = self._lark_signature(
                timestamp=timestamp,
                nonce=nonce,
                encrypt_key="encrypt-123-binding",
                body=raw_body,
            )

            response = self.client.post(
                "/channels/lark/events/default",
                content=raw_body,
                headers={
                    "Content-Type": "application/json",
                    "X-Lark-Request-Timestamp": timestamp,
                    "X-Lark-Request-Nonce": nonce,
                    "X-Lark-Signature": signature,
                },
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["challenge"], "encrypted-binding-challenge")
        finally:
            if previous_token is None:
                os.environ.pop("LARK_TEST_VERIFICATION_TOKEN", None)
            else:
                os.environ["LARK_TEST_VERIFICATION_TOKEN"] = previous_token
            if previous_encrypt_key is None:
                os.environ.pop("LARK_TEST_ENCRYPT_KEY", None)
            else:
                os.environ["LARK_TEST_ENCRYPT_KEY"] = previous_encrypt_key

    def test_lark_events_endpoint_rejects_invalid_encrypted_signature(self) -> None:
        container = self.client.app.state.container
        container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="lark",
                accounts=(
                    ChannelAccountProfile(
                        account_id="default",
                        transport_mode="webhook",
                        metadata={
                            "lark_verification_token": "token-123",
                            "lark_encrypt_key": "encrypt-123",
                        },
                    ),
                ),
            ),
        )
        outer_payload = {
            "encrypt": self._encrypt_lark_payload(
                {
                    "type": "url_verification",
                    "token": "token-123",
                    "challenge": "encrypted-challenge",
                },
                "encrypt-123",
            ),
        }
        response = self.client.post(
            "/channels/lark/events/default",
            content=json.dumps(outer_payload),
            headers={
                "content-type": "application/json",
                "X-Lark-Request-Timestamp": "1710000000",
                "X-Lark-Request-Nonce": "nonce-1",
                "X-Lark-Signature": "bad-signature",
            },
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Invalid Lark request signature.")

    def test_lark_events_endpoint_queues_message_receive_event(self) -> None:
        container = self.client.app.state.container
        container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            _SequentialTextAdapter("lark answer"),
        )
        container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="test-llm-lark",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
            ),
        )
        container.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="assistant-lark",
                name="Assistant Lark",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Be helpful.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(default_llm_id="test-llm-lark"),
                runtime_preferences=AgentRuntimePreferences(),
            ),
        )
        container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="lark",
                accounts=(
                    ChannelAccountProfile(
                        account_id="default",
                        transport_mode="webhook",
                        metadata={
                            "agent_id": "assistant-lark",
                            "lark_verification_token": "token-123",
                        },
                    ),
                ),
            ),
        )

        response = self.client.post(
            "/channels/lark/events/default",
            json={
                "schema": "2.0",
                "token": "token-123",
                "header": {
                    "event_type": "im.message.receive_v1",
                    "event_id": "evt_lark_1",
                },
                "event": {
                    "sender": {
                        "sender_id": {
                            "open_id": "ou_sender_1",
                        },
                    },
                    "message": {
                        "message_id": "om_msg_1",
                        "chat_id": "oc_chat_1",
                        "chat_type": "p2p",
                        "message_type": "text",
                        "content": json.dumps({"text": "hello from lark"}),
                    },
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["code"], 0)
        self.assertEqual(payload["status"], "accepted")
        run = container.orchestration_run_query_service.get_run(payload["run_id"])
        self.assertIsNotNone(run)
        assert run is not None
        self.assertIsNotNone(run.reply_target)
        assert run.reply_target is not None
        self.assertEqual(run.reply_target.interface_name, "lark")
        self.assertEqual(run.reply_target.address, "oc_chat_1")
        self.assertEqual(
            run.reply_target.metadata["reply_address"]["channel_type"],
            "lark",
        )
        self.assertEqual(
            run.reply_target.metadata["reply_address"]["external_conversation_id"],
            "oc_chat_1",
        )
        self.assertEqual(
            run.reply_target.metadata["reply_address"]["external_user_id"],
            "ou_sender_1",
        )
        self.assertEqual(
            run.reply_target.metadata["reply_address"]["metadata"]["receive_id_type"],
            "open_id",
        )

    def test_lark_events_endpoint_ignores_group_message_without_bot_mention(self) -> None:
        container = self.client.app.state.container
        container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            _SequentialTextAdapter("group answer"),
        )
        container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="test-llm-lark-group-ignore",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
            ),
        )
        container.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="assistant-lark-group-ignore",
                name="Assistant Lark Group Ignore",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Be helpful.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(
                    default_llm_id="test-llm-lark-group-ignore",
                ),
                runtime_preferences=AgentRuntimePreferences(),
            ),
        )
        container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="lark",
                accounts=(
                    ChannelAccountProfile(
                        account_id="default",
                        transport_mode="webhook",
                        metadata={
                            "agent_id": "assistant-lark-group-ignore",
                            "lark_verification_token": "token-group-ignore",
                            "lark_group_require_bot_mention": True,
                            "lark_bot_open_id": "ou_bot_1",
                        },
                    ),
                ),
            ),
        )

        response = self.client.post(
            "/channels/lark/events/default",
            json={
                "schema": "2.0",
                "token": "token-group-ignore",
                "header": {
                    "event_type": "im.message.receive_v1",
                    "event_id": "evt_lark_group_ignore",
                },
                "event": {
                    "sender": {
                        "sender_id": {
                            "open_id": "ou_sender_group_1",
                        },
                    },
                    "message": {
                        "message_id": "om_group_1",
                        "chat_id": "oc_group_1",
                        "chat_type": "group",
                        "message_type": "text",
                        "content": json.dumps({"text": "hello group"}),
                    },
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "code": 0,
                "msg": "ignored",
                "challenge": None,
                "run_id": None,
                "status": None,
                "session_key": None,
                "active_session_id": None,
            },
        )

    def test_lark_events_endpoint_accepts_group_message_when_bot_is_mentioned(self) -> None:
        container = self.client.app.state.container
        container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            _SequentialTextAdapter("group mention answer"),
        )
        container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="test-llm-lark-group-mention",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
            ),
        )
        container.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="assistant-lark-group-mention",
                name="Assistant Lark Group Mention",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Be helpful.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(
                    default_llm_id="test-llm-lark-group-mention",
                ),
                runtime_preferences=AgentRuntimePreferences(),
            ),
        )
        container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="lark",
                accounts=(
                    ChannelAccountProfile(
                        account_id="default",
                        transport_mode="webhook",
                        metadata={
                            "agent_id": "assistant-lark-group-mention",
                            "lark_verification_token": "token-group-mention",
                            "lark_group_require_bot_mention": True,
                            "lark_bot_open_id": "ou_bot_1",
                        },
                    ),
                ),
            ),
        )

        response = self.client.post(
            "/channels/lark/events/default",
            json={
                "schema": "2.0",
                "token": "token-group-mention",
                "header": {
                    "event_type": "im.message.receive_v1",
                    "event_id": "evt_lark_group_mention",
                },
                "event": {
                    "sender": {
                        "sender_id": {
                            "open_id": "ou_sender_group_2",
                        },
                    },
                    "message": {
                        "message_id": "om_group_2",
                        "chat_id": "oc_group_2",
                        "chat_type": "group",
                        "message_type": "text",
                        "mentions": [
                            {
                                "key": "@_user_1",
                                "name": "Crx Bot",
                                "id": {
                                    "open_id": "ou_bot_1",
                                },
                            },
                        ],
                        "content": json.dumps(
                            {
                                "text": '<at user_id="ou_bot_1">Crx Bot</at> hello group',
                            },
                        ),
                    },
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "accepted")
        run = container.orchestration_run_query_service.get_run(payload["run_id"])
        self.assertIsNotNone(run)
        assert run is not None
        self.assertEqual(run.reply_target.interface_name, "lark")
        self.assertEqual(
            run.reply_target.metadata["reply_address"]["metadata"]["chat_type"],
            "group",
        )
        self.assertEqual(
            run.reply_target.metadata["reply_address"]["metadata"]["mentions"][0]["open_id"],
            "ou_bot_1",
        )

    def test_lark_events_endpoint_resolves_bot_open_id_automatically_for_group_gating(
        self,
    ) -> None:
        container = self.client.app.state.container
        container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            _SequentialTextAdapter("group resolved answer"),
        )
        container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="test-llm-lark-group-resolved",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
            ),
        )
        container.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="assistant-lark-group-resolved",
                name="Assistant Lark Group Resolved",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Be helpful.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(
                    default_llm_id="test-llm-lark-group-resolved",
                ),
                runtime_preferences=AgentRuntimePreferences(),
            ),
        )
        container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="lark",
                accounts=(
                    ChannelAccountProfile(
                        account_id="default",
                        transport_mode="webhook",
                        metadata={
                            "agent_id": "assistant-lark-group-resolved",
                            "lark_verification_token": "token-group-resolved",
                            "lark_group_require_bot_mention": True,
                            "lark_app_id": "cli_group_resolved",
                            "lark_app_secret": "secret_group_resolved",
                        },
                    ),
                ),
            ),
        )

        def _fake_request(method: str, url: str, **kwargs):  # noqa: ANN001
            del method, kwargs
            if url.endswith("/open-apis/auth/v3/tenant_access_token/internal"):
                return _FakeJsonResponse(
                    status_code=200,
                    payload={
                        "code": 0,
                        "tenant_access_token": "tenant-token-group-resolved",
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
            response = self.client.post(
                "/channels/lark/events/default",
                json={
                    "schema": "2.0",
                    "token": "token-group-resolved",
                    "header": {
                        "event_type": "im.message.receive_v1",
                        "event_id": "evt_lark_group_resolved",
                    },
                    "event": {
                        "sender": {
                            "sender_id": {
                                "open_id": "ou_sender_group_3",
                            },
                        },
                        "message": {
                            "message_id": "om_group_3",
                            "chat_id": "oc_group_3",
                            "chat_type": "group",
                            "message_type": "text",
                            "mentions": [
                                {
                                    "key": "@_user_1",
                                    "name": "Crx Bot",
                                    "id": {
                                        "open_id": "ou_bot_resolved_1",
                                    },
                                },
                            ],
                            "content": json.dumps(
                                {
                                    "text": '<at user_id="ou_bot_resolved_1">Crx Bot</at> hello group',
                                },
                            ),
                        },
                    },
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "accepted")
        run = container.orchestration_run_query_service.get_run(payload["run_id"])
        self.assertIsNotNone(run)
        assert run is not None
        self.assertEqual(run.reply_target.interface_name, "lark")

    def test_lark_events_endpoint_normalizes_non_text_message_with_placeholder(self) -> None:
        container = self.client.app.state.container
        container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            _SequentialTextAdapter("image message answer"),
        )
        container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="test-llm-lark-image",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
            ),
        )
        container.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="assistant-lark-image",
                name="Assistant Lark Image",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Be helpful.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(default_llm_id="test-llm-lark-image"),
                runtime_preferences=AgentRuntimePreferences(),
            ),
        )
        container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="lark",
                accounts=(
                    ChannelAccountProfile(
                        account_id="default",
                        transport_mode="webhook",
                        metadata={
                            "agent_id": "assistant-lark-image",
                            "lark_verification_token": "token-image",
                        },
                    ),
                ),
            ),
        )

        response = self.client.post(
            "/channels/lark/events/default",
            json={
                "schema": "2.0",
                "token": "token-image",
                "header": {
                    "event_type": "im.message.receive_v1",
                    "event_id": "evt_lark_image",
                },
                "event": {
                    "sender": {
                        "sender_id": {
                            "open_id": "ou_sender_image_1",
                        },
                    },
                    "message": {
                        "message_id": "om_image_1",
                        "chat_id": "oc_chat_image_1",
                        "chat_type": "p2p",
                        "message_type": "image",
                        "content": json.dumps({"image_key": "img_v3_123"}),
                    },
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "accepted")
        run = container.orchestration_run_query_service.get_run(payload["run_id"])
        self.assertIsNotNone(run)
        assert run is not None
        self.assertEqual(
            run.inbound_instruction.content["text"],
            "[Lark image message]",
        )
        self.assertEqual(
            run.inbound_instruction.content["metadata"]["message_type"],
            "image",
        )

    def test_lark_events_endpoint_normalizes_file_message_with_name(self) -> None:
        container = self.client.app.state.container
        container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            _SequentialTextAdapter("file message answer"),
        )
        container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="test-llm-lark-file",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
            ),
        )
        container.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="assistant-lark-file",
                name="Assistant Lark File",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Be helpful.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(default_llm_id="test-llm-lark-file"),
                runtime_preferences=AgentRuntimePreferences(),
            ),
        )
        container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="lark",
                accounts=(
                    ChannelAccountProfile(
                        account_id="default",
                        transport_mode="webhook",
                        metadata={
                            "agent_id": "assistant-lark-file",
                            "lark_verification_token": "token-file",
                        },
                    ),
                ),
            ),
        )

        response = self.client.post(
            "/channels/lark/events/default",
            json={
                "schema": "2.0",
                "token": "token-file",
                "header": {
                    "event_type": "im.message.receive_v1",
                    "event_id": "evt_lark_file",
                },
                "event": {
                    "sender": {
                        "sender_id": {
                            "open_id": "ou_sender_file_1",
                        },
                    },
                    "message": {
                        "message_id": "om_file_1",
                        "chat_id": "oc_chat_file_1",
                        "chat_type": "p2p",
                        "message_type": "file",
                        "content": json.dumps(
                            {
                                "file_key": "file_v3_123",
                                "file_name": "design-spec.pdf",
                            },
                        ),
                    },
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "accepted")
        run = container.orchestration_run_query_service.get_run(payload["run_id"])
        self.assertIsNotNone(run)
        assert run is not None
        self.assertEqual(
            run.inbound_instruction.content["text"],
            "[Lark file: design-spec.pdf]",
        )
        self.assertEqual(
            run.inbound_instruction.content["metadata"]["file_name"],
            "design-spec.pdf",
        )
        self.assertEqual(
            run.inbound_instruction.content["metadata"]["file_key"],
            "file_v3_123",
        )

    def test_lark_events_endpoint_normalizes_post_message_into_readable_text(self) -> None:
        container = self.client.app.state.container
        container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            _SequentialTextAdapter("post message answer"),
        )
        container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="test-llm-lark-post",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
            ),
        )
        container.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="assistant-lark-post",
                name="Assistant Lark Post",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Be helpful.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(default_llm_id="test-llm-lark-post"),
                runtime_preferences=AgentRuntimePreferences(),
            ),
        )
        container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="lark",
                accounts=(
                    ChannelAccountProfile(
                        account_id="default",
                        transport_mode="webhook",
                        metadata={
                            "agent_id": "assistant-lark-post",
                            "lark_verification_token": "token-post",
                        },
                    ),
                ),
            ),
        )

        response = self.client.post(
            "/channels/lark/events/default",
            json={
                "schema": "2.0",
                "token": "token-post",
                "header": {
                    "event_type": "im.message.receive_v1",
                    "event_id": "evt_lark_post",
                },
                "event": {
                    "sender": {
                        "sender_id": {
                            "open_id": "ou_sender_post_1",
                        },
                    },
                    "message": {
                        "message_id": "om_post_1",
                        "chat_id": "oc_chat_post_1",
                        "chat_type": "p2p",
                        "message_type": "post",
                        "content": json.dumps(
                            {
                                "zh_cn": {
                                    "title": "每日播报",
                                    "content": [
                                        [
                                            {"tag": "text", "text": "第一条"},
                                            {"tag": "a", "text": "查看", "href": "https://example.test/post"},
                                        ],
                                        [
                                            {"tag": "img", "image_key": "img_v3_321"},
                                        ],
                                    ],
                                },
                            },
                        ),
                    },
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "accepted")
        run = container.orchestration_run_query_service.get_run(payload["run_id"])
        self.assertIsNotNone(run)
        assert run is not None
        self.assertEqual(
            run.inbound_instruction.content["text"],
            "每日播报\n第一条查看\n[image:img_v3_321]",
        )
        self.assertEqual(
            run.inbound_instruction.content["metadata"]["message_type"],
            "post",
        )
        self.assertEqual(
            run.inbound_instruction.content["metadata"]["post_lines"],
            ["每日播报", "第一条查看", "[image:img_v3_321]"],
        )

    def test_webhook_inbound_endpoint_accepts_turn_with_callback_reply_target(self) -> None:
        container = self.client.app.state.container
        container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            _SequentialTextAdapter("webhook callback answer"),
        )
        container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="test-llm",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
            ),
        )
        container.agent_service.register_profile(
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

        response = self.client.post(
            "/channels/webhook/inbound/default",
            json={
                "content": {"blocks": [{"type": "text", "text": "hello from webhook"}]},
                "callback_url": "https://example.test/callback",
                "agent_id": "assistant",
                "conversation_id": "ext-conv-1",
                "peer_id": "ext-user-1",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "accepted")
        run = container.orchestration_run_query_service.get_run(payload["run_id"])
        self.assertIsNotNone(run.reply_target)
        assert run.reply_target is not None
        self.assertEqual(run.reply_target.interface_name, "webhook")
        self.assertEqual(run.reply_target.address, "https://example.test/callback")
        self.assertEqual(
            run.reply_target.metadata["reply_address"]["channel_type"],
            "webhook",
        )
        self.assertEqual(
            run.reply_target.metadata["reply_address"]["channel_account_id"],
            "default",
        )
        self.assertEqual(
            run.reply_target.metadata["reply_address"]["webhook_callback_url"],
            "https://example.test/callback",
        )
        self.assertEqual(
            run.reply_target.metadata["reply_address"]["metadata"]["observation_enabled"],
            True,
        )
        interaction = container.channel_interaction_service.get_interaction(
            f"webhook:default:run:{run.id}",
        )
        self.assertIsNotNone(interaction)
        assert interaction is not None
        self.assertEqual(interaction.run_id, run.id)
        self.assertEqual(interaction.session_key, run.session_key)
        self.assertEqual(interaction.status, "accepted")
        self.assertEqual(
            interaction.reply_address["webhook_callback_url"],
            "https://example.test/callback",
        )

    def test_webhook_inbound_endpoint_validates_signature_when_configured(self) -> None:
        container = self.client.app.state.container
        container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="webhook",
                accounts=(
                    ChannelAccountProfile(
                        account_id="default",
                        transport_mode="webhook",
                        metadata={
                            "webhook_signing_secret": "top-secret",
                        },
                    ),
                ),
            ),
        )
        container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            _SequentialTextAdapter("signed webhook callback answer"),
        )
        container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="test-llm-signed",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
            ),
        )
        container.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="assistant-signed",
                name="Assistant Signed",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Be helpful.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(default_llm_id="test-llm-signed"),
                runtime_preferences=AgentRuntimePreferences(),
            ),
        )
        payload = {
            "content": {"blocks": [{"type": "text", "text": "hello signed webhook"}]},
            "callback_url": "https://example.test/callback",
            "agent_id": "assistant-signed",
            "conversation_id": "ext-conv-signed-1",
            "peer_id": "ext-user-signed-1",
        }

        response = self.client.post(
            "/channels/webhook/inbound/default",
            content=json.dumps(payload),
            headers={
                "content-type": "application/json",
                "X-Crx-Webhook-Signature": self._webhook_signature(
                    "top-secret",
                    payload,
                ),
            },
        )

        self.assertEqual(response.status_code, 200)

    def test_webhook_inbound_endpoint_rejects_invalid_signature_when_configured(self) -> None:
        container = self.client.app.state.container
        container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="webhook",
                accounts=(
                    ChannelAccountProfile(
                        account_id="default",
                        transport_mode="webhook",
                        metadata={
                            "webhook_signing_secret": "top-secret",
                        },
                    ),
                ),
            ),
        )
        container.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="assistant-invalid-signed",
                name="Assistant Invalid Signed",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Be helpful.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(default_llm_id="missing-llm-is-fine"),
                runtime_preferences=AgentRuntimePreferences(),
            ),
        )
        payload = {
            "content": {"blocks": [{"type": "text", "text": "hello signed webhook"}]},
            "callback_url": "https://example.test/callback",
            "agent_id": "assistant-invalid-signed",
            "conversation_id": "ext-conv-signed-2",
            "peer_id": "ext-user-signed-2",
        }

        response = self.client.post(
            "/channels/webhook/inbound/default",
            content=json.dumps(payload),
            headers={
                "content-type": "application/json",
                "X-Crx-Webhook-Signature": "sha256=not-valid",
            },
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Invalid webhook signature.")

    def test_channel_runtimes_endpoint_lists_runtime_ownership(self) -> None:
        container = self.client.app.state.container
        container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="web",
                accounts=(ChannelAccountProfile(account_id="default", transport_mode="sse"),),
            ),
        )
        container.web_channel_runtime_service.ensure_registered(
            runtime_id="web-runtime-http-1",
        )
        container.web_channel_runtime_service.bind_connection(
            connection_id="web-http-conn-1",
            channel_account_id="default",
            conversation_id="conv-http-1",
            runtime_id="web-runtime-http-1",
        )

        response = self.client.get("/channels/runtimes", params={"channel_type": "web"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        runtime = next(
            item for item in payload if item["runtime_id"] == "web-runtime-http-1"
        )
        self.assertEqual(runtime["runtime_id"], "web-runtime-http-1")
        self.assertEqual(runtime["channel_type"], "web")
        self.assertEqual(runtime["account_count"], 1)
        self.assertEqual(runtime["connection_count"], 1)
        self.assertNotIn("delivery_executor", runtime)

    def test_channel_runtime_endpoint_returns_runtime_detail(self) -> None:
        container = self.client.app.state.container
        container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="web",
                accounts=(ChannelAccountProfile(account_id="default", transport_mode="sse"),),
            ),
        )
        container.web_channel_runtime_service.ensure_registered(
            runtime_id="web-runtime-http-detail-1",
        )
        container.web_channel_runtime_service.bind_connection(
            connection_id="web-http-conn-detail-1",
            channel_account_id="default",
            conversation_id="conv-http-detail-1",
            runtime_id="web-runtime-http-detail-1",
        )

        response = self.client.get("/channels/runtimes/web-runtime-http-detail-1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["runtime_id"], "web-runtime-http-detail-1")
        self.assertEqual(payload["service_key"], "channel:web")
        self.assertNotIn("delivery_executor", payload)
        self.assertEqual(len(payload["account_bindings"]), 1)
        self.assertEqual(payload["account_bindings"][0]["channel_account_id"], "default")
        self.assertEqual(len(payload["connection_bindings"]), 1)
        self.assertEqual(
            payload["connection_bindings"][0]["connection_id"],
            "web-http-conn-detail-1",
        )
        self.assertEqual(
            payload["connection_bindings"][0]["conversation_id"],
            "conv-http-detail-1",
        )

    def test_web_channel_subscription_endpoint_updates_observe_subscription(self) -> None:
        container = self.client.app.state.container
        container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="web",
                accounts=(ChannelAccountProfile(account_id="default", transport_mode="sse"),),
            ),
        )
        container.web_channel_runtime_service.ensure_registered(
            runtime_id="web-runtime-http-subscription-1",
        )
        container.web_channel_runtime_service.bind_connection(
            connection_id="web-http-conn-subscription-1",
            channel_account_id="default",
            conversation_id="agent:demo:old",
            runtime_id="web-runtime-http-subscription-1",
            metadata={
                "observe_cursor": "18",
            },
        )
        container.events_service.publish(
            Event(
                topic=turn_session_topic("agent:demo:new"),
                kind="observe_fact",
                payload={
                    "event_name": "orchestration.run.queued",
                    "run_id": "run-subscription-seed",
                    "session_key": "agent:demo:new",
                    "status": "queued",
                    "stage": "queued",
                },
            ),
        )
        seeded_cursor = container.events_service.snapshot_event_topic(
            turn_session_topic("agent:demo:new"),
        )

        response = self.client.post(
            "/channels/web/connections/web-http-conn-subscription-1/subscription",
            json={"conversation_id": "agent:demo:new"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["connection_id"], "web-http-conn-subscription-1")
        self.assertEqual(payload["conversation_id"], "agent:demo:new")
        self.assertEqual(payload["metadata"]["observe_cursor"], seeded_cursor)
        self.assertEqual(payload["conversation_id"], "agent:demo:new")
        binding = container.channel_runtime_manager.resolve_connection_binding(
            channel_type="web",
            connection_id="web-http-conn-subscription-1",
        )
        self.assertIsNotNone(binding)
        assert binding is not None
        self.assertEqual(binding.conversation_id, "agent:demo:new")
        self.assertEqual(binding.metadata.get("observe_cursor"), seeded_cursor)

    def test_web_channel_subscription_endpoint_rebinds_missing_connection(self) -> None:
        container = self.client.app.state.container
        container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="web",
                accounts=(ChannelAccountProfile(account_id="default", transport_mode="sse"),),
            ),
        )
        container.web_channel_runtime_service.ensure_registered(
            runtime_id="web-runtime-http-rebind-1",
        )

        response = self.client.post(
            "/channels/web/connections/web-http-conn-rebind-1/subscription",
            json={
                "channel_account_id": "default",
                "conversation_id": "agent:demo:rebound",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["connection_id"], "web-http-conn-rebind-1")
        self.assertEqual(payload["channel_account_id"], "default")
        self.assertEqual(payload["conversation_id"], "agent:demo:rebound")
        binding = container.channel_runtime_manager.resolve_connection_binding(
            channel_type="web",
            connection_id="web-http-conn-rebind-1",
        )
        self.assertIsNotNone(binding)
        assert binding is not None
        self.assertEqual(binding.channel_account_id, "default")
        self.assertEqual(binding.conversation_id, "agent:demo:rebound")

    def test_web_channel_events_endpoint_preserves_existing_subscription_on_reconnect(self) -> None:
        container = self.client.app.state.container
        container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="web",
                accounts=(ChannelAccountProfile(account_id="default", transport_mode="sse"),),
            ),
        )
        container.web_channel_runtime_service.ensure_registered(
            runtime_id="web-runtime-http-reconnect-1",
        )
        container.web_channel_runtime_service.bind_connection(
            connection_id="web-channel-conn-reconnect-1",
            channel_account_id="default",
            conversation_id="agent:demo:preserved",
            runtime_id="web-runtime-http-reconnect-1",
        )

        with self.client.stream(
                "GET",
                "/channels/web/events",
                params={
                    "timeout_seconds": 1.0,
                    "channel_account_id": "default",
                    "connection_id": "web-channel-conn-reconnect-1",
                    "conversation_id": "agent:demo:stale",
                },
        ) as response:
            body = response.read().decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn('"conversation_id": "agent:demo:preserved"', body)

    def test_web_channel_events_endpoint_seeds_observe_cursor_without_replaying_history(self) -> None:
        container = self.client.app.state.container
        container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="web",
                accounts=(ChannelAccountProfile(account_id="default", transport_mode="sse"),),
            ),
        )
        container.web_channel_runtime_service.ensure_registered(
            runtime_id="web-runtime-http-backfill-1",
        )
        container.events_service.publish(
            Event(
                topic=turn_session_topic("agent:demo:rebound"),
                kind="fact",
                payload={
                    "event_name": "orchestration.run.completed",
                    "run_id": "run-rebound-1",
                    "session_key": "agent:demo:rebound",
                    "status": "completed",
                    "stage": "completed",
                },
            ),
        )

        with self.client.stream(
                "GET",
                "/channels/web/events",
                params={
                    "timeout_seconds": 1.0,
                    "channel_account_id": "default",
                    "connection_id": "web-channel-conn-backfill-1",
                    "conversation_id": "agent:demo:rebound",
                },
        ) as response:
            body = response.read().decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("event: observe", body)
        seeded_cursor = container.events_service.snapshot_event_topic(
            turn_session_topic("agent:demo:rebound"),
        )
        self.assertIn(f'"observe_cursor": "{seeded_cursor}"', body)

    def test_web_channel_events_endpoint_wakes_on_subscription_update_without_polling(self) -> None:
        container = self.client.app.state.container
        container.channel_profile_service.upsert_profile(
            ChannelProfile(
                channel_type="web",
                accounts=(ChannelAccountProfile(account_id="default", transport_mode="sse"),),
            ),
        )
        update_status: dict[str, int] = {}

        def _update_subscription_and_publish() -> None:
            time.sleep(0.1)
            response = self.client.post(
                "/channels/web/connections/web-channel-conn-subscribe-wake-1/subscription",
                json={
                    "channel_account_id": "default",
                    "conversation_id": "agent:demo:observe-wake",
                },
            )
            update_status["status_code"] = response.status_code
            time.sleep(0.05)
            container.events_service.publish(
                Event(
                    topic=turn_session_topic("agent:demo:observe-wake"),
                    kind="fact",
                    ordering_key="agent:demo:observe-wake",
                    payload={
                        "event_name": "orchestration.run.advanced",
                        "run_id": "run-observe-wake-1",
                        "session_key": "agent:demo:observe-wake",
                        "status": "running",
                        "stage": "tool_executing",
                    },
                ),
            )

        sender = threading.Thread(target=_update_subscription_and_publish)
        sender.start()
        try:
            with self.client.stream(
                "GET",
                "/channels/web/events",
                params={
                    "timeout_seconds": 1.0,
                    "channel_account_id": "default",
                    "connection_id": "web-channel-conn-subscribe-wake-1",
                },
            ) as response:
                body = response.read().decode("utf-8")
                status_code = response.status_code
        finally:
            sender.join(timeout=1.0)

        self.assertEqual(update_status.get("status_code"), 200)
        self.assertEqual(status_code, 200)
        self.assertIn("event: observe", body)
        self.assertIn("orchestration.run.advanced", body)
        self.assertIn("tool_executing", body)

    def test_channel_dead_letters_endpoint_lists_runtime_dead_letters(self) -> None:
        container = self.client.app.state.container
        container.events_service.publish(
            Event(
                topic=channel_dead_letter_topic(
                    "webhook",
                    runtime_id="webhook-runtime-http-dead-1",
                ),
                kind="fact",
                target=EventTarget(
                    runtime_id="webhook-runtime-http-dead-1",
                    channel_type="webhook",
                    channel_account_id="default",
                ),
                payload={
                    "event_name": "channel.observation.dead_lettered",
                    "outbound_id": "out-dead-1",
                    "status": "http_503",
                    "attempt_count": 3,
                    "callback_url": "https://example.test/callback",
                },
            ),
        )

        response = self.client.get(
            "/channels/dead-letters/webhook",
            params={"runtime_id": "webhook-runtime-http-dead-1"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        matched = [
            item
            for item in payload
            if item["payload"].get("outbound_id") == "out-dead-1"
        ]
        self.assertTrue(matched)
        record = matched[-1]
        self.assertEqual(
            record["topic"],
            channel_dead_letter_topic(
                "webhook",
                runtime_id="webhook-runtime-http-dead-1",
            ),
        )
        self.assertEqual(record["payload"]["outbound_id"], "out-dead-1")
        self.assertEqual(
            record["payload"]["event_name"],
            "channel.observation.dead_lettered",
        )
        self.assertEqual(record["payload"]["status"], "http_503")
        self.assertEqual(record["target"]["runtime_id"], "webhook-runtime-http-dead-1")

    def test_channel_dead_letters_replay_endpoint_replays_webhook_directly(self) -> None:
        container = self.client.app.state.container
        container.channel_profile_service.upsert_profile(
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
        container.webhook_channel_runtime_service.ensure_registered(
            runtime_id="webhook-runtime-http-replay-1",
        )
        callback_server = _CallbackCaptureServer()
        callback_server.start()
        self.addCleanup(callback_server.close)
        dead_letter_event = Event(
            topic=channel_dead_letter_topic(
                "webhook",
                runtime_id="webhook-runtime-http-replay-1",
            ),
            kind="fact",
            target=EventTarget(
                runtime_id="webhook-runtime-http-replay-1",
                channel_type="webhook",
                channel_account_id="default",
            ),
            payload={
                "outbound_id": "out-replay-1",
                "outbound": {
                    "outbound_id": "out-replay-1",
                    "conversation_id": "ext-conv-replay-1",
                    "session_key": "agent:assistant:webhook:replay",
                    "mode": "final",
                    "reply_address": {
                        "channel_type": "webhook",
                        "channel_account_id": "default",
                        "webhook_callback_url": f"{callback_server.base_url}/replay",
                        "external_conversation_id": "ext-conv-replay-1",
                        "external_thread_id": None,
                        "external_user_id": "ext-user-replay-1",
                        "route_hint": None,
                        "metadata": {},
                    },
                    "message": {
                        "role": "assistant",
                        "type": "text",
                        "text": "replay me",
                    },
                    "metadata": {
                        "run_id": "run-replay-1",
                    },
                    "created_at": "2026-04-13T00:00:00+00:00",
                },
                "status": "http_503",
                "attempt_count": 3,
                "callback_url": f"{callback_server.base_url}/replay",
            },
        )
        container.events_service.publish(dead_letter_event)

        response = self.client.post(
            "/channels/dead-letters/webhook/replay",
            json={
                "runtime_id": "webhook-runtime-http-replay-1",
                "event_id": dead_letter_event.id,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["replayed"], True)
        self.assertEqual(payload["outbound_id"], "out-replay-1")
        self.assertEqual(payload["replay_mode"], "direct_callback")
        self.assertEqual(payload["callback_status"], "http_200")
        self.assertNotIn("delivery_topic", payload)
        self.assertNotIn("delivery_event_id", payload)
        self.assertEqual(len(callback_server.payloads), 1)
        self.assertEqual(
            callback_server.payloads[0]["outbound_id"],
            "out-replay-1",
        )

    def test_channel_dead_letters_replay_endpoint_rejects_generic_legacy_outbound_requeue(self) -> None:
        container = self.client.app.state.container
        dead_letter_event = Event(
            topic=channel_dead_letter_topic(
                "web",
                runtime_id="web-runtime-http-replay-legacy-1",
            ),
            kind="fact",
            target=EventTarget(
                runtime_id="web-runtime-http-replay-legacy-1",
                channel_type="web",
                channel_account_id="default",
            ),
            payload={
                "outbound_id": "out-legacy-replay-1",
                "outbound": {
                    "outbound_id": "out-legacy-replay-1",
                    "conversation_id": "agent:demo:legacy",
                    "session_key": "agent:demo:legacy",
                    "mode": "final",
                    "reply_address": {
                        "channel_type": "web",
                        "channel_account_id": "default",
                        "connection_id": "web-conn-legacy-1",
                        "metadata": {},
                    },
                    "message": {
                        "role": "assistant",
                        "type": "text",
                        "text": "legacy replay",
                    },
                    "metadata": {},
                    "created_at": "2026-04-13T00:00:00+00:00",
                },
                "reply_address": {
                    "channel_type": "web",
                    "channel_account_id": "default",
                    "connection_id": "web-conn-legacy-1",
                    "metadata": {},
                },
                "status": "dropped",
                "attempt_count": 1,
            },
        )
        container.events_service.publish(dead_letter_event)

        response = self.client.post(
            "/channels/dead-letters/web/replay",
            json={
                "runtime_id": "web-runtime-http-replay-legacy-1",
                "event_id": dead_letter_event.id,
            },
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("no longer requeues generic legacy outbound events", response.json()["detail"])

    def test_web_channel_events_endpoint_ignores_legacy_runtime_events(self) -> None:
        container = self.client.app.state.container

        def _deliver_later() -> None:
            time.sleep(0.1)
            container.events_service.publish(
                Event(
                    topic="delivery.runtime.web-runtime-1",
                    kind="fact",
                    payload={
                        "outbound": {
                            "outbound_id": "legacy-web-outbound-1",
                            "conversation_id": "agent:demo:main",
                            "session_key": "agent:demo:main",
                            "mode": "final",
                            "reply_address": {
                                "channel_type": "web",
                                "channel_account_id": "default",
                                "connection_id": "web-channel-conn-1",
                                "metadata": {},
                            },
                            "message": {
                                "role": "assistant",
                                "type": "text",
                                "text": "hello from legacy web outbound topic",
                            },
                            "metadata": {},
                            "created_at": "2026-04-16T00:00:00+00:00",
                        },
                        "route": {
                            "runtime_id": "web-runtime-1",
                            "channel_type": "web",
                            "path": "connection",
                            "channel_account_id": "default",
                            "connection_id": "web-channel-conn-1",
                            "supports_streaming": True,
                            "route_hint": None,
                            "service_key": "channel:web",
                            "metadata": {},
                        },
                    },
                ),
            )

        sender = threading.Thread(target=_deliver_later)
        sender.start()
        try:
            with self.client.stream(
                "GET",
                "/channels/web/events",
                params={
                    "timeout_seconds": 1.0,
                    "channel_account_id": "default",
                    "connection_id": "web-channel-conn-1",
                    "conversation_id": "agent:demo:main",
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
        self.assertEqual(response.headers["x-crx-stream-scope"], "channel")
        self.assertIn("event: connected", body)
        self.assertIn('"stream_role": "primary"', body)
        self.assertIn('"observe_mode": "preferred"', body)
        self.assertNotIn("event: delivery", body)
        self.assertNotIn("hello from legacy web outbound topic", body)
        self.assertIn("event: timeout", body)
        self.assertIsNone(
            container.channel_runtime_manager.resolve_connection_binding(
                channel_type="web",
                connection_id="web-channel-conn-1",
            ),
        )

    def test_web_channel_events_endpoint_streams_account_broadcast(self) -> None:
        container = self.client.app.state.container

        def _broadcast_later() -> None:
            time.sleep(0.1)
            container.events_service.publish(
                Event(
                    topic=channel_broadcast_topic(
                        "web",
                        channel_account_id="default",
                    ),
                    kind="broadcast",
                    target=EventTarget(
                        channel_type="web",
                        channel_account_id="default",
                    ),
                    payload={
                        "kind": "queue_notice",
                        "message": {
                            "type": "text",
                            "text": "front queue has 3 pending jobs",
                        },
                    },
                ),
            )

        sender = threading.Thread(target=_broadcast_later)
        sender.start()
        try:
            with self.client.stream(
                "GET",
                "/channels/web/events",
                params={
                    "timeout_seconds": 1.0,
                    "channel_account_id": "default",
                    "connection_id": "web-channel-conn-2",
                },
            ) as response:
                body = response.read().decode("utf-8")
                content_type = response.headers["content-type"]
                status_code = response.status_code
        finally:
            sender.join(timeout=1.0)

        self.assertEqual(status_code, 200)
        self.assertIn("text/event-stream", content_type)
        self.assertIn("event: connected", body)
        self.assertIn("event: broadcast", body)
        self.assertIn("front queue has 3 pending jobs", body)
        self.assertIn("event: timeout", body)

    def test_web_channel_events_endpoint_streams_observe_events(self) -> None:
        container = self.client.app.state.container

        def _observe_later() -> None:
            time.sleep(0.1)
            container.events_service.publish(
                Event(
                    topic=turn_session_topic("agent:demo:observe-http"),
                    kind="fact",
                    ordering_key="agent:demo:observe-http",
                    payload={
                        "event_name": "orchestration.run.advanced",
                        "run_id": "run-observe-http-1",
                        "session_key": "agent:demo:observe-http",
                        "status": "running",
                        "stage": "llm_generating",
                    },
                ),
            )

        sender = threading.Thread(target=_observe_later)
        sender.start()
        try:
            with self.client.stream(
                "GET",
                "/channels/web/events",
                params={
                    "timeout_seconds": 1.0,
                    "channel_account_id": "default",
                    "connection_id": "web-channel-conn-observe-1",
                    "conversation_id": "agent:demo:observe-http",
                },
            ) as response:
                body = response.read().decode("utf-8")
                content_type = response.headers["content-type"]
                status_code = response.status_code
        finally:
            sender.join(timeout=1.0)

        self.assertEqual(status_code, 200)
        self.assertIn("text/event-stream", content_type)
        self.assertIn("event: connected", body)
        self.assertIn("event: observe", body)
        self.assertIn("orchestration.run.advanced", body)
        self.assertIn("llm_generating", body)
        self.assertIn("event: timeout", body)

    def test_web_channel_events_endpoint_routes_observe_from_direct_session_source(self) -> None:
        container = self.client.app.state.container
        container.web_channel_runtime_service.ensure_registered(
            runtime_id="web-runtime-1",
        )

        def _observe_later() -> None:
            time.sleep(0.1)
            container.events_service.publish(
                Event(
                    topic=turn_session_topic("agent:demo:observe-active-http"),
                    kind="fact",
                    ordering_key="agent:demo:observe-active-http",
                    payload={
                        "event_name": "orchestration.run.advanced",
                        "run_id": "run-observe-active-http-1",
                        "session_key": "agent:demo:observe-active-http",
                        "status": "running",
                        "stage": "tool_executing",
                    },
                ),
            )

        sender = threading.Thread(target=_observe_later)
        sender.start()
        try:
            with self.client.stream(
                "GET",
                "/channels/web/events",
                params={
                    "timeout_seconds": 1.0,
                    "channel_account_id": "default",
                    "connection_id": "web-channel-conn-observe-active-1",
                    "conversation_id": "agent:demo:observe-active-http",
                },
            ) as response:
                body = response.read().decode("utf-8")
                status_code = response.status_code
        finally:
            sender.join(timeout=1.0)

        self.assertEqual(status_code, 200)
        self.assertIn("event: observe", body)
        self.assertIn("tool_executing", body)

    def test_web_channel_events_endpoint_streams_live_events(self) -> None:
        container = self.client.app.state.container

        def _live_later() -> None:
            time.sleep(0.1)
            container.events_service.publish(
                Event(
                    topic=turn_session_live_topic("agent:demo:live-http"),
                    kind="live",
                    ordering_key="run-live-http-1",
                    payload={
                        "event_name": "orchestration.run.llm_text_delta",
                        "run_id": "run-live-http-1",
                        "session_key": "agent:demo:live-http",
                        "invocation_id": "invoke-live-http-1",
                        "text": "hello live stream",
                    },
                ),
            )

        sender = threading.Thread(target=_live_later)
        sender.start()
        try:
            with self.client.stream(
                "GET",
                "/channels/web/events",
                params={
                    "timeout_seconds": 1.0,
                    "channel_account_id": "default",
                    "connection_id": "web-channel-conn-live-1",
                    "conversation_id": "agent:demo:live-http",
                },
            ) as response:
                body = response.read().decode("utf-8")
                content_type = response.headers["content-type"]
                status_code = response.status_code
        finally:
            sender.join(timeout=1.0)

        self.assertEqual(status_code, 200)
        self.assertIn("text/event-stream", content_type)
        self.assertIn("event: connected", body)
        self.assertIn("event: live", body)
        self.assertIn("orchestration.run.llm_text_delta", body)
        self.assertIn("hello live stream", body)
        self.assertIn('"path": "direct_source"', body)
        self.assertIn("event: timeout", body)


if __name__ == "__main__":
    unittest.main()
