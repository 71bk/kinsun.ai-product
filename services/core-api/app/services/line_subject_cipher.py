"""Authenticated encryption for scheduled LINE push destinations."""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_AAD = b"kinsun.ai:line-subject:v1"


class LineSubjectCipher:
    """Encrypt raw LINE user IDs; only ciphertext is persisted."""

    def __init__(self, secret: str) -> None:
        if len(secret.encode("utf-8")) < 32:
            raise ValueError("LINE subject encryption secret must contain at least 32 bytes")
        self._key = hashlib.sha256(secret.encode("utf-8")).digest()

    def encrypt(self, line_user_id: str) -> str:
        if not line_user_id or len(line_user_id) > 128 or not line_user_id.isalnum():
            raise ValueError("LINE user ID has an invalid shape")
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._key).encrypt(nonce, line_user_id.encode("utf-8"), _AAD)
        return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")

    def decrypt(self, encrypted_subject: str) -> str:
        try:
            payload = base64.b64decode(encrypted_subject, altchars=b"-_", validate=True)
            if len(payload) < 29:
                raise ValueError
            plaintext = AESGCM(self._key).decrypt(payload[:12], payload[12:], _AAD)
            value = plaintext.decode("utf-8")
        except Exception as exc:  # cryptography deliberately has several failure types
            raise ValueError("LINE subject ciphertext is invalid") from exc
        if not value or len(value) > 128 or not value.isalnum():
            raise ValueError("LINE subject ciphertext is invalid")
        return value
