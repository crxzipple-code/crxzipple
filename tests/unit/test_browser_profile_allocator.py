from __future__ import annotations

from datetime import datetime, timedelta, timezone
import tempfile
import unittest
from pathlib import Path

from crxzipple.modules.browser.application import (
    BrowserProfileAdminService,
    BrowserProfileAllocatorService,
    BrowserProfilePoolService,
    BrowserProfileQueryService,
    DefaultBrowserCapabilitiesResolver,
    DefaultBrowserProfileResolver,
)
from crxzipple.modules.browser.domain import (
    BrowserProfileAllocation,
    BrowserProfileConfig,
    BrowserProfileRuntimeState,
    BrowserSystemConfig,
    BrowserValidationError,
)
from crxzipple.modules.browser.infrastructure import (
    FileBackedBrowserProfileAllocationStore,
    InMemoryBrowserProfileAllocationStore,
    InMemoryBrowserProfilePoolStore,
    InMemoryBrowserRefStore,
    InMemoryBrowserRuntimeStateStore,
    InMemoryBrowserSystemConfigStore,
)


NOW = datetime(2026, 5, 26, 8, 0, 0, tzinfo=timezone.utc)


class BrowserProfileAllocatorTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.events: list[str] = []
        self.system_store = InMemoryBrowserSystemConfigStore(
            BrowserSystemConfig(
                default_profile="crxzipple",
                profiles=(
                    BrowserProfileConfig(name="crxzipple"),
                    BrowserProfileConfig(name="crawler-a"),
                    BrowserProfileConfig(name="crawler-b"),
                    BrowserProfileConfig(name="user", driver="existing-session"),
                ),
            )
        )
        self.pool_store = InMemoryBrowserProfilePoolStore()
        self.allocation_store = InMemoryBrowserProfileAllocationStore()
        self.runtime_store = InMemoryBrowserRuntimeStateStore()
        self.pool_service = BrowserProfilePoolService(
            pool_store=self.pool_store,
            system_config_store=self.system_store,
            allocation_store=self.allocation_store,
        )
        self.allocator = BrowserProfileAllocatorService(
            allocation_store=self.allocation_store,
            pool_store=self.pool_store,
            system_config_store=self.system_store,
            runtime_state_store=self.runtime_store,
            event_emitter=lambda name, payload: self.events.append(name),
        )

    def test_allocator_reuses_sticky_consumer_allocation(self) -> None:
        self.pool_service.create_pool(
            pool_id="collection",
            profile_names=("crawler-a", "crawler-b"),
            allocation_ttl_seconds=60,
        )

        first = self.allocator.allocate(
            pool_id="collection",
            consumer_kind="tool_run",
            consumer_id="tool-1",
            target_host="ctrip.com",
            now=NOW,
        )
        second = self.allocator.allocate(
            pool_id="collection",
            consumer_kind="tool_run",
            consumer_id="tool-1",
            target_host="ctrip.com",
            now=NOW + timedelta(seconds=1),
        )

        self.assertEqual(first.allocation_id, second.allocation_id)
        self.assertEqual(first.profile_name, "crawler-a")
        self.assertEqual(self.events, ["browser.allocation.acquired"])

    def test_allocator_honors_least_busy_concurrency_and_release(self) -> None:
        self.pool_service.create_pool(
            pool_id="collection",
            profile_names=("crawler-a", "crawler-b"),
            max_concurrency_per_profile=1,
            max_concurrency_total=2,
        )

        first = self.allocator.allocate(
            pool_id="collection",
            consumer_kind="tool_run",
            consumer_id="tool-1",
            now=NOW,
        )
        second = self.allocator.allocate(
            pool_id="collection",
            consumer_kind="tool_run",
            consumer_id="tool-2",
            now=NOW,
        )

        self.assertEqual(first.profile_name, "crawler-a")
        self.assertEqual(second.profile_name, "crawler-b")
        with self.assertRaisesRegex(BrowserValidationError, "max concurrency"):
            self.allocator.allocate(
                pool_id="collection",
                consumer_kind="tool_run",
                consumer_id="tool-3",
                now=NOW,
            )

        released = self.allocator.release_allocation(
            allocation_id=first.allocation_id,
            reason="done",
            now=NOW + timedelta(seconds=5),
        )
        self.assertEqual(released.status, "released")
        self.assertEqual(released.release_reason, "done")

    def test_allocator_expires_allocations_and_applies_failure_cooldown(self) -> None:
        self.pool_service.create_pool(
            pool_id="collection",
            profile_names=("crawler-a", "crawler-b"),
            allocation_ttl_seconds=10,
            failure_cooldown_seconds=60,
        )
        first = self.allocator.allocate(
            pool_id="collection",
            consumer_kind="tool_run",
            consumer_id="tool-1",
            now=NOW,
        )
        self.allocator.fail_allocation(
            allocation_id=first.allocation_id,
            reason="proxy_failed",
            now=NOW + timedelta(seconds=2),
        )

        second = self.allocator.allocate(
            pool_id="collection",
            consumer_kind="tool_run",
            consumer_id="tool-2",
            now=NOW + timedelta(seconds=3),
        )
        self.assertEqual(second.profile_name, "crawler-b")

        expired = self.allocator.expire_allocations(
            now=NOW + timedelta(seconds=20),
        )
        self.assertEqual([item.allocation_id for item in expired], [second.allocation_id])
        self.assertEqual(expired[0].status, "expired")

    def test_allocator_tracks_owned_targets_and_recycles_on_release(self) -> None:
        class _Recycler:
            def __init__(self) -> None:
                self.closed: list[tuple[str, str]] = []

            def close_owned_target(self, *, profile_name: str, target_id: str) -> None:
                self.closed.append((profile_name, target_id))

        recycler = _Recycler()
        current_time = datetime.now(timezone.utc)
        allocator = BrowserProfileAllocatorService(
            allocation_store=self.allocation_store,
            pool_store=self.pool_store,
            system_config_store=self.system_store,
            runtime_state_store=self.runtime_store,
            target_recycler=recycler,
        )
        current_time = datetime.now(timezone.utc)
        allocation = allocator.allocate(
            profile_name="crawler-a",
            consumer_kind="manual",
            consumer_id="manual-1",
            now=current_time,
        )

        allocator.remember_allocation_target(
            allocation_id=allocation.allocation_id,
            target_id="tab-1",
        )
        tracked = allocator.remember_allocation_target(
            allocation_id=allocation.allocation_id,
            target_id="tab-1",
        )
        self.assertEqual(tracked.owned_target_ids, ("tab-1",))

        released = allocator.release_allocation(
            allocation_id=allocation.allocation_id,
            reason="done",
            now=current_time + timedelta(seconds=5),
        )

        self.assertEqual(released.status, "released")
        self.assertEqual(recycler.closed, [("crawler-a", "tab-1")])
        self.assertEqual(
            released.metadata["target_recycle"]["closed_target_ids"],
            ["tab-1"],
        )

    def test_allocator_honors_profile_target_cleanup_policy(self) -> None:
        class _Recycler:
            def __init__(self) -> None:
                self.closed: list[tuple[str, str]] = []

            def close_owned_target(self, *, profile_name: str, target_id: str) -> None:
                self.closed.append((profile_name, target_id))

        self.system_store.save(
            BrowserSystemConfig(
                default_profile="crxzipple",
                profiles=(
                    BrowserProfileConfig(name="crxzipple"),
                    BrowserProfileConfig(
                        name="crawler-a",
                        close_targets_on_release=False,
                    ),
                ),
            )
        )
        recycler = _Recycler()
        current_time = datetime.now(timezone.utc)
        allocator = BrowserProfileAllocatorService(
            allocation_store=self.allocation_store,
            pool_store=self.pool_store,
            system_config_store=self.system_store,
            runtime_state_store=self.runtime_store,
            target_recycler=recycler,
        )
        allocation = allocator.allocate(
            profile_name="crawler-a",
            consumer_kind="manual",
            consumer_id="manual-1",
            now=current_time,
        )
        allocator.remember_allocation_target(
            allocation_id=allocation.allocation_id,
            target_id="tab-1",
        )

        released = allocator.release_allocation(
            allocation_id=allocation.allocation_id,
            reason="done",
            now=current_time + timedelta(seconds=5),
        )

        self.assertEqual(released.status, "released")
        self.assertEqual(recycler.closed, [])
        self.assertNotIn("target_recycle", released.metadata)

    def test_allocator_honors_pool_target_cleanup_policy_on_expiry(self) -> None:
        class _Recycler:
            def __init__(self) -> None:
                self.closed: list[tuple[str, str]] = []

            def close_owned_target(self, *, profile_name: str, target_id: str) -> None:
                self.closed.append((profile_name, target_id))

        self.pool_service.create_pool(
            pool_id="collection",
            profile_names=("crawler-a",),
            allocation_ttl_seconds=10,
            close_targets_on_expire=False,
        )
        recycler = _Recycler()
        current_time = datetime.now(timezone.utc)
        allocator = BrowserProfileAllocatorService(
            allocation_store=self.allocation_store,
            pool_store=self.pool_store,
            system_config_store=self.system_store,
            runtime_state_store=self.runtime_store,
            target_recycler=recycler,
        )
        allocation = allocator.allocate(
            pool_id="collection",
            consumer_kind="tool_run",
            consumer_id="tool-1",
            now=current_time,
        )
        allocator.remember_allocation_target(
            allocation_id=allocation.allocation_id,
            target_id="tab-1",
        )

        expired = allocator.expire_allocations(now=current_time + timedelta(seconds=20))

        self.assertEqual([item.allocation_id for item in expired], [allocation.allocation_id])
        self.assertEqual(recycler.closed, [])
        self.assertNotIn("target_recycle", expired[0].metadata)

    def test_allocator_heartbeats_allocation_and_extends_ttl(self) -> None:
        current_time = datetime.now(timezone.utc)
        allocation = self.allocator.allocate(
            profile_name="crawler-a",
            consumer_kind="manual",
            consumer_id="heartbeat",
            now=current_time,
        )

        heartbeated = self.allocator.heartbeat_allocation(
            allocation_id=allocation.allocation_id,
            ttl_seconds=120,
            now=current_time + timedelta(seconds=5),
        )

        self.assertEqual(heartbeated.status, "active")
        self.assertEqual(
            heartbeated.last_heartbeat_at,
            current_time + timedelta(seconds=5),
        )
        self.assertEqual(
            heartbeated.expires_at,
            current_time + timedelta(seconds=125),
        )
        self.assertIn("browser.allocation.heartbeated", self.events)

    def test_allocator_reconcile_marks_allocation_lost_when_targets_disappear(self) -> None:
        current_time = datetime.now(timezone.utc)

        class _Inspector:
            def list_target_ids(self, *, profile_name: str) -> tuple[str, ...]:
                self.profile_name = profile_name
                return ()

        inspector = _Inspector()
        allocator = BrowserProfileAllocatorService(
            allocation_store=self.allocation_store,
            pool_store=self.pool_store,
            system_config_store=self.system_store,
            runtime_state_store=self.runtime_store,
            target_inspector=inspector,
            event_emitter=lambda name, payload: self.events.append(name),
        )
        allocation = allocator.allocate(
            profile_name="crawler-a",
            consumer_kind="manual",
            consumer_id="reconcile",
            now=current_time,
        )
        allocator.remember_allocation_target(
            allocation_id=allocation.allocation_id,
            target_id="tab-1",
        )

        reconciled = allocator.reconcile_allocation(
            allocation_id=allocation.allocation_id,
            now=current_time + timedelta(seconds=10),
        )

        self.assertEqual(inspector.profile_name, "crawler-a")
        self.assertEqual(reconciled.status, "lost")
        self.assertEqual(reconciled.release_reason, "target_lost")
        self.assertEqual(
            reconciled.metadata["target_reconcile"]["missing_target_ids"],
            ["tab-1"],
        )
        self.assertIn("browser.allocation.lost", self.events)

    def test_query_projects_pool_failure_cooldown_summary(self) -> None:
        now = datetime.now(timezone.utc) - timedelta(seconds=3)
        self.pool_service.create_pool(
            pool_id="collection",
            profile_names=("crawler-a", "crawler-b"),
            allocation_ttl_seconds=10,
            failure_cooldown_seconds=60,
        )
        first = self.allocator.allocate(
            pool_id="collection",
            consumer_kind="tool_run",
            consumer_id="tool-1",
            now=now,
        )
        self.allocator.fail_allocation(
            allocation_id=first.allocation_id,
            reason="proxy_failed",
            now=now + timedelta(seconds=2),
        )
        query = BrowserProfileQueryService(
            system_config_store=self.system_store,
            runtime_state_store=self.runtime_store,
            profile_resolver=DefaultBrowserProfileResolver(),
            capabilities_resolver=DefaultBrowserCapabilitiesResolver(),
            profile_pool_store=self.pool_store,
            profile_allocation_store=self.allocation_store,
        )

        pool = query.list_pools()[0]

        self.assertEqual(pool.pool_id, "collection")
        self.assertEqual(pool.diagnostics["cooling_profiles"], ("crawler-a",))
        self.assertEqual(
            pool.diagnostics["failure_cooldown_profiles"],
            ("crawler-a",),
        )
        self.assertEqual(pool.diagnostics["failed_allocation_count"], 1)
        self.assertEqual(pool.diagnostics["available_profile_count"], 1)

    def test_allocator_round_robin_and_manual_only(self) -> None:
        self.pool_service.create_pool(
            pool_id="round",
            profile_names=("crawler-a", "crawler-b"),
            selection_strategy="round_robin",
        )
        first = self.allocator.allocate(
            pool_id="round",
            consumer_kind="manual",
            consumer_id="one",
            now=NOW,
        )
        self.allocator.release_allocation(
            allocation_id=first.allocation_id,
            now=NOW + timedelta(seconds=1),
        )
        second = self.allocator.allocate(
            pool_id="round",
            consumer_kind="manual",
            consumer_id="two",
            now=NOW + timedelta(seconds=2),
        )
        self.assertEqual((first.profile_name, second.profile_name), ("crawler-a", "crawler-b"))

        self.pool_service.create_pool(
            pool_id="manual",
            profile_names=("crawler-a",),
            selection_strategy="manual_only",
        )
        with self.assertRaisesRegex(BrowserValidationError, "requires an explicit profile"):
            self.allocator.allocate(
                pool_id="manual",
                consumer_kind="manual",
                consumer_id="three",
                now=NOW,
            )
        manual = self.allocator.allocate(
            pool_id="manual",
            profile_name="crawler-a",
            consumer_kind="manual",
            consumer_id="four",
            now=NOW,
        )
        self.assertEqual(manual.profile_name, "crawler-a")

    def test_allocator_skips_blocked_runtime_profiles(self) -> None:
        self.pool_service.create_pool(
            pool_id="collection",
            profile_names=("crawler-a", "crawler-b"),
        )
        state = BrowserProfileRuntimeState(profile_name="crawler-a")
        state.mark_failed("cdp failed")
        self.runtime_store.save(state)

        allocation = self.allocator.allocate(
            pool_id="collection",
            consumer_kind="manual",
            consumer_id="one",
            now=NOW,
        )
        self.assertEqual(allocation.profile_name, "crawler-b")

    def test_file_backed_allocation_store_persists_allocations(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store = FileBackedBrowserProfileAllocationStore(
                Path(tempdir) / "allocations",
            )
            allocation = BrowserProfileAllocation(
                allocation_id="browser_alloc_test",
                pool_id="collection",
                profile_name="crawler-a",
                consumer_kind="tool_run",
                consumer_id="tool-1",
                acquired_at=NOW,
                expires_at=NOW + timedelta(seconds=60),
                owned_target_ids=("tab-1",),
            )

            store.save_allocation(allocation)
            loaded = FileBackedBrowserProfileAllocationStore(
                Path(tempdir) / "allocations",
            ).get_allocation(allocation_id="browser_alloc_test")

            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.allocation_id, "browser_alloc_test")
            self.assertEqual(loaded.profile_name, "crawler-a")
            self.assertEqual(loaded.consumer_kind, "tool_run")
            self.assertEqual(loaded.owned_target_ids, ("tab-1",))

    def test_active_allocations_guard_profile_and_pool_deletes(self) -> None:
        admin = BrowserProfileAdminService(
            system_config_store=self.system_store,
            runtime_state_store=self.runtime_store,
            ref_store=InMemoryBrowserRefStore(),
            allocation_store=self.allocation_store,
        )
        self.pool_service.create_pool(
            pool_id="collection",
            profile_names=("crawler-a",),
        )
        allocation = self.allocator.allocate(
            pool_id="collection",
            consumer_kind="manual",
            consumer_id="one",
            now=NOW,
        )

        with self.assertRaisesRegex(BrowserValidationError, "allocation"):
            self.pool_service.delete_pool(pool_id="collection")
        with self.assertRaisesRegex(BrowserValidationError, "allocation"):
            admin.disable_profile(profile_name="crawler-a")

        self.allocator.release_allocation(
            allocation_id=allocation.allocation_id,
            now=NOW + timedelta(seconds=1),
        )
        self.pool_service.delete_pool(pool_id="collection")
        admin.disable_profile(profile_name="crawler-a")
