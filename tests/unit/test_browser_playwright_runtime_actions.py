from __future__ import annotations

import json
import unittest

from crxzipple.modules.browser.domain import (
    BrowserActionTarget,
    BrowserPageActionCommand,
    BrowserStoredRef,
    BrowserValidationError,
)
from crxzipple.modules.browser.infrastructure.network_insight import (
    BrowserNetworkInsightService,
)
from tests.unit.browser_playwright_action_support import BrowserPlaywrightActionEngineTestCase


class BrowserPlaywrightRuntimeActionsTestCase(BrowserPlaywrightActionEngineTestCase):
    def test_upload_uses_locator_set_input_files(self) -> None:
        upload_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="upload",
            target=BrowserActionTarget(target_id="tab-1", selector="#file-input"),
            payload={"paths": ["/tmp/one.txt", "/tmp/two.txt"]},
            timeout_ms=2500,
        )

        upload_result = self.engine.execute(
            plan=self._plan(upload_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=upload_command,
        )

        self.assertTrue(upload_result.ok)
        self.assertEqual(upload_result.value["engine"], "cdp-backed-playwright")
        self.assertEqual(
            upload_result.value["result"],
            {
                "kind": "upload",
                "paths": ["/tmp/one.txt", "/tmp/two.txt"],
            },
        )

        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        self.assertIn(
            (
                "set_input_files",
                "#file-input",
                ["/tmp/one.txt", "/tmp/two.txt"],
                {"timeout": 2500.0},
                (),
            ),
            page.operations,
        )

    def test_download_clicks_locator_and_serializes_file(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.queue_download(filename="report.csv", data=b"city,price\nkunming,320\n")
        download_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="download",
            target=BrowserActionTarget(target_id="tab-1", selector="#download"),
            payload={"button": "left"},
            timeout_ms=1800,
        )

        download_result = self.engine.execute(
            plan=self._plan(download_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=download_command,
        )

        self.assertTrue(download_result.ok)
        self.assertEqual(download_result.value["result"]["kind"], "download")
        self.assertEqual(download_result.value["result"]["name"], "report.csv")
        self.assertEqual(download_result.value["result"]["content_type"], "text/csv")
        self.assertIn(("expect_download", {"timeout": 1800.0}), page.operations)
        self.assertIn(("click", "#download", {"timeout": 1800.0, "button": "left"}, ()), page.operations)

    def test_wait_download_waits_for_next_download_event(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.queue_download(filename="invoice.pdf", data=b"%PDF-1.4")
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="wait-download",
            target=BrowserActionTarget(target_id="tab-1"),
            timeout_ms=2200,
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.value["result"]["kind"], "download")
        self.assertEqual(result.value["result"]["name"], "invoice.pdf")
        self.assertEqual(result.value["result"]["content_type"], "application/pdf")
        self.assertIn(("wait_for_event", "download", {"timeout": 2200.0}), page.operations)

    def test_dialog_waits_for_next_dialog_and_accepts_prompt(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.queue_dialog(
            dialog_type="prompt",
            message="Enter destination",
            default_value="Kunming",
        )
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="dialog",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"accept": True, "prompt_text": "Shanghai"},
            timeout_ms=1700,
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.value["result"]["kind"], "dialog")
        self.assertEqual(result.value["result"]["type"], "prompt")
        self.assertEqual(result.value["result"]["message"], "Enter destination")
        self.assertEqual(result.value["result"]["default_value"], "Kunming")
        self.assertEqual(result.value["result"]["handled_as"], "accept")
        self.assertEqual(result.value["result"]["prompt_text"], "Shanghai")
        self.assertIn(("wait_for_event", "dialog", {"timeout": 1700.0}), page.operations)
        self.assertIn(("dialog.accept", "Shanghai"), page.operations)

    def test_console_returns_buffered_messages_and_can_clear(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.emit_console(
            text="Network fallback",
            message_type="warning",
            location={"url": "https://example.com/app.js", "lineNumber": 9, "columnNumber": 2},
        )
        page.emit_console(text="Boot complete", message_type="info")

        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="console",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"level": "warn", "clear": True},
            timeout_ms=1600,
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.value["result"]["kind"], "console")
        self.assertEqual(result.value["result"]["count"], 1)
        self.assertEqual(result.value["result"]["messages"][0]["level"], "warn")
        self.assertEqual(result.value["result"]["messages"][0]["text"], "Network fallback")
        self.assertEqual(
            result.value["result"]["messages"][0]["location"],
            {
                "url": "https://example.com/app.js",
                "line_number": 9,
                "column_number": 2,
            },
        )

        follow_up = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="console",
            target=BrowserActionTarget(target_id="tab-1"),
        )
        follow_up_result = self.engine.execute(
            plan=self._plan(follow_up),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=follow_up,
        )
        self.assertEqual(follow_up_result.value["result"]["count"], 0)

    def test_storage_supports_set_get_and_clear(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")

        set_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="storage",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "storage_kind": "local",
                "storage_operation": "set",
                "storage_key": "theme",
                "storage_value": "dark",
            },
        )
        set_result = self.engine.execute(
            plan=self._plan(set_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=set_command,
        )
        self.assertEqual(set_result.value["result"]["values"], {"theme": "dark"})
        self.assertEqual(page.local_storage, {"theme": "dark"})

        get_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="storage",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "storage_kind": "local",
                "storage_operation": "get",
                "storage_key": "theme",
            },
        )
        get_result = self.engine.execute(
            plan=self._plan(get_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=get_command,
        )
        self.assertEqual(get_result.value["result"]["values"], {"theme": "dark"})

        clear_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="storage",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "storage_kind": "local",
                "storage_operation": "clear",
            },
        )
        clear_result = self.engine.execute(
            plan=self._plan(clear_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=clear_command,
        )
        self.assertEqual(clear_result.value["result"]["values"], {})
        self.assertEqual(page.local_storage, {})

    def test_deep_storage_read_tools_use_cdp_and_page_context(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.indexeddb_databases = {
            "app-db": {
                "version": 2,
                "objectStores": [
                    {
                        "name": "flights",
                        "keyPath": "id",
                        "autoIncrement": False,
                        "indexes": [{"name": "by-city", "keyPath": "city"}],
                    }
                ],
                "entries": {
                    "flights": [
                        {
                            "key": "flight-1",
                            "primaryKey": "flight-1",
                            "value": {
                                "city": "Kunming",
                                "token": "secret-token",
                            },
                        }
                    ]
                },
            }
        }
        page.cache_storage_caches = [
            {
                "cacheId": "cache-1",
                "cacheName": "runtime-cache",
                "securityOrigin": "https://example.com",
            }
        ]
        page.cache_storage_entries = {
            "cache-1": [
                {
                    "requestURL": "https://example.com/api/flights?token=secret",
                    "requestMethod": "GET",
                    "responseStatus": 200,
                    "responseHeaders": [
                        {"name": "content-type", "value": "application/json"},
                        {"name": "set-cookie", "value": "sid=secret"},
                    ],
                }
            ]
        }
        page.cache_storage_responses = {
            ("cache-1", "https://example.com/api/flights?token=secret"): {
                "body": '{"api_key":"secret","ok":true}',
            }
        }
        page.service_worker_registrations = [
            {
                "scope_url": "https://example.com/",
                "active": {
                    "script_url": "https://example.com/sw.js",
                    "state": "activated",
                },
            }
        ]

        indexeddb_list = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="storage-indexeddb-list",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="storage-indexeddb-list",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={},
            ),
        )
        self.assertEqual(indexeddb_list.value["result"]["database_names"], ["app-db"])
        self.assertEqual(
            indexeddb_list.value["result"]["databases"][0]["object_stores"][0]["name"],
            "flights",
        )

        indexeddb_query_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="storage-indexeddb-query",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"database_name": "app-db", "object_store_name": "flights"},
        )
        indexeddb_query = self.engine.execute(
            plan=self._plan(indexeddb_query_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=indexeddb_query_command,
        )
        self.assertEqual(indexeddb_query.value["result"]["entries"][0]["key"], "flight-1")
        self.assertEqual(
            indexeddb_query.value["result"]["entries"][0]["value"]["token"],
            "[redacted]",
        )

        cache_list_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="storage-cache-list",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={},
        )
        cache_list = self.engine.execute(
            plan=self._plan(cache_list_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=cache_list_command,
        )
        self.assertEqual(cache_list.value["result"]["caches"][0]["cache_name"], "runtime-cache")

        cache_get_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="storage-cache-get",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "cache_name": "runtime-cache",
                "request_url": "https://example.com/api/flights?token=secret",
            },
        )
        cache_get = self.engine.execute(
            plan=self._plan(cache_get_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=cache_get_command,
        )
        self.assertIn("%5Bredacted%5D", cache_get.value["result"]["request_url"])
        self.assertEqual(
            cache_get.value["result"]["entries"][0]["response_headers"]["set-cookie"],
            "[redacted]",
        )
        self.assertIn("[redacted]", cache_get.value["result"]["response"]["body"])

        service_worker_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="service-worker-list",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={},
        )
        service_workers = self.engine.execute(
            plan=self._plan(service_worker_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=service_worker_command,
        )
        self.assertEqual(service_workers.value["result"]["count"], 1)
        self.assertEqual(
            service_workers.value["result"]["registrations"][0]["active"]["state"],
            "activated",
        )
        self.assertIn(("cdp.send", "IndexedDB.requestDatabaseNames", {"securityOrigin": "https://example.com"}), page.operations)
        self.assertIn(("cdp.send", "CacheStorage.requestCacheNames", {"securityOrigin": "https://example.com"}), page.operations)

    def test_cookies_supports_set_get_and_clear(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")

        set_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="cookies",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "cookies_operation": "set",
                "cookie": {
                    "name": "session",
                    "value": "abc123",
                    "url": "https://example.com",
                    "httpOnly": True,
                },
            },
        )
        set_result = self.engine.execute(
            plan=self._plan(set_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=set_command,
        )
        self.assertEqual(set_result.value["result"]["count"], 1)
        self.assertEqual(set_result.value["result"]["cookies"][0]["name"], "session")
        self.assertEqual(page.browser_context.cookie_store[0]["value"], "abc123")

        get_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="cookies",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "cookies_operation": "get",
            },
        )
        get_result = self.engine.execute(
            plan=self._plan(get_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=get_command,
        )
        self.assertEqual(get_result.value["result"]["count"], 1)
        self.assertEqual(get_result.value["result"]["cookies"][0]["name"], "session")

        clear_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="cookies",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "cookies_operation": "clear",
            },
        )
        clear_result = self.engine.execute(
            plan=self._plan(clear_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=clear_command,
        )
        self.assertEqual(clear_result.value["result"]["cookies"], [])
        self.assertEqual(page.browser_context.cookie_store, [])

    def test_cdp_raw_sends_command_through_page_cdp_session(self) -> None:
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="cdp-raw",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "method": "Runtime.evaluate",
                "params": {"expression": "1 + 1"},
            },
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        page = self.session_pool.pages["tab-1"]
        self.assertTrue(result.ok)
        self.assertEqual(result.value["result"]["kind"], "cdp-raw")
        self.assertEqual(result.value["result"]["method"], "Runtime.evaluate")
        self.assertEqual(
            result.value["result"]["result"],
            {
                "method": "Runtime.evaluate",
                "params": {"expression": "1 + 1"},
                "targetId": "tab-1",
            },
        )
        self.assertIn(("context.new_cdp_session", "tab-1"), page.operations)
        self.assertIn(
            ("cdp.send", "Runtime.evaluate", {"expression": "1 + 1"}),
            page.operations,
        )
        self.assertIn(("cdp.detach",), page.operations)

    def test_runtime_inspect_returns_page_runtime_facts(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.runtime_globals = {
            "__NEXT_DATA__": {
                "page": "/flight-search",
                "query": {"from": "KMG", "to": "SHA"},
                "props": {"pageProps": {}},
            },
            "appStore": {"state": "ready", "route": "/flights"},
        }
        page.local_storage["token"] = "redacted-in-real-browser"
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="runtime-inspect",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "global_names": ["appStore"],
                "limit": 20,
            },
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        payload = result.value["result"]
        self.assertTrue(result.ok)
        self.assertEqual(payload["kind"], "runtime-inspect")
        self.assertEqual(payload["title"], "Fake Page")
        self.assertEqual(payload["page_state"]["ready_state"], "complete")
        self.assertIn("next", payload["frameworks"]["detected"])
        globals_by_name = {
            item["name"]: item
            for item in payload["globals"]
            if isinstance(item, dict)
        }
        self.assertTrue(globals_by_name["__NEXT_DATA__"]["exists"])
        self.assertTrue(globals_by_name["appStore"]["exists"])
        self.assertEqual(globals_by_name["appStore"]["keys"], ["state", "route"])
        route_hints = payload["route_hints"]
        self.assertIn(
            {
                "source": "appStore",
                "keys": [{"key": "route", "value": "/flights"}],
            },
            route_hints,
        )
        self.assertTrue(
            any(
                item.get("source") == "__NEXT_DATA__"
                and item.get("page") == "/flight-search"
                for item in route_hints
                if isinstance(item, dict)
            )
        )
        self.assertEqual(payload["storage"]["local"]["count"], 1)
        self.assertEqual(payload["performance"]["resource_count"], 1)
        self.assertTrue(
            any(
                operation[0] == "evaluate"
                and "__crxzipple_browser_runtime_inspect__" in str(operation[1])
                for operation in page.operations
            )
        )

    def test_runtime_probe_client_describes_page_client_method(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")

        def get_shopping(payload):  # noqa: ANN001, ANN202
            return payload

        get_shopping._crxzipple_endpoint_hint = "/portal/v3/shopping/briefInfo"  # type: ignore[attr-defined]
        get_shopping._crxzipple_payload_key_candidates = (  # type: ignore[attr-defined]
            "depCityCode",
            "arrCityCode",
            "depDate",
        )
        page.runtime_globals = {
            "$nuxt": {
                "$http": {
                    "shopping": {
                        "getShopping": get_shopping,
                        "getFareDetail": lambda payload: payload,
                    },
                },
            },
        }
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="runtime-probe-client",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "object_path": "$nuxt.$http.shopping",
                "method_name": "getShopping",
                "limit": 10,
            },
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        payload = result.value["result"]
        self.assertTrue(result.ok)
        self.assertEqual(payload["kind"], "runtime-probe-client")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["object_path"], "$nuxt.$http.shopping")
        self.assertIn("getShopping", payload["object"]["keys"])
        self.assertEqual(payload["method"]["path"], "$nuxt.$http.shopping.getShopping")
        self.assertTrue(payload["method"]["callable"])
        self.assertEqual(payload["method"]["arity"], 1)
        self.assertEqual(
            payload["method"]["endpoint_hint"],
            "/portal/v3/shopping/briefInfo",
        )
        self.assertEqual(
            payload["method"]["payload_key_candidates"],
            ["depCityCode", "arrCityCode", "depDate"],
        )

    def test_runtime_probe_client_ranks_relevant_methods_before_noise(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")

        def get_shopping(payload):  # noqa: ANN001, ANN202
            return payload

        noisy_methods = {
            f"utilityMethod{index}": (lambda payload, _index=index: payload)
            for index in range(30)
        }
        noisy_methods["getShopping"] = get_shopping
        noisy_methods["getFareDetail"] = lambda payload: payload
        page.runtime_globals = {
            "$nuxt": {
                "$http": {
                    "shopping": noisy_methods,
                },
            },
        }
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="runtime-probe-client",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "object_path": "$nuxt.$http.shopping",
                "limit": 10,
            },
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        payload = result.value["result"]
        self.assertTrue(result.ok)
        self.assertIn("getShopping", payload["object"]["keys"])
        method_names = [item["name"] for item in payload["object"]["methods"]]
        self.assertIn("getShopping", method_names)
        self.assertIn("getFareDetail", method_names)

    def test_runtime_probe_client_retries_transient_empty_json_failure(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.evaluate_failures.append(
            ValueError("Expecting value: line 1 column 1 (char 0)"),
        )

        def get_shopping(payload):  # noqa: ANN001, ANN202
            return payload

        page.runtime_globals = {
            "$nuxt": {
                "$http": {
                    "shopping": {
                        "getShopping": get_shopping,
                    },
                },
            },
        }
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="runtime-probe-client",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "object_path": "$nuxt.$http.shopping",
                "method_name": "getShopping",
            },
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        payload = result.value["result"]
        self.assertTrue(result.ok)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["method"]["path"], "$nuxt.$http.shopping.getShopping")
        probe_evaluations = [
            operation
            for operation in page.operations
            if operation[0] == "evaluate"
            and "__crxzipple_browser_client_probe__" in str(operation[1])
        ]
        self.assertEqual(len(probe_evaluations), 2)

    def test_runtime_call_client_invokes_page_client_method(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")

        def get_shopping(payload):  # noqa: ANN001, ANN202
            return {
                "resultCode": "000000",
                "data": {
                    "flightItems": [
                        {
                            "flightInfos": [
                                {
                                    "flightNo": "MU5815",
                                    "depTime": "09:00",
                                    "arrTime": "12:10",
                                }
                            ],
                            "flightSort": {"price": 700, "priceWithTax": 760},
                        }
                    ]
                },
                "echo": payload,
            }

        page.runtime_globals = {
            "$nuxt": {
                "$http": {
                    "shopping": {
                        "getShopping": get_shopping,
                    },
                },
            },
        }
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="runtime-call-client",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "object_path": "$nuxt.$http.shopping",
                "method_name": "getShopping",
                "arguments": [
                    {
                        "depCityCode": "KMG",
                        "arrCityCode": "BJS",
                        "depDate": "2026-06-10",
                        "routeType": "OW",
                    }
                ],
            },
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        payload = result.value["result"]
        self.assertTrue(result.ok)
        self.assertEqual(payload["kind"], "runtime-call-client")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["object_path"], "$nuxt.$http.shopping")
        self.assertEqual(payload["method_name"], "getShopping")
        self.assertEqual(payload["argument_count"], 1)
        self.assertEqual(payload["result"]["resultCode"], "000000")
        self.assertEqual(
            payload["result"]["echo"]["depCityCode"],
            "KMG",
        )
        self.assertIn(
            "__crxzipple_client_call_results",
            page.runtime_globals,
        )
        call_evaluations = [
            operation
            for operation in page.operations
            if operation[0] == "evaluate"
            and "__crxzipple_browser_client_call__" in str(operation[1])
        ]
        self.assertEqual(len(call_evaluations), 1)

    def test_runtime_call_client_decodes_json_string_argument(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")

        def search(payload):  # noqa: ANN001, ANN202
            return {"key": payload.get("key")}

        page.runtime_globals = {
            "$nuxt": {
                "$http": {
                    "common": {
                        "search": search,
                    },
                },
            },
        }
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="runtime-call-client",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "object_path": "$nuxt.$http.common",
                "method_name": "search",
                "argument": "{\"key\":\"昆明\"}",
            },
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        payload = result.value["result"]
        self.assertTrue(result.ok)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["key"], "昆明")

    def test_runtime_probe_client_reports_missing_path_segment(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.runtime_globals = {"$nuxt": {"$http": {}}}
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="runtime-probe-client",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"object_path": "$nuxt.$http.shopping"},
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        payload = result.value["result"]
        self.assertTrue(result.ok)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["reason"], "path segment is not available")
        self.assertEqual(payload["missing_segment"], "shopping")

    def test_script_list_returns_live_debugger_script_catalog(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.debugger_scripts = [
            {
                "scriptId": "script-1",
                "url": "https://example.com/assets/app.js",
                "startLine": 0,
                "endLine": 10,
                "executionContextId": 1,
                "isModule": True,
                "sourceMapURL": "app.js.map",
            },
            {
                "scriptId": "script-2",
                "url": "https://example.com/assets/vendor.js",
                "startLine": 0,
                "endLine": 100,
                "executionContextId": 1,
            },
        ]
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="script-list",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"url_contains": "app", "limit": 10, "wait_ms": 0},
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        payload = result.value["result"]
        self.assertTrue(result.ok)
        self.assertEqual(payload["kind"], "script-list")
        self.assertEqual(payload["scripts_count"], 2)
        self.assertEqual(payload["matched_scripts"], 1)
        self.assertEqual(payload["returned_scripts"], 1)
        self.assertEqual(payload["scripts"][0]["script_id"], "script-1")
        self.assertEqual(payload["scripts"][0]["line_count"], 11)
        self.assertTrue(payload["scripts"][0]["is_module"])
        self.assertEqual(payload["scripts"][0]["source_map_url"], "app.js.map")
        self.assertIn(("cdp.send", "Debugger.enable", {}), page.operations)
        self.assertNotIn(
            ("cdp.send", "Debugger.getScriptSource", {"scriptId": "script-1"}),
            page.operations,
        )

    def test_script_find_request_locates_candidate_script_references(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.debugger_scripts = [
            {
                "scriptId": "script-1",
                "url": "https://example.com/assets/app.js",
                "startLine": 0,
                "endLine": 20,
            },
            {
                "scriptId": "script-2",
                "url": "https://example.com/assets/vendor.js",
                "startLine": 0,
                "endLine": 20,
            },
        ]
        page.debugger_script_sources = {
            "script-1": "\n".join(
                [
                    "const city = 'kunming';",
                    "const endpoint = '/api/flights/search';",
                    "fetch(`${endpoint}?city=${city}`);",
                ]
            ),
            "script-2": "console.log('vendor');",
        }
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="script-find-request",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "request_url": "https://example.com/api/flights/search?city=kunming",
                "limit": 5,
                "wait_ms": 0,
            },
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        payload = result.value["result"]
        self.assertTrue(result.ok)
        self.assertEqual(payload["kind"], "script-find-request")
        self.assertEqual(payload["request"]["path"], "/api/flights/search")
        self.assertEqual(payload["candidate_count"], 1)
        self.assertEqual(payload["match_count"], 2)
        candidate = payload["candidates"][0]
        self.assertEqual(candidate["script_id"], "script-1")
        self.assertIn("/api/flights/search", candidate["matched_terms"])
        self.assertEqual(candidate["matches"][0]["line_number"], 2)
        self.assertIn("endpoint", candidate["matches"][0]["snippet"])
        self.assertIn(("cdp.send", "Debugger.enable", {}), page.operations)
        self.assertIn(
            ("cdp.send", "Debugger.getScriptSource", {"scriptId": "script-1"}),
            page.operations,
        )

    def test_code_search_reads_live_debugger_scripts_and_returns_snippets(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.debugger_scripts = [
            {
                "scriptId": "script-1",
                "url": "https://example.com/assets/app.js",
                "startLine": 0,
                "endLine": 10,
            },
            {
                "scriptId": "script-2",
                "url": "https://example.com/assets/vendor.js",
                "startLine": 0,
                "endLine": 10,
            },
        ]
        page.debugger_script_sources = {
            "script-1": "const endpoint = '/api/flights/search';\nfetch(endpoint);",
            "script-2": "console.log('vendor');",
        }
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="code-search",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "query": "fetch",
                "context_lines": 1,
                "limit": 5,
                "wait_ms": 0,
            },
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        payload = result.value["result"]
        self.assertTrue(result.ok)
        self.assertEqual(payload["kind"], "code-search")
        self.assertEqual(payload["match_count"], 1)
        self.assertEqual(payload["matched_scripts"], 1)
        self.assertEqual(payload["matches"][0]["script_id"], "script-1")
        self.assertEqual(payload["matches"][0]["matches"][0]["line_number"], 2)
        self.assertIn("fetch(endpoint)", payload["matches"][0]["matches"][0]["snippet"])
        self.assertIn(("cdp.send", "Debugger.enable", {}), page.operations)
        self.assertIn(("cdp.send", "Debugger.getScriptSource", {"scriptId": "script-1"}), page.operations)

    def test_code_search_caps_wide_search_inputs(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.debugger_scripts = [
            {
                "scriptId": f"script-{index}",
                "url": f"https://example.com/assets/chunk-{index}.js",
                "startLine": 0,
                "endLine": 1,
            }
            for index in range(40)
        ]
        page.debugger_script_sources = {
            f"script-{index}": "\n".join(
                [
                    f"const before{index} = 'before';",
                    f"const endpoint{index} = '/api/flights/{index}';",
                    f"fetch(endpoint{index});",
                    "const after1 = 'after1';",
                    "const after2 = 'after2';",
                    "const after3 = 'after3';",
                ]
            )
            for index in range(40)
        }
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="code-search",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "query": "fetch",
                "context_lines": 10,
                "limit": 100,
                "max_scripts": 100,
                "wait_ms": 0,
            },
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        payload = result.value["result"]
        self.assertTrue(result.ok)
        self.assertEqual(payload["kind"], "code-search")
        self.assertEqual(payload["limit"], 12)
        self.assertEqual(payload["match_count"], 12)
        self.assertEqual(payload["searched_scripts"], 12)
        first_snippet = payload["matches"][0]["matches"][0]["snippet"]
        self.assertIn("after2", first_snippet)
        self.assertNotIn("after3", first_snippet)

    def test_code_search_caps_max_scripts_when_no_matches(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.debugger_scripts = [
            {
                "scriptId": f"script-{index}",
                "url": f"https://example.com/assets/chunk-{index}.js",
                "startLine": 0,
                "endLine": 1,
            }
            for index in range(40)
        ]
        page.debugger_script_sources = {
            f"script-{index}": "console.log('chunk');"
            for index in range(40)
        }
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="code-search",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "query": "fetch",
                "max_scripts": 100,
                "wait_ms": 0,
            },
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        payload = result.value["result"]
        self.assertTrue(result.ok)
        self.assertEqual(payload["kind"], "code-search")
        self.assertEqual(payload["match_count"], 0)
        self.assertEqual(payload["searched_scripts"], 24)

    def test_script_inspect_returns_bounded_source_preview(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.debugger_scripts = [
            {
                "scriptId": "script-1",
                "url": "https://example.com/assets/app.js",
                "startLine": 0,
                "endLine": 20,
            },
        ]
        page.debugger_script_sources = {
            "script-1": "\n".join(
                [
                    "const a = 1;",
                    "const endpoint = '/api/flights/search';",
                    "fetch(endpoint);",
                    "console.log(a);",
                ]
            ),
        }
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="script-inspect",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "url_contains": "app.js",
                "start_line": 2,
                "line_count": 2,
                "wait_ms": 0,
            },
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        payload = result.value["result"]
        self.assertTrue(result.ok)
        self.assertEqual(payload["kind"], "script-inspect")
        self.assertEqual(payload["script_id"], "script-1")
        self.assertEqual(payload["start_line"], 2)
        self.assertEqual(payload["end_line"], 3)
        self.assertIn("2: const endpoint", payload["source_preview"])
        self.assertIn("3: fetch(endpoint)", payload["source_preview"])

    def test_script_inspect_returns_single_line_preview_when_line_exceeds_max_chars(
        self,
    ) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.debugger_scripts = [
            {
                "scriptId": "script-min",
                "url": "https://example.com/assets/app.min.js",
                "startLine": 0,
                "endLine": 0,
            },
        ]
        page.debugger_script_sources = {
            "script-min": "const bundle='" + ("x" * 8000) + "';",
        }
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="script-inspect",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "script_id": "script-min",
                "start_line": 1,
                "line_count": 80,
                "max_chars": 400,
                "wait_ms": 0,
            },
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        payload = result.value["result"]
        self.assertTrue(result.ok)
        self.assertEqual(payload["kind"], "script-inspect")
        self.assertEqual(payload["start_line"], 1)
        self.assertEqual(payload["end_line"], 1)
        self.assertIn("1: const bundle=", payload["source_preview"])
        self.assertTrue(payload["truncated"])

    def test_script_inspect_can_preview_around_code_search_column(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.debugger_scripts = [
            {
                "scriptId": "script-min",
                "url": "https://example.com/assets/app.min.js",
                "startLine": 0,
                "endLine": 0,
            },
        ]
        page.debugger_script_sources = {
            "script-min": "before_" + ("x" * 200) + "searchFlight({dep:'KMG'});" + ("y" * 200),
        }
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="script-inspect",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "script_id": "script-min",
                "start_line": 1,
                "column": 208,
                "column_window": 120,
                "max_chars": 200,
                "wait_ms": 0,
            },
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        payload = result.value["result"]
        self.assertTrue(result.ok)
        self.assertEqual(payload["kind"], "script-inspect")
        self.assertEqual(payload["start_line"], 1)
        self.assertEqual(payload["end_line"], 1)
        self.assertLess(payload["start_column"], 208)
        self.assertGreaterEqual(payload["end_column"], 208)
        self.assertIn("searchFlight", payload["source_preview"])
        self.assertTrue(payload["truncated"])

    def test_script_inspect_treats_script_id_url_as_url_selector(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.debugger_scripts = [
            {
                "scriptId": "script-real",
                "url": "https://example.com/assets/app.min.js",
                "startLine": 0,
                "endLine": 0,
            },
        ]
        page.debugger_script_sources = {
            "script-real": "const endpoint = '/api/flights/search';",
        }
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="script-inspect",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "script_id": "https://example.com/assets/app.min.js",
                "start_line": 1,
                "line_count": 1,
                "wait_ms": 0,
            },
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        payload = result.value["result"]
        self.assertTrue(result.ok)
        self.assertEqual(payload["script_id"], "script-real")
        self.assertIn("/api/flights/search", payload["source_preview"])

    def test_script_extract_request_returns_endpoint_and_payload_candidates(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.debugger_scripts = [
            {
                "scriptId": "script-shopping",
                "url": "https://example.com/assets/shopping.js",
                "startLine": 0,
                "endLine": 8,
            },
        ]
        page.debugger_script_sources = {
            "script-shopping": "\n".join(
                [
                    "const shopping = {",
                    "  getShopping(payload) {",
                    "    return http.post('/portal/v3/shopping/briefInfo', {",
                    "      depCityCode: payload.depCityCode,",
                    "      arrCityCode: payload.arrCityCode,",
                    "      depDate: payload.depDate,",
                    "    });",
                    "  }",
                    "};",
                ],
            ),
        }
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="script-extract-request",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "script_id": "script-shopping",
                "start_line": 1,
                "line_count": 9,
                "query": "getShopping",
                "wait_ms": 0,
            },
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        payload = result.value["result"]
        self.assertTrue(result.ok)
        self.assertEqual(payload["kind"], "script-extract-request")
        self.assertEqual(payload["script_id"], "script-shopping")
        self.assertEqual(payload["candidate_count"], 1)
        candidate = payload["candidates"][0]
        self.assertEqual(candidate["endpoint"], "/portal/v3/shopping/briefInfo")
        self.assertIn("POST", candidate["method_candidates"])
        self.assertIn("http.post", candidate["client_method_candidates"])
        self.assertIn("depCityCode", candidate["payload_key_candidates"])
        self.assertIn("arrCityCode", candidate["payload_key_candidates"])
        self.assertTrue(candidate["focus_match"])
        self.assertEqual(candidate["confidence"], "high")

    def test_script_extract_request_infers_script_from_query(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.debugger_scripts = [
            {
                "scriptId": "script-shopping",
                "url": "https://example.com/assets/shopping.js",
                "startLine": 0,
                "endLine": 3,
            },
        ]
        page.debugger_script_sources = {
            "script-shopping": (
                "const api={getShopping(payload){return http.post("
                "'/portal/v3/shopping/briefInfo',"
                "{depCityCode:payload.depCityCode,arrCityCode:payload.arrCityCode})}};"
            ),
        }
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="script-extract-request",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "query": "getShopping",
                "column_window": 600,
                "wait_ms": 0,
            },
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        payload = result.value["result"]
        self.assertTrue(result.ok)
        self.assertEqual(payload["script_id"], "script-shopping")
        self.assertEqual(payload["inferred_target"]["script_id"], "script-shopping")
        self.assertGreaterEqual(payload["candidate_count"], 1)
        self.assertEqual(
            payload["candidates"][0]["endpoint"],
            "/portal/v3/shopping/briefInfo",
        )

    def test_script_extract_request_uses_column_window_for_minified_bundle(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        source = (
            "const boot=1;"
            + ("x" * 300)
            + "window.$nuxt.$http.shopping.getShopping=function(payload){"
            "return client.post('/portal/v3/shopping/briefInfo',"
            "{depCityCode:payload.depCityCode,arrCityCode:payload.arrCityCode})};"
            + ("y" * 300)
        )
        endpoint_column = source.index("/portal/v3/shopping/briefInfo") + 1
        page.debugger_scripts = [
            {
                "scriptId": "script-min",
                "url": "https://example.com/assets/app.min.js",
                "startLine": 0,
                "endLine": 0,
            },
        ]
        page.debugger_script_sources = {"script-min": source}
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="script-extract-request",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "script_id": "script-min",
                "start_line": 1,
                "column": endpoint_column,
                "column_window": 260,
                "query": "shopping",
                "wait_ms": 0,
            },
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        payload = result.value["result"]
        self.assertTrue(result.ok)
        self.assertEqual(payload["kind"], "script-extract-request")
        self.assertEqual(payload["start_line"], 1)
        self.assertEqual(payload["end_line"], 1)
        self.assertLess(payload["start_column"], endpoint_column)
        self.assertGreaterEqual(payload["end_column"], endpoint_column)
        candidate = payload["candidates"][0]
        self.assertEqual(candidate["endpoint"], "/portal/v3/shopping/briefInfo")
        self.assertIn("client.post", candidate["client_method_candidates"])
        self.assertIn("depCityCode", candidate["payload_key_candidates"])

    def test_script_extract_request_prioritizes_focused_endpoint_within_window(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        source = (
            "const api={"
            "fare:function(e){return post('/portal/skytrain/fareDetail',e)},"
            "transfer:function(e){return post('/portal/skytrain/transferCity',e)},"
            "valid:function(e){return post('/portal/skytrain/validItinerary',e)},"
            "rail:function(e){return post('/portal/skytrain/singleRailWay',e)},"
            "stop:function(e){return post('/portal/skytrain/stopoverInfo',e)},"
            "getShopping:function(e){e.verifyUrl='/portal/v3/shopping/briefInfo?'.concat(e.depCityCode).concat(e.arrCityCode).concat(e.depDate);return post('/portal/v3/shopping/briefInfo',{depCityCode:e.depCityCode,arrCityCode:e.arrCityCode,depDate:e.depDate})}"
            "};"
        )
        focus_column = source.index("/portal/v3/shopping/briefInfo") + 1
        page.debugger_scripts = [
            {
                "scriptId": "script-shopping-min",
                "url": "https://example.com/assets/shopping.min.js",
                "startLine": 0,
                "endLine": 0,
            },
        ]
        page.debugger_script_sources = {"script-shopping-min": source}
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="script-extract-request",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "script_id": "script-shopping-min",
                "start_line": 1,
                "column": focus_column,
                "column_window": 1200,
                "request_url": "/portal/v3/shopping/briefInfo",
                "limit": 3,
                "wait_ms": 0,
            },
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        payload = result.value["result"]
        self.assertTrue(result.ok)
        self.assertGreaterEqual(payload["candidate_count"], 3)
        candidate = payload["candidates"][0]
        self.assertEqual(candidate["endpoint"], "/portal/v3/shopping/briefInfo")
        self.assertTrue(candidate["endpoint_focus_match"])
        self.assertIn("getShopping", candidate["client_method_candidates"])
        self.assertIn("depCityCode", candidate["payload_key_candidates"])

    def test_network_inspect_returns_performance_entries_and_cdp_facts(self) -> None:
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="network-inspect",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"limit": 10},
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        page = self.session_pool.pages["tab-1"]
        self.assertTrue(result.ok)
        payload = result.value["result"]
        self.assertEqual(payload["kind"], "network-inspect")
        self.assertEqual(payload["url"], page.url)
        self.assertEqual(payload["performance"]["entry_count"], 2)
        self.assertEqual(payload["performance"]["entries"][0]["entry_type"], "navigation")
        self.assertEqual(payload["cdp"]["metrics"]["metrics"][0]["name"], "Timestamp")
        resource_tree = payload["cdp"]["resource_tree"]
        self.assertEqual(resource_tree["resource_count"], 1)
        self.assertEqual(resource_tree["resources"][0]["type"], "Script")
        self.assertTrue(resource_tree["raw_omitted"])
        self.assertEqual(payload["errors"], [])
        self.assertIn(
            ("cdp.send", "Performance.getMetrics", {}),
            page.operations,
        )
        self.assertIn(
            ("cdp.send", "Page.getResourceTree", {}),
            page.operations,
        )

    def test_network_inspect_summarizes_large_cdp_resource_tree(self) -> None:
        class _Page:
            url = "https://example.com/app"

            def evaluate(self, _expression, _payload):  # noqa: ANN001, ANN201
                return {
                    "url": self.url,
                    "entries": [],
                    "entry_count": 0,
                    "limit": 25,
                }

        class _Broker:
            def open_command_session(self, _page):  # noqa: ANN001, ANN201
                return object()

            def send_command(self, _session, method, _params):  # noqa: ANN001, ANN201
                if method == "Performance.getMetrics":
                    return {"metrics": [{"name": "Timestamp", "value": 1.0}]}
                if method == "Page.getResourceTree":
                    return {
                        "frameTree": {
                            "frame": {
                                "id": "frame-1",
                                "url": "https://example.com/app",
                            },
                            "resources": [
                                {
                                    "url": (
                                        "data:image/png;base64," + ("a" * 1000)
                                        if index == 0
                                        else (
                                            "https://cdn.example.com/assets/"
                                            f"{index}.js?token={'x' * 1000}"
                                        )
                                    ),
                                    "type": "Script",
                                    "mimeType": "application/javascript",
                                }
                                for index in range(400)
                            ],
                        },
                    }
                return {}

            def detach(self, _session):  # noqa: ANN001
                return None

        service = BrowserNetworkInsightService(cdp_session_broker=_Broker())

        payload = service.execute(
            page=_Page(),
            payload={
                "limit": 25,
                "include_cdp_tree": True,
                "include_performance_metrics": True,
            },
        )

        resource_tree = payload["cdp"]["resource_tree"]
        self.assertEqual(resource_tree["resource_count"], 400)
        self.assertEqual(len(resource_tree["resources"]), 25)
        self.assertEqual(
            resource_tree["resources"][0]["url"],
            "data:image/png;base64,[omitted 1000 chars]",
        )
        self.assertTrue(resource_tree["truncated"])
        self.assertTrue(resource_tree["raw_omitted"])
        self.assertLess(
            len(json.dumps(payload, ensure_ascii=False, separators=(",", ":"))),
            131072,
        )

    def test_emulation_set_applies_target_scoped_cdp_overrides(self) -> None:
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="emulation-set",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "width": 390,
                "height": 844,
                "device_scale_factor": 3,
                "is_mobile": True,
                "has_touch": True,
                "user_agent": "Test Mobile UA",
                "timezone_id": "Asia/Shanghai",
                "locale": "zh-CN",
            },
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        page = self.session_pool.pages["tab-1"]
        payload = result.value["result"]
        self.assertTrue(result.ok)
        self.assertEqual(payload["kind"], "emulation-set")
        self.assertEqual(payload["policy"]["runtime_scope"], "target")
        self.assertEqual(
            payload["changed_controls"],
            ["device_metrics", "user_agent", "timezone", "locale"],
        )
        self.assertIn(
            (
                "cdp.send",
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": 390,
                    "height": 844,
                    "deviceScaleFactor": 3.0,
                    "mobile": True,
                    "screenWidth": 390,
                    "screenHeight": 844,
                    "dontSetVisibleSize": False,
                    "screenOrientation": {
                        "type": "portraitPrimary",
                        "angle": 0,
                    },
                    "hasTouch": True,
                },
            ),
            page.operations,
        )
        self.assertIn(
            ("cdp.send", "Emulation.setUserAgentOverride", {"userAgent": "Test Mobile UA"}),
            page.operations,
        )
        self.assertIn(("cdp.detach",), page.operations)

    def test_environment_permissions_geolocation_and_network_conditions(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        grant_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="permissions-grant",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "permissions": ["geolocation", "notifications"],
                "origin": "https://example.com",
            },
        )
        grant_result = self.engine.execute(
            plan=self._plan(grant_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=grant_command,
        )

        geolocation_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="geolocation-set",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"latitude": 25.04, "longitude": 102.71, "accuracy": 10},
        )
        geolocation_result = self.engine.execute(
            plan=self._plan(geolocation_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=geolocation_command,
        )

        network_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="network-conditions-set",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "offline": False,
                "latency_ms": 120,
                "download_kbps": 512,
                "upload_kbps": 128,
                "connection_type": "cellular3g",
            },
        )
        network_result = self.engine.execute(
            plan=self._plan(network_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=network_command,
        )

        self.assertEqual(grant_result.value["result"]["permission_names"], ["geolocation", "notifications"])
        self.assertIn(
            (
                "context.grant_permissions",
                {
                    "permissions": ["geolocation", "notifications"],
                    "origin": "https://example.com",
                },
            ),
            page.operations,
        )
        self.assertEqual(
            geolocation_result.value["result"]["geolocation"],
            {"latitude": 25.04, "longitude": 102.71, "accuracy": 10.0},
        )
        self.assertIn(
            (
                "cdp.send",
                "Emulation.setGeolocationOverride",
                {"latitude": 25.04, "longitude": 102.71, "accuracy": 10.0},
            ),
            page.operations,
        )
        self.assertEqual(
            network_result.value["result"]["network_conditions"],
            {
                "offline": False,
                "latency_ms": 120.0,
                "download_throughput_bytes_per_second": 65536,
                "upload_throughput_bytes_per_second": 16384,
                "connection_type": "cellular3g",
            },
        )
        self.assertIn(
            (
                "cdp.send",
                "Network.emulateNetworkConditions",
                {
                    "offline": False,
                    "latency": 120.0,
                    "downloadThroughput": 65536,
                    "uploadThroughput": 16384,
                    "connectionType": "cellular3g",
                },
            ),
            page.operations,
        )

    def test_emulation_reset_clears_target_overrides(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="emulation-reset",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={},
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        self.assertTrue(result.ok)
        self.assertIn("device_metrics", result.value["result"]["changed_controls"])
        self.assertIn("permissions", result.value["result"]["changed_controls"])
        self.assertIn(("cdp.send", "Emulation.clearDeviceMetricsOverride", {}), page.operations)
        self.assertIn(("cdp.send", "Emulation.clearGeolocationOverride", {}), page.operations)
        self.assertIn(("context.clear_permissions",), page.operations)

    def test_diagnostics_collects_lifecycle_performance_and_console_errors(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.emit_console(text="Something failed", message_type="error")
        page.emit_page_error(
            message="Unhandled promise rejection",
            name="UnhandledRejection",
            stack="stack line",
        )
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="diagnostics-collect",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"include_entries": True},
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        payload = result.value["result"]
        self.assertTrue(result.ok)
        self.assertEqual(payload["kind"], "diagnostics-collect")
        self.assertEqual(payload["issue_count"], 2)
        self.assertEqual(payload["diagnostics"]["errors"][0]["text"], "Something failed")
        self.assertEqual(payload["diagnostics"]["errors"][1]["source"], "pageerror")
        self.assertEqual(
            payload["diagnostics"]["errors"][1]["text"],
            "Unhandled promise rejection",
        )
        self.assertEqual(payload["diagnostics"]["lifecycle"]["url"], "https://example.com")
        self.assertEqual(
            payload["diagnostics"]["performance"]["metrics"]["metrics"][0]["name"],
            "Timestamp",
        )
        self.assertIn(("cdp.send", "Page.getNavigationHistory", {}), page.operations)
        self.assertEqual(
            self.emitted_browser_events[-1][0],
            "browser.diagnostics.collected",
        )
        self.assertEqual(self.emitted_browser_events[-1][1]["issue_count"], 2)
        self.assertEqual(
            self.emitted_browser_events[-1][1]["diagnostic_kind"],
            "diagnostics-collect",
        )

    def test_trace_start_stop_and_export_returns_zip_payload(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        start_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="trace-start",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"trace_id": "trace-1", "title": "checkout"},
        )
        start_result = self.engine.execute(
            plan=self._plan(start_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=start_command,
        )

        stop_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="trace-stop",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"trace_id": "trace-1"},
        )
        stop_result = self.engine.execute(
            plan=self._plan(stop_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=stop_command,
        )

        export_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="trace-export",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"trace_id": "trace-1"},
        )
        export_result = self.engine.execute(
            plan=self._plan(export_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=export_command,
        )

        self.assertEqual(start_result.value["result"]["status"], "active")
        self.assertEqual(stop_result.value["result"]["content_type"], "application/zip")
        self.assertEqual(stop_result.value["result"]["encoding"], "base64")
        self.assertEqual(export_result.value["result"]["data"], stop_result.value["result"]["data"])
        self.assertIn(
            (
                "tracing.start",
                {"screenshots": True, "snapshots": True, "sources": False, "title": "checkout"},
            ),
            page.operations,
        )
        self.assertTrue(any(operation[0] == "tracing.stop" for operation in page.operations))
        self.assertIn(
            "browser.trace.exported",
            [event_name for event_name, _payload in self.emitted_browser_events],
        )

    def test_network_capture_actions_record_and_list_requests(self) -> None:
        start_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="network-start-capture",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "capture_id": "cap-1",
                "max_requests": 10,
                "max_body_bytes": 128,
            },
        )

        start_result = self.engine.execute(
            plan=self._plan(start_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=start_command,
        )

        self.assertTrue(start_result.ok)
        self.assertEqual(
            start_result.value["result"]["capture"]["capture_id"],
            "cap-1",
        )
        self.assertEqual(start_result.value["result"]["capture"]["status"], "active")

        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        session = page.browser_context.cdp_sessions[-1]
        assert self.engine.network_capture_controller is not None
        subscription = self.engine.network_capture_controller._subscriptions[
            ("crxzipple", "tab-1", "cap-1")
        ]
        self.assertEqual(subscription.session.mode, "subscription")
        self.assertFalse(subscription.session.detached)
        page.network_response_bodies["req-1"] = {
            "body": '{"ok":true}',
            "base64Encoded": False,
        }
        session.emit(
            "Network.requestWillBeSent",
            {
                "requestId": "req-1",
                "type": "XHR",
                "frameId": "frame-tab-1",
                "loaderId": "loader-1",
                "request": {
                    "url": "https://example.com/api/search?token=secret&city=kunming",
                    "method": "POST",
                    "headers": {
                        "Authorization": "Bearer secret",
                        "Content-Type": "application/json",
                    },
                    "postData": '{"query":"flights","token":"secret"}',
                },
                "initiator": {"type": "script"},
            },
        )
        session.emit(
            "Network.responseReceived",
            {
                "requestId": "req-1",
                "type": "XHR",
                "response": {
                    "status": 200,
                    "headers": {
                        "Content-Type": "application/json",
                        "Set-Cookie": "session=secret",
                    },
                    "mimeType": "application/json",
                    "timing": {"receiveHeadersEnd": 12.0},
                },
            },
        )
        session.emit(
            "Network.loadingFinished",
            {
                "requestId": "req-1",
                "encodedDataLength": 128,
            },
        )

        list_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="network-list-requests",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"capture_id": "cap-1", "limit": 10},
        )

        list_result = self.engine.execute(
            plan=self._plan(list_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=list_command,
        )

        payload = list_result.value["result"]
        self.assertEqual(payload["kind"], "network-list-requests")
        self.assertEqual(payload["capture"]["capture_id"], "cap-1")
        self.assertEqual(payload["request_count"], 1)
        self.assertEqual(payload["requests"][0]["resource_type"], "xhr")
        self.assertEqual(payload["requests"][0]["status"], 200)
        self.assertEqual(
            payload["requests"][0]["url"],
            "https://example.com/api/search?token=%5Bredacted%5D&city=kunming",
        )
        self.assertEqual(payload["requests"][0]["request_headers"]["Authorization"], "[redacted]")
        self.assertEqual(payload["requests"][0]["response_headers"]["Set-Cookie"], "[redacted]")
        self.assertEqual(payload["requests"][0]["encoded_data_length"], 128)

        active_list_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="network-list-requests",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"capture_id": "active", "limit": 10},
        )

        active_list_result = self.engine.execute(
            plan=self._plan(active_list_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=active_list_command,
        )

        self.assertTrue(active_list_result.ok)
        self.assertEqual(
            active_list_result.value["result"]["capture"]["capture_id"],
            "cap-1",
        )

        stale_id_list_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="network-list-requests",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"capture_id": "invented-capture-id", "limit": 10},
        )

        stale_id_list_result = self.engine.execute(
            plan=self._plan(stale_id_list_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=stale_id_list_command,
        )

        self.assertTrue(stale_id_list_result.ok)
        self.assertEqual(
            stale_id_list_result.value["result"]["capture"]["capture_id"],
            "cap-1",
        )

        request_id = payload["requests"][0]["request_id"]
        get_request_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="network-get-request",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "capture_id": "cap-1",
                "request_id": request_id,
            },
        )

        get_request_result = self.engine.execute(
            plan=self._plan(get_request_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=get_request_command,
        )

        self.assertEqual(get_request_result.value["result"]["request"]["request_id"], "req-1")
        self.assertEqual(
            get_request_result.value["result"]["request"]["request_post_data_preview"],
            '{"query":"flights","token":"[redacted]"}',
        )

        request_body_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="network-get-request-body",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "capture_id": "cap-1",
                "request_id": request_id,
            },
        )

        request_body_result = self.engine.execute(
            plan=self._plan(request_body_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=request_body_command,
        )

        self.assertEqual(request_body_result.value["result"]["body_kind"], "request")
        self.assertEqual(
            request_body_result.value["result"]["body"],
            '{"query":"flights","token":"[redacted]"}',
        )

        body_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="network-get-response-body",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "capture_id": "cap-1",
                "request_id": request_id,
            },
        )

        body_result = self.engine.execute(
            plan=self._plan(body_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=body_command,
        )

        self.assertEqual(body_result.value["result"]["body"], '{"ok":true}')
        self.assertEqual(body_result.value["result"]["body_kind"], "response")

        page.network_fetch_responses["https://example.com/api/details?token=secret"] = {
            "ok": True,
            "url": "https://example.com/api/details?token=secret",
            "status": 200,
            "headers": {"content-type": "application/json"},
            "body": '{"access_token":"secret","ok":true}',
            "size_bytes": 35,
            "stored_size_bytes": 35,
            "truncated": False,
        }
        fetch_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="network-fetch-as-page",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "url": "/api/details?token=secret",
                "method": "GET",
                "headers": {"Authorization": "Bearer secret", "X-Trace": "trace-1"},
            },
        )

        fetch_result = self.engine.execute(
            plan=self._plan(fetch_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=fetch_command,
        )

        self.assertEqual(fetch_result.value["result"]["status"], 200)
        self.assertEqual(
            fetch_result.value["result"]["url"],
            "https://example.com/api/details?token=%5Bredacted%5D",
        )
        self.assertEqual(fetch_result.value["result"]["request"]["headers"], {"X-Trace": "trace-1"})
        self.assertNotIn("body", fetch_result.value["result"])
        self.assertTrue(fetch_result.value["result"]["body_omitted"])
        self.assertNotIn("secret", fetch_result.value["result"]["body_preview"])
        self.assertEqual(fetch_result.value["result"]["fetch_safety"]["level"], "ready")
        self.assertEqual(
            fetch_result.value["result"]["fetch_safety"]["gates"]["cross_origin"],
            {
                "required": False,
                "allowed": False,
                "page_origin": "https://example.com",
                "target_origin": "https://example.com",
            },
        )
        self.assertEqual(
            fetch_result.value["result"]["fetch_safety"]["gates"]["mutating_method"],
            {
                "required": False,
                "allowed": False,
                "method": "GET",
            },
        )
        self.assertTrue(fetch_result.value["result"]["response_summary"]["ok"])
        self.assertEqual(fetch_result.value["result"]["response_summary"]["status"], 200)
        self.assertTrue(fetch_result.value["result"]["response_summary"]["body_omitted"])

        include_body_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="network-fetch-as-page",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "url": "/api/details?token=secret",
                "method": "GET",
                "include_body": True,
                "body_preview_bytes": 8,
            },
        )

        include_body_result = self.engine.execute(
            plan=self._plan(include_body_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=include_body_command,
        )

        self.assertIn("body", include_body_result.value["result"])
        self.assertFalse(include_body_result.value["result"]["body_omitted"])
        self.assertEqual(include_body_result.value["result"]["body_preview"], '{"access')
        self.assertTrue(include_body_result.value["result"]["body_preview_truncated"])

        page.network_fetch_responses["https://example.com/api/search?city=kunming"] = {
            "ok": True,
            "url": "https://example.com/api/search?city=kunming",
            "status": 201,
            "headers": {"content-type": "application/json"},
            "body": '{"items":[1]}',
            "size_bytes": 13,
            "stored_size_bytes": 13,
            "truncated": False,
        }
        replay_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="network-replay-request",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "capture_id": "cap-1",
                "request_id": request_id,
                "url": "/api/search?city=kunming",
                "json": {"query": "flights"},
                "allow_mutating": True,
            },
        )

        replay_result = self.engine.execute(
            plan=self._plan(replay_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=replay_command,
        )

        replay_payload = replay_result.value["result"]
        self.assertEqual(replay_payload["status"], 201)
        self.assertEqual(replay_payload["source_request_id"], "req-1")
        self.assertEqual(
            replay_payload["request"]["url"],
            "https://example.com/api/search?city=kunming",
        )
        self.assertNotIn("body", replay_payload)
        self.assertEqual(replay_payload["body_preview"], '{"items":[1]}')
        self.assertTrue(replay_payload["body_omitted"])
        self.assertEqual(replay_payload["replay_suitability"]["level"], "warning")
        self.assertEqual(
            replay_payload["replay_suitability"]["gates"]["captured_body"]["source"],
            "override-json",
        )
        self.assertTrue(
            replay_payload["replay_suitability"]["gates"]["mutating_method"]["required"],
        )
        self.assertTrue(
            replay_payload["replay_suitability"]["gates"]["mutating_method"]["allowed"],
        )
        self.assertIn(
            "Source request URL contains redacted values; replay may not match the original request.",
            replay_payload["replay_suitability"]["warnings"],
        )
        self.assertIn(
            "Source request headers contain redacted values; sensitive headers were not reused.",
            replay_payload["replay_suitability"]["warnings"],
        )
        self.assertIn(
            "Captured request body was redacted; replay requires an explicit replacement body.",
            replay_payload["replay_suitability"]["warnings"],
        )
        self.assertEqual(replay_payload["request_diff"]["body_source"], "override-json")
        self.assertIn("url", replay_payload["request_diff"]["changed_fields"])
        self.assertIn("body_unknown", replay_payload["request_diff"]["changed_fields"])
        self.assertEqual(replay_payload["request_diff"]["source"]["body"]["state"], "redacted")
        self.assertTrue(replay_payload["response_summary"]["ok"])
        self.assertEqual(replay_payload["response_summary"]["status"], 201)
        self.assertEqual(replay_payload["response_summary"]["mime_type"], "application/json")
        self.assertEqual(
            [event_name for event_name, _payload in self.emitted_browser_events],
            [
                "browser.network.fetch.executed",
                "browser.network.fetch.executed",
                "browser.network.replay.executed",
            ],
        )
        fetch_event = self.emitted_browser_events[0][1]
        self.assertEqual(fetch_event["profile_name"], "crxzipple")
        self.assertEqual(fetch_event["target_id"], "tab-1")
        self.assertEqual(fetch_event["status"], "succeeded")
        self.assertEqual(fetch_event["status_code"], 200)
        self.assertNotIn("secret", str(fetch_event))
        replay_event = self.emitted_browser_events[2][1]
        self.assertEqual(replay_event["source_request_id"], "req-1")
        self.assertEqual(replay_event["source_capture_id"], "cap-1")

    def test_network_fetch_failure_emits_display_safe_event(self) -> None:
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="network-fetch-as-page",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "url": "https://api.example.test/search?token=secret",
                "method": "GET",
            },
        )

        with self.assertRaisesRegex(BrowserValidationError, "cross-origin"):
            self.engine.execute(
                plan=self._plan(command),
                runtime_state=self.runtime_state,
                tab=self.tab,
                command=command,
            )

        self.assertEqual(len(self.emitted_browser_events), 1)
        event_name, payload = self.emitted_browser_events[0]
        self.assertEqual(event_name, "browser.network.fetch.failed")
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["level"], "error")
        self.assertEqual(payload["profile_name"], "crxzipple")
        self.assertEqual(payload["target_id"], "tab-1")
        self.assertNotIn("secret", str(payload))

    def test_dom_inspection_actions_return_layout_style_and_clickability(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.main_frame.interactive_items = [
            {
                "selector": "#submit",
                "label": "Submit",
                "role": "button",
                "text": "Submit",
                "tag": "button",
                "clickable": False,
                "blocked_by": {
                    "tag": "div",
                    "selector_hint": "div.modal-mask",
                    "text": "",
                },
                "computed_style": {
                    "display": "block",
                    "pointer-events": "auto",
                    "z-index": "1",
                },
                "inline_handlers": ["click"],
                "listener_types": ["click", "pointerdown"],
                "box": {
                    "x": 24,
                    "y": 48,
                    "width": 160,
                    "height": 40,
                    "top": 48,
                    "right": 184,
                    "bottom": 88,
                    "left": 24,
                },
                "mutation_wait": {
                    "changed": True,
                    "reason": "quiet",
                    "mutation_count": 3,
                    "elapsed_ms": 140,
                },
            },
        ]

        inspect_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="dom-inspect",
            target=BrowserActionTarget(target_id="tab-1", selector="#submit"),
            payload={"properties": ["display", "z-index"]},
        )

        inspect_result = self.engine.execute(
            plan=self._plan(inspect_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=inspect_command,
        )

        result = inspect_result.value["result"]
        self.assertEqual(result["kind"], "dom-inspect")
        self.assertEqual(result["selector"], "#submit")
        self.assertFalse(result["clickable"])
        self.assertEqual(result["blocked_by"]["selector_hint"], "div.modal-mask")
        self.assertEqual(result["computed_style"]["z-index"], "1")
        self.assertEqual(result["event_summary"]["inline_handlers"], ["click"])
        self.assertEqual(result["event_summary"]["listener_types"], ["click", "pointerdown"])
        self.assertTrue(result["event_summary"]["has_handlers"])

        clickability_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="dom-clickability",
            target=BrowserActionTarget(target_id="tab-1", selector="#submit"),
            payload={},
        )
        clickability_result = self.engine.execute(
            plan=self._plan(clickability_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=clickability_command,
        )

        self.assertEqual(clickability_result.value["result"]["kind"], "dom-clickability")
        self.assertEqual(
            clickability_result.value["result"]["reasons"],
            ["blocked_by_overlay"],
        )

        highlight_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="dom-highlight",
            target=BrowserActionTarget(target_id="tab-1", selector="#submit"),
            payload={"duration_ms": 900, "color": "#ff0000", "label": "Submit CTA"},
        )
        highlight_result = self.engine.execute(
            plan=self._plan(highlight_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=highlight_command,
        )

        self.assertEqual(highlight_result.value["result"]["kind"], "dom-highlight")
        self.assertTrue(highlight_result.value["result"]["highlighted"])
        self.assertEqual(highlight_result.value["result"]["duration_ms"], 900)
        self.assertEqual(highlight_result.value["result"]["color"], "#ff0000")

        mutation_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="dom-mutation-wait",
            target=BrowserActionTarget(target_id="tab-1", selector="#submit"),
            payload={"quiet_ms": 50},
            timeout_ms=1800,
        )
        mutation_result = self.engine.execute(
            plan=self._plan(mutation_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=mutation_command,
        )

        self.assertEqual(mutation_result.value["result"]["kind"], "dom-mutation-wait")
        self.assertTrue(mutation_result.value["result"]["changed"])
        self.assertEqual(mutation_result.value["result"]["mutation_count"], 3)
        self.assertEqual(mutation_result.value["result"]["timeout_ms"], 1800)

    def test_dom_inspection_merges_devtools_event_listener_evidence(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": "#actual-submit",
                "label": "Submit",
                "role": "button",
                "text": "Submit",
                "tag": "button",
                "event_summary": {
                    "inline_handlers": [],
                    "property_handlers": [],
                    "listener_types": [],
                    "has_handlers": False,
                },
            },
        ]
        page.backend_node_selectors[42] = "#actual-submit"
        page.devtools_event_listeners_by_backend_node[42] = [
            {
                "type": "click",
                "scriptId": "17",
                "lineNumber": 12,
                "columnNumber": 4,
                "useCapture": False,
                "passive": True,
                "once": False,
                "handler": {
                    "description": "function onSubmit(event) { /* test */ }",
                },
            },
            {
                "type": "change",
                "scriptId": "18",
                "lineNumber": 20,
            },
        ]
        self.ref_store.save_tab_refs(
            profile_name="crxzipple",
            target_id="tab-1",
            refs=(
                BrowserStoredRef(
                    ref="r-submit",
                    selector="#stale-submit",
                    backend_node_id=42,
                    generation=1,
                    snapshot_format="interactive",
                    label="Submit",
                    role="button",
                    text="Submit",
                    tag="button",
                ),
            ),
        )
        self.runtime_state.remember_page_snapshot(
            target_id="tab-1",
            generation=1,
            snapshot_format="interactive",
            ref_count=1,
            frame_count=1,
        )

        inspect_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="dom-clickability",
            target=BrowserActionTarget(target_id="tab-1", ref="r-submit"),
            payload={},
        )

        inspect_result = self.engine.execute(
            plan=self._plan(inspect_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=inspect_command,
        )

        event_summary = inspect_result.value["result"]["event_summary"]
        self.assertTrue(event_summary["has_handlers"])
        self.assertEqual(event_summary["listener_types"], ["change", "click"])
        self.assertTrue(event_summary["devtools_available"])
        self.assertEqual(event_summary["devtools_listener_count"], 2)
        self.assertEqual(event_summary["devtools_listeners"][0]["type"], "click")
        self.assertEqual(event_summary["devtools_listeners"][0]["script_id"], "17")
        self.assertIn(
            (
                "cdp.send",
                "DOMDebugger.getEventListeners",
                {"objectId": "backend-node:42", "depth": 1, "pierce": True},
            ),
            page.operations,
        )



if __name__ == "__main__":
    unittest.main()
