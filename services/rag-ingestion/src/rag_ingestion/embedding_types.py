"""Provider-neutral document embedding contracts."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


class EmbeddingError(RuntimeError):
    """Raised when embeddings cannot be safely generated or loaded."""


class EmbeddingBatchError(EmbeddingError):
    def __init__(self, message: str, *, success_count: int, failure_count: int) -> None:
        self.success_count = success_count
        self.failure_count = failure_count
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    vectors: tuple[tuple[float, ...], ...]
    success_count: int
    failure_count: int


class DocumentEmbeddingProvider(Protocol):
    """Minimal provider boundary used by the guarded artifact writer."""

    model_id: str
    dimension: int

    def embed_documents(self, texts: Sequence[str]) -> EmbeddingResult: ...
