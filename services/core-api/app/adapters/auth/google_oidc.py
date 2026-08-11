"""Google OpenID Connect ID-token verification boundary.

This module performs cryptographic provider verification only. It does not
create Actors, link identities, issue App Sessions, or register a runtime
authenticator. Those operations remain behind later rollout gates.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm
from jwt.exceptions import (
    ExpiredSignatureError,
    ImmatureSignatureError,
    InvalidAudienceError,
    InvalidSignatureError,
    InvalidTokenError,
    MissingRequiredClaimError,
)

from app.core.exceptions import AuthenticationError

_AUTHENTICATION_REQUIRED = "Authentication required"
_GOOGLE_ISSUERS = frozenset({"https://accounts.google.com", "accounts.google.com"})
_GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
_MAX_TOKEN_LENGTH = 16_384
_MIN_NONCE_LENGTH = 32
_MAX_NONCE_LENGTH = 512
_MAX_KID_LENGTH = 256
_CACHE_MAX_AGE_PATTERN = re.compile(r"(?:^|,)\s*max-age=(\d+)\s*(?:,|$)", re.IGNORECASE)
logger = logging.getLogger(__name__)


class _InvalidGoogleHeaderError(Exception):
    """Internal marker for a rejected, untrusted JWT header."""


class _InvalidGoogleClaimError(Exception):
    """Internal marker for provider-specific claim rejection."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _rejection_reason(exc: Exception) -> str:
    if isinstance(exc, _InvalidGoogleHeaderError):
        return "HEADER"
    if isinstance(exc, _InvalidGoogleClaimError):
        return exc.reason
    if isinstance(exc, ExpiredSignatureError):
        return "EXPIRED"
    if isinstance(exc, ImmatureSignatureError):
        return "TOKEN_TIME"
    if isinstance(exc, InvalidAudienceError):
        return "AUDIENCE"
    if isinstance(exc, InvalidSignatureError):
        return "SIGNATURE"
    if isinstance(exc, MissingRequiredClaimError):
        return "REQUIRED_CLAIM"
    if isinstance(exc, AuthenticationError):
        return "JWKS"
    if isinstance(exc, InvalidTokenError):
        return "INVALID_TOKEN"
    return "INVALID_TOKEN"


def _log_rejection(reason: str) -> None:
    logger.warning("Google ID token rejected reason=%s", reason)


@dataclass(frozen=True)
class VerifiedGoogleIdentity:
    """Minimal Google identity returned only after full ID-token verification."""

    subject: str
    email: str | None = None
    email_verified: bool = False
    display_name: str | None = None

    def __post_init__(self) -> None:
        if (
            not self.subject
            or self.subject != self.subject.strip()
            or len(self.subject) > 255
            or not self.subject.isascii()
            or any(character.isspace() for character in self.subject)
        ):
            raise ValueError("Google subject must be normalized ASCII of at most 255 characters")
        if self.email_verified != (self.email is not None):
            raise ValueError("Google email may be retained only when verified")
        if self.email is not None and (
            not self.email or self.email != self.email.strip() or len(self.email) > 254
        ):
            raise ValueError("Google email must be normalized and at most 254 characters")
        if self.display_name is not None:
            normalized_display_name = self.display_name.strip()
            if len(normalized_display_name) > 120:
                raise ValueError("Google display name must be at most 120 characters")
            object.__setattr__(self, "display_name", normalized_display_name or None)

    @property
    def provider(self) -> str:
        return "GOOGLE"


class GoogleTokenVerifier(ABC):
    """Provider boundary used by the future Google code-exchange workflow."""

    @abstractmethod
    async def verify_id_token(
        self,
        token: str,
        *,
        expected_nonce: str,
    ) -> VerifiedGoogleIdentity:
        """Verify one Google ID token and its browser-transaction nonce."""
        ...


class GoogleJwksCache:
    """Process-local Google JWKS cache honoring bounded Cache-Control max-age."""

    def __init__(
        self,
        *,
        max_ttl_seconds: int,
        timeout_seconds: float,
    ) -> None:
        if not 30 <= max_ttl_seconds <= 3_600:
            raise ValueError("Google JWKS cache TTL must be between 30 and 3600 seconds")
        if not 0 < timeout_seconds <= 15:
            raise ValueError("Google JWKS HTTP timeout must be between 0 and 15 seconds")
        self._jwks_url = _GOOGLE_JWKS_URL
        self._max_ttl_seconds = max_ttl_seconds
        self._timeout = timeout_seconds
        self._keys: dict[str, dict[str, Any]] = {}
        self._expires_at = datetime.min.replace(tzinfo=UTC)
        self._lock = asyncio.Lock()

    async def get(self, kid: str, *, force_refresh: bool = False) -> dict[str, Any]:
        now = datetime.now(UTC)
        if not force_refresh and now < self._expires_at and kid in self._keys:
            return self._keys[kid]

        async with self._lock:
            now = datetime.now(UTC)
            if not force_refresh and now < self._expires_at and kid in self._keys:
                return self._keys[kid]
            await self._refresh()
            key = self._keys.get(kid)
            if key is None:
                raise AuthenticationError(_AUTHENTICATION_REQUIRED)
            return key

    async def _refresh(self) -> None:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(self._jwks_url)
                response.raise_for_status()
                document = response.json()
                cache_control = response.headers.get("cache-control", "")
            keys = document.get("keys") if isinstance(document, dict) else None
            if not isinstance(keys, list):
                raise ValueError("JWKS response has no keys")

            parsed: dict[str, dict[str, Any]] = {}
            for key in keys:
                if (
                    not isinstance(key, dict)
                    or not isinstance(key.get("kid"), str)
                    or not key["kid"]
                    or len(key["kid"]) > _MAX_KID_LENGTH
                    or key.get("kty") != "RSA"
                    or key.get("alg") not in {None, "RS256"}
                    or key.get("use") not in {None, "sig"}
                ):
                    continue
                if key["kid"] in parsed:
                    raise ValueError("JWKS response contains duplicate key IDs")
                parsed[key["kid"]] = key
            if not parsed:
                raise ValueError("JWKS response has no usable RSA signing keys")
        except Exception as exc:
            raise AuthenticationError(_AUTHENTICATION_REQUIRED) from exc

        ttl_seconds = self._cache_ttl_seconds(cache_control)
        self._keys = parsed
        self._expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)

    def _cache_ttl_seconds(self, cache_control: str) -> int:
        match = _CACHE_MAX_AGE_PATTERN.search(cache_control)
        if match is None:
            return self._max_ttl_seconds
        return min(int(match.group(1)), self._max_ttl_seconds)


class GoogleOidcJwtVerifier(GoogleTokenVerifier):
    """Verify Google RS256 ID tokens locally against Google's rotating JWKS."""

    def __init__(
        self,
        *,
        client_id: str,
        jwks_cache_seconds: int = 300,
        http_timeout_seconds: float = 5.0,
        jwks_cache: GoogleJwksCache | None = None,
    ) -> None:
        normalized_client_id = client_id.strip()
        if (
            not normalized_client_id
            or normalized_client_id != client_id
            or len(normalized_client_id) > 512
            or any(character.isspace() for character in normalized_client_id)
        ):
            raise ValueError("Google OIDC client ID must be a normalized non-empty value")
        self._client_id = normalized_client_id
        self._jwks_cache = jwks_cache or GoogleJwksCache(
            max_ttl_seconds=jwks_cache_seconds,
            timeout_seconds=http_timeout_seconds,
        )

    async def verify_id_token(
        self,
        token: str,
        *,
        expected_nonce: str,
    ) -> VerifiedGoogleIdentity:
        if (
            not isinstance(token, str)
            or not token
            or len(token) > _MAX_TOKEN_LENGTH
            or not token.isascii()
            or not isinstance(expected_nonce, str)
            or len(expected_nonce) < _MIN_NONCE_LENGTH
            or expected_nonce != expected_nonce.strip()
            or len(expected_nonce) > _MAX_NONCE_LENGTH
            or not expected_nonce.isascii()
        ):
            _log_rejection("INPUT")
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)

        claims = await self._decode(token)
        try:
            issuer = claims.get("iss")
            if not isinstance(issuer, str) or issuer not in _GOOGLE_ISSUERS:
                raise _InvalidGoogleClaimError("ISSUER")
            if claims.get("aud") != self._client_id:
                raise _InvalidGoogleClaimError("AUDIENCE")
            issued_at = claims.get("iat")
            expires_at = claims.get("exp")
            if type(issued_at) is not int or type(expires_at) is not int or issued_at >= expires_at:
                raise _InvalidGoogleClaimError("TOKEN_TIME")
            nonce = claims.get("nonce")
            if (
                not isinstance(nonce, str)
                or not nonce.isascii()
                or not hmac.compare_digest(nonce, expected_nonce)
            ):
                raise _InvalidGoogleClaimError("NONCE")
            authorized_party = claims.get("azp")
            if authorized_party is not None and authorized_party != self._client_id:
                raise _InvalidGoogleClaimError("AUTHORIZED_PARTY")

            subject = self._subject(claims)
            email, email_verified = self._verified_email(claims)
            display_name = self._display_name(claims)
            return VerifiedGoogleIdentity(
                subject=subject,
                email=email,
                email_verified=email_verified,
                display_name=display_name,
            )
        except _InvalidGoogleClaimError as exc:
            _log_rejection(exc.reason)
            raise AuthenticationError(_AUTHENTICATION_REQUIRED) from None

    async def _decode(self, token: str) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if (
                header.get("alg") != "RS256"
                or not isinstance(kid, str)
                or not kid
                or len(kid) > _MAX_KID_LENGTH
            ):
                raise _InvalidGoogleHeaderError
            claims = await self._decode_with_key(token, await self._jwks_cache.get(kid))
        except InvalidSignatureError:
            try:
                claims = await self._decode_with_key(
                    token,
                    await self._jwks_cache.get(kid, force_refresh=True),
                )
            except Exception as exc:
                _log_rejection(_rejection_reason(exc))
                raise AuthenticationError(_AUTHENTICATION_REQUIRED) from None
        except Exception as exc:
            _log_rejection(_rejection_reason(exc))
            raise AuthenticationError(_AUTHENTICATION_REQUIRED) from None
        return claims

    async def _decode_with_key(self, token: str, jwk: dict[str, Any]) -> dict[str, Any]:
        key = RSAAlgorithm.from_jwk(json.dumps(jwk))
        return jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=self._client_id,
            options={
                "require": ["aud", "exp", "iat", "iss", "nonce", "sub"],
                "verify_iss": False,
            },
        )

    @staticmethod
    def _subject(claims: dict[str, Any]) -> str:
        subject = claims.get("sub")
        if (
            not isinstance(subject, str)
            or not subject
            or subject != subject.strip()
            or len(subject) > 255
            or not subject.isascii()
            or any(character.isspace() for character in subject)
        ):
            raise _InvalidGoogleClaimError("SUBJECT")
        return subject

    @staticmethod
    def _verified_email(claims: dict[str, Any]) -> tuple[str | None, bool]:
        verified_claim = claims.get("email_verified")
        if verified_claim is True or verified_claim == "true":
            email = claims.get("email")
            if (
                not isinstance(email, str)
                or not email
                or email != email.strip()
                or len(email) > 254
            ):
                raise _InvalidGoogleClaimError("IDENTITY_CLAIMS")
            return email, True
        if verified_claim is None or verified_claim is False or verified_claim == "false":
            return None, False
        raise _InvalidGoogleClaimError("IDENTITY_CLAIMS")

    @staticmethod
    def _display_name(claims: dict[str, Any]) -> str | None:
        display_name = claims.get("name")
        if display_name is None:
            return None
        if not isinstance(display_name, str):
            raise _InvalidGoogleClaimError("IDENTITY_CLAIMS")
        normalized = display_name.strip()
        if len(normalized) > 120:
            raise _InvalidGoogleClaimError("IDENTITY_CLAIMS")
        return normalized or None
