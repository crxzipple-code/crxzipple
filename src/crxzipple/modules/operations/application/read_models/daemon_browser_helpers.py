from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.daemon_common import (
    _bool,
    _status_label,
    _text,
)


def _is_browser_host_service(service_key: str) -> bool:
    return service_key.startswith("host:browser:")


def _browser_host_manifest_label(metadata: dict[str, Any]) -> str:
    manifest_status = _text(metadata.get("manifest_status"), "")
    if manifest_status and manifest_status != "-":
        return _status_label(manifest_status)
    if _bool(metadata.get("adopted")):
        return "Adopted"
    if _text(metadata.get("browser_pid"), "") != "-":
        return "Launched"
    mode = _text(metadata.get("mode"), "")
    return _status_label(mode) if mode and mode != "-" else "-"
