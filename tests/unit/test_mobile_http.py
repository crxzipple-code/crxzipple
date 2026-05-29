from __future__ import annotations

from tests.unit.http_test_support import *

from crxzipple.modules.mobile.domain import (
    MobileActionCommand,
    MobileActionResult,
    MobileActionTarget,
    MobileControlCommand,
)


class MobileHttpTestCase(HttpModuleTestCase):
    def test_mobile_control_endpoint_uses_mobile_facade_and_serializer(self) -> None:
        captured_requests: list[object] = []
        container = self.client.app.state.container

        def _execute(request):  # noqa: ANN001, ANN202
            captured_requests.append(request)
            return MobileActionResult(
                ok=True,
                device_name=request.device_name,
                message="Launched Android app activity.",
                command=MobileControlCommand(
                    device_name=request.device_name,
                    kind=request.kind,
                    payload=request.payload,
                    timeout_ms=request.timeout_ms,
                ),
                value={"app_package": "com.google.android.gm", "app_activity": ".ComposeActivity"},
            )

        with patch.object(
            type(container.require(AppKey.MOBILE_FACADE)),
            "execute",
            autospec=True,
            side_effect=lambda _self, request: _execute(request),
        ):
            response = self.client.post(
                "/mobile/control",
                json={
                    "device_name": "pixel",
                    "kind": "launch-app",
                    "payload": {
                        "app_package": "com.google.android.gm",
                        "app_activity": ".ComposeActivity",
                    },
                    "timeout_ms": 45000,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["device_name"], "pixel")
        self.assertEqual(payload["command"]["family"], "control")
        self.assertEqual(
            captured_requests[0].payload["app_package"],
            "com.google.android.gm",
        )

    def test_mobile_actions_endpoint_serializes_snapshot_result(self) -> None:
        captured_requests: list[object] = []
        container = self.client.app.state.container

        def _execute(request):  # noqa: ANN001, ANN202
            captured_requests.append(request)
            return MobileActionResult(
                ok=True,
                device_name=request.device_name,
                message="Captured mobile UI snapshot.",
                command=MobileActionCommand(
                    device_name=request.device_name,
                    kind=request.kind,
                    target=MobileActionTarget(
                        ref=request.ref,
                        selector=request.selector,
                    ),
                    payload=request.payload,
                    timeout_ms=request.timeout_ms,
                ),
                value={
                    "format": "interactive_text",
                    "snapshot": '- android.widget.EditText "To" [ref=m1]',
                    "text": "To\nSubject\nMessage Body",
                    "refs": [],
                },
            )

        with patch.object(
            type(container.require(AppKey.MOBILE_FACADE)),
            "execute",
            autospec=True,
            side_effect=lambda _self, request: _execute(request),
        ):
            response = self.client.post(
                "/mobile/actions",
                json={
                    "device_name": "pixel",
                    "kind": "snapshot",
                    "payload": {"format": "interactive_text"},
                    "timeout_ms": 30000,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"]["family"], "action")
        self.assertEqual(payload["command"]["kind"], "snapshot")
        self.assertEqual(payload["value"]["format"], "interactive_text")
        self.assertIsNone(captured_requests[0].ref)
