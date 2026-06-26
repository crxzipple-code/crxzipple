from __future__ import annotations

from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from crxzipple.modules.mobile.application import (
    DefaultMobileActionCommandAssembler,
    DefaultMobileControlCommandAssembler,
)
from crxzipple.modules.mobile.domain import (
    MobileActionCommand,
    MobileActionTarget,
    MobileDeviceCapabilities,
    MobileDeviceRuntimeState,
    MobileExecutionError,
    MobileExecutionPlan,
    MobileStoredRef,
    MobileSystemConfig,
    MobileValidationError,
    ResolvedMobileDevice,
)
from crxzipple.modules.mobile.infrastructure import (
    AdbBackedMobileActionEngine,
    AdbControlEngine,
    AndroidAdbClient,
    AndroidUiDump,
    FileBackedMobileRefStore,
)
from crxzipple.modules.ocr.domain import OcrPoint, OcrResult, OcrTextBlock


class MobileDomainTestCase(unittest.TestCase):
    def test_action_command_assembler_no_longer_accepts_session_state(self) -> None:
        assembler = DefaultMobileActionCommandAssembler()

        command = assembler.assemble(
            device_name="pixel",
            kind="tap",
            ref="g1-m1",
            selector=None,
            payload={"foo": "bar"},
            timeout_ms=15_000,
        )

        self.assertEqual(command.device_name, "pixel")
        self.assertEqual(command.target.ref, "g1-m1")
        self.assertIsNone(command.target.selector)
        self.assertEqual(command.payload["foo"], "bar")

    def test_runtime_state_tracks_snapshot_generations(self) -> None:
        state = MobileDeviceRuntimeState(device_name="pixel")

        self.assertEqual(state.next_ref_generation(), 1)
        state.remember_snapshot(
            generation=1,
            ref_count=4,
            snapshot_format="interactive_text",
            package_name="com.android.launcher",
            activity_name=".Launcher",
            source_length=1024,
        )

        self.assertEqual(state.current_ref_generation, 1)
        self.assertEqual(state.last_known_package, "com.android.launcher")
        self.assertEqual(state.last_known_activity, ".Launcher")
        self.assertEqual(state.last_snapshot_ref_count, 4)
        self.assertEqual(state.last_snapshot_source_length, 1024)
        self.assertEqual(state.next_ref_generation(), 2)

    def test_ref_store_round_trip_is_scoped_by_generation(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = FileBackedMobileRefStore(Path(tmpdir))
            refs = (
                MobileStoredRef(
                    ref="g2-m1",
                    generation=2,
                    text="Send",
                    bounds=(0, 0, 100, 100),
                ),
            )

            store.save_refs(device_name="pixel", generation=2, refs=refs)

            self.assertEqual(store.get_refs(device_name="pixel", generation=2), refs)
            self.assertEqual(store.get_refs(device_name="pixel", generation=1), ())

    def test_adb_snapshot_engine_persists_generation_scoped_refs(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = FileBackedMobileRefStore(Path(tmpdir))
            engine = AdbBackedMobileActionEngine(ref_store=store)
            runtime_state = MobileDeviceRuntimeState(device_name="pixel")
            plan = MobileExecutionPlan(
                system=MobileSystemConfig(adb_binary="adb"),
                device=ResolvedMobileDevice(
                    name="pixel",
                    platform="android",
                    udid="serial-1",
                    app_package="com.android.launcher",
                    app_activity=".Launcher",
                ),
                capabilities=MobileDeviceCapabilities(
                    mode="adb-android",
                    control_family="adb-control",
                    action_family="adb-backed",
                ),
                command=MobileActionCommand(
                    device_name="pixel",
                    kind="snapshot",
                    payload={"format": "interactive_text"},
                    timeout_ms=15_000,
                ),
            )

            class _FakeClient:
                def capture_ui_xml(self) -> AndroidUiDump:
                    return AndroidUiDump(
                        xml=(
                            "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>"
                            "<hierarchy>"
                            "<node class='android.widget.FrameLayout' text='' clickable='false' bounds='[0,0][100,100]'>"
                            "<node class='android.widget.Button' text='Send' clickable='true' bounds='[10,10][90,40]' />"
                            "</node>"
                            "</hierarchy>"
                        ),
                        root_package="com.android.launcher",
                        current_package="com.android.launcher",
                        current_activity=".Launcher",
                        mitigations_applied=(),
                    )

            with patch(
                "crxzipple.modules.mobile.infrastructure.engines._make_client",
                return_value=_FakeClient(),
            ):
                result, updated_state = engine.execute(
                    plan=plan,
                    runtime_state=runtime_state,
                )

            self.assertTrue(result.ok)
            self.assertEqual(result.value["generation"], 1)
            self.assertEqual(result.value["ref_count"], 1)
            self.assertEqual(updated_state.current_ref_generation, 1)
            saved_refs = store.get_refs(device_name="pixel", generation=1)
            self.assertEqual(len(saved_refs), 1)
            self.assertEqual(saved_refs[0].ref, "g1-m1")

    def test_adb_snapshot_prunes_previous_generation_refs(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = FileBackedMobileRefStore(Path(tmpdir))
            engine = AdbBackedMobileActionEngine(ref_store=store)
            runtime_state = MobileDeviceRuntimeState(device_name="pixel")
            plan = MobileExecutionPlan(
                system=MobileSystemConfig(adb_binary="adb"),
                device=ResolvedMobileDevice(
                    name="pixel",
                    platform="android",
                    udid="serial-1",
                    app_package="com.android.launcher",
                    app_activity=".Launcher",
                ),
                capabilities=MobileDeviceCapabilities(
                    mode="adb-android",
                    control_family="adb-control",
                    action_family="adb-backed",
                ),
                command=MobileActionCommand(
                    device_name="pixel",
                    kind="snapshot",
                    payload={"format": "interactive_text"},
                    timeout_ms=15_000,
                ),
            )

            class _FakeClient:
                call_count = 0

                def capture_ui_xml(self) -> AndroidUiDump:
                    self.call_count += 1
                    text = f"Send {self.call_count}"
                    return AndroidUiDump(
                        xml=(
                            "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>"
                            "<hierarchy>"
                            "<node class='android.widget.FrameLayout' text='' clickable='false' bounds='[0,0][100,100]'>"
                            f"<node class='android.widget.Button' text='{text}' clickable='true' bounds='[10,10][90,40]' />"
                            "</node>"
                            "</hierarchy>"
                        ),
                        root_package="com.android.launcher",
                        current_package="com.android.launcher",
                        current_activity=".Launcher",
                        mitigations_applied=(),
                    )

            fake_client = _FakeClient()
            with patch(
                "crxzipple.modules.mobile.infrastructure.engines._make_client",
                return_value=fake_client,
            ):
                first_result, runtime_state = engine.execute(
                    plan=plan,
                    runtime_state=runtime_state,
                )
                second_result, runtime_state = engine.execute(
                    plan=plan,
                    runtime_state=runtime_state,
                )

            self.assertEqual(first_result.value["generation"], 1)
            self.assertEqual(second_result.value["generation"], 2)
            self.assertEqual(store.get_refs(device_name="pixel", generation=1), ())
            second_refs = store.get_refs(device_name="pixel", generation=2)
            self.assertEqual(len(second_refs), 1)
            self.assertEqual(second_refs[0].ref, "g2-m1")

    def test_adb_screenshot_returns_artifact_ref_without_inline_image_bytes(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = FileBackedMobileRefStore(Path(tmpdir))

            class _FakeArtifactService:
                def create_artifact(self, **kwargs):  # noqa: ANN003, ANN202
                    self.last_payload = dict(kwargs)
                    return SimpleNamespace(
                        id="artifact-screenshot-1",
                        mime_type="image/png",
                        name="pixel-screenshot.png",
                        width=100,
                        height=200,
                    )

            artifact_service = _FakeArtifactService()
            engine = AdbBackedMobileActionEngine(
                ref_store=store,
                artifact_service=artifact_service,
            )
            runtime_state = MobileDeviceRuntimeState(device_name="pixel")
            plan = MobileExecutionPlan(
                system=MobileSystemConfig(adb_binary="adb"),
                device=ResolvedMobileDevice(
                    name="pixel",
                    platform="android",
                    udid="serial-1",
                ),
                capabilities=MobileDeviceCapabilities(
                    mode="adb-android",
                    control_family="adb-control",
                    action_family="adb-backed",
                ),
                command=MobileActionCommand(
                    device_name="pixel",
                    kind="screenshot",
                    timeout_ms=15_000,
                ),
            )

            class _FakeClient:
                def take_screenshot(self) -> bytes:
                    return b"fake-png-bytes"

            with patch(
                "crxzipple.modules.mobile.infrastructure.engines._make_client",
                return_value=_FakeClient(),
            ):
                result, _ = engine.execute(plan=plan, runtime_state=runtime_state)

            self.assertTrue(result.ok)
            self.assertEqual(artifact_service.last_payload["data"], b"fake-png-bytes")
            self.assertEqual(result.value["artifact_id"], "artifact-screenshot-1")
            self.assertEqual(result.value["mime_type"], "image/png")
            self.assertNotIn("data", result.value)
            self.assertNotIn("image_bytes", result.value)

    def test_adb_snapshot_falls_back_to_ocr_and_returns_generation_scoped_refs(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = FileBackedMobileRefStore(Path(tmpdir))

            class _FakeArtifactService:
                def create_artifact(self, **kwargs):  # noqa: ANN003, ANN202
                    self.last_payload = dict(kwargs)
                    return SimpleNamespace(id="artifact-1")

            class _FakeOcrService:
                def analyze_artifact(self, **kwargs):  # noqa: ANN003, ANN202
                    self.last_payload = dict(kwargs)
                    return OcrResult(
                        backend="ppstructurev3",
                        language="ch",
                        artifact_id="artifact-1",
                        variant="original",
                        image_width=1080,
                        image_height=2400,
                        blocks=(
                            OcrTextBlock(
                                text="微信(322)",
                                confidence=0.99,
                                polygon=(
                                    OcrPoint(422, 33),
                                    OcrPoint(647, 33),
                                    OcrPoint(647, 121),
                                    OcrPoint(422, 121),
                                ),
                            ),
                            OcrTextBlock(
                                text="腾讯新闻",
                                confidence=0.98,
                                polygon=(
                                    OcrPoint(180, 183),
                                    OcrPoint(386, 183),
                                    OcrPoint(386, 263),
                                    OcrPoint(180, 263),
                                ),
                            ),
                        ),
                    )

            engine = AdbBackedMobileActionEngine(
                ref_store=store,
                artifact_service=_FakeArtifactService(),
                ocr_service=_FakeOcrService(),
            )
            runtime_state = MobileDeviceRuntimeState(device_name="pixel")
            plan = MobileExecutionPlan(
                system=MobileSystemConfig(adb_binary="adb"),
                device=ResolvedMobileDevice(
                    name="pixel",
                    platform="android",
                    udid="serial-1",
                ),
                capabilities=MobileDeviceCapabilities(
                    mode="adb-android",
                    control_family="adb-control",
                    action_family="adb-backed",
                ),
                command=MobileActionCommand(
                    device_name="pixel",
                    kind="snapshot",
                    payload={"format": "interactive_text"},
                    timeout_ms=15_000,
                ),
            )

            class _FakeClient:
                def capture_ui_xml(self) -> AndroidUiDump:
                    raise MobileExecutionError("adb uiautomator dump failed")

                def take_screenshot(self) -> bytes:
                    return b"fake-png"

                def current_focus(self) -> dict[str, str | None]:
                    return {
                        "package": "com.tencent.mm",
                        "activity": "com.tencent.mm.ui.LauncherUI",
                        "raw": "",
                    }

            with patch(
                "crxzipple.modules.mobile.infrastructure.engines._make_client",
                return_value=_FakeClient(),
            ):
                result, updated_state = engine.execute(
                    plan=plan,
                    runtime_state=runtime_state,
                )

            self.assertTrue(result.ok)
            self.assertEqual(result.value["observation_mode"], "ocr")
            self.assertEqual(result.value["ocr_artifact_id"], "artifact-1")
            self.assertEqual(result.value["generation"], 1)
            self.assertEqual(result.value["ref_count"], 2)
            self.assertEqual(result.value["current_package"], "com.tencent.mm")
            self.assertEqual(result.value["current_activity"], "com.tencent.mm.ui.LauncherUI")
            self.assertIn('ocr.block "微信(322)" [ref=g1-m1]', result.value["snapshot"])
            self.assertIn('ocr.block "腾讯新闻" [ref=g1-m2]', result.value["snapshot"])
            saved_refs = store.get_refs(device_name="pixel", generation=1)
            self.assertEqual(len(saved_refs), 2)
            self.assertEqual(saved_refs[0].ref, "g1-m1")
            self.assertEqual(saved_refs[0].bounds, (422, 33, 647, 121))
            self.assertEqual(updated_state.current_ref_generation, 1)

    def test_adb_snapshot_uses_ocr_when_ui_tree_is_low_quality(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = FileBackedMobileRefStore(Path(tmpdir))

            class _FakeArtifactService:
                def create_artifact(self, **kwargs):  # noqa: ANN003, ANN202
                    self.last_payload = dict(kwargs)
                    return SimpleNamespace(id="artifact-2")

            class _FakeOcrService:
                def analyze_artifact(self, **kwargs):  # noqa: ANN003, ANN202
                    self.last_payload = dict(kwargs)
                    return OcrResult(
                        backend="ppstructurev3",
                        language="ch",
                        artifact_id="artifact-2",
                        variant="original",
                        image_width=1080,
                        image_height=2400,
                        blocks=(
                            OcrTextBlock(
                                text="微信(322)",
                                confidence=0.99,
                                polygon=(
                                    OcrPoint(422, 33),
                                    OcrPoint(647, 33),
                                    OcrPoint(647, 121),
                                    OcrPoint(422, 121),
                                ),
                            ),
                            OcrTextBlock(
                                text="腾讯新闻",
                                confidence=0.98,
                                polygon=(
                                    OcrPoint(180, 183),
                                    OcrPoint(386, 183),
                                    OcrPoint(386, 263),
                                    OcrPoint(180, 263),
                                ),
                            ),
                        ),
                    )

            engine = AdbBackedMobileActionEngine(
                ref_store=store,
                artifact_service=_FakeArtifactService(),
                ocr_service=_FakeOcrService(),
            )
            runtime_state = MobileDeviceRuntimeState(device_name="pixel")
            plan = MobileExecutionPlan(
                system=MobileSystemConfig(adb_binary="adb"),
                device=ResolvedMobileDevice(
                    name="pixel",
                    platform="android",
                    udid="serial-1",
                ),
                capabilities=MobileDeviceCapabilities(
                    mode="adb-android",
                    control_family="adb-control",
                    action_family="adb-backed",
                ),
                command=MobileActionCommand(
                    device_name="pixel",
                    kind="snapshot",
                    payload={"format": "interactive_text"},
                    timeout_ms=15_000,
                ),
            )

            class _FakeClient:
                def capture_ui_xml(self) -> AndroidUiDump:
                    return AndroidUiDump(
                        xml=(
                            "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>"
                            "<hierarchy rotation='0'>"
                            "<node index='0' text='' resource-id='' class='' package='com.tencent.mm'"
                            " bounds='[0,0][0,0]'/>"
                            "</hierarchy>"
                        ),
                        root_package="com.tencent.mm",
                        current_package="com.tencent.mm",
                        current_activity="com.tencent.mm.ui.LauncherUI",
                        mitigations_applied=(),
                    )

                def take_screenshot(self) -> bytes:
                    return b"fake-png"

                def current_focus(self) -> dict[str, str | None]:
                    return {
                        "package": "com.tencent.mm",
                        "activity": "com.tencent.mm.ui.LauncherUI",
                        "raw": "",
                    }

            with patch(
                "crxzipple.modules.mobile.infrastructure.engines._make_client",
                return_value=_FakeClient(),
            ):
                result, updated_state = engine.execute(
                    plan=plan,
                    runtime_state=runtime_state,
                )

            self.assertTrue(result.ok)
            self.assertEqual(result.value["observation_mode"], "ocr")
            self.assertEqual(result.value["ocr_artifact_id"], "artifact-2")
            self.assertEqual(result.value["generation"], 1)
            self.assertEqual(result.value["ref_count"], 2)
            self.assertEqual(result.value["current_package"], "com.tencent.mm")
            self.assertEqual(result.value["current_activity"], "com.tencent.mm.ui.LauncherUI")
            self.assertIn('ocr.block "微信(322)" [ref=g1-m1]', result.value["snapshot"])
            self.assertIn('ocr.block "腾讯新闻" [ref=g1-m2]', result.value["snapshot"])
            self.assertEqual(updated_state.metadata["last_snapshot_fallback_error"], "low_quality_ui_tree")
            saved_refs = store.get_refs(device_name="pixel", generation=1)
            self.assertEqual(len(saved_refs), 2)
            self.assertEqual(saved_refs[1].ref, "g1-m2")
            self.assertEqual(updated_state.current_ref_generation, 1)

    def test_adb_snapshot_ocr_fallback_augments_snapshot_with_vision_candidates(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = FileBackedMobileRefStore(Path(tmpdir))

            class _FakeArtifactService:
                def create_artifact(self, **kwargs):  # noqa: ANN003, ANN202
                    return SimpleNamespace(id="artifact-3")

            class _FakeOcrService:
                def analyze_artifact(self, **kwargs):  # noqa: ANN003, ANN202
                    return OcrResult(
                        backend="ppstructurev3",
                        language="ch",
                        artifact_id="artifact-3",
                        variant="original",
                        image_width=1080,
                        image_height=2400,
                        blocks=(
                            OcrTextBlock(
                                text="搜索",
                                confidence=0.99,
                                polygon=(
                                    OcrPoint(120, 120),
                                    OcrPoint(200, 120),
                                    OcrPoint(200, 160),
                                    OcrPoint(120, 160),
                                ),
                            ),
                        ),
                    )

            engine = AdbBackedMobileActionEngine(
                ref_store=store,
                artifact_service=_FakeArtifactService(),
                ocr_service=_FakeOcrService(),
            )
            runtime_state = MobileDeviceRuntimeState(device_name="pixel")
            plan = MobileExecutionPlan(
                system=MobileSystemConfig(adb_binary="adb"),
                device=ResolvedMobileDevice(
                    name="pixel",
                    platform="android",
                    udid="serial-1",
                ),
                capabilities=MobileDeviceCapabilities(
                    mode="adb-android",
                    control_family="adb-control",
                    action_family="adb-backed",
                ),
                command=MobileActionCommand(
                    device_name="pixel",
                    kind="snapshot",
                    payload={"format": "interactive_text"},
                    timeout_ms=15_000,
                ),
            )

            class _FakeClient:
                def capture_ui_xml(self) -> AndroidUiDump:
                    raise MobileExecutionError("adb uiautomator dump failed")

                def take_screenshot(self) -> bytes:
                    return b"fake-png"

                def current_focus(self) -> dict[str, str | None]:
                    return {
                        "package": "com.android.launcher",
                        "activity": ".Launcher",
                        "raw": "",
                    }

            with (
                patch(
                    "crxzipple.modules.mobile.infrastructure.engines._make_client",
                    return_value=_FakeClient(),
                ),
                patch(
                    "crxzipple.modules.mobile.infrastructure.mobile_snapshot_actions.detect_visual_layout_candidates",
                    return_value=(
                        SimpleNamespace(
                            kind="vision.input",
                            bounds=(80, 96, 1000, 192),
                            label="搜索",
                            score=0.95,
                        ),
                        SimpleNamespace(
                            kind="vision.button",
                            bounds=(820, 2100, 1040, 2200),
                            label="立即购买",
                            score=0.91,
                        ),
                    ),
                ),
            ):
                result, updated_state = engine.execute(
                    plan=plan,
                    runtime_state=runtime_state,
                )

            self.assertTrue(result.ok)
            self.assertEqual(result.value["observation_mode"], "ocr")
            self.assertEqual(result.value["ref_count"], 3)
            self.assertIn('vision.input "搜索" [ref=g1-m2]', result.value["snapshot"])
            self.assertIn('vision.button "立即购买" [ref=g1-m3]', result.value["snapshot"])
            saved_refs = store.get_refs(device_name="pixel", generation=1)
            self.assertEqual(saved_refs[1].class_name, "vision.input")
            self.assertEqual(saved_refs[1].focusable, True)
            self.assertEqual(saved_refs[2].class_name, "vision.button")
            self.assertEqual(updated_state.current_ref_generation, 1)

    def test_adb_tap_rejects_stale_ref_generations(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = FileBackedMobileRefStore(Path(tmpdir))
            store.save_refs(
                device_name="pixel",
                generation=1,
                refs=(
                    MobileStoredRef(
                        ref="g1-m1",
                        generation=1,
                        text="Send",
                        bounds=(10, 10, 90, 40),
                    ),
                ),
            )
            engine = AdbBackedMobileActionEngine(ref_store=store)
            runtime_state = MobileDeviceRuntimeState(device_name="pixel")
            runtime_state.remember_snapshot(
                generation=2,
                ref_count=0,
                snapshot_format="interactive_text",
            )
            tap_plan = MobileExecutionPlan(
                system=MobileSystemConfig(adb_binary="adb"),
                device=ResolvedMobileDevice(name="pixel", platform="android", udid="serial-1"),
                capabilities=MobileDeviceCapabilities(
                    mode="adb-android",
                    control_family="adb-control",
                    action_family="adb-backed",
                ),
                command=MobileActionCommand(
                    device_name="pixel",
                    kind="tap",
                    payload={},
                    timeout_ms=5_000,
                    target=MobileActionTarget(ref="g1-m1"),
                ),
            )

            class _FakeClient:
                def tap(self, *, x: int, y: int) -> None:
                    raise AssertionError(f"unexpected tap at {(x, y)}")

            with patch(
                "crxzipple.modules.mobile.infrastructure.engines._make_client",
                return_value=_FakeClient(),
            ):
                with self.assertRaisesRegex(MobileValidationError, "stale"):
                    engine.execute(
                        plan=tap_plan,
                        runtime_state=runtime_state,
                    )

    def test_adb_swipe_supports_directional_fullscreen_swipe(self) -> None:
        engine = AdbBackedMobileActionEngine(ref_store=FileBackedMobileRefStore(Path(TemporaryDirectory().name)))
        runtime_state = MobileDeviceRuntimeState(device_name="pixel")
        plan = MobileExecutionPlan(
            system=MobileSystemConfig(adb_binary="adb"),
            device=ResolvedMobileDevice(name="pixel", platform="android", udid="serial-1"),
            capabilities=MobileDeviceCapabilities(
                mode="adb-android",
                control_family="adb-control",
                action_family="adb-backed",
            ),
            command=MobileActionCommand(
                device_name="pixel",
                kind="swipe",
                payload={"direction": "up", "duration_ms": 450},
                timeout_ms=5_000,
            ),
        )
        swipes: list[tuple[int, int, int, int, int | None]] = []

        class _FakeClient:
            def display_size(self):  # noqa: ANN201
                return SimpleNamespace(width=1080, height=2400)

            def swipe(
                self,
                *,
                start_x: int,
                start_y: int,
                end_x: int,
                end_y: int,
                duration_ms: int | None = None,
            ) -> None:
                swipes.append((start_x, start_y, end_x, end_y, duration_ms))

        with patch(
            "crxzipple.modules.mobile.infrastructure.engines._make_client",
            return_value=_FakeClient(),
        ):
            result, updated_state = engine.execute(plan=plan, runtime_state=runtime_state)

        self.assertTrue(result.ok)
        self.assertEqual(swipes, [(540, 1920, 540, 480, 450)])
        self.assertIs(updated_state, runtime_state)

    def test_adb_client_input_text_uses_adb_keyboard_b64_for_non_ascii(self) -> None:
        calls: list[list[str]] = []

        class _FakeClient(AndroidAdbClient):
            def _run(  # type: ignore[override]
                self,
                args: list[str],
                *,
                timeout_seconds: float | None = None,
                text: bool = True,
            ) -> str | bytes:
                del timeout_seconds, text
                calls.append(list(args))
                if args == ["shell", "ime", "list", "-s"]:
                    return "com.android.adbkeyboard/.AdbIME\ncom.baidu.input_vivo/.ImeVivoService\n"
                return ""

            def _get_secure_setting(self, key: str) -> str | None:  # type: ignore[override]
                if key == "default_input_method":
                    return "com.baidu.input_vivo/.ImeVivoService"
                raise AssertionError(f"unexpected key: {key}")

            def _run_completed(  # type: ignore[override]
                self,
                args: list[str],
                *,
                timeout_seconds: float | None = None,
                text: bool = True,
                check: bool = True,
            ):
                del timeout_seconds, text, check
                calls.append(list(args))
                return SimpleNamespace(returncode=0, stdout="", stderr="")

        client = _FakeClient(adb_binary="adb", device_serial="serial-1")

        client.input_text("你好")

        self.assertEqual(
            calls,
            [
                ["shell", "ime", "list", "-s"],
                ["shell", "ime", "set", "com.android.adbkeyboard/.AdbIME"],
                ["shell", "am", "broadcast", "-a", "ADB_INPUT_B64", "--es", "msg", "5L2g5aW9"],
                ["shell", "ime", "set", "com.baidu.input_vivo/.ImeVivoService"],
            ],
        )

    def test_adb_client_truncates_large_command_failure_output(self) -> None:
        client = AndroidAdbClient(adb_binary="adb", device_serial="serial-1")
        stderr = "x" * 3_000

        with patch(
            "crxzipple.modules.mobile.infrastructure.adb_client.subprocess.run",
            side_effect=subprocess.CalledProcessError(
                returncode=1,
                cmd=["adb", "-s", "serial-1", "shell", "bad"],
                stderr=stderr,
            ),
        ):
            with self.assertRaises(MobileExecutionError) as context:
                client._run(["shell", "bad"])

        message = str(context.exception)
        self.assertIn("[truncated", message)
        self.assertLess(len(message), 2_100)

    def test_adb_client_reports_command_timeout(self) -> None:
        client = AndroidAdbClient(adb_binary="adb", device_serial="serial-1")

        with patch(
            "crxzipple.modules.mobile.infrastructure.adb_client.subprocess.run",
            side_effect=subprocess.TimeoutExpired(
                cmd=["adb", "-s", "serial-1", "shell", "sleep"],
                timeout=0.5,
            ),
        ):
            with self.assertRaisesRegex(MobileExecutionError, "timed out after 0.5"):
                client._run(["shell", "sleep"], timeout_seconds=0.5)

    def test_adb_device_probe_truncates_large_failure_output(self) -> None:
        stderr = "device-error\n" + ("x" * 3_000)

        with patch(
            "crxzipple.modules.mobile.infrastructure.adb_client.subprocess.run",
            side_effect=subprocess.CalledProcessError(
                returncode=1,
                cmd=["adb", "devices", "-l"],
                stderr=stderr,
            ),
        ):
            result = AndroidAdbClient.probe_adb_devices(adb_binary="adb")

        self.assertTrue(result["adb_available"])
        self.assertFalse(result["probe_ok"])
        self.assertIn("[truncated", str(result["adb_error"]))
        self.assertLess(len(str(result["adb_error"])), 2_100)

    def test_adb_client_press_key_combination_uses_input_keycombination(self) -> None:
        calls: list[list[str]] = []

        class _FakeClient(AndroidAdbClient):
            def _run(  # type: ignore[override]
                self,
                args: list[str],
                *,
                timeout_seconds: float | None = None,
                text: bool = True,
            ) -> str | bytes:
                del timeout_seconds, text
                calls.append(list(args))
                return ""

        client = _FakeClient(adb_binary="adb", device_serial="serial-1")

        client.press_key_combination(keycodes=(113, 29))

        self.assertEqual(
            calls,
            [["shell", "input", "keycombination", "113", "29"]],
        )

    def test_adb_client_wait_for_input_connection_matches_served_view_resource_id(self) -> None:
        case = self
        responses = iter(
            (
                "mServedInputConnection=null\n",
                (
                    "mServedInputConnection=RemoteInputConnectionImpl{finished=false "
                    "mServedView=com.bbk.launcher2.ui.allapps.ExtendedEditText{ "
                    "#7f0a0412 app:id/search_edit_text}}\n"
                ),
            )
        )

        class _FakeClient(AndroidAdbClient):
            def _run(  # type: ignore[override]
                self,
                args: list[str],
                *,
                timeout_seconds: float | None = None,
                text: bool = True,
            ) -> str | bytes:
                del timeout_seconds, text
                case.assertEqual(args, ["shell", "dumpsys", "input_method"])
                return next(responses)

        client = _FakeClient(adb_binary="adb", device_serial="serial-1")

        self.assertTrue(
            client.wait_for_input_connection(
                expected_resource_id="com.bbk.launcher2:id/search_edit_text",
                timeout_seconds=0.2,
                poll_seconds=0.01,
            )
        )

    def test_adb_type_clears_via_select_all_then_delete(self) -> None:
        engine = AdbBackedMobileActionEngine(ref_store=FileBackedMobileRefStore(Path(TemporaryDirectory().name)))
        runtime_state = MobileDeviceRuntimeState(device_name="pixel")
        runtime_state.remember_snapshot(
            generation=1,
            ref_count=1,
            snapshot_format="interactive_text",
        )
        engine.ref_store.save_refs(
            device_name="pixel",
            generation=1,
            refs=(
                MobileStoredRef(
                    ref="g1-m1",
                    generation=1,
                    text="旧内容",
                    class_name="android.widget.EditText",
                    resource_id="com.bbk.launcher2:id/search_edit_text",
                    bounds=(100, 200, 900, 300),
                ),
            ),
        )
        plan = MobileExecutionPlan(
            system=MobileSystemConfig(adb_binary="adb"),
            device=ResolvedMobileDevice(name="pixel", platform="android", udid="serial-1"),
            capabilities=MobileDeviceCapabilities(
                mode="adb-android",
                control_family="adb-control",
                action_family="adb-backed",
            ),
            command=MobileActionCommand(
                device_name="pixel",
                kind="type",
                payload={"text": "你好", "clear": True},
                timeout_ms=5_000,
                target=MobileActionTarget(ref="g1-m1"),
            ),
        )
        operations: list[tuple[str, object]] = []

        class _FakeClient:
            def tap(self, *, x: int, y: int) -> None:
                operations.append(("tap", (x, y)))

            def wait_for_input_connection(
                self,
                *,
                expected_resource_id: str | None = None,
                timeout_seconds: float = 0.8,
            ) -> bool:
                operations.append(("wait_for_input_connection", expected_resource_id, timeout_seconds))
                return True

            def press_key_combination(self, *, keycodes: tuple[int, ...]) -> None:
                operations.append(("keycombination", keycodes))

            def press_keycode(self, *, keycode: int) -> None:
                operations.append(("keyevent", keycode))

            def input_text(self, text: str) -> None:
                operations.append(("input_text", text))

            def dump_ui_xml(self) -> str:
                return """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node index="0" text="你好" resource-id="com.bbk.launcher2:id/search_edit_text" class="android.widget.EditText" bounds="[100,200][900,300]" clickable="true" focusable="true" enabled="true" />
</hierarchy>"""

        with patch(
            "crxzipple.modules.mobile.infrastructure.engines._make_client",
            return_value=_FakeClient(),
        ):
            result, updated_state = engine.execute(plan=plan, runtime_state=runtime_state)

        self.assertTrue(result.ok)
        self.assertEqual(
            operations,
            [
                ("tap", (500, 250)),
                ("wait_for_input_connection", "com.bbk.launcher2:id/search_edit_text", 0.8),
                ("keycombination", (113, 29)),
                ("keyevent", 67),
                ("input_text", "你好"),
            ],
        )
        self.assertIs(updated_state, runtime_state)

    def test_adb_type_skips_initial_tap_when_target_is_already_focused(self) -> None:
        engine = AdbBackedMobileActionEngine(ref_store=FileBackedMobileRefStore(Path(TemporaryDirectory().name)))
        runtime_state = MobileDeviceRuntimeState(device_name="pixel")
        runtime_state.remember_snapshot(
            generation=1,
            ref_count=1,
            snapshot_format="interactive_text",
        )
        engine.ref_store.save_refs(
            device_name="pixel",
            generation=1,
            refs=(
                MobileStoredRef(
                    ref="g1-m1",
                    generation=1,
                    text="旧内容",
                    class_name="android.widget.EditText",
                    resource_id="com.bbk.launcher2:id/search_edit_text",
                    bounds=(100, 200, 900, 300),
                    focused=True,
                ),
            ),
        )
        plan = MobileExecutionPlan(
            system=MobileSystemConfig(adb_binary="adb"),
            device=ResolvedMobileDevice(name="pixel", platform="android", udid="serial-1"),
            capabilities=MobileDeviceCapabilities(
                mode="adb-android",
                control_family="adb-control",
                action_family="adb-backed",
            ),
            command=MobileActionCommand(
                device_name="pixel",
                kind="type",
                payload={"text": "应用市场", "clear": True},
                timeout_ms=5_000,
                target=MobileActionTarget(ref="g1-m1"),
            ),
        )
        operations: list[tuple[str, object]] = []

        class _FakeClient:
            def tap(self, *, x: int, y: int) -> None:
                operations.append(("tap", (x, y)))

            def wait_for_input_connection(
                self,
                *,
                expected_resource_id: str | None = None,
                timeout_seconds: float = 0.8,
            ) -> bool:
                operations.append(("wait_for_input_connection", expected_resource_id, timeout_seconds))
                return True

            def press_key_combination(self, *, keycodes: tuple[int, ...]) -> None:
                operations.append(("keycombination", keycodes))

            def press_keycode(self, *, keycode: int) -> None:
                operations.append(("keyevent", keycode))

            def input_text(self, text: str) -> None:
                operations.append(("input_text", text))

            def dump_ui_xml(self) -> str:
                return """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node index="0" text="应用市场" resource-id="com.bbk.launcher2:id/search_edit_text" class="android.widget.EditText" bounds="[100,200][900,300]" clickable="true" focusable="true" focused="true" enabled="true" />
</hierarchy>"""

        with patch(
            "crxzipple.modules.mobile.infrastructure.engines._make_client",
            return_value=_FakeClient(),
        ):
            result, updated_state = engine.execute(plan=plan, runtime_state=runtime_state)

        self.assertTrue(result.ok)
        self.assertEqual(
            operations,
            [
                ("wait_for_input_connection", "com.bbk.launcher2:id/search_edit_text", 0.8),
                ("keycombination", (113, 29)),
                ("keyevent", 67),
                ("input_text", "应用市场"),
            ],
        )
        self.assertIs(updated_state, runtime_state)

    def test_adb_type_retries_once_when_first_input_does_not_appear(self) -> None:
        engine = AdbBackedMobileActionEngine(ref_store=FileBackedMobileRefStore(Path(TemporaryDirectory().name)))
        runtime_state = MobileDeviceRuntimeState(device_name="pixel")
        runtime_state.remember_snapshot(
            generation=1,
            ref_count=1,
            snapshot_format="interactive_text",
        )
        engine.ref_store.save_refs(
            device_name="pixel",
            generation=1,
            refs=(
                MobileStoredRef(
                    ref="g1-m1",
                    generation=1,
                    text="搜索本地应用",
                    class_name="android.widget.EditText",
                    resource_id="com.bbk.launcher2:id/search_edit_text",
                    bounds=(100, 200, 900, 300),
                ),
            ),
        )
        plan = MobileExecutionPlan(
            system=MobileSystemConfig(adb_binary="adb"),
            device=ResolvedMobileDevice(name="pixel", platform="android", udid="serial-1"),
            capabilities=MobileDeviceCapabilities(
                mode="adb-android",
                control_family="adb-control",
                action_family="adb-backed",
            ),
            command=MobileActionCommand(
                device_name="pixel",
                kind="type",
                payload={"text": "应用市场", "clear": True},
                timeout_ms=5_000,
                target=MobileActionTarget(ref="g1-m1"),
            ),
        )
        operations: list[tuple[str, object]] = []

        class _FakeClient:
            def tap(self, *, x: int, y: int) -> None:
                operations.append(("tap", (x, y)))

            def wait_for_input_connection(
                self,
                *,
                expected_resource_id: str | None = None,
                timeout_seconds: float = 0.8,
            ) -> bool:
                operations.append(("wait_for_input_connection", expected_resource_id, timeout_seconds))
                return True

            def press_key_combination(self, *, keycodes: tuple[int, ...]) -> None:
                operations.append(("keycombination", keycodes))

            def press_keycode(self, *, keycode: int) -> None:
                operations.append(("keyevent", keycode))

            def input_text(self, text: str) -> None:
                operations.append(("input_text", text))

        with patch(
            "crxzipple.modules.mobile.infrastructure.engines._make_client",
            return_value=_FakeClient(),
        ), patch(
            "crxzipple.modules.mobile.infrastructure.mobile_interaction_actions._verify_typed_text",
            side_effect=[False, True],
        ):
            result, updated_state = engine.execute(plan=plan, runtime_state=runtime_state)

        self.assertTrue(result.ok)
        self.assertEqual(
            operations,
            [
                ("tap", (500, 250)),
                ("wait_for_input_connection", "com.bbk.launcher2:id/search_edit_text", 0.8),
                ("keycombination", (113, 29)),
                ("keyevent", 67),
                ("input_text", "应用市场"),
                ("tap", (500, 250)),
                ("wait_for_input_connection", "com.bbk.launcher2:id/search_edit_text", 0.8),
                ("keycombination", (113, 29)),
                ("keyevent", 67),
                ("input_text", "应用市场"),
            ],
        )
        self.assertIs(updated_state, runtime_state)

    def test_adb_control_engine_launches_activity(self) -> None:
        engine = AdbControlEngine()
        runtime_state = MobileDeviceRuntimeState(device_name="pixel")
        plan = MobileExecutionPlan(
            system=MobileSystemConfig(adb_binary="adb"),
            device=ResolvedMobileDevice(
                name="pixel",
                platform="android",
                udid="serial-1",
            ),
            capabilities=MobileDeviceCapabilities(
                mode="adb-android",
                control_family="adb-control",
                action_family="adb-backed",
            ),
            command=DefaultMobileControlCommandAssembler().assemble(
                device_name="pixel",
                kind="launch-app",
                payload={
                    "app_package": "com.tencent.mm",
                    "app_activity": ".ui.LauncherUI",
                },
                timeout_ms=10_000,
            ),
        )

        launched: list[tuple[str, str]] = []

        class _FakeClient:
            def start_activity(self, *, app_package: str, app_activity: str) -> None:
                launched.append((app_package, app_activity))

        with patch(
            "crxzipple.modules.mobile.infrastructure.mobile_control_engine._make_client",
            return_value=_FakeClient(),
        ):
            result, updated_state = engine.execute(plan=plan, runtime_state=runtime_state)

        self.assertTrue(result.ok)
        self.assertEqual(launched, [("com.tencent.mm", ".ui.LauncherUI")])
        self.assertIs(updated_state, runtime_state)

    def test_adb_client_dump_ui_xml_reads_back_from_tty_dump(self) -> None:
        calls: list[list[str]] = []

        class _FakeClient(AndroidAdbClient):
            def _run(  # type: ignore[override]
                self,
                args: list[str],
                *,
                timeout_seconds: float | None = None,
                text: bool = True,
            ) -> str | bytes:
                del timeout_seconds, text
                calls.append(list(args))
                if args == ["shell", "dumpsys", "window", "windows"]:
                    return (
                        "mCurrentFocus=Window{e9267fb u0 com.bbk.launcher2/com.bbk.launcher2.Launcher type=1}\n"
                        "mFocusedApp=ActivityRecord{6bc6c65 u0 com.bbk.launcher2/.Launcher t5 d0}"
                    )
                if args == ["shell", "dumpsys", "activity", "activities"]:
                    return ""
                raise AssertionError(f"unexpected adb args: {args}")

            def _run_completed(  # type: ignore[override]
                self,
                args: list[str],
                *,
                timeout_seconds: float | None = None,
                text: bool = True,
                check: bool = True,
            ):
                del timeout_seconds, text, check
                calls.append(list(args))
                if args[:3] == ["shell", "uiautomator", "dump"]:
                    return SimpleNamespace(
                        returncode=0,
                        stdout=(
                            "UI hierchary dumped to: /dev/tty\n"
                            "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>"
                            "<hierarchy><node text='Hello' /></hierarchy>"
                        ),
                        stderr="",
                    )
                raise AssertionError(f"unexpected adb args: {args}")

        client = _FakeClient(adb_binary="adb", device_serial="serial-1")

        xml = client.dump_ui_xml()

        self.assertTrue(xml.startswith("<?xml"))
        self.assertEqual(calls[0], ["shell", "dumpsys", "window", "windows"])
        self.assertEqual(calls[1], ["shell", "uiautomator", "dump", "/dev/tty"])

    def test_adb_client_dump_ui_xml_falls_back_to_compressed_file_dump(self) -> None:
        calls: list[list[str]] = []

        class _FakeClient(AndroidAdbClient):
            def _run(  # type: ignore[override]
                self,
                args: list[str],
                *,
                timeout_seconds: float | None = None,
                text: bool = True,
            ) -> str | bytes:
                del timeout_seconds, text
                calls.append(list(args))
                if args == ["shell", "dumpsys", "window", "windows"]:
                    return (
                        "mCurrentFocus=Window{123 u0 com.taobao.taobao/com.taobao.tao.welcome.Welcome type=1}\n"
                        "mFocusedApp=ActivityRecord{234 u0 com.taobao.taobao/com.taobao.tao.welcome.Welcome t35 d0}"
                    )
                if args == ["shell", "dumpsys", "activity", "activities"]:
                    return ""
                raise AssertionError(f"unexpected adb args: {args}")

            def _run_completed(  # type: ignore[override]
                self,
                args: list[str],
                *,
                timeout_seconds: float | None = None,
                text: bool = True,
                check: bool = True,
            ):
                del timeout_seconds, text, check
                calls.append(list(args))
                if args == ["shell", "uiautomator", "dump", "/dev/tty"]:
                    return SimpleNamespace(
                        returncode=0,
                        stdout="UI hierchary dumped to: /dev/tty\n",
                        stderr="",
                    )
                if args[:3] == ["shell", "rm", "-f"]:
                    return SimpleNamespace(returncode=0, stdout="", stderr="")
                if args == ["shell", "uiautomator", "dump", "--compressed"]:
                    return SimpleNamespace(
                        returncode=0,
                        stdout="UI hierchary dumped to: /sdcard/window_dump.xml\n",
                        stderr="",
                    )
                if args[:2] == ["shell", "cat"]:
                    return SimpleNamespace(
                        returncode=0,
                        stdout=(
                            "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>"
                            "<hierarchy><node package='com.taobao.taobao' text='淘宝' /></hierarchy>"
                        ),
                        stderr="",
                    )
                raise AssertionError(f"unexpected adb args: {args}")

        client = _FakeClient(adb_binary="adb", device_serial="serial-1")

        xml = client.dump_ui_xml()

        self.assertIn("com.taobao.taobao", xml)
        self.assertEqual(calls[0], ["shell", "dumpsys", "window", "windows"])
        self.assertEqual(calls[1], ["shell", "uiautomator", "dump", "/dev/tty"])
        self.assertEqual(calls[2][:3], ["shell", "rm", "-f"])
        self.assertEqual(calls[3], ["shell", "uiautomator", "dump", "--compressed"])
        self.assertEqual(calls[4][:2], ["shell", "cat"])
        self.assertEqual(calls[5][:3], ["shell", "rm", "-f"])

    def test_adb_client_dump_ui_xml_falls_back_to_compressed_dump_after_idle_state_error(self) -> None:
        calls: list[list[str]] = []

        class _FakeClient(AndroidAdbClient):
            def _run(  # type: ignore[override]
                self,
                args: list[str],
                *,
                timeout_seconds: float | None = None,
                text: bool = True,
            ) -> str | bytes:
                del timeout_seconds, text
                calls.append(list(args))
                if args == ["shell", "dumpsys", "window", "windows"]:
                    return (
                        "mCurrentFocus=Window{123 u0 com.sankuai.meituan/"
                        "com.sankuai.waimai.business.page.homepage.TakeoutActivity type=1}\n"
                        "mFocusedApp=ActivityRecord{234 u0 com.sankuai.meituan/"
                        "com.sankuai.waimai.business.page.homepage.TakeoutActivity t35 d0}"
                    )
                if args == ["shell", "dumpsys", "activity", "activities"]:
                    return ""
                raise AssertionError(f"unexpected adb args: {args}")

            def _run_completed(  # type: ignore[override]
                self,
                args: list[str],
                *,
                timeout_seconds: float | None = None,
                text: bool = True,
                check: bool = True,
            ):
                del timeout_seconds, text, check
                calls.append(list(args))
                if args == ["shell", "uiautomator", "dump", "/dev/tty"]:
                    return SimpleNamespace(
                        returncode=0,
                        stdout="",
                        stderr="ERROR: could not get idle state.\n",
                    )
                if args[:3] == ["shell", "rm", "-f"]:
                    return SimpleNamespace(returncode=0, stdout="", stderr="")
                if args == ["shell", "uiautomator", "dump", "--compressed"]:
                    return SimpleNamespace(
                        returncode=0,
                        stdout="UI hierchary dumped to: /sdcard/window_dump.xml\n",
                        stderr="",
                    )
                if args[:2] == ["shell", "cat"]:
                    return SimpleNamespace(
                        returncode=0,
                        stdout=(
                            "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>"
                            "<hierarchy><node package='com.sankuai.meituan' text='美团' /></hierarchy>"
                        ),
                        stderr="",
                    )
                raise AssertionError(f"unexpected adb args: {args}")

        client = _FakeClient(adb_binary="adb", device_serial="serial-1")

        xml = client.dump_ui_xml()

        self.assertIn("com.sankuai.meituan", xml)
        self.assertEqual(calls[1], ["shell", "uiautomator", "dump", "/dev/tty"])
        self.assertEqual(calls[3], ["shell", "uiautomator", "dump", "--compressed"])

    def test_adb_client_caps_internal_timeout_for_ui_dump_commands(self) -> None:
        timeouts: list[tuple[list[str], float | None]] = []

        class _FakeClient(AndroidAdbClient):
            def _run(  # type: ignore[override]
                self,
                args: list[str],
                *,
                timeout_seconds: float | None = None,
                text: bool = True,
            ) -> str | bytes:
                del timeout_seconds, text
                if args == ["shell", "dumpsys", "window", "windows"]:
                    return (
                        "mCurrentFocus=Window{123 u0 com.sankuai.meituan/"
                        "com.sankuai.waimai.business.page.homepage.TakeoutActivity type=1}\n"
                        "mFocusedApp=ActivityRecord{234 u0 com.sankuai.meituan/"
                        "com.sankuai.waimai.business.page.homepage.TakeoutActivity t35 d0}"
                    )
                if args == ["shell", "dumpsys", "activity", "activities"]:
                    return ""
                raise AssertionError(f"unexpected adb args: {args}")

            def _run_completed(  # type: ignore[override]
                self,
                args: list[str],
                *,
                timeout_seconds: float | None = None,
                text: bool = True,
                check: bool = True,
            ):
                del text, check
                timeouts.append((list(args), timeout_seconds))
                if args == ["shell", "uiautomator", "dump", "/dev/tty"]:
                    return SimpleNamespace(
                        returncode=0,
                        stdout="",
                        stderr="ERROR: could not get idle state.\n",
                    )
                if args[:3] == ["shell", "rm", "-f"]:
                    return SimpleNamespace(returncode=0, stdout="", stderr="")
                if args == ["shell", "uiautomator", "dump", "--compressed"]:
                    return SimpleNamespace(
                        returncode=0,
                        stdout="UI hierchary dumped to: /sdcard/window_dump.xml\n",
                        stderr="",
                    )
                if args[:2] == ["shell", "cat"]:
                    return SimpleNamespace(
                        returncode=0,
                        stdout=(
                            "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>"
                            "<hierarchy><node package='com.sankuai.meituan' text='美团' /></hierarchy>"
                        ),
                        stderr="",
                    )
                raise AssertionError(f"unexpected adb args: {args}")

        client = _FakeClient(adb_binary="adb", device_serial="serial-1", timeout_seconds=15.0)

        xml = client.dump_ui_xml()

        self.assertIn("com.sankuai.meituan", xml)
        timed_dump_calls = {
            tuple(args): timeout
            for args, timeout in timeouts
            if args in (
                ["shell", "uiautomator", "dump", "/dev/tty"],
                ["shell", "uiautomator", "dump", "--compressed"],
                ["shell", "cat", "/sdcard/window_dump.xml"],
            )
        }
        self.assertEqual(timed_dump_calls[("shell", "uiautomator", "dump", "/dev/tty")], 4.0)
        self.assertEqual(timed_dump_calls[("shell", "uiautomator", "dump", "--compressed")], 4.0)
        self.assertEqual(timed_dump_calls[("shell", "cat", "/sdcard/window_dump.xml")], 4.0)

    def test_adb_client_dump_ui_xml_falls_back_to_compressed_dump_after_tty_timeout(self) -> None:
        calls: list[list[str]] = []

        class _FakeClient(AndroidAdbClient):
            def _run(  # type: ignore[override]
                self,
                args: list[str],
                *,
                timeout_seconds: float | None = None,
                text: bool = True,
            ) -> str | bytes:
                del timeout_seconds, text
                calls.append(list(args))
                if args == ["shell", "dumpsys", "window", "windows"]:
                    return (
                        "mCurrentFocus=Window{123 u0 com.sankuai.meituan/"
                        "com.sankuai.waimai.business.page.homepage.TakeoutActivity type=1}\n"
                        "mFocusedApp=ActivityRecord{234 u0 com.sankuai.meituan/"
                        "com.sankuai.waimai.business.page.homepage.TakeoutActivity t35 d0}"
                    )
                if args == ["shell", "dumpsys", "activity", "activities"]:
                    return ""
                raise AssertionError(f"unexpected adb args: {args}")

            def _run_completed(  # type: ignore[override]
                self,
                args: list[str],
                *,
                timeout_seconds: float | None = None,
                text: bool = True,
                check: bool = True,
            ):
                del timeout_seconds, text, check
                calls.append(list(args))
                if args == ["shell", "uiautomator", "dump", "/dev/tty"]:
                    raise MobileExecutionError("adb command timed out after 4.0 seconds.")
                if args[:3] == ["shell", "rm", "-f"]:
                    return SimpleNamespace(returncode=0, stdout="", stderr="")
                if args == ["shell", "uiautomator", "dump", "--compressed"]:
                    return SimpleNamespace(
                        returncode=0,
                        stdout="UI hierchary dumped to: /sdcard/window_dump.xml\n",
                        stderr="",
                    )
                if args[:2] == ["shell", "cat"]:
                    return SimpleNamespace(
                        returncode=0,
                        stdout=(
                            "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>"
                            "<hierarchy><node package='com.sankuai.meituan' text='美团' /></hierarchy>"
                        ),
                        stderr="",
                    )
                raise AssertionError(f"unexpected adb args: {args}")

        client = _FakeClient(adb_binary="adb", device_serial="serial-1", timeout_seconds=15.0)

        xml = client.dump_ui_xml()

        self.assertIn("com.sankuai.meituan", xml)
        self.assertEqual(calls[1], ["shell", "uiautomator", "dump", "/dev/tty"])
        self.assertEqual(calls[3], ["shell", "uiautomator", "dump", "--compressed"])

    def test_adb_client_dump_ui_xml_rejects_failed_dump_without_reusing_stale_file(self) -> None:
        calls: list[list[str]] = []
        dump_attempts = 0

        class _FakeClient(AndroidAdbClient):
            def _run_completed(  # type: ignore[override]
                self,
                args: list[str],
                *,
                timeout_seconds: float | None = None,
                text: bool = True,
                check: bool = True,
            ):
                nonlocal dump_attempts
                del timeout_seconds, text, check
                calls.append(list(args))
                if args[:3] == ["shell", "uiautomator", "dump"]:
                    dump_attempts += 1
                    return SimpleNamespace(
                        returncode=0,
                        stdout="",
                        stderr="ERROR: null root node returned by UiTestAutomationBridge.",
                    )
                if args[:4] == ["shell", "settings", "get", "secure"]:
                    key = args[4]
                    values = {
                        "autofill_service": None,
                        "enabled_accessibility_services": None,
                        "accessibility_enabled": None,
                    }
                    value = values[key]
                    return SimpleNamespace(returncode=0, stdout="" if value is None else value, stderr="")
                if args[:3] == ["shell", "cmd", "autofill"]:
                    return SimpleNamespace(returncode=0, stdout="", stderr="")
                if args[:4] == ["shell", "settings", "delete", "secure"]:
                    return SimpleNamespace(returncode=0, stdout="", stderr="")
                if args[:2] == ["shell", "cat"]:
                    raise AssertionError("cat should not run after a failed dump")
                raise AssertionError(f"unexpected adb args: {args}")

            def _run(  # type: ignore[override]
                self,
                args: list[str],
                *,
                timeout_seconds: float | None = None,
                text: bool = True,
            ) -> str | bytes:
                del timeout_seconds, text
                calls.append(list(args))
                if args == ["shell", "dumpsys", "window", "windows"]:
                    return (
                        "mCurrentFocus=Window{7ea93a1 u0 com.android.contacts/"
                        "com.android.dialer.BBKTwelveKeyDialer type=1}\n"
                        "mFocusedApp=ActivityRecord{75a636d u0 com.android.contacts/"
                        "com.android.dialer.BBKTwelveKeyDialer t29 d0}"
                    )
                if args == ["shell", "dumpsys", "activity", "activities"]:
                    return ""
                raise AssertionError(f"unexpected adb args: {args}")

        client = _FakeClient(adb_binary="adb", device_serial="serial-1")

        with self.assertRaisesRegex(MobileExecutionError, "UiTestAutomationBridge"):
            client.dump_ui_xml()

        self.assertGreaterEqual(dump_attempts, 1)
        self.assertIn(["shell", "dumpsys", "window", "windows"], calls)
        self.assertIn(["shell", "settings", "get", "secure", "enabled_accessibility_services"], calls)

    def test_adb_client_capture_ui_xml_skips_mitigations_for_timeout_only_failures(self) -> None:
        calls: list[list[str]] = []

        class _FakeClient(AndroidAdbClient):
            def _run_completed(  # type: ignore[override]
                self,
                args: list[str],
                *,
                timeout_seconds: float | None = None,
                text: bool = True,
                check: bool = True,
            ):
                del timeout_seconds, text, check
                calls.append(list(args))
                if args[:3] == ["shell", "uiautomator", "dump"]:
                    raise MobileExecutionError("adb command timed out after 4.0 seconds.")
                if args[:3] == ["shell", "rm", "-f"]:
                    return SimpleNamespace(returncode=0, stdout="", stderr="")
                if args[:2] == ["shell", "cat"]:
                    raise AssertionError("cat should not run after timed out dump commands")
                if args[:4] == ["shell", "settings", "get", "secure"]:
                    raise AssertionError("mitigation settings should not be queried for timeout-only failures")
                raise AssertionError(f"unexpected adb args: {args}")

            def _run(  # type: ignore[override]
                self,
                args: list[str],
                *,
                timeout_seconds: float | None = None,
                text: bool = True,
            ) -> str | bytes:
                del timeout_seconds, text
                calls.append(list(args))
                if args == ["shell", "dumpsys", "window", "windows"]:
                    return (
                        "mCurrentFocus=Window{123 u0 com.sankuai.meituan/"
                        "com.sankuai.waimai.business.page.homepage.TakeoutActivity type=1}\n"
                        "mFocusedApp=ActivityRecord{234 u0 com.sankuai.meituan/"
                        "com.sankuai.waimai.business.page.homepage.TakeoutActivity t35 d0}"
                    )
                raise AssertionError(f"unexpected adb args: {args}")

        client = _FakeClient(adb_binary="adb", device_serial="serial-1", timeout_seconds=15.0)

        with self.assertRaisesRegex(MobileExecutionError, "tty dump also failed"):
            client.dump_ui_xml()

        self.assertEqual(calls[0], ["shell", "dumpsys", "window", "windows"])
        self.assertEqual(calls[1], ["shell", "uiautomator", "dump", "/dev/tty"])
        self.assertEqual(calls[2][:3], ["shell", "rm", "-f"])
        self.assertEqual(calls[3], ["shell", "uiautomator", "dump", "--compressed"])
        self.assertEqual(calls[4][:3], ["shell", "rm", "-f"])

    def test_adb_client_dump_ui_xml_temporarily_disables_autofill_on_focus_mismatch(self) -> None:
        settings_state = {
            "autofill_service": "com.google.android.gms/com.google.android.gms.autofill.service.AutofillService",
            "enabled_accessibility_services": "com.vivo.dr/.WXAssistService",
            "accessibility_enabled": "1",
        }
        dump_attempts = 0
        reset_calls = 0

        class _FakeClient(AndroidAdbClient):
            def _run_completed(  # type: ignore[override]
                self,
                args: list[str],
                *,
                timeout_seconds: float | None = None,
                text: bool = True,
                check: bool = True,
            ):
                nonlocal dump_attempts, reset_calls
                del timeout_seconds, text, check
                if args[:3] == ["shell", "uiautomator", "dump"]:
                    dump_attempts += 1
                    xml = (
                        "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>"
                        "<hierarchy><node package='android' class='android.widget.FrameLayout' text='' /></hierarchy>"
                        if dump_attempts == 1
                        else "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>"
                        "<hierarchy><node package='com.alibaba.android.rimet' class='android.widget.FrameLayout' text='' /></hierarchy>"
                    )
                    return SimpleNamespace(
                        returncode=0,
                        stdout=f"UI hierchary dumped to: {args[3]}\n{xml}",
                        stderr="",
                    )
                if args[:4] == ["shell", "settings", "get", "secure"]:
                    return SimpleNamespace(returncode=0, stdout=settings_state.get(args[4], ""), stderr="")
                if args[:4] == ["shell", "settings", "put", "secure"]:
                    settings_state[args[4]] = args[5]
                    return SimpleNamespace(returncode=0, stdout="", stderr="")
                if args[:4] == ["shell", "settings", "delete", "secure"]:
                    settings_state[args[4]] = ""
                    return SimpleNamespace(returncode=0, stdout="", stderr="")
                if args[:3] == ["shell", "cmd", "autofill"]:
                    reset_calls += 1
                    return SimpleNamespace(returncode=0, stdout="", stderr="")
                raise AssertionError(f"unexpected adb args: {args}")

            def _run(  # type: ignore[override]
                self,
                args: list[str],
                *,
                timeout_seconds: float | None = None,
                text: bool = True,
            ) -> str | bytes:
                del timeout_seconds, text
                if args == ["shell", "dumpsys", "window", "windows"]:
                    if dump_attempts == 0:
                        return (
                            "mCurrentFocus=Window{android: parentWindow@2a9ac89: 67711d u0 Autofill UI type=1005}\n"
                            "mFocusedApp=ActivityRecord{c7524da u0 com.alibaba.android.rimet/"
                            "com.alibaba.android.user.login.v3.LoginByMultiFactorActivity t28 d0}"
                        )
                    return (
                        "mCurrentFocus=Window{2a9ac89 u0 com.alibaba.android.rimet/"
                        "com.alibaba.android.user.login.v3.LoginByMultiFactorActivity type=1}\n"
                        "mFocusedApp=ActivityRecord{c7524da u0 com.alibaba.android.rimet/"
                        "com.alibaba.android.user.login.v3.LoginByMultiFactorActivity t28 d0}"
                    )
                if args == ["shell", "dumpsys", "activity", "activities"]:
                    return ""
                raise AssertionError(f"unexpected adb args: {args}")

        client = _FakeClient(adb_binary="adb", device_serial="serial-1")

        capture = client.capture_ui_xml()

        self.assertEqual(capture.root_package, "com.alibaba.android.rimet")
        self.assertEqual(capture.current_package, "com.alibaba.android.rimet")
        self.assertEqual(capture.mitigations_applied, ("disable_autofill_service",))
        self.assertEqual(dump_attempts, 2)
        self.assertGreaterEqual(reset_calls, 2)
        self.assertEqual(
            settings_state["autofill_service"],
            "com.google.android.gms/com.google.android.gms.autofill.service.AutofillService",
        )

    def test_adb_client_dump_ui_xml_temporarily_disables_accessibility_interferer(self) -> None:
        settings_state = {
            "autofill_service": "com.google.android.gms/com.google.android.gms.autofill.service.AutofillService",
            "enabled_accessibility_services": "com.vivo.dr/.WXAssistService",
            "accessibility_enabled": "1",
        }
        dump_attempts = 0

        class _FakeClient(AndroidAdbClient):
            def _run_completed(  # type: ignore[override]
                self,
                args: list[str],
                *,
                timeout_seconds: float | None = None,
                text: bool = True,
                check: bool = True,
            ):
                nonlocal dump_attempts
                del timeout_seconds, text, check
                if args[:3] == ["shell", "uiautomator", "dump"]:
                    dump_attempts += 1
                    if dump_attempts < 2:
                        return SimpleNamespace(
                            returncode=0,
                            stdout="",
                            stderr="ERROR: null root node returned by UiTestAutomationBridge.",
                        )
                    return SimpleNamespace(
                        returncode=0,
                        stdout=(
                            f"UI hierchary dumped to: {args[3]}\n"
                            "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>"
                            "<hierarchy><node package='com.android.contacts' class='android.widget.FrameLayout' text='拨号' /></hierarchy>"
                        ),
                        stderr="",
                    )
                if args[:4] == ["shell", "settings", "get", "secure"]:
                    return SimpleNamespace(returncode=0, stdout=settings_state.get(args[4], ""), stderr="")
                if args[:4] == ["shell", "settings", "put", "secure"]:
                    settings_state[args[4]] = args[5]
                    return SimpleNamespace(returncode=0, stdout="", stderr="")
                if args[:4] == ["shell", "settings", "delete", "secure"]:
                    settings_state[args[4]] = ""
                    return SimpleNamespace(returncode=0, stdout="", stderr="")
                if args[:3] == ["shell", "cmd", "autofill"]:
                    return SimpleNamespace(returncode=0, stdout="", stderr="")
                raise AssertionError(f"unexpected adb args: {args}")

            def _run(  # type: ignore[override]
                self,
                args: list[str],
                *,
                timeout_seconds: float | None = None,
                text: bool = True,
            ) -> str | bytes:
                del timeout_seconds, text
                if args == ["shell", "dumpsys", "window", "windows"]:
                    return (
                        "mCurrentFocus=Window{7ea93a1 u0 com.android.contacts/"
                        "com.android.dialer.BBKTwelveKeyDialer type=1}\n"
                        "mFocusedApp=ActivityRecord{75a636d u0 com.android.contacts/"
                        "com.android.dialer.BBKTwelveKeyDialer t29 d0}"
                    )
                if args == ["shell", "dumpsys", "activity", "activities"]:
                    return ""
                raise AssertionError(f"unexpected adb args: {args}")

        client = _FakeClient(adb_binary="adb", device_serial="serial-1")

        capture = client.capture_ui_xml()

        self.assertEqual(capture.root_package, "com.android.contacts")
        self.assertEqual(capture.current_package, "com.android.contacts")
        self.assertEqual(
            capture.mitigations_applied,
            ("disable_accessibility_interferers",),
        )
        self.assertEqual(dump_attempts, 2)
        self.assertEqual(
            settings_state["enabled_accessibility_services"],
            "com.vivo.dr/.WXAssistService",
        )
        self.assertEqual(settings_state["accessibility_enabled"], "1")

    def test_adb_client_current_focus_falls_back_to_activity_dump(self) -> None:
        calls: list[list[str]] = []

        class _FakeClient(AndroidAdbClient):
            def _run(  # type: ignore[override]
                self,
                args: list[str],
                *,
                timeout_seconds: float | None = None,
                text: bool = True,
            ) -> str | bytes:
                del timeout_seconds, text
                calls.append(list(args))
                if args == ["shell", "dumpsys", "window", "windows"]:
                    return "Window dump without focus lines"
                if args == ["shell", "dumpsys", "activity", "activities"]:
                    return "topResumedActivity=ActivityRecord{123 u0 com.bbk.launcher2/.Launcher t5 d0}"
                raise AssertionError(f"unexpected adb args: {args}")

        client = _FakeClient(adb_binary="adb", device_serial="serial-1")

        focus = client.current_focus()

        self.assertEqual(focus["package"], "com.bbk.launcher2")
        self.assertEqual(focus["activity"], ".Launcher")
        self.assertEqual(
            calls,
            [
                ["shell", "dumpsys", "window", "windows"],
                ["shell", "dumpsys", "activity", "activities"],
            ],
        )

    def test_adb_client_capture_ui_xml_falls_back_to_activity_dump_for_context(self) -> None:
        calls: list[list[str]] = []

        class _FakeClient(AndroidAdbClient):
            def _run(  # type: ignore[override]
                self,
                args: list[str],
                *,
                timeout_seconds: float | None = None,
                text: bool = True,
            ) -> str | bytes:
                del timeout_seconds, text
                calls.append(list(args))
                if args == ["shell", "dumpsys", "window", "windows"]:
                    return "Window dump without focus lines"
                if args == ["shell", "dumpsys", "activity", "activities"]:
                    return "topResumedActivity=ActivityRecord{123 u0 com.bbk.launcher2/.Launcher t5 d0}"
                raise AssertionError(f"unexpected adb args: {args}")

            def _run_completed(  # type: ignore[override]
                self,
                args: list[str],
                *,
                timeout_seconds: float | None = None,
                text: bool = True,
                check: bool = True,
            ):
                del timeout_seconds, text, check
                calls.append(list(args))
                if args[:3] == ["shell", "uiautomator", "dump"]:
                    return SimpleNamespace(
                        returncode=0,
                        stdout=(
                            f"UI hierchary dumped to: {args[3]}\n"
                            "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>"
                            "<hierarchy><node package='com.bbk.launcher2' text='主页' /></hierarchy>"
                        ),
                        stderr="",
                    )
                raise AssertionError(f"unexpected adb args: {args}")

        client = _FakeClient(adb_binary="adb", device_serial="serial-1")

        capture = client.capture_ui_xml()

        self.assertEqual(capture.root_package, "com.bbk.launcher2")
        self.assertEqual(capture.current_package, "com.bbk.launcher2")
        self.assertEqual(capture.current_activity, ".Launcher")
        self.assertEqual(calls[0], ["shell", "dumpsys", "window", "windows"])
        self.assertEqual(calls[1], ["shell", "uiautomator", "dump", "/dev/tty"])
        self.assertEqual(calls[2], ["shell", "dumpsys", "activity", "activities"])
