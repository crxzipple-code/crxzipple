from __future__ import annotations

from crxzipple.modules.browser.domain import BrowserValidationError

from .http_request_models import (
    BrowserProfilePoolUpdateRequestBody,
    BrowserProfileUpdateRequestBody,
)


def _profile_update_kwargs(
    payload: BrowserProfileUpdateRequestBody,
) -> dict[str, object]:
    updates: dict[str, object] = {}
    provided_fields = payload.model_fields_set

    if (
        payload.clear_cdp_url
        and "cdp_url" in provided_fields
        and payload.cdp_url is not None
    ):
        raise BrowserValidationError(
            "cdp_url cannot be provided together with clear_cdp_url."
        )
    if (
        payload.clear_cdp_port
        and "cdp_port" in provided_fields
        and payload.cdp_port is not None
    ):
        raise BrowserValidationError(
            "cdp_port cannot be provided together with clear_cdp_port."
        )
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
    if (
        "proxy_credential_kind" in provided_fields
        and payload.proxy_credential_kind is not None
    ):
        updates["proxy_credential_kind"] = payload.proxy_credential_kind
    if (
        "close_targets_on_release" in provided_fields
        and payload.close_targets_on_release is not None
    ):
        updates["close_targets_on_release"] = payload.close_targets_on_release
    if (
        "close_targets_on_expire" in provided_fields
        and payload.close_targets_on_expire is not None
    ):
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
    if (
        "selection_strategy" in provided_fields
        and payload.selection_strategy is not None
    ):
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
    if (
        "close_targets_on_release" in provided_fields
        and payload.close_targets_on_release is not None
    ):
        updates["close_targets_on_release"] = payload.close_targets_on_release
    if (
        "close_targets_on_expire" in provided_fields
        and payload.close_targets_on_expire is not None
    ):
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
