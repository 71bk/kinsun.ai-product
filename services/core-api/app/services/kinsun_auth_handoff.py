"""Authentication for the private BFF-to-Core Kinsun auth boundary."""

from __future__ import annotations

import hmac

from app.core.exceptions import AuthenticationError


class KinsunAuthHandoffAuthenticator:
    def __init__(self, secret: str) -> None:
        if (
            not isinstance(secret, str)
            or len(secret.encode("utf-8")) < 32
            or len(secret) > 512
            or secret != secret.strip()
            or any(character.isspace() for character in secret)
        ):
            raise ValueError("Kinsun auth handoff secret must contain at least 32 bytes")
        self._secret = secret

    def authenticate(self, authorization_values: list[str]) -> None:
        if len(authorization_values) != 1:
            raise AuthenticationError("Authentication required")
        scheme, separator, credential = authorization_values[0].partition(" ")
        if (
            separator != " "
            or scheme.casefold() != "bearer"
            or not credential
            or any(character.isspace() for character in credential)
            or not hmac.compare_digest(credential, self._secret)
        ):
            raise AuthenticationError("Authentication required")
