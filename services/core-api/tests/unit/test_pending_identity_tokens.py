"""Tests for one-time pending identity credentials."""

from __future__ import annotations

import pytest

from app.services.pending_identity_tokens import PendingIdentityTokenCodec


def test_issue_returns_random_versioned_token_and_digest() -> None:
    codec = PendingIdentityTokenCodec()

    first = codec.issue()
    second = codec.issue()

    assert first.value.startswith("kp1_")
    assert len(first.value) == 47
    assert len(first.digest) == 64
    assert first.digest == codec.digest(first.value)
    assert first.value != second.value
    assert first.digest != second.digest


@pytest.mark.parametrize(
    "value",
    ["", "ks1_" + "a" * 43, "kp1_short", "kp1_" + "!" * 43, " kp1_" + "a" * 43],
)
def test_digest_rejects_malformed_tokens(value: str) -> None:
    with pytest.raises(ValueError, match="Invalid pending identity token"):
        PendingIdentityTokenCodec().digest(value)
