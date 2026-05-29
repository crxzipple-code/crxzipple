from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest
from typing import Mapping

from crxzipple.modules.browser.application.network_capture import (
    BrowserNetworkCaptureService,
)
from crxzipple.modules.browser.domain import BrowserValidationError
from crxzipple.modules.browser.domain.value_objects import BrowserNetworkBodyKind
from crxzipple.modules.browser.infrastructure.network_capture import (
    InMemoryBrowserNetworkCaptureStore,
)

NOW = datetime(2026, 5, 28, 8, 0, tzinfo=timezone.utc)


class _HookRedactor:
    def redact_url(self, url: str) -> str:
        return url.replace("secret", "hooked")

    def redact_headers(self, headers: Mapping[str, str]) -> dict[str, str]:
        return {key: f"hooked:{value}" for key, value in headers.items()}

    def redact_body(
        self,
        *,
        body: str,
        kind: BrowserNetworkBodyKind,
        mime_type: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> str:
        del kind, mime_type, headers
        return body.replace("secret", "hooked")


class BrowserNetworkCaptureTestCase(unittest.TestCase):
    def _service(
        self,
        *,
        store: InMemoryBrowserNetworkCaptureStore | None = None,
        event_emitter=None,  # noqa: ANN001
    ) -> BrowserNetworkCaptureService:
        return BrowserNetworkCaptureService(
            capture_store=store or InMemoryBrowserNetworkCaptureStore(),
            capture_id_factory=lambda: "cap-1",
            clock=lambda: NOW,
            event_emitter=event_emitter,
        )

    def test_start_stop_and_scope_capture_by_profile_target_and_capture_id(self) -> None:
        service = self._service()

        capture = service.start_capture(
            profile_name=" CRXZipple ",
            target_id="tab-1",
            max_requests=2,
            max_body_bytes=32,
        )

        self.assertEqual(capture.profile_name, "crxzipple")
        self.assertEqual(capture.target_id, "tab-1")
        self.assertEqual(capture.capture_id, "cap-1")
        self.assertEqual(capture.status, "active")
        self.assertEqual(capture.started_at, NOW)
        self.assertEqual(
            service.list_captures(profile_name="crxzipple", target_id="tab-1"),
            (capture,),
        )

        stopped = service.stop_capture(
            profile_name="crxzipple",
            target_id="tab-1",
            capture_id="cap-1",
        )

        self.assertEqual(stopped.status, "stopped")
        self.assertEqual(stopped.stopped_at, NOW)
        with self.assertRaisesRegex(BrowserValidationError, "not active"):
            service.record_request(
                profile_name="crxzipple",
                target_id="tab-1",
                capture_id="cap-1",
                request_id="req-1",
                url="https://example.test/",
                method="GET",
            )

    def test_records_requests_filters_and_redacts_sensitive_data(self) -> None:
        service = self._service()
        service.start_capture(
            profile_name="crxzipple",
            target_id="tab-1",
            capture_id="cap-1",
            max_body_bytes=128,
        )

        request = service.record_request(
            profile_name="crxzipple",
            target_id="tab-1",
            capture_id="cap-1",
            request_id="req-1",
            url="https://api.example.test/search?token=secret&q=flight",
            method="post",
            resource_type="XHR",
            request_headers={
                "Authorization": "Bearer secret",
                "X-Trace": "trace-1",
            },
            request_post_data='{"password":"secret","q":"flight"}',
            initiator={"type": "script"},
        )
        service.record_response(
            profile_name="crxzipple",
            target_id="tab-1",
            capture_id="cap-1",
            request_id="req-1",
            status=200,
            response_headers={
                "Content-Type": "application/json",
                "Set-Cookie": "sid=secret",
            },
            mime_type="application/json",
        )
        service.record_response_body(
            profile_name="crxzipple",
            target_id="tab-1",
            capture_id="cap-1",
            request_id="req-1",
            body='{"access_token":"secret","items":[1]}',
        )

        self.assertNotIn("secret", request.url)
        self.assertEqual(request.request_headers["Authorization"], "[redacted]")
        self.assertEqual(request.request_headers["X-Trace"], "trace-1")
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.resource_type, "xhr")
        request_body = service.get_request_body(
            profile_name="crxzipple",
            target_id="tab-1",
            capture_id="cap-1",
            request_id="req-1",
        )
        self.assertTrue(request_body.redacted)
        self.assertNotIn("secret", request_body.body)

        stored = service.get_request(
            profile_name="crxzipple",
            target_id="tab-1",
            capture_id="cap-1",
            request_id="req-1",
        )
        self.assertEqual(stored.status, 200)
        self.assertEqual(stored.response_headers["Set-Cookie"], "[redacted]")
        response_body = service.get_response_body(
            profile_name="crxzipple",
            target_id="tab-1",
            capture_id="cap-1",
            request_id="req-1",
        )
        self.assertTrue(response_body.redacted)
        self.assertNotIn("secret", response_body.body)

        records = service.list_requests(
            profile_name="crxzipple",
            target_id="tab-1",
            capture_id="cap-1",
            resource_type="xhr",
            domain="example.test",
            method="POST",
            status_min=200,
            status_max=299,
            keyword="search",
        )
        self.assertEqual([item.request_id for item in records], ["req-1"])

    def test_body_size_limit_and_ring_buffer_evict_old_requests(self) -> None:
        service = self._service()
        service.start_capture(
            profile_name="crxzipple",
            target_id="tab-1",
            capture_id="cap-1",
            max_requests=2,
            max_body_bytes=10,
        )

        for index in range(3):
            request_id = f"req-{index}"
            service.record_request(
                profile_name="crxzipple",
                target_id="tab-1",
                capture_id="cap-1",
                request_id=request_id,
                url=f"https://example.test/{index}",
                method="GET",
                created_at=NOW + timedelta(seconds=index),
            )
            service.record_response(
                profile_name="crxzipple",
                target_id="tab-1",
                capture_id="cap-1",
                request_id=request_id,
                status=200,
            )
            service.record_response_body(
                profile_name="crxzipple",
                target_id="tab-1",
                capture_id="cap-1",
                request_id=request_id,
                body="0123456789abcdef",
            )

        records = service.list_requests(
            profile_name="crxzipple",
            target_id="tab-1",
            capture_id="cap-1",
        )
        self.assertEqual([item.request_id for item in records], ["req-1", "req-2"])
        with self.assertRaisesRegex(BrowserValidationError, "req-0"):
            service.get_request(
                profile_name="crxzipple",
                target_id="tab-1",
                capture_id="cap-1",
                request_id="req-0",
            )
        body = service.get_response_body(
            profile_name="crxzipple",
            target_id="tab-1",
            capture_id="cap-1",
            request_id="req-1",
        )
        self.assertEqual(body.body, "0123456789")
        self.assertEqual(body.stored_size_bytes, 10)
        self.assertTrue(body.truncated)

    def test_custom_redactor_hook_is_used_before_storage(self) -> None:
        service = self._service(
            store=InMemoryBrowserNetworkCaptureStore(redactor=_HookRedactor()),
        )
        service.start_capture(
            profile_name="crxzipple",
            target_id="tab-1",
            capture_id="cap-1",
        )

        request = service.record_request(
            profile_name="crxzipple",
            target_id="tab-1",
            capture_id="cap-1",
            request_id="req-1",
            url="https://example.test/?token=secret",
            method="POST",
            request_headers={"X-Test": "secret"},
            request_post_data="secret body",
        )

        self.assertIn("hooked", request.url)
        self.assertEqual(request.request_headers["X-Test"], "hooked:secret")
        body = service.get_request_body(
            profile_name="crxzipple",
            target_id="tab-1",
            capture_id="cap-1",
            request_id="req-1",
        )
        self.assertEqual(body.body, "hooked body")

    def test_clear_removes_capture_requests_and_bodies(self) -> None:
        service = self._service()
        service.start_capture(
            profile_name="crxzipple",
            target_id="tab-1",
            capture_id="cap-1",
        )
        service.record_request(
            profile_name="crxzipple",
            target_id="tab-1",
            capture_id="cap-1",
            request_id="req-1",
            url="https://example.test/",
            method="GET",
        )

        service.clear(
            profile_name="crxzipple",
            target_id="tab-1",
            capture_id="cap-1",
        )

        self.assertEqual(service.list_captures(profile_name="crxzipple"), ())
        with self.assertRaisesRegex(BrowserValidationError, "cap-1"):
            service.list_requests(
                profile_name="crxzipple",
                target_id="tab-1",
                capture_id="cap-1",
            )

    def test_emits_capture_and_request_events(self) -> None:
        emitted: list[tuple[str, dict[str, object]]] = []
        service = self._service(
            event_emitter=lambda event_name, payload: emitted.append((event_name, payload)),
        )

        service.start_capture(
            profile_name="crxzipple",
            target_id="tab-1",
            capture_id="cap-1",
        )
        service.record_request(
            profile_name="crxzipple",
            target_id="tab-1",
            capture_id="cap-1",
            request_id="req-1",
            url="https://example.test/",
            method="GET",
        )
        service.record_failure(
            profile_name="crxzipple",
            target_id="tab-1",
            capture_id="cap-1",
            request_id="req-1",
            failure_text="net::ERR_FAILED",
        )
        service.stop_capture(
            profile_name="crxzipple",
            target_id="tab-1",
            capture_id="cap-1",
        )

        self.assertEqual(
            [event_name for event_name, _payload in emitted],
            [
                "browser.network.capture.started",
                "browser.network.request.observed",
                "browser.network.request.failed",
                "browser.network.capture.stopped",
            ],
        )
        self.assertEqual(emitted[1][1]["request_id"], "req-1")
        self.assertEqual(emitted[2][1]["level"], "warning")
        self.assertEqual(emitted[2][1]["failure_text"], "net::ERR_FAILED")


if __name__ == "__main__":
    unittest.main()
