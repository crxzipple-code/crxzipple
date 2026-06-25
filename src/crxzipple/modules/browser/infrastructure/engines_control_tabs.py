from __future__ import annotations

from typing import Any

import requests

from crxzipple.modules.browser.domain import (
    BrowserExecutionPlan,
    BrowserProfileRuntimeState,
    BrowserTab,
    BrowserValidationError,
)

from .cdp_urls import append_cdp_path, build_cdp_json_new_endpoint
from .daemon_leases import host_daemon_lease
from .engines_cdp_io import (
    request_error_message as _request_error_message,
    send_cdp_command as _send_cdp_command,
)
from .engines_tab_state import (
    METADATA_ACTIVE_TARGET_KEY as _METADATA_ACTIVE_TARGET_KEY,
    canonicalize_opened_tab as _canonicalize_opened_tab,
    set_active_target as _set_active_target,
    store_tabs as _store_tabs,
    tab_from_cdp_payload as _tab_from_cdp_payload,
)


class CdpControlTabMixin:
    def list_tabs(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
    ) -> tuple[BrowserTab, ...]:
        with host_daemon_lease(
            daemon_service=self.daemon_service,
            plan=plan,
            user_data_dir=self._try_resolve_user_data_dir(plan=plan),
        ):
            return self._list_tabs_unleased(plan=plan, runtime_state=runtime_state)

    def open_tab(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
        url: str,
    ) -> BrowserTab:
        with host_daemon_lease(
            daemon_service=self.daemon_service,
            plan=plan,
            user_data_dir=self._try_resolve_user_data_dir(plan=plan),
        ):
            base_url = self._current_cdp_base_url(plan=plan, runtime_state=runtime_state)
            payload, base_url = self._request_cdp_json(
                plan=plan,
                runtime_state=runtime_state,
                path=build_cdp_json_new_endpoint(base_url, url).removeprefix(base_url),
                methods=("put", "get"),
            )

            if not isinstance(payload, dict):
                raise BrowserValidationError("Browser CDP open-tab returned an invalid payload.")
            tab = _tab_from_cdp_payload(
                payload,
                include_ws_url=plan.capabilities.supports_per_tab_ws,
                include_json_endpoints=plan.capabilities.supports_json_tab_endpoints,
                base_url=base_url,
            )
            tabs = (
                self._list_tabs_unleased(plan=plan, runtime_state=runtime_state)
                if self._host_daemon_enabled(plan=plan)
                else self.list_tabs(plan=plan, runtime_state=runtime_state)
            )
            tab = _canonicalize_opened_tab(opened_tab=tab, live_tabs=tabs)
            _store_tabs(runtime_state, tabs)
            _set_active_target(runtime_state, tab.target_id)
            return tab

    def navigate_tab(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
        target_id: str,
        url: str,
    ) -> BrowserTab:
        with host_daemon_lease(
            daemon_service=self.daemon_service,
            plan=plan,
            user_data_dir=self._try_resolve_user_data_dir(plan=plan),
        ):
            base_url = self._current_cdp_base_url(plan=plan, runtime_state=runtime_state)
            payload = self._require_tab_payload(plan=plan, target_id=target_id)
            ws_url = str(payload.get("webSocketDebuggerUrl", "")).strip()
            if not ws_url:
                raise BrowserValidationError(
                    f"Browser tab '{target_id}' does not expose a websocket debugger URL.",
                )
            _send_cdp_command(
                ws_connect=self.ws_connect,
                ws_url=ws_url,
                method="Page.navigate",
                params={"url": url},
                timeout_s=self.request_timeout_s,
            )
            refreshed_payload = self._require_tab_payload(plan=plan, target_id=target_id)
            tab = _tab_from_cdp_payload(
                refreshed_payload,
                include_ws_url=plan.capabilities.supports_per_tab_ws,
                include_json_endpoints=plan.capabilities.supports_json_tab_endpoints,
                base_url=base_url,
            )
            tabs = (
                self._list_tabs_unleased(plan=plan, runtime_state=runtime_state)
                if self._host_daemon_enabled(plan=plan)
                else self.list_tabs(plan=plan, runtime_state=runtime_state)
            )
            _store_tabs(runtime_state, tabs)
            _set_active_target(runtime_state, tab.target_id)
            return tab

    def focus_tab(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
        target_id: str,
    ) -> BrowserTab:
        with host_daemon_lease(
            daemon_service=self.daemon_service,
            plan=plan,
            user_data_dir=self._try_resolve_user_data_dir(plan=plan),
        ):
            base_url = self._current_cdp_base_url(plan=plan, runtime_state=runtime_state)
            request_url = append_cdp_path(base_url, f"/json/activate/{target_id}")
            try:
                response = self._http.get(request_url, timeout=self.request_timeout_s)
                response.raise_for_status()
            except requests.RequestException as exc:
                raise BrowserValidationError(
                    _request_error_message(method="get", url=request_url, exc=exc),
                ) from exc
            tab = _tab_from_cdp_payload(
                self._require_tab_payload(plan=plan, target_id=target_id),
                include_ws_url=plan.capabilities.supports_per_tab_ws,
                include_json_endpoints=plan.capabilities.supports_json_tab_endpoints,
                base_url=base_url,
            )
            tabs = (
                self._list_tabs_unleased(plan=plan, runtime_state=runtime_state)
                if self._host_daemon_enabled(plan=plan)
                else self.list_tabs(plan=plan, runtime_state=runtime_state)
            )
            _store_tabs(runtime_state, tabs)
            _set_active_target(runtime_state, tab.target_id)
            return tab

    def close_tab(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
        target_id: str,
    ) -> None:
        with host_daemon_lease(
            daemon_service=self.daemon_service,
            plan=plan,
            user_data_dir=self._try_resolve_user_data_dir(plan=plan),
        ):
            base_url = self._current_cdp_base_url(plan=plan, runtime_state=runtime_state)
            request_url = append_cdp_path(base_url, f"/json/close/{target_id}")
            try:
                response = self._http.get(request_url, timeout=self.request_timeout_s)
                response.raise_for_status()
            except requests.RequestException as exc:
                raise BrowserValidationError(
                    _request_error_message(method="get", url=request_url, exc=exc),
                ) from exc
            tabs = (
                self._list_tabs_unleased(plan=plan, runtime_state=runtime_state)
                if self._host_daemon_enabled(plan=plan)
                else self.list_tabs(plan=plan, runtime_state=runtime_state)
            )
            _store_tabs(runtime_state, tabs)
            active_target = runtime_state.metadata.get(_METADATA_ACTIVE_TARGET_KEY)
            if active_target == target_id:
                _set_active_target(runtime_state, tabs[0].target_id if tabs else None)

    def _list_tab_payloads(
        self,
        *,
        plan: BrowserExecutionPlan,
    ) -> tuple[dict[str, Any], ...]:
        payload, _ = self._request_cdp_json(
            plan=plan,
            runtime_state=None,
            path="/json/list",
        )
        if not isinstance(payload, list):
            raise BrowserValidationError("Browser CDP list-tabs returned an invalid payload.")
        resolved: list[dict[str, Any]] = []
        for item in payload:
            if isinstance(item, dict):
                resolved.append(dict(item))
        return tuple(resolved)

    def _list_tabs_unleased(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
    ) -> tuple[BrowserTab, ...]:
        base_url = self._current_cdp_base_url(plan=plan, runtime_state=runtime_state)
        payloads = self._list_tab_payloads(plan=plan)
        return tuple(
            _tab_from_cdp_payload(
                payload,
                include_ws_url=plan.capabilities.supports_per_tab_ws,
                include_json_endpoints=plan.capabilities.supports_json_tab_endpoints,
                base_url=base_url,
            )
            for payload in payloads
            if str(payload.get("id", "")).strip()
        )

    def _require_tab_payload(
        self,
        *,
        plan: BrowserExecutionPlan,
        target_id: str,
    ) -> dict[str, Any]:
        for payload in self._list_tab_payloads(plan=plan):
            if str(payload.get("id", "")).strip() == target_id:
                return payload
        raise BrowserValidationError(f"Browser tab '{target_id}' was not found.")


__all__ = ["CdpControlTabMixin"]
