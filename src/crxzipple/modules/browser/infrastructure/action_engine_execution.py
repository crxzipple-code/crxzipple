from __future__ import annotations

from typing import Any

from crxzipple.modules.browser.domain import (
    BrowserActionResult,
    BrowserExecutionPlan,
    BrowserPageActionCommand,
    BrowserProfileRuntimeState,
    BrowserTab,
    BrowserValidationError,
)

from .action_engine_payloads import (
    _ACTION_EFFECT_KINDS,
    _action_result_envelope,
    _action_result_message,
    _capture_action_effect_page_state,
    _RETRYABLE_TRANSIENT_ACTION_KINDS,
    _serialize_frame_path,
    _serialize_tab,
    _SUPPORTED_KINDS,
)
from .action_engine_snapshots import _is_transient_page_context_error
from .cdp_urls import browser_ref_to_cdp_http_base
from .daemon_leases import host_daemon_lease


def _host_lease_user_data_dir(
    *,
    plan: BrowserExecutionPlan,
    runtime_state: BrowserProfileRuntimeState,
) -> str | None:
    runtime_user_data_dir = runtime_state.metadata.get("user_data_dir")
    if isinstance(runtime_user_data_dir, str) and runtime_user_data_dir.strip():
        return runtime_user_data_dir.strip()
    return plan.profile.user_data_dir


class BrowserActionExecutionMixin:
    def supports(
        self,
        *,
        command: BrowserPageActionCommand,
    ) -> bool:
        return command.kind in _SUPPORTED_KINDS

    def execute(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
        tab: BrowserTab | None,
        command: BrowserPageActionCommand,
    ) -> BrowserActionResult:
        if tab is None:
            raise BrowserValidationError("cdp-backed-playwright actions require a tab.")
        with host_daemon_lease(
            daemon_service=self.daemon_service,
            plan=plan,
            user_data_dir=_host_lease_user_data_dir(
                plan=plan,
                runtime_state=runtime_state,
            ),
        ):
            cdp_url = self._runtime_cdp_url(plan=plan, runtime_state=runtime_state)
            max_attempts = (
                2
                if command.kind in _RETRYABLE_TRANSIENT_ACTION_KINDS
                else 1
            )
            last_error: Exception | None = None
            effect_before: dict[str, Any] | None = None
            for attempt in range(max_attempts):
                page = self.session_pool.resolve_page(
                    profile=plan.profile,
                    target_id=tab.target_id,
                    timeout_ms=command.timeout_ms,
                    cdp_url=cdp_url,
                )
                try:
                    effect_before = (
                        _capture_action_effect_page_state(page)
                        if command.kind in _ACTION_EFFECT_KINDS
                        else None
                    )
                    result_value, resolved_selector, resolved_frame_path = self._execute_on_page(
                        plan=plan,
                        tab=tab,
                        page=page,
                        runtime_state=runtime_state,
                        command=command,
                    )
                    break
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    if attempt + 1 < max_attempts and _is_transient_page_context_error(exc):
                        continue
                    raise
            else:
                assert last_error is not None
                raise last_error
        effect_after = (
            _capture_action_effect_page_state(page)
            if command.kind in _ACTION_EFFECT_KINDS
            else None
        )
        if command.kind == "snapshot" and isinstance(result_value, dict):
            runtime_state.remember_page_snapshot(
                target_id=tab.target_id,
                generation=int(result_value.get("generation") or 1),
                snapshot_format=str(result_value.get("format") or "snapshot"),
                ref_count=int(result_value.get("ref_count") or 0),
                frame_count=int(result_value.get("frame_count") or 0),
            )
        else:
            runtime_state.remember_page_action(
                target_id=tab.target_id,
                action_kind=command.kind,
            )
        value = {
            "engine": self.family,
            "control_family": plan.control_family,
            "profile": plan.profile.name,
            "tab": _serialize_tab(tab),
            "ref": command.target.ref,
            "selector": resolved_selector,
            "frame_path": _serialize_frame_path(resolved_frame_path),
            "payload": dict(command.payload),
            "result": result_value,
        }
        envelope = _action_result_envelope(
            kind=command.kind,
            tool_ok=True,
            before=effect_before if command.kind in _ACTION_EFFECT_KINDS else None,
            after=effect_after,
            result=result_value,
        )
        if envelope is not None:
            value["action_envelope"] = envelope
        return BrowserActionResult(
            command=command,
            ok=True,
            target_id=tab.target_id,
            value=value,
            message=_action_result_message(command.kind, envelope=envelope),
        )

    def clear_profile(
        self,
        *,
        profile_name: str,
    ) -> None:
        if self.network_capture_controller is not None:
            self.network_capture_controller.clear_profile(profile_name=profile_name)
        self.session_pool.clear_profile(profile_name=profile_name)

    def _runtime_cdp_url(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
    ) -> str | None:
        cached = runtime_state.metadata.get("cdp_base_url")
        if isinstance(cached, str) and cached.strip():
            return cached.strip()
        derived = browser_ref_to_cdp_http_base(runtime_state.browser_ref)
        if derived is not None:
            return derived
        return plan.profile.cdp_url
