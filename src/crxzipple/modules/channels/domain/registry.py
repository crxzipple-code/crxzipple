from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.channels.domain.entities import (
    ChannelAccountRuntimeBinding,
    ChannelConnectionBinding,
    ChannelInteraction,
    ChannelRuntimeRegistration,
)


@dataclass(frozen=True, slots=True)
class ChannelRuntimeRegistry:
    runtimes: tuple[ChannelRuntimeRegistration, ...] = ()
    account_bindings: tuple[ChannelAccountRuntimeBinding, ...] = ()
    connection_bindings: tuple[ChannelConnectionBinding, ...] = ()

    def to_payload(self) -> dict[str, object]:
        return {
            "runtimes": [runtime.to_payload() for runtime in self.runtimes],
            "account_bindings": [binding.to_payload() for binding in self.account_bindings],
            "connection_bindings": [
                binding.to_payload() for binding in self.connection_bindings
            ],
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "ChannelRuntimeRegistry":
        raw_runtimes = payload.get("runtimes")
        raw_account_bindings = payload.get("account_bindings")
        raw_connection_bindings = payload.get("connection_bindings")
        runtime_payloads = raw_runtimes if isinstance(raw_runtimes, list) else []
        account_binding_payloads = (
            raw_account_bindings if isinstance(raw_account_bindings, list) else []
        )
        connection_binding_payloads = (
            raw_connection_bindings if isinstance(raw_connection_bindings, list) else []
        )
        return cls(
            runtimes=tuple(
                ChannelRuntimeRegistration.from_payload(item)
                for item in runtime_payloads
                if isinstance(item, dict)
            ),
            account_bindings=tuple(
                ChannelAccountRuntimeBinding.from_payload(item)
                for item in account_binding_payloads
                if isinstance(item, dict)
            ),
            connection_bindings=tuple(
                ChannelConnectionBinding.from_payload(item)
                for item in connection_binding_payloads
                if isinstance(item, dict)
            ),
        )


@dataclass(frozen=True, slots=True)
class ChannelInteractionRegistry:
    interactions: tuple[ChannelInteraction, ...] = ()

    def to_payload(self) -> dict[str, object]:
        return {
            "interactions": [interaction.to_payload() for interaction in self.interactions],
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "ChannelInteractionRegistry":
        raw_interactions = payload.get("interactions")
        interaction_payloads = raw_interactions if isinstance(raw_interactions, list) else []
        return cls(
            interactions=tuple(
                ChannelInteraction.from_payload(item)
                for item in interaction_payloads
                if isinstance(item, dict)
            ),
        )
