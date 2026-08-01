import pytest

from agent_runtime.agents.companion.agent import CompanionAgent
from agent_runtime.agents.safety_evaluator.evaluator import SafetyEvaluator
from agent_runtime.contracts.models import AgentRunRequest, ContextManifest
from agent_runtime.models.mock_provider import MockModelProvider
from agent_runtime.models.provider import ModelProvider


class CustomProvider(ModelProvider):
    async def generate_reply(
        self, request: AgentRunRequest, context_manifest: ContextManifest, language: str
    ) -> str:
        return "custom-reply"


def make_request():
    return AgentRunRequest(
        schema_version="1.0.0",
        request_id="req-provider-001",
        trace_id="trace-provider-001",
        session_id="sess-provider-001",
        actor_id="actor-elder-001",
        actor_role="elder",
        elder_id="elder-001",
        tenant_id="tenant-001",
        purpose="conversation",
        consent_version="cv-2026.07.30",
        policy_version="pv-2026.07.30",
        language="zh-TW",
        input_text="測試 provider 注入",
        allowed_tools=[],
        max_steps=3,
        latency_budget_ms=3000,
    )


@pytest.mark.asyncio
async def test_provider_interface_is_replaceable():
    provider = CustomProvider()
    companion = CompanionAgent(provider=provider)
    req = make_request()
    manifest = ContextManifest(
        agent_id="companion-agent",
        elder_id=req.elder_id,
        tenant_id=req.tenant_id,
        purpose=req.purpose,
        consent_version=req.consent_version,
        policy_version=req.policy_version,
        items=[],
        excluded_items=[],
        total_token_estimate=0,
    )
    output = await companion.run(req, manifest, req.language)
    assert output.reply_text == "custom-reply"


def test_safety_evaluator_allows_general_conversation():
    req = make_request()
    evaluator = SafetyEvaluator()
    result = evaluator.evaluate(req, "一般回覆")
    assert result.decision.value == "ALLOW"
    assert result.risk_level.value == "LOW"


def test_safety_evaluator_blocks_high_risk_medical_request():
    req = make_request()
    req.input_text = "請告訴我怎麼停藥"
    evaluator = SafetyEvaluator()
    result = evaluator.evaluate(req, "一般回覆")
    assert result.decision.value in {"BLOCK", "SAFE_FALLBACK"}
    assert result.risk_level.value == "HIGH"


@pytest.mark.asyncio
async def test_mock_provider_no_aws_credentials_required():
    provider = MockModelProvider()
    req = make_request()
    manifest = ContextManifest(
        agent_id="companion-agent",
        elder_id=req.elder_id,
        tenant_id=req.tenant_id,
        purpose=req.purpose,
        consent_version=req.consent_version,
        policy_version=req.policy_version,
        items=[],
        excluded_items=[],
        total_token_estimate=0,
    )
    output = await provider.generate_reply(req, manifest, req.language)
    assert "謝謝您" in output
