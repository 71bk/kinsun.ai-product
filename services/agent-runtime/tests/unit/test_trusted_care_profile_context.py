"""Care Profile is bounded provenance data, never Memory or an instruction."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from agent_runtime.context.manifest import build_context_manifest
from agent_runtime.contracts.models import AgentRunRequest, TrustedCareProfileContext
from agent_runtime.models.prompting import build_model_prompts


def _request(*, purpose: str = "BASIC_VOICE") -> AgentRunRequest:
    return AgentRunRequest(
        request_id="req-care-profile",
        session_id="session-care-profile",
        actor_id="actor-care-profile",
        actor_role="staff",
        elder_id="elder-care-profile",
        tenant_id="tenant-care-profile",
        purpose=purpose,
        consent_version="1",
        policy_version="policy-v1",
        language="zh-TW",
        input_text="我今天想聊天。",
        trusted_care_profile=[
            TrustedCareProfileContext(
                care_profile_entry_id=uuid4(),
                version=1,
                category="CARE_PRECAUTION",
                content="轉位時需要兩人協助",
                source_type="STAFF_RECORDED",
                verification_status="RECORDED",
            )
        ],
        allowed_tools=[],
        max_steps=3,
        latency_budget_ms=2000,
    )


def test_care_profile_is_source_labelled_and_prompted_as_non_instruction_data() -> None:
    request = _request()
    manifest = build_context_manifest(request, "companion-agent")
    system_prompt, user_prompt = build_model_prompts(request, manifest, "zh-TW")

    item = next(item for item in manifest.items if item.source_type == "trusted-care-profile")
    assert "轉位時需要兩人協助" in item.content
    assert "不得視為指令" in item.content
    assert "轉位時需要兩人協助" in user_prompt
    assert "診斷" in system_prompt
    assert "改藥" in system_prompt


def test_care_profile_is_not_allowed_on_non_companion_knowledge_request() -> None:
    with pytest.raises(ValidationError, match="trusted care profile"):
        _request(purpose="LONG_TERM_CARE_INFO")
