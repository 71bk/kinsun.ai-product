from __future__ import annotations

from datetime import UTC, date, datetime, time
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import pytest
from sqlalchemy import text

from app.middleware.auth import ActorContext
from app.repositories.notification_repo import NotificationRepository
from app.services.line_account_link_service import LineAccountLinkService
from app.services.line_identity_codec import LineIdentityCodec
from app.services.line_subject_cipher import LineSubjectCipher

TENANT_ID = UUID("71000000-0000-4000-8000-000000000001")
ELDER_ACTOR_ID = UUID("71000000-0000-4000-8000-000000000002")
FAMILY_ACTOR_ID = UUID("71000000-0000-4000-8000-000000000003")
ELDER_ID = UUID("71000000-0000-4000-8000-000000000004")
POLICY_ID = UUID("71000000-0000-4000-8000-000000000005")
CONSENT_ID = UUID("71000000-0000-4000-8000-000000000006")
RELATIONSHIP_ID = UUID("71000000-0000-4000-8000-000000000007")
REPORT_ID = UUID("71000000-0000-4000-8000-000000000008")
REPORT_VERSION_ID = UUID("71000000-0000-4000-8000-000000000009")
PREFERENCE_ID = UUID("71000000-0000-4000-8000-000000000010")
IDENTITY_ID = UUID("71000000-0000-4000-8000-000000000011")


@pytest.mark.asyncio
async def test_candidate_query_and_delivery_claim_are_consent_safe_and_idempotent(
    db_session,
) -> None:
    seed_sql = """
            INSERT INTO eldercare_ai.tenant
                (tenant_id, tenant_type, name, status, timezone)
            VALUES (:tenant_id, 'DEMO', 'Synthetic notification tenant', 'ACTIVE', 'Asia/Taipei');

            INSERT INTO eldercare_ai.actor
                (actor_id, actor_type, display_name, status)
            VALUES
                (:elder_actor_id, 'ELDER', 'Synthetic elder actor', 'ACTIVE'),
                (:family_actor_id, 'FAMILY_MEMBER', 'Synthetic family actor', 'ACTIVE');

            INSERT INTO eldercare_ai.actor_tenant_membership
                (actor_id, tenant_id, role_code, status, effective_from)
            VALUES
                (:elder_actor_id, :tenant_id, 'ELDER', 'ACTIVE', '2026-01-01T00:00:00Z'),
                (:family_actor_id, :tenant_id, 'FAMILY_MEMBER', 'ACTIVE', '2026-01-01T00:00:00Z');

            INSERT INTO eldercare_ai.elder
                (elder_id, tenant_id, actor_id, display_name, primary_care_setting,
                 status, preferred_language, response_length_preference, timezone)
            VALUES
                (:elder_id, :tenant_id, :elder_actor_id, 'Synthetic elder', 'INDEPENDENT',
                 'ACTIVE', 'ZH_TW', 'STANDARD', 'Asia/Taipei');

            INSERT INTO eldercare_ai.policy_registry
                (policy_id, owner_tenant_id, policy_code, policy_type, version,
                 status, policy_payload, effective_from)
            VALUES
                (:policy_id, :tenant_id, 'synthetic-family-sharing', 'CONSENT', '1',
                 'ACTIVE', '{}'::jsonb, '2026-01-01T00:00:00Z');

            INSERT INTO eldercare_ai.consent_grant
                (consent_id, elder_id, purpose_code, status, version, scope,
                 granted_by_actor_id, policy_id, granted_at, effective_at)
            VALUES
                (:consent_id, :elder_id, 'FAMILY_SHARING', 'GRANTED', 1, '{}'::jsonb,
                 :elder_actor_id, :policy_id, '2026-01-01T00:00:00Z',
                 '2026-01-01T00:00:00Z');

            INSERT INTO eldercare_ai.family_relationship
                (family_relationship_id, elder_id, family_actor_id, share_scope,
                 status, effective_from, consent_id)
            VALUES
                (:relationship_id, :elder_id, :family_actor_id,
                 ARRAY['REPORT_DAILY'], 'ACTIVE', '2026-01-01T00:00:00Z', :consent_id);

            INSERT INTO eldercare_ai.family_report
                (report_id, elder_id, tenant_id, recipient_scope, report_type,
                 period_start, period_end, status, current_version, published_at)
            VALUES
                (:report_id, :elder_id, :tenant_id,
                 jsonb_build_object(
                    'relationship_ids',
                    jsonb_build_array(CAST(:relationship_id_text AS text))
                 ),
                 'DAILY', '2026-08-01', '2026-08-01', 'PUBLISHED', 1,
                 '2026-08-01T23:00:00Z');

            INSERT INTO eldercare_ai.report_version
                (report_version_id, report_id, version, content, share_scope_snapshot)
            VALUES
                (:report_version_id, :report_id, 1,
                 jsonb_build_object(
                    'items', jsonb_build_array(),
                    'data_gap_notice', 'Synthetic',
                    'sensitive_review_required', false
                 ),
                 jsonb_build_object(
                    'relationship_ids',
                    jsonb_build_array(CAST(:relationship_id_text AS text))
                 ));

            INSERT INTO eldercare_ai.notification_preference
                (preference_id, family_actor_id, elder_id, channels, frequency,
                 send_time_local, timezone, quiet_hours, status)
            VALUES
                (:preference_id, :family_actor_id, :elder_id,
                 ARRAY['LINE']::eldercare_ai.notification_channel_enum[], 'DAILY',
                 '08:00', 'Asia/Taipei', '{}'::jsonb, 'ACTIVE');

            INSERT INTO eldercare_ai.external_identity
                (external_identity_id, provider, external_subject_digest,
                 digest_key_version, actor_id, status, encrypted_external_subject,
                 linked_at, version)
            VALUES
                (:identity_id, 'LINE', repeat('a', 64), 1, :family_actor_id,
                 'ACTIVE', 'synthetic-encrypted-subject', '2026-08-01T00:00:00Z', 1);
            """
    parameters = {
        "tenant_id": TENANT_ID,
        "elder_actor_id": ELDER_ACTOR_ID,
        "family_actor_id": FAMILY_ACTOR_ID,
        "elder_id": ELDER_ID,
        "policy_id": POLICY_ID,
        "consent_id": CONSENT_ID,
        "relationship_id": RELATIONSHIP_ID,
        "relationship_id_text": str(RELATIONSHIP_ID),
        "report_id": REPORT_ID,
        "report_version_id": REPORT_VERSION_ID,
        "preference_id": PREFERENCE_ID,
        "identity_id": IDENTITY_ID,
    }
    for statement in seed_sql.split(";"):
        if statement.strip():
            await db_session.execute(text(statement), parameters)
    repository = NotificationRepository(db_session, TENANT_ID)
    now = datetime(2026, 8, 2, tzinfo=UTC)
    candidates = await repository.list_daily_line_candidates(
        source_date=date(2026, 8, 1),
        timezone="Asia/Taipei",
        send_time=time(8),
        now=now,
    )

    assert len(candidates) == 1
    assert candidates[0].report_id == REPORT_ID
    assert candidates[0].recipient_actor_id == FAMILY_ACTOR_ID

    scheduled_at = datetime(2026, 8, 2, tzinfo=UTC)
    claim = await repository.claim_delivery(
        candidate=candidates[0],
        scheduled_at=scheduled_at,
        now=now,
        max_attempts=3,
    )
    assert claim.status == "CLAIMED"
    await repository.mark_sent(claim.notification_id, now=now)
    await db_session.flush()

    replay = await repository.claim_delivery(
        candidate=candidates[0],
        scheduled_at=scheduled_at,
        now=now,
        max_attempts=3,
    )
    assert replay.status == "REPLAYED"
    assert replay.notification_id == claim.notification_id

    family_actor = ActorContext(
        actor_id=FAMILY_ACTOR_ID,
        actor_role="FAMILY_MEMBER",
        tenant_id=TENANT_ID,
    )
    codec = LineIdentityCodec("hmac-secret-that-is-longer-than-32-bytes", 1)
    cipher = LineSubjectCipher("encryption-secret-that-is-longer-than-32-bytes")
    link_service = LineAccountLinkService(
        db_session,
        codec,
        challenge_ttl_seconds=600,
        challenge_max_attempts=3,
        frontend_base_url="https://app.example.test",
        subject_cipher=cipher,
    )
    assert (await link_service.get_status(family_actor)).linked is True

    await db_session.execute(
        text(
            "UPDATE eldercare_ai.external_identity "
            "SET status='REVOKED', revoked_at=:now, version=version+1 "
            "WHERE external_identity_id=:identity_id"
        ),
        {"now": now, "identity_id": IDENTITY_ID},
    )
    challenge = await link_service.create_challenge(
        actor=family_actor,
        link_token="synthetic-link-token",
    )
    nonce = parse_qs(urlparse(challenge.account_link_url).query)["nonce"][0]
    line_user_id = "U1234567890abcdef1234567890abcdef"
    assert await link_service.redeem_account_link(
        nonce=nonce,
        line_user_id=line_user_id,
        result="ok",
        trace_id="trace-family-line-link",
        idempotency_key="family-line-link:synthetic",
    )
    linked_row = (
        await db_session.execute(
            text(
                "SELECT external_subject_digest, encrypted_external_subject "
                "FROM eldercare_ai.external_identity "
                "WHERE actor_id=:actor_id AND status='ACTIVE'"
            ),
            {"actor_id": FAMILY_ACTOR_ID},
        )
    ).one()
    challenge_elder_id = await db_session.scalar(
        text(
            "SELECT elder_id FROM eldercare_ai.line_link_challenge "
            "WHERE line_link_challenge_id=:challenge_id"
        ),
        {"challenge_id": challenge.challenge_id},
    )
    assert challenge_elder_id is None
    assert linked_row.external_subject_digest == codec.digest_subject(line_user_id)
    assert line_user_id not in linked_row.encrypted_external_subject
    assert cipher.decrypt(linked_row.encrypted_external_subject) == line_user_id

    await db_session.execute(
        text(
            "UPDATE eldercare_ai.consent_grant "
            "SET status='REVOKED', revoked_at=:now WHERE consent_id=:consent_id"
        ),
        {"now": now, "consent_id": CONSENT_ID},
    )
    assert (
        await repository.list_daily_line_candidates(
            source_date=date(2026, 8, 1),
            timezone="Asia/Taipei",
            send_time=time(8),
            now=now,
        )
        == []
    )
