from __future__ import annotations

from typing import Mapping


class ChannelValidationError(ValueError):
    """Raised when channel configuration or runtime state is invalid."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = dict(details or {})

    @property
    def has_payload(self) -> bool:
        return self.code is not None or bool(self.details)

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {"message": self.message}
        if self.code is not None:
            payload["code"] = self.code
        if self.details:
            payload["details"] = dict(self.details)
        return payload
