"""Synthetic provider envelopes retain strict prose, JSON and evidence bounds."""

import json
from types import SimpleNamespace

import httpx
import pytest

from agent_runtime.common.errors import ModelDependencyError
from agent_runtime.contracts.models import AgentRunRequest
from agent_runtime.models.bedrock_provider import BedrockModelProvider
from agent_runtime.models.gemini_provider import GeminiModelProvider
from agent_runtime.models.openai_compatible_provider import OpenAICompatibleModelProvider
from agent_runtime.rag.grounded_answer import (
    MAX_OUTPUT_CHARS,
    GroundedAnswerError,
    build_grounded_context,
    evidence_quote_spans,
    parse_grounded_answer,
)


def public_case():
    request = AgentRunRequest(
        request_id="synthetic-envelope-request",
        session_id="public-session",
        actor_id="public-actor",
        actor_role="system",
        elder_id="public-elder",
        tenant_id="public-tenant",
        purpose="general_information",
        consent_version="public",
        policy_version="synthetic-policy",
        language="zh-TW",
        input_text="請列出全部合成測試項目。",
        latency_budget_ms=5000,
    )
    source = SimpleNamespace(
        chunk_id="synthetic-" + "a" * 118,
        text="\n".join(f"合成項目{i}：依合成指南規定，可向測試中心提出申請。" for i in range(20)),
        title="合成指南",
        source_version="synthetic-v1",
        source_locator="合成章節",
        current_status="unknown",
        warnings=["CURRENCY_UNKNOWN"],
        requires_official_assessment=False,
        requires_professional_assessment=False,
    )
    document = {
        "status": "ANSWER",
        "answer_text": source.text,
        "citation_ids": [source.chunk_id],
        "support_quotes": [
            {"chunk_id": source.chunk_id, "span_id": span}
            for span in evidence_quote_spans(source.text)
        ],
        "missing_facets": [],
    }
    return request, source, build_grounded_context(request, [source]), document


async def provider_reply(kind, raw, request, manifest):
    if kind == "gemini":

        async def generate_content(**_kwargs):
            return SimpleNamespace(text=raw)

        client = SimpleNamespace(
            aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
        )
        provider = GeminiModelProvider(
            api_key="synthetic-key",
            model_id="configured-model",
            max_tokens=512,
            temperature=0.2,
            timeout_seconds=30,
            client=client,
        )
        return await provider.generate_reply(request, manifest, "zh-TW")
    if kind == "bedrock":
        client = SimpleNamespace(
            converse=lambda **_kwargs: {"output": {"message": {"content": [{"text": raw}]}}}
        )
        provider = BedrockModelProvider(
            client, model_id="configured-model", max_tokens=512, temperature=0.2
        )
        return await provider.generate_reply(request, manifest, "zh-TW")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"choices": [{"message": {"content": raw}}]})
        )
    ) as client:
        provider = OpenAICompatibleModelProvider(
            base_url="https://models.example.test/v1",
            model_id="configured-model",
            api_key=None,
            max_tokens=512,
            temperature=0.2,
            timeout_seconds=30,
            client=client,
        )
        return await provider.generate_reply(request, manifest, "zh-TW")


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["gemini", "openai-compatible", "bedrock"])
async def test_long_source_ids_fit_envelope_and_still_parse(kind):
    request, source, manifest, document = public_case()
    raw = json.dumps(document, ensure_ascii=False)
    assert 4000 < len(raw) < MAX_OUTPUT_CHARS
    result = await provider_reply(kind, raw, request, manifest)
    assert parse_grounded_answer(result, [source]).answer_text == source.text


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["gemini", "openai-compatible", "bedrock"])
async def test_structured_envelope_cannot_bypass_answer_or_span_validation(kind):
    request, source, manifest, document = public_case()
    for changes in (
        {"answer_text": "字" * 4001},
        {"support_quotes": [{"chunk_id": source.chunk_id, "span_id": "unknown-span"}]},
    ):
        raw = json.dumps({**document, **changes}, ensure_ascii=False)
        result = await provider_reply(kind, raw, request, manifest)
        with pytest.raises(GroundedAnswerError):
            parse_grounded_answer(result, [source])


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["gemini", "openai-compatible", "bedrock"])
async def test_providers_reject_envelope_overflow(kind):
    request, _source, manifest, _document = public_case()
    with pytest.raises(ModelDependencyError):
        await provider_reply(kind, "x" * (MAX_OUTPUT_CHARS + 1), request, manifest)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["gemini", "openai-compatible", "bedrock"])
async def test_ordinary_reply_cannot_use_structured_envelope_allowance(kind):
    request, _source, manifest, _document = public_case()
    manifest.items = [item for item in manifest.items if item.source_type == "user_input"]
    with pytest.raises(ModelDependencyError):
        await provider_reply(kind, "x" * 4001, request, manifest)
