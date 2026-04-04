from __future__ import annotations

from types import SimpleNamespace
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
    pass


class _FailingMcpPool:
    def __init__(self, message: str) -> None:
        self._message = message

    def list_tabs(self, **kwargs):  # noqa: ANN003, ANN201
        del kwargs
        raise BrowserValidationError(self._message)

    def get_pid(self, **kwargs):  # noqa: ANN003, ANN201
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

    def test_mcp_probe_classifies_missing_command(self) -> None:
        service = BrowserProfileProbeService(
            cdp_control=_DummyCdpControl(),  # type: ignore[arg-type]
            mcp_pool=_FailingMcpPool(
                "Chrome MCP for profile 'user' could not start command ('npx',): [Errno 2] No such file or directory: 'npx'",
            ),  # type: ignore[arg-type]
        )

        payload = service.probe(
            system=self.system,
            profile=self.profile,
            capabilities=self.capabilities,
            runtime_state=None,
        )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "mcp-command-unavailable")
        self.assertIn("Install Node.js/NPX", payload["message"])
        self.assertIn("could not start command", payload["raw_message"])

    def test_mcp_probe_classifies_browser_not_running(self) -> None:
        service = BrowserProfileProbeService(
            cdp_control=_DummyCdpControl(),  # type: ignore[arg-type]
            mcp_pool=_FailingMcpPool(
                "Chrome MCP for profile 'user' timed out while waiting for 'initialize'.",
            ),  # type: ignore[arg-type]
        )

        payload = service.probe(
            system=self.system,
            profile=self.profile,
            capabilities=self.capabilities,
            runtime_state=None,
        )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "awaiting-existing-browser")
        self.assertIn("could not attach", payload["message"])

    def test_mcp_probe_classifies_incompatible_command(self) -> None:
        service = BrowserProfileProbeService(
            cdp_control=_DummyCdpControl(),  # type: ignore[arg-type]
            mcp_pool=_FailingMcpPool(
                "Chrome MCP for profile 'user' did not expose list_pages.",
            ),  # type: ignore[arg-type]
        )

        payload = service.probe(
            system=self.system,
            profile=self.profile,
            capabilities=self.capabilities,
            runtime_state=None,
        )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "mcp-incompatible")
        self.assertIn("did not expose the expected browser tools", payload["message"])

