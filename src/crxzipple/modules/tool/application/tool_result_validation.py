from __future__ import annotations

import json

from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.domain.value_objects import ToolRunResult


def validate_tool_result_details(
    result: ToolRunResult,
    *,
    details_max_chars: int,
) -> None:
    if result.details is None:
        return
    try:
        serialized = json.dumps(
            result.details,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except TypeError as exc:
        raise ToolValidationError(
            "Tool run result details must be JSON-serializable.",
        ) from exc
    if len(serialized) > details_max_chars:
        raise ToolValidationError(
            "Tool run result details exceed the allowed size budget "
            f"({details_max_chars} chars).",
        )


__all__ = ["validate_tool_result_details"]
