"""Read-only, exact-campaign DB evidence for the real HTTP Wave 2 chain.

No credentials, transcripts, model replies or unrestricted DB rows are emitted.
Importing this module neither reads environment files nor opens a connection.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

RUN = "wave2-agent-chain-20260908"
ELDER = "40000000-0000-4000-8000-000000000001"
TENANT = "10000000-0000-4000-8000-000000000001"


def validate_target(app_env: str, database_url: str) -> None:
    target = urlsplit(database_url)
    if not (
        app_env == "development"
        and target.scheme == "postgresql+asyncpg"
        and (target.hostname or "").endswith(".supabase.com")
        and target.path == "/postgres"
    ):
        raise RuntimeError("Only the configured Supabase development target is allowed")


SESSION = """
SELECT session_id FROM eldercare_ai.conversation_session
WHERE session_id IN (
  SELECT resource_id FROM eldercare_ai.idempotency_record
  WHERE idempotency_key=:session_key AND resource_type='conversation_session'
) AND elder_id=CAST(:elder AS uuid) AND tenant_id=CAST(:tenant AS uuid)
"""
EVENTS = f"SELECT event_id FROM eldercare_ai.care_event WHERE source_session_id IN ({SESSION})"
CANDIDATES = f"""
SELECT care_action_candidate_id FROM eldercare_ai.care_action_candidate_event_provenance
WHERE event_id IN ({EVENTS})
"""
ACTIONS = f"""
SELECT adopted_care_action_id FROM eldercare_ai.care_action_candidate
WHERE care_action_candidate_id IN ({CANDIDATES}) AND adopted_care_action_id IS NOT NULL
"""
QUERIES = {
    "sessions": f"""
        SELECT session_id,state,input_mode,initiator_actor_id,consent_version
        FROM eldercare_ai.conversation_session WHERE session_id IN ({SESSION})
    """,
    "runs": f"""
        SELECT agent_run_id,session_id,agent_id,agent_version,model_id,
               result_status,latency_ms,trace_id
        FROM eldercare_ai.agent_run WHERE session_id IN ({SESSION})
    """,
    "events": f"""
        SELECT event_id,source_session_id,event_type,status,current_version
        FROM eldercare_ai.care_event WHERE event_id IN ({EVENTS})
    """,
    "versions": f"""
        SELECT event_id,event_version_id,version,
               care_action_candidate_proposal IS NOT NULL AS has_action_proposal,
               speaker_role,speaker_verification_level
        FROM eldercare_ai.care_event_version WHERE event_id IN ({EVENTS}) ORDER BY version
    """,
    "reviews": f"""
        SELECT review_id,event_id,reviewer_actor_id,decision,before_version,after_version
        FROM eldercare_ai.review_decision WHERE event_id IN ({EVENTS})
    """,
    "candidates": f"""
        SELECT care_action_candidate_id,status,version,extractor_version,
               decided_by_actor_id,adopted_care_action_id
        FROM eldercare_ai.care_action_candidate
        WHERE care_action_candidate_id IN ({CANDIDATES})
    """,
    "candidate_sources": f"""
        SELECT care_action_candidate_id,event_id,event_version_id,event_version,
               source_status,snapshot_sha256
        FROM eldercare_ai.care_action_candidate_event_provenance
        WHERE care_action_candidate_id IN ({CANDIDATES})
    """,
    "actions": f"""
        SELECT care_action_id,status,version,action_type,assignee_actor_id,
               created_by_actor_id,related_event_ids
        FROM eldercare_ai.care_action WHERE care_action_id IN ({ACTIONS})
    """,
    "action_sources": f"""
        SELECT care_action_id,event_id,event_version_id,event_version,source_status,snapshot_sha256
        FROM eldercare_ai.care_action_event_provenance WHERE care_action_id IN ({ACTIONS})
    """,
    "outbox": f"""
        SELECT event_id,event_type,aggregate_type,aggregate_id,aggregate_version
        FROM eldercare_ai.outbox_event WHERE aggregate_id IN ({SESSION})
        OR aggregate_id IN ({EVENTS}) OR aggregate_id IN ({ACTIONS})
        ORDER BY created_at,event_type
    """,
    "claims": f"""
        SELECT idempotency_key,status,resource_type,resource_id,response_status
        FROM eldercare_ai.idempotency_record WHERE tenant_id=CAST(:tenant AS uuid)
        AND (idempotency_key IN (:session_key,:turn_key,:review_key,:adopt_key)
        OR resource_id IN ({EVENTS}) OR resource_id IN ({CANDIDATES})
        OR resource_id IN ({ACTIONS})) ORDER BY idempotency_key
    """,
}


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "services/core-api"))
    from sqlalchemy import create_engine, text

    from app.core.config import get_settings
    from app.database_url import to_psycopg_database_url

    settings = get_settings()
    validate_target(settings.app_env, settings.database_url)
    engine = create_engine(
        to_psycopg_database_url(settings.database_url),
        hide_parameters=True,
        connect_args={"connect_timeout": 10},
    )
    params = {"run": RUN, "elder": ELDER, "tenant": TENANT}
    for step in ("session", "turn", "review", "adopt"):
        actor = (
            "20000000-0000-4000-8000-000000000001"
            if step in ("session", "turn")
            else "20000000-0000-4000-8000-000000000010"
        )
        digest = hashlib.sha256(f"{TENANT}:{actor}:{RUN}:{step}".encode()).hexdigest()
        params[f"{step}_key"] = f"v2:{digest}"
    try:
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            connection.execute(text("SET LOCAL statement_timeout = '10000'"))
            result = {
                name: [dict(row) for row in connection.execute(text(query), params).mappings()]
                for name, query in QUERIES.items()
            }
            digest = hashlib.sha256(
                json.dumps(result, sort_keys=True, default=str).encode()
            ).hexdigest()
            print(
                json.dumps(
                    {"campaign": RUN, "selected_metadata_sha256": digest, **result},
                    default=str,
                    indent=2,
                )
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"error_type": type(error).__name__}))
        raise SystemExit(1) from None
