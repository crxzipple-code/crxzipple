from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import requests

from crxzipple.modules.tool.domain import ToolExecutionContext, ToolRunResult


GOLD_API_URL = "https://api.gold-api.com/price/XAU"
FX_API_URL = "https://open.er-api.com/v6/latest/USD"
TROY_OUNCE_GRAMS = 31.1034768
DEFAULT_TIMEOUT_SECONDS = 12


async def _gold_spot_handler(
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None = None,
) -> ToolRunResult:
    timeout_seconds = _positive_timeout(
        arguments.get("timeout_seconds"),
        default=DEFAULT_TIMEOUT_SECONDS,
    )
    quote = await asyncio.to_thread(_fetch_gold_quote, timeout_seconds)
    rates = await asyncio.to_thread(_fetch_usd_rates, timeout_seconds)
    cny_rate = _float_value(rates.get("rates", {}).get("CNY"))
    if cny_rate is None or cny_rate <= 0:
        raise ValueError("USD/CNY rate was not available from the exchange-rate source.")

    usd_per_oz = _float_value(quote.get("price"))
    if usd_per_oz is None or usd_per_oz <= 0:
        raise ValueError("XAU/USD spot price was not available from the gold source.")

    cny_per_gram = usd_per_oz * cny_rate / TROY_OUNCE_GRAMS
    updated_at = _string_value(quote.get("updatedAt"))
    fx_updated_at = _string_value(rates.get("time_last_update_utc"))
    generated_at = datetime.now(UTC).isoformat()

    details = {
        "instrument": "XAU",
        "source": {
            "gold": {
                "name": "Gold API",
                "url": GOLD_API_URL,
                "updated_at": updated_at,
                "raw": quote,
            },
            "fx": {
                "name": "ExchangeRate-API open endpoint",
                "url": FX_API_URL,
                "base": "USD",
                "quote": "CNY",
                "updated_at": fx_updated_at,
                "raw": {
                    "result": rates.get("result"),
                    "provider": rates.get("provider"),
                    "time_last_update_utc": rates.get("time_last_update_utc"),
                    "time_next_update_utc": rates.get("time_next_update_utc"),
                    "base_code": rates.get("base_code"),
                    "CNY": cny_rate,
                },
            },
        },
        "quote": {
            "usd_per_troy_ounce": round(usd_per_oz, 4),
            "usd_per_gram": round(usd_per_oz / TROY_OUNCE_GRAMS, 4),
            "usd_cny": round(cny_rate, 6),
            "cny_per_gram": round(cny_per_gram, 4),
        },
        "unit_notes": {
            "usd_per_troy_ounce": "international spot-style XAU quote",
            "cny_per_gram": "computed from USD/oz using USD/CNY and 31.1034768 grams per troy ounce",
        },
        "generated_at": generated_at,
        "execution_context": (
            execution_context.to_payload() if execution_context is not None else None
        ),
    }
    text = (
        "Gold quote:\n"
        f"- USD/oz: {usd_per_oz:,.2f}\n"
        f"- CNY/g: {cny_per_gram:,.2f}\n"
        f"- USD/CNY: {cny_rate:.6f}\n"
        f"- Gold source updated: {updated_at or 'unknown'}\n"
        f"- FX source updated: {fx_updated_at or 'unknown'}\n"
        "Sources: Gold API XAU endpoint; ExchangeRate-API open USD latest endpoint."
    )
    return ToolRunResult.text(
        text,
        details=details,
        metadata={
            "tool": "market_quote.gold_spot",
            "generated_at": generated_at,
            "gold_source": GOLD_API_URL,
            "fx_source": FX_API_URL,
        },
    )


def gold_spot(_deps: Any):
    return _gold_spot_handler


def _fetch_gold_quote(timeout_seconds: int) -> dict[str, Any]:
    return _fetch_json(GOLD_API_URL, timeout_seconds=timeout_seconds)


def _fetch_usd_rates(timeout_seconds: int) -> dict[str, Any]:
    return _fetch_json(FX_API_URL, timeout_seconds=timeout_seconds)


def _fetch_json(url: str, *, timeout_seconds: int) -> dict[str, Any]:
    last_error: Exception | None = None
    for _ in range(3):
        try:
            response = requests.get(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "crxzipple-market-quote/1.0",
                },
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            decoded = response.json()
            if not isinstance(decoded, dict):
                raise ValueError(
                    "Market quote source returned a non-object JSON payload.",
                )
            return decoded
        except requests.RequestException as exc:
            last_error = exc
        except json.JSONDecodeError as exc:
            raise ValueError("Market quote source returned invalid JSON.") from exc
    message = str(last_error) if last_error is not None else "unknown error"
    raise ValueError(f"Market quote source is unavailable: {message}")


def _positive_timeout(value: Any, *, default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return default
    return min(parsed, 30)


def _float_value(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_value(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None
