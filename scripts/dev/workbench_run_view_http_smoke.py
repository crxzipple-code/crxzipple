#!/usr/bin/env python
"""Smoke Workbench run-view HTTP payload size and latency."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure /ui/workbench/runs/{run_id} latency and payload.",
    )
    parser.add_argument("run_id", help="Workbench run id to fetch.")
    parser.add_argument(
        "--api-base",
        default="http://127.0.0.1:8000",
        help="HTTP API base URL. Defaults to the direct local dev API.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--max-ms",
        type=float,
        default=None,
        help="Optional latency assertion in milliseconds.",
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=None,
        help="Optional response-size assertion in bytes.",
    )
    parser.add_argument(
        "--include-timeline",
        action="store_true",
        help="Request full timeline. By default this matches Workbench first paint.",
    )
    args = parser.parse_args()

    include_timeline = "true" if args.include_timeline else "false"
    url = (
        f"{args.api_base.rstrip('/')}/ui/workbench/runs/{args.run_id}"
        f"?include_timeline={include_timeline}"
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=args.timeout) as response:
            body = response.read()
            status = response.status
            content_type = response.headers.get("content-type", "")
    except urllib.error.HTTPError as exc:
        body = exc.read()
        elapsed_ms = (time.perf_counter() - started) * 1000
        print(
            json.dumps(
                {
                    "status": exc.code,
                    "elapsed_ms": round(elapsed_ms, 3),
                    "url": url,
                    "error": body.decode("utf-8", errors="replace")[:2000],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
        )
        return 1
    elapsed_ms = (time.perf_counter() - started) * 1000

    decoded: dict[str, Any] | None = None
    if "json" in content_type:
        decoded = json.loads(body.decode("utf-8"))
    summary = _summarize_payload(decoded)
    failures: list[str] = []
    if args.max_ms is not None and elapsed_ms > args.max_ms:
        failures.append(
            f"elapsed_ms {elapsed_ms:.3f} exceeds max_ms {args.max_ms:.3f}",
        )
    if args.max_bytes is not None and len(body) > args.max_bytes:
        failures.append(f"response_bytes {len(body)} exceeds max_bytes {args.max_bytes}")

    print(
        json.dumps(
            {
                "status": status,
                "elapsed_ms": round(elapsed_ms, 3),
                "response_bytes": len(body),
                "content_type": content_type,
                "url": url,
                **summary,
                "assertions": {
                    "status": "failed" if failures else "passed",
                    **({"failures": failures} if failures else {}),
                },
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
    )
    return 1 if failures else 0


def _summarize_payload(payload: dict[str, Any] | None) -> dict[str, object]:
    if payload is None:
        return {}
    turns = payload.get("turns")
    timeline = payload.get("timeline")
    return {
        "run_id": payload.get("run_id"),
        "session_key": payload.get("session_key"),
        "status_text": payload.get("status"),
        "turn_count": len(turns) if isinstance(turns, list) else None,
        "timeline_count": len(timeline) if isinstance(timeline, list) else None,
    }


if __name__ == "__main__":
    raise SystemExit(main())
