"""Verify short-lived request-bound Gate 1 service credentials."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from agent_runtime.common.errors import ServiceAuthenticationError
from agent_runtime.security.replay_store import ReplayStore, ReplayStoreError

SERVICE_CREDENTIAL_HEADER = "X-Kinsun-Service-Credential"
_TOKEN_PREFIX = "ksvc1"
_REQUIRED_CLAIMS = frozenset(
    {
        "aud",
        "body_sha256",
        "correlation_id",
        "exp",
        "iat",
        "iss",
        "jti",
        "method",
        "path",
        "sub",
        "v",
    }
)


def _decode_b64url(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _encode_b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


@dataclass(frozen=True, slots=True)
class ServiceCredentialSigner:
    """Matching signer used by synthetic tests and future Runtime→Core calls."""

    secret: str
    issuer: str = "kinsun-local"
    subject: str = "core-api"
    audience: str = "agent-runtime"
    ttl_seconds: int = 30

    def sign(
        self,
        *,
        method: str,
        path: str,
        body: bytes,
        correlation_id: str,
        issued_at: int | None = None,
        credential_id: str | None = None,
    ) -> str:
        now = int(time.time()) if issued_at is None else issued_at
        claims = {
            "aud": self.audience,
            "body_sha256": hashlib.sha256(body).hexdigest(),
            "correlation_id": correlation_id,
            "exp": now + self.ttl_seconds,
            "iat": now,
            "iss": self.issuer,
            "jti": credential_id or str(uuid.uuid4()),
            "method": method.upper(),
            "path": path,
            "sub": self.subject,
            "v": 1,
        }
        encoded_claims = _encode_b64url(canonical_json_bytes(claims))
        signed = f"{_TOKEN_PREFIX}.{encoded_claims}".encode("ascii")
        signature = hmac.new(self.secret.encode("utf-8"), signed, hashlib.sha256).digest()
        return f"{signed.decode('ascii')}.{_encode_b64url(signature)}"


@dataclass(frozen=True, slots=True)
class ServicePrincipal:
    issuer: str
    subject: str
    audience: str
    credential_id: str
    correlation_id: str


class ServiceCredentialVerifier:
    """Fail-closed verifier whose replay protection comes from an injected store.

    ``replay_store`` is required rather than defaulted: a forgotten store used to
    mean silent process-local protection, which cannot span replicas. The app
    refuses to start in production unless the configured store is durable.
    """

    def __init__(
        self,
        *,
        secret: str,
        issuer: str,
        expected_subject: str,
        audience: str,
        replay_store: ReplayStore,
        max_ttl_seconds: int = 60,
        clock_skew_seconds: int = 5,
    ) -> None:
        if len(secret.encode("utf-8")) < 32:
            raise ValueError("Service identity secret must contain at least 32 bytes")
        if not 1 <= max_ttl_seconds <= 60:
            raise ValueError("Service credential max TTL must be between 1 and 60 seconds")
        self._secret = secret.encode("utf-8")
        self._issuer = issuer
        self._expected_subject = expected_subject
        self._audience = audience
        self._replay_store = replay_store
        self._max_ttl_seconds = max_ttl_seconds
        self._clock_skew_seconds = clock_skew_seconds

    async def verify(
        self,
        token: str | None,
        *,
        method: str,
        path: str,
        body: bytes,
        correlation_id: str,
        now: int | None = None,
    ) -> ServicePrincipal:
        if not token or len(token) > 4096:
            raise ServiceAuthenticationError("Service credential is missing or invalid")
        try:
            prefix, encoded_claims, encoded_signature = token.split(".", 2)
            if prefix != _TOKEN_PREFIX:
                raise ValueError("wrong credential version")
            signed = f"{prefix}.{encoded_claims}".encode("ascii")
            supplied_signature = _decode_b64url(encoded_signature)
            expected_signature = hmac.new(self._secret, signed, hashlib.sha256).digest()
            if not hmac.compare_digest(supplied_signature, expected_signature):
                raise ValueError("signature mismatch")
            claims: dict[str, Any] = json.loads(_decode_b64url(encoded_claims))
        except (ValueError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
            raise ServiceAuthenticationError("Service credential is missing or invalid") from exc

        if set(claims) != _REQUIRED_CLAIMS:
            raise ServiceAuthenticationError("Service credential is missing or invalid")
        current_time = int(time.time()) if now is None else now
        try:
            issued_at = int(claims["iat"])
            expires_at = int(claims["exp"])
            credential_id = str(claims["jti"])
        except (TypeError, ValueError) as exc:
            raise ServiceAuthenticationError("Service credential is missing or invalid") from exc
        if isinstance(claims["iat"], bool) or isinstance(claims["exp"], bool):
            raise ServiceAuthenticationError("Service credential is missing or invalid")
        if (
            claims["v"] != 1
            or claims["iss"] != self._issuer
            or claims["sub"] != self._expected_subject
            or claims["aud"] != self._audience
            or claims["method"] != method.upper()
            or claims["path"] != path
            or claims["correlation_id"] != correlation_id
            or claims["body_sha256"] != hashlib.sha256(body).hexdigest()
            or not credential_id
            or issued_at > current_time + self._clock_skew_seconds
            or expires_at < current_time
            or expires_at <= issued_at
            or expires_at - issued_at > self._max_ttl_seconds
        ):
            raise ServiceAuthenticationError("Service credential is missing or invalid")

        try:
            claimed = await self._replay_store.claim(
                issuer=str(claims["iss"]),
                subject=str(claims["sub"]),
                audience=str(claims["aud"]),
                credential_id=credential_id,
                expires_at=datetime.fromtimestamp(expires_at, tz=UTC),
                now=datetime.fromtimestamp(current_time, tz=UTC),
            )
        except ReplayStoreError as exc:
            # An undecidable claim is a rejection, never an implicit accept.
            raise ServiceAuthenticationError("Service credential is missing or invalid") from exc
        if not claimed:
            raise ServiceAuthenticationError("Service credential is missing or invalid")
        return ServicePrincipal(
            issuer=str(claims["iss"]),
            subject=str(claims["sub"]),
            audience=str(claims["aud"]),
            credential_id=credential_id,
            correlation_id=correlation_id,
        )
