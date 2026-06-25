from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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


__all__ = (
    "BrowserControlRequestBody",
    "BrowserPageActionRequestBody",
    "BrowserProfileCreateRequestBody",
    "BrowserProfileUpdateRequestBody",
    "BrowserDefaultProfileRequestBody",
    "BrowserProfileEgressTestRequestBody",
    "BrowserProfilePoolCreateRequestBody",
    "BrowserProfilePoolUpdateRequestBody",
    "BrowserProfileAllocationCreateRequestBody",
    "BrowserProfileAllocationReleaseRequestBody",
    "BrowserProfileAllocationHeartbeatRequestBody",
)
