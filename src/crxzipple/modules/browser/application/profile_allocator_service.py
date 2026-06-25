from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any, Mapping
from uuid import uuid4

from crxzipple.modules.browser.domain import (
    BrowserProfileAllocation,
    BrowserProfileConfig,
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
        reusable = self._find_reusable_allocation(
            pool_id=synthetic_pool_id,
            consumer_kind=normalized_consumer_kind,
            consumer_id=normalized_consumer_id,
            target_host=normalized_target_host,
            now=current_time,
        )
        if reusable is not None:
            return reusable

        selected_profile, selection_reason = self._select_profile(
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
        should_recycle = self._should_recycle_targets(
            allocation,
            reason_kind="release",
            explicit=recycle_targets,
        )
        metadata = self._recycle_target_metadata(
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
        if self.target_inspector is None or not allocation.owned_target_ids:
            updated = replace(
                allocation,
                metadata={
                    **dict(allocation.metadata),
                    "target_reconcile": {
                        "status": "not_required",
                        "checked_at": current_time.isoformat(),
                    },
                },
            )
            return self.allocation_store.save_allocation(updated)
        try:
            live_target_ids = self.target_inspector.list_target_ids(
                profile_name=allocation.profile_name,
            )
        except BrowserValidationError as exc:
            return self._mark_allocation_lost(
                allocation,
                reason="target_reconcile_failed",
                now=current_time,
                metadata={
                    "target_reconcile": {
                        "status": "failed",
                        "checked_at": current_time.isoformat(),
                        "error": str(exc)[:500],
                    },
                },
            )
        live_set = set(live_target_ids)
        kept_targets = tuple(
            target_id for target_id in allocation.owned_target_ids if target_id in live_set
        )
        missing_targets = tuple(
            target_id
            for target_id in allocation.owned_target_ids
            if target_id not in live_set
        )
        reconcile_metadata = {
            "status": "ok" if not missing_targets else "missing_targets",
            "checked_at": current_time.isoformat(),
            "live_target_ids": list(live_target_ids),
            "missing_target_ids": list(missing_targets),
        }
        if missing_targets and not kept_targets:
            return self._mark_allocation_lost(
                allocation,
                reason="target_lost",
                now=current_time,
                metadata={"target_reconcile": reconcile_metadata},
            )
        updated = replace(
            allocation,
            owned_target_ids=kept_targets,
            metadata={
                **dict(allocation.metadata),
                "target_reconcile": reconcile_metadata,
            },
        )
        return self.allocation_store.save_allocation(updated)

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
            should_recycle = self._should_recycle_targets(
                allocation,
                reason_kind="expire",
                explicit=recycle_targets,
            )
            metadata = self._recycle_target_metadata(
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
        normalized_target = target_id.strip()
        if allocation.status != "active" or not normalized_target:
            return allocation
        if normalized_target in allocation.owned_target_ids:
            return allocation
        updated = replace(
            allocation,
            owned_target_ids=(*allocation.owned_target_ids, normalized_target),
            metadata={
                **dict(allocation.metadata),
                "last_owned_target_id": normalized_target,
            },
        )
        return self.allocation_store.save_allocation(updated)

    def forget_allocation_target(
        self,
        *,
        allocation_id: str,
        target_id: str,
    ) -> BrowserProfileAllocation:
        allocation = self.get_allocation(allocation_id=allocation_id)
        normalized_target = target_id.strip()
        if allocation.status != "active" or not normalized_target:
            return allocation
        remaining = tuple(
            owned_target_id
            for owned_target_id in allocation.owned_target_ids
            if owned_target_id != normalized_target
        )
        if remaining == allocation.owned_target_ids:
            return allocation
        updated = replace(
            allocation,
            owned_target_ids=remaining,
            metadata={
                **dict(allocation.metadata),
                "last_released_target_id": normalized_target,
            },
        )
        return self.allocation_store.save_allocation(updated)

    def _recycle_target_metadata(
        self,
        allocation: BrowserProfileAllocation,
        *,
        reason: str,
    ) -> dict[str, Any]:
        metadata = dict(allocation.metadata)
        if self.target_recycler is None or not allocation.owned_target_ids:
            return metadata
        closed_target_ids: list[str] = []
        failed_targets: list[dict[str, str]] = []
        for target_id in allocation.owned_target_ids:
            try:
                self.target_recycler.close_owned_target(
                    profile_name=allocation.profile_name,
                    target_id=target_id,
                )
            except BrowserValidationError as exc:
                message = str(exc)
                if "not found" in message.lower():
                    closed_target_ids.append(target_id)
                    continue
                failed_targets.append(
                    {
                        "target_id": target_id,
                        "reason": message[:500],
                    },
                )
            else:
                closed_target_ids.append(target_id)
        metadata["target_recycle"] = {
            "reason": reason,
            "closed_target_ids": closed_target_ids,
            "failed_targets": failed_targets,
        }
        return metadata

    def _should_recycle_targets(
        self,
        allocation: BrowserProfileAllocation,
        *,
        reason_kind: str,
        explicit: bool | None,
    ) -> bool:
        if explicit is not None:
            return explicit
        pool = self.pool_store.get_pool(pool_id=allocation.pool_id)
        if pool is not None:
            return (
                pool.close_targets_on_expire
                if reason_kind == "expire"
                else pool.close_targets_on_release
            )
        system = self.system_config_store.load()
        profile = self._profile_or_raise(
            {profile.name: profile for profile in system.profiles},
            allocation.profile_name,
        )
        return (
            profile.close_targets_on_expire
            if reason_kind == "expire"
            else profile.close_targets_on_release
        )

    def _allocation_ttl_seconds(self, allocation: BrowserProfileAllocation) -> int:
        pool = self.pool_store.get_pool(pool_id=allocation.pool_id)
        if pool is not None:
            return pool.allocation_ttl_seconds
        duration = int(
            (allocation.expires_at - allocation.acquired_at).total_seconds(),
        )
        return max(duration, 1)

    def _mark_allocation_lost(
        self,
        allocation: BrowserProfileAllocation,
        *,
        reason: str,
        now: datetime,
        metadata: Mapping[str, Any] | None = None,
    ) -> BrowserProfileAllocation:
        updated = replace(
            allocation,
            status="lost",
            released_at=now,
            release_reason=reason,
            metadata={
                **dict(allocation.metadata),
                **dict(metadata or {}),
            },
        )
        saved = self.allocation_store.save_allocation(updated)
        self._emit_allocation_event(
            BROWSER_ALLOCATION_LOST_EVENT,
            allocation=saved,
            status="lost",
        )
        return saved

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

    def _find_reusable_allocation(
        self,
        *,
        pool_id: str,
        consumer_kind: str,
        consumer_id: str,
        target_host: str | None,
        now: datetime,
    ) -> BrowserProfileAllocation | None:
        for allocation in self.allocation_store.list_allocations():
            if not allocation.is_active_at(now):
                continue
            if allocation.matches_consumer(
                pool_id=pool_id,
                consumer_kind=consumer_kind,
                consumer_id=consumer_id,
                target_host=target_host,
            ):
                return allocation
        return None

    def _select_profile(
        self,
        *,
        profiles: dict[str, BrowserProfileConfig],
        pool: BrowserProfilePool | None,
        profile_name: str | None,
        default_profile: str,
        now: datetime,
    ) -> tuple[BrowserProfileConfig, str]:
        requested_profile = profile_name.strip().lower() if profile_name else None
        if pool is None:
            profile = self._profile_or_raise(
                profiles,
                requested_profile or default_profile,
            )
            if not profile.enabled:
                raise BrowserValidationError(
                    f"Browser profile '{profile.name}' is disabled.",
                )
            return profile, "explicit_profile"

        if requested_profile is not None:
            if requested_profile not in pool.profile_names:
                raise BrowserValidationError(
                    f"Browser profile '{requested_profile}' is not a member of pool '{pool.pool_id}'.",
                )
            if pool.selection_strategy != "manual_only":
                raise BrowserValidationError(
                    "profile and profile_pool can be combined only when pool selection_strategy is manual_only.",
                )
            profile = self._profile_or_raise(profiles, requested_profile)
            self._validate_pool_profile_candidate(pool=pool, profile=profile)
            return profile, "manual_pool_profile"

        if pool.selection_strategy == "manual_only":
            raise BrowserValidationError(
                f"Browser profile pool '{pool.pool_id}' requires an explicit profile.",
            )

        active_allocations = tuple(
            allocation
            for allocation in self.allocation_store.list_allocations()
            if allocation.pool_id == pool.pool_id and allocation.is_active_at(now)
        )
        if (
            pool.max_concurrency_total is not None
            and len(active_allocations) >= pool.max_concurrency_total
        ):
            raise BrowserValidationError(
                f"Browser profile pool '{pool.pool_id}' reached max concurrency.",
            )
        candidates = tuple(
            profile
            for profile_name in pool.profile_names
            for profile in (profiles.get(profile_name),)
            if profile is not None
            and self._candidate_available(
                pool=pool,
                profile=profile,
                active_allocations=active_allocations,
                now=now,
            )
        )
        if not candidates:
            raise BrowserValidationError(
                f"Browser profile pool '{pool.pool_id}' has no eligible profile.",
            )
        if pool.selection_strategy == "round_robin":
            return self._select_round_robin(pool=pool, candidates=candidates)
        return self._select_least_busy(
            pool=pool,
            candidates=candidates,
            active_allocations=active_allocations,
        )

    def _profile_or_raise(
        self,
        profiles: dict[str, BrowserProfileConfig],
        profile_name: str,
    ) -> BrowserProfileConfig:
        profile = profiles.get(profile_name.strip().lower())
        if profile is None:
            raise BrowserValidationError(
                f"Browser profile '{profile_name}' is not configured.",
            )
        return profile

    def _validate_pool_profile_candidate(
        self,
        *,
        pool: BrowserProfilePool,
        profile: BrowserProfileConfig,
    ) -> None:
        if not profile.enabled:
            raise BrowserValidationError(
                f"Browser profile '{profile.name}' is disabled.",
            )
        if (
            not pool.allow_attach_only
            and (profile.attach_only or profile.driver == "existing-session")
        ):
            raise BrowserValidationError(
                f"Browser profile '{profile.name}' is attach-only and cannot be allocated by pool '{pool.pool_id}'.",
            )

    def _candidate_available(
        self,
        *,
        pool: BrowserProfilePool,
        profile: BrowserProfileConfig,
        active_allocations: tuple[BrowserProfileAllocation, ...],
        now: datetime,
    ) -> bool:
        try:
            self._validate_pool_profile_candidate(pool=pool, profile=profile)
        except BrowserValidationError:
            return False
        if self._runtime_blocked(profile.name):
            return False
        profile_active_count = sum(
            1
            for allocation in active_allocations
            if allocation.profile_name == profile.name
        )
        if profile_active_count >= pool.max_concurrency_per_profile:
            return False
        return not self._profile_in_cooldown(pool=pool, profile_name=profile.name, now=now)

    def _runtime_blocked(self, profile_name: str) -> bool:
        runtime_state = self.runtime_state_store.get(profile_name=profile_name)
        if runtime_state is None:
            return False
        return runtime_state.attachment_status in {"failed", "degraded"}

    def _profile_in_cooldown(
        self,
        *,
        pool: BrowserProfilePool,
        profile_name: str,
        now: datetime,
    ) -> bool:
        for allocation in self.allocation_store.list_allocations():
            if allocation.pool_id != pool.pool_id or allocation.profile_name != profile_name:
                continue
            if allocation.released_at is None:
                continue
            if (
                allocation.status == "failed"
                and allocation.released_at + timedelta(seconds=pool.failure_cooldown_seconds) > now
            ):
                return True
            if (
                allocation.status == "released"
                and allocation.released_at + timedelta(seconds=pool.cooldown_seconds) > now
            ):
                return True
        return False

    def _select_round_robin(
        self,
        *,
        pool: BrowserProfilePool,
        candidates: tuple[BrowserProfileConfig, ...],
    ) -> tuple[BrowserProfileConfig, str]:
        candidate_names = [profile.name for profile in candidates]
        last = next(
            (
                allocation.profile_name
                for allocation in sorted(
                    self.allocation_store.list_allocations(),
                    key=lambda item: item.acquired_at,
                    reverse=True,
                )
                if allocation.pool_id == pool.pool_id
                and allocation.profile_name in candidate_names
            ),
            None,
        )
        if last is None:
            return candidates[0], "round_robin"
        index = candidate_names.index(last)
        return candidates[(index + 1) % len(candidates)], "round_robin"

    def _select_least_busy(
        self,
        *,
        pool: BrowserProfilePool,
        candidates: tuple[BrowserProfileConfig, ...],
        active_allocations: tuple[BrowserProfileAllocation, ...],
    ) -> tuple[BrowserProfileConfig, str]:
        active_counts = {
            profile.name: sum(
                1
                for allocation in active_allocations
                if allocation.profile_name == profile.name
            )
            for profile in candidates
        }
        order = {profile_name: index for index, profile_name in enumerate(pool.profile_names)}
        return min(
            candidates,
            key=lambda profile: (active_counts[profile.name], order.get(profile.name, 9999)),
        ), "least_busy"

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
