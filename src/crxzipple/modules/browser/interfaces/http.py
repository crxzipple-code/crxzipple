from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.modules.browser.domain import BrowserValidationError

from .http_profile_egress import _record_profile_egress, _test_profile_egress
from .http_profile_helpers import (
    _allocations_payload,
    _default_profile,
    _execute_profile_control,
    _pools_payload,
    _profiles_payload,
    _system_config,
)
from .http_request_models import (
    BrowserControlRequestBody,
    BrowserDefaultProfileRequestBody,
    BrowserPageActionRequestBody,
    BrowserProfileAllocationCreateRequestBody,
    BrowserProfileAllocationHeartbeatRequestBody,
    BrowserProfileAllocationReleaseRequestBody,
    BrowserProfileCreateRequestBody,
    BrowserProfileEgressTestRequestBody,
    BrowserProfilePoolCreateRequestBody,
    BrowserProfilePoolUpdateRequestBody,
    BrowserProfileUpdateRequestBody,
)
from .http_update_payloads import _pool_update_kwargs, _profile_update_kwargs
from .profile_payloads import (
    build_allocation_entry,
    build_pool_entry,
    build_profile_diagnostics_payload,
)
from .requests import BrowserControlRequest, BrowserPageActionRequest


router = APIRouter()


@router.get("/pools")
def list_pools(
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    return _pools_payload(container)


@router.post("/pools")
def create_pool(
    payload: BrowserProfilePoolCreateRequestBody,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        container.require(AppKey.BROWSER_PROFILE_POOL_SERVICE).create_pool(
            pool_id=payload.pool_id,
            display_name=payload.display_name,
            enabled=payload.enabled,
            profile_names=tuple(payload.profile_names),
            target_hosts=tuple(payload.target_hosts),
            selection_strategy=payload.selection_strategy,
            max_concurrency_per_profile=payload.max_concurrency_per_profile,
            max_concurrency_total=payload.max_concurrency_total,
            allocation_ttl_seconds=payload.allocation_ttl_seconds,
            cooldown_seconds=payload.cooldown_seconds,
            failure_cooldown_seconds=payload.failure_cooldown_seconds,
            allow_attach_only=payload.allow_attach_only,
            close_targets_on_release=payload.close_targets_on_release,
            close_targets_on_expire=payload.close_targets_on_expire,
            health_policy=payload.health_policy,
            metadata=payload.metadata,
        )
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _pools_payload(container)


@router.get("/pools/{pool_id}")
def get_pool(
    pool_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        pool = container.require(AppKey.BROWSER_PROFILE_POOL_SERVICE).get_pool(
            pool_id=pool_id,
        )
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "pool": build_pool_entry(
            container,
            pool=pool,
            system_config=_system_config(container),
        ),
    }


@router.put("/pools/{pool_id}")
def update_pool(
    pool_id: str,
    payload: BrowserProfilePoolUpdateRequestBody,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        container.require(AppKey.BROWSER_PROFILE_POOL_SERVICE).update_pool(
            pool_id=pool_id,
            **_pool_update_kwargs(payload),
        )
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _pools_payload(container)


@router.post("/pools/{pool_id}/enable")
def enable_pool(
    pool_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        container.require(AppKey.BROWSER_PROFILE_POOL_SERVICE).enable_pool(
            pool_id=pool_id,
        )
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _pools_payload(container)


@router.post("/pools/{pool_id}/disable")
def disable_pool(
    pool_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        container.require(AppKey.BROWSER_PROFILE_POOL_SERVICE).disable_pool(
            pool_id=pool_id,
        )
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _pools_payload(container)


@router.delete("/pools/{pool_id}")
def delete_pool(
    pool_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        container.require(AppKey.BROWSER_PROFILE_POOL_SERVICE).delete_pool(
            pool_id=pool_id,
        )
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _pools_payload(container)


@router.post("/pools/{pool_id}/drain")
def drain_pool(
    pool_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        drained = container.require(
            AppKey.BROWSER_PROFILE_ALLOCATOR_SERVICE
        ).drain_pool(
            pool_id=pool_id,
        )
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "pool_id": pool_id.strip().lower(),
        "released": len(drained),
        "allocations": [build_allocation_entry(allocation) for allocation in drained],
    }


@router.get("/allocations")
def list_allocations(
    container: Annotated[AppContainer, Depends(get_container)],
    status: str | None = None,
    pool_id: str | None = None,
    profile_name: str | None = None,
    active_only: bool = False,
) -> dict[str, object]:
    return _allocations_payload(
        container,
        status=status,
        pool_id=pool_id,
        profile_name=profile_name,
        active_only=active_only,
    )


@router.post("/allocations")
def allocate_profile(
    payload: BrowserProfileAllocationCreateRequestBody,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        allocation = container.require(
            AppKey.BROWSER_PROFILE_ALLOCATOR_SERVICE
        ).allocate(
            pool_id=payload.pool_id,
            profile_name=payload.profile_name,
            consumer_kind=payload.consumer_kind,
            consumer_id=payload.consumer_id,
            target_host=payload.target_host,
        )
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"allocation": build_allocation_entry(allocation)}


@router.get("/allocations/{allocation_id}")
def get_allocation(
    allocation_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        allocation = container.require(
            AppKey.BROWSER_PROFILE_ALLOCATOR_SERVICE
        ).get_allocation(
            allocation_id=allocation_id,
        )
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"allocation": build_allocation_entry(allocation)}


@router.post("/allocations/{allocation_id}/release")
def release_allocation(
    allocation_id: str,
    payload: BrowserProfileAllocationReleaseRequestBody,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        allocation = container.require(
            AppKey.BROWSER_PROFILE_ALLOCATOR_SERVICE
        ).release_allocation(
            allocation_id=allocation_id,
            reason=payload.reason,
            failed=payload.failed,
            recycle_targets=payload.close_owned_targets,
        )
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"allocation": build_allocation_entry(allocation)}


@router.post("/allocations/{allocation_id}/heartbeat")
def heartbeat_allocation(
    allocation_id: str,
    payload: BrowserProfileAllocationHeartbeatRequestBody,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        allocation = container.require(
            AppKey.BROWSER_PROFILE_ALLOCATOR_SERVICE
        ).heartbeat_allocation(
            allocation_id=allocation_id,
            ttl_seconds=payload.ttl_seconds,
        )
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"allocation": build_allocation_entry(allocation)}


@router.post("/allocations/{allocation_id}/reconcile")
def reconcile_allocation(
    allocation_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        allocation = container.require(
            AppKey.BROWSER_PROFILE_ALLOCATOR_SERVICE
        ).reconcile_allocation(
            allocation_id=allocation_id,
        )
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"allocation": build_allocation_entry(allocation)}


@router.post("/allocations/reconcile")
def reconcile_allocations(
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        allocations = container.require(
            AppKey.BROWSER_PROFILE_ALLOCATOR_SERVICE
        ).reconcile_allocations()
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "allocations": [
            build_allocation_entry(allocation) for allocation in allocations
        ],
        "reconciled": len(allocations),
    }


@router.get("/profiles")
def list_profiles(
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    return _profiles_payload(container)


@router.get("/profiles/{profile_name}/diagnostics")
def diagnose_profile(
    profile_name: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        return build_profile_diagnostics_payload(container, profile_name=profile_name)
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/profiles")
def create_profile(
    payload: BrowserProfileCreateRequestBody,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        system_config = container.require(
            AppKey.BROWSER_PROFILE_ADMIN_SERVICE
        ).create_profile(
            name=payload.name,
            driver=payload.driver,
            enabled=payload.enabled,
            cdp_url=payload.cdp_url,
            cdp_port=payload.cdp_port,
            user_data_dir=payload.user_data_dir,
            profile_directory=payload.profile_directory,
            attach_only=payload.attach_only,
            autostart=payload.autostart,
            proxy_mode=payload.proxy_mode,
            proxy_server=payload.proxy_server,
            proxy_bypass_list=tuple(payload.proxy_bypass_list),
            proxy_binding_id=payload.proxy_binding_id,
            proxy_credential_kind=payload.proxy_credential_kind,
            close_targets_on_release=payload.close_targets_on_release,
            close_targets_on_expire=payload.close_targets_on_expire,
            set_as_default=payload.set_as_default,
        )
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _profiles_payload(container, system_config=system_config)


@router.post("/profiles/default")
def set_default_profile(
    payload: BrowserDefaultProfileRequestBody,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        system_config = container.require(
            AppKey.BROWSER_PROFILE_ADMIN_SERVICE
        ).set_default_profile(
            profile_name=payload.profile_name,
        )
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _profiles_payload(container, system_config=system_config)


@router.put("/profiles/{profile_name}")
def update_profile(
    profile_name: str,
    payload: BrowserProfileUpdateRequestBody,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        system_config = container.require(
            AppKey.BROWSER_PROFILE_ADMIN_SERVICE
        ).update_profile(
            profile_name=profile_name,
            **_profile_update_kwargs(payload),
        )
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _profiles_payload(container, system_config=system_config)


@router.post("/profiles/{profile_name}/enable")
def enable_profile(
    profile_name: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        system_config = container.require(
            AppKey.BROWSER_PROFILE_ADMIN_SERVICE
        ).enable_profile(
            profile_name=profile_name,
        )
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _profiles_payload(container, system_config=system_config)


@router.post("/profiles/{profile_name}/disable")
def disable_profile(
    profile_name: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        system_config = container.require(
            AppKey.BROWSER_PROFILE_ADMIN_SERVICE
        ).disable_profile(
            profile_name=profile_name,
        )
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _profiles_payload(container, system_config=system_config)


@router.post("/profiles/{profile_name}/start")
def start_profile(
    profile_name: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    try:
        return _execute_profile_control(
            container, profile_name=profile_name, kind="start"
        )
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/profiles/{profile_name}/stop")
def stop_profile(
    profile_name: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    try:
        return _execute_profile_control(
            container, profile_name=profile_name, kind="stop"
        )
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/profiles/{profile_name}/restart")
def restart_profile(
    profile_name: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    try:
        stopped = _execute_profile_control(
            container, profile_name=profile_name, kind="stop"
        )
        started = _execute_profile_control(
            container, profile_name=profile_name, kind="start"
        )
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "profile": profile_name.strip().lower(),
        "stopped": stopped,
        "started": started,
    }


@router.post("/profiles/{profile_name}/test-cdp")
def test_profile_cdp(
    profile_name: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        return build_profile_diagnostics_payload(container, profile_name=profile_name)
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/profiles/{profile_name}/test-egress")
def test_profile_egress(
    profile_name: str,
    payload: BrowserProfileEgressTestRequestBody,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    try:
        response = _test_profile_egress(
            container,
            profile_name=profile_name,
            url=payload.url,
            timeout_s=payload.timeout_s,
        )
        _record_profile_egress(
            container,
            profile_name=profile_name,
            response=response,
        )
        return response
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/profiles/{profile_name}")
def delete_profile(
    profile_name: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        system_config = container.require(
            AppKey.BROWSER_PROFILE_ADMIN_SERVICE
        ).delete_profile(
            profile_name=profile_name,
        )
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _profiles_payload(container, system_config=system_config)


@router.post("/control")
def execute_control(
    payload: BrowserControlRequestBody,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    try:
        result = container.require(AppKey.BROWSER_FACADE).execute(
            BrowserControlRequest(
                profile_name=payload.profile_name or _default_profile(container),
                kind=payload.kind,
                target_id=payload.target_id,
                payload=payload.payload,
                timeout_ms=payload.timeout_ms,
            ),
        )
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return container.require(AppKey.BROWSER_RESULT_SERIALIZER).serialize(result)


@router.post("/actions")
def execute_page_action(
    payload: BrowserPageActionRequestBody,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    try:
        result = container.require(AppKey.BROWSER_FACADE).execute(
            BrowserPageActionRequest(
                profile_name=payload.profile_name or _default_profile(container),
                kind=payload.kind,
                target_id=payload.target_id,
                ref=payload.ref,
                selector=payload.selector,
                payload=payload.payload,
                timeout_ms=payload.timeout_ms,
            ),
        )
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return container.require(AppKey.BROWSER_RESULT_SERIALIZER).serialize(result)
