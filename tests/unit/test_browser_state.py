from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from crxzipple.modules.browser.domain import (
    BrowserProfileConfig,
    BrowserProfileRuntimeState,
    BrowserStoredRef,
    BrowserSystemConfig,
)
from crxzipple.modules.browser.infrastructure import (
    FileBackedBrowserRefStore,
    FileBackedBrowserRuntimeStateStore,
    FileBackedBrowserSystemConfigStore,
    initialize_browser_state_root,
)


class BrowserStateTestCase(unittest.TestCase):
    def test_initialize_browser_state_root_builds_clean_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = initialize_browser_state_root(
                tempdir,
                system_config=BrowserSystemConfig(
                    default_profile="crxzipple",
                    profiles=(
                        BrowserProfileConfig(name="crxzipple"),
                        BrowserProfileConfig(name="user", driver="existing-session"),
                    ),
                ),
            )

            self.assertTrue((root.root_dir / "layout.json").is_file())
            self.assertTrue((root.config_dir / "system.json").is_file())
            self.assertTrue(root.pools_dir.is_dir())
            self.assertTrue(root.allocations_dir.is_dir())
            self.assertTrue((root.profiles_dir / "crxzipple" / "profile.json").is_file())
            self.assertTrue((root.profiles_dir / "crxzipple" / "userdata").is_dir())
            self.assertTrue((root.profiles_dir / "user" / "profile.json").is_file())
            payload = json.loads((root.config_dir / "system.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["default_profile"], "crxzipple")
            self.assertEqual([item["name"] for item in payload["profiles"]], ["crxzipple", "user"])
            crxzipple_profile = payload["profiles"][0]
            self.assertIsNone(crxzipple_profile["profile_directory"])
            self.assertTrue(crxzipple_profile["autostart"])
            self.assertEqual(crxzipple_profile["proxy_mode"], "none")
            self.assertEqual(crxzipple_profile["proxy_bypass_list"], [])
            self.assertNotIn("mcp_command", payload)
            self.assertNotIn("mcp_timeout_seconds", payload)
            self.assertIsNone(payload["managed_tab_limit"])

    def test_file_backed_runtime_state_store_persists_state(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store = FileBackedBrowserRuntimeStateStore(Path(tempdir) / "runtime")
            state = BrowserProfileRuntimeState(profile_name="crxzipple")
            state.mark_attached(browser_ref="cdp:crxzipple", running_pid=123)
            state.remember_target("tab-1")
            state.metadata["active_target_id"] = "tab-1"

            store.save(state)
            loaded = store.get(profile_name="crxzipple")

            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.profile_name, "crxzipple")
            self.assertEqual(loaded.attachment_status, "attached")
            self.assertEqual(loaded.browser_ref, "cdp:crxzipple")
            self.assertEqual(loaded.running_pid, 123)
            self.assertEqual(loaded.last_target_id, "tab-1")
            self.assertEqual(loaded.metadata["active_target_id"], "tab-1")

    def test_file_backed_system_config_store_reads_disk_as_source_of_truth(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = initialize_browser_state_root(
                tempdir,
                system_config=BrowserSystemConfig(
                    default_profile="crxzipple",
                    profiles=(
                        BrowserProfileConfig(name="crxzipple"),
                        BrowserProfileConfig(name="user", driver="existing-session"),
                ),
                    managed_tab_limit=3,
                    cdp_port_range_start=18800,
                    cdp_port_range_end=18832,
                ),
            )

            system_payload = json.loads(
                (root.config_dir / "system.json").read_text(encoding="utf-8")
            )
            system_payload["default_profile"] = "work"
            system_payload["profiles"].append(
                {
                    "name": "work",
                    "driver": "managed",
                    "cdp_url": "http://browser.example:9555",
                    "cdp_port": 9555,
                    "user_data_dir": None,
                    "profile_directory": "Profile 1",
                    "attach_only": False,
                    "autostart": True,
                    "proxy_mode": "static",
                    "proxy_server": "socks5://127.0.0.1:7890",
                    "proxy_bypass_list": ["127.0.0.1", "localhost"],
                    "proxy_binding_id": None,
                }
            )
            (root.config_dir / "system.json").write_text(
                json.dumps(system_payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )

            store = FileBackedBrowserSystemConfigStore(root.root_dir)
            loaded = store.load()

            self.assertEqual(loaded.default_profile, "work")
            self.assertEqual(
                [profile.name for profile in loaded.profiles],
                ["crxzipple", "user", "work"],
            )
            self.assertEqual(loaded.profiles[-1].cdp_url, "http://browser.example:9555")
            self.assertEqual(loaded.profiles[-1].profile_directory, "Profile 1")
            self.assertEqual(loaded.profiles[-1].proxy_mode, "static")
            self.assertEqual(loaded.profiles[-1].proxy_server, "socks5://127.0.0.1:7890")
            self.assertEqual(
                loaded.profiles[-1].proxy_bypass_list,
                ("127.0.0.1", "localhost"),
            )
            self.assertEqual(loaded.managed_tab_limit, 3)
            self.assertTrue((root.profiles_dir / "work" / "profile.json").is_file())
            self.assertTrue((root.profiles_dir / "work" / "userdata").is_dir())

    def test_file_backed_ref_store_persists_frame_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store = FileBackedBrowserRefStore(Path(tempdir) / "refs")
            refs = (
                BrowserStoredRef(
                    ref="r1",
                    selector="#submit",
                    scope_selector="#panel-a",
                    generation=1,
                    snapshot_format="interactive",
                    frame_path=(),
                    label="Submit",
                ),
                BrowserStoredRef(
                    ref="r2",
                    role="button",
                    nth=1,
                    generation=2,
                    snapshot_format="interactive",
                    frame_path=(0, 1),
                    label="Confirm",
                ),
            )

            store.save_tab_refs(
                profile_name="crxzipple",
                target_id="tab-1",
                refs=refs,
            )
            loaded = store.get_tab_refs(
                profile_name="crxzipple",
                target_id="tab-1",
            )

            self.assertEqual(loaded, refs)
            self.assertEqual(loaded[0].scope_selector, "#panel-a")
