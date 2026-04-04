from __future__ import annotations

from collections.abc import Sequence
import json
import math
import re

import requests

from crxzipple.modules.llm.infrastructure.adapters.common import (
    ensure_json_response,
    join_url,
    resolve_credential_binding,
)


class LocalHashedMemoryEmbeddingProvider:
    def __init__(
        self,
        *,
        dimensions: int = 64,
        model_name: str = "local-hashed-v1",
    ) -> None:
        self._dimensions = max(dimensions, 16)
        self._model_name = model_name

    @property
    def provider_name(self) -> str:
        return "local"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def provider_key(self) -> str:
        return f"dim:{self._dimensions}"

    def embed_texts(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        return tuple(self._embed_text(text) for text in texts)

    def _embed_text(self, text: str) -> tuple[float, ...]:
        values = [0.0] * self._dimensions
        normalized = _normalize_text(text)
        if not normalized:
            return tuple(values)
        for token in _tokenize(normalized):
            values[_stable_bucket(f"tok:{token}", self._dimensions)] += 1.0
        padded = f"  {normalized}  "
        for size in (3, 4):
            for index in range(max(len(padded) - size + 1, 0)):
                gram = padded[index : index + size]
                values[_stable_bucket(f"gram:{gram}", self._dimensions)] += 0.5
        return _normalize_vector(values)


class OpenAICompatibleMemoryEmbeddingProvider:
    def __init__(
        self,
        *,
        base_url: str,
        model_name: str,
        credential_binding: str,
        timeout_seconds: int = 30,
    ) -> None:
        normalized_base_url = base_url.strip()
        normalized_model_name = model_name.strip()
        normalized_binding = credential_binding.strip()
        if not normalized_base_url:
            raise ValueError("OpenAI-compatible memory embeddings require a base_url.")
        if not normalized_model_name:
            raise ValueError("OpenAI-compatible memory embeddings require a model_name.")
        if not normalized_binding:
            raise ValueError(
                "OpenAI-compatible memory embeddings require a credential_binding.",
            )
        self._base_url = normalized_base_url
        self._model_name = normalized_model_name
        self._credential_binding = normalized_binding
        self._timeout_seconds = max(timeout_seconds, 1)

    @property
    def provider_name(self) -> str:
        return "openai_compatible"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def provider_key(self) -> str:
        return self._base_url.rstrip("/")

    def embed_texts(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        normalized_texts = [str(text) for text in texts]
        if not normalized_texts:
            return ()
        token = resolve_credential_binding(
            self._credential_binding,
            required=True,
            description="memory vector provider",
        )
        response = requests.post(
            join_url(self._base_url, "/embeddings"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._model_name,
                "input": normalized_texts,
            },
            timeout=self._timeout_seconds,
        )
        payload = ensure_json_response(
            response,
            description="memory vector provider",
        )
        raw_data = payload.get("data")
        if not isinstance(raw_data, list):
            raise RuntimeError("memory vector provider returned invalid embedding data.")
        embeddings: list[tuple[float, ...]] = []
        for item in raw_data:
            if not isinstance(item, dict):
                raise RuntimeError("memory vector provider returned invalid embedding item.")
            raw_embedding = item.get("embedding")
            if not isinstance(raw_embedding, list) or not raw_embedding:
                raise RuntimeError("memory vector provider returned an empty embedding.")
            embeddings.append(tuple(float(value) for value in raw_embedding))
        if len(embeddings) != len(normalized_texts):
            raise RuntimeError("memory vector provider returned a mismatched embedding count.")
        return tuple(embeddings)


def encode_embedding(embedding: Sequence[float]) -> str:
    return json.dumps([float(value) for value in embedding], separators=(",", ":"))


def decode_embedding(payload: str) -> tuple[float, ...]:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError("invalid memory embedding payload.") from exc
    if not isinstance(data, list):
        raise RuntimeError("invalid memory embedding payload.")
    return tuple(float(value) for value in data)


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(float(a) * float(b) for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(float(value) * float(value) for value in left))
    right_norm = math.sqrt(sum(float(value) * float(value) for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _tokenize(value: str) -> tuple[str, ...]:
    return tuple(token for token in re.findall(r"[0-9a-z_]+", value) if token)


def _stable_bucket(seed: str, dimensions: int) -> int:
    import hashlib

    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False) % dimensions


def _normalize_vector(values: list[float]) -> tuple[float, ...]:
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0.0:
        return tuple(values)
    return tuple(value / norm for value in values)
