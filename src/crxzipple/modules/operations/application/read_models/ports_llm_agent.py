from __future__ import annotations

from typing import Any, Protocol


class OperationsLlmQueryPort(Protocol):
    def list_profiles(self) -> list[Any]: ...

    def list_invocations(
        self,
        *,
        run_id: str | None = None,
        limit: int = 100,
    ) -> list[Any]: ...

    def list_response_events(
        self,
        invocation_id: str,
        *,
        limit: int | None = None,
        after_sequence: int | None = None,
    ) -> list[Any]: ...

    def response_event_retention_policy(self) -> Any: ...


class OperationsAgentProfilePort(Protocol):
    def list_profiles(self) -> list[Any]: ...

    def get_profile(self, profile_id: str) -> Any: ...
