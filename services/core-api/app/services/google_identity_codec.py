"""Domain-separated keyed digests for verified Google subjects."""

from __future__ import annotations

import hashlib
import hmac


class GoogleIdentityCodec:
    """Digest Google subjects before persistence or database lookup."""

    def __init__(self, secret: str, key_version: int) -> None:
        if not isinstance(secret, str) or len(secret.encode("utf-8")) < 32:
            raise ValueError("Google identity HMAC secret must contain at least 32 bytes")
        if not isinstance(key_version, int) or key_version < 1:
            raise ValueError("Google identity HMAC key version must be positive")
        self._secret = secret.encode("utf-8")
        self.key_version = key_version

    def digest_subject(self, subject: str) -> str:
        if (
            not isinstance(subject, str)
            or not subject
            or len(subject) > 255
            or subject != subject.strip()
            or not subject.isascii()
            or any(character.isspace() for character in subject)
        ):
            raise ValueError("Google subject has an invalid shape")
        message = f"google:v{self.key_version}:subject:{subject}".encode("ascii")
        return hmac.new(self._secret, message, hashlib.sha256).hexdigest()
