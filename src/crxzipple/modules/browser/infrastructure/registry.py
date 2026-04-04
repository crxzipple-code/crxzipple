from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.browser.domain import (
    BrowserActionFamily,
    BrowserCommand,
    BrowserControlCommand,
    BrowserControlFamily,
    BrowserExecutionPlan,
    BrowserValidationError,
)

from ..application.ports import (
    BrowserActionEngine,
    BrowserControlEngine,
    BrowserEngineBinding,
    BrowserEngineRegistry,
)


@dataclass(frozen=True, slots=True)
class StaticBrowserEngineRegistry(BrowserEngineRegistry):
    cdp_control: BrowserControlEngine
    mcp_control: BrowserControlEngine
    cdp_backed_playwright: BrowserActionEngine
    mcp_backed: BrowserActionEngine

    def control_engine(self, *, family: BrowserControlFamily) -> BrowserControlEngine:
        if family == "cdp-control":
            return self.cdp_control
        if family == "mcp-control":
            return self.mcp_control
        raise ValueError(f"Unsupported browser control family '{family}'.")

    def action_engine(self, *, family: BrowserActionFamily) -> BrowserActionEngine:
        if family == "cdp-backed-playwright":
            return self.cdp_backed_playwright
        if family == "mcp-backed":
            return self.mcp_backed
        raise ValueError(f"Unsupported browser action family '{family}'.")

    def resolve(
        self,
        *,
        plan: BrowserExecutionPlan,
        command: BrowserCommand,
    ) -> BrowserEngineBinding:
        control_engine = self.control_engine(family=plan.control_family)
        action_engine = self.action_engine(family=plan.action_family)
        if not isinstance(command, BrowserControlCommand) and not action_engine.supports(
            command=command,
        ):
            raise BrowserValidationError(
                f"Action engine '{plan.action_family}' does not support '{command.kind}'.",
            )
        return BrowserEngineBinding(
            control_engine=control_engine,
            action_engine=action_engine,
        )
