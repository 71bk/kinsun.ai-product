"""Replay-store contract for single-use service credentials.

Process-local state only protects the replica that saw the first request, so a
signed Core request replayed against a second replica would be accepted twice.
Verification therefore depends on this contract rather than on a private
dictionary, and the app chooses a durable implementation wherever more than one
replica can exist.

Kept free of database imports: credential verification is pure crypto plus one
claim, and only the durable implementation needs a driver.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class ReplayStoreError(RuntimeError):
    """Raised when the replay claim itself could not be decided."""


class ReplayStore(Protocol):
    """Claim a credential ID exactly once for one audience."""

    #: False for stores whose state cannot be seen by another replica.
    durable: bool

    async def claim(
        self,
        *,
        issuer: str,
        subject: str,
        audience: str,
        credential_id: str,
        expires_at: datetime,
        now: datetime,
    ) -> bool:
        """Return True when this caller won the claim, False on replay."""

    async def aclose(self) -> None:
        """Release any connection resources held by the store."""


class InMemoryReplayStore:
    """Process-local store for tests and single-process local runs."""

    durable = False

    def __init__(self) -> None:
        self._claimed: dict[tuple[str, str], datetime] = {}

    async def claim(
        self,
        *,
        issuer: str,
        subject: str,
        audience: str,
        credential_id: str,
        expires_at: datetime,
        now: datetime,
    ) -> bool:
        del issuer, subject
        self._claimed = {key: expiry for key, expiry in self._claimed.items() if expiry >= now}
        key = (audience, credential_id)
        if key in self._claimed:
            return False
        self._claimed[key] = expires_at
        return True

    async def aclose(self) -> None:
        self._claimed.clear()
