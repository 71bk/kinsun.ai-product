"""Tests for the dedicated BFF handoff credential."""

from __future__ import annotations

import pytest

from app.core.exceptions import AuthenticationError
from app.services.google_oidc_handoff_auth import GoogleOidcHandoffAuthenticator

_SECRET = "dedicated-google-handoff-test-secret-32-bytes"


def test_accepts_exactly_one_matching_bearer_value() -> None:
    GoogleOidcHandoffAuthenticator(_SECRET).authenticate([f"Bearer {_SECRET}"])


@pytest.mark.parametrize(
    "values",
    [
        [],
        [f"Bearer {_SECRET}", f"Bearer {_SECRET}"],
        ["Basic credentials"],
        ["Bearer wrong-secret"],
        [f"Bearer {_SECRET} "],
    ],
)
def test_rejects_missing_ambiguous_or_invalid_credentials(values: list[str]) -> None:
    with pytest.raises(AuthenticationError, match="Authentication required"):
        GoogleOidcHandoffAuthenticator(_SECRET).authenticate(values)


def test_requires_strong_configuration_secret() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        GoogleOidcHandoffAuthenticator("short")
