"""Native Google Gen AI adapter for Gemini Developer and Vertex AI Express keys."""

from __future__ import annotations

from typing import Any

from google import genai
from google.genai import types

from agent_runtime.common.errors import ModelDependencyError
from agent_runtime.contracts.models import AgentRunRequest, ContextManifest
from agent_runtime.models.generation_diagnostics import (
    record_generation_diagnostics,
    record_generation_failure,
)
from agent_runtime.models.prompting import build_model_prompts, grounded_generation_token_limit
from agent_runtime.models.provider import ModelProvider
from agent_runtime.rag.grounded_answer import GROUNDED_SOURCE_TYPE

_VERTEX_EXPRESS_KEY_PREFIX = "AQ."


class GeminiModelProvider(ModelProvider):
    """Generate one bounded text reply through the native Google Gen AI SDK."""

    def __init__(
        self,
        *,
        api_key: str,
        model_id: str,
        max_tokens: int,
        temperature: float,
        timeout_seconds: float,
        client: Any | None = None,
    ) -> None:
        api_key = api_key.strip()
        model_id = model_id.strip()
        if not api_key:
            raise ValueError("api_key is required")
        if not model_id:
            raise ValueError("model_id is required")
        if max_tokens < 1:
            raise ValueError("max_tokens must be positive")
        if not 0.0 <= temperature <= 1.0:
            raise ValueError("temperature must be between zero and one")
        if not 0.0 < timeout_seconds <= 120.0:
            raise ValueError("timeout_seconds must be between zero and 120")

        self.model_id = model_id
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.uses_vertex_ai = api_key.startswith(_VERTEX_EXPRESS_KEY_PREFIX)
        self._owns_client = client is None
        self._client = client or genai.Client(
            api_key=api_key,
            vertexai=self.uses_vertex_ai,
            http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000)),
        )
        self._async_client = self._client.aio

    async def generate_reply(
        self,
        request: AgentRunRequest,
        context_manifest: ContextManifest,
        language: str,
    ) -> str:
        system_prompt, user_prompt = build_model_prompts(request, context_manifest, language)
        try:
            generation_config: dict[str, Any] = {
                "system_instruction": system_prompt,
                "max_output_tokens": grounded_generation_token_limit(
                    context_manifest, self.max_tokens
                ),
            }
            if any(item.source_type == GROUNDED_SOURCE_TYPE for item in context_manifest.items):
                generation_config["response_mime_type"] = "application/json"
                generation_config["response_json_schema"] = _grounded_response_json_schema()
            if self.model_id == "gemini-3.6-flash":
                generation_config["thinking_config"] = types.ThinkingConfig(
                    include_thoughts=False,
                    thinking_level=types.ThinkingLevel.MINIMAL,
                )
            elif self.model_id == "gemini-3.8-flash":
                # 3.8 rejects MINIMAL. Keep the lowest supported thinking level
                # and the model's default temperature for bounded care replies.
                generation_config["thinking_config"] = types.ThinkingConfig(
                    include_thoughts=False,
                    thinking_level=types.ThinkingLevel.LOW,
                )
            else:
                generation_config["temperature"] = self.temperature
            response = await self._async_client.models.generate_content(
                model=self.model_id,
                contents=user_prompt,
                config=types.GenerateContentConfig(**generation_config),
            )
        except Exception as exc:
            record_generation_failure(exc)
            # Google errors can contain project metadata or echo request content.
            # Only the exception class crosses the provider boundary.
            raise ModelDependencyError(f"Gemini reply failed: {type(exc).__name__}") from exc
        record_generation_diagnostics(response)
        return _extract_reply_text(response)

    async def aclose(self) -> None:
        if not self._owns_client:
            return
        await self._async_client.aclose()
        self._client.close()


def _extract_reply_text(response: Any) -> str:
    try:
        content = response.text
    except Exception as exc:
        raise ModelDependencyError("Gemini response has no text content") from exc
    if not isinstance(content, str) or not content.strip():
        raise ModelDependencyError("Gemini response has no text content")
    reply = content.strip()
    if len(reply) > 4000:
        raise ModelDependencyError("Gemini response exceeds the reply limit")
    return reply


def _grounded_response_json_schema() -> dict[str, Any]:
    """Constrain shape; the parser validates envelope and source anchors."""
    identifier = {"type": "string"}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["status", "answer_text", "citation_ids", "support_quotes", "missing_facets"],
        "properties": {
            "status": {"type": "string", "enum": ["ANSWER", "PARTIAL", "INSUFFICIENT", "CLARIFY"]},
            "answer_text": {"type": ["string", "null"]},
            "citation_ids": {
                "type": "array",
                "items": identifier,
                "maxItems": 5,
            },
            "support_quotes": {
                "type": "array",
                "maxItems": 20,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["chunk_id", "span_id"],
                    "properties": {
                        "chunk_id": identifier,
                        "span_id": {"type": "string"},
                    },
                },
            },
            "missing_facets": {
                "type": "array",
                "maxItems": 100,
                "items": {"type": "string"},
            },
        },
    }
