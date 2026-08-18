"""Authentication value types and application-facing port."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol


class AuthorizationHeaders(Protocol):
    """Minimal header collection needed by an HTTP authenticator."""

    def getlist(self, key: str) -> list[str]:
        """Return every value supplied for one header name."""
        ...


class AuthenticationRequest(Protocol):
    """Framework-neutral request shape accepted by authentication adapters."""

    @property
    def headers(self) -> AuthorizationHeaders:
        """Expose request headers without depending on FastAPI or Starlette."""
        ...


@dataclass(frozen=True)
class ActorContext:
    """Immutable identity context derived from trusted authentication state."""

    actor_id: uuid.UUID
    actor_role: str
    tenant_id: uuid.UUID
    status: str = "ACTIVE"


class Authenticator(ABC):
    """Port used by the HTTP authentication dependency."""

    @abstractmethod
    async def authenticate(self, request: AuthenticationRequest) -> ActorContext:
        """Validate request credentials and return a trusted actor context."""
        ...
