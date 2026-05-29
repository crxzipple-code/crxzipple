from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from crxzipple.modules.browser.application.events import (
    BROWSER_ENVIRONMENT_CHANGED_EVENT,
    BrowserEventEmitter,
    emit_browser_event,
)
from crxzipple.modules.browser.domain import BrowserValidationError

from .cdp_sessions import BrowserCdpSessionBroker
from crxzipple.modules.browser.domain.value_objects import _normalize_optional_text

_ENVIRONMENT_CONTROL_KINDS = frozenset(
    {
        "emulation-set",
        "emulation-reset",
        "permissions-grant",
        "permissions-clear",
        "geolocation-set",
        "network-conditions-set",
    }
)
_ALLOWED_PERMISSIONS = frozenset(
    {
        "accessibility-events",
        "audio-capture",
        "background-sync",
        "camera",
        "clipboard-read",
        "clipboard-sanitized-write",
        "clipboard-write",
        "display-capture",
        "geolocation",
        "idle-detection",
        "midi",
        "midi-sysex",
        "nfc",
        "notifications",
        "payment-handler",
        "periodic-background-sync",
        "protected-media-identifier",
        "sensors",
        "storage-access",
        "video-capture",
        "window-management",
    }
)
_CONNECTION_TYPES = frozenset(
    {
        "none",
        "cellular2g",
        "cellular3g",
        "cellular4g",
        "bluetooth",
        "ethernet",
        "wifi",
        "wimax",
        "other",
    }
)


@dataclass(slots=True)
class BrowserEnvironmentControlService:
    event_emitter: BrowserEventEmitter | None = None

    def execute(
        self,
        *,
        page: Any,
        kind: str,
        payload: Mapping[str, Any],
        profile_name: str | None = None,
        target_id: str | None = None,
        page_url: str | None = None,
    ) -> dict[str, Any]:
        normalized_kind = _normalize_kind(kind)
        raw_payload = dict(payload)
        if normalized_kind == "emulation-set":
            result = self._set_emulation(page=page, payload=raw_payload)
        elif normalized_kind == "emulation-reset":
            result = self._reset_emulation(page=page, payload=raw_payload)
        elif normalized_kind == "permissions-grant":
            result = self._grant_permissions(page=page, payload=raw_payload)
        elif normalized_kind == "permissions-clear":
            result = self._clear_permissions(page=page, payload=raw_payload)
        elif normalized_kind == "geolocation-set":
            result = self._set_geolocation(page=page, payload=raw_payload)
        elif normalized_kind == "network-conditions-set":
            result = self._set_network_conditions(page=page, payload=raw_payload)
        else:  # pragma: no cover - guarded by _normalize_kind
            raise BrowserValidationError(f"Unsupported browser environment kind '{kind}'.")

        result.update(
            {
                "kind": normalized_kind,
                "profile_name": profile_name,
                "target_id": target_id,
                "page_url": page_url,
                "policy": {
                    "runtime_scope": result.get("environment_scope"),
                    "profile_name": profile_name,
                    "persistent_profile_affected": bool(
                        result.get("persistent_profile_affected"),
                    ),
                    "allowed_by": "browser-profile-runtime-policy",
                },
            }
        )
        self._emit_change(
            profile_name=profile_name,
            target_id=target_id,
            page_url=page_url,
            result=result,
        )
        return result

    def _set_emulation(self, *, page: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
        commands: list[str] = []
        changed: list[str] = []
        session = _new_page_cdp_session(page)
        try:
            metrics = _device_metrics_payload(payload)
            if metrics is not None:
                _send_cdp_session_command(
                    session,
                    "Emulation.setDeviceMetricsOverride",
                    metrics,
                )
                commands.append("Emulation.setDeviceMetricsOverride")
                changed.append("device_metrics")
            user_agent = _payload_text(payload, "user_agent", "userAgent")
            if user_agent is not None:
                _send_cdp_session_command(
                    session,
                    "Emulation.setUserAgentOverride",
                    {"userAgent": user_agent},
                )
                commands.append("Emulation.setUserAgentOverride")
                changed.append("user_agent")
            timezone_id = _payload_text(payload, "timezone_id", "timezoneId", "timezone")
            if timezone_id is not None:
                _send_cdp_session_command(
                    session,
                    "Emulation.setTimezoneOverride",
                    {"timezoneId": timezone_id},
                )
                commands.append("Emulation.setTimezoneOverride")
                changed.append("timezone")
            locale = _payload_text(payload, "locale")
            if locale is not None:
                _send_cdp_session_command(
                    session,
                    "Emulation.setLocaleOverride",
                    {"locale": locale},
                )
                commands.append("Emulation.setLocaleOverride")
                changed.append("locale")
        finally:
            _detach_cdp_session(session)
        if not changed:
            raise BrowserValidationError(
                "browser.emulation.set requires viewport, user_agent, timezone_id, or locale.",
            )
        return {
            "environment_scope": "target",
            "persistent_profile_affected": False,
            "changed_controls": changed,
            "commands": commands,
            "device_metrics": metrics,
            "user_agent_set": user_agent is not None,
            "timezone_id": timezone_id,
            "locale": locale,
        }

    def _reset_emulation(self, *, page: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
        flags = {
            "device_metrics": _payload_bool(payload, "device_metrics", "viewport"),
            "geolocation": _payload_bool(payload, "geolocation"),
            "network_conditions": _payload_bool(
                payload,
                "network_conditions",
                "networkConditions",
            ),
            "timezone": _payload_bool(payload, "timezone"),
            "locale": _payload_bool(payload, "locale"),
            "user_agent": _payload_bool(payload, "user_agent", "userAgent"),
            "permissions": _payload_bool(payload, "permissions"),
        }
        reset_all = all(value is None for value in flags.values())
        commands: list[str] = []
        changed: list[str] = []
        warnings: list[str] = []
        session = _new_page_cdp_session(page)
        try:
            if _enabled(flags["device_metrics"], reset_all):
                _send_cdp_session_command(session, "Emulation.clearDeviceMetricsOverride", {})
                commands.append("Emulation.clearDeviceMetricsOverride")
                changed.append("device_metrics")
            if _enabled(flags["geolocation"], reset_all):
                _send_cdp_session_command(session, "Emulation.clearGeolocationOverride", {})
                commands.append("Emulation.clearGeolocationOverride")
                changed.append("geolocation")
            if _enabled(flags["network_conditions"], reset_all):
                _send_cdp_session_command(session, "Network.enable", {})
                _send_cdp_session_command(
                    session,
                    "Network.emulateNetworkConditions",
                    {
                        "offline": False,
                        "latency": 0,
                        "downloadThroughput": -1,
                        "uploadThroughput": -1,
                    },
                )
                commands.extend(("Network.enable", "Network.emulateNetworkConditions"))
                changed.append("network_conditions")
            if _enabled(flags["timezone"], reset_all):
                _send_cdp_session_command(
                    session,
                    "Emulation.setTimezoneOverride",
                    {"timezoneId": ""},
                )
                commands.append("Emulation.setTimezoneOverride")
                changed.append("timezone")
            if _enabled(flags["locale"], reset_all):
                _send_cdp_session_command(
                    session,
                    "Emulation.setLocaleOverride",
                    {"locale": ""},
                )
                commands.append("Emulation.setLocaleOverride")
                changed.append("locale")
            if _enabled(flags["user_agent"], reset_all):
                version = _send_cdp_session_command(session, "Browser.getVersion", {})
                default_user_agent = (
                    _payload_text(version, "userAgent")
                    if isinstance(version, Mapping)
                    else None
                )
                if default_user_agent is None:
                    warnings.append("default_user_agent_unavailable")
                else:
                    _send_cdp_session_command(
                        session,
                        "Emulation.setUserAgentOverride",
                        {"userAgent": default_user_agent},
                    )
                    commands.extend(
                        ("Browser.getVersion", "Emulation.setUserAgentOverride")
                    )
                    changed.append("user_agent")
        finally:
            _detach_cdp_session(session)
        permission_changed = False
        if _enabled(flags["permissions"], reset_all):
            permission_changed = self._clear_browser_permissions(page=page, origin=None)
            changed.append("permissions")
        return {
            "environment_scope": "target",
            "persistent_profile_affected": False,
            "changed_controls": changed,
            "commands": commands,
            "permissions_cleared": permission_changed,
            "warnings": warnings,
        }

    def _grant_permissions(self, *, page: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
        permissions = _permission_names(payload)
        origin = _payload_text(payload, "origin")
        page_context = _page_context(page)
        grant_permissions = getattr(page_context, "grant_permissions", None)
        command = "context.grant_permissions"
        if callable(grant_permissions):
            if origin is None:
                grant_permissions(permissions)
            else:
                grant_permissions(permissions, origin=origin)
        else:
            session = _new_page_cdp_session(page)
            try:
                params: dict[str, Any] = {"permissions": permissions}
                if origin is not None:
                    params["origin"] = origin
                _send_cdp_session_command(session, "Browser.grantPermissions", params)
                command = "Browser.grantPermissions"
            finally:
                _detach_cdp_session(session)
        return {
            "environment_scope": "browser_context",
            "persistent_profile_affected": False,
            "changed_controls": ["permissions"],
            "permission_names": permissions,
            "origin": origin,
            "commands": [command],
        }

    def _clear_permissions(self, *, page: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
        origin = _payload_text(payload, "origin")
        cleared = self._clear_browser_permissions(page=page, origin=origin)
        return {
            "environment_scope": "browser_context",
            "persistent_profile_affected": False,
            "changed_controls": ["permissions"],
            "permission_names": [],
            "origin": origin,
            "permissions_cleared": cleared,
        }

    def _set_geolocation(self, *, page: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
        latitude = _payload_number(payload, "latitude", minimum=-90, maximum=90)
        longitude = _payload_number(payload, "longitude", minimum=-180, maximum=180)
        if latitude is None or longitude is None:
            raise BrowserValidationError("latitude and longitude are required.")
        accuracy = _payload_number(payload, "accuracy", minimum=0) or 0
        session = _new_page_cdp_session(page)
        try:
            _send_cdp_session_command(
                session,
                "Emulation.setGeolocationOverride",
                {
                    "latitude": latitude,
                    "longitude": longitude,
                    "accuracy": accuracy,
                },
            )
        finally:
            _detach_cdp_session(session)
        return {
            "environment_scope": "target",
            "persistent_profile_affected": False,
            "changed_controls": ["geolocation"],
            "geolocation": {
                "latitude": latitude,
                "longitude": longitude,
                "accuracy": accuracy,
            },
            "commands": ["Emulation.setGeolocationOverride"],
        }

    def _set_network_conditions(
        self,
        *,
        page: Any,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        offline = _payload_bool(payload, "offline")
        if offline is None:
            offline = False
        latency = _payload_number(payload, "latency_ms", "latency", minimum=0) or 0
        download = _throughput_bytes(payload, "download")
        upload = _throughput_bytes(payload, "upload")
        connection_type = _payload_text(payload, "connection_type", "connectionType")
        params: dict[str, Any] = {
            "offline": bool(offline),
            "latency": latency,
            "downloadThroughput": download,
            "uploadThroughput": upload,
        }
        if connection_type is not None:
            normalized_connection = connection_type.strip().lower()
            if normalized_connection not in _CONNECTION_TYPES:
                allowed = ", ".join(sorted(_CONNECTION_TYPES))
                raise BrowserValidationError(
                    f"connection_type must be one of {allowed}.",
                )
            params["connectionType"] = normalized_connection
        session = _new_page_cdp_session(page)
        try:
            _send_cdp_session_command(session, "Network.enable", {})
            _send_cdp_session_command(session, "Network.emulateNetworkConditions", params)
        finally:
            _detach_cdp_session(session)
        return {
            "environment_scope": "target",
            "persistent_profile_affected": False,
            "changed_controls": ["network_conditions"],
            "network_conditions": {
                "offline": bool(offline),
                "latency_ms": latency,
                "download_throughput_bytes_per_second": download,
                "upload_throughput_bytes_per_second": upload,
                "connection_type": params.get("connectionType"),
            },
            "commands": ["Network.enable", "Network.emulateNetworkConditions"],
        }

    def _clear_browser_permissions(self, *, page: Any, origin: str | None) -> bool:
        page_context = _page_context(page)
        clear_permissions = getattr(page_context, "clear_permissions", None)
        if callable(clear_permissions):
            clear_permissions()
            return True
        session = _new_page_cdp_session(page)
        try:
            params: dict[str, Any] = {}
            if origin is not None:
                params["origin"] = origin
            _send_cdp_session_command(session, "Browser.resetPermissions", params)
        finally:
            _detach_cdp_session(session)
        return True

    def _emit_change(
        self,
        *,
        profile_name: str | None,
        target_id: str | None,
        page_url: str | None,
        result: Mapping[str, Any],
    ) -> None:
        changed = tuple(
            str(item)
            for item in result.get("changed_controls", ())
            if str(item).strip()
        )
        emit_browser_event(
            self.event_emitter,
            BROWSER_ENVIRONMENT_CHANGED_EVENT,
            payload={
                "profile_name": profile_name,
                "target_id": target_id,
                "page_url": page_url,
                "environment_action": result.get("kind"),
                "environment_scope": result.get("environment_scope"),
                "persistent_profile_affected": bool(
                    result.get("persistent_profile_affected"),
                ),
                "changed_controls": changed,
                "permission_names": tuple(
                    str(item)
                    for item in result.get("permission_names", ())
                    if str(item).strip()
                ),
                "entity_type": "browser.environment",
                "entity_id": f"{profile_name or 'unknown'}:{target_id or 'unknown'}",
                "display_label": "Browser environment changed",
                "display_summary": ", ".join(changed) if changed else "No controls changed",
                "summary": (
                    f"Browser environment {result.get('kind')} changed "
                    f"{', '.join(changed) if changed else 'no controls'}."
                ),
            },
            status="updated",
            level="info",
        )


def _normalize_kind(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in _ENVIRONMENT_CONTROL_KINDS:
        supported = ", ".join(sorted(_ENVIRONMENT_CONTROL_KINDS))
        raise BrowserValidationError(f"kind must be one of {supported}.")
    return normalized


def _page_context(page: Any) -> Any:
    page_context = getattr(page, "context", None)
    if callable(page_context):
        page_context = page_context()
    if page_context is None:
        raise BrowserValidationError("Playwright page does not expose a browser context.")
    return page_context


def _new_page_cdp_session(page: Any) -> Any:
    return BrowserCdpSessionBroker().open_command_session(page)


def _send_cdp_session_command(
    session: Any,
    method: str,
    params: Mapping[str, Any] | None = None,
) -> Any:
    return BrowserCdpSessionBroker().send_command(session, method, params)


def _detach_cdp_session(session: Any) -> None:
    BrowserCdpSessionBroker().detach(session)


def _payload_text(payload: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = _normalize_optional_text(payload.get(key))
        if value is not None:
            return value
    return None


def _payload_bool(payload: Mapping[str, Any], *keys: str) -> bool | None:
    for key in keys:
        value = payload.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True
            if normalized in {"false", "0", "no", "off"}:
                return False
        raise BrowserValidationError(f"{key} must be a boolean.")
    return None


def _payload_number(
    payload: Mapping[str, Any],
    *keys: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float | None:
    for key in keys:
        value = payload.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, bool):
            raise BrowserValidationError(f"{key} must be a number.")
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise BrowserValidationError(f"{key} must be a number.") from exc
        if minimum is not None and numeric < minimum:
            raise BrowserValidationError(
                f"{key} must be greater than or equal to {minimum}.",
            )
        if maximum is not None and numeric > maximum:
            raise BrowserValidationError(
                f"{key} must be less than or equal to {maximum}.",
            )
        return numeric
    return None


def _payload_int(
    payload: Mapping[str, Any],
    *keys: str,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int | None:
    value = _payload_number(payload, *keys, minimum=minimum, maximum=maximum)
    if value is None:
        return None
    return int(value)


def _enabled(value: bool | None, reset_all: bool) -> bool:
    return reset_all if value is None else bool(value)


def _device_metrics_payload(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    width = _payload_int(payload, "width", minimum=1, maximum=16384)
    height = _payload_int(payload, "height", minimum=1, maximum=16384)
    scale = _payload_number(
        payload,
        "device_scale_factor",
        "deviceScaleFactor",
        minimum=0.1,
        maximum=10,
    )
    mobile = _payload_bool(payload, "is_mobile", "mobile")
    touch = _payload_bool(payload, "has_touch", "touch")
    if all(value is None for value in (width, height, scale, mobile, touch)):
        return None
    if width is None or height is None:
        raise BrowserValidationError(
            "width and height are required when changing device metrics.",
        )
    return {
        "width": width,
        "height": height,
        "deviceScaleFactor": 1 if scale is None else scale,
        "mobile": bool(mobile) if mobile is not None else False,
        "screenWidth": width,
        "screenHeight": height,
        "dontSetVisibleSize": False,
        "screenOrientation": {
            "type": "portraitPrimary" if height >= width else "landscapePrimary",
            "angle": 0,
        },
        **({"hasTouch": bool(touch)} if touch is not None else {}),
    }


def _permission_names(payload: Mapping[str, Any]) -> list[str]:
    raw_value = payload.get("permissions")
    if raw_value is None:
        raw_value = payload.get("permission_names")
    if isinstance(raw_value, str):
        values = [item.strip() for item in raw_value.split(",")]
    elif isinstance(raw_value, (list, tuple)):
        values = [str(item).strip() for item in raw_value]
    else:
        raise BrowserValidationError("permissions must be a string or list.")
    permissions = [
        value.lower()
        for value in values
        if value
    ]
    unknown = sorted(set(permissions) - _ALLOWED_PERMISSIONS)
    if unknown:
        raise BrowserValidationError(
            "Unsupported browser permissions: " + ", ".join(unknown) + ".",
        )
    if not permissions:
        raise BrowserValidationError("permissions cannot be empty.")
    return list(dict.fromkeys(permissions))


def _throughput_bytes(payload: Mapping[str, Any], prefix: str) -> int:
    bytes_value = _payload_int(
        payload,
        f"{prefix}_throughput_bytes_per_second",
        f"{prefix}ThroughputBytesPerSecond",
        minimum=-1,
    )
    if bytes_value is not None:
        return bytes_value
    kbps_value = _payload_number(
        payload,
        f"{prefix}_kbps",
        f"{prefix}Kbps",
        minimum=0,
    )
    if kbps_value is None:
        return -1
    return int(kbps_value * 1024 / 8)


__all__ = ["BrowserEnvironmentControlService"]
