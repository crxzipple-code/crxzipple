from crxzipple.modules.memory.infrastructure.indexing.sqlite_index_manager import (
    FileMemoryIndexManager,
)
from crxzipple.modules.memory.infrastructure.indexing.sqlite_index_store import (
    SqliteMemoryIndexStore,
)

_EMBEDDING_EXPORTS = {
    "LocalHashedMemoryEmbeddingProvider",
    "OpenAICompatibleMemoryEmbeddingProvider",
}

__all__ = [
    "FileMemoryIndexManager",
    "LocalHashedMemoryEmbeddingProvider",
    "OpenAICompatibleMemoryEmbeddingProvider",
    "SqliteMemoryIndexStore",
]


def __getattr__(name: str) -> object:
    if name in _EMBEDDING_EXPORTS:
        from crxzipple.modules.memory.infrastructure.indexing import embeddings

        value = getattr(embeddings, name)
        globals()[name] = value
        return value
    raise AttributeError(name)
