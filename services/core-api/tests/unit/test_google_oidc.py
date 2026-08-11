"""Security tests for the unbound Google OpenID Connect verifier."""

from __future__ import annotations

import json
import logging
from collections import deque
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.adapters.auth.google_oidc import (
    GoogleJwksCache,
    GoogleOidcJwtVerifier,
    VerifiedGoogleIdentity,
)
from app.core.exceptions import AuthenticationError

_CLIENT_ID = "google-web-client.apps.googleusercontent.com"
_NONCE = "nonce_" + "a" * 37


class _StaticJwksCache:
    def __init__(self, key: dict) -> None:
        self._key = key
        self.calls: list[bool] = []

    async def get(self, kid: str, *, force_refresh: bool = False) -> dict:
        assert kid == "test-key"
        self.calls.append(force_refresh)
        return self._key


class _RotatingJwksCache:
    def __init__(self, stale_key: dict, current_key: dict) -> None:
        self._stale_key = stale_key
        self._current_key = current_key
        self.calls: list[bool] = []

    async def get(self, kid: str, *, force_refresh: bool = False) -> dict:
        assert kid == "test-key"
        self.calls.append(force_refresh)
        return self._current_key if force_refresh else self._stale_key


def _key_pair(*, kid: str = "test-key") -> tuple[object, dict]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({"kid": kid, "alg": "RS256", "use": "sig"})
    return private_key, jwk


def _claims(**overrides: object) -> dict:
    now = datetime.now(UTC)
    claims: dict = {
        "iss": "https://accounts.google.com",
        "aud": _CLIENT_ID,
        "sub": "107691503500061507151",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "nonce": _NONCE,
        "email": "elder@example.test",
        "email_verified": True,
        "name": "  Lin Elder  ",
    }
    claims.update(overrides)
    return claims


def _signed_token(
    *,
    claims: dict | None = None,
    private_key: object | None = None,
    headers: dict | None = None,
) -> tuple[str, dict]:
    signing_key, jwk = _key_pair() if private_key is None else (private_key, None)
    token = jwt.encode(
        claims or _claims(),
        signing_key,
        algorithm="RS256",
        headers={"kid": "test-key"} if headers is None else headers,
    )
    if jwk is None:
        public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key()))
        public_jwk.update({"kid": "test-key", "alg": "RS256", "use": "sig"})
        jwk = public_jwk
    return token, jwk


def _verifier(cache) -> GoogleOidcJwtVerifier:
    return GoogleOidcJwtVerifier(
        client_id=_CLIENT_ID,
        jwks_cache=cache,
    )


@pytest.mark.asyncio
async def test_valid_id_token_returns_only_bounded_verified_identity() -> None:
    token, jwk = _signed_token()
    cache = _StaticJwksCache(jwk)

    identity = await _verifier(cache).verify_id_token(token, expected_nonce=_NONCE)

    assert identity == VerifiedGoogleIdentity(
        subject="107691503500061507151",
        email="elder@example.test",
        email_verified=True,
        display_name="Lin Elder",
    )
    assert identity.provider == "GOOGLE"
    assert cache.calls == [False]
    assert not hasattr(identity, "claims")
    assert not hasattr(identity, "token")


@pytest.mark.asyncio
async def test_legacy_issuer_and_signed_string_email_verification_are_supported() -> None:
    token, jwk = _signed_token(
        claims=_claims(
            iss="accounts.google.com",
            email_verified="true",
        )
    )

    identity = await _verifier(_StaticJwksCache(jwk)).verify_id_token(
        token,
        expected_nonce=_NONCE,
    )

    assert identity.email == "elder@example.test"
    assert identity.email_verified is True


@pytest.mark.asyncio
@pytest.mark.parametrize("verified_claim", [None, False, "false"])
async def test_unverified_or_absent_email_is_not_retained(verified_claim: object) -> None:
    token, jwk = _signed_token(claims=_claims(email_verified=verified_claim))

    identity = await _verifier(_StaticJwksCache(jwk)).verify_id_token(
        token,
        expected_nonce=_NONCE,
    )

    assert identity.email is None
    assert identity.email_verified is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "claim_overrides",
    [
        {"iss": "https://issuer.example.test"},
        {"aud": "another-client.apps.googleusercontent.com"},
        {"aud": [_CLIENT_ID]},
        {"azp": "another-client.apps.googleusercontent.com"},
        {"nonce": "different_" + "b" * 34},
        {"nonce": "驗證值"},
        {"sub": " subject-with-space"},
        {"sub": "使用者"},
        {"sub": "a" * 256},
    ],
)
async def test_provider_specific_claim_mismatches_fail_closed(claim_overrides: dict) -> None:
    token, jwk = _signed_token(claims=_claims(**claim_overrides))

    with pytest.raises(AuthenticationError, match="^Authentication required$"):
        await _verifier(_StaticJwksCache(jwk)).verify_id_token(
            token,
            expected_nonce=_NONCE,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "claim_overrides",
    [
        {"exp": int((datetime.now(UTC) - timedelta(seconds=1)).timestamp())},
        {"iat": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp())},
        {"iat": "not-an-integer"},
        {
            "iat": int((datetime.now(UTC) + timedelta(minutes=4)).timestamp()),
            "exp": int((datetime.now(UTC) + timedelta(minutes=3)).timestamp()),
        },
    ],
)
async def test_invalid_token_time_claims_fail_closed(claim_overrides: dict) -> None:
    token, jwk = _signed_token(claims=_claims(**claim_overrides))

    with pytest.raises(AuthenticationError, match="Authentication required"):
        await _verifier(_StaticJwksCache(jwk)).verify_id_token(
            token,
            expected_nonce=_NONCE,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_claim", ["aud", "exp", "iat", "iss", "nonce", "sub"])
async def test_required_claims_cannot_be_omitted(missing_claim: str) -> None:
    claims = _claims()
    claims.pop(missing_claim)
    token, jwk = _signed_token(claims=claims)

    with pytest.raises(AuthenticationError, match="Authentication required"):
        await _verifier(_StaticJwksCache(jwk)).verify_id_token(
            token,
            expected_nonce=_NONCE,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "expected_nonce",
    ["", "short", " nonce_" + "a" * 37, "驗證值" * 16, "a" * 513],
)
async def test_expected_nonce_must_be_strong_normalized_ascii(expected_nonce: str) -> None:
    token, jwk = _signed_token()
    cache = _StaticJwksCache(jwk)

    with pytest.raises(AuthenticationError, match="Authentication required"):
        await _verifier(cache).verify_id_token(token, expected_nonce=expected_nonce)

    assert cache.calls == []


@pytest.mark.asyncio
async def test_non_rs256_or_missing_kid_headers_are_rejected_before_jwks_lookup() -> None:
    cache = _StaticJwksCache({})
    hs_token = jwt.encode(
        _claims(),
        "restricted-secret-material-at-least-32-bytes",
        algorithm="HS256",
        headers={"kid": "test-key"},
    )
    rs_token, _ = _signed_token(headers={})

    for token in (hs_token, rs_token):
        with pytest.raises(AuthenticationError, match="Authentication required"):
            await _verifier(cache).verify_id_token(token, expected_nonce=_NONCE)

    assert cache.calls == []


@pytest.mark.asyncio
async def test_signature_failure_refreshes_rotated_jwks_once() -> None:
    signing_key, current_jwk = _key_pair()
    _, stale_jwk = _key_pair()
    token, _ = _signed_token(private_key=signing_key)
    cache = _RotatingJwksCache(stale_jwk, current_jwk)

    identity = await _verifier(cache).verify_id_token(token, expected_nonce=_NONCE)

    assert identity.subject == "107691503500061507151"
    assert cache.calls == [False, True]


@pytest.mark.asyncio
async def test_signature_failure_after_refresh_is_uniform_and_secret_free(
    caplog: pytest.LogCaptureFixture,
) -> None:
    token, _ = _signed_token(claims=_claims(email="restricted@example.test"))
    _, wrong_jwk = _key_pair()
    cache = _StaticJwksCache(wrong_jwk)
    caplog.set_level(logging.WARNING, logger="app.adapters.auth.google_oidc")

    with pytest.raises(AuthenticationError, match="^Authentication required$") as exc_info:
        await _verifier(cache).verify_id_token(token, expected_nonce=_NONCE)

    assert exc_info.value.__cause__ is None
    assert "reason=SIGNATURE" in caplog.text
    assert token not in caplog.text
    assert "restricted@example.test" not in caplog.text
    assert cache.calls == [False, True]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "claim_overrides",
    [
        {"email_verified": True, "email": None},
        {"email_verified": "yes"},
        {"email_verified": True, "email": " email@example.test"},
        {"email_verified": True, "email": "a" * 255},
        {"name": 123},
        {"name": "a" * 121},
    ],
)
async def test_malformed_optional_identity_claims_are_rejected_without_logging_values(
    claim_overrides: dict,
    caplog: pytest.LogCaptureFixture,
) -> None:
    token, jwk = _signed_token(claims=_claims(**claim_overrides))
    caplog.set_level(logging.WARNING, logger="app.adapters.auth.google_oidc")

    with pytest.raises(AuthenticationError, match="Authentication required"):
        await _verifier(_StaticJwksCache(jwk)).verify_id_token(
            token,
            expected_nonce=_NONCE,
        )

    assert "reason=IDENTITY_CLAIMS" in caplog.text
    assert token not in caplog.text


def test_verified_identity_invariants_prevent_unverified_email_retention() -> None:
    with pytest.raises(ValueError, match="only when verified"):
        VerifiedGoogleIdentity(
            subject="google-subject",
            email="unverified@example.test",
            email_verified=False,
        )


@pytest.mark.parametrize("client_id", ["", " padded-client ", "client id", "a" * 513])
def test_verifier_rejects_invalid_client_configuration(client_id: str) -> None:
    with pytest.raises(ValueError, match="Google OIDC client ID"):
        GoogleOidcJwtVerifier(client_id=client_id)


class _FakeResponse:
    def __init__(self, document: object, *, cache_control: str = "") -> None:
        self._document = document
        self.headers = {"cache-control": cache_control}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._document


class _FakeAsyncClient:
    def __init__(self, response: _FakeResponse, calls: list[str]) -> None:
        self._response = response
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def get(self, url: str) -> _FakeResponse:
        self._calls.append(url)
        return self._response


@pytest.mark.asyncio
async def test_jwks_cache_uses_fixed_google_endpoint_and_honors_bounded_max_age(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, jwk = _key_pair()
    calls: list[str] = []
    responses = deque(
        [_FakeResponse({"keys": [jwk]}, cache_control="public, max-age=120, must-revalidate")]
    )

    def client_factory(*, timeout: float):
        assert timeout == 4
        return _FakeAsyncClient(responses.popleft(), calls)

    monkeypatch.setattr("app.adapters.auth.google_oidc.httpx.AsyncClient", client_factory)
    cache = GoogleJwksCache(max_ttl_seconds=60, timeout_seconds=4)

    assert await cache.get("test-key") == jwk
    assert await cache.get("test-key") == jwk
    assert calls == ["https://www.googleapis.com/oauth2/v3/certs"]
    assert cache._expires_at <= datetime.now(UTC) + timedelta(seconds=60)  # noqa: SLF001


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "document",
    [
        {},
        {"keys": []},
        {"keys": [{"kid": "test-key", "kty": "EC"}]},
        {
            "keys": [
                {"kid": "duplicate", "kty": "RSA"},
                {"kid": "duplicate", "kty": "RSA"},
            ]
        },
    ],
)
async def test_malformed_jwks_documents_fail_closed(
    document: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def client_factory(*, timeout: float):
        del timeout
        return _FakeAsyncClient(_FakeResponse(document), calls)

    monkeypatch.setattr("app.adapters.auth.google_oidc.httpx.AsyncClient", client_factory)

    with pytest.raises(AuthenticationError, match="Authentication required"):
        await GoogleJwksCache(max_ttl_seconds=300, timeout_seconds=5).get("test-key")


@pytest.mark.parametrize(
    ("ttl", "timeout"),
    [(29, 5), (3_601, 5), (300, 0), (300, 16)],
)
def test_jwks_cache_configuration_is_bounded(ttl: int, timeout: float) -> None:
    with pytest.raises(ValueError):
        GoogleJwksCache(max_ttl_seconds=ttl, timeout_seconds=timeout)
