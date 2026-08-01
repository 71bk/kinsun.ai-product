from agent_runtime.agents.companion.agent import CompanionAgent
from agent_runtime.agents.safety_evaluator.evaluator import SafetyEvaluator
from agent_runtime.common.errors import StepLimitError
from agent_runtime.context.builder import build_minimal_context_manifest
from agent_runtime.contracts.models import AgentRunRequest, AgentRunResponse
from agent_runtime.models.provider import ModelProvider
from agent_runtime.orchestration.fallback import fallback_reply
from agent_runtime.orchestration.loop_controller import LoopController
from agent_runtime.orchestration.stop_conditions import map_to_status
from agent_runtime.tracing.trace import new_agent_run_id, new_trace_id


class AgentOrchestrator:
    """Minimal orchestrator for the M0 flow."""

    def __init__(self, provider: ModelProvider, *, max_steps: int) -> None:
        self.provider = provider
        self.max_steps = max_steps
        self.companion = CompanionAgent(provider)
        self.safety_evaluator = SafetyEvaluator()

    def select_agent(self, _request: AgentRunRequest) -> str:
        return "companion-agent"

    async def run(self, request: AgentRunRequest) -> AgentRunResponse:
        if request.max_steps > self.max_steps:
            raise StepLimitError("max_steps exceeds system limit")

        trace_id = request.trace_id or new_trace_id()
        selected_agent = self.select_agent(request)
        context_manifest = build_minimal_context_manifest(request, selected_agent)

        # M0 runs exactly one decision step. There is no Tool round and no
        # rewrite path yet, so a second iteration would repeat an identical
        # deterministic pass and could never change the outcome. The multi-step
        # loop that consumes MAX_TOOL_ROUNDS and MAX_REWRITE arrives with the
        # Tool execution engine.
        #
        # This replaced a `while True` whose body ended in an unconditional
        # break: the loop always ran once, so its StepLimitError could never
        # fire and the step budget was decorative.
        step_count = 1
        if not LoopController(self.max_steps).can_execute(request.max_steps, step_count):
            raise StepLimitError("max_steps does not allow a single decision step")

        companion_output = (
            await self.companion.run(request, context_manifest, request.language)
        ).reply_text
        safety_result = self.safety_evaluator.evaluate(request, companion_output)

        return AgentRunResponse(
            request_id=request.request_id,
            trace_id=trace_id,
            agent_run_id=new_agent_run_id(),
            selected_agent=selected_agent,
            reply_text=fallback_reply(safety_result, companion_output),
            reply_language=request.language,
            safety_result=safety_result,
            context_manifest_id=context_manifest.context_manifest_id,
            step_count=step_count,
            result_status=map_to_status(safety_result),
            reason_codes=safety_result.reason_codes,
        )
