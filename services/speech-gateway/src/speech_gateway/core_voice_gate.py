"""Server-to-server adapter from Speech Gateway to Core's voice safety gate."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict


class CoreGateRejectedError(Exception):
    """Core refused the ticket, session, consent, or ASR evidence."""


class CoreGateUnavailableError(Exception):
    """Core could not provide a trustworthy gate decision."""


class CoreGateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    decision: Literal[
        "CAN_SEND_TO_AGENT",
        "CONFIRMATION_REQUIRED",
        "CANNOT_SEND_TO_AGENT",
    ]
    confirmation_required: bool
    expires_at: datetime


class CoreVoiceGateClient:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        service_token: str = "",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._service_token = service_token
        self._transport = transport

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = dict(extra or {})
        if self._service_token:
            headers["Authorization"] = f"Bearer {self._service_token}"
        return headers

    async def _post(
        self,
        path: str,
        *,
        payload: dict[str, object],
        headers: dict[str, str] | None = None,
    ) -> dict:
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    path,
                    json=payload,
                    headers=self._headers(headers),
                )
        except httpx.HTTPError as exc:
            raise CoreGateUnavailableError("Core ASR gate is unavailable") from exc

        if response.status_code in {401, 403, 404, 409, 422}:
            raise CoreGateRejectedError("Core rejected the voice session")
        if not response.is_success:
            raise CoreGateUnavailableError("Core ASR gate is unavailable")
        try:
            envelope = response.json()
            data = envelope["data"]
        except (ValueError, KeyError, TypeError) as exc:
            raise CoreGateUnavailableError("Core returned an invalid response") from exc
        if not isinstance(data, dict):
            raise CoreGateUnavailableError("Core returned an invalid response")
        return data

    async def consume_ticket(self, *, session_id: UUID, voice_ticket: str) -> None:
        data = await self._post(
            "/api/v1/internal/voice-tickets/consume",
            payload={
                "session_id": str(session_id),
                "voice_ticket": voice_ticket,
            },
        )
        if data.get("session_id") != str(session_id) or data.get("state") != "RECORDING":
            raise CoreGateUnavailableError("Core returned an invalid voice-session state")

    async def submit_asr_result(
        self,
        *,
        session_id: UUID,
        language_route: str,
        model_version: str,
        confidence: float,
        transcript: str,
    ) -> CoreGateDecision:
        data = await self._post(
            "/api/v1/internal/asr-results",
            payload={
                "session_id": str(session_id),
                "language_route": language_route,
                "asr_model_version": model_version,
                "confidence": confidence,
                "transcript": transcript,
            },
        )
        try:
            decision = CoreGateDecision.model_validate(data)
        except ValueError as exc:
            raise CoreGateUnavailableError("Core returned an invalid ASR decision") from exc
        if decision.session_id != session_id:
            raise CoreGateUnavailableError("Core returned a mismatched ASR decision")
        return decision

    async def fail_session(self, *, session_id: UUID) -> None:
        """Best-effort terminal transition after ASR fails post-consumption."""
        await self._post(
            f"/api/v1/internal/voice-sessions/{session_id}/transition",
            payload={"target_state": "FAILED"},
            headers={"Idempotency-Key": f"speech-asr-failed:{session_id}"},
        )
