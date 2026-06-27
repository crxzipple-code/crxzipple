from __future__ import annotations

from typing import Any

import requests

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.modules.browser.domain import BrowserValidationError
from crxzipple.modules.browser.infrastructure import BrowserLocalProxyAdapter
from crxzipple.modules.browser.infrastructure.error_projection import (
    display_safe_exception_message,
)
from crxzipple.shared.access import AccessConsumerRef

from .http_profile_helpers import _profile_by_name, _system_config


def _extract_ipish_value(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        return text[:120] if text else "-"
    if isinstance(payload, dict):
        for key in ("ip", "origin", "query", "remote_addr"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return "-"


def _test_static_proxy_egress(
    *,
    proxy_server: str,
    url: str,
    timeout_s: float,
) -> dict[str, Any]:
    session = requests.Session()
    session.trust_env = False
    try:
        response = session.get(
            url,
            proxies={"http": proxy_server, "https": proxy_server},
            timeout=timeout_s,
        )
        response.raise_for_status()
        return {
            "status": "ready",
            "ip": _extract_ipish_value(response),
            "url": url,
            "http_status": response.status_code,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "failed",
            "reason": display_safe_exception_message(exc),
            "url": display_safe_exception_message(url),
        }
    finally:
        session.close()


def _test_profile_egress(
    container: AppContainer,
    *,
    profile_name: str,
    url: str | None,
    timeout_s: float,
) -> dict[str, Any]:
    settings = container.require(AppKey.CORE_SETTINGS)
    test_url = (
        url or getattr(settings, "browser_proxy_egress_check_url", None) or ""
    ).strip()
    if not test_url:
        raise BrowserValidationError(
            "browser_proxy_egress_check_url is required to test browser proxy egress.",
        )
    system_config = _system_config(container)
    profile = _profile_by_name(system_config, profile_name)
    if profile.proxy_mode == "none":
        return {
            "profile": profile.name,
            "attempted": False,
            "status": "not_required",
            "proxy_mode": profile.proxy_mode,
            "url": test_url,
        }
    if profile.proxy_mode == "static":
        if profile.proxy_server is None:
            raise BrowserValidationError(
                "proxy_server is required for static proxy egress test."
            )
        return {
            "profile": profile.name,
            "attempted": True,
            "proxy_mode": profile.proxy_mode,
            "result": _test_static_proxy_egress(
                proxy_server=profile.proxy_server,
                url=test_url,
                timeout_s=timeout_s,
            ),
        }
    if profile.proxy_mode != "access_binding":
        raise BrowserValidationError(f"Unsupported proxy mode '{profile.proxy_mode}'.")
    if profile.proxy_server is None or profile.proxy_binding_id is None:
        raise BrowserValidationError(
            "proxy_server and proxy_binding_id are required for access_binding proxy egress test.",
        )
    credential = container.require(AppKey.ACCESS_SERVICE).resolve_credential(
        profile.proxy_binding_id,
        expected_kind=profile.proxy_credential_kind,
        consumer=AccessConsumerRef(
            consumer_id=f"browser.profile:{profile.name}:proxy",
            module="browser",
            component="profile_proxy",
            runtime_ref=profile.name,
        ),
    )
    adapter = BrowserLocalProxyAdapter(
        upstream_proxy_url=profile.proxy_server,
        credential=str(credential),
        credential_kind=profile.proxy_credential_kind,
    )
    try:
        adapter.start()
        result = adapter.check_egress(test_url, timeout_s=timeout_s)
    finally:
        adapter.close()
    return {
        "profile": profile.name,
        "attempted": True,
        "proxy_mode": profile.proxy_mode,
        "binding_id": profile.proxy_binding_id,
        "result": result,
    }


def _record_profile_egress(
    container: AppContainer,
    *,
    profile_name: str,
    response: dict[str, Any],
) -> None:
    result = response.get("result")
    if not isinstance(result, dict):
        return
    container.require(AppKey.BROWSER_PROFILE_ADMIN_SERVICE).record_profile_egress(
        profile_name=profile_name,
        result=result,
    )
