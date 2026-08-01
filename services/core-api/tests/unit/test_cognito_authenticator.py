"""Tests for the unbound Cognito authentication adapter boundary."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import Request

from app.adapters.auth.cognito import (
    CognitoActorContextResolver,
    CognitoAuthenticator,
    CognitoTokenVerifier,
    VerifiedCognitoIdentity,
)
from app.core.exceptions import AuthenticationError
from app.middleware.auth import ActorContext


def _request(authorization: str | None) -> Request:
    headers = [] if authorization is None else [(b"authorization", authorization.encode())]
    return Request({"type": "http", "headers": headers})


async def test_cognito_authenticator_resolves_formal_actor_context() -> None:
    identity = VerifiedCognitoIdentity(subject="synthetic-subject")
    actor = ActorContext(
        actor_id=uuid4(),
        actor_role="DAYCARE_CARE_WORKER",
        tenant_id=uuid4(),
    )
    verifier = AsyncMock(spec=CognitoTokenVerifier)
    verifier.verify_access_token.return_value = identity
    resolver = AsyncMock(spec=CognitoActorContextResolver)
    resolver.resolve_actor_context.return_value = actor

    result = await CognitoAuthenticator(verifier, resolver).authenticate(
        _request("Bearer synthetic-token")
    )

    assert result == actor
    verifier.verify_access_token.assert_awaited_once_with("synthetic-token")
    resolver.resolve_actor_context.assert_awaited_once_with(identity)


@pytest.mark.parametrize(
    "authorization",
    [None, "", "Basic synthetic-token", "Bearer", "Bearer token with spaces"],
)
async def test_cognito_authenticator_rejects_malformed_bearer_header(
    authorization: str | None,
) -> None:
    verifier = AsyncMock(spec=CognitoTokenVerifier)
    resolver = AsyncMock(spec=CognitoActorContextResolver)

    with pytest.raises(AuthenticationError, match="Authentication required"):
        await CognitoAuthenticator(verifier, resolver).authenticate(_request(authorization))

    verifier.verify_access_token.assert_not_awaited()
    resolver.resolve_actor_context.assert_not_awaited()


async def test_cognito_authenticator_does_not_chain_provider_secret() -> None:
    verifier = AsyncMock(spec=CognitoTokenVerifier)
    verifier.verify_access_token.side_effect = RuntimeError("token=restricted-value")
    resolver = AsyncMock(spec=CognitoActorContextResolver)

    with pytest.raises(AuthenticationError) as exc_info:
        await CognitoAuthenticator(verifier, resolver).authenticate(
            _request("Bearer synthetic-token")
        )

    assert str(exc_info.value) == "Authentication required"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert "restricted-value" not in str(exc_info.value)
    resolver.resolve_actor_context.assert_not_awaited()


async def test_cognito_authenticator_rejects_untrusted_provider_types() -> None:
    verifier = AsyncMock(spec=CognitoTokenVerifier)
    verifier.verify_access_token.return_value = {"sub": "untrusted-claim"}
    resolver = AsyncMock(spec=CognitoActorContextResolver)

    with pytest.raises(AuthenticationError):
        await CognitoAuthenticator(verifier, resolver).authenticate(
            _request("Bearer synthetic-token")
        )

    resolver.resolve_actor_context.assert_not_awaited()
