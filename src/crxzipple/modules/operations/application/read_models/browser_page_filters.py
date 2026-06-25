from __future__ import annotations

from crxzipple.modules.operations.application.read_models.browser_models import (
    BrowserOperationsQuery,
)
from crxzipple.modules.operations.application.read_models.browser_values import (
    normalized_filter,
    text,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
)


def normalize_browser_query(
    query: BrowserOperationsQuery | None,
) -> BrowserOperationsQuery:
    if query is None:
        return BrowserOperationsQuery()
    return BrowserOperationsQuery(
        status=normalized_filter(query.status),
        profile=normalized_filter(query.profile),
        search=query.search.strip() if isinstance(query.search, str) else "",
        limit=max(1, min(int(query.limit), 200)),
        offset=max(0, int(query.offset)),
    )


def filter_rows(
    rows: tuple[OperationsTableRowModel, ...],
    query: BrowserOperationsQuery,
) -> tuple[OperationsTableRowModel, ...]:
    filtered = rows
    if query.status != "all":
        filtered = tuple(
            row for row in filtered if text(row.status, "").lower() == query.status
        )
    if query.profile != "all":
        filtered = tuple(
            row
            for row in filtered
            if row.cells.get("profile", "").lower() == query.profile
        )
    if query.search:
        needle = query.search.lower()
        filtered = tuple(
            row
            for row in filtered
            if needle in " ".join(str(value) for value in row.cells.values()).lower()
        )
    return filtered


def visible_rows(
    rows: tuple[OperationsTableRowModel, ...],
    query: BrowserOperationsQuery,
) -> tuple[OperationsTableRowModel, ...]:
    return rows[query.offset : query.offset + query.limit]
