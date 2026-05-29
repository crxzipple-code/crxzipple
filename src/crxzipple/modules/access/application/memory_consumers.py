from __future__ import annotations

from crxzipple.modules.access.application.read_models import (
    AccessConsumerBindingReadModel,
)


_VECTOR_EMBEDDING_SLOT = "embedding_api_key"


def memory_access_consumer_bindings(
    memory_config: object | None,
) -> tuple[AccessConsumerBindingReadModel, ...]:
    """Project Memory-owned credential needs into the Access requirement catalog."""

    if memory_config is None:
        return ()
    vector_provider = _optional_text(getattr(memory_config, "vector_provider", None))
    if vector_provider != "openai_compatible":
        return ()
    binding_id = _optional_text(
        getattr(memory_config, "vector_credential_binding_id", None),
    )
    credential_bindings = (
        {_VECTOR_EMBEDDING_SLOT: binding_id}
        if binding_id is not None
        else {}
    )
    return (
        AccessConsumerBindingReadModel(
            binding_id="memory:engine:file_markdown:vector_embeddings",
            consumer_module="memory",
            consumer_kind="memory_engine",
            consumer_id="file_markdown.vector_embeddings",
            display_name="Memory vector embeddings",
            enabled=True,
            credential_binding_id=binding_id,
            credential_bindings=credential_bindings,
            requirement_sets=(
                (f"openai_compatible:api_key({_VECTOR_EMBEDDING_SLOT})",),
            ),
            status="active",
            metadata={
                "source": "memory.bootstrap_config",
                "engine_id": "file_markdown",
                "provider": "openai_compatible",
                "slot": _VECTOR_EMBEDDING_SLOT,
            },
        ),
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


__all__ = ["memory_access_consumer_bindings"]
