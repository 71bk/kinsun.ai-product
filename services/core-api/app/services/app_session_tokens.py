"""Generation and one-way lookup encoding for opaque App Session tokens."""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
from dataclasses import dataclass

_TOKEN_PREFIX = "ks1_"
_TOKEN_PATTERN = re.compile(r"^ks1_[A-Za-z0-9_-]{43}$")
_TOKEN_BYTES = 32


@dataclass(frozen=True)
class IssuedAppSessionToken:
    """A raw one-time credential and the only representation safe to persist."""

    value: str
    digest: str


class AppSessionTokenCodec:
    """Issue 256-bit random tokens and derive lowercase SHA-256 digests."""

    def issue(self) -> IssuedAppSessionToken:
        random_value = base64.urlsafe_b64encode(secrets.token_bytes(_TOKEN_BYTES)).rstrip(b"=")
        value = f"{_TOKEN_PREFIX}{random_value.decode('ascii')}"
        return IssuedAppSessionToken(value=value, digest=self.digest(value))

    def digest(self, value: str) -> str:
        """Validate a versioned raw token and return its database lookup digest."""
        if not isinstance(value, str) or _TOKEN_PATTERN.fullmatch(value) is None:
            raise ValueError("Invalid App Session token")
        return hashlib.sha256(value.encode("ascii")).hexdigest()
