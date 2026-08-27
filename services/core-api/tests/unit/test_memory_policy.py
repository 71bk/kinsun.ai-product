"""Deterministic candidate policy and source-speaker tests."""

from __future__ import annotations

from uuid import uuid4

from app.policies.memory_policy import (
    GatedVoiceTurnFacts,
    derive_turn_speaker_evidence,
    evaluate_memory_candidate,
)


def _decision(**overrides):
    values = {
        "memory_type": "PREFERENCE",
        "memory_kind": "MUSIC_PREFERENCE",
        "normalized_content": "喜歡聽歌仔戲。",
        "confirmation_question": "要記住您喜歡聽歌仔戲嗎？",
        "extraction_confidence": 0.9,
        "possible_conflict": False,
        "speaker_verification_level": "VERIFIED_ELDER",
        "speaker_evidence_reference": "speaker-evidence:test",
    }
    values.update(overrides)
    return evaluate_memory_candidate(**values)


def test_only_authenticated_elder_text_derives_verified_elder_speaker() -> None:
    actor_id = uuid4()
    session_id = uuid4()
    evidence = derive_turn_speaker_evidence(
        input_mode="text",
        actor_role="ELDER",
        actor_id=actor_id,
        session_id=session_id,
        turn_reference="run-1",
    )
    assert evidence.verification_level == "VERIFIED_ELDER"
    assert evidence.speaker_actor_id == actor_id
    assert evidence.verification_method == "AUTHENTICATED_TEXT"
    assert str(session_id) in evidence.evidence_reference


def test_family_text_and_unverified_voice_cannot_become_elder_speaker() -> None:
    family = derive_turn_speaker_evidence(
        input_mode="text",
        actor_role="FAMILY_MEMBER",
        actor_id=uuid4(),
        session_id=uuid4(),
        turn_reference="run-family",
    )
    voice = derive_turn_speaker_evidence(
        input_mode="voice",
        actor_role="ELDER",
        actor_id=uuid4(),
        session_id=uuid4(),
        turn_reference="run-voice",
    )
    assert family.verification_level == "THIRD_PARTY"
    assert voice.verification_level == "UNKNOWN"
    assert voice.speaker_actor_id is None


def test_gated_elder_only_voice_session_derives_verified_elder_speaker() -> None:
    elder_actor_id = uuid4()
    session_id = uuid4()
    gate_evidence_id = uuid4()

    evidence = derive_turn_speaker_evidence(
        input_mode="voice",
        actor_role="ELDER",
        actor_id=elder_actor_id,
        session_id=session_id,
        turn_reference="run-voice",
        voice_turn=GatedVoiceTurnFacts(
            asr_gate_evidence_id=gate_evidence_id,
            initiator_actor_id=elder_actor_id,
            elder_actor_id=elder_actor_id,
        ),
    )

    assert evidence.verification_level == "VERIFIED_ELDER"
    assert evidence.speaker_actor_id == elder_actor_id
    assert evidence.verification_method == "ELDER_ONLY_VOICE_SESSION"
    assert str(session_id) in evidence.evidence_reference
    assert str(gate_evidence_id) in evidence.evidence_reference


def test_gated_voice_without_elder_only_session_stays_unknown() -> None:
    elder_actor_id = uuid4()
    staff_actor_id = uuid4()
    gate_evidence_id = uuid4()

    def _derive(*, actor_role: str, actor_id, initiator_actor_id, elder_id):
        return derive_turn_speaker_evidence(
            input_mode="voice_with_text_fallback",
            actor_role=actor_role,
            actor_id=actor_id,
            session_id=uuid4(),
            turn_reference="run-voice",
            voice_turn=GatedVoiceTurnFacts(
                asr_gate_evidence_id=gate_evidence_id,
                initiator_actor_id=initiator_actor_id,
                elder_actor_id=elder_id,
            ),
        )

    # A caregiver opened the session, so Spec 18 6.2 leaves initiator evidence only.
    staff_initiated = _derive(
        actor_role="ELDER",
        actor_id=elder_actor_id,
        initiator_actor_id=staff_actor_id,
        elder_id=elder_actor_id,
    )
    # The speaking actor is not the elder this session belongs to.
    third_party_actor = _derive(
        actor_role="DAYCARE_CARE_WORKER",
        actor_id=staff_actor_id,
        initiator_actor_id=staff_actor_id,
        elder_id=elder_actor_id,
    )
    # The elder record carries no actor, so ownership cannot be established.
    unlinked_elder = _derive(
        actor_role="ELDER",
        actor_id=elder_actor_id,
        initiator_actor_id=elder_actor_id,
        elder_id=None,
    )

    for evidence in (staff_initiated, third_party_actor, unlinked_elder):
        assert evidence.verification_level == "UNKNOWN"
        assert evidence.speaker_actor_id is None
        assert evidence.evidence_reference is None


def test_low_all_of_auto_activates_but_medium_requires_elder_confirmation() -> None:
    low = _decision()
    medium = _decision(
        memory_type="ROUTINE",
        memory_kind="DAILY_ROUTINE",
        normalized_content="每天早餐習慣吃粥。",
        confirmation_question="要記住每天早餐習慣嗎？",
    )
    downgraded_low = _decision(extraction_confidence=0.8)

    assert low.create_memory is True
    assert low.status == "ACTIVE"
    assert low.policy_decision == "AUTO_ACTIVATED_LOW"
    assert medium.status == "PENDING_CONFIRMATION"
    assert medium.policy_decision == "PENDING_ELDER_CONFIRMATION"
    assert downgraded_low.actual_risk_level == "MEDIUM"
    assert downgraded_low.status == "PENDING_CONFIRMATION"


def test_high_unverified_conflict_and_low_confidence_have_zero_memory_side_effect() -> None:
    high = _decision(memory_kind="HEALTH_INFERENCE")
    unverified = _decision(speaker_verification_level="THIRD_PARTY")
    conflict = _decision(possible_conflict=True)
    low_confidence = _decision(extraction_confidence=0.4)

    assert high.create_memory is False
    assert high.policy_decision == "REJECTED_HIGH_RISK"
    assert unverified.reason_code == "SPEAKER_OWNERSHIP_UNVERIFIED"
    assert conflict.reason_code == "CONFLICT_REVIEW_REQUIRED"
    assert low_confidence.reason_code == "EXTRACTION_CONFIDENCE_TOO_LOW"


def test_mislabeled_sensitive_content_and_kind_type_mismatch_fail_closed() -> None:
    disguised_health = _decision(
        normalized_content="我有糖尿病，需要記得吃藥。",
        confirmation_question="要記住我的用藥嗎？",
    )
    mismatched_type = _decision(memory_type="ROUTINE")

    assert disguised_health.create_memory is False
    assert disguised_health.policy_decision == "REJECTED_HIGH_RISK"
    assert mismatched_type.reason_code == "MEMORY_KIND_TYPE_MISMATCH"
