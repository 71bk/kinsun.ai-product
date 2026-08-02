"""Domain-separated keyed digests for ephemeral LINE identifiers."""

from __future__ import annotations

import hashlib
import hmac
import secrets


class LineIdentityCodec:
    """Generate account-link nonces and digest LINE values before persistence."""

    def __init__(self, secret: str, key_version: int) -> None:
        if not isinstance(secret, str) or len(secret.encode("utf-8")) < 32:
            raise ValueError("LINE identity HMAC secret must contain at least 32 bytes")
        if not isinstance(key_version, int) or key_version < 1:
            raise ValueError("LINE identity HMAC key version must be positive")
        self._secret = secret.encode("utf-8")
        self.key_version = key_version

    def generate_nonce(self) -> tuple[str, str]:
        """Return a 256-bit URL-safe nonce and its persistence-safe digest."""
        nonce = secrets.token_urlsafe(32)
        return nonce, self.digest_nonce(nonce)

    def digest_subject(self, value: str) -> str:
        self._validate(value, field="LINE subject", minimum=1, maximum=255)
        return self._digest("subject", value)

    def digest_nonce(self, value: str) -> str:
        self._validate(value, field="LINE account-link nonce", minimum=10, maximum=255)
        return self._digest("nonce", value)

    @staticmethod
    def _validate(value: str, *, field: str, minimum: int, maximum: int) -> None:
        if not isinstance(value, str) or not minimum <= len(value) <= maximum:
            raise ValueError(f"{field} has an invalid shape")
        if any(character.isspace() for character in value):
            raise ValueError(f"{field} has an invalid shape")

    def _digest(self, purpose: str, value: str) -> str:
        message = f"line:v{self.key_version}:{purpose}:{value}".encode()
        return hmac.new(self._secret, message, hashlib.sha256).hexdigest()
