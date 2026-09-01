"""One-way credential encoding for staff-assisted tablet handoff."""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
from dataclasses import dataclass

_PAIRING_PREFIX = "ep1_"
_SESSION_PREFIX = "es1_"
_PAIRING_PATTERN = re.compile(r"^ep1_[A-Za-z0-9_-]{43}$")
_SESSION_PATTERN = re.compile(r"^es1_[A-Za-z0-9_-]{43}$")
_TOKEN_BYTES = 32
_INVALID_TOKEN = "Invalid assisted Elder Session token"


@dataclass(frozen=True)
class IssuedAssistedSessionToken:
    """A raw one-time credential and the digest safe to persist."""

    value: str
    digest: str


class AssistedSessionTokenCodec:
    """Keep pairing and active-session credentials cryptographically separate."""

    def issue_pairing(self) -> IssuedAssistedSessionToken:
        return self._issue(_PAIRING_PREFIX, self.digest_pairing)

    def issue_session(self) -> IssuedAssistedSessionToken:
        return self._issue(_SESSION_PREFIX, self.digest_session)

    def digest_pairing(self, value: str) -> str:
        return self._digest(value, _PAIRING_PATTERN)

    def digest_session(self, value: str) -> str:
        return self._digest(value, _SESSION_PATTERN)

    @staticmethod
    def _issue(prefix: str, digest) -> IssuedAssistedSessionToken:
        random_value = base64.urlsafe_b64encode(secrets.token_bytes(_TOKEN_BYTES)).rstrip(b"=")
        value = f"{prefix}{random_value.decode('ascii')}"
        return IssuedAssistedSessionToken(value=value, digest=digest(value))

    @staticmethod
    def _digest(value: str, pattern: re.Pattern[str]) -> str:
        if not isinstance(value, str) or pattern.fullmatch(value) is None:
            raise ValueError(_INVALID_TOKEN)
        return hashlib.sha256(value.encode("ascii")).hexdigest()
