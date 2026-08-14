from __future__ import annotations

import pytest

from app.services.kinsun_identity_codec import (
    KinsunEmailChallengeCodec,
    KinsunIdentityCodec,
)

_IDENTITY_SECRET = "kinsun-identity-test-secret-material-at-least-32-bytes"
_CHALLENGE_SECRET = "kinsun-challenge-test-secret-material-at-least-32-bytes"


def test_email_normalization_and_digest_are_stable() -> None:
    codec = KinsunIdentityCodec(_IDENTITY_SECRET, 1)

    normalized = codec.normalize_email("  User.Name@Example.COM ")

    assert normalized == "user.name@example.com"
    assert codec.digest_email(normalized) == codec.digest_email("USER.NAME@example.com")
    assert len(codec.digest_email(normalized)) == 64


@pytest.mark.parametrize(
    "value",
    ["", "missing-at.example.com", "name@localhost", "a b@example.com", "使用者@example.com"],
)
def test_email_normalization_rejects_unsafe_shapes(value: str) -> None:
    with pytest.raises(ValueError):
        KinsunIdentityCodec(_IDENTITY_SECRET, 1).normalize_email(value)


def test_challenge_token_and_code_are_bound() -> None:
    codec = KinsunEmailChallengeCodec(_CHALLENGE_SECRET)

    first = codec.issue()
    second = codec.issue()

    assert first.value.startswith("ke1_")
    assert len(first.value) == 47
    assert codec.digest_token(first.value) == first.digest
    assert codec.digest_code(token_digest=first.digest, code="246810") != codec.digest_code(
        token_digest=second.digest,
        code="246810",
    )


@pytest.mark.parametrize("value", ["12345", "1234567", "１２３４５６", "abcdef"])
def test_challenge_code_requires_six_ascii_digits(value: str) -> None:
    codec = KinsunEmailChallengeCodec(_CHALLENGE_SECRET)
    with pytest.raises(ValueError):
        codec.digest_code(token_digest="a" * 64, code=value)
