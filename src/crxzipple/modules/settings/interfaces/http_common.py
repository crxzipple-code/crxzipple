from __future__ import annotations

from fastapi import HTTPException

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.modules.settings.application import SettingsActionService, SettingsQueryService
from crxzipple.modules.settings.application.action_policy import normalize_kind as _normalize_kind


def settings_query_service(container: AppContainer) -> SettingsQueryService:
    return container.require(AppKey.SETTINGS_QUERY_SERVICE)


def settings_action_service(container: AppContainer) -> SettingsActionService:
    return container.require(AppKey.SETTINGS_ACTION_SERVICE)


def require_kind(kind: str) -> str:
    resolved = _normalize_kind(kind)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Settings resource kind not found.")
    return resolved
