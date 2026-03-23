from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
import json
from typing import Any

import typer


def _normalize(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _normalize(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def echo_data(value: Any) -> None:
    typer.echo(json.dumps(_normalize(value), indent=2, sort_keys=True))
