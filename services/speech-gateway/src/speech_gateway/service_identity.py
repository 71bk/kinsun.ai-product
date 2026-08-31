"""Short-lived request-bound signer for Speech Gateway to Core calls."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass

SERVICE_CREDENTIAL_HEADER = "X-Kinsun-Service-Credential"
_TOKEN_PREFIX = "ksvc1"


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


@dataclass(frozen=True, slots=True)
class ServiceCredentialSigner:
    secret: str
    issuer: str = "kinsun-local"
    subject: str = "speech-gateway"
    audience: str = "core-api"
    ttl_seconds: int = 30

    def __post_init__(self) -> None:
        if len(self.secret.encode("utf-8")) < 32:
            raise ValueError("Service identity secret must contain at least 32 bytes")
        if not 1 <= self.ttl_seconds <= 60:
            raise ValueError("Service credential TTL must be between 1 and 60 seconds")

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
        encoded_claims = _b64url(_canonical_json_bytes(claims))
        signed = f"{_TOKEN_PREFIX}.{encoded_claims}".encode("ascii")
        signature = hmac.new(self.secret.encode("utf-8"), signed, hashlib.sha256).digest()
        return f"{signed.decode('ascii')}.{_b64url(signature)}"
