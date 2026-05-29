from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.daemon import DaemonNotFoundError, DaemonValidationError
from .presenters import (
    instance_payload,
    lease_payload,
    service_detail_payload,
    service_set_payload,
    spec_payload,
)


router = APIRouter()


def _raise_http_error(exc: Exception) -> None:
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/services")
def list_services(
    container: Annotated[AppContainer, Depends(get_container)],
    role: str | None = Query(default=None),
    service_group: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    return [
        spec_payload(spec)
        for spec in container.require(AppKey.DAEMON_SERVICE).list_service_specs(
            role=role,
            service_group=service_group,
        )
    ]


@router.get("/service-sets")
def list_service_sets(
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[dict[str, Any]]:
    return [
        service_set_payload(service_set)
        for service_set in container.require(AppKey.DAEMON_SERVICE).list_service_sets()
    ]


@router.get("/instances")
def list_instances(
    container: Annotated[AppContainer, Depends(get_container)],
    service_key: str | None = Query(default=None),
    refresh: bool = Query(default=True),
) -> list[dict[str, Any]]:
    try:
        instances = container.require(AppKey.DAEMON_MANAGER).list_instances(
            service_key=service_key,
            refresh=refresh,
        )
    except (DaemonValidationError, DaemonNotFoundError) as exc:
        _raise_http_error(exc)
    return [instance_payload(instance) for instance in instances]


@router.get("/leases")
def list_leases(
    container: Annotated[AppContainer, Depends(get_container)],
    service_key: str | None = Query(default=None),
    status: str | None = Query(default=None),
    owner_kind: str | None = Query(default=None),
    owner_id: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    leases = container.require(AppKey.DAEMON_SERVICE).list_leases(service_key=service_key)
    if status is not None:
        normalized_status = status.strip().lower()
        leases = tuple(lease for lease in leases if lease.status == normalized_status)
    if owner_kind is not None:
        normalized_owner_kind = owner_kind.strip().lower()
        leases = tuple(lease for lease in leases if lease.owner_kind == normalized_owner_kind)
    if owner_id is not None:
        normalized_owner_id = owner_id.strip().lower()
        leases = tuple(lease for lease in leases if lease.owner_id == normalized_owner_id)
    return [lease_payload(lease) for lease in leases]


@router.get("/services/{service_key}")
def get_service_detail(
    service_key: str,
    container: Annotated[AppContainer, Depends(get_container)],
    refresh: bool = Query(default=True),
) -> dict[str, Any]:
    try:
        spec = container.require(AppKey.DAEMON_SERVICE).get_service_spec(service_key)
        instances = container.require(AppKey.DAEMON_MANAGER).list_instances(
            service_key=service_key,
            refresh=refresh,
        )
        leases = container.require(AppKey.DAEMON_SERVICE).list_leases(service_key=service_key)
    except (DaemonValidationError, DaemonNotFoundError) as exc:
        _raise_http_error(exc)
    return service_detail_payload(
        spec=spec,
        instances=instances,
        leases=leases,
    )


@router.post("/services/{service_key}/ensure")
def ensure_service(
    service_key: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[dict[str, Any]]:
    try:
        instances = container.require(AppKey.DAEMON_MANAGER).ensure_service(service_key)
    except (DaemonValidationError, DaemonNotFoundError) as exc:
        _raise_http_error(exc)
    return [instance_payload(instance) for instance in instances]


@router.post("/services/{service_key}/healthcheck")
def healthcheck_service(
    service_key: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[dict[str, Any]]:
    try:
        instances = container.require(AppKey.DAEMON_MANAGER).healthcheck_service(service_key)
    except (DaemonValidationError, DaemonNotFoundError) as exc:
        _raise_http_error(exc)
    return [instance_payload(instance) for instance in instances]


@router.post("/services/{service_key}/reconcile")
def reconcile_service(
    service_key: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[dict[str, Any]]:
    try:
        instances = container.require(AppKey.DAEMON_MANAGER).reconcile_service(service_key)
    except (DaemonValidationError, DaemonNotFoundError) as exc:
        _raise_http_error(exc)
    return [instance_payload(instance) for instance in instances]


@router.post("/services/{service_key}/stop")
def stop_service(
    service_key: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[dict[str, Any]]:
    try:
        instances = container.require(AppKey.DAEMON_MANAGER).stop_service(service_key)
    except (DaemonValidationError, DaemonNotFoundError) as exc:
        _raise_http_error(exc)
    return [instance_payload(instance) for instance in instances]
