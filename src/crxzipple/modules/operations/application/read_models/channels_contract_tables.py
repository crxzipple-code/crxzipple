from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.channels_contract_rows import (
    contract_rows,
)
from crxzipple.modules.operations.application.read_models.channels_sections import table
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableSectionModel,
)


def contracts_table(
    *,
    event_contract_registry: Any | None,
    event_definition_registry: Any | None,
) -> OperationsTableSectionModel:
    rows = contract_rows(
        event_contract_registry=event_contract_registry,
        event_definition_registry=event_definition_registry,
    )
    return table(
        "contracts",
        "Contracts",
        (
            ("type", "Type"),
            ("name", "Name"),
            ("pattern", "Pattern"),
            ("kind", "Kind"),
            ("status", "Status"),
        ),
        rows,
        total=len(rows),
        empty_state="No channel event contracts registered.",
    )
