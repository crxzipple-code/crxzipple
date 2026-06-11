from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
import ipaddress
import json
import socket
import time
from typing import Any
from urllib.parse import urlparse

import requests

from crxzipple.modules.tool.domain import ToolExecutionContext, ToolRunResult


BENCHMARK_PROXY_NETWORK = ipaddress.ip_network("198.18.0.0/15")
DEFAULT_TIMEOUT_SECONDS = 12
MAX_TIMEOUT_SECONDS = 30
DEFAULT_MAX_BYTES = 262_144
MAX_BYTES = 1_048_576
DEFAULT_TEXT_CHARS = 4_000
MAX_TEXT_CHARS = 12_000
USER_AGENT = "crxzipple-public-web-fetch/1.0"


@dataclass(frozen=True, slots=True)
class _FetchResult:
    url: str
    final_url: str
    status_code: int
    reason: str
    content_type: str | None
    content_length_header: str | None
    body: bytes
    truncated: bool
    elapsed_ms: int
    fetched_at: str


async def _fetch_json_handler(
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None = None,
) -> ToolRunResult:
    url = _required_text(arguments.get("url"), label="url")
    json_path = _optional_text(arguments.get("json_path"))
    timeout_seconds = _positive_int(
        arguments.get("timeout_seconds"),
        default=DEFAULT_TIMEOUT_SECONDS,
        maximum=MAX_TIMEOUT_SECONDS,
    )
    max_bytes = _positive_int(
        arguments.get("max_bytes"),
        default=DEFAULT_MAX_BYTES,
        maximum=MAX_BYTES,
    )
    result = await asyncio.to_thread(
        _fetch_public_url,
        url,
        timeout_seconds=timeout_seconds,
        max_bytes=max_bytes,
        accept="application/json, text/json;q=0.9, */*;q=0.5",
    )
    try:
        decoded = json.loads(result.body.decode(_response_encoding(result), errors="replace"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Public URL did not return valid JSON: {result.final_url}",
        ) from exc

    extracted = _extract_json_path(decoded, json_path) if json_path else None
    preview = _bounded_json(decoded, max_chars=4_000)
    details = _base_details(
        result,
        execution_context=execution_context,
        max_bytes=max_bytes,
    )
    details["json"] = decoded
    if json_path:
        details["json_path"] = json_path
        details["json_path_found"] = extracted.found
        details["json_path_value"] = extracted.value

    lines = [
        "Fetched public JSON:",
        f"- URL: {result.final_url}",
        f"- HTTP: {result.status_code} {result.reason}",
        f"- Content-Type: {result.content_type or 'unknown'}",
        f"- Fetched at: {result.fetched_at}",
    ]
    if result.truncated:
        lines.append(f"- Body truncated at {max_bytes} bytes before JSON parsing.")
    if json_path:
        if extracted.found:
            lines.append(f"- JSON path {json_path}: {_render_scalar(extracted.value)}")
        else:
            lines.append(f"- JSON path {json_path}: not found")
    lines.extend(("", "JSON preview:", preview))
    return ToolRunResult.text(
        "\n".join(lines),
        details=details,
        metadata={
            "tool": "web.fetch_json",
            "url": result.url,
            "final_url": result.final_url,
            "status_code": result.status_code,
            "content_type": result.content_type,
            "fetched_at": result.fetched_at,
            "json_path": json_path,
            "json_path_found": extracted.found if json_path else None,
        },
    )


async def _fetch_text_handler(
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None = None,
) -> ToolRunResult:
    url = _required_text(arguments.get("url"), label="url")
    timeout_seconds = _positive_int(
        arguments.get("timeout_seconds"),
        default=DEFAULT_TIMEOUT_SECONDS,
        maximum=MAX_TIMEOUT_SECONDS,
    )
    max_bytes = _positive_int(
        arguments.get("max_bytes"),
        default=DEFAULT_MAX_BYTES,
        maximum=MAX_BYTES,
    )
    max_chars = _positive_int(
        arguments.get("max_chars"),
        default=DEFAULT_TEXT_CHARS,
        maximum=MAX_TEXT_CHARS,
    )
    result = await asyncio.to_thread(
        _fetch_public_url,
        url,
        timeout_seconds=timeout_seconds,
        max_bytes=max_bytes,
        accept="text/html, text/plain;q=0.9, application/json;q=0.8, */*;q=0.5",
    )
    text = result.body.decode(_response_encoding(result), errors="replace")
    preview, text_truncated = _truncate_text(text, max_chars=max_chars)
    details = _base_details(
        result,
        execution_context=execution_context,
        max_bytes=max_bytes,
    )
    details.update(
        {
            "text_preview": preview,
            "text_truncated": text_truncated,
            "max_chars": max_chars,
        },
    )
    lines = [
        "Fetched public text:",
        f"- URL: {result.final_url}",
        f"- HTTP: {result.status_code} {result.reason}",
        f"- Content-Type: {result.content_type or 'unknown'}",
        f"- Fetched at: {result.fetched_at}",
    ]
    if result.truncated:
        lines.append(f"- Body truncated at {max_bytes} bytes.")
    if text_truncated:
        lines.append(f"- Text preview truncated at {max_chars} chars.")
    lines.extend(("", "Text preview:", preview))
    return ToolRunResult.text(
        "\n".join(lines),
        details=details,
        metadata={
            "tool": "web.fetch_text",
            "url": result.url,
            "final_url": result.final_url,
            "status_code": result.status_code,
            "content_type": result.content_type,
            "fetched_at": result.fetched_at,
            "text_truncated": text_truncated,
        },
    )


def fetch_json(_deps: Any):
    return _fetch_json_handler


def fetch_text(_deps: Any):
    return _fetch_text_handler


def _fetch_public_url(
    url: str,
    *,
    timeout_seconds: int,
    max_bytes: int,
    accept: str,
) -> _FetchResult:
    _validate_public_url(url)
    start = time.monotonic()
    with requests.get(
        url,
        headers={
            "Accept": accept,
            "User-Agent": USER_AGENT,
        },
        timeout=timeout_seconds,
        allow_redirects=True,
        stream=True,
    ) as response:
        _validate_public_url(response.url)
        body, truncated = _read_bounded(response.iter_content(chunk_size=16_384), max_bytes)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        if response.status_code >= 400:
            preview = body[:500].decode("utf-8", errors="replace").replace("\n", " ")
            raise ValueError(
                f"Public URL returned HTTP {response.status_code}: {preview}",
            )
        return _FetchResult(
            url=url,
            final_url=response.url,
            status_code=response.status_code,
            reason=response.reason,
            content_type=response.headers.get("Content-Type"),
            content_length_header=response.headers.get("Content-Length"),
            body=body,
            truncated=truncated,
            elapsed_ms=elapsed_ms,
            fetched_at=datetime.now(UTC).isoformat(),
        )


def _validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("web fetch only supports http and https URLs.")
    if not parsed.hostname:
        raise ValueError("web fetch URL must include a hostname.")
    host = parsed.hostname.strip().lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
        raise ValueError("web fetch does not allow localhost URLs.")
    try:
        literal_ip = ipaddress.ip_address(host)
    except ValueError:
        literal_ip = None
    if literal_ip is not None:
        _reject_non_public_ip(literal_ip, allow_benchmark_proxy=False)
        return
    try:
        infos = socket.getaddrinfo(host, parsed.port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"web fetch could not resolve hostname '{host}'.") from exc
    checked: set[str] = set()
    for info in infos:
        raw_ip = info[4][0]
        if raw_ip in checked:
            continue
        checked.add(raw_ip)
        _reject_non_public_ip(
            ipaddress.ip_address(raw_ip),
            allow_benchmark_proxy=True,
        )


def _reject_non_public_ip(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
    *,
    allow_benchmark_proxy: bool,
) -> None:
    if allow_benchmark_proxy and ip in BENCHMARK_PROXY_NETWORK:
        return
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        raise ValueError(f"web fetch does not allow non-public address {ip}.")


def _read_bounded(chunks: Iterable[bytes], max_bytes: int) -> tuple[bytes, bool]:
    parts: list[bytes] = []
    total = 0
    truncated = False
    for chunk in chunks:
        if not chunk:
            continue
        remaining = max_bytes - total
        if remaining <= 0:
            truncated = True
            break
        if len(chunk) > remaining:
            parts.append(chunk[:remaining])
            total += remaining
            truncated = True
            break
        parts.append(chunk)
        total += len(chunk)
    return b"".join(parts), truncated


def _response_encoding(result: _FetchResult) -> str:
    content_type = result.content_type or ""
    for part in content_type.split(";"):
        part = part.strip()
        if part.lower().startswith("charset="):
            value = part.split("=", 1)[1].strip()
            if value:
                return value
    return "utf-8"


def _base_details(
    result: _FetchResult,
    *,
    execution_context: ToolExecutionContext | None,
    max_bytes: int,
) -> dict[str, Any]:
    return {
        "url": result.url,
        "final_url": result.final_url,
        "status_code": result.status_code,
        "reason": result.reason,
        "content_type": result.content_type,
        "content_length_header": result.content_length_header,
        "body_bytes": len(result.body),
        "body_truncated": result.truncated,
        "max_bytes": max_bytes,
        "elapsed_ms": result.elapsed_ms,
        "fetched_at": result.fetched_at,
        "execution_context": (
            execution_context.to_payload() if execution_context is not None else None
        ),
    }


@dataclass(frozen=True, slots=True)
class _JsonPathResult:
    found: bool
    value: Any = None


def _extract_json_path(value: Any, path: str | None) -> _JsonPathResult:
    if path is None:
        return _JsonPathResult(found=False)
    current = value
    for segment in _json_path_segments(path):
        key, indexes = segment
        if key:
            if not isinstance(current, dict) or key not in current:
                return _JsonPathResult(found=False)
            current = current[key]
        for index in indexes:
            if not isinstance(current, list):
                return _JsonPathResult(found=False)
            if index < 0 or index >= len(current):
                return _JsonPathResult(found=False)
            current = current[index]
    return _JsonPathResult(found=True, value=current)


def _json_path_segments(path: str) -> list[tuple[str, list[int]]]:
    segments: list[tuple[str, list[int]]] = []
    for raw_segment in path.strip().split("."):
        if not raw_segment:
            continue
        key = raw_segment
        indexes: list[int] = []
        if "[" in raw_segment:
            key = raw_segment.split("[", 1)[0]
            remainder = raw_segment[len(key):]
            while remainder:
                if not remainder.startswith("["):
                    raise ValueError(f"Invalid JSON path segment: {raw_segment}")
                end = remainder.find("]")
                if end < 0:
                    raise ValueError(f"Invalid JSON path segment: {raw_segment}")
                raw_index = remainder[1:end].strip()
                try:
                    indexes.append(int(raw_index))
                except ValueError as exc:
                    raise ValueError(f"Invalid JSON path index: {raw_index}") from exc
                remainder = remainder[end + 1:]
        segments.append((key, indexes))
    return segments


def _bounded_json(value: Any, *, max_chars: int) -> str:
    rendered = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    preview, truncated = _truncate_text(rendered, max_chars=max_chars)
    if truncated:
        return preview + "\n... <truncated>"
    return preview


def _truncate_text(value: str, *, max_chars: int) -> tuple[str, bool]:
    if len(value) <= max_chars:
        return value, False
    return value[:max_chars], True


def _render_scalar(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _required_text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required.")
    return value.strip()


def _optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _positive_int(value: Any, *, default: int, maximum: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return default
    return min(parsed, maximum)
