"""Factory for provider-neutral document embedding adapters."""

from __future__ import annotations

from rag_ingestion.bedrock_embedder import BedrockEmbedder
from rag_ingestion.embedding_types import DocumentEmbeddingProvider
from rag_ingestion.google_embedder import GoogleDocumentEmbedder
from rag_ingestion.settings import IngestionSettings


def build_document_embedding_provider(
    settings: IngestionSettings,
) -> DocumentEmbeddingProvider:
    """Build exactly the configured provider; never fall back to another adapter."""

    profile = settings.require_embedding_profile()
    if profile.provider == "bedrock":
        region, model_id, dimension = settings.require_bedrock()
        return BedrockEmbedder.from_boto3(
            region=region,
            model_id=model_id,
            dimension=dimension,
            batch_size=profile.batch_size,
            truncate=profile.truncate,
        )
    return GoogleDocumentEmbedder(
        api_key=settings.require_google_api_key(),
        model_id=profile.model_id,
        dimension=profile.dimension,
        document_input_type=profile.document_input_type,
        batch_size=profile.batch_size,
        timeout_seconds=settings.gemini_embedding_timeout_seconds,
    )
