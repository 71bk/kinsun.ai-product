from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Mapping
from typing import Any, Protocol, cast

import boto3
from google import genai
from google.genai import types

from agent_runtime.rag.models import QueryEmbeddingSettings


class QueryEmbeddingError(RuntimeError):
    """The query embedding could not be produced or validated."""


class BedrockRuntimeClient(Protocol):
    def invoke_model(self, **kwargs: object) -> Mapping[str, object]: ...


_VERTEX_EXPRESS_KEY_PREFIX = "AQ."


class EmbeddingProvider(Protocol):
    @property
    def dimension(self) -> int: ...

    async def embed_query(self, text: str) -> list[float]: ...

    async def aclose(self) -> None: ...


class BedrockQueryEmbedder:
    """Cohere Embed v4 query adapter with an injected boto3-compatible client."""

    def __init__(
        self,
        client: BedrockRuntimeClient,
        settings: QueryEmbeddingSettings,
    ) -> None:
        self._client = client
        self._settings = settings

    @property
    def dimension(self) -> int:
        return self._settings.dimension

    async def embed_query(self, text: str) -> list[float]:
        if not text.strip():
            raise QueryEmbeddingError("query text cannot be blank")
        request_body = {
            "texts": [text],
            "input_type": "search_query",
            "embedding_types": ["float"],
            "output_dimension": self._settings.dimension,
        }
        response = await asyncio.to_thread(
            self._client.invoke_model,
            modelId=self._settings.model_id,
            body=json.dumps(request_body).encode("utf-8"),
            contentType="application/json",
            accept="application/json",
        )
        if inspect.isawaitable(response):
            response = await response
        payload = _decode_response(response)
        vector = _extract_first_float_embedding(payload)
        if len(vector) != self._settings.dimension:
            raise QueryEmbeddingError(
                f"expected {self._settings.dimension} dimensions, got {len(vector)}"
            )
        return vector

    async def aclose(self) -> None:
        return None


class GoogleQueryEmbedder:
    """Google Gen AI query embedding adapter with no credential leakage."""

    def __init__(
        self,
        *,
        api_key: str,
        settings: QueryEmbeddingSettings,
        timeout_seconds: float,
        client: Any | None = None,
    ) -> None:
        api_key = api_key.strip()
        if not api_key:
            raise ValueError("Google embedding api_key is required")
        if settings.provider != "google":
            raise ValueError("GoogleQueryEmbedder requires provider=google")
        if not 0.0 < timeout_seconds <= 120.0:
            raise ValueError("timeout_seconds must be between zero and 120")

        self._settings = settings
        self._owns_client = client is None
        self._client = client or genai.Client(
            api_key=api_key,
            vertexai=api_key.startswith(_VERTEX_EXPRESS_KEY_PREFIX),
            http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000)),
        )
        self._async_models = self._client.aio.models

    @property
    def dimension(self) -> int:
        return self._settings.dimension

    async def embed_query(self, text: str) -> list[float]:
        if not text.strip():
            raise QueryEmbeddingError("query text cannot be blank")
        try:
            response = await self._async_models.embed_content(
                model=self._settings.model_id,
                contents=text,
                config=types.EmbedContentConfig(
                    task_type="RETRIEVAL_QUERY",
                    output_dimensionality=self._settings.dimension,
                ),
            )
        except Exception as exc:
            # Google exceptions may contain project metadata or echo input text.
            raise QueryEmbeddingError(f"Google embedding failed: {type(exc).__name__}") from exc
        vector = _extract_google_embedding(response)
        if len(vector) != self._settings.dimension:
            raise QueryEmbeddingError(
                f"expected {self._settings.dimension} dimensions, got {len(vector)}"
            )
        return vector

    async def aclose(self) -> None:
        if not self._owns_client:
            return
        await self._client.aio.aclose()
        self._client.close()


def build_bedrock_client(settings: QueryEmbeddingSettings) -> BedrockRuntimeClient:
    """Create a real Bedrock Runtime client via the standard AWS credential chain."""

    if settings.provider != "bedrock" or settings.region is None:
        raise ValueError("Bedrock client requires provider=bedrock and an AWS region")
    session = boto3.Session(region_name=settings.region)
    return cast(
        BedrockRuntimeClient,
        session.client("bedrock-runtime", region_name=settings.region),
    )


def build_bedrock_query_embedder(settings: QueryEmbeddingSettings) -> BedrockQueryEmbedder:
    if settings.provider != "bedrock":
        raise ValueError("BedrockQueryEmbedder requires provider=bedrock")
    return BedrockQueryEmbedder(build_bedrock_client(settings), settings)


def build_embedding_provider(
    settings: QueryEmbeddingSettings,
    *,
    google_api_key: str | None = None,
    google_timeout_seconds: float = 30.0,
) -> EmbeddingProvider:
    if settings.provider == "bedrock":
        return build_bedrock_query_embedder(settings)
    if not google_api_key:
        raise ValueError("Google embedding requires GEMINI_API_KEY")
    return GoogleQueryEmbedder(
        api_key=google_api_key,
        settings=settings,
        timeout_seconds=google_timeout_seconds,
    )


def _decode_response(response: Mapping[str, object]) -> Mapping[str, object]:
    body = response.get("body")
    if hasattr(body, "read"):
        body = body.read()
    if isinstance(body, bytes):
        body = body.decode("utf-8")
    if isinstance(body, str):
        try:
            decoded = json.loads(body)
        except json.JSONDecodeError as exc:
            raise QueryEmbeddingError("Bedrock returned invalid JSON") from exc
        if not isinstance(decoded, Mapping):
            raise QueryEmbeddingError("Bedrock response must be a JSON object")
        return cast(Mapping[str, object], decoded)
    if isinstance(body, Mapping):
        return body
    if "embeddings" in response:
        return response
    raise QueryEmbeddingError("Bedrock response body is missing")


def _extract_first_float_embedding(payload: Mapping[str, object]) -> list[float]:
    embeddings = payload.get("embeddings")
    if isinstance(embeddings, Mapping):
        embeddings = embeddings.get("float")
    if not isinstance(embeddings, list) or not embeddings:
        raise QueryEmbeddingError("Bedrock response has no float embeddings")

    first = embeddings[0]
    if not isinstance(first, list) or not first:
        raise QueryEmbeddingError("Bedrock response embedding is malformed")
    if any(isinstance(value, bool) or not isinstance(value, int | float) for value in first):
        raise QueryEmbeddingError("Bedrock response embedding contains non-numeric values")
    return [float(value) for value in first]


def _extract_google_embedding(response: object) -> list[float]:
    embeddings = (
        response.get("embeddings")
        if isinstance(response, Mapping)
        else getattr(response, "embeddings", None)
    )
    if not isinstance(embeddings, list) or len(embeddings) != 1:
        raise QueryEmbeddingError("Google response must contain exactly one embedding")
    embedding = embeddings[0]
    values = (
        embedding.get("values")
        if isinstance(embedding, Mapping)
        else getattr(embedding, "values", None)
    )
    if not isinstance(values, list) or not values:
        raise QueryEmbeddingError("Google response embedding is malformed")
    if any(isinstance(value, bool) or not isinstance(value, int | float) for value in values):
        raise QueryEmbeddingError("Google response embedding contains non-numeric values")
    return [float(value) for value in values]
