"""Per-process provider concurrency boundary for TTS calls."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class SynthesisConcurrencyExceeded(Exception):
    pass


class SynthesisConcurrencyLimiter:
    """Reject excess work immediately and always release acquired capacity."""

    def __init__(self, limit: int) -> None:
        if limit < 1:
            raise ValueError("TTS concurrency limit must be positive")
        self._limit = limit
        self._active = 0
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        async with self._lock:
            if self._active >= self._limit:
                raise SynthesisConcurrencyExceeded
            self._active += 1
        try:
            yield
        finally:
            async with self._lock:
                self._active -= 1
