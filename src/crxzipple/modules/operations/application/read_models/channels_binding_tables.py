from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.channels_sections import (
    table,
)
from crxzipple.modules.operations.application.read_models.channels_table_rows import (
    account_binding_rows,
    connection_binding_row,
    profile_row,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableSectionModel,
)


def account_bindings_table(
    bindings: tuple[Any, ...],
    *,
    profiles: tuple[Any, ...],
) -> OperationsTableSectionModel:
    rows = account_binding_rows(bindings, profiles=profiles)
    return table(
        "channel_bindings",
        "Account Bindings",
        (
            ("channel_type", "Channel Type"),
            ("account_id", "Account ID"),
            ("runtime_id", "Runtime ID"),
            ("transport_mode", "Transport Mode"),
            ("status", "Status"),
            ("updated_at", "Updated At"),
        ),
        rows,
        total=len(rows),
        empty_state="No channel account bindings registered.",
    )


def connection_bindings_table(
    bindings: tuple[Any, ...],
) -> OperationsTableSectionModel:
    rows = tuple(connection_binding_row(binding) for binding in bindings)
    return table(
        "connection_bindings",
        "Connection Bindings",
        (
            ("channel_type", "Channel Type"),
            ("connection_id", "Connection ID"),
            ("runtime_id", "Runtime ID"),
            ("account_id", "Account ID"),
            ("conversation_id", "Conversation ID"),
            ("supports_streaming", "Streaming"),
            ("observe_cursor", "Observe Cursor"),
            ("live_cursor", "Live Cursor"),
            ("updated_at", "Updated At"),
        ),
        rows,
        total=len(rows),
        empty_state="No channel connection bindings registered.",
    )


def profiles_table(
    profiles: tuple[Any, ...],
) -> OperationsTableSectionModel:
    rows = tuple(profile_row(profile) for profile in profiles)
    return table(
        "channel_profiles",
        "Channel Profiles",
        (
            ("channel_type", "Channel Type"),
            ("status", "Status"),
            ("account_count", "Accounts"),
            ("transport_modes", "Transport Modes"),
            ("capabilities", "Capabilities"),
            ("metadata", "Metadata"),
        ),
        rows,
        total=len(rows),
        empty_state="No channel profiles configured.",
    )
