from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping

from crxzipple.modules.browser.domain import (
    BrowserProfileAllocation,
    BrowserProfileConfig,
    BrowserProfilePool,
    BrowserValidationError,
)

from .ports import BrowserProfileAllocationStore, BrowserRuntimeStateStore


def find_reusable_allocation(
    allocation_store: BrowserProfileAllocationStore,
    *,
    pool_id: str,
    consumer_kind: str,
    consumer_id: str,
    target_host: str | None,
    now: datetime,
) -> BrowserProfileAllocation | None:
    for allocation in allocation_store.list_allocations():
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


def profile_or_raise(
    profiles: Mapping[str, BrowserProfileConfig],
    profile_name: str,
) -> BrowserProfileConfig:
    profile = profiles.get(profile_name.strip().lower())
    if profile is None:
        raise BrowserValidationError(
            f"Browser profile '{profile_name}' is not configured.",
        )
    return profile


def validate_pool_profile_candidate(
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


@dataclass(slots=True)
class BrowserProfileAllocationSelector:
    allocation_store: BrowserProfileAllocationStore
    runtime_state_store: BrowserRuntimeStateStore

    def select_profile(
        self,
        *,
        profiles: Mapping[str, BrowserProfileConfig],
        pool: BrowserProfilePool | None,
        profile_name: str | None,
        default_profile: str,
        now: datetime,
    ) -> tuple[BrowserProfileConfig, str]:
        requested_profile = profile_name.strip().lower() if profile_name else None
        if pool is None:
            profile = profile_or_raise(
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
            profile = profile_or_raise(profiles, requested_profile)
            validate_pool_profile_candidate(pool=pool, profile=profile)
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
            for candidate_profile_name in pool.profile_names
            for profile in (profiles.get(candidate_profile_name),)
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

    def _candidate_available(
        self,
        *,
        pool: BrowserProfilePool,
        profile: BrowserProfileConfig,
        active_allocations: tuple[BrowserProfileAllocation, ...],
        now: datetime,
    ) -> bool:
        try:
            validate_pool_profile_candidate(pool=pool, profile=profile)
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
        return not self._profile_in_cooldown(
            pool=pool,
            profile_name=profile.name,
            now=now,
        )

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
                and allocation.released_at
                + timedelta(seconds=pool.failure_cooldown_seconds)
                > now
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
        order = {
            profile_name: index
            for index, profile_name in enumerate(pool.profile_names)
        }
        return min(
            candidates,
            key=lambda profile: (
                active_counts[profile.name],
                order.get(profile.name, 9999),
            ),
        ), "least_busy"
