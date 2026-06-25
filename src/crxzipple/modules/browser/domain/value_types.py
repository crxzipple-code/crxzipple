from __future__ import annotations

from typing import Literal, TypeAlias

BrowserProfileDriver: TypeAlias = Literal["managed", "existing-session"]

BrowserProfileProxyMode: TypeAlias = Literal["none", "static", "access_binding"]

BrowserProxyCredentialKind: TypeAlias = Literal["basic", "bearer_token"]

BrowserProfilePoolSelectionStrategy: TypeAlias = Literal[
    "round_robin",
    "least_busy",
    "sticky_session",
    "manual_only",
]

BrowserProfileMode: TypeAlias = Literal[
    "local-managed",
    "local-existing-session",
    "remote-cdp",
]

BrowserControlFamily: TypeAlias = Literal["cdp-control"]

BrowserActionFamily: TypeAlias = Literal["cdp-backed-playwright"]

BrowserLaunchPolicy: TypeAlias = Literal["launch-if-missing", "attach-only"]

BrowserTabSelectionPolicy: TypeAlias = Literal[
    "sticky-last-target",
    "explicit-only",
]

BrowserTabType: TypeAlias = Literal["page", "background", "worker", "other"]

BrowserControlKind: TypeAlias = Literal[
    "status",
    "start",
    "stop",
    "navigate",
    "open-tab",
    "focus-tab",
    "close-tab",
    "list-tabs",
    "reset",
]

BrowserPageActionKind: TypeAlias = Literal[
    "click",
    "console",
    "cookies",
    "dialog",
    "type",
    "press",
    "hover",
    "drag",
    "batch",
    "resize",
    "scroll-into-view",
    "select",
    "fill",
    "upload",
    "download",
    "wait-download",
    "wait",
    "snapshot",
    "screenshot",
    "pdf",
    "evaluate",
    "storage",
    "storage-indexeddb-list",
    "storage-indexeddb-get",
    "storage-indexeddb-query",
    "storage-cache-list",
    "storage-cache-get",
    "service-worker-list",
    "service-worker-inspect",
    "dom-inspect",
    "dom-box-model",
    "dom-computed-style",
    "dom-clickability",
    "dom-highlight",
    "dom-mutation-wait",
    "emulation-set",
    "emulation-reset",
    "permissions-grant",
    "permissions-clear",
    "geolocation-set",
    "network-conditions-set",
    "diagnostics-collect",
    "performance-metrics",
    "trace-start",
    "trace-stop",
    "trace-export",
    "page-lifecycle",
    "page-errors",
    "network-inspect",
    "network-start-capture",
    "network-stop-capture",
    "network-list-requests",
    "network-get-request",
    "network-get-response-body",
    "network-get-request-body",
    "network-fetch-as-page",
    "network-replay-request",
    "network-clear-capture",
    "action-trace",
    "runtime-inspect",
    "script-list",
    "script-find-request",
    "code-search",
    "script-inspect",
    "script-extract-request",
    "cdp-raw",
]

BrowserNetworkCaptureStatus: TypeAlias = Literal["active", "stopped"]

BrowserNetworkBodyKind: TypeAlias = Literal["request", "response"]

__all__ = (
    "BrowserProfileDriver",
    "BrowserProfileProxyMode",
    "BrowserProxyCredentialKind",
    "BrowserProfilePoolSelectionStrategy",
    "BrowserProfileMode",
    "BrowserControlFamily",
    "BrowserActionFamily",
    "BrowserLaunchPolicy",
    "BrowserTabSelectionPolicy",
    "BrowserTabType",
    "BrowserControlKind",
    "BrowserPageActionKind",
    "BrowserNetworkCaptureStatus",
    "BrowserNetworkBodyKind",
)
