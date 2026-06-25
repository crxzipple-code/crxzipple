from __future__ import annotations

import json
from typing import Any

import typer

from crxzipple.interfaces.cli.context import AppKey

from .profile_payloads import (
    build_allocations_payload,
    build_pools_payload,
    build_profiles_payload,
)
from .requests import BrowserControlRequest


def _load_payload(raw: str | None) -> dict[str, Any]:
    if raw is None:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter("payload must be valid JSON.") from exc
    if not isinstance(payload, dict):
        raise typer.BadParameter("payload JSON must decode to an object.")
    return dict(payload)


def _default_profile(container) -> str:  # noqa: ANN001
    return container.require(AppKey.BROWSER_SYSTEM_CONFIG_STORE).load().default_profile


def _system_config(container):  # noqa: ANN001
    return container.require(AppKey.BROWSER_SYSTEM_CONFIG_STORE).load()


def _profiles_payload(container, system_config=None) -> dict[str, object]:  # noqa: ANN001
    return build_profiles_payload(container, system_config=system_config)


def _pools_payload(container) -> dict[str, object]:  # noqa: ANN001
    return build_pools_payload(container)


def _allocations_payload(container) -> dict[str, object]:  # noqa: ANN001
    return build_allocations_payload(container)


def _execute_control_payload(
    container, *, profile_name: str, kind: str
) -> dict[str, Any]:  # noqa: ANN001
    result = container.require(AppKey.BROWSER_FACADE).execute(
        BrowserControlRequest(
            profile_name=profile_name,
            kind=kind,
        ),
    )
    return container.require(AppKey.BROWSER_RESULT_SERIALIZER).serialize(result)


def _close_container(container) -> None:  # noqa: ANN001
    close = getattr(container, "close", None)
    if callable(close):
        close()


def _resolve_profile_update_kwargs(
    *,
    driver: str | None,
    enabled: bool | None,
    cdp_url: str | None,
    cdp_port: int | None,
    clear_cdp_port: bool,
    user_data_dir: str | None,
    profile_directory: str | None,
    attach_only: bool | None,
    autostart: bool | None,
    proxy_mode: str | None,
    proxy_server: str | None,
    proxy_bypass_list: tuple[str, ...],
    clear_proxy_bypass_list: bool,
    proxy_binding_id: str | None,
    proxy_credential_kind: str | None,
    close_targets_on_release: bool | None,
    close_targets_on_expire: bool | None,
    set_default: bool,
) -> dict[str, object]:
    updates: dict[str, object] = {}
    if driver is not None:
        updates["driver"] = driver
    if enabled is not None:
        updates["enabled"] = enabled
    if cdp_url is not None:
        updates["cdp_url"] = cdp_url
    if cdp_port is not None:
        updates["cdp_port"] = cdp_port
    if clear_cdp_port:
        updates["cdp_port"] = None
    if user_data_dir is not None:
        updates["user_data_dir"] = user_data_dir
    if profile_directory is not None:
        updates["profile_directory"] = profile_directory
    if attach_only is not None:
        updates["attach_only"] = attach_only
    if autostart is not None:
        updates["autostart"] = autostart
    if proxy_mode is not None:
        updates["proxy_mode"] = proxy_mode
    if proxy_server is not None:
        updates["proxy_server"] = proxy_server
    if proxy_bypass_list:
        updates["proxy_bypass_list"] = proxy_bypass_list
    if clear_proxy_bypass_list:
        updates["proxy_bypass_list"] = ()
    if proxy_binding_id is not None:
        updates["proxy_binding_id"] = proxy_binding_id
    if proxy_credential_kind is not None:
        updates["proxy_credential_kind"] = proxy_credential_kind
    if close_targets_on_release is not None:
        updates["close_targets_on_release"] = close_targets_on_release
    if close_targets_on_expire is not None:
        updates["close_targets_on_expire"] = close_targets_on_expire
    if set_default:
        updates["set_as_default"] = True
    return updates
