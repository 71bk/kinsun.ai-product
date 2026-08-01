from agent_runtime.agents.companion.models import CompanionOutput
from agent_runtime.contracts.models import AgentRunRequest, ContextManifest
from agent_runtime.models.provider import ModelProvider


class CompanionAgent:
    """Generate user-facing replies from a provider."""

    def __init__(self, provider: ModelProvider) -> None:
        self.provider = provider

    async def run(
        self,
        request: AgentRunRequest,
        context_manifest: ContextManifest,
        language: str,
    ) -> CompanionOutput:
        reply_text = await self.provider.generate_reply(
            request=request,
            context_manifest=context_manifest,
            language=language,
        )
        return CompanionOutput(reply_text=reply_text)
