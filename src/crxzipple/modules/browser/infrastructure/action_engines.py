from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field

from crxzipple.modules.browser.application.network_capture import (
    BrowserNetworkCaptureService,
)
from crxzipple.modules.browser.domain import BrowserActionFamily
from crxzipple.modules.daemon import DaemonApplicationService

from ..application.ports import BrowserActionEngine, BrowserRefStore
from .action_engine_execution import BrowserActionExecutionMixin
from .action_engine_interactions import BrowserInteractionPrimitivesMixin
from .action_engine_locator_resolution import BrowserLocatorResolutionMixin
from .action_engine_page_actions import BrowserPagePrimitiveActionMixin
from .action_engine_page_dispatch import BrowserPageDispatchMixin
from .action_engine_refs import BrowserRefOverlayMixin
from .action_engine_snapshot_runner import BrowserSnapshotActionMixin
from .action_engine_trace_runner import BrowserActionTraceRunnerMixin
from .action_engine_wait import BrowserWaitActionMixin
from .action_trace import BrowserActionTraceService
from .cdp_sessions import BrowserCdpSessionBroker
from .devtools import BrowserDevToolsAdapter
from .diagnostics import BrowserDiagnosticsService
from .dom_inspection import BrowserDomInspectionService
from .environment_control import BrowserEnvironmentControlService
from .network_actions import BrowserNetworkActionService
from .network_capture import InMemoryBrowserNetworkCaptureStore
from .network_cdp_capture import CdpNetworkCaptureController
from .network_insight import BrowserNetworkInsightService
from .network_page_fetch import BrowserPageNetworkFetchService
from .peripheral_actions import BrowserPeripheralActionService
from .playwright import PlaywrightCdpSessionPool
from .script_insight import BrowserScriptInsightService
from .storage_inspection import BrowserStorageInspectionService


@dataclass(slots=True)
class CdpBackedPlaywrightActionEngine(
    BrowserSnapshotActionMixin,
    BrowserRefOverlayMixin,
    BrowserLocatorResolutionMixin,
    BrowserInteractionPrimitivesMixin,
    BrowserPagePrimitiveActionMixin,
    BrowserWaitActionMixin,
    BrowserActionTraceRunnerMixin,
    BrowserPageDispatchMixin,
    BrowserActionExecutionMixin,
    BrowserActionEngine,
):
    session_pool: PlaywrightCdpSessionPool
    ref_store: BrowserRefStore
    daemon_service: DaemonApplicationService = field(repr=False)
    cdp_session_broker: BrowserCdpSessionBroker = field(
        default_factory=BrowserCdpSessionBroker,
        repr=False,
    )
    devtools_adapter: BrowserDevToolsAdapter | None = field(default=None, repr=False)
    action_trace_service: BrowserActionTraceService = field(
        default_factory=BrowserActionTraceService,
        repr=False,
    )
    script_insight_service: BrowserScriptInsightService | None = field(
        default=None,
        repr=False,
    )
    network_capture_service: BrowserNetworkCaptureService = field(
        default_factory=lambda: BrowserNetworkCaptureService(
            capture_store=InMemoryBrowserNetworkCaptureStore(),
        ),
        repr=False,
    )
    network_capture_controller: CdpNetworkCaptureController | None = field(
        default=None,
        repr=False,
    )
    network_page_fetch_service: BrowserPageNetworkFetchService = field(
        default_factory=BrowserPageNetworkFetchService,
        repr=False,
    )
    network_action_service: BrowserNetworkActionService | None = field(
        default=None,
        repr=False,
    )
    network_insight_service: BrowserNetworkInsightService = field(
        default_factory=BrowserNetworkInsightService,
        repr=False,
    )
    storage_inspection_service: BrowserStorageInspectionService = field(
        default_factory=BrowserStorageInspectionService,
        repr=False,
    )
    dom_inspection_service: BrowserDomInspectionService = field(
        default_factory=BrowserDomInspectionService,
        repr=False,
    )
    peripheral_action_service: BrowserPeripheralActionService = field(
        default_factory=BrowserPeripheralActionService,
        repr=False,
    )
    environment_control_service: BrowserEnvironmentControlService = field(
        default_factory=BrowserEnvironmentControlService,
        repr=False,
    )
    diagnostics_service: BrowserDiagnosticsService = field(
        default_factory=BrowserDiagnosticsService,
        repr=False,
    )
    family: BrowserActionFamily = "cdp-backed-playwright"

    def __post_init__(self) -> None:
        if self.devtools_adapter is None:
            self.devtools_adapter = BrowserDevToolsAdapter(
                cdp_session_broker=self.cdp_session_broker,
            )
        if self.script_insight_service is None:
            self.script_insight_service = BrowserScriptInsightService(
                devtools_adapter=self.devtools_adapter,
            )
        if self.network_capture_controller is None:
            self.network_capture_controller = CdpNetworkCaptureController(
                capture_service=self.network_capture_service,
                cdp_session_broker=self.cdp_session_broker,
            )
        if self.network_action_service is None:
            self.network_action_service = BrowserNetworkActionService(
                network_capture_service=self.network_capture_service,
                network_capture_controller=self.network_capture_controller,
                network_page_fetch_service=self.network_page_fetch_service,
            )
