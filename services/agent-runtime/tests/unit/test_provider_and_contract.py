import pytest

from agent_runtime.agents.companion.agent import CompanionAgent
from agent_runtime.agents.safety_evaluator.evaluator import SafetyEvaluator
from agent_runtime.contracts.models import AgentRunRequest, ContextItem, ContextManifest
from agent_runtime.models.mock_provider import MockModelProvider
from agent_runtime.models.prompting import build_model_prompts
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


def test_safety_evaluator_blocks_model_generated_cause_and_self_treatment() -> None:
    req = make_request()
    req.input_text = "我頭痛。"
    result = SafetyEvaluator().evaluate(
        req,
        "會不會是沒睡好或太累了呢？要不要先喝點溫水、坐著休息一下？",
    )
    assert result.decision.value == "BLOCK"
    assert result.reason_codes == ["UNSAFE_MEDICAL_REPLY"]


def test_safety_evaluator_allows_general_nutrition_guidance() -> None:
    req = make_request()
    req.purpose = "general_information"
    req.input_text = "長者平常要怎麼吃得比較均衡？"

    result = SafetyEvaluator().evaluate(
        req,
        "建議每天均衡吃六大類食物，也可以依日常需要適量喝水。",
    )

    assert result.decision.value == "ALLOW"
    assert result.reason_codes == ["ALLOW"]


def test_safety_evaluator_still_blocks_medication_advice_without_symptom_words() -> None:
    req = make_request()
    req.input_text = "請提供一般資訊。"

    result = SafetyEvaluator().evaluate(req, "建議先服用藥物再觀察。")

    assert result.decision.value == "BLOCK"
    assert result.reason_codes == ["UNSAFE_MEDICAL_REPLY"]


def test_companion_prompt_uses_neutral_address_when_profile_has_none() -> None:
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
    system_prompt, _ = build_model_prompts(req, manifest, req.language)
    assert "只使用中性的「您／您好」" in system_prompt
    assert "不得使用大哥、大姐" in system_prompt


def test_companion_prompt_honors_only_trusted_address_and_length() -> None:
    req = make_request()
    req.preferred_address = "林奶奶"
    req.response_length = "SHORT"
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
    system_prompt, _ = build_model_prompts(req, manifest, req.language)
    assert "稱呼只能使用 Core 提供的「林奶奶」" in system_prompt
    assert "回覆限制為一到兩句" in system_prompt


def test_knowledge_prompt_requires_readable_body_without_model_citations() -> None:
    req = make_request()
    manifest = ContextManifest(
        agent_id="companion-agent",
        elder_id=req.elder_id,
        tenant_id=req.tenant_id,
        purpose=req.purpose,
        consent_version=req.consent_version,
        policy_version=req.policy_version,
        items=[
            ContextItem(
                item_id="rag-item-001",
                source_type="rag-approved",
                content="合成的知識庫內容。",
                token_estimate=10,
            )
        ],
        excluded_items=[],
        total_token_estimate=10,
    )

    system_prompt, _ = build_model_prompts(req, manifest, req.language)

    assert "第一行先用一句話直接回答" in system_prompt
    assert "每行重點以「• 」開頭" in system_prompt
    assert "不要輸出標題、Markdown 連結或「引用來源」清單" in system_prompt
    assert "不得替任何人判定長照申請資格、長照等級、補助額度" in system_prompt
    assert "官方或專業評估提醒會由系統另外附上" in system_prompt


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
