from __future__ import annotations

import unittest
from unittest.mock import patch

from crxzipple.modules.browser.interfaces.http_profile_egress import (
    _test_static_proxy_egress,
)


class BrowserHttpProfileEgressTestCase(unittest.TestCase):
    def test_static_proxy_egress_failure_is_display_safe(self) -> None:
        class _FailingSession:
            def __init__(self) -> None:
                self.trust_env = True

            def get(self, url, *, proxies, timeout):  # noqa: ANN001
                del url, proxies, timeout
                raise RuntimeError(
                    "proxy egress failed at "
                    "https://example.com/ip?token=secret-token#frag "
                    "Authorization: Bearer secret-token"
                )

            def close(self) -> None:
                return None

        with patch(
            "crxzipple.modules.browser.interfaces.http_profile_egress.requests.Session",
            _FailingSession,
        ):
            result = _test_static_proxy_egress(
                proxy_server="socks5://127.0.0.1:7890",
                url="https://example.com/ip?token=secret-token#frag",
                timeout_s=1.0,
            )

        result_text = str(result)
        self.assertEqual(result["status"], "failed")
        self.assertIn("https://example.com/ip?[redacted]", result_text)
        self.assertIn("Authorization: [redacted]", result_text)
        self.assertNotIn("secret-token", result_text)
        self.assertNotIn("#frag", result_text)


if __name__ == "__main__":
    unittest.main()
