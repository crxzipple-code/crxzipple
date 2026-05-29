from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import requests

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.browser.domain import (
    BrowserValidationError,
)
from crxzipple.modules.browser.infrastructure import BrowserLocalProxyAdapter
from crxzipple.shared.access import AccessConsumerRef

from .profile_payloads import build_allocation_entry
from .profile_payloads import build_allocations_payload
from .profile_payloads import build_pool_entry
from .profile_payloads import build_pools_payload
from .profile_payloads import build_profile_diagnostics_payload
from .profile_payloads import build_profiles_payload
from .requests import BrowserControlRequest, BrowserPageActionRequest


router = APIRouter()


class BrowserControlRequestBody(BaseModel):
    profile_name: str | None = None
    kind: str = Field(min_length=1)
    target_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    timeout_ms: int | None = Field(default=None, ge=1)


class BrowserPageActionRequestBody(BaseModel):
    profile_name: str | None = None
    kind: str = Field(min_length=1)
    target_id: str | None = None
    ref: str | None = None
    selector: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    timeout_ms: int | None = Field(default=None, ge=1)


class BrowserProfileCreateRequestBody(BaseModel):
    name: str = Field(min_length=1)
    driver: str = Field(default="managed", min_length=1)
    enabled: bool = True
    cdp_url: str | None = None
    cdp_port: int | None = Field(default=None, ge=1)
    user_data_dir: str | None = None
    profile_directory: str | None = None
    attach_only: bool = False
    autostart: bool = True
    proxy_mode: str = "none"
    proxy_server: str | None = None
    proxy_bypass_list: list[str] = Field(default_factory=list)
    proxy_binding_id: str | None = None
    proxy_credential_kind: str = "basic"
    close_targets_on_release: bool = True
    close_targets_on_expire: bool = True
    set_as_default: bool = False


class BrowserProfileUpdateRequestBody(BaseModel):
    driver: str | None = Field(default=None, min_length=1)
    enabled: bool | None = None
    cdp_url: str | None = None
    cdp_port: int | None = Field(default=None, ge=1)
    user_data_dir: str | None = None
    profile_directory: str | None = None
    attach_only: bool | None = None
    autostart: bool | None = None
    proxy_mode: str | None = None
    proxy_server: str | None = None
    proxy_bypass_list: list[str] | None = None
    proxy_binding_id: str | None = None
    proxy_credential_kind: str | None = None
    close_targets_on_release: bool | None = None
    close_targets_on_expire: bool | None = None
    clear_cdp_url: bool = False
    clear_cdp_port: bool = False
    clear_user_data_dir: bool = False
    clear_profile_directory: bool = False
    clear_proxy_server: bool = False
    clear_proxy_bypass_list: bool = False
    clear_proxy_binding_id: bool = False
    set_as_default: bool | None = None


class BrowserDefaultProfileRequestBody(BaseModel):
    profile_name: str = Field(min_length=1)


class BrowserProfileEgressTestRequestBody(BaseModel):
    url: str | None = None
    timeout_s: float = Field(default=5.0, ge=0.1, le=60.0)


class BrowserProfilePoolCreateRequestBody(BaseModel):
    pool_id: str = Field(min_length=1)
    display_name: str | None = None
    enabled: bool = True
    profile_names: list[str] = Field(default_factory=list)
    target_hosts: list[str] = Field(default_factory=list)
    selection_strategy: str = "least_busy"
    max_concurrency_per_profile: int = Field(default=1, ge=1)
    max_concurrency_total: int | None = Field(default=None, ge=1)
    allocation_ttl_seconds: int = Field(default=900, ge=1)
    cooldown_seconds: int = Field(default=0, ge=0)
    failure_cooldown_seconds: int = Field(default=300, ge=0)
    allow_attach_only: bool = False
    close_targets_on_release: bool = True
    close_targets_on_expire: bool = True
    health_policy: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BrowserProfilePoolUpdateRequestBody(BaseModel):
    display_name: str | None = None
    enabled: bool | None = None
    profile_names: list[str] | None = None
    target_hosts: list[str] | None = None
    selection_strategy: str | None = None
    max_concurrency_per_profile: int | None = Field(default=None, ge=1)
    max_concurrency_total: int | None = Field(default=None, ge=1)
    allocation_ttl_seconds: int | None = Field(default=None, ge=1)
    cooldown_seconds: int | None = Field(default=None, ge=0)
    failure_cooldown_seconds: int | None = Field(default=None, ge=0)
    allow_attach_only: bool | None = None
    close_targets_on_release: bool | None = None
    close_targets_on_expire: bool | None = None
    health_policy: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    clear_display_name: bool = False
    clear_target_hosts: bool = False
    clear_max_concurrency_total: bool = False
    clear_health_policy: bool = False
    clear_metadata: bool = False


class BrowserProfileAllocationCreateRequestBody(BaseModel):
    pool_id: str | None = None
    profile_name: str | None = None
    consumer_kind: str = Field(default="manual", min_length=1)
    consumer_id: str = Field(min_length=1)
    target_host: str | None = None


class BrowserProfileAllocationReleaseRequestBody(BaseModel):
    reason: str = Field(default="released", min_length=1)
    failed: bool = False
    close_owned_targets: bool | None = None


class BrowserProfileAllocationHeartbeatRequestBody(BaseModel):
    ttl_seconds: int | None = Field(default=None, ge=1)


def _default_profile(container: AppContainer) -> str:
    return container.require(AppKey.BROWSER_SYSTEM_CONFIG_STORE).load().default_profile


def _system_config(container: AppContainer):  # noqa: ANN001
    return container.require(AppKey.BROWSER_SYSTEM_CONFIG_STORE).load()


def _profiles_payload(
    container: AppContainer,
    system_config=None,  # noqa: ANN001
) -> dict[str, object]:
    return build_profiles_payload(container, system_config=system_config)


def _pools_payload(container: AppContainer) -> dict[str, object]:
    return build_pools_payload(container)


def _allocations_payload(
    container: AppContainer,
    *,
    status: str | None = None,
    pool_id: str | None = None,
    profile_name: str | None = None,
    active_only: bool = False,
) -> dict[str, object]:
    return build_allocations_payload(
        container,
        status=status,
        pool_id=pool_id,
        profile_name=profile_name,
        active_only=active_only,
    )


def _execute_profile_control(
    container: AppContainer,
    *,
    profile_name: str,
    kind: str,
) -> dict[str, Any]:
    result = container.require(AppKey.BROWSER_FACADE).execute(
        BrowserControlRequest(
            profile_name=profile_name,
            kind=kind,
        ),
    )
    return container.require(AppKey.BROWSER_RESULT_SERIALIZER).serialize(result)


def _profile_by_name(system_config, profile_name: str):  # noqa: ANN001, ANN201
    normalized = profile_name.strip().lower()
    for profile in system_config.profiles:
        if profile.name == normalized:
            return profile
    raise BrowserValidationError(f"Browser profile '{profile_name}' is not configured.")


def _extract_ipish_value(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        return text[:120] if text else "-"
    if isinstance(payload, dict):
        for key in ("ip", "origin", "query", "remote_addr"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return "-"


def _test_static_proxy_egress(
    *,
    proxy_server: str,
    url: str,
    timeout_s: float,
) -> dict[str, Any]:
    session = requests.Session()
    session.trust_env = False
    try:
        response = session.get(
            url,
            proxies={"http": proxy_server, "https": proxy_server},
            timeout=timeout_s,
        )
        response.raise_for_status()
        return {
            "status": "ready",
            "ip": _extract_ipish_value(response),
            "url": url,
            "http_status": response.status_code,
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "reason": str(exc), "url": url}
    finally:
        session.close()


def _test_profile_egress(
    container: AppContainer,
    *,
    profile_name: str,
    url: str | None,
    timeout_s: float,
) -> dict[str, Any]:
    settings = container.require(AppKey.CORE_SETTINGS)
    test_url = (url or getattr(settings, "browser_proxy_egress_check_url", None) or "").strip()
    if not test_url:
        raise BrowserValidationError(
            "browser_proxy_egress_check_url is required to test browser proxy egress.",
        )
    system_config = _system_config(container)
    profile = _profile_by_name(system_config, profile_name)
    if profile.proxy_mode == "none":
        return {
            "profile": profile.name,
            "attempted": False,
            "status": "not_required",
            "proxy_mode": profile.proxy_mode,
            "url": test_url,
        }
    if profile.proxy_mode == "static":
        if profile.proxy_server is None:
            raise BrowserValidationError("proxy_server is required for static proxy egress test.")
        return {
            "profile": profile.name,
            "attempted": True,
            "proxy_mode": profile.proxy_mode,
            "result": _test_static_proxy_egress(
                proxy_server=profile.proxy_server,
                url=test_url,
                timeout_s=timeout_s,
            ),
        }
    if profile.proxy_mode != "access_binding":
        raise BrowserValidationError(f"Unsupported proxy mode '{profile.proxy_mode}'.")
    if profile.proxy_server is None or profile.proxy_binding_id is None:
        raise BrowserValidationError(
            "proxy_server and proxy_binding_id are required for access_binding proxy egress test.",
        )
    credential = container.require(AppKey.ACCESS_SERVICE).resolve_credential(
        profile.proxy_binding_id,
        expected_kind=profile.proxy_credential_kind,
        consumer=AccessConsumerRef(
            consumer_id=f"browser.profile:{profile.name}:proxy",
            module="browser",
            component="profile_proxy",
            runtime_ref=profile.name,
        ),
    )
    adapter = BrowserLocalProxyAdapter(
        upstream_proxy_url=profile.proxy_server,
        credential=str(credential),
        credential_kind=profile.proxy_credential_kind,
    )
    try:
        adapter.start()
        result = adapter.check_egress(test_url, timeout_s=timeout_s)
    finally:
        adapter.close()
    return {
        "profile": profile.name,
        "attempted": True,
        "proxy_mode": profile.proxy_mode,
        "binding_id": profile.proxy_binding_id,
        "result": result,
    }


def _record_profile_egress(
    container: AppContainer,
    *,
    profile_name: str,
    response: dict[str, Any],
) -> None:
    result = response.get("result")
    if not isinstance(result, dict):
        return
    container.require(AppKey.BROWSER_PROFILE_ADMIN_SERVICE).record_profile_egress(
        profile_name=profile_name,
        result=result,
    )


def _profile_update_kwargs(
    payload: BrowserProfileUpdateRequestBody,
) -> dict[str, object]:
    updates: dict[str, object] = {}
    provided_fields = payload.model_fields_set

    if payload.clear_cdp_url and "cdp_url" in provided_fields and payload.cdp_url is not None:
        raise BrowserValidationError("cdp_url cannot be provided together with clear_cdp_url.")
    if payload.clear_cdp_port and "cdp_port" in provided_fields and payload.cdp_port is not None:
        raise BrowserValidationError("cdp_port cannot be provided together with clear_cdp_port.")
    if (
        payload.clear_user_data_dir
        and "user_data_dir" in provided_fields
        and payload.user_data_dir is not None
    ):
        raise BrowserValidationError(
            "user_data_dir cannot be provided together with clear_user_data_dir.",
        )
    if (
        payload.clear_profile_directory
        and "profile_directory" in provided_fields
        and payload.profile_directory is not None
    ):
        raise BrowserValidationError(
            "profile_directory cannot be provided together with clear_profile_directory.",
        )
    if (
        payload.clear_proxy_server
        and "proxy_server" in provided_fields
        and payload.proxy_server is not None
    ):
        raise BrowserValidationError(
            "proxy_server cannot be provided together with clear_proxy_server.",
        )
    if (
        payload.clear_proxy_bypass_list
        and "proxy_bypass_list" in provided_fields
        and payload.proxy_bypass_list is not None
    ):
        raise BrowserValidationError(
            "proxy_bypass_list cannot be provided together with clear_proxy_bypass_list.",
        )
    if (
        payload.clear_proxy_binding_id
        and "proxy_binding_id" in provided_fields
        and payload.proxy_binding_id is not None
    ):
        raise BrowserValidationError(
            "proxy_binding_id cannot be provided together with clear_proxy_binding_id.",
        )

    if "driver" in provided_fields and payload.driver is not None:
        updates["driver"] = payload.driver
    if "enabled" in provided_fields and payload.enabled is not None:
        updates["enabled"] = payload.enabled
    if "cdp_url" in provided_fields:
        updates["cdp_url"] = payload.cdp_url
    if "cdp_port" in provided_fields:
        updates["cdp_port"] = payload.cdp_port
    if "user_data_dir" in provided_fields:
        updates["user_data_dir"] = payload.user_data_dir
    if "profile_directory" in provided_fields:
        updates["profile_directory"] = payload.profile_directory
    if "attach_only" in provided_fields and payload.attach_only is not None:
        updates["attach_only"] = payload.attach_only
    if "autostart" in provided_fields and payload.autostart is not None:
        updates["autostart"] = payload.autostart
    if "proxy_mode" in provided_fields and payload.proxy_mode is not None:
        updates["proxy_mode"] = payload.proxy_mode
    if "proxy_server" in provided_fields:
        updates["proxy_server"] = payload.proxy_server
    if "proxy_bypass_list" in provided_fields:
        updates["proxy_bypass_list"] = tuple(payload.proxy_bypass_list or ())
    if "proxy_binding_id" in provided_fields:
        updates["proxy_binding_id"] = payload.proxy_binding_id
    if "proxy_credential_kind" in provided_fields and payload.proxy_credential_kind is not None:
        updates["proxy_credential_kind"] = payload.proxy_credential_kind
    if "close_targets_on_release" in provided_fields and payload.close_targets_on_release is not None:
        updates["close_targets_on_release"] = payload.close_targets_on_release
    if "close_targets_on_expire" in provided_fields and payload.close_targets_on_expire is not None:
        updates["close_targets_on_expire"] = payload.close_targets_on_expire
    if "set_as_default" in provided_fields:
        updates["set_as_default"] = payload.set_as_default

    if payload.clear_cdp_url:
        updates["cdp_url"] = None
    if payload.clear_cdp_port:
        updates["cdp_port"] = None
    if payload.clear_user_data_dir:
        updates["user_data_dir"] = None
    if payload.clear_profile_directory:
        updates["profile_directory"] = None
    if payload.clear_proxy_server:
        updates["proxy_server"] = None
    if payload.clear_proxy_bypass_list:
        updates["proxy_bypass_list"] = ()
    if payload.clear_proxy_binding_id:
        updates["proxy_binding_id"] = None

    return updates


def _pool_update_kwargs(
    payload: BrowserProfilePoolUpdateRequestBody,
) -> dict[str, object]:
    updates: dict[str, object] = {}
    provided_fields = payload.model_fields_set

    if (
        payload.clear_display_name
        and "display_name" in provided_fields
        and payload.display_name is not None
    ):
        raise BrowserValidationError(
            "display_name cannot be provided together with clear_display_name.",
        )
    if (
        payload.clear_target_hosts
        and "target_hosts" in provided_fields
        and payload.target_hosts is not None
    ):
        raise BrowserValidationError(
            "target_hosts cannot be provided together with clear_target_hosts.",
        )
    if (
        payload.clear_max_concurrency_total
        and "max_concurrency_total" in provided_fields
        and payload.max_concurrency_total is not None
    ):
        raise BrowserValidationError(
            "max_concurrency_total cannot be provided together with clear_max_concurrency_total.",
        )
    if (
        payload.clear_health_policy
        and "health_policy" in provided_fields
        and payload.health_policy is not None
    ):
        raise BrowserValidationError(
            "health_policy cannot be provided together with clear_health_policy.",
        )
    if (
        payload.clear_metadata
        and "metadata" in provided_fields
        and payload.metadata is not None
    ):
        raise BrowserValidationError(
            "metadata cannot be provided together with clear_metadata.",
        )

    if "display_name" in provided_fields:
        updates["display_name"] = payload.display_name
    if "enabled" in provided_fields and payload.enabled is not None:
        updates["enabled"] = payload.enabled
    if "profile_names" in provided_fields and payload.profile_names is not None:
        updates["profile_names"] = tuple(payload.profile_names)
    if "target_hosts" in provided_fields and payload.target_hosts is not None:
        updates["target_hosts"] = tuple(payload.target_hosts)
    if "selection_strategy" in provided_fields and payload.selection_strategy is not None:
        updates["selection_strategy"] = payload.selection_strategy
    if (
        "max_concurrency_per_profile" in provided_fields
        and payload.max_concurrency_per_profile is not None
    ):
        updates["max_concurrency_per_profile"] = payload.max_concurrency_per_profile
    if "max_concurrency_total" in provided_fields:
        updates["max_concurrency_total"] = payload.max_concurrency_total
    if (
        "allocation_ttl_seconds" in provided_fields
        and payload.allocation_ttl_seconds is not None
    ):
        updates["allocation_ttl_seconds"] = payload.allocation_ttl_seconds
    if "cooldown_seconds" in provided_fields and payload.cooldown_seconds is not None:
        updates["cooldown_seconds"] = payload.cooldown_seconds
    if (
        "failure_cooldown_seconds" in provided_fields
        and payload.failure_cooldown_seconds is not None
    ):
        updates["failure_cooldown_seconds"] = payload.failure_cooldown_seconds
    if "allow_attach_only" in provided_fields and payload.allow_attach_only is not None:
        updates["allow_attach_only"] = payload.allow_attach_only
    if "close_targets_on_release" in provided_fields and payload.close_targets_on_release is not None:
        updates["close_targets_on_release"] = payload.close_targets_on_release
    if "close_targets_on_expire" in provided_fields and payload.close_targets_on_expire is not None:
        updates["close_targets_on_expire"] = payload.close_targets_on_expire
    if "health_policy" in provided_fields and payload.health_policy is not None:
        updates["health_policy"] = payload.health_policy
    if "metadata" in provided_fields and payload.metadata is not None:
        updates["metadata"] = payload.metadata

    if payload.clear_display_name:
        updates["display_name"] = None
    if payload.clear_target_hosts:
        updates["target_hosts"] = ()
    if payload.clear_max_concurrency_total:
        updates["max_concurrency_total"] = None
    if payload.clear_health_policy:
        updates["health_policy"] = {}
    if payload.clear_metadata:
        updates["metadata"] = {}

    return updates


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
        drained = container.require(AppKey.BROWSER_PROFILE_ALLOCATOR_SERVICE).drain_pool(
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
        allocation = container.require(AppKey.BROWSER_PROFILE_ALLOCATOR_SERVICE).allocate(
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
        allocation = container.require(AppKey.BROWSER_PROFILE_ALLOCATOR_SERVICE).get_allocation(
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
        allocation = container.require(AppKey.BROWSER_PROFILE_ALLOCATOR_SERVICE).release_allocation(
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
        allocation = container.require(AppKey.BROWSER_PROFILE_ALLOCATOR_SERVICE).heartbeat_allocation(
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
        allocation = container.require(AppKey.BROWSER_PROFILE_ALLOCATOR_SERVICE).reconcile_allocation(
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
        allocations = container.require(AppKey.BROWSER_PROFILE_ALLOCATOR_SERVICE).reconcile_allocations()
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "allocations": [build_allocation_entry(allocation) for allocation in allocations],
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
        system_config = container.require(AppKey.BROWSER_PROFILE_ADMIN_SERVICE).create_profile(
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
        system_config = container.require(AppKey.BROWSER_PROFILE_ADMIN_SERVICE).set_default_profile(
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
        system_config = container.require(AppKey.BROWSER_PROFILE_ADMIN_SERVICE).update_profile(
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
        system_config = container.require(AppKey.BROWSER_PROFILE_ADMIN_SERVICE).enable_profile(
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
        system_config = container.require(AppKey.BROWSER_PROFILE_ADMIN_SERVICE).disable_profile(
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
        return _execute_profile_control(container, profile_name=profile_name, kind="start")
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/profiles/{profile_name}/stop")
def stop_profile(
    profile_name: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    try:
        return _execute_profile_control(container, profile_name=profile_name, kind="stop")
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/profiles/{profile_name}/restart")
def restart_profile(
    profile_name: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    try:
        stopped = _execute_profile_control(container, profile_name=profile_name, kind="stop")
        started = _execute_profile_control(container, profile_name=profile_name, kind="start")
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"profile": profile_name.strip().lower(), "stopped": stopped, "started": started}


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
        system_config = container.require(AppKey.BROWSER_PROFILE_ADMIN_SERVICE).delete_profile(
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
