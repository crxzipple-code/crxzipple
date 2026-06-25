from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.daemon_browser_helpers import (
    _is_browser_host_service,
)
from crxzipple.modules.operations.application.read_models.daemon_common import (
    _as_dict,
    _bool,
    _first_text,
    _short,
    _status_label,
    _text,
    _yes_no,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
)


def browser_instance_summary_items(
    instance: dict[str, Any],
    service: dict[str, Any],
) -> tuple[OperationsKeyValueItemModel, ...]:
    service_key = _text(instance.get("service_key"), "")
    if _is_browser_host_service(service_key):
        return _browser_host_summary_items(instance)
    del service
    return ()


def _browser_host_summary_items(
    instance: dict[str, Any],
) -> tuple[OperationsKeyValueItemModel, ...]:
    metadata = _as_dict(instance.get("metadata"))
    manifest_status = _first_text(metadata.get("manifest_status"), "active")
    stale_reason = _text(metadata.get("stale_reason"), "")
    items: list[OperationsKeyValueItemModel] = [
        OperationsKeyValueItemModel("Runtime Kind", "Browser Host"),
        OperationsKeyValueItemModel("Profile", _text(metadata.get("profile_name"))),
        OperationsKeyValueItemModel("Host Runner PID", _text(instance.get("pid"))),
        OperationsKeyValueItemModel("Browser PID", _text(metadata.get("browser_pid"))),
        OperationsKeyValueItemModel("Host Mode", _text(metadata.get("mode"))),
        OperationsKeyValueItemModel(
            "Adopted",
            _yes_no(_bool(metadata.get("adopted"))),
            "success" if _bool(metadata.get("adopted")) else "neutral",
        ),
        OperationsKeyValueItemModel(
            "Manifest",
            _status_label(manifest_status),
            _browser_manifest_tone(manifest_status),
        ),
        OperationsKeyValueItemModel(
            "CDP Endpoint",
            _first_text(
                instance.get("endpoint"),
                metadata.get("server_url"),
                metadata.get("cdp_url"),
            ),
        ),
        OperationsKeyValueItemModel("CDP Port", _text(metadata.get("cdp_port"))),
        OperationsKeyValueItemModel(
            "Profile Directory",
            _text(metadata.get("profile_directory")),
        ),
        OperationsKeyValueItemModel("Proxy Mode", _text(metadata.get("proxy_mode"), "none")),
        OperationsKeyValueItemModel(
            "Launch Fingerprint",
            _short(metadata.get("launch_fingerprint"), 40),
        ),
    ]
    user_data_dir = _text(metadata.get("user_data_dir"), "")
    if user_data_dir and user_data_dir != "-":
        items.append(
            OperationsKeyValueItemModel("User Data Dir", _short(user_data_dir, 140))
        )
    if stale_reason and stale_reason != "-":
        items.append(
            OperationsKeyValueItemModel(
                "Stale Reason",
                _short(stale_reason, 140),
                "danger",
            )
        )
    return tuple(items)


def _browser_manifest_tone(value: Any) -> str:
    normalized = _text(value, "").lower()
    if normalized in {"stale", "conflict", "failed", "error"}:
        return "danger"
    if normalized in {"unknown", "discovering", "starting", "degraded"}:
        return "warning"
    if normalized in {"active", "adopted", "ready", "launched"}:
        return "success"
    return "neutral"
