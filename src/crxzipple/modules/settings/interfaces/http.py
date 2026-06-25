from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.access.application.importer import AccessSettingsBootstrapImporter
from crxzipple.modules.settings.application import import_core_settings_resources
from crxzipple.modules.settings.application.action_policy import SettingsActionName
from crxzipple.modules.settings.application.read_models import (
    audit_by_id as _audit_by_id,
    audit_page as _audit_page,
    audit_payload as _audit_payload,
    kind_payload as _kind_payload,
    overview_payload as _overview_payload,
    resource_by_kind as _resource_by_kind,
    resource_detail_payload as _resource_detail_payload,
)
from crxzipple.modules.settings.interfaces.http_actions import (
    SettingsActionRequest,
    run_settings_action,
)
from crxzipple.modules.settings.interfaces.http_common import (
    require_kind as _require_kind,
    settings_action_service as _settings_action_service,
    settings_query_service as _settings_query_service,
)


router = APIRouter()


@router.get("")
def get_settings_overview(
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    return _overview_payload(_settings_query_service(container))


@router.get("/{kind}")
def list_settings_resources(
    kind: str,
    container: Annotated[AppContainer, Depends(get_container)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    resolved_kind = _require_kind(kind)
    query = _settings_query_service(container)
    if resolved_kind == "audit-logs":
        return _audit_page(query, limit=limit, offset=offset)
    return _kind_payload(query, resolved_kind, limit=limit, offset=offset)


@router.get("/{kind}/{resource_id}")
def get_settings_resource_detail(
    kind: str,
    resource_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    resolved_kind = _require_kind(kind)
    query = _settings_query_service(container)
    if resolved_kind == "audit-logs":
        audit = _audit_by_id(query, resource_id)
        if audit is None:
            raise HTTPException(status_code=404, detail="Settings audit record not found.")
        return _audit_payload(audit)
    resource = _resource_by_kind(query, resolved_kind, resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Settings resource not found.")
    return _resource_detail_payload(query, resource)


@router.post(
    "/{kind}/actions/{action}",
    status_code=status.HTTP_202_ACCEPTED,
)
def run_kind_settings_action(
    kind: str,
    action: SettingsActionName,
    payload: SettingsActionRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    return run_settings_action(
        container,
        action=action,
        kind=kind,
        resource_id=payload.resource_id,
        payload=payload,
    )


@router.post(
    "/{kind}/{resource_id}/actions/{action}",
    status_code=status.HTTP_202_ACCEPTED,
)
def run_resource_settings_action(
    kind: str,
    resource_id: str,
    action: SettingsActionName,
    payload: SettingsActionRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    return run_settings_action(
        container,
        action=action,
        kind=kind,
        resource_id=resource_id,
        payload=payload,
    )


@router.post("/bootstrap-import", status_code=status.HTTP_202_ACCEPTED)
def bootstrap_import_settings(
    payload: SettingsActionRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    if not payload.reason:
        raise HTTPException(status_code=400, detail="Settings bootstrap import requires a reason.")
    core_result = import_core_settings_resources(
        container.require(AppKey.CORE_SETTINGS),
        actions=_settings_action_service(container),
        queries=_settings_query_service(container),
        actor=payload.actor,
        reason=payload.reason,
    )
    access_result = AccessSettingsBootstrapImporter(
        action_service=_settings_action_service(container),
        query_service=_settings_query_service(container),
    ).import_from_legacy_container(
        container,
        actor=payload.actor,
        reason=payload.reason,
    )
    imported_counts = dict(core_result.imported_counts)
    imported_counts["access-assets"] = imported_counts.get(
        "access-assets",
        0,
    ) + int(access_result.imported_counts.get("access-assets", 0))
    return {
        "action": "bootstrap-import",
        "status": "succeeded",
        "result": {
            "core": core_result.to_payload(),
            "access": access_result.to_payload(),
        },
        "imported_counts": imported_counts,
    }
