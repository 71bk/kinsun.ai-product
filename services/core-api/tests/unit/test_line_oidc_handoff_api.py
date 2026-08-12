"""Rollout-gate and schema contracts for private LINE handoff endpoints."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.line_oidc_handoff import router
from app.core.config import get_settings
from app.main import app
from app.schemas.line_oidc_handoff import (
    ConfirmLineAccountMergeRequest,
    LineOidcHandoffRequest,
    LinkLineIdentityRequest,
)


def test_internal_line_handoff_mount_matches_runtime_gate() -> None:
    private_paths = {route.path for route in router.routes}
    runtime_paths = {route.path for route in app.routes}

    assert "/api/v1/internal/auth/line/handoff" in private_paths
    assert "/api/v1/internal/auth/line/status" in private_paths
    assert "/api/v1/internal/auth/line/link" in private_paths
    assert "/api/v1/internal/auth/line/merge/confirm" in private_paths
    assert (
        "/api/v1/internal/auth/line/handoff" in runtime_paths
    ) is get_settings().line_oidc_handoff_enabled


def test_line_handoff_request_is_strict() -> None:
    request = LineOidcHandoffRequest(
        id_token="header.payload.signature",
        expected_nonce="n" * 32,
        intent="ELDER",
    )
    assert request.intent == "ELDER"

    with pytest.raises(ValidationError):
        LineOidcHandoffRequest(
            id_token="header. payload.signature",
            expected_nonce="n" * 32,
            intent="ELDER",
        )
    with pytest.raises(ValidationError):
        LineOidcHandoffRequest(
            id_token="header.payload.signature",
            expected_nonce="short",
            intent="ELDER",
        )


def test_line_link_and_merge_requests_reject_browser_session_or_raw_subject() -> None:
    request = LinkLineIdentityRequest(
        id_token="header.payload.signature",
        expected_nonce="n" * 32,
    )
    assert request.expected_nonce == "n" * 32

    with pytest.raises(ValidationError):
        LinkLineIdentityRequest.model_validate(
            {
                "id_token": "header.payload.signature",
                "expected_nonce": "n" * 32,
                "session_token": "ks1_" + "a" * 43,
            }
        )
    with pytest.raises(ValidationError):
        ConfirmLineAccountMergeRequest(merge_token="U1234567890abcdef")
