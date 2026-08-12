"""LINE Login v2.1 ID-token verification boundary."""

from __future__ import annotations

import hmac
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.exceptions import AuthenticationError

_AUTHENTICATION_REQUIRED = "Authentication required"
_LINE_ISSUER = "https://access.line.me"
_LINE_VERIFY_ENDPOINT = "https://api.line.me/oauth2/v2.1/verify"
_MAX_TOKEN_LENGTH = 16_384
_MIN_NONCE_LENGTH = 32
_MAX_NONCE_LENGTH = 512
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VerifiedLineIdentity:
    """Minimal LINE identity returned after provider-side token verification."""

    subject: str
    email: str | None = None
    display_name: str | None = None

    def __post_init__(self) -> None:
        if (
            not self.subject
            or self.subject != self.subject.strip()
            or len(self.subject) > 255
            or not self.subject.isascii()
            or any(character.isspace() for character in self.subject)
        ):
            raise ValueError("LINE subject must be normalized ASCII of at most 255 characters")
        if self.email is not None and (
            not self.email
            or self.email != self.email.strip()
            or len(self.email) > 254
            or any(character.isspace() for character in self.email)
            or "@" not in self.email
        ):
            raise ValueError("LINE email must be normalized and at most 254 characters")
        if self.display_name is not None:
            normalized = self.display_name.strip()
            if len(normalized) > 120:
                raise ValueError("LINE display name must be at most 120 characters")
            object.__setattr__(self, "display_name", normalized or None)

    @property
    def provider(self) -> str:
        return "LINE"


class LineTokenVerifier(ABC):
    @abstractmethod
    async def verify_id_token(
        self,
        token: str,
        *,
        expected_nonce: str,
    ) -> VerifiedLineIdentity:
        """Verify one LINE ID token and its browser-transaction nonce."""
        ...


class LineOidcEndpointVerifier(LineTokenVerifier):
    """Verify web-login ID tokens through LINE's dedicated v2.1 endpoint."""

    def __init__(
        self,
        *,
        channel_id: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not channel_id or not channel_id.isascii() or not channel_id.isdigit():
            raise ValueError("LINE Login channel ID is invalid")
        if len(channel_id) > 32:
            raise ValueError("LINE Login channel ID is invalid")
        if not 0 < timeout_seconds <= 15:
            raise ValueError("LINE OIDC HTTP timeout must be between 0 and 15 seconds")
        self._channel_id = channel_id
        self._timeout = timeout_seconds
        self._transport = transport

    async def verify_id_token(
        self,
        token: str,
        *,
        expected_nonce: str,
    ) -> VerifiedLineIdentity:
        if (
            not isinstance(token, str)
            or not token
            or len(token) > _MAX_TOKEN_LENGTH
            or not token.isascii()
            or any(character.isspace() for character in token)
            or not isinstance(expected_nonce, str)
            or not _MIN_NONCE_LENGTH <= len(expected_nonce) <= _MAX_NONCE_LENGTH
            or expected_nonce != expected_nonce.strip()
            or not expected_nonce.isascii()
        ):
            self._reject("INPUT")

        claims: Any = None
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    _LINE_VERIFY_ENDPOINT,
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={
                        "id_token": token,
                        "client_id": self._channel_id,
                        "nonce": expected_nonce,
                    },
                )
                response.raise_for_status()
                claims = response.json()
        except Exception:
            self._reject("PROVIDER_VERIFICATION")

        if not isinstance(claims, dict):
            self._reject("CLAIMS")
        self._validate_claims(claims, expected_nonce=expected_nonce)
        try:
            return VerifiedLineIdentity(
                subject=self._subject(claims),
                email=self._email(claims),
                display_name=self._display_name(claims),
            )
        except ValueError:
            self._reject("IDENTITY_CLAIMS")

    def _validate_claims(self, claims: dict[str, Any], *, expected_nonce: str) -> None:
        now = int(datetime.now(UTC).timestamp())
        issued_at = claims.get("iat")
        expires_at = claims.get("exp")
        nonce = claims.get("nonce")
        if claims.get("iss") != _LINE_ISSUER:
            self._reject("ISSUER")
        if claims.get("aud") != self._channel_id:
            self._reject("AUDIENCE")
        if (
            type(issued_at) is not int
            or type(expires_at) is not int
            or issued_at >= expires_at
            or expires_at <= now
            or issued_at > now + 300
        ):
            self._reject("TOKEN_TIME")
        if (
            not isinstance(nonce, str)
            or not nonce.isascii()
            or not hmac.compare_digest(nonce, expected_nonce)
        ):
            self._reject("NONCE")

    @staticmethod
    def _subject(claims: dict[str, Any]) -> str:
        subject = claims.get("sub")
        if not isinstance(subject, str):
            raise ValueError("invalid subject")
        return subject

    @staticmethod
    def _email(claims: dict[str, Any]) -> str | None:
        value = claims.get("email")
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("invalid email")
        return value.strip().casefold()

    @staticmethod
    def _display_name(claims: dict[str, Any]) -> str | None:
        value = claims.get("name")
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("invalid display name")
        return value

    @staticmethod
    def _reject(reason: str) -> None:
        logger.warning("LINE ID token rejected reason=%s", reason)
        raise AuthenticationError(_AUTHENTICATION_REQUIRED)
