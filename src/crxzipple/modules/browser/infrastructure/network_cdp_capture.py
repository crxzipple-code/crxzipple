from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from crxzipple.modules.browser.application.network_capture import (
    BrowserNetworkCaptureService,
)
from crxzipple.modules.browser.domain import BrowserValidationError

from .cdp_sessions import (
    BrowserCdpSessionBroker,
    BrowserCdpSessionLease,
    display_safe_cdp_error,
)


@dataclass(slots=True)
class _NetworkCaptureSubscription:
    profile_name: str
    target_id: str
    capture_id: str
    session: BrowserCdpSessionLease
    handlers: dict[str, Callable[[Any], None]] = field(default_factory=dict)


@dataclass(slots=True)
class CdpNetworkCaptureController:
    capture_service: BrowserNetworkCaptureService
    cdp_session_broker: BrowserCdpSessionBroker = field(
        default_factory=BrowserCdpSessionBroker,
    )
    _subscriptions: dict[tuple[str, str, str], _NetworkCaptureSubscription] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    def start_capture(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
        page: Any,
    ) -> list[dict[str, str]]:
        errors: list[dict[str, str]] = []
        key = _capture_key(
            profile_name=profile_name,
            target_id=target_id,
            capture_id=capture_id,
        )
        self.stop_capture(
            profile_name=profile_name,
            target_id=target_id,
            capture_id=capture_id,
        )
        try:
            session = self.cdp_session_broker.open_subscription_session(
                page,
                operation="Network capture subscription",
            )
        except Exception as exc:  # noqa: BLE001
            return [
                {
                    "source": "cdp_session",
                    "message": display_safe_cdp_error(
                        exc,
                        operation="Network capture subscription",
                    ),
                }
            ]

        subscription = _NetworkCaptureSubscription(
            profile_name=profile_name,
            target_id=target_id,
            capture_id=capture_id,
            session=session,
        )
        for event_name, handler in self._event_handlers(subscription).items():
            if not _attach_event_handler(session=session, event_name=event_name, handler=handler):
                errors.append(
                    {
                        "source": "cdp_session",
                        "message": "CDP session does not support event subscription.",
                    }
                )
                self.cdp_session_broker.detach(session)
                return errors
            subscription.handlers[event_name] = handler
        try:
            self.cdp_session_broker.send_command(session, "Network.enable", {})
        except Exception as exc:  # noqa: BLE001
            errors.append(
                {
                    "source": "Network.enable",
                    "message": display_safe_cdp_error(
                        exc,
                        operation="Network.enable",
                    ),
                }
            )
            self.cdp_session_broker.detach(session)
            return errors
        self._subscriptions[key] = subscription
        return errors

    def stop_capture(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
    ) -> None:
        subscription = self._subscriptions.pop(
            _capture_key(
                profile_name=profile_name,
                target_id=target_id,
                capture_id=capture_id,
            ),
            None,
        )
        if subscription is None:
            return
        for event_name, handler in subscription.handlers.items():
            _detach_event_handler(
                session=subscription.session,
                event_name=event_name,
                handler=handler,
            )
        self.cdp_session_broker.detach(subscription.session)

    def clear_profile(self, *, profile_name: str) -> None:
        normalized_profile = profile_name.strip().lower()
        keys = [
            key for key in self._subscriptions
            if key[0] == normalized_profile
        ]
        for stored_profile, target_id, capture_id in keys:
            self.stop_capture(
                profile_name=stored_profile,
                target_id=target_id,
                capture_id=capture_id,
            )

    def is_subscribed(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
    ) -> bool:
        return _capture_key(
            profile_name=profile_name,
            target_id=target_id,
            capture_id=capture_id,
        ) in self._subscriptions

    def fetch_response_body(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
        request_id: str,
        page: Any,
    ) -> list[dict[str, str]]:
        key = _capture_key(
            profile_name=profile_name,
            target_id=target_id,
            capture_id=capture_id,
        )
        subscription = self._subscriptions.get(key)
        session = subscription.session if subscription is not None else None
        detach_after = False
        if session is None:
            try:
                session = self.cdp_session_broker.open_command_session(
                    page,
                    operation="Network.getResponseBody",
                )
            except Exception as exc:  # noqa: BLE001
                return [
                    {
                        "source": "cdp_session",
                        "message": display_safe_cdp_error(
                            exc,
                            operation="Network.getResponseBody",
                        ),
                    }
                ]
            detach_after = True
        try:
            self._store_response_body(
                subscription=_NetworkCaptureSubscription(
                    profile_name=profile_name,
                    target_id=target_id,
                    capture_id=capture_id,
                    session=session,
                ),
                request_id=request_id,
            )
        except Exception as exc:  # noqa: BLE001
            return [
                {
                    "source": "Network.getResponseBody",
                    "message": display_safe_cdp_error(
                        exc,
                        operation="Network.getResponseBody",
                    ),
                }
            ]
        finally:
            if detach_after:
                self.cdp_session_broker.detach(session)
        return []

    def _event_handlers(
        self,
        subscription: _NetworkCaptureSubscription,
    ) -> dict[str, Callable[[Any], None]]:
        return {
            "Network.requestWillBeSent": (
                lambda payload: self._on_request_will_be_sent(subscription, payload)
            ),
            "Network.responseReceived": (
                lambda payload: self._on_response_received(subscription, payload)
            ),
            "Network.loadingFinished": (
                lambda payload: self._on_loading_finished(subscription, payload)
            ),
            "Network.loadingFailed": (
                lambda payload: self._on_loading_failed(subscription, payload)
            ),
        }

    def _on_request_will_be_sent(
        self,
        subscription: _NetworkCaptureSubscription,
        payload: Any,
    ) -> None:
        if not isinstance(payload, Mapping):
            return
        request = payload.get("request")
        if not isinstance(request, Mapping):
            return
        request_id = _text(payload.get("requestId"))
        url = _text(request.get("url"))
        method = _text(request.get("method")) or "GET"
        if request_id is None or url is None:
            return
        try:
            self.capture_service.record_request(
                profile_name=subscription.profile_name,
                target_id=subscription.target_id,
                capture_id=subscription.capture_id,
                request_id=request_id,
                url=url,
                method=method,
                resource_type=_text(payload.get("type")) or "other",
                frame_id=_text(payload.get("frameId")),
                loader_id=_text(payload.get("loaderId")),
                request_headers=_mapping(request.get("headers")),
                request_post_data=_text(request.get("postData")),
                initiator=_mapping(payload.get("initiator")),
            )
        except BrowserValidationError:
            return

    def _on_response_received(
        self,
        subscription: _NetworkCaptureSubscription,
        payload: Any,
    ) -> None:
        if not isinstance(payload, Mapping):
            return
        response = payload.get("response")
        if not isinstance(response, Mapping):
            return
        request_id = _text(payload.get("requestId"))
        if request_id is None:
            return
        try:
            self.capture_service.record_response(
                profile_name=subscription.profile_name,
                target_id=subscription.target_id,
                capture_id=subscription.capture_id,
                request_id=request_id,
                status=int(response.get("status") or 0),
                response_headers=_mapping(response.get("headers")),
                mime_type=_text(response.get("mimeType")),
                timing=_mapping(response.get("timing")),
            )
        except Exception:  # noqa: BLE001 - CDP body retrieval is best effort.
            return

    def _on_loading_finished(
        self,
        subscription: _NetworkCaptureSubscription,
        payload: Any,
    ) -> None:
        if not isinstance(payload, Mapping):
            return
        request_id = _text(payload.get("requestId"))
        if request_id is None:
            return
        try:
            encoded_data_length = payload.get("encodedDataLength")
            self.capture_service.record_loading_finished(
                profile_name=subscription.profile_name,
                target_id=subscription.target_id,
                capture_id=subscription.capture_id,
                request_id=request_id,
                encoded_data_length=(
                    int(encoded_data_length)
                    if isinstance(encoded_data_length, (int, float))
                    and not isinstance(encoded_data_length, bool)
                    else None
                ),
            )
            self._store_response_body(subscription=subscription, request_id=request_id)
        except (BrowserValidationError, TypeError, ValueError):
            return

    def _on_loading_failed(
        self,
        subscription: _NetworkCaptureSubscription,
        payload: Any,
    ) -> None:
        if not isinstance(payload, Mapping):
            return
        request_id = _text(payload.get("requestId"))
        if request_id is None:
            return
        try:
            self.capture_service.record_failure(
                profile_name=subscription.profile_name,
                target_id=subscription.target_id,
                capture_id=subscription.capture_id,
                request_id=request_id,
                failure_text=_text(payload.get("errorText")) or "loading failed",
            )
        except BrowserValidationError:
            return

    def _store_response_body(
        self,
        *,
        subscription: _NetworkCaptureSubscription,
        request_id: str,
    ) -> None:
        raw_body = self.cdp_session_broker.send_command(
            subscription.session,
            "Network.getResponseBody",
            {"requestId": request_id},
        )
        if not isinstance(raw_body, Mapping):
            return
        body = raw_body.get("body")
        if not isinstance(body, str):
            return
        if raw_body.get("base64Encoded") is True:
            try:
                body_value: str | bytes = base64.b64decode(body)
            except Exception:  # noqa: BLE001
                body_value = body
        else:
            body_value = body
        request = self.capture_service.get_request(
            profile_name=subscription.profile_name,
            target_id=subscription.target_id,
            capture_id=subscription.capture_id,
            request_id=request_id,
        )
        self.capture_service.record_response_body(
            profile_name=subscription.profile_name,
            target_id=subscription.target_id,
            capture_id=subscription.capture_id,
            request_id=request_id,
            body=body_value,
            mime_type=request.mime_type,
        )


def _attach_event_handler(
    *,
    session: Any,
    event_name: str,
    handler: Callable[[Any], None],
) -> bool:
    on = getattr(session, "on", None)
    if not callable(on):
        return False
    on(event_name, handler)
    return True


def _detach_event_handler(
    *,
    session: Any,
    event_name: str,
    handler: Callable[[Any], None],
) -> None:
    for method_name in ("off", "remove_listener", "removeListener"):
        method = getattr(session, method_name, None)
        if not callable(method):
            continue
        try:
            method(event_name, handler)
            return
        except TypeError:
            continue


def _capture_key(
    *,
    profile_name: str,
    target_id: str,
    capture_id: str,
) -> tuple[str, str, str]:
    return (profile_name.strip().lower(), str(target_id).strip(), str(capture_id).strip())


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}
