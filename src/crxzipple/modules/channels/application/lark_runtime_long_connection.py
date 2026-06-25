from __future__ import annotations

import logging
from threading import Event as ThreadEvent, Lock, Thread
from typing import Any, Protocol

from crxzipple.modules.channels.application.lark_runtime_identity import (
    lark_base_url_from_metadata,
)
from crxzipple.modules.channels.application.services import (
    ChannelProfileApplicationService,
    ChannelRuntimeManager,
)


logger = logging.getLogger(__name__)


class LarkAccountProfileResolver(Protocol):
    def __call__(self, channel_account_id: str) -> Any:
        ...


class LarkMetadataCredentialResolver(Protocol):
    def __call__(
        self,
        metadata: dict[str, Any],
        *,
        key: str,
        description: str,
        required: bool,
        channel_type: str,
        component: str,
        channel_account_id: str | None = None,
        runtime_ref: str | None = None,
    ) -> str | None:
        ...


class LarkMessageSubmitter(Protocol):
    def __call__(
        self,
        channel_account_id: str,
        *,
        event_id: str | None,
        sender_open_id: str | None,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        ...


class LarkLongConnectionIngressRuntime:
    def __init__(
        self,
        *,
        profile_service: ChannelProfileApplicationService,
        runtime_manager: ChannelRuntimeManager,
        account_profile_resolver: LarkAccountProfileResolver,
        metadata_credential_resolver: LarkMetadataCredentialResolver,
        message_submitter: LarkMessageSubmitter,
    ) -> None:
        self._profile_service = profile_service
        self._runtime_manager = runtime_manager
        self._account_profile_resolver = account_profile_resolver
        self._metadata_credential_resolver = metadata_credential_resolver
        self._message_submitter = message_submitter
        self._threads: dict[str, Thread] = {}
        self._lock = Lock()

    def ensure_started(
        self,
        runtime_id: str,
        *,
        stop_event: ThreadEvent | None,
    ) -> None:
        accounts = self._long_connection_accounts()
        if not accounts:
            return
        if len(accounts) > 1:
            logger.warning(
                "lark long connection currently starts only the first enabled account on a runtime: %s",
                accounts,
            )
        account_id = accounts[0]
        thread_key = f"{runtime_id}:{account_id}"
        with self._lock:
            existing = self._threads.get(thread_key)
            if existing is not None and existing.is_alive():
                return
            thread = Thread(
                target=self._run,
                kwargs={
                    "runtime_id": runtime_id,
                    "channel_account_id": account_id,
                    "stop_event": stop_event,
                },
                name=f"lark-long-connection-{account_id}",
                daemon=True,
            )
            self._threads[thread_key] = thread
            thread.start()

    def _long_connection_accounts(self) -> tuple[str, ...]:
        profile = self._profile_service.get_profile("lark")
        if profile is None or not profile.enabled:
            return ()
        resolved: list[str] = []
        for account in profile.accounts:
            if not account.enabled:
                continue
            mode = str(account.transport_mode or "").strip().lower()
            if mode in {"long_connection", "long-connection", "long"}:
                resolved.append(account.account_id)
        return tuple(resolved)

    def _run(
        self,
        *,
        runtime_id: str,
        channel_account_id: str,
        stop_event: ThreadEvent | None,
    ) -> None:
        try:
            import lark_oapi
            from lark_oapi import EventDispatcherHandler
            from lark_oapi.ws import Client as LarkWsClient
        except Exception as exc:  # pragma: no cover - import guard
            logger.exception("failed to import lark long connection sdk: %s", exc)
            return

        try:
            account_profile = self._account_profile_resolver(channel_account_id)
            metadata = dict(account_profile.metadata)
            app_id = self._metadata_credential_resolver(
                metadata,
                key="lark_app_id",
                description="Lark app id",
                required=True,
                channel_type="lark",
                component="long_connection",
                channel_account_id=channel_account_id,
                runtime_ref=runtime_id,
            )
            app_secret = self._metadata_credential_resolver(
                metadata,
                key="lark_app_secret",
                description="Lark app secret",
                required=True,
                channel_type="lark",
                component="long_connection",
                channel_account_id=channel_account_id,
                runtime_ref=runtime_id,
            )
            verification_token = self._metadata_credential_resolver(
                metadata,
                key="lark_verification_token",
                description="Lark verification token",
                required=False,
                channel_type="lark",
                component="long_connection",
                channel_account_id=channel_account_id,
                runtime_ref=runtime_id,
            ) or ""
            encrypt_key = self._metadata_credential_resolver(
                metadata,
                key="lark_encrypt_key",
                description="Lark encrypt key",
                required=False,
                channel_type="lark",
                component="long_connection",
                channel_account_id=channel_account_id,
                runtime_ref=runtime_id,
            ) or ""
            base_url = lark_base_url_from_metadata(metadata)

            def _handle_message(data) -> None:  # noqa: ANN001
                try:
                    result = self._message_submitter(
                        channel_account_id,
                        event_id=getattr(getattr(data, "header", None), "event_id", None),
                        sender_open_id=_sender_open_id(data),
                        message=_message_payload(data),
                    )
                    self._runtime_manager.merge_runtime_metadata(
                        runtime_id,
                        metadata={
                            "lark_ingress_mode": "long_connection",
                            "lark_last_ingress_event_id": getattr(
                                getattr(data, "header", None),
                                "event_id",
                                None,
                            ),
                            "lark_last_ingress_status": result.get("status")
                            or result.get("msg"),
                        },
                        touch_heartbeat=True,
                    )
                except Exception as exc:  # pragma: no cover - defensive
                    logger.exception("failed to handle lark long connection event: %s", exc)

            event_handler = (
                EventDispatcherHandler
                .builder(encrypt_key, verification_token)
                .register_p2_im_message_receive_v1(_handle_message)
                .build()
            )
            client = LarkWsClient(
                app_id=app_id,
                app_secret=app_secret,
                log_level=lark_oapi.LogLevel.INFO,
                event_handler=event_handler,
                domain=base_url,
                auto_reconnect=True,
            )
            self._runtime_manager.merge_runtime_metadata(
                runtime_id,
                metadata={
                    "lark_ingress_mode": "long_connection",
                    "lark_ingress_account_id": channel_account_id,
                    "lark_ingress_status": "connecting",
                },
                touch_heartbeat=True,
            )
            del stop_event
            client.start()
        except Exception as exc:  # pragma: no cover - network/sdk behavior
            logger.exception("lark long connection ingress failed: %s", exc)
            self._runtime_manager.merge_runtime_metadata(
                runtime_id,
                metadata={
                    "lark_ingress_mode": "long_connection",
                    "lark_ingress_account_id": channel_account_id,
                    "lark_ingress_status": "failed",
                    "lark_ingress_error": f"{type(exc).__name__}:{exc}",
                },
                touch_heartbeat=True,
            )


def _sender_open_id(data: Any) -> str | None:
    event = getattr(data, "event", None)
    sender = getattr(event, "sender", None)
    sender_id = getattr(sender, "sender_id", None)
    return getattr(sender_id, "open_id", None)


def _message_payload(data: Any) -> dict[str, Any]:
    event = getattr(data, "event", None)
    message = getattr(event, "message", None)
    if message is None:
        return {}
    return {
        "message_id": getattr(message, "message_id", None),
        "chat_id": getattr(message, "chat_id", None),
        "chat_type": getattr(message, "chat_type", None),
        "message_type": getattr(message, "message_type", None),
        "content": getattr(message, "content", None),
        "thread_id": getattr(message, "thread_id", None),
        "root_id": getattr(message, "root_id", None),
        "parent_id": getattr(message, "parent_id", None),
        "mentions": [_mention_payload(item) for item in getattr(message, "mentions", None) or []],
    }


def _mention_payload(item: Any) -> dict[str, Any]:
    item_id = getattr(item, "id", None)
    return {
        "key": getattr(item, "key", None),
        "name": getattr(item, "name", None),
        "id": {
            "open_id": getattr(item_id, "open_id", None),
            "user_id": getattr(item_id, "user_id", None),
            "union_id": getattr(item_id, "union_id", None),
        },
    }
