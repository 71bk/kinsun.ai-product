"""Provider-neutral interfaces for a future Amazon Cognito authenticator.

This module deliberately contains no AWS SDK or JWT implementation. A
production composition root must supply a token verifier configured for the
approved Cognito User Pool and a server-side actor resolver before registering
``CognitoAuthenticator`` with the application.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from fastapi import Request

from app.core.exceptions import AuthenticationError
from app.middleware.auth import ActorContext, Authenticator

_AUTHENTICATION_REQUIRED = "Authentication required"


@dataclass(frozen=True)
class VerifiedCognitoIdentity:
    """Minimal identity returned only after an access token is verified.

    Actor role, tenant, and status are intentionally absent. Those values are
    formal Core state and must be loaded by ``CognitoActorContextResolver``;
    they must not be copied from request data or unverified JWT claims.
    """

    subject: str

    def __post_init__(self) -> None:
        if not self.subject or self.subject != self.subject.strip():
            raise ValueError("Cognito subject must be a non-empty normalized string")


class CognitoTokenVerifier(ABC):
    """Cryptographic Cognito access-token verification interface.

    A production implementation must validate the signature against the
    configured User Pool JWKS as well as issuer, expiration, ``token_use``
    (access), and application client identity. It must never return raw token
    claims as an authenticated ``ActorContext``.
    """

    @abstractmethod
    async def verify_access_token(self, token: str) -> VerifiedCognitoIdentity:
        """Verify one opaque bearer token and return its trusted subject."""
        ...


class CognitoActorContextResolver(ABC):
    """Resolve a verified Cognito subject to formal Core identity state.

    Implementations must use a server-side source of truth to resolve actor ID,
    role, tenant membership, and actor status. Tenant-selection and membership
    policy belong here or in a delegated Core service, never in request headers,
    query parameters, bodies, or unverified claims.
    """

    @abstractmethod
    async def resolve_actor_context(self, identity: VerifiedCognitoIdentity) -> ActorContext:
        """Return the formal actor context for a verified Cognito identity."""
        ...


class CognitoAuthenticator(Authenticator):
    """Authenticate a request through injected Cognito provider boundaries.

    This class is safe to instantiate only when both dependencies have concrete
    production implementations. It normalizes every provider or lookup failure
    to the same public authentication error and never logs or returns the token.
    """

    def __init__(
        self,
        token_verifier: CognitoTokenVerifier,
        actor_context_resolver: CognitoActorContextResolver,
    ) -> None:
        self._token_verifier = token_verifier
        self._actor_context_resolver = actor_context_resolver

    async def authenticate(self, request: Request) -> ActorContext:
        token = _extract_bearer_token(request)

        try:
            identity = await self._token_verifier.verify_access_token(token)
            if not isinstance(identity, VerifiedCognitoIdentity):
                raise TypeError("Token verifier returned an invalid identity type")

            actor_context = await self._actor_context_resolver.resolve_actor_context(identity)
            if not isinstance(actor_context, ActorContext):
                raise TypeError("Actor resolver returned an invalid context type")

            return actor_context
        except Exception:
            pass

        raise AuthenticationError(_AUTHENTICATION_REQUIRED)


def _extract_bearer_token(request: Request) -> str:
    """Extract exactly one well-formed Bearer credential from a request."""
    authorization_values = request.headers.getlist("authorization")
    if len(authorization_values) != 1:
        raise AuthenticationError(_AUTHENTICATION_REQUIRED)

    scheme, separator, token = authorization_values[0].partition(" ")
    if (
        separator != " "
        or scheme.casefold() != "bearer"
        or not token
        or any(character.isspace() for character in token)
    ):
        raise AuthenticationError(_AUTHENTICATION_REQUIRED)

    return token
