"""Schema-level invariants for accountless Elder onboarding."""

from __future__ import annotations

from app.models.assisted_elder_session import AssistedElderSession
from app.models.care_action import CareAction
from app.models.care_profile import ElderCareProfileEntry
from app.models.elder_enrollment import ElderEnrollment


def test_enrollment_keeps_elder_and_service_context_separate() -> None:
    columns = ElderEnrollment.__table__.columns

    assert columns["elder_id"].nullable is False
    assert columns["tenant_id"].nullable is False
    assert columns["created_by_actor_id"].nullable is False
    assert columns["valid_until"].nullable is True


def test_care_profile_has_provenance_and_no_memory_link() -> None:
    columns = ElderCareProfileEntry.__table__.columns

    assert columns["source_actor_id"].nullable is False
    assert columns["source_type"].nullable is False
    assert columns["verification_status"].nullable is False
    assert "memory_id" not in columns
    assert "diagnosis" not in columns


def test_assisted_session_persists_only_digests_and_real_initiator() -> None:
    columns = AssistedElderSession.__table__.columns

    assert "pairing_token" not in columns
    assert "session_token" not in columns
    assert columns["pairing_token_digest"].nullable is False
    assert columns["session_token_digest"].nullable is True
    assert columns["initiated_by_actor_id"].nullable is False
    assert columns["elder_id"].nullable is False


def test_care_action_has_scope_sources_owner_and_optimistic_version() -> None:
    columns = CareAction.__table__.columns

    assert columns["tenant_id"].nullable is False
    assert columns["elder_id"].nullable is False
    assert columns["related_event_ids"].nullable is False
    assert columns["assignee_actor_id"].nullable is False
    assert columns["created_by_actor_id"].nullable is False
    assert columns["version"].nullable is False
