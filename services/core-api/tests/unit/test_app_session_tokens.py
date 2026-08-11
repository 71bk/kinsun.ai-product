"""Unit tests for opaque App Session token generation and lookup digests."""

from __future__ import annotations

import hashlib
import re

import pytest

from app.services.app_session_tokens import AppSessionTokenCodec


def test_issue_returns_versioned_256_bit_random_credential_and_sha256_digest() -> None:
    issued = AppSessionTokenCodec().issue()

    assert re.fullmatch(r"ks1_[A-Za-z0-9_-]{43}", issued.value)
    assert issued.digest == hashlib.sha256(issued.value.encode("ascii")).hexdigest()
    assert re.fullmatch(r"[0-9a-f]{64}", issued.digest)


def test_two_issued_tokens_are_distinct() -> None:
    codec = AppSessionTokenCodec()
    first = codec.issue()
    second = codec.issue()

    assert first.value != second.value
    assert first.digest != second.digest


@pytest.mark.parametrize(
    "value",
    [
        "",
        "ks1_short",
        "ks2_" + "A" * 43,
        "ks1_" + "A" * 42,
        "ks1_" + "A" * 44,
        "ks1_" + "A" * 42 + "=",
        "ks1_" + "A" * 42 + ".",
        " ks1_" + "A" * 43,
    ],
)
def test_digest_rejects_noncanonical_token_shape(value: str) -> None:
    with pytest.raises(ValueError, match="Invalid App Session token"):
        AppSessionTokenCodec().digest(value)
