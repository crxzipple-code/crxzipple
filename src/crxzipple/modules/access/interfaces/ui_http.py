from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from crxzipple.bootstrap import AppContainer
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.access.application.query import AccessControlPlaneQueryProvider
from crxzipple.modules.access.application.settings_integration import (
    AccessSettingsConfigProvider,
)


router = APIRouter()


@router.get("")
def get_access_overview(
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    return _provider(container).overview().to_payload()


@router.get("/assets")
def list_access_assets(
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    return _provider(container).assets().to_payload()


@router.get("/assets/{asset_id}")
def get_access_asset_detail(
    asset_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    result = _provider(container).asset_detail(asset_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Access asset not found.")
    return result.to_payload()


@router.get("/consumers")
def list_access_consumers(
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    return _provider(container).consumers().to_payload()


@router.get("/audits")
def list_access_audits(
    container: Annotated[AppContainer, Depends(get_container)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, object]:
    return _provider(container).audits(limit=limit, offset=offset).to_payload()


def _provider(container: AppContainer) -> AccessControlPlaneQueryProvider:
    governance_repository = container.access_governance_repository
    settings_config_provider = AccessSettingsConfigProvider(
        getattr(container, "settings_query_service", None),
        environment=getattr(getattr(container, "settings", None), "environment", None),
    )
    if governance_repository is None:
        return AccessControlPlaneQueryProvider(
            governance_repository=None,
            audit_repository=None,
            settings_config_provider=settings_config_provider,
        )
    return AccessControlPlaneQueryProvider(
        governance_repository=governance_repository,
        audit_repository=container.access_action_audit_repository,
        settings_config_provider=settings_config_provider,
    )
