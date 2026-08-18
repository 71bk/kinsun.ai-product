"""classify and quarantine legacy memory evidence

Revision ID: c5d7e9f1a234
Revises: a4c6e8f0b123
Create Date: 2026-08-18 19:00:00+08:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c5d7e9f1a234"
down_revision: str | Sequence[str] | None = "a4c6e8f0b123"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "eldercare_ai"
CURRENT_POLICY_VERSION = "memory-policy-2026-08-18.v1"


def upgrade() -> None:
    # Expand first. A fail-closed default keeps an older writer from silently
    # creating trusted rows while application instances are rolling forward.
    op.add_column(
        "memory",
        sa.Column(
            "evidence_state",
            sa.String(length=32),
            nullable=True,
            server_default=sa.text("'LEGACY_NEEDS_REVIEW'"),
        ),
        schema=SCHEMA,
    )

    # Promote only rows whose current version, source, speaker, consent, risk,
    # policy, and (when applicable) append-only confirmation can be proven from
    # authoritative relational evidence. Nothing is synthesized during backfill.
    op.execute(
        f"""
        WITH evidence AS (
          SELECT
            m.memory_id,
            EXISTS (
              SELECT 1
              FROM {SCHEMA}.memory_version mv
              JOIN {SCHEMA}.care_event ce
                ON ce.event_id = mv.source_event_ids[1]
              JOIN {SCHEMA}.care_event_version cev
                ON cev.event_id = ce.event_id
               AND cev.version = ce.current_version
              WHERE mv.memory_id = m.memory_id
                AND mv.version = m.current_version
                AND mv.version_status = 'ACTIVE'
                AND mv.content_digest IS NOT NULL
                AND mv.content_digest = encode(
                  digest(convert_to(mv.content, 'UTF8'), 'sha256'),
                  'hex'
                )
                AND cardinality(mv.source_event_ids) = 1
                AND ce.tenant_id = m.tenant_id
                AND ce.elder_id = m.elder_id
                AND ce.status IN ('VERIFIED', 'CORRECTED')
                AND ce.source_session_id IS NOT DISTINCT FROM
                    mv.source_session_id
                AND mv.source_turn_reference =
                    concat(
                      'care-event', chr(58), ce.event_id::text,
                      chr(58), 'v', ce.current_version::text
                    )
                AND cev.memory_candidate_proposal IS NOT NULL
                AND cev.memory_candidate_proposal ->> 'memory_type' =
                    m.memory_type
                AND cev.memory_candidate_proposal ->> 'memory_kind' =
                    m.memory_kind
                AND cev.memory_candidate_proposal ->> 'normalized_content' =
                    mv.content
                AND cev.memory_candidate_proposal ->> 'confirmation_question' =
                    mv.confirmation_question
                AND cev.memory_candidate_proposal ->> 'extractor_version' =
                    mv.extractor_version
                AND cev.memory_candidate_proposal ->> 'proposal_risk_hint' =
                    mv.proposal_risk_hint
                AND cev.speaker_verification_level =
                    m.speaker_verification_level
                AND cev.speaker_evidence_reference =
                    m.speaker_evidence_reference
            ) AS current_version_proven,
            EXISTS (
              SELECT 1
              FROM {SCHEMA}.memory_version mv
              JOIN {SCHEMA}.memory_confirmation mc
                ON mc.memory_id = m.memory_id
               AND mc.memory_version = m.current_version
               AND mc.content_digest = mv.content_digest
              WHERE mv.memory_id = m.memory_id
                AND mv.version = m.current_version
                AND mc.tenant_id = m.tenant_id
                AND mc.elder_id = m.elder_id
                AND mc.consent_id = m.consent_id
                AND mc.consent_version = m.consent_version
                AND mc.policy_version = m.policy_version
                AND mc.response_intent = 'AFFIRM'
                AND mc.confirmation_method = m.confirmation_method
                AND mc.confirmed_by_actor_id = m.confirmed_by_actor_id
                AND mc.confirmation_session_id IS NOT DISTINCT FROM
                    m.confirmation_session_id
                AND mc.confirmed_at = m.confirmed_at
                AND mc.speaker_verification_level =
                    m.speaker_verification_level
                AND mc.speaker_evidence_reference =
                    m.speaker_evidence_reference
                AND mc.confirmation_evidence_reference =
                    m.confirmation_evidence_ref
                AND mc.decision_support_profile_id IS NOT DISTINCT FROM
                    m.decision_support_profile_id
                AND mc.decision_support_profile_version IS NOT DISTINCT FROM
                    m.decision_support_profile_version
                AND m.confirmed_version = m.current_version
                AND m.confirmed_content_digest = mv.content_digest
            ) AS confirmation_proven
          FROM {SCHEMA}.memory m
        )
        UPDATE {SCHEMA}.memory AS m
        SET evidence_state = 'CURRENT'
        FROM evidence e
        WHERE e.memory_id = m.memory_id
          AND m.memory_kind IS NOT NULL
          AND m.actual_risk_level IS NOT NULL
          AND m.policy_decision IS NOT NULL
          AND m.policy_version = '{CURRENT_POLICY_VERSION}'
          AND m.verification_level IS NOT NULL
          AND m.required_verification IS NOT NULL
          AND m.consent_id IS NOT NULL
          AND m.consent_version > 0
          AND m.speaker_verification_level IN (
            'VERIFIED_ELDER',
            'WITNESSED_ELDER'
          )
          AND m.speaker_evidence_reference IS NOT NULL
          AND e.current_version_proven
          AND (
            (
              m.status NOT IN ('ACTIVE', 'CONFIRMED')
              AND (
                (
                  m.confirmed_version IS NULL
                  AND m.confirmed_content_digest IS NULL
                  AND m.confirmation_method IS NULL
                  AND m.confirmed_by_actor_id IS NULL
                  AND m.confirmed_at IS NULL
                  AND m.confirmation_evidence_ref IS NULL
                )
                OR e.confirmation_proven
              )
            )
            OR (
              m.status IN ('ACTIVE', 'CONFIRMED')
              AND (
                (
                  m.actual_risk_level = 'LOW'
                  AND m.policy_decision = 'AUTO_ACTIVATED_LOW'
                  AND m.verification_level = 'POLICY_VERIFIED'
                  AND m.required_verification = 'NONE'
                )
                OR e.confirmation_proven
              )
            )
          )
        """
    )

    # Quarantine anything that could not be proven. Status changes are
    # intentionally one-way so a schema rollback cannot resurrect old context.
    op.execute(
        f"""
        UPDATE {SCHEMA}.memory
        SET
          status = CASE
            WHEN status IN ('ACTIVE', 'CONFIRMED') THEN 'INACTIVE'
            WHEN status IN ('CANDIDATE', 'PENDING_CONFIRMATION') THEN 'DEFERRED'
            ELSE status
          END,
          deactivated_at = CASE
            WHEN status IN ('ACTIVE', 'CONFIRMED')
              THEN COALESCE(deactivated_at, now())
            ELSE deactivated_at
          END,
          lifecycle_reason = CASE
            WHEN status IN (
              'ACTIVE',
              'CONFIRMED',
              'CANDIDATE',
              'PENDING_CONFIRMATION',
              'DEFERRED'
            ) THEN 'LEGACY_NEEDS_REVIEW'
            ELSE lifecycle_reason
          END,
          updated_at = now()
        WHERE evidence_state = 'LEGACY_NEEDS_REVIEW'
        """
    )

    op.alter_column(
        "memory",
        "evidence_state",
        existing_type=sa.String(length=32),
        nullable=False,
        server_default=sa.text("'LEGACY_NEEDS_REVIEW'"),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_memory_evidence_state",
        "memory",
        "evidence_state IN ('CURRENT','LEGACY_NEEDS_REVIEW')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_memory_legacy_not_active",
        "memory",
        "evidence_state <> 'LEGACY_NEEDS_REVIEW' " "OR status NOT IN ('ACTIVE','CONFIRMED')",
        schema=SCHEMA,
    )
    op.create_index(
        "ix_memory_evidence_context",
        "memory",
        ["tenant_id", "elder_id", "evidence_state", "status", "updated_at"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    # Do not reverse quarantine status changes: preserving INACTIVE/DEFERRED is
    # what prevents an older reader from seeing legacy rows as ACTIVE.
    op.drop_index(
        "ix_memory_evidence_context",
        table_name="memory",
        schema=SCHEMA,
    )
    op.drop_constraint(
        "ck_memory_legacy_not_active",
        "memory",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_constraint(
        "ck_memory_evidence_state",
        "memory",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_column("memory", "evidence_state", schema=SCHEMA)
