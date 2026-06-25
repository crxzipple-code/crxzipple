from __future__ import annotations

from time import perf_counter


def now() -> float:
    return perf_counter()


def record_timing(
    timings: dict[str, float],
    phase: str,
    started: float,
) -> float:
    current = perf_counter()
    timings[f"{phase}_ms"] = round((current - started) * 1000, 3)
    return current


def elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000, 3)


def attach_request_render_timings(
    snapshot_metadata: dict[str, object],
    request_render_report: dict[str, object],
    timings: dict[str, float],
) -> None:
    timing_payload = dict(timings)
    snapshot_metadata["request_render_timings"] = timing_payload
    request_render_metadata = snapshot_metadata.get("request_render_snapshot")
    if isinstance(request_render_metadata, dict):
        request_render_metadata["timings"] = dict(timing_payload)
        _attach_elapsed_to_cost(request_render_metadata.get("cost"), timing_payload)
    _attach_elapsed_to_cost(
        snapshot_metadata.get("request_render_cost"),
        timing_payload,
    )
    _attach_elapsed_to_cost(request_render_report.get("cost"), timing_payload)


def _attach_elapsed_to_cost(
    value: object,
    timings: dict[str, float],
) -> None:
    if not isinstance(value, dict):
        return
    elapsed = timings.get("total_before_request_render_snapshot_ms")
    if elapsed is None:
        elapsed = timings.get("total_ms")
    if elapsed is not None:
        value["elapsed_ms"] = round(float(elapsed), 3)
