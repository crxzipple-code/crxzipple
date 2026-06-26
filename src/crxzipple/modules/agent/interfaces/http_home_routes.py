from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.runtime_container import AppContainer
from crxzipple.modules.agent.domain.exceptions import AgentError
from crxzipple.modules.agent.interfaces.http_models import (
    AgentHomeConfigResponse,
    AgentHomeMigrationResponse,
    AgentHomeSnapshotResponse,
    agent_home_config_response,
    agent_home_migration_response,
    agent_home_snapshot_response,
)
from crxzipple.modules.agent.interfaces.http_requests import (
    ExportAgentHomeRequest,
    MigrateAgentHomeRequest,
    SyncAgentHomeRequest,
    UpdateAgentHomeFilesRequest,
    export_agent_home_input,
    migrate_agent_home_input,
    sync_agent_home_input,
    update_agent_home_files_input,
)
from crxzipple.modules.agent.interfaces.http_services import (
    agent_service,
    raise_agent_http_error,
)


router = APIRouter()


@router.post("/{agent_id}/migrate-home", response_model=AgentHomeMigrationResponse)
def migrate_home(
    agent_id: str,
    payload: MigrateAgentHomeRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AgentHomeMigrationResponse:
    try:
        result = agent_service(container).migrate_profile_home(
            migrate_agent_home_input(agent_id, payload),
        )
    except AgentError as exc:
        raise_agent_http_error(exc)
    return agent_home_migration_response(result)


@router.get("/{agent_id}/home", response_model=AgentHomeSnapshotResponse)
def get_home(
    agent_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AgentHomeSnapshotResponse:
    try:
        snapshot = agent_service(container).inspect_profile_home(agent_id)
    except AgentError as exc:
        raise_agent_http_error(exc)
    return agent_home_snapshot_response(snapshot)


@router.put("/{agent_id}/home", response_model=AgentHomeSnapshotResponse)
def update_home(
    agent_id: str,
    payload: UpdateAgentHomeFilesRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AgentHomeSnapshotResponse:
    try:
        snapshot = agent_service(container).update_profile_home_files(
            update_agent_home_files_input(agent_id, payload),
        )
    except AgentError as exc:
        raise_agent_http_error(exc)
    return agent_home_snapshot_response(snapshot)


@router.post("/{agent_id}/sync-home", response_model=AgentHomeConfigResponse)
def sync_home(
    agent_id: str,
    payload: SyncAgentHomeRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AgentHomeConfigResponse:
    try:
        result = agent_service(container).sync_profile_home(
            sync_agent_home_input(agent_id, payload),
        )
    except AgentError as exc:
        raise_agent_http_error(exc)
    return agent_home_config_response(result)


@router.post("/{agent_id}/export-home", response_model=AgentHomeConfigResponse)
def export_home(
    agent_id: str,
    payload: ExportAgentHomeRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AgentHomeConfigResponse:
    try:
        result = agent_service(container).export_profile_home(
            export_agent_home_input(agent_id, payload),
        )
    except AgentError as exc:
        raise_agent_http_error(exc)
    return agent_home_config_response(result)


__all__ = ["router"]
