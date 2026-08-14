"""Native Google Gen AI adapter for Gemini Developer and Vertex AI Express keys."""

from __future__ import annotations

from typing import Any

from google import genai
from google.genai import types

from agent_runtime.common.errors import ModelDependencyError
from agent_runtime.contracts.models import AgentRunRequest, ContextManifest
from agent_runtime.models.prompting import build_model_prompts
from agent_runtime.models.provider import ModelProvider

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
                "max_output_tokens": self.max_tokens,
            }
            if self.model_id == "gemini-3.6-flash":
                generation_config["thinking_config"] = types.ThinkingConfig(
                    include_thoughts=False,
                    thinking_level=types.ThinkingLevel.MINIMAL,
                )
            else:
                generation_config["temperature"] = self.temperature
            response = await self._async_client.models.generate_content(
                model=self.model_id,
                contents=user_prompt,
                config=types.GenerateContentConfig(**generation_config),
            )
        except Exception as exc:
            # Google errors can contain project metadata or echo request content.
            # Only the exception class crosses the provider boundary.
            raise ModelDependencyError(f"Gemini reply failed: {type(exc).__name__}") from exc
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
