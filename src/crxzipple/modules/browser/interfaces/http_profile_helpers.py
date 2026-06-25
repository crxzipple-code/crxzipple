from __future__ import annotations

from typing import Any

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.modules.browser.domain import BrowserValidationError

from .profile_payloads import (
    build_allocations_payload,
    build_pools_payload,
    build_profiles_payload,
)
from .requests import BrowserControlRequest


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
