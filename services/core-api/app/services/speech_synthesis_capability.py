"""Short-lived capabilities binding one Core reply to one TTS request."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, ServiceUnavailableError

_INVALID_CAPABILITY_MESSAGE = "Speech synthesis capability is invalid or unavailable"
_CITATION_MARKER = "\n\n引用來源：\n"
_MAX_TTS_CHARACTERS = 3000


def _utc_now() -> datetime:
    return datetime.now(UTC)


def prepare_speech_synthesis_text(reply_text: str) -> str | None:
    """Return the exact bounded text Core authorizes the provider to synthesize."""

    normalized = reply_text.replace("\r\n", "\n").replace("\r", "\n")
    marker_index = normalized.rfind(_CITATION_MARKER)
    speech_text = normalized[:marker_index].strip() if marker_index >= 0 else normalized.strip()
    if not speech_text or len(speech_text) > _MAX_TTS_CHARACTERS:
        return None
    return speech_text


@dataclass(frozen=True, slots=True)
class IssuedSpeechSynthesisCapability:
    value: str
    expires_at: datetime


class SpeechSynthesisCapabilityCodec:
    """Issue opaque HMAC capabilities bound to immutable turn metadata."""

    def __init__(
        self,
        secret: str,
        ttl_seconds: int = 60,
        *,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        if len(secret.encode("utf-8")) < 32:
            raise ValueError("Speech synthesis capability secret must contain at least 32 bytes")
        if not 15 <= ttl_seconds <= 120:
            raise ValueError("Speech synthesis capability TTL must be between 15 and 120 seconds")
        self._secret = secret.encode("utf-8")
        self._ttl = timedelta(seconds=ttl_seconds)
        self._now = now

    def issue(
        self,
        *,
        session_id: UUID,
        agent_run_id: UUID,
        tenant_id: UUID,
        actor_id: UUID,
        text: str,
        language: str,
        completed_at: datetime,
    ) -> IssuedSpeechSynthesisCapability:
        issued_at = self._as_utc(completed_at)
        text_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        character_count = len(text)
        return IssuedSpeechSynthesisCapability(
            value=self._expected_value(
                session_id=session_id,
                agent_run_id=agent_run_id,
                tenant_id=tenant_id,
                actor_id=actor_id,
                text_sha256=text_sha256,
                character_count=character_count,
                language=language,
                issued_at=issued_at,
            ),
            expires_at=issued_at + self._ttl,
        )

    def verify(
        self,
        value: str,
        *,
        session_id: UUID,
        agent_run_id: UUID,
        tenant_id: UUID,
        actor_id: UUID,
        text_sha256: str,
        character_count: int,
        language: str,
        completed_at: datetime,
    ) -> datetime:
        """Verify all request bindings and return the trusted expiry."""

        try:
            issued_at = self._as_utc(completed_at)
            expires_at = issued_at + self._ttl
            expected = self._expected_value(
                session_id=session_id,
                agent_run_id=agent_run_id,
                tenant_id=tenant_id,
                actor_id=actor_id,
                text_sha256=text_sha256,
                character_count=character_count,
                language=language,
                issued_at=issued_at,
            )
            if (
                not 32 <= len(value) <= 128
                or not value.isascii()
                or self._now() >= expires_at
                or not hmac.compare_digest(value, expected)
            ):
                raise AuthenticationError(_INVALID_CAPABILITY_MESSAGE)
            return expires_at
        except AuthenticationError:
            raise
        except Exception:
            raise AuthenticationError(_INVALID_CAPABILITY_MESSAGE) from None

    def _expected_value(
        self,
        *,
        session_id: UUID,
        agent_run_id: UUID,
        tenant_id: UUID,
        actor_id: UUID,
        text_sha256: str,
        character_count: int,
        language: str,
        issued_at: datetime,
    ) -> str:
        claims = {
            "actor_id": str(actor_id),
            "agent_run_id": str(agent_run_id),
            "audience": "kinsun-speech-gateway",
            "character_count": character_count,
            "expires_at": int((issued_at + self._ttl).timestamp()),
            "issued_at": int(issued_at.timestamp()),
            "issuer": "kinsun-core-api",
            "language": language,
            "purpose": "SPEECH_SYNTHESIS",
            "session_id": str(session_id),
            "tenant_id": str(tenant_id),
            "text_sha256": text_sha256,
            "version": 1,
        }
        canonical = json.dumps(
            claims,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digest = hmac.new(self._secret, canonical, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    @staticmethod
    def digest(value: str) -> str:
        return hashlib.sha256(value.encode("ascii")).hexdigest()

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def get_speech_synthesis_capability_codec() -> SpeechSynthesisCapabilityCodec:
    settings = get_settings()
    if not settings.speech_synthesis_capability_enabled:
        raise ServiceUnavailableError("Speech synthesis authorization is not configured")
    try:
        return SpeechSynthesisCapabilityCodec(
            settings.speech_synthesis_capability_hmac_secret,
            settings.speech_synthesis_capability_ttl_seconds,
        )
    except ValueError:
        raise ServiceUnavailableError("Speech synthesis authorization is not configured") from None
