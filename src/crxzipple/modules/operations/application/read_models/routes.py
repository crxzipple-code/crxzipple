from __future__ import annotations


def workbench_trace_route(trace_id: str | None, *, focus_id: str | None = None) -> str:
    if not trace_id:
        return "-"
    route = f"/workbench/traces/{trace_id}"
    return f"{route}?focus_id={focus_id}" if focus_id else route


def normalize_workbench_trace_route(route: str | None) -> str:
    if not route:
        return "-"
    normalized = route.strip()
    if not normalized or normalized == "-":
        return "-"
    if normalized.startswith("/ui/trace/"):
        return normalized.replace("/ui/trace/", "/workbench/traces/", 1)
    return normalized
