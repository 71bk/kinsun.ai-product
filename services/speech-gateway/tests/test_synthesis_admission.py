from __future__ import annotations

import pytest

from speech_gateway.synthesis_admission import (
    SynthesisConcurrencyExceeded,
    SynthesisConcurrencyLimiter,
)


@pytest.mark.asyncio
async def test_concurrency_limit_rejects_excess_and_releases_after_failure() -> None:
    limiter = SynthesisConcurrencyLimiter(1)

    with pytest.raises(RuntimeError, match="provider failed"):
        async with limiter.slot():
            with pytest.raises(SynthesisConcurrencyExceeded):
                async with limiter.slot():
                    pass
            raise RuntimeError("provider failed")

    async with limiter.slot():
        pass
