from __future__ import annotations

from abc import ABC, abstractmethod

from agent_runtime.contracts.models import AgentRunRequest, ContextManifest


class ModelProvider(ABC):
    """Provider abstraction for text generation adapters."""

    @abstractmethod
    async def generate_reply(
        self, request: AgentRunRequest, context_manifest: ContextManifest, language: str
    ) -> str: ...
