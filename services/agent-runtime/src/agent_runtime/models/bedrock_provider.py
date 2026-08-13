"""Bedrock text generation bound to the approved context manifest.

Uses the Converse API so the model identifier stays a pure configuration
choice: selecting a model is an owner decision recorded in an ADR, not
something this adapter should encode.

The reply is still only a candidate. It passes through the deterministic
Safety Evaluator, and citations are appended separately by the orchestrator.
"""

from __future__ import annotations

import asyncio
from typing import Any, Protocol, cast

from agent_runtime.common.errors import ModelDependencyError
from agent_runtime.contracts.models import AgentRunRequest, ContextManifest
from agent_runtime.models.prompting import build_model_prompts
from agent_runtime.models.provider import ModelProvider


class BedrockConverseClient(Protocol):
    def converse(self, **kwargs: Any) -> dict[str, Any]: ...


class BedrockModelProvider(ModelProvider):
    def __init__(
        self,
        client: BedrockConverseClient,
        *,
        model_id: str,
        max_tokens: int,
        temperature: float,
    ) -> None:
        if not model_id.strip():
            raise ValueError("model_id is required")
        if max_tokens < 1:
            raise ValueError("max_tokens must be positive")
        if not 0.0 <= temperature <= 1.0:
            raise ValueError("temperature must be between zero and one")
        self._client = client
        self.model_id = model_id
        self.max_tokens = max_tokens
        self.temperature = temperature

    async def generate_reply(
        self,
        request: AgentRunRequest,
        context_manifest: ContextManifest,
        language: str,
    ) -> str:
        system_prompt, user_prompt = build_model_prompts(request, context_manifest, language)

        try:
            response = await asyncio.to_thread(
                self._client.converse,
                modelId=self.model_id,
                system=[{"text": system_prompt}],
                messages=[{"role": "user", "content": [{"text": user_prompt}]}],
                inferenceConfig={
                    "maxTokens": self.max_tokens,
                    "temperature": self.temperature,
                },
            )
        except Exception as exc:
            # Provider messages can quote the request, which carries the elder's
            # words. Only the exception class is safe to surface.
            raise ModelDependencyError(f"Bedrock reply failed: {type(exc).__name__}") from exc

        return _extract_text(response)


def _extract_text(response: Any) -> str:
    """Read the Converse reply, refusing anything that is not usable text."""

    if not isinstance(response, dict):
        raise ModelDependencyError("Bedrock response must be an object")
    output = response.get("output")
    message = output.get("message") if isinstance(output, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list) or not content:
        raise ModelDependencyError("Bedrock response has no content")
    parts = [
        block["text"]
        for block in content
        if isinstance(block, dict) and isinstance(block.get("text"), str)
    ]
    reply = "\n".join(part.strip() for part in parts if part.strip()).strip()
    if not reply:
        raise ModelDependencyError("Bedrock returned an empty reply")
    return reply


def build_bedrock_model_provider(
    *,
    region: str,
    model_id: str,
    max_tokens: int,
    temperature: float,
    session: Any | None = None,
) -> BedrockModelProvider:
    if not region.strip():
        raise ValueError("AWS region is required")
    if session is None:
        import boto3

        session = boto3.Session()
    client = session.client("bedrock-runtime", region_name=region)
    return BedrockModelProvider(
        cast(BedrockConverseClient, client),
        model_id=model_id,
        max_tokens=max_tokens,
        temperature=temperature,
    )
