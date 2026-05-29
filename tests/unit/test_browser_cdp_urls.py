from __future__ import annotations

import unittest

from crxzipple.modules.browser.infrastructure.cdp_urls import (
    browser_ref_to_cdp_http_base,
    build_cdp_json_new_endpoint,
    candidate_cdp_http_bases,
    normalize_cdp_http_base,
    normalize_cdp_ws_url,
)


class BrowserCdpUrlHelpersTestCase(unittest.TestCase):
    def test_normalize_cdp_http_base_strips_trailing_slash(self) -> None:
        self.assertEqual(
            normalize_cdp_http_base("http://127.0.0.1:18800/"),
            "http://127.0.0.1:18800",
        )

    def test_browser_ref_to_cdp_http_base_converts_websocket_scheme(self) -> None:
        self.assertEqual(
            browser_ref_to_cdp_http_base("ws://localhost:18800/devtools/browser/abc"),
            "http://localhost:18800",
        )
        self.assertEqual(
            browser_ref_to_cdp_http_base("wss://browser.example/devtools/browser/abc"),
            "https://browser.example",
        )

    def test_candidate_cdp_http_bases_prefers_cached_base_and_adds_loopback_fallbacks(self) -> None:
        self.assertEqual(
            candidate_cdp_http_bases(
                "http://127.0.0.1:18800",
                cached_base_url="http://localhost:18800",
            ),
            (
                "http://localhost:18800",
                "http://127.0.0.1:18800",
            ),
        )

    def test_candidate_cdp_http_bases_allows_runtime_only_endpoint_candidates(self) -> None:
        self.assertEqual(
            candidate_cdp_http_bases(
                None,
                cached_base_url="http://127.0.0.1:18800",
                browser_ref="ws://localhost:18801/devtools/browser/abc",
            ),
            (
                "http://127.0.0.1:18800",
                "http://localhost:18801",
            ),
        )

    def test_normalize_cdp_ws_url_uses_cdp_base_host(self) -> None:
        self.assertEqual(
            normalize_cdp_ws_url(
                "ws://127.0.0.1:18800/devtools/page/tab-1",
                "http://localhost:18800",
            ),
            "ws://localhost:18800/devtools/page/tab-1",
        )

    def test_build_cdp_json_new_endpoint_preserves_nested_query_string(self) -> None:
        self.assertEqual(
            build_cdp_json_new_endpoint(
                "http://127.0.0.1:18800",
                "https://www.google.com/search?q=",
            ),
            "http://127.0.0.1:18800/json/new?https://www.google.com/search%3Fq%3D",
        )


if __name__ == "__main__":
    unittest.main()
