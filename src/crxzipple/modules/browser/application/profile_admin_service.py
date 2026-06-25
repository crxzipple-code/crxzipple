from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from crxzipple.modules.browser.domain import (
    BrowserProfileConfig,
    BrowserProfileRuntimeState,
    BrowserSystemConfig,
    BrowserValidationError,
)

from .events import (
    BROWSER_PROFILE_CREATED_EVENT,
    BROWSER_PROFILE_DELETED_EVENT,
    BROWSER_PROFILE_DISABLED_EVENT,
    BROWSER_PROFILE_ENABLED_EVENT,
    BROWSER_PROFILE_UPDATED_EVENT,
    BrowserEventEmitter,
    emit_browser_event,
)
from .ports import (
    BrowserProfileAllocationStore,
    BrowserProfileHostServiceSync,
    BrowserRefStore,
    BrowserRuntimeStateStore,
    BrowserSystemConfigStore,
)
from .profile_lifecycle_common import (
    UNSET as _UNSET,
    changed_profile_fields as _changed_profile_fields,
    profile_event_payload as _profile_event_payload,
    sanitize_profile_egress_result as _sanitize_profile_egress_result,
    utc_now as _utc_now,
)

@dataclass(slots=True)
class BrowserProfileAdminService:
    system_config_store: BrowserSystemConfigStore
    runtime_state_store: BrowserRuntimeStateStore
    ref_store: BrowserRefStore
    allocation_store: BrowserProfileAllocationStore | None = None
    host_service_sync: BrowserProfileHostServiceSync | None = None
    event_emitter: BrowserEventEmitter | None = None

    def list_profiles(self) -> BrowserSystemConfig:
        return self.system_config_store.load()

    def create_profile(
        self,
        *,
        name: str,
        driver: str = "managed",
        enabled: bool = True,
        cdp_url: str | None = None,
        cdp_port: int | None = None,
        user_data_dir: str | None = None,
        profile_directory: str | None = None,
        attach_only: bool = False,
        autostart: bool = True,
        proxy_mode: str = "none",
        proxy_server: str | None = None,
        proxy_bypass_list: tuple[str, ...] = (),
        proxy_binding_id: str | None = None,
        proxy_credential_kind: str = "basic",
        close_targets_on_release: bool = True,
        close_targets_on_expire: bool = True,
        set_as_default: bool = False,
    ) -> BrowserSystemConfig:
        system = self.system_config_store.load()
        normalized_name = name.strip().lower()
        if any(profile.name == normalized_name for profile in system.profiles):
            raise BrowserValidationError(
                f"Browser profile '{name}' already exists.",
            )

        profile = BrowserProfileConfig(
            name=name,
            driver=driver,  # type: ignore[arg-type]
            enabled=enabled,
            cdp_url=cdp_url,
            cdp_port=cdp_port,
            user_data_dir=user_data_dir,
            profile_directory=profile_directory,
            attach_only=attach_only,
            autostart=autostart,
            proxy_mode=proxy_mode,  # type: ignore[arg-type]
            proxy_server=proxy_server,
            proxy_bypass_list=proxy_bypass_list,
            proxy_binding_id=proxy_binding_id,
            proxy_credential_kind=proxy_credential_kind,  # type: ignore[arg-type]
            close_targets_on_release=close_targets_on_release,
            close_targets_on_expire=close_targets_on_expire,
        )
        updated = self._rebuild_system(
            system,
            profiles=system.profiles + (profile,),
            default_profile=profile.name if set_as_default else system.default_profile,
        )
        saved = self.system_config_store.save(updated)
        self._sync_profile_host_service(system=saved, profile=profile)
        self._emit_profile_event(
            BROWSER_PROFILE_CREATED_EVENT,
            profile=profile,
            system=saved,
            status="created",
        )
        return saved

    def update_profile(
        self,
        *,
        profile_name: str,
        driver: str | object = _UNSET,
        enabled: bool | object = _UNSET,
        cdp_url: str | None | object = _UNSET,
        cdp_port: int | None | object = _UNSET,
        user_data_dir: str | None | object = _UNSET,
        profile_directory: str | None | object = _UNSET,
        attach_only: bool | object = _UNSET,
        autostart: bool | object = _UNSET,
        proxy_mode: str | object = _UNSET,
        proxy_server: str | None | object = _UNSET,
        proxy_bypass_list: tuple[str, ...] | object = _UNSET,
        proxy_binding_id: str | None | object = _UNSET,
        proxy_credential_kind: str | object = _UNSET,
        close_targets_on_release: bool | object = _UNSET,
        close_targets_on_expire: bool | object = _UNSET,
        set_as_default: bool | None = None,
    ) -> BrowserSystemConfig:
        system = self.system_config_store.load()
        current = self._get_profile(system, profile_name)
        requested_enabled = current.enabled if enabled is _UNSET else bool(enabled)
        if not requested_enabled:
            self._raise_if_profile_runtime_active(current.name, action="disable")
            self._raise_if_profile_allocation_active(current.name, action="disable")

        updated_profile = BrowserProfileConfig(
            name=current.name,
            driver=current.driver if driver is _UNSET else str(driver),
            enabled=requested_enabled,
            cdp_url=current.cdp_url if cdp_url is _UNSET else cdp_url,
            cdp_port=current.cdp_port if cdp_port is _UNSET else cdp_port,
            user_data_dir=(
                current.user_data_dir if user_data_dir is _UNSET else user_data_dir
            ),
            profile_directory=(
                current.profile_directory
                if profile_directory is _UNSET
                else profile_directory
            ),
            attach_only=(
                current.attach_only if attach_only is _UNSET else bool(attach_only)
            ),
            autostart=(
                current.autostart if autostart is _UNSET else bool(autostart)
            ),
            proxy_mode=(
                current.proxy_mode if proxy_mode is _UNSET else str(proxy_mode)
            ),  # type: ignore[arg-type]
            proxy_server=(
                current.proxy_server if proxy_server is _UNSET else proxy_server
            ),
            proxy_bypass_list=(
                current.proxy_bypass_list
                if proxy_bypass_list is _UNSET
                else proxy_bypass_list
            ),
            proxy_binding_id=(
                current.proxy_binding_id
                if proxy_binding_id is _UNSET
                else proxy_binding_id
            ),
            proxy_credential_kind=(
                current.proxy_credential_kind
                if proxy_credential_kind is _UNSET
                else str(proxy_credential_kind)
            ),  # type: ignore[arg-type]
            close_targets_on_release=(
                current.close_targets_on_release
                if close_targets_on_release is _UNSET
                else bool(close_targets_on_release)
            ),
            close_targets_on_expire=(
                current.close_targets_on_expire
                if close_targets_on_expire is _UNSET
                else bool(close_targets_on_expire)
            ),
        )

        profiles = tuple(
            updated_profile if profile.name == current.name else profile
            for profile in system.profiles
        )
        default_profile = (
            updated_profile.name
            if set_as_default is True
            else system.default_profile
        )
        updated = self._rebuild_system(
            system,
            profiles=profiles,
            default_profile=default_profile,
        )
        saved = self.system_config_store.save(updated)
        self._sync_profile_host_service(system=saved, profile=updated_profile)
        changed_fields = _changed_profile_fields(current, updated_profile)
        if system.default_profile != default_profile:
            changed_fields = tuple((*changed_fields, "default_profile"))
        if changed_fields:
            self._emit_profile_event(
                BROWSER_PROFILE_UPDATED_EVENT,
                profile=updated_profile,
                system=saved,
                status="updated",
                changed_fields=changed_fields,
            )
        if current.enabled != updated_profile.enabled:
            self._emit_profile_event(
                BROWSER_PROFILE_ENABLED_EVENT
                if updated_profile.enabled
                else BROWSER_PROFILE_DISABLED_EVENT,
                profile=updated_profile,
                system=saved,
                status="enabled" if updated_profile.enabled else "disabled",
                changed_fields=("enabled",),
            )
        return saved

    def delete_profile(self, *, profile_name: str) -> BrowserSystemConfig:
        system = self.system_config_store.load()
        profile = self._get_profile(system, profile_name)
        if system.default_profile == profile.name:
            raise BrowserValidationError(
                "Cannot delete the default browser profile. Set another default first.",
            )
        self._raise_if_profile_runtime_active(profile.name, action="delete")
        self._raise_if_profile_allocation_active(profile.name, action="delete")
        remaining = tuple(
            candidate for candidate in system.profiles if candidate.name != profile.name
        )
        if not remaining:
            raise BrowserValidationError("Cannot delete the last browser profile.")

        default_profile = (
            system.default_profile
            if system.default_profile != profile.name
            else remaining[0].name
        )
        updated = self._rebuild_system(
            system,
            profiles=remaining,
            default_profile=default_profile,
        )
        saved = self.system_config_store.save(updated)
        self.runtime_state_store.delete(profile_name=profile.name)
        self.ref_store.delete_profile_refs(profile_name=profile.name)
        self._remove_profile_host_service(profile.name)
        self._emit_profile_event(
            BROWSER_PROFILE_DELETED_EVENT,
            profile=profile,
            system=saved,
            status="deleted",
        )
        return saved

    def enable_profile(self, *, profile_name: str) -> BrowserSystemConfig:
        return self.update_profile(profile_name=profile_name, enabled=True)

    def disable_profile(self, *, profile_name: str) -> BrowserSystemConfig:
        return self.update_profile(profile_name=profile_name, enabled=False)

    def record_profile_egress(
        self,
        *,
        profile_name: str,
        result: Mapping[str, Any],
    ) -> BrowserProfileRuntimeState:
        system = self.system_config_store.load()
        profile = self._get_profile(system, profile_name)
        sanitized = _sanitize_profile_egress_result(result)
        checked_at = _utc_now().isoformat()

        runtime_state = self.runtime_state_store.get(profile_name=profile.name)
        if runtime_state is None:
            runtime_state = BrowserProfileRuntimeState(profile_name=profile.name)
        runtime_state.metadata["proxy_egress"] = sanitized
        runtime_state.metadata["proxy_egress_status"] = sanitized.get("status")
        runtime_state.metadata["proxy_egress_checked_at"] = checked_at
        if sanitized.get("ip"):
            runtime_state.metadata["proxy_egress_ip"] = sanitized["ip"]
        else:
            runtime_state.metadata.pop("proxy_egress_ip", None)
        self.runtime_state_store.save(runtime_state)

        self._emit_profile_event(
            BROWSER_PROFILE_UPDATED_EVENT,
            profile=profile,
            system=system,
            status="egress_checked",
            changed_fields=("proxy_egress",),
            extra_payload={
                "proxy_egress_status": sanitized.get("status"),
                "proxy_egress_ip": sanitized.get("ip"),
                "proxy_egress_checked_at": checked_at,
            },
        )
        return runtime_state

    def _sync_profile_host_service(
        self,
        *,
        system: BrowserSystemConfig,
        profile: BrowserProfileConfig,
    ) -> None:
        if self.host_service_sync is None:
            return
        self.host_service_sync.sync_profile(system=system, profile=profile)

    def _remove_profile_host_service(self, profile_name: str) -> None:
        if self.host_service_sync is None:
            return
        self.host_service_sync.remove_profile(profile_name=profile_name)

    def set_default_profile(self, *, profile_name: str) -> BrowserSystemConfig:
        system = self.system_config_store.load()
        profile = self._get_profile(system, profile_name)
        updated = self._rebuild_system(
            system,
            default_profile=profile.name,
        )
        saved = self.system_config_store.save(updated)
        if system.default_profile != saved.default_profile:
            self._emit_profile_event(
                BROWSER_PROFILE_UPDATED_EVENT,
                profile=profile,
                system=saved,
                status="updated",
                changed_fields=("default_profile",),
            )
        return saved

    @staticmethod
    def _get_profile(
        system: BrowserSystemConfig,
        profile_name: str,
    ) -> BrowserProfileConfig:
        normalized_name = profile_name.strip().lower()
        for profile in system.profiles:
            if profile.name == normalized_name:
                return profile
        raise BrowserValidationError(
            f"Browser profile '{profile_name}' is not configured.",
        )

    def _raise_if_profile_runtime_active(self, profile_name: str, *, action: str) -> None:
        runtime_state = self.runtime_state_store.get(profile_name=profile_name)
        if runtime_state is None:
            return
        if runtime_state.attachment_status in {"attached", "attaching", "recovering", "degraded"}:
            raise BrowserValidationError(
                f"Cannot {action} browser profile '{profile_name}' while it is running. Stop it first.",
            )
        if runtime_state.browser_ref is not None or runtime_state.running_pid is not None:
            raise BrowserValidationError(
                f"Cannot {action} browser profile '{profile_name}' while it has active runtime state. Stop it first.",
            )

    def _raise_if_profile_allocation_active(self, profile_name: str, *, action: str) -> None:
        if self.allocation_store is None:
            return
        normalized_profile = profile_name.strip().lower()
        for allocation in self.allocation_store.list_allocations():
            if allocation.profile_name == normalized_profile and allocation.status == "active":
                raise BrowserValidationError(
                    f"Cannot {action} browser profile '{profile_name}' while allocation '{allocation.allocation_id}' is active. Release it first.",
                )

    def _emit_profile_event(
        self,
        event_name: str,
        *,
        profile: BrowserProfileConfig,
        system: BrowserSystemConfig,
        status: str,
        changed_fields: tuple[str, ...] = (),
        extra_payload: Mapping[str, Any] | None = None,
    ) -> None:
        payload = _profile_event_payload(
            profile,
            system=system,
            changed_fields=changed_fields,
        )
        if extra_payload:
            payload.update(extra_payload)
        emit_browser_event(
            self.event_emitter,
            event_name,
            status=status,
            payload=payload,
        )

    @staticmethod
    def _rebuild_system(
        system: BrowserSystemConfig,
        *,
        profiles: tuple[BrowserProfileConfig, ...] | None = None,
        default_profile: str | None = None,
    ) -> BrowserSystemConfig:
        return BrowserSystemConfig(
            default_profile=default_profile or system.default_profile,
            profiles=profiles or system.profiles,
            headless=system.headless,
            executable_path=system.executable_path,
            no_sandbox=system.no_sandbox,
            managed_tab_limit=system.managed_tab_limit,
            cdp_host=system.cdp_host,
            cdp_port_range_start=system.cdp_port_range_start,
            cdp_port_range_end=system.cdp_port_range_end,
        )
