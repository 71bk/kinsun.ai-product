"""Executable request and error-envelope checks for Kinsun native auth."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.api.responses import authentication_rejected
from app.schemas.kinsun_email_auth import (
    CompleteKinsunEmailAuthRequest,
    PasswordLoginRequest,
    StartKinsunEmailAuthRequest,
)


def test_start_request_normalizes_only_a_valid_ascii_email() -> None:
    request = StartKinsunEmailAuthRequest(
        email=" Synthetic.Elder@Example.COM ",
        intent="ELDER",
    )

    assert request.email == "synthetic.elder@example.com"

    with pytest.raises(ValidationError):
        StartKinsunEmailAuthRequest(email="not-an-email", intent="ELDER")


def test_password_login_reuses_the_same_email_boundary() -> None:
    with pytest.raises(ValidationError):
        PasswordLoginRequest(email="elder@localhost", password="synthetic-password")


def test_completion_rejects_non_ascii_verification_digits() -> None:
    with pytest.raises(ValidationError):
        CompleteKinsunEmailAuthRequest(
            challenge_token="ke1_" + "a" * 43,
            verification_code="１２３４５６",
            password="synthetic-password",
        )


def test_authentication_failure_uses_the_canonical_error_envelope() -> None:
    response = authentication_rejected()
    payload = json.loads(response.body)

    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert set(payload) == {"error"}
    assert payload["error"] == {
        "code": "authentication_required",
        "message": "Authentication required.",
        "correlation_id": payload["error"]["correlation_id"],
        "reason_code": "AUTHENTICATION_FAILED",
        "retryable": False,
        "details": None,
    }
