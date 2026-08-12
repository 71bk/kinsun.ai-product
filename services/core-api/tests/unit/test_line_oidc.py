"""Security tests for LINE Login v2.1 ID-token verification."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.adapters.auth.line_oidc import LineOidcEndpointVerifier
from app.core.exceptions import AuthenticationError

_CHANNEL_ID = "1234567890"
_NONCE = "n" * 43


def _claims(**overrides):
    now = datetime.now(UTC)
    claims = {
        "iss": "https://access.line.me",
        "sub": "U1234567890abcdef",
        "aud": _CHANNEL_ID,
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "iat": int((now - timedelta(seconds=5)).timestamp()),
        "nonce": _NONCE,
        "name": "LINE User",
    }
    claims.update(overrides)
    return claims


def _verifier(claims: dict | None = None, *, status: int = 200) -> LineOidcEndpointVerifier:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.line.me/oauth2/v2.1/verify"
        return httpx.Response(status, content=json.dumps(claims or {}).encode())

    return LineOidcEndpointVerifier(
        channel_id=_CHANNEL_ID,
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.asyncio
async def test_verifies_identity_without_requiring_email() -> None:
    identity = await _verifier(_claims()).verify_id_token(
        "header.payload.signature",
        expected_nonce=_NONCE,
    )

    assert identity.subject == "U1234567890abcdef"
    assert identity.email is None
    assert identity.display_name == "LINE User"


@pytest.mark.asyncio
async def test_normalizes_provider_verified_email() -> None:
    identity = await _verifier(_claims(email="Person@Example.COM")).verify_id_token(
        "header.payload.signature",
        expected_nonce=_NONCE,
    )

    assert identity.email == "person@example.com"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "claims",
    [
        _claims(iss="https://attacker.invalid"),
        _claims(aud="different-channel"),
        _claims(nonce="different-nonce"),
        _claims(exp=1),
    ],
)
async def test_rejects_invalid_claims(claims: dict) -> None:
    with pytest.raises(AuthenticationError, match="Authentication required"):
        await _verifier(claims).verify_id_token(
            "header.payload.signature",
            expected_nonce=_NONCE,
        )


@pytest.mark.asyncio
async def test_rejects_provider_verification_failure() -> None:
    with pytest.raises(AuthenticationError, match="Authentication required"):
        await _verifier(status=400).verify_id_token(
            "header.payload.signature",
            expected_nonce=_NONCE,
        )
