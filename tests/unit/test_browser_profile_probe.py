from __future__ import annotations

import unittest

from crxzipple.modules.browser.application import (
    DefaultBrowserCapabilitiesResolver,
    DefaultBrowserProfileResolver,
)
from crxzipple.modules.browser.domain import (
    BrowserProfileConfig,
    BrowserSystemConfig,
    BrowserValidationError,
)
from crxzipple.modules.browser.infrastructure import BrowserProfileProbeService


class _DummyCdpControl:
    def __init__(self, *, base_url: str = "http://127.0.0.1:18800") -> None:
        self.base_url = base_url

    def _request_cdp_json(self, **kwargs):  # noqa: ANN003, ANN201
        del kwargs
        return (
            {
                "webSocketDebuggerUrl": self.base_url.replace("http://", "ws://")
                + "/devtools/browser/browser-id",
            },
            self.base_url,
        )

    def _list_tab_payloads(self, **kwargs):  # noqa: ANN003, ANN201
        del kwargs
        return (
            {
                "id": "tab-1",
                "type": "page",
                "title": "Example",
                "url": "https://example.com",
            },
        )

    def _find_matching_managed_process(self, **kwargs):  # noqa: ANN003, ANN201
        del kwargs
        return None

    def _find_process_for_cdp_port(self, **kwargs):  # noqa: ANN003, ANN201
        del kwargs
        return None

    def _try_resolve_user_data_dir(self, **kwargs):  # noqa: ANN003, ANN201
        del kwargs
        return "/tmp/crxzipple-profile"


class _ConflictingCdpControl(_DummyCdpControl):
    def _find_process_for_cdp_port(self, **kwargs):  # noqa: ANN003, ANN201
        del kwargs
        return {
            "pid": 4242,
            "command": (
                "/Applications/Google Chrome "
                "--remote-debugging-port=18800 "
                "--user-data-dir=/tmp/other-profile"
            ),
            "headless": False,
        }


class _FailingCdpControl:
    def __init__(self, message: str) -> None:
        self._message = message

    def _request_cdp_json(self, **kwargs):  # noqa: ANN003, ANN201
        del kwargs
        raise BrowserValidationError(self._message)

    def _list_tab_payloads(self, **kwargs):  # noqa: ANN003, ANN201
        del kwargs
        return ()

    def _resolve_executable_path(self, **kwargs):  # noqa: ANN003, ANN201
        del kwargs
        raise BrowserValidationError("No browser executable found.")

    def _find_matching_managed_process(self, **kwargs):  # noqa: ANN003, ANN201
        del kwargs
        return None

    def _find_process_for_cdp_port(self, **kwargs):  # noqa: ANN003, ANN201
        del kwargs
        return None

    def _try_resolve_user_data_dir(self, **kwargs):  # noqa: ANN003, ANN201
        del kwargs
        return None


class BrowserProfileProbeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.system = BrowserSystemConfig(
            default_profile="user",
            profiles=(
                BrowserProfileConfig(
                    name="user",
                    driver="existing-session",
                    user_data_dir="/tmp/browser-user",
                ),
            ),
        )
        self.profile = DefaultBrowserProfileResolver().resolve(
            system=self.system,
            profile_name="user",
        )
        self.capabilities = DefaultBrowserCapabilitiesResolver().resolve(profile=self.profile)
        self.managed_system = BrowserSystemConfig(
            default_profile="crxzipple",
            profiles=(BrowserProfileConfig(name="crxzipple"),),
            cdp_port_range_start=18800,
            cdp_port_range_end=18832,
        )
        self.managed_profile = DefaultBrowserProfileResolver().resolve(
            system=self.managed_system,
            profile_name="crxzipple",
        )
        self.managed_capabilities = DefaultBrowserCapabilitiesResolver().resolve(
            profile=self.managed_profile,
        )

    def test_existing_session_probe_reports_reachable_cdp(self) -> None:
        service = BrowserProfileProbeService(
            cdp_control=_DummyCdpControl(),  # type: ignore[arg-type]
        )

        payload = service.probe(
            system=self.system,
            profile=self.profile,
            capabilities=self.capabilities,
            runtime_state=None,
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "cdp-reachable")
        self.assertEqual(payload["tab_count"], 1)

    def test_existing_session_probe_reports_unreachable_cdp(self) -> None:
        service = BrowserProfileProbeService(
            cdp_control=_FailingCdpControl("CDP endpoint did not respond."),  # type: ignore[arg-type]
        )

        payload = service.probe(
            system=self.system,
            profile=self.profile,
            capabilities=self.capabilities,
            runtime_state=None,
        )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "cdp-unreachable")
        self.assertIn("CDP endpoint did not respond", payload["message"])

    def test_managed_profile_probe_reports_launchable_when_cdp_is_down(self) -> None:
        service = BrowserProfileProbeService(
            cdp_control=_FailingCdpControl("CDP endpoint did not respond."),  # type: ignore[arg-type]
        )

        payload = service.probe(
            system=self.managed_system,
            profile=self.managed_profile,
            capabilities=self.managed_capabilities,
            runtime_state=None,
        )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "unlaunchable")
        self.assertIn("No browser executable found", payload["message"])

    def test_cdp_probe_reports_when_playwright_attach_fails(self) -> None:
        service = BrowserProfileProbeService(
            cdp_control=_DummyCdpControl(),  # type: ignore[arg-type]
            playwright_probe=lambda **kwargs: (_ for _ in ()).throw(
                BrowserValidationError("Playwright could not connect over CDP to 'http://127.0.0.1:18800'"),
            ),
        )

        payload = service.probe(
            system=self.managed_system,
            profile=self.managed_profile,
            capabilities=self.managed_capabilities,
            runtime_state=None,
        )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "cdp-playwright-unreachable")
        self.assertIn("Retry or reset this managed profile", payload["message"])
        self.assertIn("Playwright could not connect over CDP", payload["raw_message"])

    def test_managed_profile_probe_reports_cdp_profile_mismatch(self) -> None:
        service = BrowserProfileProbeService(
            cdp_control=_ConflictingCdpControl(),  # type: ignore[arg-type]
        )

        payload = service.probe(
            system=self.managed_system,
            profile=self.managed_profile,
            capabilities=self.managed_capabilities,
            runtime_state=None,
        )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "cdp-profile-mismatch")
        self.assertEqual(payload["conflict_pid"], 4242)
        self.assertIn("user_data_dir", payload["mismatch_fields"])
