from __future__ import annotations

from crxzipple.modules.workbench.application import view_models as models


def key_value(
    label: str,
    value: object,
    *,
    tone: str = "neutral",
    route: str | None = None,
):
    return models.WorkbenchKeyValueItem(
        label=label,
        value=str(value),
        tone=tone,
        route=route,
        copy_value=str(value),
    )


def tone_for_status(status: str) -> str:
    if status in {"completed", "success", "connected"}:
        return "success"
    if status in {"queued", "waiting"}:
        return "warning"
    if status in {"failed", "cancelled"}:
        return "danger"
    if status in {"running", "accepted"}:
        return "info"
    return "neutral"
