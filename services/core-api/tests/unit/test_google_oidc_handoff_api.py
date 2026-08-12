"""Rollout-gate contracts for the private Google handoff endpoint."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.google_oidc_handoff import router
from app.core.config import get_settings
from app.main import app
from app.schemas.google_oidc_handoff import GoogleOidcHandoffRequest


def test_internal_handoff_router_mount_matches_runtime_gate() -> None:
    private_paths = {route.path for route in router.routes}
    runtime_paths = {route.path for route in app.routes}

    assert "/api/v1/internal/auth/google/handoff" in private_paths
    assert (
        "/api/v1/internal/auth/google/handoff" in runtime_paths
    ) is get_settings().google_oidc_handoff_enabled


def test_handoff_request_accepts_only_bounded_ascii_credentials_and_known_intent() -> None:
    request = GoogleOidcHandoffRequest(
        id_token="header.payload.signature",
        expected_nonce="n" * 32,
        intent="ELDER",
    )

    assert request.intent == "ELDER"

    with pytest.raises(ValidationError):
        GoogleOidcHandoffRequest(
            id_token="header. payload.signature",
            expected_nonce="n" * 32,
            intent="ELDER",
        )
    with pytest.raises(ValidationError):
        GoogleOidcHandoffRequest(
            id_token="header.payload.signature",
            expected_nonce="short",
            intent="ELDER",
        )
    with pytest.raises(ValidationError):
        GoogleOidcHandoffRequest(
            id_token="header.payload.signature",
            expected_nonce="n" * 32,
            intent="ADMIN",
        )
