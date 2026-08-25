from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from rag_ingestion.embedding_types import EmbeddingBatchError, EmbeddingError
from rag_ingestion.google_embedder import GoogleDocumentEmbedder, uses_vertex_express

DIMENSION = 1024


def test_vertex_express_classification_does_not_require_client_initialization() -> None:
    assert uses_vertex_express("AQ.synthetic-express-key") is True
    assert uses_vertex_express("synthetic-developer-key") is False


class FakeModels:
    def __init__(
        self,
        *,
        dimension: int = DIMENSION,
        error_at_request: int | None = None,
    ) -> None:
        self.dimension = dimension
        self.error_at_request = error_at_request
        self.requests: list[dict[str, Any]] = []

    def embed_content(self, **kwargs: Any) -> object:
        self.requests.append(kwargs)
        if self.error_at_request == len(self.requests):
            raise RuntimeError("sensitive provider detail and document text")
        contents = kwargs["contents"]
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=[0.25] * self.dimension) for _ in contents]
        )


class FakeClient:
    def __init__(self, models: FakeModels) -> None:
        self.models = models
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


def make_embedder(
    models: FakeModels,
    *,
    api_key: str = "synthetic-developer-key",
    batch_size: int = 2,
) -> GoogleDocumentEmbedder:
    return GoogleDocumentEmbedder(
        api_key=api_key,
        model_id="gemini-embedding-001",
        dimension=DIMENSION,
        document_input_type="RETRIEVAL_DOCUMENT",
        batch_size=batch_size,
        timeout_seconds=30.0,
        client=FakeClient(models),
    )


def test_google_document_embedder_batches_with_fixed_task_type_and_dimension() -> None:
    models = FakeModels()
    embedder = make_embedder(models, batch_size=2)

    result = embedder.embed_documents(["document one", "document two", "document three"])

    assert result.success_count == 3
    assert result.failure_count == 0
    assert len(result.vectors) == 3
    assert [request["contents"] for request in models.requests] == [
        ["document one", "document two"],
        ["document three"],
    ]
    for request in models.requests:
        assert request["model"] == "gemini-embedding-001"
        assert request["config"].task_type == "RETRIEVAL_DOCUMENT"
        assert request["config"].output_dimensionality == DIMENSION


def test_vertex_express_key_uses_single_document_requests() -> None:
    models = FakeModels()
    embedder = make_embedder(models, api_key="AQ.synthetic-express-key", batch_size=96)

    result = embedder.embed_documents(["document one", "document two"])

    assert result.success_count == 2
    assert [request["contents"] for request in models.requests] == [
        ["document one"],
        ["document two"],
    ]


def test_google_provider_failure_is_scrubbed_and_reports_remaining_count() -> None:
    models = FakeModels(error_at_request=2)
    embedder = make_embedder(models, api_key="AQ.synthetic-express-key")

    with pytest.raises(EmbeddingBatchError) as raised:
        embedder.embed_documents(["private first", "private second", "private third"])

    assert raised.value.success_count == 1
    assert raised.value.failure_count == 2
    assert "sensitive provider detail" not in str(raised.value)
    assert "private second" not in str(raised.value)
    assert "AQ.synthetic-express-key" not in str(raised.value)


def test_google_dimension_mismatch_fails_closed() -> None:
    embedder = make_embedder(FakeModels(dimension=DIMENSION - 1))

    with pytest.raises(EmbeddingBatchError) as raised:
        embedder.embed_documents(["synthetic document"])

    assert isinstance(raised.value.__cause__, EmbeddingError)
    assert raised.value.success_count == 0
    assert raised.value.failure_count == 1


@pytest.mark.parametrize("text", ["", "   "])
def test_google_blank_document_is_rejected_before_provider_call(text: str) -> None:
    models = FakeModels()
    embedder = make_embedder(models)

    with pytest.raises(EmbeddingError, match="non-empty"):
        embedder.embed_documents([text])

    assert models.requests == []


def test_injected_google_client_is_not_closed_by_adapter() -> None:
    client = FakeClient(FakeModels())
    embedder = GoogleDocumentEmbedder(
        api_key="synthetic-developer-key",
        model_id="gemini-embedding-001",
        dimension=DIMENSION,
        document_input_type="RETRIEVAL_DOCUMENT",
        client=client,
    )

    embedder.close()

    assert client.close_calls == 0
