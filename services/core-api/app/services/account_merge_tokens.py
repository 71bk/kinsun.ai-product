"""Opaque confirmation credentials for bounded account consolidation."""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
from dataclasses import dataclass

_TOKEN_PREFIX = "km1_"
_TOKEN_PATTERN = re.compile(r"^km1_[A-Za-z0-9_-]{43}$")


@dataclass(frozen=True)
class IssuedAccountMergeToken:
    value: str
    digest: str


class AccountMergeTokenCodec:
    """Issue a single-use 256-bit merge confirmation credential."""

    def issue(self) -> IssuedAccountMergeToken:
        random_value = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=")
        value = f"{_TOKEN_PREFIX}{random_value.decode('ascii')}"
        return IssuedAccountMergeToken(value=value, digest=self.digest(value))

    def digest(self, value: str) -> str:
        if not isinstance(value, str) or _TOKEN_PATTERN.fullmatch(value) is None:
            raise ValueError("Invalid account merge token")
        return hashlib.sha256(value.encode("ascii")).hexdigest()
