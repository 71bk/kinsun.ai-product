from __future__ import annotations

import pytest

from app.core.exceptions import AuthenticationError
from app.services.kinsun_auth_handoff import KinsunAuthHandoffAuthenticator

_SECRET = "kinsun-bff-handoff-test-secret-material-at-least-32-bytes"


def test_accepts_exact_single_bearer() -> None:
    KinsunAuthHandoffAuthenticator(_SECRET).authenticate([f"Bearer {_SECRET}"])


@pytest.mark.parametrize(
    "values",
    [[], [f"Bearer {_SECRET}", f"Bearer {_SECRET}"], ["Basic value"], ["Bearer wrong"]],
)
def test_rejects_missing_ambiguous_or_wrong_authorization(values: list[str]) -> None:
    with pytest.raises(AuthenticationError):
        KinsunAuthHandoffAuthenticator(_SECRET).authenticate(values)


def test_rejects_short_configuration_secret() -> None:
    with pytest.raises(ValueError):
        KinsunAuthHandoffAuthenticator("short")
