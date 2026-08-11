"""Static contracts for provider-neutral identities and application sessions."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from app.models.app_session import AppSession
from app.models.line_identity import ExternalIdentity


def _check_sql(model, name: str) -> str:
    constraint = next(
        item
        for item in model.__table__.constraints
        if isinstance(item, CheckConstraint) and item.name == name
    )
    return str(constraint.sqltext)


def test_external_identity_accepts_only_reviewed_login_providers() -> None:
    sql = _check_sql(ExternalIdentity, "ck_external_identity_provider")

    assert "GOOGLE" in sql
    assert "LINE" in sql
    assert "provider IN" in sql


def test_external_identity_cardinality_is_actor_and_provider_safe() -> None:
    indexes = {index.name: index for index in ExternalIdentity.__table__.indexes}
    constraints = {
        constraint.name: constraint
        for constraint in ExternalIdentity.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    subject_index = indexes["uq_external_identity_active_subject"]
    assert subject_index.unique is True
    assert [column.name for column in subject_index.columns] == [
        "provider",
        "digest_key_version",
        "external_subject_digest",
    ]

    actor_index = indexes["uq_external_identity_active_actor"]
    assert actor_index.unique is True
    assert [column.name for column in actor_index.columns] == ["provider", "actor_id"]

    identity_actor = constraints["uq_external_identity_id_actor"]
    assert [column.name for column in identity_actor.columns] == [
        "external_identity_id",
        "actor_id",
    ]


def test_app_session_persists_only_a_digest_and_authority_references() -> None:
    columns = AppSession.__table__.columns

    assert columns["token_digest"].type.length == 64
    assert columns["token_digest"].nullable is False
    assert "token_digest ~ '^[0-9a-f]{64}$'" == _check_sql(
        AppSession,
        "ck_app_session_token_digest",
    )
    assert "token" not in columns
    assert "access_token" not in columns
    assert "refresh_token" not in columns
    assert "id_token" not in columns
    assert "tenant_id" not in columns
    assert "actor_role" not in columns


def test_app_session_identity_and_actor_cannot_disagree() -> None:
    composite = next(
        constraint
        for constraint in AppSession.__table__.foreign_key_constraints
        if constraint.name == "fk_app_session_external_identity_actor"
    )

    assert isinstance(composite, ForeignKeyConstraint)
    assert [element.parent.name for element in composite.elements] == [
        "external_identity_id",
        "actor_id",
    ]
    assert [element.target_fullname for element in composite.elements] == [
        "eldercare_ai.external_identity.external_identity_id",
        "eldercare_ai.external_identity.actor_id",
    ]
    assert composite.ondelete == "RESTRICT"


def test_app_session_has_revocation_expiry_and_lookup_constraints() -> None:
    check_names = {
        constraint.name
        for constraint in AppSession.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    index_names = {index.name for index in AppSession.__table__.indexes}
    unique_names = {
        constraint.name
        for constraint in AppSession.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert {
        "ck_app_session_status",
        "ck_app_session_last_seen",
        "ck_app_session_idle_expiry",
        "ck_app_session_absolute_expiry",
        "ck_app_session_revocation",
        "ck_app_session_version",
    }.issubset(check_names)
    assert "uq_app_session_token_digest" in unique_names
    assert index_names == {
        "idx_app_session_actor_status",
        "idx_app_session_expiry",
    }
