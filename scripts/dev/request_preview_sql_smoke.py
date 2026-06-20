#!/usr/bin/env python
"""Measure SQL issued while building an orchestration LLM request preview.

Usage:
    PYTHONPATH=src python scripts/dev/request_preview_sql_smoke.py <run_id> [<run_id> ...]

The script is intentionally read-only from the orchestration caller's
perspective: it uses the request-preview assembly plan and reports SQL statement
counts around `preview_runtime_llm_request`.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import sys
from time import perf_counter
from typing import Any

from sqlalchemy import event

from crxzipple.core.config import load_settings
from crxzipple.interfaces.runtime_container import (
    AppKey,
    AssemblyTarget,
    build_runtime_container,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure SQL counts for runtime LLM request preview.",
    )
    parser.add_argument(
        "run_ids",
        nargs="+",
        help="Existing orchestration run id. Pass multiple ids for comparison.",
    )
    parser.add_argument(
        "--show-sql",
        action="store_true",
        help="Include normalized SQL statements in the JSON output.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Emit one-line JSON for machine collection.",
    )
    parser.add_argument(
        "--warmup",
        action="store_true",
        help="Build each preview once before measurement; useful for new fixtures.",
    )
    parser.add_argument(
        "--allow-write-sql",
        action="store_true",
        help="Do not fail when INSERT/UPDATE/DELETE statements are observed.",
    )
    parser.add_argument(
        "--max-sql-total",
        type=int,
        default=None,
        help="Fail if any run exceeds this SQL statement count.",
    )
    parser.add_argument(
        "--max-sql-delta",
        type=int,
        default=None,
        help="Fail if max(sql_total)-min(sql_total) exceeds this value.",
    )
    parser.add_argument(
        "--max-sql-per-message",
        type=float,
        default=None,
        help="Fail if sql_total/message_count exceeds this value.",
    )
    parser.add_argument(
        "--max-sql-per-included-ref",
        type=float,
        default=None,
        help="Fail if sql_total/included_ref_count exceeds this value.",
    )
    args = parser.parse_args()

    settings = load_settings()
    container = build_runtime_container(
        settings,
        target=AssemblyTarget.CLI_ADMIN,
        run_activation_tasks=False,
        plan_kind="request_preview",
    )
    engine = container.require(AppKey.DATABASE_ENGINE)
    try:
        inspection_service = container.require(AppKey.ORCHESTRATION_INSPECTION_SERVICE)
        results = [
            _measure_preview(
                engine=engine,
                inspection_service=inspection_service,
                run_id=run_id,
                show_sql=args.show_sql,
                warmup=args.warmup,
            )
            for run_id in args.run_ids
        ]
    finally:
        container.close()

    output: dict[str, Any]
    if len(results) == 1:
        output = results[0]
    else:
        output = {
            "runs": results,
            "summary": _summary(results),
        }
    failures = _validate_results(
        results,
        allow_write_sql=args.allow_write_sql,
        max_sql_total=args.max_sql_total,
        max_sql_delta=args.max_sql_delta,
        max_sql_per_message=args.max_sql_per_message,
        max_sql_per_included_ref=args.max_sql_per_included_ref,
    )
    if failures:
        output["assertions"] = {"status": "failed", "failures": failures}
    else:
        output["assertions"] = {"status": "passed"}
    indent = None if args.compact else 2
    print(json.dumps(output, ensure_ascii=False, indent=indent, sort_keys=True))
    if failures:
        for failure in failures:
            print(f"request-preview-sql-smoke: {failure}", file=sys.stderr)
        return 1
    return 0


def _measure_preview(
    *,
    engine: object,
    inspection_service: object,
    run_id: str,
    show_sql: bool,
    warmup: bool,
) -> dict[str, Any]:
    statements: list[tuple[str, str]] = []
    if warmup:
        inspection_service.preview_runtime_llm_request(run_id)

    def before_cursor_execute(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del conn, cursor, parameters, context, executemany
        normalized = " ".join(statement.strip().split())
        head = normalized.split(" ", 1)[0].upper() if normalized else ""
        statements.append((head, normalized))

    started = perf_counter()
    try:
        event.listen(engine, "before_cursor_execute", before_cursor_execute)
        preview = inspection_service.preview_runtime_llm_request(run_id)
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)
    elapsed_ms = (perf_counter() - started) * 1000

    counts = Counter(head for head, _statement in statements)
    snapshot_id = _preview_request_render_snapshot_id(preview)
    snapshot_counts = _preview_request_render_snapshot_counts(preview)
    message_count = len(preview.messages)
    tool_schema_count = len(preview.tool_schemas)
    payload: dict[str, Any] = {
        "run_id": run_id,
        "elapsed_ms": round(elapsed_ms, 3),
        "warmup": warmup,
        "sql_total": len(statements),
        "sql_counts": dict(sorted(counts.items())),
        "llm_id": preview.llm_id,
        "mode": preview.mode.value,
        "message_count": message_count,
        "tool_schema_count": tool_schema_count,
        "request_render_snapshot_id": snapshot_id,
        **snapshot_counts,
        "ratios": {
            "sql_per_message": _ratio(len(statements), message_count),
            "sql_per_tool_schema": _ratio(len(statements), tool_schema_count),
            "sql_per_included_ref": _ratio(
                len(statements),
                snapshot_counts.get("included_ref_count"),
            ),
        },
    }
    if show_sql:
        payload["sql"] = [statement for _head, statement in statements]
    return payload


def _summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    sql_totals = [
        int(result["sql_total"])
        for result in results
        if isinstance(result.get("sql_total"), int)
    ]
    elapsed = [
        float(result["elapsed_ms"])
        for result in results
        if isinstance(result.get("elapsed_ms"), int | float)
    ]
    return {
        "run_count": len(results),
        "sql_total_min": min(sql_totals) if sql_totals else None,
        "sql_total_max": max(sql_totals) if sql_totals else None,
        "sql_total_delta": (
            max(sql_totals) - min(sql_totals) if len(sql_totals) > 1 else 0
        ),
        "elapsed_ms_min": round(min(elapsed), 3) if elapsed else None,
        "elapsed_ms_max": round(max(elapsed), 3) if elapsed else None,
    }


def _validate_results(
    results: list[dict[str, Any]],
    *,
    allow_write_sql: bool,
    max_sql_total: int | None,
    max_sql_delta: int | None,
    max_sql_per_message: float | None,
    max_sql_per_included_ref: float | None,
) -> list[str]:
    failures: list[str] = []
    write_heads = {"INSERT", "UPDATE", "DELETE", "MERGE", "CREATE", "DROP", "ALTER"}
    for result in results:
        run_id = str(result.get("run_id") or "<unknown>")
        counts = result.get("sql_counts")
        if isinstance(counts, dict) and not allow_write_sql:
            observed_writes = sorted(
                head
                for head in counts
                if isinstance(head, str)
                and head.upper() in write_heads
                and int(counts.get(head) or 0) > 0
            )
            if observed_writes:
                failures.append(
                    f"{run_id}: write SQL observed: {', '.join(observed_writes)}",
                )
        if max_sql_total is not None:
            sql_total = result.get("sql_total")
            if isinstance(sql_total, int) and sql_total > max_sql_total:
                failures.append(
                    f"{run_id}: sql_total {sql_total} exceeds {max_sql_total}",
                )
        if max_sql_per_message is not None:
            _append_ratio_failure(
                failures,
                result,
                run_id=run_id,
                ratio_key="sql_per_message",
                limit=max_sql_per_message,
            )
        if max_sql_per_included_ref is not None:
            _append_ratio_failure(
                failures,
                result,
                run_id=run_id,
                ratio_key="sql_per_included_ref",
                limit=max_sql_per_included_ref,
            )
    if max_sql_delta is not None and len(results) > 1:
        summary = _summary(results)
        delta = summary.get("sql_total_delta")
        if isinstance(delta, int) and delta > max_sql_delta:
            failures.append(
                f"sql_total_delta {delta} exceeds {max_sql_delta}",
            )
    return failures


def _append_ratio_failure(
    failures: list[str],
    result: dict[str, Any],
    *,
    run_id: str,
    ratio_key: str,
    limit: float,
) -> None:
    ratios = result.get("ratios")
    if not isinstance(ratios, dict):
        return
    value = ratios.get(ratio_key)
    if value is None:
        return
    if isinstance(value, int | float) and float(value) > limit:
        failures.append(f"{run_id}: {ratio_key} {value} exceeds {limit}")


def _ratio(numerator: int, denominator: object) -> float | None:
    if not isinstance(denominator, int) or denominator <= 0:
        return None
    return round(numerator / denominator, 3)


def _preview_request_render_snapshot_id(preview: object) -> str | None:
    snapshot = getattr(preview, "request_render_snapshot", None)
    if snapshot is None:
        return None
    if isinstance(snapshot, dict):
        value = snapshot.get("snapshot_id") or snapshot.get("id")
        return value if isinstance(value, str) and value.strip() else None
    value = getattr(snapshot, "snapshot_id", None) or getattr(snapshot, "id", None)
    return value if isinstance(value, str) and value.strip() else None


def _preview_request_render_snapshot_counts(preview: object) -> dict[str, int]:
    snapshot = getattr(preview, "request_render_snapshot", None)
    if not isinstance(snapshot, dict):
        return {
            "included_ref_count": 0,
            "protocol_required_ref_count": 0,
            "collapsed_ref_count": 0,
        }
    return {
        "included_ref_count": _snapshot_count(snapshot, "included_ref_count"),
        "protocol_required_ref_count": _snapshot_count(
            snapshot,
            "protocol_required_ref_count",
        ),
        "collapsed_ref_count": _snapshot_count(snapshot, "collapsed_ref_count"),
    }


def _snapshot_count(snapshot: dict[str, object], key: str) -> int:
    value = snapshot.get(key)
    if isinstance(value, bool):
        return 0
    if isinstance(value, int) and value >= 0:
        return value
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
