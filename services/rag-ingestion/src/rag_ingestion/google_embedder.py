"""Google Gen AI document embedding adapter with fail-closed validation."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from google import genai
from google.genai import types

from rag_ingestion.embedding_types import (
    EmbeddingBatchError,
    EmbeddingError,
    EmbeddingResult,
)
from rag_ingestion.settings import GOOGLE_DOCUMENT_INPUT_TYPE, REQUIRED_EMBEDDING_DIMENSION

_VERTEX_EXPRESS_KEY_PREFIX = "AQ."


def uses_vertex_express(api_key: str) -> bool:
    """Classify the API surface without returning or logging the credential."""

    return api_key.strip().startswith(_VERTEX_EXPRESS_KEY_PREFIX)


class GoogleDocumentEmbedder:
    """Synchronous Google adapter for a complete staging corpus rebuild."""

    def __init__(
        self,
        *,
        api_key: str,
        model_id: str,
        dimension: int,
        document_input_type: str,
        batch_size: int = 96,
        timeout_seconds: float = 30.0,
        client: Any | None = None,
    ) -> None:
        api_key = api_key.strip()
        if not api_key:
            raise ValueError("Google embedding api_key is required")
        if not model_id.strip():
            raise ValueError("model_id is required")
        if dimension != REQUIRED_EMBEDDING_DIMENSION:
            raise ValueError(f"embedding dimension must be {REQUIRED_EMBEDDING_DIMENSION}")
        if document_input_type != GOOGLE_DOCUMENT_INPUT_TYPE:
            raise ValueError(f"Google document input type must be {GOOGLE_DOCUMENT_INPUT_TYPE}")
        if not 1 <= batch_size <= 96:
            raise ValueError("batch_size must be between 1 and 96")
        if not 0.0 < timeout_seconds <= 120.0:
            raise ValueError("timeout_seconds must be between zero and 120")

        self.model_id = model_id.strip()
        self.dimension = dimension
        self.document_input_type = document_input_type
        self.batch_size = batch_size
        self._vertex_express = uses_vertex_express(api_key)
        self._owns_client = client is None
        self._client = client or genai.Client(
            api_key=api_key,
            vertexai=self._vertex_express,
            http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000)),
        )
        self._models = self._client.models

    def embed_documents(self, texts: Sequence[str]) -> EmbeddingResult:
        if not texts:
            raise EmbeddingError("at least one document is required")
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise EmbeddingError("all embedding inputs must be non-empty strings")

        vectors: list[tuple[float, ...]] = []
        total = len(texts)
        request_batch_size = 1 if self._vertex_express else self.batch_size
        for offset in range(0, total, request_batch_size):
            batch = list(texts[offset : offset + request_batch_size])
            try:
                response = self._models.embed_content(
                    model=self.model_id,
                    contents=batch,
                    config=types.EmbedContentConfig(
                        task_type=self.document_input_type,
                        output_dimensionality=self.dimension,
                    ),
                )
                parsed_vectors = _parse_google_vectors(response, self.dimension)
                if len(parsed_vectors) != len(batch):
                    raise EmbeddingError("Google response vector count does not match request")
                vectors.extend(parsed_vectors)
            except Exception as exc:
                if isinstance(exc, EmbeddingBatchError):
                    raise
                # Google failures may echo request text, endpoint metadata, or credentials.
                raise EmbeddingBatchError(
                    f"Google embedding batch failed: {type(exc).__name__}",
                    success_count=len(vectors),
                    failure_count=total - len(vectors),
                ) from exc
        return EmbeddingResult(
            vectors=tuple(vectors),
            success_count=len(vectors),
            failure_count=0,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


def _parse_google_vectors(response: object, dimension: int) -> tuple[tuple[float, ...], ...]:
    embeddings = (
        response.get("embeddings")
        if isinstance(response, Mapping)
        else getattr(response, "embeddings", None)
    )
    if not isinstance(embeddings, list) or not embeddings:
        raise EmbeddingError("Google response is missing embeddings")
    return tuple(_parse_google_vector(embedding, dimension) for embedding in embeddings)


def _parse_google_vector(embedding: object, dimension: int) -> tuple[float, ...]:
    values = (
        embedding.get("values")
        if isinstance(embedding, Mapping)
        else getattr(embedding, "values", None)
    )
    if not isinstance(values, list) or len(values) != dimension:
        raise EmbeddingError(f"embedding vector must contain exactly {dimension} values")
    vector: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise EmbeddingError("embedding vector values must be numeric")
        converted = float(value)
        if not math.isfinite(converted):
            raise EmbeddingError("embedding vector values must be finite")
        vector.append(converted)
    return tuple(vector)
