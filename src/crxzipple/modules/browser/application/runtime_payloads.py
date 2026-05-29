from __future__ import annotations

from typing import Any

from crxzipple.modules.browser.domain import BrowserProfileRuntimeState


def browser_runtime_state_applies_to_profile(
    runtime_state: BrowserProfileRuntimeState | None,
    *,
    resolved_profile: Any,
) -> bool:
    if runtime_state is None:
        return False
    if (
        getattr(resolved_profile, "driver", None) == "existing-session"
        and getattr(resolved_profile, "cdp_url", None) is None
        and getattr(resolved_profile, "cdp_port", None) is None
    ):
        return False
    return True


def browser_runtime_status_payload(
    runtime_state: BrowserProfileRuntimeState,
) -> dict[str, Any]:
    page_state = _page_state_payload(runtime_state)
    payload = {
        "attachment_status": runtime_state.attachment_status,
        "browser_ref": runtime_state.browser_ref,
        "running_pid": runtime_state.running_pid,
        "last_target_id": runtime_state.last_target_id,
        "last_error": runtime_state.last_error,
        "host_generation": runtime_state.host_generation(),
        "host_generation_changed": bool(
            runtime_state.metadata.get("host_generation_changed"),
        ),
        "page_state": page_state,
    }
    proxy_egress = runtime_state.metadata.get("proxy_egress")
    if isinstance(proxy_egress, dict):
        payload["proxy_egress"] = dict(proxy_egress)
    if runtime_state.metadata.get("proxy_egress_status"):
        payload["proxy_egress_status"] = runtime_state.metadata.get(
            "proxy_egress_status",
        )
    if runtime_state.metadata.get("proxy_egress_ip"):
        payload["proxy_egress_ip"] = runtime_state.metadata.get("proxy_egress_ip")
    if runtime_state.metadata.get("proxy_egress_checked_at"):
        payload["proxy_egress_checked_at"] = runtime_state.metadata.get(
            "proxy_egress_checked_at",
        )
    return payload


def _page_state_payload(runtime_state: BrowserProfileRuntimeState) -> dict[str, Any]:
    pages = _page_generation_payloads(runtime_state)
    active_target_id = _optional_text(
        runtime_state.metadata.get("active_target_id"),
    ) or runtime_state.last_target_id
    active_page = next(
        (page for page in pages if page["target_id"] == active_target_id),
        None,
    )
    return {
        "active_target_id": active_target_id,
        "page_count": len(pages),
        "active_page": active_page,
        "pages": pages,
    }


def _page_generation_payloads(
    runtime_state: BrowserProfileRuntimeState,
) -> list[dict[str, Any]]:
    raw = runtime_state.metadata.get("page_state_by_target")
    if not isinstance(raw, dict):
        return []

    pages: list[dict[str, Any]] = []
    for target_id, state in sorted(raw.items(), key=lambda item: str(item[0])):
        normalized_target = _optional_text(target_id)
        if normalized_target is None or not isinstance(state, dict):
            continue
        pages.append(
            {
                "target_id": normalized_target,
                "page_generation": _positive_int(state.get("page_generation")),
                "page_generation_reason": _optional_text(
                    state.get("page_generation_reason"),
                ),
                "snapshot_generation": _positive_int(
                    state.get("snapshot_generation"),
                    allow_none=True,
                ),
                "current_ref_generation": _positive_int(
                    state.get("current_ref_generation"),
                    allow_none=True,
                ),
                "last_action_kind": _optional_text(state.get("last_action_kind")),
                "last_snapshot_format": _optional_text(
                    state.get("last_snapshot_format"),
                ),
                "last_snapshot_ref_count": _non_negative_int(
                    state.get("last_snapshot_ref_count"),
                ),
                "last_snapshot_frame_count": _non_negative_int(
                    state.get("last_snapshot_frame_count"),
                ),
                "ref_session_restored": bool(state.get("ref_session_restored")),
            },
        )
    return pages


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _positive_int(value: Any, *, allow_none: bool = False) -> int | None:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return None if allow_none else 0
    if numeric < 1:
        return None if allow_none else 0
    return numeric


def _non_negative_int(value: Any) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return 0
    return max(numeric, 0)
