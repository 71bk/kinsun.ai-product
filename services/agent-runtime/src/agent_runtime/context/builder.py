from agent_runtime.context.manifest import build_context_manifest
from agent_runtime.contracts.models import AgentRunRequest, ContextManifest


def build_minimal_context_manifest(request: AgentRunRequest, agent_id: str) -> ContextManifest:
    return build_context_manifest(request, agent_id)
