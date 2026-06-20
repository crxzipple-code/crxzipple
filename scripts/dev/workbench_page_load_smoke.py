#!/usr/bin/env python
"""Smoke Workbench page load latency in a real browser."""

from __future__ import annotations

import argparse
import json
import time
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure Workbench route first-load latency with Playwright.",
    )
    parser.add_argument("run_id", help="Workbench run id to open.")
    parser.add_argument(
        "--frontend-base",
        default="http://127.0.0.1:4173",
        help="Frontend base URL. Defaults to local dev frontend.",
    )
    parser.add_argument(
        "--wait-text",
        default=None,
        help="Text expected on the loaded page. Defaults to run_id.",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=10_000,
        help="Page/load assertion timeout in milliseconds.",
    )
    parser.add_argument(
        "--max-ms",
        type=float,
        default=None,
        help="Optional elapsed-time assertion in milliseconds.",
    )
    parser.add_argument(
        "--screenshot",
        default=None,
        help="Optional screenshot path for visual inspection.",
    )
    args = parser.parse_args()

    url = f"{args.frontend_base.rstrip('/')}/workbench/runs/{args.run_id}"
    wait_text = args.wait_text or args.run_id
    failures: list[str] = []
    page_title = ""
    body_chars = 0
    console_errors: list[str] = []
    page_errors: list[str] = []
    request_failures: list[str] = []
    api_timings: list[dict[str, object]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 960})
        request_started_at: dict[object, float] = {}
        page.on(
            "request",
            lambda request: request_started_at.setdefault(request, time.perf_counter()),
        )
        page.on(
            "response",
            lambda response: (
                api_timings.append(
                    {
                        "status": response.status,
                        "elapsed_ms": round(
                            (
                                time.perf_counter()
                                - request_started_at.get(
                                    response.request,
                                    time.perf_counter(),
                                )
                            )
                            * 1000,
                            3,
                        ),
                        "url": response.url,
                    }
                )
                if "/api/" in response.url
                else None
            ),
        )
        page.on(
            "console",
            lambda message: (
                console_errors.append(f"{message.type}: {message.text}")
                if message.type in {"error", "warning"}
                else None
            ),
        )
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on(
            "requestfailed",
            lambda request: request_failures.append(
                f"{request.method} {request.url}: {request.failure}"
            ),
        )
        try:
            started = time.perf_counter()
            page.goto(url, wait_until="domcontentloaded", timeout=args.timeout_ms)
            page.get_by_text(wait_text).first.wait_for(timeout=args.timeout_ms)
            page_title = page.title()
            body_chars = len(page.locator("body").inner_text(timeout=args.timeout_ms))
            if args.screenshot:
                page.screenshot(path=args.screenshot, full_page=True)
        except PlaywrightTimeoutError as exc:
            failures.append(f"timeout waiting for page text {wait_text!r}: {exc}")
        finally:
            browser.close()
    elapsed_ms = (time.perf_counter() - started) * 1000
    if args.max_ms is not None and elapsed_ms > args.max_ms:
        failures.append(
            f"elapsed_ms {elapsed_ms:.3f} exceeds max_ms {args.max_ms:.3f}",
        )

    payload: dict[str, Any] = {
        "url": url,
        "run_id": args.run_id,
        "wait_text": wait_text,
        "elapsed_ms": round(elapsed_ms, 3),
        "page_title": page_title,
        "body_chars": body_chars,
        "console_errors": console_errors[-10:],
        "page_errors": page_errors[-10:],
        "request_failures": request_failures[-10:],
        "api_timings": api_timings[-20:],
        "assertions": {
            "status": "failed" if failures else "passed",
            **({"failures": failures} if failures else {}),
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
