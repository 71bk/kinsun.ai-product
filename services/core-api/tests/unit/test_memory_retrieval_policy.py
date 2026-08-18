"""Spec 18 final-gate tests for trusted memory context."""

from __future__ import annotations

from dataclasses import replace

from app.policies.memory_retrieval import (
    CURRENT_MEMORY_POLICY_VERSION,
    MemoryTrustEvidence,
    evaluate_memory_trust,
    memory_content_digest,
)


def _low_evidence() -> MemoryTrustEvidence:
    content = "喜歡聽歌仔戲"
    return MemoryTrustEvidence(
        version=2,
        content=content,
        content_digest=memory_content_digest(content),
        memory_kind="MUSIC_PREFERENCE",
        consent_id_present=True,
        policy_version=CURRENT_MEMORY_POLICY_VERSION,
        policy_decision="AUTO_ACTIVATED_LOW",
        actual_risk_level="LOW",
        verification_level="POLICY_VERIFIED",
        required_verification="NONE",
        speaker_verification_level="VERIFIED_ELDER",
        speaker_evidence_reference="speaker-evidence:low",
        confirmed_version=None,
        confirmed_content_digest=None,
        confirmation_method=None,
        confirmation_evidence_reference=None,
        confirmed_by_present=False,
        confirmed_at_present=False,
        confirmation_record_present=False,
    )


def _medium_evidence() -> MemoryTrustEvidence:
    content = "每天早餐習慣吃粥。"
    digest = memory_content_digest(content)
    return MemoryTrustEvidence(
        version=3,
        content=content,
        content_digest=digest,
        memory_kind="DAILY_ROUTINE",
        consent_id_present=True,
        policy_version=CURRENT_MEMORY_POLICY_VERSION,
        policy_decision="ELDER_CONFIRMED_MEDIUM",
        actual_risk_level="MEDIUM",
        verification_level="ELDER_CONFIRMED",
        required_verification="ELDER_CONFIRMATION",
        speaker_verification_level="VERIFIED_ELDER",
        speaker_evidence_reference="speaker-evidence:medium",
        confirmed_version=3,
        confirmed_content_digest=digest,
        confirmation_method="ELDER_UI",
        confirmation_evidence_reference="core-command:test",
        confirmed_by_present=True,
        confirmed_at_present=True,
        confirmation_record_present=True,
    )


def test_low_requires_all_policy_and_speaker_evidence() -> None:
    assert evaluate_memory_trust(_low_evidence()).allowed is True
    assert (
        evaluate_memory_trust(replace(_low_evidence(), speaker_evidence_reference=None)).reason_code
        == "SPEAKER_EVIDENCE_INVALID"
    )


def test_medium_confirmation_is_bound_to_current_version_and_digest() -> None:
    assert evaluate_memory_trust(_medium_evidence()).allowed is True
    stale = evaluate_memory_trust(replace(_medium_evidence(), confirmed_version=2))
    assert stale.allowed is False
    assert stale.reason_code == "CONFIRMATION_VERSION_STALE"

    missing_record = evaluate_memory_trust(
        replace(_medium_evidence(), confirmation_record_present=False)
    )
    assert missing_record.allowed is False
    assert missing_record.reason_code == "CONFIRMATION_RECORD_MISSING"


def test_tampered_content_and_stale_policy_are_rejected() -> None:
    digest_mismatch = evaluate_memory_trust(replace(_low_evidence(), content="已被修改的內容"))
    assert digest_mismatch.reason_code == "CONTENT_DIGEST_MISMATCH"

    stale_policy = evaluate_memory_trust(
        replace(_low_evidence(), policy_version="memory-policy-old")
    )
    assert stale_policy.reason_code == "POLICY_VERSION_STALE"


def test_high_or_legacy_memory_never_enters_context() -> None:
    high = evaluate_memory_trust(
        replace(
            _low_evidence(),
            memory_kind="HEALTH_INFERENCE",
            actual_risk_level="HIGH",
            policy_decision="REJECTED_HIGH_RISK",
        )
    )
    assert high.reason_code == "HIGH_OR_UNKNOWN_RISK"

    legacy = evaluate_memory_trust(
        replace(
            _low_evidence(),
            content_digest=None,
            memory_kind=None,
            policy_version=None,
        )
    )
    assert legacy.reason_code == "LEGACY_EVIDENCE_MISSING"
