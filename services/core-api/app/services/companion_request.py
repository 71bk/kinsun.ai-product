"""Pure mapping from Core-owned turn context to the Agent Runtime request."""

from __future__ import annotations

from app.core.auth import ActorContext
from app.models.conversation import ConversationSession

_ACTOR_ROLE_MAP = {
    "ELDER": "elder",
    "FAMILY_MEMBER": "family",
    "SYSTEM_SERVICE": "system",
}

_LANGUAGE_MAP = {
    "ZH_TW": "zh-TW",
    "NAN_TW": "nan-TW",
    "HAK_TW": "hak-TW",
    "EN_US": "en-US",
    "MIXED": "zh-TW",
    "UNKNOWN": "zh-TW",
}


def build_companion_runtime_request(
    *,
    conversation: ConversationSession,
    actor_context: ActorContext,
    request_id: str,
    agent_run_wire_id: str,
    purpose: str,
    preferred_address: str | None,
    response_length: str,
    input_text: str,
    confirmed_memories: list[dict[str, object]],
    verified_care_events: list[dict[str, object]],
    trusted_care_profile: list[dict[str, object]],
    requested_outputs: list[str],
    latency_budget_ms: int,
) -> dict[str, object]:
    """Build the runtime payload from already-authorized Core context."""
    return {
        "schema_version": "1.0.0",
        "request_id": request_id,
        "trace_id": conversation.trace_id,
        "agent_run_id": agent_run_wire_id,
        "session_id": str(conversation.id),
        "actor_id": str(actor_context.actor_id),
        "actor_role": _ACTOR_ROLE_MAP.get(actor_context.actor_role, "staff"),
        "elder_id": str(conversation.elder_id),
        "tenant_id": str(actor_context.tenant_id),
        "purpose": purpose,
        "consent_version": str(conversation.consent_version),
        "policy_version": conversation.policy_version,
        "language": _LANGUAGE_MAP[conversation.language_route],
        "preferred_address": preferred_address,
        "response_length": response_length,
        "input_text": input_text,
        "confirmed_memories": confirmed_memories,
        "verified_care_events": verified_care_events,
        "trusted_care_profile": trusted_care_profile,
        "allowed_tools": [],
        "requested_outputs": requested_outputs,
        "max_steps": 3,
        "latency_budget_ms": latency_budget_ms,
    }
