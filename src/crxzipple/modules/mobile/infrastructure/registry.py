from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.mobile.application.ports import (
    MobileActionEngine,
    MobileControlEngine,
    MobileEngineBinding,
    MobileEngineRegistry,
)
from crxzipple.modules.mobile.domain import MobileValidationError


@dataclass(frozen=True, slots=True)
class StaticMobileEngineRegistry(MobileEngineRegistry):
    adb_control: MobileControlEngine
    adb_backed: MobileActionEngine

    def resolve(
        self,
        *,
        control_family: str,
        action_family: str,
    ) -> MobileEngineBinding:
        if control_family != "adb-control" or action_family != "adb-backed":
            raise MobileValidationError(
                f"Unsupported mobile engine combination '{control_family}/{action_family}'.",
            )
        return MobileEngineBinding(
            control_engine=self.adb_control,
            action_engine=self.adb_backed,
        )
