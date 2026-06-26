from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from crxzipple.interfaces.runtime_container import AppContainer
from crxzipple.modules.settings.application.action_policy import SettingsActionName
from crxzipple.modules.settings.domain import (
    SettingsAlreadyExistsError,
    SettingsConflictError,
    SettingsError,
    SettingsNotFoundError,
)
from crxzipple.modules.settings.interfaces.http_action_execution import (
    execute_settings_action,
)
from crxzipple.modules.settings.interfaces.http_action_models import SettingsActionRequest
from crxzipple.modules.settings.interfaces.http_common import (
    require_kind,
    settings_action_service,
    settings_query_service,
)


def run_settings_action(
    container: AppContainer,
    *,
    action: SettingsActionName,
    kind: str,
    resource_id: str | None,
    payload: SettingsActionRequest,
) -> dict[str, Any]:
    resolved_kind = require_kind(kind)
    query = settings_query_service(container)
    actions = settings_action_service(container)
    try:
        return execute_settings_action(
            query=query,
            actions=actions,
            action=action,
            kind=resolved_kind,
            resource_id=resource_id,
            payload=payload,
        )
    except HTTPException:
        raise
    except SettingsNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SettingsAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SettingsConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (SettingsError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
