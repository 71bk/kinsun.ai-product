"""Strict server-to-server adapter for the M0 Agent Runtime."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError, field_validator

from app.adapters.service_identity import (
    SERVICE_CREDENTIAL_HEADER,
    ServiceCredentialSigner,
    canonical_json_bytes,
)
from app.core.agent_runtime import (
    AgentEventCandidateProposal,
    AgentMemoryCandidateProposal,
    AgentRunResult,
    AgentSafetyResult,
)
from app.core.config import get_settings
from app.core.exceptions import ServiceUnavailableError

_RESTRICTED_PROPOSAL_KEYS = frozenset(
    {
        "actor_id",
        "actor_role",
        "agent_run_id",
        "asr_confidence",
        "audio",
        "audio_uri",
        "consent_id",
        "consent_version",
        "elder_id",
        "full_prompt",
        "input_text",
        "policy_version",
        "prompt",
        "request_id",
        "secret",
        "session_id",
        "source_id",
        "source_type",
        "source_version",
        "tenant_id",
        "token",
        "trace_id",
        "transcript",
        "transcript_text",
    }
)
_EVIDENCE_REF_PATTERN = (
    r"^evidence:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-" r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
EvidenceReference = Annotated[
    str,
    Field(min_length=45, max_length=45, pattern=_EVIDENCE_REF_PATTERN),
]


def _contains_restricted_proposal_key(value: JsonValue) -> bool:
    if isinstance(value, dict):
        return any(
            key.casefold() in _RESTRICTED_PROPOSAL_KEYS or _contains_restricted_proposal_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_restricted_proposal_key(item) for item in value)
    return False


class _AgentSafetyPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0.0"]
    decision: Literal["ALLOW", "BLOCK", "SAFE_FALLBACK", "HUMAN_REVIEW"]
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    reason_codes: list[str]
    matched_terms: list[str]
    safe_reply: str | None


class _AgentEventCandidateProposalPayload(BaseModel):
    """Minimized untrusted output; it deliberately contains no scope facts."""

    model_config = ConfigDict(extra="forbid")

    event_type: Literal[
        "MEAL",
        "ACTIVITY",
        "SLEEP",
        "MEDICATION_STATEMENT",
        "EMOTION_EXPRESSION",
        "SOCIAL_CONTACT",
        "EXPECTED_CONTACT_MISSED",
        "ACTIVITY_PARTICIPATION",
        "ACTIVITY_CANCELLED",
        "COMPANIONSHIP_NEED",
    ]
    event_time: datetime | None
    structured_payload: dict[str, JsonValue]
    evidence_refs: list[EvidenceReference] = Field(max_length=16)
    confidence_band: Literal["LOW", "MEDIUM", "HIGH"]
    review_requirement: Literal["REQUIRED"]
    extractor_version: str = Field(min_length=1, max_length=80)

    @field_validator("structured_payload")
    @classmethod
    def reject_restricted_payload_keys(
        cls,
        payload: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        if _contains_restricted_proposal_key(payload):
            raise ValueError("structured_payload contains a restricted field")
        return payload


class _AgentMemoryCandidateProposalPayload(BaseModel):
    """Minimized untrusted memory output; Core owns scope, source, and state."""

    model_config = ConfigDict(extra="forbid")

    memory_type: Literal[
        "PREFERENCE",
        "IMPORTANT_RELATIONSHIP",
        "ROUTINE",
        "COMMUNICATION_PREFERENCE",
        "PERSONAL_HISTORY",
    ]
    memory_kind: Literal[
        "MUSIC_PREFERENCE",
        "HOBBY",
        "PREFERRED_ADDRESS",
        "FAMILY_RELATIONSHIP",
        "CONTACT_ROUTINE",
        "DAILY_ROUTINE",
        "HEALTH_INFERENCE",
        "MEDICATION_JUDGMENT",
        "MOOD_OR_LONELINESS_INFERENCE",
        "FAMILY_CONFLICT",
        "FINANCIAL_INFORMATION",
        "SENSITIVE_OR_UNKNOWN",
    ]
    normalized_content: str = Field(min_length=1, max_length=500)
    confirmation_question: str = Field(min_length=1, max_length=300)
    extraction_confidence: float = Field(ge=0, le=1)
    proposal_risk_hint: Literal["LOW", "MEDIUM", "HIGH"]
    extractor_version: str = Field(min_length=1, max_length=80)


class _AgentRunPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0.0"]
    request_id: str
    trace_id: str
    agent_run_id: str
    selected_agent: str
    reply_text: str = Field(min_length=1, max_length=4000)
    reply_language: str
    safety_result: _AgentSafetyPayload
    context_manifest_id: str
    step_count: int
    result_status: Literal["SUCCESS", "BLOCKED", "SAFE_FALLBACK", "FAILED"]
    reason_codes: list[str]
    event_candidate_proposal: _AgentEventCandidateProposalPayload | None = None
    memory_candidate_proposal: _AgentMemoryCandidateProposalPayload | None = None


class _AgentResponseMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    correlation_id: str
    timestamp: str
    schema_version: Literal["1.0"] = "1.0"


class _AgentRunEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: _AgentRunPayload
    meta: _AgentResponseMeta


class AgentRuntimeClient:
    """Call the private Agent Runtime and reject malformed responses."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        credential_signer: ServiceCredentialSigner,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        normalized_url = base_url.rstrip("/")
        parsed_url = urlsplit(normalized_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
            raise ValueError("Agent Runtime URL must be an absolute HTTP(S) origin")
        if parsed_url.scheme == "http" and parsed_url.hostname not in {
            "127.0.0.1",
            "localhost",
            "::1",
        }:
            raise ValueError("Remote Agent Runtime transport must use HTTPS")
        if parsed_url.username or parsed_url.password or parsed_url.query or parsed_url.fragment:
            raise ValueError("Agent Runtime URL must not contain credentials, query, or fragment")
        self._base_url = normalized_url
        self._timeout_seconds = timeout_seconds
        self._credential_signer = credential_signer
        self._transport = transport

    async def run(
        self,
        *,
        request_payload: dict[str, object],
        correlation_id: str,
    ) -> AgentRunResult:
        path = "/api/v1/agent/runs"
        body = canonical_json_bytes(request_payload)
        credential = self._credential_signer.sign(
            method="POST",
            path=path,
            body=body,
            correlation_id=correlation_id,
        )
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                transport=self._transport,
                # Agent Runtime is a private service boundary. Process-level
                # HTTP(S)_PROXY settings must never reroute localhost or
                # service-discovery traffic through an outbound proxy.
                trust_env=False,
            ) as client:
                response = await client.post(
                    path,
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Correlation-ID": correlation_id,
                        SERVICE_CREDENTIAL_HEADER: credential,
                    },
                )
                response.raise_for_status()
            envelope = _AgentRunEnvelope.model_validate(response.json())
        except (httpx.HTTPError, ValueError, ValidationError) as exc:
            raise ServiceUnavailableError("Agent runtime is unavailable") from exc
        if envelope.meta.correlation_id != correlation_id:
            raise ServiceUnavailableError("Agent runtime response correlation mismatch")
        data = envelope.data
        event_proposal = data.event_candidate_proposal
        memory_proposal = data.memory_candidate_proposal
        return AgentRunResult(
            schema_version=data.schema_version,
            request_id=data.request_id,
            trace_id=data.trace_id,
            agent_run_id=data.agent_run_id,
            selected_agent=data.selected_agent,
            reply_text=data.reply_text,
            reply_language=data.reply_language,
            safety_result=AgentSafetyResult(**data.safety_result.model_dump()),
            context_manifest_id=data.context_manifest_id,
            step_count=data.step_count,
            result_status=data.result_status,
            reason_codes=data.reason_codes,
            event_candidate_proposal=(
                AgentEventCandidateProposal(**event_proposal.model_dump())
                if event_proposal is not None
                else None
            ),
            memory_candidate_proposal=(
                AgentMemoryCandidateProposal(**memory_proposal.model_dump())
                if memory_proposal is not None
                else None
            ),
        )


def get_agent_runtime_client() -> AgentRuntimeClient:
    settings = get_settings()
    if not settings.service_identity_enabled:
        raise ServiceUnavailableError("Agent runtime service identity is disabled")
    try:
        signer = ServiceCredentialSigner(
            secret=settings.service_identity_hmac_secret,
            issuer=settings.service_identity_issuer,
            subject="core-api",
            audience="agent-runtime",
            ttl_seconds=settings.service_identity_ttl_seconds,
        )
    except ValueError as exc:
        raise ServiceUnavailableError("Agent runtime service identity is unavailable") from exc
    return AgentRuntimeClient(
        base_url=settings.agent_runtime_url,
        timeout_seconds=settings.agent_runtime_timeout_seconds,
        credential_signer=signer,
    )
