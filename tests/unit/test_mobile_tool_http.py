from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
import unittest

from crxzipple.modules.mobile.domain import MobileExecutionError, MobileValidationError
from tools.mobile.local import (
    mobile_screenshot,
    mobile_script,
    mobile_snapshot,
    mobile_swipe,
    mobile_tap,
    mobile_type,
)


class MobileToolHttpTestCase(unittest.TestCase):
    def test_mobile_type_handler_requires_ref_or_selector(self) -> None:
        container = SimpleNamespace(
            mobile_facade=SimpleNamespace(),
            mobile_result_serializer=SimpleNamespace(),
        )
        handler = mobile_type(container)
        assert handler is not None

        with self.assertRaises(MobileValidationError) as context:
            asyncio.run(
                handler(
                    {
                        "device": "pixel",
                        "text": "淘宝",
                    }
                )
            )

        self.assertEqual(
            str(context.exception),
            "mobile_type requires ref or selector.",
        )

    def test_mobile_devices_handler_reports_missing_adb_clearly(self) -> None:
        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                return SimpleNamespace(
                    ok=True,
                    device_name=None,
                    message="Unable to inspect Android devices because adb is not available.",
                    command=request,
                    value={
                        "adb_binary": "adb",
                        "adb_available": False,
                        "probe_ok": False,
                        "adb_error": "[Errno 2] No such file or directory: 'adb'",
                        "connected": False,
                        "device_count": 0,
                        "connected_device_count": 0,
                        "devices": [],
                    },
                )

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return {
                    "ok": result.ok,
                    "device_name": result.device_name,
                    "message": result.message,
                    "value": result.value,
                }

        container = SimpleNamespace(
            mobile_facade=_Facade(),
            mobile_result_serializer=_Serializer(),
        )
        from tools.mobile.local import mobile_devices

        handler = mobile_devices(container)
        assert handler is not None

        result = asyncio.run(handler({}))

        self.assertIn("adb", result.blocks[0]["text"])
        self.assertIn("not available", result.blocks[0]["text"])
        self.assertIn("No such file or directory", result.blocks[0]["text"])

    def test_mobile_snapshot_handler_renders_snapshot_text(self) -> None:
        captured_requests: list[object] = []

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                captured_requests.append(request)
                return SimpleNamespace(
                    ok=True,
                    device_name="pixel",
                    message="Captured mobile UI snapshot.",
                    command=request,
                    value={
                        "format": "interactive_text",
                        "snapshot": '- android.widget.EditText "To" [ref=m1]',
                        "text": "To\nSubject\nMessage Body",
                    },
                )

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return {
                    "ok": result.ok,
                    "device_name": result.device_name,
                    "message": result.message,
                    "value": result.value,
                }

        container = SimpleNamespace(
            mobile_facade=_Facade(),
            mobile_result_serializer=_Serializer(),
        )
        handler = mobile_snapshot(container)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "device": "pixel",
                    "format": "interactive_text",
                }
            )
        )

        self.assertEqual(captured_requests[0].kind, "snapshot")
        self.assertEqual(captured_requests[0].payload["format"], "interactive_text")
        self.assertIn("android.widget.EditText", result.blocks[0]["text"])
        self.assertIn("Message Body", result.blocks[0]["text"])

    def test_mobile_screenshot_handler_returns_image_ref_block(self) -> None:
        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                return SimpleNamespace(
                    ok=True,
                    device_name="pixel",
                    message="Captured mobile screenshot.",
                    command=request,
                    value={
                        "artifact_id": "img123",
                        "mime_type": "image/png",
                        "name": "pixel-screenshot.png",
                        "width": 1080,
                        "height": 1920,
                    },
                )

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return {
                    "ok": result.ok,
                    "device_name": result.device_name,
                    "message": result.message,
                    "value": result.value,
                }

        container = SimpleNamespace(
            mobile_facade=_Facade(),
            mobile_result_serializer=_Serializer(),
        )
        handler = mobile_screenshot(container)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "device": "pixel",
                }
            )
        )

        self.assertEqual(result.blocks[0]["type"], "text")
        self.assertEqual(result.blocks[1]["type"], "image_ref")
        self.assertEqual(result.blocks[1]["artifact_id"], "img123")

    def test_mobile_swipe_handler_builds_directional_action_request(self) -> None:
        captured_requests: list[object] = []

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                captured_requests.append(request)
                return SimpleNamespace(
                    ok=True,
                    device_name="pixel",
                    message="Swiped on Android device.",
                    command=request,
                    value={"start_x": 540, "start_y": 1920, "end_x": 540, "end_y": 480},
                )

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return {
                    "ok": result.ok,
                    "device_name": result.device_name,
                    "message": result.message,
                    "value": result.value,
                }

        container = SimpleNamespace(
            mobile_facade=_Facade(),
            mobile_result_serializer=_Serializer(),
        )
        handler = mobile_swipe(container)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "device": "pixel",
                    "direction": "up",
                    "duration_ms": 400,
                }
            )
        )

        self.assertEqual(captured_requests[0].kind, "swipe")
        self.assertEqual(captured_requests[0].payload["direction"], "up")
        self.assertEqual(captured_requests[0].payload["duration_ms"], 400)
        self.assertIn("Swiped on Android device.", result.blocks[0]["text"])

    def test_mobile_tap_handler_appends_post_state_snapshot_by_default(self) -> None:
        captured_requests: list[object] = []

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                captured_requests.append(request)
                if request.kind == "tap":
                    return SimpleNamespace(
                        ok=True,
                        device_name="pixel",
                        message="Tapped mobile UI target.",
                        command=request,
                        value=None,
                    )
                if request.kind == "wait":
                    return SimpleNamespace(
                        ok=True,
                        device_name="pixel",
                        message="Wait condition satisfied on mobile device.",
                        command=request,
                        value=None,
                    )
                if request.kind == "snapshot":
                    return SimpleNamespace(
                        ok=True,
                        device_name="pixel",
                        message="Captured mobile UI snapshot.",
                        command=request,
                        value={
                            "format": request.payload.get("format", "interactive_text"),
                            "snapshot": '- android.widget.Button "Buy now" [ref=g1-m1]',
                            "text": "Buy now\nAdd to cart",
                            "refs": [{"ref": "g1-m1"}],
                        },
                    )
                raise AssertionError(f"unexpected kind: {request.kind}")

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return {
                    "ok": result.ok,
                    "device_name": result.device_name,
                    "message": result.message,
                    "value": result.value,
                }

        container = SimpleNamespace(
            mobile_facade=_Facade(),
            mobile_result_serializer=_Serializer(),
        )
        handler = mobile_tap(container)
        assert handler is not None

        result = asyncio.run(handler({"device": "pixel", "ref": "g1-m1"}))

        self.assertEqual([request.kind for request in captured_requests], ["tap", "wait", "snapshot"])
        self.assertEqual(captured_requests[1].payload["delay_ms"], 200)
        self.assertEqual(captured_requests[2].payload["format"], "interactive_text")
        self.assertIn("Tapped mobile UI target.", result.blocks[0]["text"])
        self.assertEqual(result.blocks[1]["text"], "Post-action stabilize:")
        self.assertIn("Wait condition satisfied on mobile device.", result.blocks[2]["text"])
        self.assertIn('android.widget.Button "Buy now"', result.blocks[3]["text"])
        self.assertEqual(result.details["stabilize"], "micro")
        self.assertIsNotNone(result.details["stabilize_result"])
        self.assertEqual(result.details["observe_after"]["format"], "interactive_text")
        self.assertIsNotNone(result.details["post_state"])

    def test_mobile_tap_handler_can_disable_post_state_snapshot(self) -> None:
        captured_requests: list[object] = []

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                captured_requests.append(request)
                return SimpleNamespace(
                    ok=True,
                    device_name="pixel",
                    message="Tapped mobile UI target.",
                    command=request,
                    value=None,
                )

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return {
                    "ok": result.ok,
                    "device_name": result.device_name,
                    "message": result.message,
                    "value": result.value,
                }

        container = SimpleNamespace(
            mobile_facade=_Facade(),
            mobile_result_serializer=_Serializer(),
        )
        handler = mobile_tap(container)
        assert handler is not None

        result = asyncio.run(
            handler({"device": "pixel", "ref": "g1-m1", "observe_after": False})
        )

        self.assertEqual([request.kind for request in captured_requests], ["tap"])
        self.assertNotIn("post_state", result.details)
        self.assertEqual(len(result.blocks), 1)

    def test_mobile_tap_handler_can_disable_default_stabilize(self) -> None:
        captured_requests: list[object] = []

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                captured_requests.append(request)
                if request.kind == "tap":
                    return SimpleNamespace(
                        ok=True,
                        device_name="pixel",
                        message="Tapped mobile UI target.",
                        command=request,
                        value=None,
                    )
                if request.kind == "snapshot":
                    return SimpleNamespace(
                        ok=True,
                        device_name="pixel",
                        message="Captured mobile UI snapshot.",
                        command=request,
                        value={
                            "format": request.payload.get("format", "interactive_text"),
                            "snapshot": '- android.widget.Button "Buy now" [ref=g1-m1]',
                            "text": "Buy now\nAdd to cart",
                            "refs": [{"ref": "g1-m1"}],
                        },
                    )
                raise AssertionError(f"unexpected kind: {request.kind}")

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return {
                    "ok": result.ok,
                    "device_name": result.device_name,
                    "message": result.message,
                    "value": result.value,
                }

        container = SimpleNamespace(
            mobile_facade=_Facade(),
            mobile_result_serializer=_Serializer(),
        )
        handler = mobile_tap(container)
        assert handler is not None

        result = asyncio.run(
            handler({"device": "pixel", "ref": "g1-m1", "stabilize": "none"})
        )

        self.assertEqual([request.kind for request in captured_requests], ["tap", "snapshot"])
        self.assertEqual(result.details["stabilize"], "none")
        self.assertNotIn("stabilize_result", result.details)

    def test_mobile_tap_handler_reports_post_state_failure_without_failing_action(self) -> None:
        captured_requests: list[object] = []

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                captured_requests.append(request)
                if request.kind == "tap":
                    return SimpleNamespace(
                        ok=True,
                        device_name="pixel",
                        message="Tapped mobile UI target.",
                        command=request,
                        value=None,
                    )
                if request.kind == "wait":
                    return SimpleNamespace(
                        ok=True,
                        device_name="pixel",
                        message="Wait condition satisfied on mobile device.",
                        command=request,
                        value=None,
                    )
                if request.kind == "snapshot":
                    raise MobileExecutionError("snapshot failed")
                raise AssertionError(f"unexpected kind: {request.kind}")

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return {
                    "ok": result.ok,
                    "device_name": result.device_name,
                    "message": result.message,
                    "value": result.value,
                }

        container = SimpleNamespace(
            mobile_facade=_Facade(),
            mobile_result_serializer=_Serializer(),
        )
        handler = mobile_tap(container)
        assert handler is not None

        result = asyncio.run(handler({"device": "pixel", "ref": "g1-m1"}))

        self.assertEqual([request.kind for request in captured_requests], ["tap", "wait", "snapshot"])
        self.assertEqual(result.blocks[1]["text"], "Post-action stabilize:")
        self.assertIn("Wait condition satisfied on mobile device.", result.blocks[2]["text"])
        self.assertIn("Post-action snapshot failed:", result.blocks[3]["text"])
        self.assertEqual(result.details["post_state_error"], "snapshot failed")

    def test_mobile_script_handler_runs_action_steps_and_appends_final_snapshot(self) -> None:
        captured_requests: list[object] = []

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                captured_requests.append(request)
                if request.kind == "press":
                    return SimpleNamespace(
                        ok=True,
                        device_name="pixel",
                        message="Pressed Android key.",
                        command=request,
                        value={"key": request.payload.get("key")},
                    )
                if request.kind == "snapshot":
                    return SimpleNamespace(
                        ok=True,
                        device_name="pixel",
                        message="Captured mobile UI snapshot.",
                        command=request,
                        value={
                            "format": request.payload.get("format", "interactive_text"),
                            "snapshot": '- android.widget.Button "Send" [ref=g1-m1]',
                            "text": "Send\nCancel",
                            "refs": [{"ref": "g1-m1"}],
                        },
                    )
                raise AssertionError(f"unexpected kind: {request.kind}")

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return {
                    "ok": result.ok,
                    "device_name": result.device_name,
                    "message": result.message,
                    "value": result.value,
                }

        container = SimpleNamespace(
            mobile_facade=_Facade(),
            mobile_result_serializer=_Serializer(),
        )
        handler = mobile_script(container)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "device": "pixel",
                    "steps": json.dumps(
                        [
                            {"kind": "press", "key": "ENTER"},
                        ]
                    ),
                    "observe_after": True,
                }
            )
        )

        self.assertEqual(captured_requests[0].kind, "press")
        self.assertEqual(captured_requests[1].kind, "snapshot")
        self.assertIn("Mobile script completed 1 step(s).", result.blocks[0]["text"])
        self.assertIn('android.widget.Button "Send"', result.blocks[1]["text"])
        self.assertEqual(result.details["steps"][0]["kind"], "press")

    def test_mobile_script_handler_supports_step_stabilize_and_observe_after(self) -> None:
        captured_requests: list[object] = []

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                captured_requests.append(request)
                if request.kind == "tap":
                    return SimpleNamespace(
                        ok=True,
                        device_name="pixel",
                        message="Tapped mobile UI target.",
                        command=request,
                        value=None,
                    )
                if request.kind == "wait":
                    return SimpleNamespace(
                        ok=True,
                        device_name="pixel",
                        message="Wait condition satisfied on mobile device.",
                        command=request,
                        value=None,
                    )
                if request.kind == "snapshot":
                    format_name = request.payload.get("format", "interactive_text")
                    if format_name == "text":
                        snapshot_value = "Message Body\nSend"
                    else:
                        snapshot_value = '- android.widget.EditText "Message Body" [ref=m2]'
                    return SimpleNamespace(
                        ok=True,
                        device_name="pixel",
                        message="Captured mobile UI snapshot.",
                        command=request,
                        value={
                            "format": format_name,
                            "snapshot": snapshot_value,
                            "text": "Message Body\nSend",
                            "refs": [{"ref": "g1-m2"}],
                        },
                    )
                raise AssertionError(f"unexpected kind: {request.kind}")

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return {
                    "ok": result.ok,
                    "device_name": result.device_name,
                    "message": result.message,
                    "value": result.value,
                }

        container = SimpleNamespace(
            mobile_facade=_Facade(),
            mobile_result_serializer=_Serializer(),
        )
        handler = mobile_script(container)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "device": "pixel",
                    "default_stabilize": "micro",
                    "default_observe_after": "text",
                    "steps": [
                        {"kind": "tap", "ref": "g1-m1"},
                    ],
                }
            )
        )

        self.assertEqual([request.kind for request in captured_requests], ["tap", "wait", "snapshot"])
        self.assertEqual(captured_requests[1].payload["delay_ms"], 200)
        self.assertEqual(captured_requests[2].payload["format"], "text")
        self.assertEqual(result.details["steps"][0]["stabilize"], "micro")
        self.assertEqual(result.details["steps"][0]["observe_after"], "text")
        self.assertIn("Message Body\nSend", result.blocks[1]["text"])

    def test_mobile_script_rejects_control_steps_in_tool_mode(self) -> None:
        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                raise AssertionError(f"unexpected request: {request}")

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                raise AssertionError(f"unexpected result: {result}")

        container = SimpleNamespace(
            mobile_facade=_Facade(),
            mobile_result_serializer=_Serializer(),
        )
        handler = mobile_script(container)
        assert handler is not None

        with self.assertRaisesRegex(
            Exception,
            "do not expose control or lifecycle steps",
        ):
            asyncio.run(
                handler(
                    {
                        "device": "pixel",
                        "steps": [{"family": "control", "kind": "launch-app"}],
                    }
                )
            )
