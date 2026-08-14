"""Opaque challenge tokens and domain-separated Kinsun email digests."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass

_TOKEN_PREFIX = "ke1_"
_TOKEN_PATTERN = re.compile(r"^ke1_[A-Za-z0-9_-]{43}$")
_EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)


@dataclass(frozen=True)
class IssuedKinsunEmailChallengeToken:
    value: str
    digest: str


class KinsunIdentityCodec:
    """Normalize email and derive a non-reversible identity lookup key."""

    def __init__(self, secret: str, key_version: int) -> None:
        if not isinstance(secret, str) or len(secret.encode("utf-8")) < 32:
            raise ValueError("Kinsun identity HMAC secret must contain at least 32 bytes")
        if not isinstance(key_version, int) or key_version < 1:
            raise ValueError("Kinsun identity HMAC key version must be positive")
        self._secret = secret.encode("utf-8")
        self.key_version = key_version

    @staticmethod
    def normalize_email(value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("Email address has an invalid shape")
        normalized = value.strip().casefold()
        if (
            len(normalized) > 254
            or not normalized.isascii()
            or _EMAIL_PATTERN.fullmatch(normalized) is None
        ):
            raise ValueError("Email address has an invalid shape")
        return normalized

    def digest_email(self, normalized_email: str) -> str:
        normalized = self.normalize_email(normalized_email)
        message = f"kinsun:v{self.key_version}:email:{normalized}".encode("ascii")
        return hmac.new(self._secret, message, hashlib.sha256).hexdigest()

class KinsunEmailChallengeCodec:
    """Issue 256-bit challenge tokens and bind OTP digests to each token."""

    def __init__(self, secret: str) -> None:
        if not isinstance(secret, str) or len(secret.encode("utf-8")) < 32:
            raise ValueError("Kinsun challenge HMAC secret must contain at least 32 bytes")
        self._secret = secret.encode("utf-8")

    def issue(self) -> IssuedKinsunEmailChallengeToken:
        random_value = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=")
        value = f"{_TOKEN_PREFIX}{random_value.decode('ascii')}"
        return IssuedKinsunEmailChallengeToken(value=value, digest=self.digest_token(value))

    @staticmethod
    def digest_token(value: str) -> str:
        if not isinstance(value, str) or _TOKEN_PATTERN.fullmatch(value) is None:
            raise ValueError("Invalid Kinsun email challenge token")
        return hashlib.sha256(value.encode("ascii")).hexdigest()

    def digest_code(self, *, token_digest: str, code: str) -> str:
        if not re.fullmatch(r"[0-9]{6}", code):
            raise ValueError("Verification code has an invalid shape")
        if not re.fullmatch(r"[0-9a-f]{64}", token_digest):
            raise ValueError("Challenge digest has an invalid shape")
        message = f"kinsun-email:v1:{token_digest}:code:{code}".encode("ascii")
        return hmac.new(self._secret, message, hashlib.sha256).hexdigest()
