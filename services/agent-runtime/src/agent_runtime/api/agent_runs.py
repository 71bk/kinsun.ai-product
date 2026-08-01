from fastapi import APIRouter, Request

from agent_runtime.contracts.models import AgentRunRequest, AgentRunResponse
from agent_runtime.core.envelopes import ResponseMeta, SuccessEnvelope
from agent_runtime.middleware.correlation import get_correlation_id
from agent_runtime.tracing.trace import new_trace_id

router = APIRouter()


@router.post("/api/v1/agent/runs", response_model=SuccessEnvelope[AgentRunResponse])
async def run_agent(
    request: Request, payload: AgentRunRequest
) -> SuccessEnvelope[AgentRunResponse]:
    """Run one agent turn.

    Step-limit validation lives in the orchestrator, not here. This endpoint
    used to repeat those checks, which meant the orchestrator's own
    StepLimitError could never fire and its limit was never actually exercised.
    """
    orchestrator = request.app.state.orchestrator

    if payload.trace_id is None:
        payload.trace_id = new_trace_id()

    response = await orchestrator.run(payload)

    return SuccessEnvelope(
        data=response,
        meta=ResponseMeta(correlation_id=get_correlation_id()),
    )
