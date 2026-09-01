"""Credential separation for staff-assisted tablet handoff."""

from __future__ import annotations

import hashlib

import pytest

from app.services.assisted_session_tokens import AssistedSessionTokenCodec


def test_pairing_and_session_credentials_use_distinct_prefixes_and_digests() -> None:
    codec = AssistedSessionTokenCodec()

    pairing = codec.issue_pairing()
    session = codec.issue_session()

    assert pairing.value.startswith("ep1_")
    assert session.value.startswith("es1_")
    assert pairing.digest == hashlib.sha256(pairing.value.encode("ascii")).hexdigest()
    assert session.digest == hashlib.sha256(session.value.encode("ascii")).hexdigest()
    assert codec.digest_pairing(pairing.value) == pairing.digest
    assert codec.digest_session(session.value) == session.digest


@pytest.mark.parametrize(
    ("method_name", "value"),
    [
        ("digest_pairing", "es1_" + "a" * 43),
        ("digest_session", "ep1_" + "a" * 43),
        ("digest_pairing", "ep1_short"),
        ("digest_session", ""),
        ("digest_session", "ks1_" + "a" * 43),
    ],
)
def test_credentials_reject_wrong_type_or_shape(method_name: str, value: str) -> None:
    codec = AssistedSessionTokenCodec()

    with pytest.raises(ValueError, match="Invalid assisted Elder Session token"):
        getattr(codec, method_name)(value)
