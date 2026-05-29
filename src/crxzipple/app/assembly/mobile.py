"""Mobile module app assembly."""

from __future__ import annotations

from dataclasses import dataclass

from crxzipple.app.keys import AppKey
from crxzipple.app.plan import ApplicationFactory
from crxzipple.core.config import Settings
from crxzipple.modules.artifacts import ArtifactApplicationService
from crxzipple.modules.mobile.application import (
    DefaultMobileActionCommandAssembler,
    DefaultMobileCapabilitiesResolver,
    DefaultMobileControlCommandAssembler,
    DefaultMobileDeviceResolver,
    DefaultMobileExecutionPlanner,
    MobileExecutionCoordinatorService,
)
from crxzipple.modules.mobile.domain import MobileDeviceConfig, MobileSystemConfig
from crxzipple.modules.mobile.infrastructure import (
    AdbBackedMobileActionEngine,
    AdbControlEngine,
    AndroidAdbClient,
    FileBackedMobileRefStore,
    FileBackedMobileRuntimeStateStore,
    FileBackedMobileSystemConfigStore,
    MobileStateRoot,
    StaticMobileEngineRegistry,
    bootstrap_mobile_state_root,
)
from crxzipple.modules.mobile.interfaces import MobileInterfaceFacade, MobileResultSerializer
from crxzipple.modules.ocr import OcrApplicationService


@dataclass(slots=True)
class MobileInfrastructure:
    system_config: MobileSystemConfig
    system_config_store: FileBackedMobileSystemConfigStore
    state_root: MobileStateRoot
    runtime_state_store: FileBackedMobileRuntimeStateStore
    ref_store: FileBackedMobileRefStore
    control_engine: AdbControlEngine
    action_engine: AdbBackedMobileActionEngine
    facade: MobileInterfaceFacade
    result_serializer: MobileResultSerializer


def mobile_factories() -> tuple[ApplicationFactory, ...]:
    """Build Mobile profile/runtime applications."""

    return (
        ApplicationFactory(
            key="mobile.infrastructure",
            provides=(
                AppKey.MOBILE_INFRASTRUCTURE,
                AppKey.MOBILE_SYSTEM_CONFIG_STORE,
                AppKey.MOBILE_FACADE,
                AppKey.MOBILE_RESULT_SERIALIZER,
            ),
            requires=(
                AppKey.CORE_SETTINGS,
                AppKey.ARTIFACT_SERVICE,
                AppKey.OCR_SERVICE,
            ),
            build=_build_mobile_infrastructure,
        ),
    )


def _build_mobile_infrastructure(ctx) -> MobileInfrastructure:
    settings = ctx.require(AppKey.CORE_SETTINGS)
    infrastructure = build_mobile_infrastructure(
        settings,
        artifact_service=ctx.require(AppKey.ARTIFACT_SERVICE),
        ocr_service=ctx.require(AppKey.OCR_SERVICE),
        system_config=build_mobile_system_config(settings),
    )
    return {
        AppKey.MOBILE_INFRASTRUCTURE: infrastructure,
        AppKey.MOBILE_SYSTEM_CONFIG_STORE: infrastructure.system_config_store,
        AppKey.MOBILE_FACADE: infrastructure.facade,
        AppKey.MOBILE_RESULT_SERIALIZER: infrastructure.result_serializer,
    }


def build_mobile_system_config(settings: Settings) -> MobileSystemConfig:
    devices = tuple(
        MobileDeviceConfig(
            name=device.name,
            platform=device.platform,  # type: ignore[arg-type]
            udid=device.udid,
            app_package=device.app_package,
            app_activity=device.app_activity,
        )
        for device in settings.mobile_devices
    )
    default_device = devices[0].name if devices else None
    return MobileSystemConfig(
        default_device=default_device,
        devices=devices,
        adb_binary=settings.mobile_adb_binary,
    )


def build_mobile_infrastructure(
    settings: Settings,
    *,
    artifact_service: ArtifactApplicationService,
    ocr_service: OcrApplicationService,
    system_config: MobileSystemConfig,
) -> MobileInfrastructure:
    state_root = bootstrap_mobile_state_root(settings.mobile_state_dir)
    system_config_store = FileBackedMobileSystemConfigStore(
        state_root.config_dir,
        bootstrap_config=system_config,
    )
    resolved_system_config = system_config_store.load()
    runtime_state_store = FileBackedMobileRuntimeStateStore(state_root.runtime_dir)
    ref_store = FileBackedMobileRefStore(state_root.refs_dir)
    control_engine = AdbControlEngine()
    action_engine = AdbBackedMobileActionEngine(
        ref_store=ref_store,
        artifact_service=artifact_service,
        ocr_service=ocr_service,
    )
    coordinator = MobileExecutionCoordinatorService(
        system_config_store=system_config_store,
        device_resolver=DefaultMobileDeviceResolver(
            system_config_store=system_config_store,
            device_probe=AndroidAdbClient.probe_adb_devices,
        ),
        capabilities_resolver=DefaultMobileCapabilitiesResolver(),
        runtime_state_store=runtime_state_store,
        execution_planner=DefaultMobileExecutionPlanner(),
        engine_registry=StaticMobileEngineRegistry(
            adb_control=control_engine,
            adb_backed=action_engine,
        ),
    )
    return MobileInfrastructure(
        system_config=resolved_system_config,
        system_config_store=system_config_store,
        state_root=state_root,
        runtime_state_store=runtime_state_store,
        ref_store=ref_store,
        control_engine=control_engine,
        action_engine=action_engine,
        facade=MobileInterfaceFacade(
            control_command_assembler=DefaultMobileControlCommandAssembler(),
            action_command_assembler=DefaultMobileActionCommandAssembler(),
            execution_coordinator=coordinator,
        ),
        result_serializer=MobileResultSerializer(),
    )


__all__ = [
    "MobileInfrastructure",
    "build_mobile_infrastructure",
    "build_mobile_system_config",
    "mobile_factories",
]
