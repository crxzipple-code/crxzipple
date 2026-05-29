from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from crxzipple.modules.browser.application import BrowserProfilePoolService
from crxzipple.modules.browser.domain import (
    BrowserProfileConfig,
    BrowserProfilePool,
    BrowserSystemConfig,
    BrowserValidationError,
)
from crxzipple.modules.browser.infrastructure import (
    FileBackedBrowserProfilePoolStore,
    InMemoryBrowserProfilePoolStore,
    InMemoryBrowserSystemConfigStore,
)


class BrowserProfilePoolTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []
        self.system_store = InMemoryBrowserSystemConfigStore(
            BrowserSystemConfig(
                default_profile="crxzipple",
                profiles=(
                    BrowserProfileConfig(name="crxzipple"),
                    BrowserProfileConfig(name="crawler-a"),
                    BrowserProfileConfig(name="user", driver="existing-session"),
                ),
            )
        )
        self.pool_store = InMemoryBrowserProfilePoolStore()
        self.service = BrowserProfilePoolService(
            pool_store=self.pool_store,
            system_config_store=self.system_store,
            event_emitter=lambda event_name, payload: self.events.append(
                (event_name, payload)
            ),
        )

    def test_profile_pool_normalizes_values(self) -> None:
        pool = BrowserProfilePool(
            pool_id=" Collection ",
            display_name="  Collection Pool  ",
            profile_names=(" CRXZipple ", "crxzipple", "crawler-a"),
            target_hosts=("Example.COM", " example.com ", "ctrip.com"),
            selection_strategy="ROUND_ROBIN",
        )

        self.assertEqual(pool.pool_id, "collection")
        self.assertEqual(pool.display_name, "Collection Pool")
        self.assertEqual(pool.profile_names, ("crxzipple", "crawler-a"))
        self.assertEqual(pool.target_hosts, ("example.com", "ctrip.com"))
        self.assertEqual(pool.selection_strategy, "round_robin")

    def test_service_creates_updates_and_deletes_pool(self) -> None:
        created = self.service.create_pool(
            pool_id="collection",
            profile_names=("crxzipple", "crawler-a"),
            target_hosts=("ctrip.com",),
            max_concurrency_per_profile=2,
        )

        self.assertEqual(created.pool_id, "collection")
        self.assertEqual(created.profile_names, ("crxzipple", "crawler-a"))
        self.assertEqual(created.target_hosts, ("ctrip.com",))
        self.assertEqual(self.events[-1][0], "browser.pool.created")

        updated = self.service.update_pool(
            pool_id="collection",
            enabled=False,
            selection_strategy="round_robin",
            max_concurrency_total=3,
        )

        self.assertFalse(updated.enabled)
        self.assertEqual(updated.selection_strategy, "round_robin")
        self.assertEqual(updated.max_concurrency_total, 3)
        self.assertEqual(self.events[-2][0], "browser.pool.updated")
        self.assertEqual(self.events[-1][0], "browser.pool.disabled")

        self.service.delete_pool(pool_id="collection")

        self.assertEqual(self.events[-1][0], "browser.pool.deleted")
        with self.assertRaises(BrowserValidationError):
            self.service.get_pool(pool_id="collection")

    def test_service_rejects_unknown_and_attach_only_profiles_by_default(self) -> None:
        with self.assertRaisesRegex(BrowserValidationError, "unknown profiles"):
            self.service.create_pool(
                pool_id="missing",
                profile_names=("missing",),
            )

        with self.assertRaisesRegex(BrowserValidationError, "attach-only"):
            self.service.create_pool(
                pool_id="personal",
                profile_names=("user",),
            )

        pool = self.service.create_pool(
            pool_id="personal",
            profile_names=("user",),
            allow_attach_only=True,
        )
        self.assertEqual(pool.profile_names, ("user",))
        self.assertTrue(pool.allow_attach_only)

    def test_file_backed_pool_store_persists_pools(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store = FileBackedBrowserProfilePoolStore(Path(tempdir) / "pools")
            store.save_pool(
                BrowserProfilePool(
                    pool_id="collection",
                    profile_names=("crxzipple",),
                    target_hosts=("ctrip.com",),
                    metadata={"purpose": "fare-watch"},
                )
            )

            loaded = FileBackedBrowserProfilePoolStore(
                Path(tempdir) / "pools"
            ).get_pool(pool_id="collection")

            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.pool_id, "collection")
            self.assertEqual(loaded.profile_names, ("crxzipple",))
            self.assertEqual(loaded.target_hosts, ("ctrip.com",))
            self.assertEqual(loaded.metadata["purpose"], "fare-watch")
