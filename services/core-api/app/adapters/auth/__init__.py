"""Authentication provider adapter boundaries."""

from app.adapters.auth.app_session import DatabaseAppSessionAuthenticator
from app.adapters.auth.cognito import (
    CognitoActorContextResolver,
    CognitoAuthenticator,
    CognitoJwksCache,
    CognitoJwtVerifier,
    CognitoTokenVerifier,
    DatabaseCognitoActorContextResolver,
    VerifiedCognitoIdentity,
)
from app.adapters.auth.google_oidc import (
    GoogleJwksCache,
    GoogleOidcJwtVerifier,
    GoogleTokenVerifier,
    VerifiedGoogleIdentity,
)

__all__ = [
    "DatabaseAppSessionAuthenticator",
    "CognitoActorContextResolver",
    "CognitoAuthenticator",
    "CognitoJwksCache",
    "CognitoJwtVerifier",
    "CognitoTokenVerifier",
    "DatabaseCognitoActorContextResolver",
    "GoogleJwksCache",
    "GoogleOidcJwtVerifier",
    "GoogleTokenVerifier",
    "VerifiedCognitoIdentity",
    "VerifiedGoogleIdentity",
]
