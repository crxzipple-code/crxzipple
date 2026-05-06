from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.mobile.application import (
    MobileActionCommandAssembler,
    MobileControlCommandAssembler,
    MobileExecutionCoordinator,
)
from crxzipple.modules.mobile.domain import MobileActionResult

from .requests import MobileActionRequest, MobileControlRequest, MobileInterfaceRequest


@dataclass(slots=True)
class MobileInterfaceFacade:
    control_command_assembler: MobileControlCommandAssembler
    action_command_assembler: MobileActionCommandAssembler
    execution_coordinator: MobileExecutionCoordinator

    def execute(self, request: MobileInterfaceRequest) -> MobileActionResult:
        if isinstance(request, MobileControlRequest):
            command = self.control_command_assembler.assemble(
                device_name=request.device_name,
                kind=request.kind,
                payload=request.payload,
                timeout_ms=request.timeout_ms,
            )
        else:
            command = self.action_command_assembler.assemble(
                device_name=request.device_name,
                kind=request.kind,
                ref=request.ref,
                selector=request.selector,
                payload=request.payload,
                timeout_ms=request.timeout_ms,
            )
        return self.execution_coordinator.execute(command)
