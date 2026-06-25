from __future__ import annotations

from crxzipple.modules.operations.application.read_models.presenters import (
    display_value,
    health_delta,
    health_label,
    health_tone,
    status_label,
    status_tone,
    title_label,
    truncate_text,
)
from crxzipple.modules.operations.application.read_models.routes import (
    normalize_workbench_trace_route,
    workbench_trace_route,
)


def test_health_presenters_share_common_labels_and_tones() -> None:
    assert health_label("healthy") == "Healthy"
    assert health_label("unknown") == "Unknown"
    assert health_delta("healthy", healthy="Runtime is queryable") == (
        "Runtime is queryable"
    )
    assert health_delta("warning", healthy="Runtime is queryable") == (
        "Operator attention recommended"
    )
    assert health_tone("error") == "danger"
    assert health_tone("unknown") == "neutral"


def test_text_presenters_normalize_display_without_business_rules() -> None:
    assert title_label("queued_run") == "Queued Run"
    assert title_label("tool-run") == "Tool Run"
    assert display_value(None) == "-"
    assert display_value("  ready  ") == "ready"
    assert truncate_text("abcdef", 5) == "ab..."


def test_status_presenters_allow_module_specific_tone_sets() -> None:
    assert status_label("dead-letter") == "Dead Letter"
    assert status_label("") == "Observed"
    assert status_tone("failed") == "danger"
    assert status_tone("running", info=frozenset({"running"})) == "info"
    assert status_tone("cancel-requested", warning=frozenset({"cancel-requested"})) == (
        "warning"
    )


def test_workbench_trace_route_builds_optional_focus_link() -> None:
    assert workbench_trace_route(None) == "-"
    assert workbench_trace_route("trace-1") == "/workbench/traces/trace-1"
    assert workbench_trace_route("trace-1", focus_id="step-1") == (
        "/workbench/traces/trace-1?focus_id=step-1"
    )


def test_normalize_workbench_trace_route_handles_legacy_trace_links() -> None:
    assert normalize_workbench_trace_route(None) == "-"
    assert normalize_workbench_trace_route("  ") == "-"
    assert normalize_workbench_trace_route("/ui/trace/trace-1") == (
        "/workbench/traces/trace-1"
    )
    assert normalize_workbench_trace_route("/workbench/traces/trace-1") == (
        "/workbench/traces/trace-1"
    )
