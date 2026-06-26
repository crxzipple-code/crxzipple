from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from uuid import uuid4

from crxzipple.modules.browser.domain import (
    BrowserProfileAllocation,
    BrowserProfilePool,
    BrowserValidationError,
)

from .events import (
    BROWSER_ALLOCATION_ACQUIRED_EVENT,
    BROWSER_ALLOCATION_EXPIRED_EVENT,
    BROWSER_ALLOCATION_FAILED_EVENT,
    BROWSER_ALLOCATION_HEARTBEATED_EVENT,
    BROWSER_ALLOCATION_LOST_EVENT,
    BROWSER_ALLOCATION_RELEASED_EVENT,
    BrowserEventEmitter,
    emit_browser_event,
)
from .ports import (
    BrowserAllocationTargetInspector,
    BrowserAllocationTargetRecycler,
    BrowserProfileAllocationStore,
    BrowserProfilePoolStore,
    BrowserRuntimeStateStore,
    BrowserSystemConfigStore,
)
from .profile_allocation_selection import (
    BrowserProfileAllocationSelector,
    find_reusable_allocation,
)
from .profile_allocation_targets import (
    BrowserProfileAllocationTargetLifecycle,
    forget_allocation_target as _forget_allocation_target,
    reconcile_allocation_targets as _reconcile_allocation_targets,
    remember_allocation_target as _remember_allocation_target,
)
from .profile_lifecycle_common import (
    allocation_event_payload as _allocation_event_payload,
    require_positive_int as _require_positive_int,
    utc_now as _utc_now,
)

@dataclass(slots=True)
class BrowserProfileAllocatorService:
    allocation_store: BrowserProfileAllocationStore
    pool_store: BrowserProfilePoolStore
    system_config_store: BrowserSystemConfigStore
    runtime_state_store: BrowserRuntimeStateStore
    target_recycler: BrowserAllocationTargetRecycler | None = None
    target_inspector: BrowserAllocationTargetInspector | None = None
    event_emitter: BrowserEventEmitter | None = None

    def list_allocations(
        self,
        *,
        status: str | None = None,
        pool_id: str | None = None,
        profile_name: str | None = None,
        active_only: bool = False,
    ) -> tuple[BrowserProfileAllocation, ...]:
        self.expire_allocations()
        allocations = self.allocation_store.list_allocations()
        normalized_status = status.strip().lower() if status else None
        normalized_pool = pool_id.strip().lower() if pool_id else None
        normalized_profile = profile_name.strip().lower() if profile_name else None
        if active_only:
            normalized_status = "active"
        return tuple(
            allocation
            for allocation in allocations
            if (normalized_status is None or allocation.status == normalized_status)
            and (normalized_pool is None or allocation.pool_id == normalized_pool)
            and (normalized_profile is None or allocation.profile_name == normalized_profile)
        )

    def get_allocation(self, *, allocation_id: str) -> BrowserProfileAllocation:
        allocation = self.allocation_store.get_allocation(allocation_id=allocation_id)
        if allocation is None:
            raise BrowserValidationError(
                f"Browser profile allocation '{allocation_id}' is not configured.",
            )
        if allocation.status == "active" and allocation.expires_at <= _utc_now():
            self.expire_allocations()
            allocation = self.allocation_store.get_allocation(allocation_id=allocation_id)
            if allocation is None:
                raise BrowserValidationError(
                    f"Browser profile allocation '{allocation_id}' is not configured.",
                )
        return allocation

    def allocate(
        self,
        *,
        consumer_kind: str,
        consumer_id: str,
        pool_id: str | None = None,
        profile_name: str | None = None,
        target_host: str | None = None,
        now: datetime | None = None,
    ) -> BrowserProfileAllocation:
        current_time = now or _utc_now()
        self.expire_allocations(now=current_time)
        system = self.system_config_store.load()
        profiles = {profile.name: profile for profile in system.profiles}
        pool = self._resolve_pool(pool_id)
        synthetic_pool_id = (
            pool.pool_id
            if pool is not None
            else f"profile:{(profile_name or system.default_profile).strip().lower()}"
        )
        normalized_consumer_kind = consumer_kind.strip().lower()
        normalized_consumer_id = consumer_id.strip()
        normalized_target_host = target_host.strip().lower() if target_host else None
        reusable = find_reusable_allocation(
            self.allocation_store,
            pool_id=synthetic_pool_id,
            consumer_kind=normalized_consumer_kind,
            consumer_id=normalized_consumer_id,
            target_host=normalized_target_host,
            now=current_time,
        )
        if reusable is not None:
            return reusable

        selected_profile, selection_reason = self._allocation_selector().select_profile(
            profiles=profiles,
            pool=pool,
            profile_name=profile_name,
            default_profile=system.default_profile,
            now=current_time,
        )
        ttl_seconds = pool.allocation_ttl_seconds if pool is not None else 900
        allocation = BrowserProfileAllocation(
            allocation_id=f"browser_alloc_{uuid4().hex}",
            pool_id=synthetic_pool_id,
            profile_name=selected_profile.name,
            consumer_kind=normalized_consumer_kind,  # type: ignore[arg-type]
            consumer_id=normalized_consumer_id,
            target_host=normalized_target_host,
            status="active",
            acquired_at=current_time,
            expires_at=current_time + timedelta(seconds=ttl_seconds),
            metadata={
                "selection_reason": selection_reason,
                "profile_source": (
                    "pool_allocation" if pool is not None else "explicit_profile"
                ),
                "host_service_key": f"host:browser:{selected_profile.name}",
            },
        )
        saved = self.allocation_store.save_allocation(allocation)
        self._emit_allocation_event(
            BROWSER_ALLOCATION_ACQUIRED_EVENT,
            allocation=saved,
            status="acquired",
        )
        return saved

    def release_allocation(
        self,
        *,
        allocation_id: str,
        reason: str = "released",
        failed: bool = False,
        recycle_targets: bool | None = None,
        now: datetime | None = None,
    ) -> BrowserProfileAllocation:
        allocation = self.allocation_store.get_allocation(allocation_id=allocation_id)
        if allocation is None:
            raise BrowserValidationError(
                f"Browser profile allocation '{allocation_id}' is not configured.",
            )
        if allocation.status != "active":
            return allocation
        current_time = now or _utc_now()
        target_lifecycle = self._target_lifecycle()
        should_recycle = target_lifecycle.should_recycle_targets(
            allocation,
            reason_kind="release",
            explicit=recycle_targets,
        )
        metadata = target_lifecycle.recycle_target_metadata(
            allocation,
            reason=reason,
        ) if should_recycle else dict(allocation.metadata)
        updated = replace(
            allocation,
            status="failed" if failed else "released",
            released_at=current_time,
            release_reason=reason,
            metadata=metadata,
        )
        saved = self.allocation_store.save_allocation(updated)
        self._emit_allocation_event(
            BROWSER_ALLOCATION_FAILED_EVENT
            if failed
            else BROWSER_ALLOCATION_RELEASED_EVENT,
            allocation=saved,
            status=saved.status,
        )
        return saved

    def fail_allocation(
        self,
        *,
        allocation_id: str,
        reason: str = "failed",
        now: datetime | None = None,
    ) -> BrowserProfileAllocation:
        return self.release_allocation(
            allocation_id=allocation_id,
            reason=reason,
            failed=True,
            now=now,
        )

    def heartbeat_allocation(
        self,
        *,
        allocation_id: str,
        ttl_seconds: int | None = None,
        now: datetime | None = None,
    ) -> BrowserProfileAllocation:
        current_time = now or _utc_now()
        allocation = self.get_allocation(allocation_id=allocation_id)
        if not allocation.is_active_at(current_time):
            expired = self.expire_allocations(now=current_time)
            refreshed = self.allocation_store.get_allocation(
                allocation_id=allocation.allocation_id,
            )
            allocation = refreshed or allocation
            if allocation.status != "active":
                raise BrowserValidationError(
                    f"Browser profile allocation '{allocation_id}' is not active.",
                )
            if any(item.allocation_id == allocation.allocation_id for item in expired):
                raise BrowserValidationError(
                    f"Browser profile allocation '{allocation_id}' expired before heartbeat.",
                )
        extension_seconds = (
            _require_positive_int(ttl_seconds, label="ttl_seconds")
            if ttl_seconds is not None
            else self._allocation_ttl_seconds(allocation)
        )
        updated = replace(
            allocation,
            expires_at=current_time + timedelta(seconds=extension_seconds),
            last_heartbeat_at=current_time,
            metadata={
                **dict(allocation.metadata),
                "last_heartbeat_at": current_time.isoformat(),
            },
        )
        saved = self.allocation_store.save_allocation(updated)
        self._emit_allocation_event(
            BROWSER_ALLOCATION_HEARTBEATED_EVENT,
            allocation=saved,
            status="heartbeated",
        )
        return saved

    def reconcile_allocation(
        self,
        *,
        allocation_id: str,
        now: datetime | None = None,
    ) -> BrowserProfileAllocation:
        current_time = now or _utc_now()
        allocation = self.get_allocation(allocation_id=allocation_id)
        if allocation.status != "active":
            return allocation
        if allocation.expires_at <= current_time:
            expired = self.expire_allocations(now=current_time)
            for item in expired:
                if item.allocation_id == allocation.allocation_id:
                    return item
            refreshed = self.allocation_store.get_allocation(
                allocation_id=allocation.allocation_id,
            )
            return refreshed or allocation
        result = _reconcile_allocation_targets(
            allocation,
            target_inspector=self.target_inspector,
            now=current_time,
        )
        saved = self.allocation_store.save_allocation(result.allocation)
        if result.lost:
            self._emit_allocation_event(
                BROWSER_ALLOCATION_LOST_EVENT,
                allocation=saved,
                status="lost",
            )
        return saved

    def reconcile_allocations(
        self,
        *,
        now: datetime | None = None,
    ) -> tuple[BrowserProfileAllocation, ...]:
        current_time = now or _utc_now()
        reconciled: list[BrowserProfileAllocation] = []
        for allocation in self.list_allocations(active_only=True):
            reconciled.append(
                self.reconcile_allocation(
                    allocation_id=allocation.allocation_id,
                    now=current_time,
                ),
            )
        return tuple(reconciled)

    def expire_allocations(
        self,
        *,
        recycle_targets: bool | None = None,
        now: datetime | None = None,
    ) -> tuple[BrowserProfileAllocation, ...]:
        current_time = now or _utc_now()
        expired: list[BrowserProfileAllocation] = []
        for allocation in self.allocation_store.list_allocations():
            if allocation.status != "active" or allocation.expires_at > current_time:
                continue
            target_lifecycle = self._target_lifecycle()
            should_recycle = target_lifecycle.should_recycle_targets(
                allocation,
                reason_kind="expire",
                explicit=recycle_targets,
            )
            metadata = target_lifecycle.recycle_target_metadata(
                allocation,
                reason="ttl_expired",
            ) if should_recycle else dict(allocation.metadata)
            updated = replace(
                allocation,
                status="expired",
                released_at=current_time,
                release_reason="ttl_expired",
                metadata=metadata,
            )
            saved = self.allocation_store.save_allocation(updated)
            self._emit_allocation_event(
                BROWSER_ALLOCATION_EXPIRED_EVENT,
                allocation=saved,
                status="expired",
            )
            expired.append(saved)
        return tuple(expired)

    def drain_pool(
        self,
        *,
        pool_id: str,
        reason: str = "pool_drained",
        recycle_targets: bool | None = None,
        now: datetime | None = None,
    ) -> tuple[BrowserProfileAllocation, ...]:
        pool = self._get_pool(pool_id, require_enabled=False)
        current_time = now or _utc_now()
        drained: list[BrowserProfileAllocation] = []
        for allocation in self.list_allocations(
            pool_id=pool.pool_id,
            active_only=True,
        ):
            drained.append(
                self.release_allocation(
                    allocation_id=allocation.allocation_id,
                    reason=reason,
                    recycle_targets=recycle_targets,
                    now=current_time,
                )
            )
        return tuple(drained)

    def remember_allocation_target(
        self,
        *,
        allocation_id: str,
        target_id: str,
    ) -> BrowserProfileAllocation:
        allocation = self.get_allocation(allocation_id=allocation_id)
        updated = _remember_allocation_target(
            allocation,
            target_id=target_id,
        )
        return self.allocation_store.save_allocation(updated)

    def forget_allocation_target(
        self,
        *,
        allocation_id: str,
        target_id: str,
    ) -> BrowserProfileAllocation:
        allocation = self.get_allocation(allocation_id=allocation_id)
        updated = _forget_allocation_target(
            allocation,
            target_id=target_id,
        )
        return self.allocation_store.save_allocation(updated)

    def _allocation_ttl_seconds(self, allocation: BrowserProfileAllocation) -> int:
        pool = self.pool_store.get_pool(pool_id=allocation.pool_id)
        if pool is not None:
            return pool.allocation_ttl_seconds
        duration = int(
            (allocation.expires_at - allocation.acquired_at).total_seconds(),
        )
        return max(duration, 1)

    def _resolve_pool(self, pool_id: str | None) -> BrowserProfilePool | None:
        if pool_id is None or not pool_id.strip():
            return None
        return self._get_pool(pool_id)

    def _get_pool(self, pool_id: str, *, require_enabled: bool = True) -> BrowserProfilePool:
        pool = self.pool_store.get_pool(pool_id=pool_id.strip().lower())
        if pool is None:
            raise BrowserValidationError(
                f"Browser profile pool '{pool_id}' is not configured.",
            )
        if require_enabled and not pool.enabled:
            raise BrowserValidationError(
                f"Browser profile pool '{pool.pool_id}' is disabled.",
            )
        return pool

    def _allocation_selector(self) -> BrowserProfileAllocationSelector:
        return BrowserProfileAllocationSelector(
            allocation_store=self.allocation_store,
            runtime_state_store=self.runtime_state_store,
        )

    def _target_lifecycle(self) -> BrowserProfileAllocationTargetLifecycle:
        return BrowserProfileAllocationTargetLifecycle(
            pool_store=self.pool_store,
            system_config_store=self.system_config_store,
            target_recycler=self.target_recycler,
        )

    def _emit_allocation_event(
        self,
        event_name: str,
        *,
        allocation: BrowserProfileAllocation,
        status: str,
    ) -> None:
        emit_browser_event(
            self.event_emitter,
            event_name,
            status=status,
            payload=_allocation_event_payload(allocation),
        )
