"""Tests for persistence-safe Google subject digests."""

from __future__ import annotations

import pytest

from app.services.google_identity_codec import GoogleIdentityCodec


def test_digest_is_deterministic_versioned_and_domain_separated() -> None:
    secret = "google-identity-test-secret-material-32-bytes"
    first = GoogleIdentityCodec(secret, 1)
    second = GoogleIdentityCodec(secret, 2)

    digest = first.digest_subject("google-subject-123")

    assert len(digest) == 64
    assert digest == first.digest_subject("google-subject-123")
    assert digest != first.digest_subject("google-subject-456")
    assert digest != second.digest_subject("google-subject-123")
    assert "google-subject-123" not in digest


@pytest.mark.parametrize("subject", ["", " leading", "trailing ", "has space", "中"])
def test_rejects_malformed_subjects(subject: str) -> None:
    codec = GoogleIdentityCodec("google-identity-test-secret-material-32-bytes", 1)

    with pytest.raises(ValueError, match="invalid shape"):
        codec.digest_subject(subject)


def test_requires_independent_strong_secret_and_positive_version() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        GoogleIdentityCodec("short", 1)
    with pytest.raises(ValueError, match="positive"):
        GoogleIdentityCodec("google-identity-test-secret-material-32-bytes", 0)
