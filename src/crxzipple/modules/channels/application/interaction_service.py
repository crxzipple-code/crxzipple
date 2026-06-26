from __future__ import annotations

from dataclasses import replace

from crxzipple.modules.channels.application.ports import ChannelInteractionRegistryStore
from crxzipple.modules.channels.application.service_helpers import (
    normalize_identifier,
    normalize_key,
    utcnow,
)
from crxzipple.modules.channels.domain import (
    ChannelInteraction,
    ChannelInteractionRegistry,
    ChannelValidationError,
)


class ChannelInteractionService:
    def __init__(self, *, registry_store: ChannelInteractionRegistryStore) -> None:
        self.registry_store = registry_store

    def snapshot(self) -> ChannelInteractionRegistry:
        return self.registry_store.load()

    def list_interactions(
        self,
        *,
        channel_type: str | None = None,
        run_id: str | None = None,
        session_key: str | None = None,
    ) -> tuple[ChannelInteraction, ...]:
        interactions = self.registry_store.load().interactions
        if channel_type is not None:
            normalized_channel = normalize_key(channel_type)
            interactions = tuple(
                item
                for item in interactions
                if normalize_key(item.channel_type) == normalized_channel
            )
        if run_id is not None:
            normalized_run_id = normalize_identifier(run_id)
            interactions = tuple(
                item
                for item in interactions
                if normalize_identifier(item.run_id or "") == normalized_run_id
            )
        if session_key is not None:
            normalized_session_key = normalize_identifier(session_key)
            interactions = tuple(
                item
                for item in interactions
                if normalize_identifier(item.session_key or "")
                == normalized_session_key
            )
        return interactions

    def get_interaction(self, interaction_id: str) -> ChannelInteraction | None:
        normalized = normalize_identifier(interaction_id)
        for interaction in self.registry_store.load().interactions:
            if interaction.interaction_id == normalized:
                return interaction
        return None

    def get_interaction_by_run_id(self, run_id: str) -> ChannelInteraction | None:
        normalized = normalize_identifier(run_id)
        if not normalized:
            return None
        for interaction in self.registry_store.load().interactions:
            if normalize_identifier(interaction.run_id or "") == normalized:
                return interaction
        return None

    def upsert_interaction(
        self,
        interaction: ChannelInteraction,
    ) -> ChannelInteraction:
        if not interaction.interaction_id.strip():
            raise ChannelValidationError("channel interaction must include interaction_id.")
        if not interaction.channel_type.strip():
            raise ChannelValidationError("channel interaction must include channel_type.")

        def _mutate(registry: ChannelInteractionRegistry) -> ChannelInteractionRegistry:
            existing = next(
                (
                    item
                    for item in registry.interactions
                    if item.interaction_id == interaction.interaction_id
                ),
                None,
            )
            updated_interaction = replace(
                interaction,
                created_at=(
                    existing.created_at
                    if existing is not None
                    else interaction.created_at
                ),
                updated_at=utcnow(),
            )
            interactions_by_id = {
                item.interaction_id: item
                for item in registry.interactions
            }
            interactions_by_id[updated_interaction.interaction_id] = updated_interaction
            return replace(
                registry,
                interactions=tuple(
                    interactions_by_id[key] for key in sorted(interactions_by_id)
                ),
            )

        registry = self.registry_store.update(_mutate)
        resolved = next(
            (
                item
                for item in registry.interactions
                if item.interaction_id == interaction.interaction_id
            ),
            None,
        )
        if resolved is None:
            raise ChannelValidationError("channel interaction upsert did not persist.")
        return resolved

    def bind_run(
        self,
        interaction_id: str,
        *,
        run_id: str,
        session_key: str | None = None,
        agent_id: str | None = None,
        status: str = "submitted",
        metadata: dict[str, object] | None = None,
    ) -> ChannelInteraction | None:
        normalized_interaction_id = normalize_identifier(interaction_id)
        normalized_run_id = normalize_identifier(run_id)
        if not normalized_interaction_id:
            raise ChannelValidationError("interaction_id is required to bind a run.")
        if not normalized_run_id:
            raise ChannelValidationError("run_id is required to bind a run.")
        found = False

        def _mutate(registry: ChannelInteractionRegistry) -> ChannelInteractionRegistry:
            nonlocal found
            interactions: list[ChannelInteraction] = []
            for item in registry.interactions:
                if item.interaction_id == normalized_interaction_id:
                    found = True
                    interactions.append(
                        replace(
                            item,
                            run_id=normalized_run_id,
                            session_key=(
                                normalize_identifier(session_key)
                                if isinstance(session_key, str) and session_key.strip()
                                else item.session_key
                            ),
                            agent_id=(
                                normalize_identifier(agent_id)
                                if isinstance(agent_id, str) and agent_id.strip()
                                else item.agent_id
                            ),
                            status=normalize_identifier(status) or item.status,
                            metadata={
                                **dict(item.metadata),
                                **dict(metadata or {}),
                            },
                            updated_at=utcnow(),
                        )
                    )
                else:
                    interactions.append(item)
            if not found:
                return registry
            return replace(registry, interactions=tuple(interactions))

        registry = self.registry_store.update(_mutate)
        if not found:
            return None
        return next(
            (
                item
                for item in registry.interactions
                if item.interaction_id == normalized_interaction_id
            ),
            None,
        )

    def bind_run_by_run_id(
        self,
        run_id: str,
        *,
        session_key: str | None = None,
        agent_id: str | None = None,
        status: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> tuple[ChannelInteraction, ...]:
        normalized_run_id = normalize_identifier(run_id)
        if not normalized_run_id:
            raise ChannelValidationError("run_id is required to bind channel interactions.")
        normalized_status = (
            normalize_identifier(status)
            if isinstance(status, str) and status.strip()
            else None
        )
        updated_ids: list[str] = []

        def _mutate(registry: ChannelInteractionRegistry) -> ChannelInteractionRegistry:
            interactions: list[ChannelInteraction] = []
            for item in registry.interactions:
                if normalize_identifier(item.run_id or "") != normalized_run_id:
                    interactions.append(item)
                    continue
                updated = replace(
                    item,
                    session_key=(
                        normalize_identifier(session_key)
                        if isinstance(session_key, str) and session_key.strip()
                        else item.session_key
                    ),
                    agent_id=(
                        normalize_identifier(agent_id)
                        if isinstance(agent_id, str) and agent_id.strip()
                        else item.agent_id
                    ),
                    status=normalized_status or item.status,
                    metadata={
                        **dict(item.metadata),
                        **dict(metadata or {}),
                    },
                    updated_at=utcnow(),
                )
                updated_ids.append(updated.interaction_id)
                interactions.append(updated)
            if not updated_ids:
                return registry
            return replace(registry, interactions=tuple(interactions))

        registry = self.registry_store.update(_mutate)
        if not updated_ids:
            return ()
        updated_id_set = set(updated_ids)
        return tuple(
            item for item in registry.interactions if item.interaction_id in updated_id_set
        )

    def mark_status(
        self,
        interaction_id: str,
        *,
        status: str,
        last_error: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ChannelInteraction | None:
        normalized_interaction_id = normalize_identifier(interaction_id)
        normalized_status = normalize_identifier(status)
        if not normalized_interaction_id:
            raise ChannelValidationError(
                "interaction_id is required to update interaction status.",
            )
        if not normalized_status:
            raise ChannelValidationError("status is required to update interaction status.")
        found = False

        def _mutate(registry: ChannelInteractionRegistry) -> ChannelInteractionRegistry:
            nonlocal found
            interactions: list[ChannelInteraction] = []
            for item in registry.interactions:
                if item.interaction_id == normalized_interaction_id:
                    found = True
                    interactions.append(
                        replace(
                            item,
                            status=normalized_status,
                            last_error=last_error,
                            metadata={
                                **dict(item.metadata),
                                **dict(metadata or {}),
                            },
                            updated_at=utcnow(),
                        )
                    )
                else:
                    interactions.append(item)
            if not found:
                return registry
            return replace(registry, interactions=tuple(interactions))

        registry = self.registry_store.update(_mutate)
        if not found:
            return None
        return next(
            (
                item
                for item in registry.interactions
                if item.interaction_id == normalized_interaction_id
            ),
            None,
        )
