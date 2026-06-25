from __future__ import annotations

from typing import Any

from .observation_interaction_payloads import (
    _form_payload,
    _observation_guidance,
    _overlay_payload,
)
from .observation_page_payloads import (
    _evidence_summary,
    _observation_message,
    _page_payload,
    _snapshot_frames,
    _snapshot_refs,
    _tabs_payload,
)
from .observation_runtime_payloads import (
    _code_payload,
    _network_payload,
    _runtime_payload,
)
from .observation_values import (
    _optional_error,
    _result_payload,
    _safe_int,
    _successful_result_payload,
)


def _build_observation_payload(
    *,
    profile_name: str,
    target_id: str | None,
    tabs: dict[str, Any] | None,
    snapshot: dict[str, Any],
    console: dict[str, Any] | None,
    page_errors: dict[str, Any] | None,
    runtime: dict[str, Any] | None,
    network_runtime: dict[str, Any] | None,
    network_requests: dict[str, Any] | None,
    scripts: dict[str, Any] | None,
    code_search: dict[str, Any] | None,
    request_matches: dict[str, Any] | None,
) -> dict[str, Any]:
    snapshot_result = _result_payload(snapshot)
    page = _page_payload(snapshot, tabs=tabs, target_id=target_id)
    refs = _snapshot_refs(snapshot_result)
    frames = _snapshot_frames(snapshot_result)
    runtime_result = _successful_result_payload(runtime)
    network_runtime_result = _successful_result_payload(network_runtime)
    network_requests_result = _successful_result_payload(network_requests)
    scripts_result = _successful_result_payload(scripts)
    code_search_result = _successful_result_payload(code_search)
    request_matches_result = _successful_result_payload(request_matches)
    runtime_payload = (
        _runtime_payload(
            runtime_result,
            network_runtime=network_runtime_result,
        )
        if runtime_result or network_runtime_result
        else None
    )
    network_payload = _network_payload(
        runtime=network_runtime_result,
        requests=network_requests_result,
    )
    code_payload = _code_payload(
        scripts=scripts_result,
        search=code_search_result,
        request_matches=request_matches_result,
    )
    errors = [
        item
        for item in (
            _optional_error(console),
            _optional_error(page_errors),
            _optional_error(runtime),
            _optional_error(network_runtime),
            _optional_error(network_requests),
            _optional_error(scripts),
            _optional_error(code_search),
            _optional_error(request_matches),
        )
        if item is not None
    ]
    form_payload = _form_payload(refs=refs)
    overlay_payload = _overlay_payload(snapshot_result=snapshot_result, refs=refs)
    return {
        "ok": True,
        "kind": "observe",
        "profile_name": profile_name,
        "target_id": target_id,
        "message": _observation_message(page=page, refs=refs),
        "page": page,
        "tabs": _tabs_payload(tabs),
        "frames": {
            "count": len(frames),
            "items": frames,
        },
        "interaction": {
            "ref_count": _safe_int(snapshot_result.get("ref_count")),
            "frame_count": _safe_int(snapshot_result.get("frame_count")),
            "refs": list(refs),
            "evidence": _evidence_summary(refs),
        },
        "snapshot": snapshot_result,
        "console": _successful_result_payload(console),
        "page_errors": _successful_result_payload(page_errors),
        "runtime": runtime_payload,
        "network": network_payload,
        "code": code_payload,
        "form": form_payload,
        "overlay": overlay_payload,
        "guidance": _observation_guidance(
            refs=refs,
            errors=errors,
            runtime=runtime_payload,
            network=network_payload,
            code=code_payload,
            form=form_payload,
            overlay=overlay_payload,
        ),
        "errors": errors,
    }
