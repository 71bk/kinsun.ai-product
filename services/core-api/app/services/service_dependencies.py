"""Small, cache-safe service dependencies assembled from validated settings."""

from __future__ import annotations

from functools import lru_cache

from app.adapters.line_messaging import LineMessagingClient
from app.core.config import get_settings
from app.core.exceptions import ServiceUnavailableError
from app.core.line_messaging import LineMessagingPort
from app.services.family_invitation_tokens import FamilyInvitationTokenCodec
from app.services.google_identity_codec import GoogleIdentityCodec
from app.services.google_oidc_handoff_auth import GoogleOidcHandoffAuthenticator
from app.services.kinsun_auth_handoff import KinsunAuthHandoffAuthenticator
from app.services.kinsun_identity_codec import (
    KinsunEmailChallengeCodec,
    KinsunIdentityCodec,
)
from app.services.line_identity_codec import LineIdentityCodec
from app.services.line_oidc_handoff_auth import LineOidcHandoffAuthenticator
from app.services.line_subject_cipher import LineSubjectCipher
from app.services.password_hasher import Argon2idPolicy, PasswordHasher


@lru_cache(maxsize=4)
def _build_family_invitation_token_codec(secret: str) -> FamilyInvitationTokenCodec:
    return FamilyInvitationTokenCodec(secret)


def get_family_invitation_token_codec() -> FamilyInvitationTokenCodec:
    secret = get_settings().family_invitation_hmac_secret
    try:
        return _build_family_invitation_token_codec(secret)
    except ValueError as exc:
        raise ServiceUnavailableError("Family invitation service is unavailable") from exc


@lru_cache(maxsize=8)
def _build_kinsun_identity_codec(secret: str, key_version: int) -> KinsunIdentityCodec:
    return KinsunIdentityCodec(secret, key_version)


def get_kinsun_identity_codec() -> KinsunIdentityCodec:
    settings = get_settings()
    try:
        return _build_kinsun_identity_codec(
            settings.kinsun_identity_hmac_secret,
            settings.kinsun_identity_hmac_key_version,
        )
    except ValueError as exc:
        raise ServiceUnavailableError("Kinsun authentication is unavailable") from exc


@lru_cache(maxsize=4)
def _build_kinsun_email_challenge_codec(secret: str) -> KinsunEmailChallengeCodec:
    return KinsunEmailChallengeCodec(secret)


def get_kinsun_email_challenge_codec() -> KinsunEmailChallengeCodec:
    try:
        return _build_kinsun_email_challenge_codec(
            get_settings().kinsun_email_challenge_hmac_secret
        )
    except ValueError as exc:
        raise ServiceUnavailableError("Kinsun authentication is unavailable") from exc


@lru_cache(maxsize=4)
def _build_kinsun_auth_handoff_authenticator(secret: str) -> KinsunAuthHandoffAuthenticator:
    return KinsunAuthHandoffAuthenticator(secret)


def get_kinsun_auth_handoff_authenticator() -> KinsunAuthHandoffAuthenticator:
    try:
        return _build_kinsun_auth_handoff_authenticator(
            get_settings().kinsun_auth_handoff_secret
        )
    except ValueError as exc:
        raise ServiceUnavailableError("Kinsun authentication is unavailable") from exc


@lru_cache(maxsize=4)
def _build_password_hasher(
    parameter_version: int,
    memory_cost_kib: int,
    iterations: int,
    lanes: int,
) -> PasswordHasher:
    return PasswordHasher(
        Argon2idPolicy(
            parameter_version=parameter_version,
            memory_cost_kib=memory_cost_kib,
            iterations=iterations,
            lanes=lanes,
        )
    )


def get_password_hasher() -> PasswordHasher:
    settings = get_settings()
    try:
        return _build_password_hasher(
            settings.kinsun_password_parameter_version,
            settings.kinsun_password_memory_cost_kib,
            settings.kinsun_password_iterations,
            settings.kinsun_password_lanes,
        )
    except ValueError as exc:
        raise ServiceUnavailableError("Kinsun authentication is unavailable") from exc


@lru_cache(maxsize=8)
def _build_google_identity_codec(secret: str, key_version: int) -> GoogleIdentityCodec:
    return GoogleIdentityCodec(secret, key_version)


def get_google_identity_codec() -> GoogleIdentityCodec:
    settings = get_settings()
    try:
        return _build_google_identity_codec(
            settings.google_identity_hmac_secret,
            settings.google_identity_hmac_key_version,
        )
    except ValueError as exc:
        raise ServiceUnavailableError("Google identity handoff is unavailable") from exc


@lru_cache(maxsize=4)
def _build_google_oidc_handoff_authenticator(secret: str) -> GoogleOidcHandoffAuthenticator:
    return GoogleOidcHandoffAuthenticator(secret)


def get_google_oidc_handoff_authenticator() -> GoogleOidcHandoffAuthenticator:
    try:
        return _build_google_oidc_handoff_authenticator(get_settings().google_oidc_handoff_secret)
    except ValueError as exc:
        raise ServiceUnavailableError("Google identity handoff is unavailable") from exc


@lru_cache(maxsize=8)
def _build_line_identity_codec(secret: str, key_version: int) -> LineIdentityCodec:
    return LineIdentityCodec(secret, key_version)


def get_line_identity_codec() -> LineIdentityCodec:
    settings = get_settings()
    try:
        return _build_line_identity_codec(
            settings.line_identity_hmac_secret,
            settings.line_identity_hmac_key_version,
        )
    except ValueError as exc:
        raise ServiceUnavailableError("LINE account linking is unavailable") from exc


@lru_cache(maxsize=4)
def _build_line_oidc_handoff_authenticator(secret: str) -> LineOidcHandoffAuthenticator:
    return LineOidcHandoffAuthenticator(secret)


def get_line_oidc_handoff_authenticator() -> LineOidcHandoffAuthenticator:
    try:
        return _build_line_oidc_handoff_authenticator(get_settings().line_oidc_handoff_secret)
    except ValueError as exc:
        raise ServiceUnavailableError("LINE identity handoff is unavailable") from exc


@lru_cache(maxsize=8)
def _build_line_messaging_client(
    channel_access_token: str,
    timeout_seconds: float,
) -> LineMessagingPort:
    return LineMessagingClient(
        channel_access_token=channel_access_token,
        timeout_seconds=timeout_seconds,
    )


def get_line_messaging_client() -> LineMessagingPort:
    settings = get_settings()
    try:
        return _build_line_messaging_client(
            settings.line_channel_access_token,
            settings.line_messaging_timeout_seconds,
        )
    except ValueError as exc:
        raise ServiceUnavailableError("LINE Messaging API is unavailable") from exc


@lru_cache(maxsize=8)
def _build_line_subject_cipher(secret: str) -> LineSubjectCipher:
    return LineSubjectCipher(secret)


def get_line_subject_cipher() -> LineSubjectCipher:
    try:
        return _build_line_subject_cipher(get_settings().line_subject_encryption_secret)
    except ValueError as exc:
        raise ServiceUnavailableError("LINE push delivery is unavailable") from exc
