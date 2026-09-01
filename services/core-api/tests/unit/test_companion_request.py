"""Pure Agent Runtime request mapping tests."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.services.companion_request import build_companion_runtime_request

_SESSION_ID = UUID("11111111-1111-4111-8111-111111111111")
_ACTOR_ID = UUID("22222222-2222-4222-8222-222222222222")
_ELDER_ID = UUID("33333333-3333-4333-8333-333333333333")
_TENANT_ID = UUID("44444444-4444-4444-8444-444444444444")


def _conversation(*, language_route: str = "ZH_TW") -> SimpleNamespace:
    return SimpleNamespace(
        id=_SESSION_ID,
        elder_id=_ELDER_ID,
        trace_id="trace-core-22",
        consent_version=7,
        policy_version="policy-v7",
        language_route=language_route,
    )


def _actor(*, actor_role: str = "ELDER") -> SimpleNamespace:
    return SimpleNamespace(
        actor_id=_ACTOR_ID,
        actor_role=actor_role,
        tenant_id=_TENANT_ID,
    )


def _build(
    *,
    actor_role: str = "ELDER",
    language_route: str = "ZH_TW",
) -> dict[str, object]:
    return build_companion_runtime_request(
        conversation=_conversation(language_route=language_route),
        actor_context=_actor(actor_role=actor_role),
        request_id="req-fixed",
        agent_run_wire_id="run-fixed",
        purpose="BASIC_VOICE",
        preferred_address="林阿嬤",
        response_length="short",
        input_text="今天早餐吃稀飯。",
        confirmed_memories=[{"memory_id": "memory-1", "statement": "早餐喜歡稀飯"}],
        verified_care_events=[{"event_id": "event-1", "summary": "已確認按時用餐"}],
        trusted_care_profile=[
            {
                "care_profile_entry_id": "profile-1",
                "version": 1,
                "category": "CARE_PRECAUTION",
                "content": "轉位時需要兩人協助",
                "source_type": "STAFF_RECORDED",
                "verification_status": "RECORDED",
            }
        ],
        requested_outputs=["event_candidate", "memory_candidate"],
        latency_budget_ms=1_800,
    )


def test_build_companion_runtime_request_preserves_complete_payload() -> None:
    payload = _build()

    expected = {
        "schema_version": "1.0.0",
        "request_id": "req-fixed",
        "trace_id": "trace-core-22",
        "agent_run_id": "run-fixed",
        "session_id": str(_SESSION_ID),
        "actor_id": str(_ACTOR_ID),
        "actor_role": "elder",
        "elder_id": str(_ELDER_ID),
        "tenant_id": str(_TENANT_ID),
        "purpose": "BASIC_VOICE",
        "consent_version": "7",
        "policy_version": "policy-v7",
        "language": "zh-TW",
        "preferred_address": "林阿嬤",
        "response_length": "short",
        "input_text": "今天早餐吃稀飯。",
        "confirmed_memories": [{"memory_id": "memory-1", "statement": "早餐喜歡稀飯"}],
        "verified_care_events": [{"event_id": "event-1", "summary": "已確認按時用餐"}],
        "trusted_care_profile": [
            {
                "care_profile_entry_id": "profile-1",
                "version": 1,
                "category": "CARE_PRECAUTION",
                "content": "轉位時需要兩人協助",
                "source_type": "STAFF_RECORDED",
                "verification_status": "RECORDED",
            }
        ],
        "allowed_tools": [],
        "requested_outputs": ["event_candidate", "memory_candidate"],
        "max_steps": 3,
        "latency_budget_ms": 1_800,
    }
    assert len(payload) == 23
    assert payload == expected


@pytest.mark.parametrize(
    ("actor_role", "expected"),
    [
        ("ELDER", "elder"),
        ("FAMILY_MEMBER", "family"),
        ("SYSTEM_SERVICE", "system"),
        ("CARE_WORKER", "staff"),
    ],
)
def test_build_companion_runtime_request_maps_actor_role(
    actor_role: str,
    expected: str,
) -> None:
    assert _build(actor_role=actor_role)["actor_role"] == expected


@pytest.mark.parametrize(
    ("language_route", "expected"),
    [
        ("ZH_TW", "zh-TW"),
        ("NAN_TW", "nan-TW"),
        ("HAK_TW", "hak-TW"),
        ("EN_US", "en-US"),
        ("MIXED", "zh-TW"),
        ("UNKNOWN", "zh-TW"),
    ],
)
def test_build_companion_runtime_request_maps_language_route(
    language_route: str,
    expected: str,
) -> None:
    assert _build(language_route=language_route)["language"] == expected
