from __future__ import annotations

from typing import Any

from crxzipple.modules.settings.application.service_common import required_text
from crxzipple.modules.settings.domain.repositories import SettingsActionAuditRepository


JsonObject = dict[str, Any]


def record_settings_action_attempt(
    audit_repository: SettingsActionAuditRepository,
    *,
    action_type: str,
    target_type: str,
    target_id: str | None,
    reason: str,
    actor: str | None = None,
    risk: str | None = None,
    request_metadata: JsonObject | None = None,
):
    return audit_repository.record_attempt(
        action_type=action_type,
        target_type=target_type,
        target_id=target_id,
        reason=required_text(reason, "reason"),
        actor=actor,
        risk=risk,
        request_metadata=request_metadata or {},
    )
