"""Small, cache-safe service dependencies assembled from validated settings."""

from __future__ import annotations

from functools import lru_cache

from app.adapters.line_messaging import LineMessagingClient
from app.core.config import get_settings
from app.core.exceptions import ServiceUnavailableError
from app.services.family_invitation_tokens import FamilyInvitationTokenCodec
from app.services.line_identity_codec import LineIdentityCodec
from app.services.line_subject_cipher import LineSubjectCipher


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


@lru_cache(maxsize=8)
def _build_line_messaging_client(
    channel_access_token: str,
    timeout_seconds: float,
) -> LineMessagingClient:
    return LineMessagingClient(
        channel_access_token=channel_access_token,
        timeout_seconds=timeout_seconds,
    )


def get_line_messaging_client() -> LineMessagingClient:
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
