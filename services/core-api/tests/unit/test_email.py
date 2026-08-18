"""Tests for validation-free email text normalization."""

import pytest

from app.core.email import normalize_email_text


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("  User.Name@Example.COM ", "user.name@example.com"),
        (" STRASSE@EXAMPLE.COM ", "strasse@example.com"),
        ("  not an email  ", "not an email"),
    ],
)
def test_normalize_email_text_only_trims_and_casefolds(value: str, expected: str) -> None:
    assert normalize_email_text(value) == expected
