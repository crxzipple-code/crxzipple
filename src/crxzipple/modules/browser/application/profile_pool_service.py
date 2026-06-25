from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from crxzipple.modules.browser.domain import (
    BrowserProfilePool,
    BrowserValidationError,
)

from .events import (
    BROWSER_POOL_CREATED_EVENT,
    BROWSER_POOL_DELETED_EVENT,
    BROWSER_POOL_DISABLED_EVENT,
    BROWSER_POOL_ENABLED_EVENT,
    BROWSER_POOL_UPDATED_EVENT,
    BrowserEventEmitter,
    emit_browser_event,
)
from .ports import (
    BrowserProfileAllocationStore,
    BrowserProfilePoolStore,
    BrowserSystemConfigStore,
)
from .profile_lifecycle_common import (
    UNSET as _UNSET,
    changed_pool_fields as _changed_pool_fields,
    pool_event_payload as _pool_event_payload,
)

@dataclass(slots=True)
class BrowserProfilePoolService:
    pool_store: BrowserProfilePoolStore
    system_config_store: BrowserSystemConfigStore
    allocation_store: BrowserProfileAllocationStore | None = None
    event_emitter: BrowserEventEmitter | None = None

    def list_pools(self) -> tuple[BrowserProfilePool, ...]:
        return self.pool_store.list_pools()

    def get_pool(self, *, pool_id: str) -> BrowserProfilePool:
        return self._get_pool(pool_id)

    def create_pool(
        self,
        *,
        pool_id: str,
        display_name: str | None = None,
        enabled: bool = True,
        profile_names: tuple[str, ...] = (),
        target_hosts: tuple[str, ...] = (),
        selection_strategy: str = "least_busy",
        max_concurrency_per_profile: int = 1,
        max_concurrency_total: int | None = None,
        allocation_ttl_seconds: int = 900,
        cooldown_seconds: int = 0,
        failure_cooldown_seconds: int = 300,
        allow_attach_only: bool = False,
        close_targets_on_release: bool = True,
        close_targets_on_expire: bool = True,
        health_policy: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> BrowserProfilePool:
        pool = BrowserProfilePool(
            pool_id=pool_id,
            display_name=display_name,
            enabled=enabled,
            profile_names=profile_names,
            target_hosts=target_hosts,
            selection_strategy=selection_strategy,  # type: ignore[arg-type]
            max_concurrency_per_profile=max_concurrency_per_profile,
            max_concurrency_total=max_concurrency_total,
            allocation_ttl_seconds=allocation_ttl_seconds,
            cooldown_seconds=cooldown_seconds,
            failure_cooldown_seconds=failure_cooldown_seconds,
            allow_attach_only=allow_attach_only,
            close_targets_on_release=close_targets_on_release,
            close_targets_on_expire=close_targets_on_expire,
            health_policy=health_policy or {},
            metadata=metadata or {},
        )
        if self.pool_store.get_pool(pool_id=pool.pool_id) is not None:
            raise BrowserValidationError(
                f"Browser profile pool '{pool.pool_id}' already exists.",
            )
        self._validate_pool(pool)
        saved = self.pool_store.save_pool(pool)
        self._emit_pool_event(
            BROWSER_POOL_CREATED_EVENT,
            pool=saved,
            status="created",
        )
        return saved

    def update_pool(
        self,
        *,
        pool_id: str,
        display_name: str | None | object = _UNSET,
        enabled: bool | object = _UNSET,
        profile_names: tuple[str, ...] | object = _UNSET,
        target_hosts: tuple[str, ...] | object = _UNSET,
        selection_strategy: str | object = _UNSET,
        max_concurrency_per_profile: int | object = _UNSET,
        max_concurrency_total: int | None | object = _UNSET,
        allocation_ttl_seconds: int | object = _UNSET,
        cooldown_seconds: int | object = _UNSET,
        failure_cooldown_seconds: int | object = _UNSET,
        allow_attach_only: bool | object = _UNSET,
        close_targets_on_release: bool | object = _UNSET,
        close_targets_on_expire: bool | object = _UNSET,
        health_policy: Mapping[str, Any] | object = _UNSET,
        metadata: Mapping[str, Any] | object = _UNSET,
    ) -> BrowserProfilePool:
        current = self._get_pool(pool_id)
        requested_enabled = current.enabled if enabled is _UNSET else bool(enabled)
        if not requested_enabled:
            self._raise_if_pool_allocation_active(current.pool_id, action="disable")
        updated = BrowserProfilePool(
            pool_id=current.pool_id,
            display_name=(
                current.display_name
                if display_name is _UNSET
                else display_name
            ),
            enabled=requested_enabled,
            profile_names=(
                current.profile_names
                if profile_names is _UNSET
                else profile_names
            ),
            target_hosts=(
                current.target_hosts
                if target_hosts is _UNSET
                else target_hosts
            ),
            selection_strategy=(
                current.selection_strategy
                if selection_strategy is _UNSET
                else str(selection_strategy)
            ),  # type: ignore[arg-type]
            max_concurrency_per_profile=(
                current.max_concurrency_per_profile
                if max_concurrency_per_profile is _UNSET
                else int(max_concurrency_per_profile)
            ),
            max_concurrency_total=(
                current.max_concurrency_total
                if max_concurrency_total is _UNSET
                else max_concurrency_total
            ),
            allocation_ttl_seconds=(
                current.allocation_ttl_seconds
                if allocation_ttl_seconds is _UNSET
                else int(allocation_ttl_seconds)
            ),
            cooldown_seconds=(
                current.cooldown_seconds
                if cooldown_seconds is _UNSET
                else int(cooldown_seconds)
            ),
            failure_cooldown_seconds=(
                current.failure_cooldown_seconds
                if failure_cooldown_seconds is _UNSET
                else int(failure_cooldown_seconds)
            ),
            allow_attach_only=(
                current.allow_attach_only
                if allow_attach_only is _UNSET
                else bool(allow_attach_only)
            ),
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
            health_policy=(
                current.health_policy
                if health_policy is _UNSET
                else health_policy
            ),
            metadata=current.metadata if metadata is _UNSET else metadata,
        )
        self._validate_pool(updated)
        saved = self.pool_store.save_pool(updated)
        changed_fields = _changed_pool_fields(current, saved)
        if changed_fields:
            self._emit_pool_event(
                BROWSER_POOL_UPDATED_EVENT,
                pool=saved,
                status="updated",
                changed_fields=changed_fields,
            )
        if current.enabled != saved.enabled:
            self._emit_pool_event(
                BROWSER_POOL_ENABLED_EVENT
                if saved.enabled
                else BROWSER_POOL_DISABLED_EVENT,
                pool=saved,
                status="enabled" if saved.enabled else "disabled",
                changed_fields=("enabled",),
            )
        return saved

    def delete_pool(self, *, pool_id: str) -> None:
        pool = self._get_pool(pool_id)
        self._raise_if_pool_allocation_active(pool.pool_id, action="delete")
        self.pool_store.delete_pool(pool_id=pool.pool_id)
        self._emit_pool_event(
            BROWSER_POOL_DELETED_EVENT,
            pool=pool,
            status="deleted",
        )

    def enable_pool(self, *, pool_id: str) -> BrowserProfilePool:
        return self.update_pool(pool_id=pool_id, enabled=True)

    def disable_pool(self, *, pool_id: str) -> BrowserProfilePool:
        return self.update_pool(pool_id=pool_id, enabled=False)

    def _get_pool(self, pool_id: str) -> BrowserProfilePool:
        normalized = pool_id.strip().lower()
        if not normalized:
            raise BrowserValidationError("browser profile pool id is required.")
        pool = self.pool_store.get_pool(pool_id=normalized)
        if pool is None:
            raise BrowserValidationError(
                f"Browser profile pool '{pool_id}' is not configured.",
            )
        return pool

    def _validate_pool(self, pool: BrowserProfilePool) -> None:
        if not pool.profile_names:
            raise BrowserValidationError(
                "browser profile pool must include at least one profile.",
            )
        system = self.system_config_store.load()
        profiles = {profile.name: profile for profile in system.profiles}
        missing = tuple(
            profile_name
            for profile_name in pool.profile_names
            if profile_name not in profiles
        )
        if missing:
            raise BrowserValidationError(
                "browser profile pool references unknown profiles: "
                + ", ".join(missing),
            )
        if pool.allow_attach_only:
            return
        attach_only_profiles = tuple(
            profile.name
            for profile in profiles.values()
            if profile.name in pool.profile_names
            and (profile.attach_only or profile.driver == "existing-session")
        )
        if attach_only_profiles:
            raise BrowserValidationError(
                "browser profile pool contains attach-only profiles; "
                "set allow_attach_only to true or remove: "
                + ", ".join(attach_only_profiles),
            )

    def _raise_if_pool_allocation_active(self, pool_id: str, *, action: str) -> None:
        if self.allocation_store is None:
            return
        normalized_pool = pool_id.strip().lower()
        for allocation in self.allocation_store.list_allocations():
            if allocation.pool_id == normalized_pool and allocation.status == "active":
                raise BrowserValidationError(
                    f"Cannot {action} browser profile pool '{pool_id}' while allocation '{allocation.allocation_id}' is active. Release it first.",
                )

    def _emit_pool_event(
        self,
        event_name: str,
        *,
        pool: BrowserProfilePool,
        status: str,
        changed_fields: tuple[str, ...] = (),
    ) -> None:
        emit_browser_event(
            self.event_emitter,
            event_name,
            status=status,
            payload=_pool_event_payload(pool, changed_fields=changed_fields),
        )
