from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.browser.application import (
    BrowserExecutionCoordinator,
    BrowserControlCommandAssembler,
    BrowserPageActionAssembler,
)
from crxzipple.modules.browser.domain import BrowserActionResult

from .requests import (
    BrowserControlRequest,
    BrowserInterfaceRequest,
)


@dataclass(slots=True)
class BrowserInterfaceFacade:
    control_command_assembler: BrowserControlCommandAssembler
    page_action_assembler: BrowserPageActionAssembler
    execution_coordinator: BrowserExecutionCoordinator

    def execute(self, request: BrowserInterfaceRequest) -> BrowserActionResult:
        if isinstance(request, BrowserControlRequest):
            command = self.control_command_assembler.assemble(
                profile_name=request.profile_name,
                kind=request.kind,
                target_id=request.target_id,
                payload=request.payload,
                timeout_ms=request.timeout_ms,
            )
        else:
            command = self.page_action_assembler.assemble(
                profile_name=request.profile_name,
                kind=request.kind,
                target_id=request.target_id,
                ref=request.ref,
                selector=request.selector,
                payload=request.payload,
                timeout_ms=request.timeout_ms,
            )
        return self.execution_coordinator.execute(command)
