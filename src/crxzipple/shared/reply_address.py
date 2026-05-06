from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ReplyAddress:
    channel_type: str
    channel_account_id: str | None = None
    connection_id: str | None = None
    webhook_callback_url: str | None = None
    external_conversation_id: str | None = None
    external_thread_id: str | None = None
    external_user_id: str | None = None
    route_hint: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.channel_type.strip():
            raise ValueError("ReplyAddress.channel_type cannot be empty.")
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_payload(self) -> dict[str, Any]:
        return {
            "channel_type": self.channel_type,
            "channel_account_id": self.channel_account_id,
            "connection_id": self.connection_id,
            "webhook_callback_url": self.webhook_callback_url,
            "external_conversation_id": self.external_conversation_id,
            "external_thread_id": self.external_thread_id,
            "external_user_id": self.external_user_id,
            "route_hint": self.route_hint,
            "metadata": dict(self.metadata),
        }
