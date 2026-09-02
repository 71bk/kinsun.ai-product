"""Replay-store contract for single-use service credentials.

A verifier that keeps used credential IDs in process memory only protects the
replica that saw the first request.  ADR 0009 requires the claim to be atomic
across every replica before a multi-replica deployment, so verification depends
on this contract rather than on a private dictionary.

Kept free of database imports: credential verification is pure crypto plus one
claim, and only the durable implementation needs a driver.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


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


class InMemoryReplayStore:
    """Process-local store for unit tests and single-process local runs.

    ``durable`` is False so wiring code can refuse to serve traffic with it.
    """

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
