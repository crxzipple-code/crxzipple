from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.access.application.query import AccessControlPlaneQueryProvider
from crxzipple.modules.access.application.settings_integration import (
    AccessSettingsConfigProvider,
)
from crxzipple.modules.access.interfaces.external_consumers import (
    external_access_consumer_bindings,
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


def _provider(container: AppContainer) -> AccessControlPlaneQueryProvider:
    governance_repository = container.require(AppKey.ACCESS_GOVERNANCE_REPOSITORY)
    settings_config_provider = AccessSettingsConfigProvider(
        container.require(AppKey.SETTINGS_QUERY_SERVICE),
        environment=container.require(AppKey.CORE_SETTINGS).environment,
    )
    return AccessControlPlaneQueryProvider(
        governance_repository=governance_repository,
        audit_repository=container.require(AppKey.ACCESS_ACTION_AUDIT_REPOSITORY),
        settings_config_provider=settings_config_provider,
        external_consumer_binding_provider=lambda: external_access_consumer_bindings(container),
    )
