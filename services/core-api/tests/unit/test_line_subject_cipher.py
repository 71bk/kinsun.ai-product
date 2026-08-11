from __future__ import annotations

import pytest

from app.services.line_subject_cipher import LineSubjectCipher


def test_line_subject_cipher_round_trip_is_randomized() -> None:
    cipher = LineSubjectCipher("synthetic-line-encryption-secret-at-least-32-bytes")
    subject = "U0123456789abcdef0123456789abcdef"

    first = cipher.encrypt(subject)
    second = cipher.encrypt(subject)

    assert first != second
    assert subject not in first
    assert cipher.decrypt(first) == subject
    assert cipher.decrypt(second) == subject


def test_line_subject_cipher_rejects_wrong_key_and_malformed_values() -> None:
    first = LineSubjectCipher("synthetic-line-encryption-secret-at-least-32-bytes")
    second = LineSubjectCipher("another-independent-secret-at-least-32-bytes")
    encrypted = first.encrypt("U0123456789abcdef0123456789abcdef")

    with pytest.raises(ValueError, match="ciphertext"):
        second.decrypt(encrypted)
    with pytest.raises(ValueError, match="invalid shape"):
        first.encrypt("not a valid LINE subject")
    with pytest.raises(ValueError, match="at least 32 bytes"):
        LineSubjectCipher("too-short")
