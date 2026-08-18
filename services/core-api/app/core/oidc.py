"""Inward-facing contracts for external OIDC identity verification."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class VerifiedLineIdentity:
    """Minimal LINE identity returned after provider-side token verification."""

    subject: str
    email: str | None = None
    display_name: str | None = None

    def __post_init__(self) -> None:
        if (
            not self.subject
            or self.subject != self.subject.strip()
            or len(self.subject) > 255
            or not self.subject.isascii()
            or any(character.isspace() for character in self.subject)
        ):
            raise ValueError("LINE subject must be normalized ASCII of at most 255 characters")
        if self.email is not None and (
            not self.email
            or self.email != self.email.strip()
            or len(self.email) > 254
            or any(character.isspace() for character in self.email)
            or "@" not in self.email
        ):
            raise ValueError("LINE email must be normalized and at most 254 characters")
        if self.display_name is not None:
            normalized = self.display_name.strip()
            if len(normalized) > 120:
                raise ValueError("LINE display name must be at most 120 characters")
            object.__setattr__(self, "display_name", normalized or None)

    @property
    def provider(self) -> str:
        return "LINE"


class LineTokenVerifier(ABC):
    """Verify LINE identity tokens without exposing an adapter implementation."""

    @abstractmethod
    async def verify_id_token(
        self,
        token: str,
        *,
        expected_nonce: str,
    ) -> VerifiedLineIdentity:
        """Verify one LINE ID token and its browser-transaction nonce."""
        ...


@dataclass(frozen=True)
class VerifiedGoogleIdentity:
    """Minimal Google identity returned only after full ID-token verification."""

    subject: str
    email: str | None = None
    email_verified: bool = False
    display_name: str | None = None

    def __post_init__(self) -> None:
        if (
            not self.subject
            or self.subject != self.subject.strip()
            or len(self.subject) > 255
            or not self.subject.isascii()
            or any(character.isspace() for character in self.subject)
        ):
            raise ValueError("Google subject must be normalized ASCII of at most 255 characters")
        if self.email_verified != (self.email is not None):
            raise ValueError("Google email may be retained only when verified")
        if self.email is not None and (
            not self.email or self.email != self.email.strip() or len(self.email) > 254
        ):
            raise ValueError("Google email must be normalized and at most 254 characters")
        if self.display_name is not None:
            normalized_display_name = self.display_name.strip()
            if len(normalized_display_name) > 120:
                raise ValueError("Google display name must be at most 120 characters")
            object.__setattr__(self, "display_name", normalized_display_name or None)

    @property
    def provider(self) -> str:
        return "GOOGLE"


class GoogleTokenVerifier(ABC):
    """Verify Google identity tokens without exposing an adapter implementation."""

    @abstractmethod
    async def verify_id_token(
        self,
        token: str,
        *,
        expected_nonce: str,
    ) -> VerifiedGoogleIdentity:
        """Verify one Google ID token and its browser-transaction nonce."""
        ...
