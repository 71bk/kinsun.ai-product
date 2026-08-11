from __future__ import annotations

import pytest

from app.services.line_identity_codec import LineIdentityCodec


def test_line_identity_codec_is_domain_separated_and_deterministic() -> None:
    codec = LineIdentityCodec("synthetic-line-hmac-secret-at-least-32-bytes", 1)
    subject = "U0123456789abcdef0123456789abcdef"
    nonce = "synthetic-account-link-nonce"

    assert codec.digest_subject(subject) == codec.digest_subject(subject)
    assert codec.digest_subject(subject) != codec.digest_nonce(nonce)
    assert subject not in codec.digest_subject(subject)


def test_line_identity_codec_generates_nonce_and_rejects_weak_inputs() -> None:
    codec = LineIdentityCodec("synthetic-line-hmac-secret-at-least-32-bytes", 1)
    nonce, digest = codec.generate_nonce()

    assert len(nonce) >= 32
    assert digest == codec.digest_nonce(nonce)
    with pytest.raises(ValueError, match="at least 32 bytes"):
        LineIdentityCodec("too-short", 1)
    with pytest.raises(ValueError, match="positive"):
        LineIdentityCodec("synthetic-line-hmac-secret-at-least-32-bytes", 0)
    with pytest.raises(ValueError, match="invalid shape"):
        codec.digest_subject("contains whitespace")
