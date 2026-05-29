from __future__ import annotations

from types import SimpleNamespace

from crxzipple.interfaces.runtime_container import AppKey
from tests.unit.cli_test_support import *

from crxzipple.modules.mobile.domain import (
    MobileActionCommand,
    MobileActionResult,
    MobileActionTarget,
    MobileControlCommand,
)
from crxzipple.modules.mobile.interfaces.serializers import MobileResultSerializer


class _StaticMobileConfigStore:
    def __init__(self, default_device: str | None = "pixel") -> None:
        self._config = SimpleNamespace(default_device=default_device)

    def load(self):  # noqa: ANN201
        return self._config


class _MobileCliContainer:
    def __init__(self, *, facade: object, serializer: object, config_store: object) -> None:
        self._values = {
            AppKey.MOBILE_FACADE: facade,
            AppKey.MOBILE_RESULT_SERIALIZER: serializer,
            AppKey.MOBILE_SYSTEM_CONFIG_STORE: config_store,
        }

    def require(self, key: AppKey) -> object:
        return self._values[key]


class MobileCliTestCase(CliModuleTestCase):
    def test_mobile_control_command_returns_serialized_result(self) -> None:
        captured_requests: list[object] = []

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
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

        container = _MobileCliContainer(
            facade=_Facade(),
            serializer=MobileResultSerializer(),
            config_store=_StaticMobileConfigStore("pixel"),
        )

        with patch(
            "crxzipple.modules.mobile.interfaces.cli.ensure_container",
            return_value=container,
        ):
            result = self.runner.invoke(
                app,
                [
                    "mobile",
                    "control",
                    "launch-app",
                    "--payload",
                    '{"app_package":"com.google.android.gm","app_activity":".ComposeActivity"}',
                ],
                env=self.env,
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["device_name"], "pixel")
        self.assertEqual(payload["command"]["kind"], "launch-app")
        self.assertEqual(
            captured_requests[0].payload["app_package"],
            "com.google.android.gm",
        )

    def test_mobile_act_command_returns_serialized_snapshot(self) -> None:
        captured_requests: list[object] = []

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
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
                    value={"snapshot": '- android.widget.Button "Send" [ref=m1]'},
                )

        container = _MobileCliContainer(
            facade=_Facade(),
            serializer=MobileResultSerializer(),
            config_store=_StaticMobileConfigStore("pixel"),
        )

        with patch(
            "crxzipple.modules.mobile.interfaces.cli.ensure_container",
            return_value=container,
        ):
            result = self.runner.invoke(
                app,
                [
                    "mobile",
                    "act",
                    "snapshot",
                    "--payload",
                    '{"format":"interactive"}',
                ],
                env=self.env,
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["command"]["kind"], "snapshot")
        self.assertEqual(captured_requests[0].payload["format"], "interactive")
