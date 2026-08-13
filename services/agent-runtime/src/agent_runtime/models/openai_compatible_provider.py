"""Provider-neutral adapter for OpenAI-compatible Chat Completions endpoints."""

from __future__ import annotations

from typing import Any

import httpx

from agent_runtime.common.errors import ModelDependencyError
from agent_runtime.contracts.models import AgentRunRequest, ContextManifest
from agent_runtime.models.prompting import build_model_prompts
from agent_runtime.models.provider import ModelProvider

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


class OpenAICompatibleModelProvider(ModelProvider):
    """Call a configured Chat Completions endpoint without provider SDK coupling."""

    def __init__(
        self,
        *,
        base_url: str,
        model_id: str,
        api_key: str | None,
        max_tokens: int,
        temperature: float,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        endpoint = _chat_completions_endpoint(base_url)
        model_id = model_id.strip()
        api_key = api_key.strip() if api_key else None
        if not model_id:
            raise ValueError("model_id is required")
        if max_tokens < 1:
            raise ValueError("max_tokens must be positive")
        if not 0.0 <= temperature <= 1.0:
            raise ValueError("temperature must be between zero and one")
        if not 0.0 < timeout_seconds <= 120.0:
            raise ValueError("timeout_seconds must be between zero and 120")
        if endpoint.scheme == "http" and api_key and endpoint.host not in _LOOPBACK_HOSTS:
            raise ValueError("API keys require HTTPS except for loopback endpoints")

        self.endpoint = endpoint
        self.model_id = model_id
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._owns_client = client is None
        headers = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = client or httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            trust_env=False,
        )
        self._request_headers = headers if client is not None else None

    async def generate_reply(
        self,
        request: AgentRunRequest,
        context_manifest: ContextManifest,
        language: str,
    ) -> str:
        system_prompt, user_prompt = build_model_prompts(request, context_manifest, language)
        payload = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": False,
        }
        try:
            response = await self._client.post(
                self.endpoint,
                headers=self._request_headers,
                json=payload,
            )
        except Exception as exc:
            # Transport errors can include URLs, headers, or request content.
            raise ModelDependencyError(
                f"OpenAI-compatible reply failed: {type(exc).__name__}"
            ) from exc

        if not 200 <= response.status_code < 300:
            # Status is operationally useful; upstream bodies and URLs are Restricted Data risks.
            raise ModelDependencyError(
                f"OpenAI-compatible reply failed with HTTP {response.status_code}"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise ModelDependencyError("OpenAI-compatible response is not JSON") from exc
        return _extract_reply_text(body)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


def _chat_completions_endpoint(base_url: str) -> httpx.URL:
    value = base_url.strip()
    if not value:
        raise ValueError("base_url is required")
    url = httpx.URL(value)
    if url.scheme not in {"http", "https"} or not url.host:
        raise ValueError("base_url must be an absolute HTTP(S) URL")
    if url.username or url.password:
        raise ValueError("base_url must not contain credentials")
    if url.query or url.fragment:
        raise ValueError("base_url must not contain a query or fragment")
    return httpx.URL(f"{str(url).rstrip('/')}/chat/completions")


def _extract_reply_text(body: Any) -> str:
    if not isinstance(body, dict):
        raise ModelDependencyError("OpenAI-compatible response must be an object")
    choices = body.get("choices")
    first = choices[0] if isinstance(choices, list) and choices else None
    message = first.get("message") if isinstance(first, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise ModelDependencyError("OpenAI-compatible response has no text content")
    reply = content.strip()
    if len(reply) > 4000:
        raise ModelDependencyError("OpenAI-compatible response exceeds the reply limit")
    return reply
