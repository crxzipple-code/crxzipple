from __future__ import annotations

from copy import deepcopy
from typing import Any

BROWSER_EVIDENCE_PATH_LADDER: tuple[dict[str, Any], ...] = (
    {
        "key": "orient",
        "title": "Orient In Browser State",
        "summary": (
            "Start with the live page, tabs, console, visible controls, and "
            "runtime hints. Treat the first observation as a map, not proof "
            "that hidden or script-driven behavior is absent."
        ),
        "tool_ids": ["browser.observe", "browser.tabs.list"],
    },
    {
        "key": "runtime_and_code",
        "title": "Inspect Runtime And Frontend Code",
        "summary": (
            "When a site is script-driven, inspect live runtime objects, "
            "resource trees, scripts, and request-building code before "
            "repeating fragile form clicks."
        ),
        "tool_ids": [
            "browser.runtime.inspect",
            "browser.script.find_request",
            "browser.code.search",
            "browser.script.extract_request",
            "browser.runtime.probe_client",
            "browser.runtime.call_client",
            "browser.script.inspect",
        ],
    },
    {
        "key": "network_truth",
        "title": "Trace Network Truth",
        "summary": (
            "Use captured requests, page-context fetches, response bodies, "
            "and replayable requests to verify data returned by the site."
        ),
        "tool_ids": [
            "browser.network.inspect",
            "browser.network.fetch_as_page",
            "browser.network.replay_request",
        ],
    },
    {
        "key": "stateful_interaction",
        "title": "Act With Evidence",
        "summary": (
            "When page interaction is needed, perform one state-changing "
            "action at a time and verify the before/after state, network, "
            "storage, or lifecycle delta."
        ),
        "tool_ids": [
            "browser.action.trace",
            "browser.form.inspect",
            "browser.overlay.observe",
            "browser.dom.clickability",
        ],
    },
    {
        "key": "diagnose_blockers",
        "title": "Diagnose Blockers",
        "summary": (
            "Use storage, service worker, page errors, performance metrics, "
            "and traces to explain auth/session/runtime failures."
        ),
        "tool_ids": [
            "browser.storage.indexeddb.list",
            "browser.service_worker.inspect",
            "browser.page.errors",
            "browser.performance.metrics",
        ],
    },
)


def browser_evidence_path_ladder_payload() -> list[dict[str, Any]]:
    return deepcopy(list(BROWSER_EVIDENCE_PATH_LADDER))


def browser_evidence_path_payload(key: str | None) -> dict[str, Any] | None:
    if key is None:
        return None
    for path in BROWSER_EVIDENCE_PATH_LADDER:
        if path.get("key") == key:
            return deepcopy(path)
    return None


def browser_evidence_path_alternatives(primary_key: str | None) -> list[dict[str, Any]]:
    preferred_order = (
        "runtime_and_code",
        "network_truth",
        "stateful_interaction",
        "diagnose_blockers",
        "orient",
    )
    alternatives: list[dict[str, Any]] = []
    for key in preferred_order:
        if key == primary_key:
            continue
        path = browser_evidence_path_payload(key)
        if path is not None:
            alternatives.append(path)
    return alternatives
