"""Opaque credentials for short-lived pending external identities."""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
from dataclasses import dataclass

_TOKEN_PREFIX = "kp1_"
_TOKEN_PATTERN = re.compile(r"^kp1_[A-Za-z0-9_-]{43}$")
_TOKEN_BYTES = 32


@dataclass(frozen=True)
class IssuedPendingIdentityToken:
    """Raw one-time credential and the digest safe for persistence."""

    value: str
    digest: str


class PendingIdentityTokenCodec:
    """Issue 256-bit pending credentials and derive SHA-256 digests."""

    def issue(self) -> IssuedPendingIdentityToken:
        random_value = base64.urlsafe_b64encode(secrets.token_bytes(_TOKEN_BYTES)).rstrip(b"=")
        value = f"{_TOKEN_PREFIX}{random_value.decode('ascii')}"
        return IssuedPendingIdentityToken(value=value, digest=self.digest(value))

    def digest(self, value: str) -> str:
        if not isinstance(value, str) or _TOKEN_PATTERN.fullmatch(value) is None:
            raise ValueError("Invalid pending identity token")
        return hashlib.sha256(value.encode("ascii")).hexdigest()
