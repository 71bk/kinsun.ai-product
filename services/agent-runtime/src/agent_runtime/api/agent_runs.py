from fastapi import APIRouter, Request

from agent_runtime.contracts.models import AgentRunRequest, AgentRunResponse
from agent_runtime.core.envelopes import ResponseMeta, SuccessEnvelope
from agent_runtime.middleware.correlation import get_correlation_id
from agent_runtime.security.service_identity import SERVICE_CREDENTIAL_HEADER
from agent_runtime.tracing.trace import new_trace_id

router = APIRouter()


@router.post("/api/v1/agent/runs", response_model=SuccessEnvelope[AgentRunResponse])
async def run_agent(
    request: Request, payload: AgentRunRequest
) -> SuccessEnvelope[AgentRunResponse]:
    """Run one bounded turn and return only replies or typed proposals."""
    raw_body = await request.body()
    request.app.state.service_identity_verifier.verify(
        request.headers.get(SERVICE_CREDENTIAL_HEADER),
        method=request.method,
        path=request.url.path,
        body=raw_body,
        correlation_id=get_correlation_id(),
    )
    orchestrator = request.app.state.orchestrator

    if payload.trace_id is None:
        payload.trace_id = new_trace_id()

    response = await orchestrator.run(
        payload,
        rag_retriever=getattr(request.app.state, "rag_retriever", None),
    )
    return _envelope(response)


def _envelope(response: AgentRunResponse) -> SuccessEnvelope[AgentRunResponse]:
    return SuccessEnvelope(
        data=response,
        meta=ResponseMeta(correlation_id=get_correlation_id()),
    )
