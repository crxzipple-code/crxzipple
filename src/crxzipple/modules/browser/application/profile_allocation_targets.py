from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from crxzipple.modules.browser.domain import (
    BrowserProfileAllocation,
    BrowserValidationError,
)

from .ports import (
    BrowserAllocationTargetInspector,
    BrowserAllocationTargetRecycler,
    BrowserProfilePoolStore,
    BrowserSystemConfigStore,
)
from .profile_allocation_selection import profile_or_raise


@dataclass(frozen=True, slots=True)
class BrowserTargetReconcileResult:
    allocation: BrowserProfileAllocation
    lost: bool = False


def remember_allocation_target(
    allocation: BrowserProfileAllocation,
    *,
    target_id: str,
) -> BrowserProfileAllocation:
    normalized_target = target_id.strip()
    if allocation.status != "active" or not normalized_target:
        return allocation
    if normalized_target in allocation.owned_target_ids:
        return allocation
    return replace(
        allocation,
        owned_target_ids=(*allocation.owned_target_ids, normalized_target),
        metadata={
            **dict(allocation.metadata),
            "last_owned_target_id": normalized_target,
        },
    )


def forget_allocation_target(
    allocation: BrowserProfileAllocation,
    *,
    target_id: str,
) -> BrowserProfileAllocation:
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
    return replace(
        allocation,
        owned_target_ids=remaining,
        metadata={
            **dict(allocation.metadata),
            "last_released_target_id": normalized_target,
        },
    )


def reconcile_allocation_targets(
    allocation: BrowserProfileAllocation,
    *,
    target_inspector: BrowserAllocationTargetInspector | None,
    now: datetime,
) -> BrowserTargetReconcileResult:
    if target_inspector is None or not allocation.owned_target_ids:
        return BrowserTargetReconcileResult(
            allocation=replace(
                allocation,
                metadata={
                    **dict(allocation.metadata),
                    "target_reconcile": {
                        "status": "not_required",
                        "checked_at": now.isoformat(),
                    },
                },
            ),
        )
    try:
        live_target_ids = target_inspector.list_target_ids(
            profile_name=allocation.profile_name,
        )
    except BrowserValidationError as exc:
        return BrowserTargetReconcileResult(
            allocation=_lost_allocation(
                allocation,
                reason="target_reconcile_failed",
                now=now,
                metadata={
                    "target_reconcile": {
                        "status": "failed",
                        "checked_at": now.isoformat(),
                        "error": str(exc)[:500],
                    },
                },
            ),
            lost=True,
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
        "checked_at": now.isoformat(),
        "live_target_ids": list(live_target_ids),
        "missing_target_ids": list(missing_targets),
    }
    if missing_targets and not kept_targets:
        return BrowserTargetReconcileResult(
            allocation=_lost_allocation(
                allocation,
                reason="target_lost",
                now=now,
                metadata={"target_reconcile": reconcile_metadata},
            ),
            lost=True,
        )
    return BrowserTargetReconcileResult(
        allocation=replace(
            allocation,
            owned_target_ids=kept_targets,
            metadata={
                **dict(allocation.metadata),
                "target_reconcile": reconcile_metadata,
            },
        ),
    )


def _lost_allocation(
    allocation: BrowserProfileAllocation,
    *,
    reason: str,
    now: datetime,
    metadata: dict[str, Any],
) -> BrowserProfileAllocation:
    return replace(
        allocation,
        status="lost",
        released_at=now,
        release_reason=reason,
        metadata={
            **dict(allocation.metadata),
            **metadata,
        },
    )


@dataclass(slots=True)
class BrowserProfileAllocationTargetLifecycle:
    pool_store: BrowserProfilePoolStore
    system_config_store: BrowserSystemConfigStore
    target_recycler: BrowserAllocationTargetRecycler | None = None

    def should_recycle_targets(
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
        profile = profile_or_raise(
            {profile.name: profile for profile in system.profiles},
            allocation.profile_name,
        )
        return (
            profile.close_targets_on_expire
            if reason_kind == "expire"
            else profile.close_targets_on_release
        )

    def recycle_target_metadata(
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
