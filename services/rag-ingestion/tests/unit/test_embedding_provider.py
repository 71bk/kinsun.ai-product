from __future__ import annotations

from typing import Any

from rag_ingestion import embedding_provider
from rag_ingestion.settings import IngestionSettings


def isolated_settings(**values: object) -> IngestionSettings:
    return IngestionSettings(_env_file=None, **values)


def test_factory_builds_google_document_provider_without_fallback(
    monkeypatch: Any,
) -> None:
    captured: dict[str, Any] = {}
    sentinel = object()

    def fake_google(**kwargs: Any) -> object:
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(embedding_provider, "GoogleDocumentEmbedder", fake_google)
    settings = isolated_settings(
        embedding_provider="google",
        embedding_document_input_type="RETRIEVAL_DOCUMENT",
        GEMINI_API_KEY="synthetic-google-key",
        GEMINI_EMBEDDING_MODEL_ID="gemini-embedding-001",
        GEMINI_EMBEDDING_DIMENSION=1024,
        GEMINI_EMBEDDING_TIMEOUT_SECONDS=30,
    )

    provider = embedding_provider.build_document_embedding_provider(settings)

    assert provider is sentinel
    assert captured == {
        "api_key": "synthetic-google-key",
        "model_id": "gemini-embedding-001",
        "dimension": 1024,
        "document_input_type": "RETRIEVAL_DOCUMENT",
        "batch_size": 96,
        "timeout_seconds": 30.0,
    }


def test_factory_builds_bedrock_only_for_bedrock_profile(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}
    sentinel = object()

    def fake_bedrock(**kwargs: Any) -> object:
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(embedding_provider.BedrockEmbedder, "from_boto3", fake_bedrock)
    settings = isolated_settings(
        embedding_provider="bedrock",
        embedding_document_input_type="search_document",
        AWS_REGION="configured-region",
        BEDROCK_EMBEDDING_MODEL_ID="cohere.embed-v4:0",
        BEDROCK_EMBEDDING_DIMENSION=1024,
    )

    provider = embedding_provider.build_document_embedding_provider(settings)

    assert provider is sentinel
    assert captured["region"] == "configured-region"
    assert captured["model_id"] == "cohere.embed-v4:0"
    assert captured["dimension"] == 1024
