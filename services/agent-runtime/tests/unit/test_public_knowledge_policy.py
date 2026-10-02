from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

from agent_runtime.rag.models import (
    HybridSearchPlan,
    PostgresSearchSettings,
    QueryEmbeddingSettings,
)
from agent_runtime.rag.postgres_backend import (
    POSTGRES_HYBRID_SEARCH_SQL,
    POSTGRES_PUBLIC_KNOWLEDGE_SEARCH_SQL,
    PostgresSearchBackend,
)
from agent_runtime.rag.public_knowledge_policy import (
    LEGACY_PUBLIC_PROJECT_SOURCE_IDS,
    RETIRED_BLOCK_REASONS,
    evaluate_public_knowledge,
)


def source(**changes):
    return {
        "data_classification": "public",
        "distribution_scope": "public_knowledge",
        "is_official_source": True,
        "direct_official_source_url": "https://example.gov.tw/source",
        "stop_normal_rag": False,
        "risk_level": "low",
        "allowed_audiences": ["elder"],
        "allowed_purposes": ["general_information", "legal_reference"],
        "current_status": "current",
        "retrieval_eligible": True,
        "retrieval_block_reasons": [],
        "requires_official_assessment": False,
        "requires_professional_assessment": False,
        "review_status": "needs_review",
        "production_approved": False,
        **changes,
    }


def evaluate(row, *, purpose="general_information", require_current=False):
    return evaluate_public_knowledge(
        row, audience="elder", purpose=purpose, require_current=require_current
    )


def test_needs_review_is_provenance_not_admission_gate():
    assert evaluate(source()).allowed


@pytest.mark.parametrize("block", RETIRED_BLOCK_REASONS)
def test_retired_blocks_allow_derived_false_eligibility(block):
    assert evaluate(source(retrieval_eligible=False, retrieval_block_reasons=[block])).allowed


def test_unknown_currency_is_general_information_only_with_warning():
    row = source(
        current_status="unknown",
        retrieval_eligible=False,
        retrieval_block_reasons=["current_status_not_current"],
    )
    decision = evaluate(row)
    assert decision.allowed
    assert decision.warnings == ("source_currency_unknown",)
    assert not evaluate(row, purpose="legal_reference").allowed
    assert not evaluate(row, require_current=True).allowed


def test_unknown_assessment_remains_unknown_with_conservative_advisory():
    row = source(requires_official_assessment=None, requires_professional_assessment=None)
    decision = evaluate(row)
    assert decision.allowed
    assert decision.requires_official_assessment is True
    assert decision.requires_professional_assessment is True
    assert len(decision.warnings) == 2
    assert row["requires_official_assessment"] is None


@pytest.mark.parametrize(
    "changes",
    [
        {"data_classification": "restricted"},
        {"data_classification": "internal"},
        {"distribution_scope": "private"},
        {"is_official_source": 1},
        {"is_official_source": False},
        {"stop_normal_rag": True},
        {"stop_normal_rag": None},
        {"risk_level": "high_red_line"},
        {"risk_level": "unknown"},
        {"allowed_audiences": []},
        {"allowed_audiences": ["care_professional"]},
        {"allowed_audiences": ["elder", ""]},
        {"allowed_purposes": []},
        {"allowed_purposes": ["legal_reference"]},
        {"current_status": "superseded"},
        {"retrieval_eligible": False},
        {"retrieval_block_reasons": ["stop_normal_rag"]},
        {"retrieval_block_reasons": ["unexpected_reason"]},
        {"retrieval_block_reasons": ["human_source_review_pending", "scope_denied"]},
        {"retrieval_block_reasons": [1]},
        {"requires_professional_assessment": "false"},
    ],
)
def test_restrictions_are_not_overridden(changes):
    assert not evaluate(source(**changes)).allowed


def test_currency_block_does_not_authorize_current_row_with_false_eligibility():
    assert not evaluate(
        source(retrieval_eligible=False, retrieval_block_reasons=["current_status_not_current"])
    ).allowed


def test_sql_predicate_structurally_matches_policy_without_legacy_allowlist():
    """Offline template parity check, not a claim that PostgreSQL was executed."""
    sql = POSTGRES_PUBLIC_KNOWLEDGE_SEARCH_SQL
    assert "554" not in sql
    assert ":policy_candidate_chunk_ids" not in sql
    assert (
        "OR (projection.production_approved IS TRUE AND projection.review_status = 'verified')"
        in sql
    )
    assert "release.release_status = 'STAGING_CANDIDATE'" in sql
    assert "release.production_approved IS FALSE" in sql
    assert "'public_knowledge'" in sql and "'public'" in sql
    assert "projection.provenance -> 'is_official_source' = 'true'::jsonb" in sql
    assert "projection.risk_level IN ('low', 'medium')" in sql
    assert "projection.stop_normal_rag IS FALSE" in sql
    assert "projection.current_status = 'unknown'" in sql
    assert "CAST(:purpose AS text) = 'general_information'" in sql
    assert "CAST(:require_current AS boolean) IS FALSE" in sql
    assert ":retired_block_reasons" in sql
    assert "cardinality(projection.allowed_audiences) > 0" in sql
    assert "cardinality(projection.allowed_purposes) > 0" in sql
    assert "embedding.embedding_text_sha256 = projection.embedding_text_sha256" in sql
    for invariant in (
        "profile.document_task_type = 'RETRIEVAL_DOCUMENT'",
        "projection_run.candidate_sha256 = release.candidate_sha256",
        "embedding_run.candidate_sha256 = release.candidate_sha256",
        "profile.dimension = CAST(:embedding_dimension AS integer)",
        "release.chunk_count = (",
    ):
        assert invariant in sql and invariant in POSTGRES_HYBRID_SEARCH_SQL


@pytest.mark.asyncio
async def test_opt_in_backend_binds_shared_policy_and_rechecks_returned_rows():
    class Connection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def execute(self, statement, parameters):
            compiled = statement.compile(dialect=postgresql.dialect())
            assert set(compiled.params) <= set(parameters)
            assert "spac" not in compiled.params
            if "eligible AS" in str(compiled):
                assert r"\S" in str(compiled)
            self.sql = str(statement)
            self.parameters = parameters
            rows = [
                {"score": 0.9, **source(current_status="unknown")},
                {"score": 0.9, **source(data_classification="restricted")},
            ]
            return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows))

    connection = Connection()
    engine = SimpleNamespace(connect=lambda: connection)
    backend = PostgresSearchBackend(
        engine,
        PostgresSearchSettings(
            database_url=SecretStr("postgresql+asyncpg://reader:synthetic@db.example.test/test"),
            release_id="knowledge-v007-123456789abc",
            embedding_profile_id="ep-google-synthetic",
            mode="staging",
        ),
        QueryEmbeddingSettings(provider="google", model_id="synthetic", dimension=1024),
    )
    plan = HybridSearchPlan(
        query="synthetic",
        query_vector=[0.01] * 1024,
        profile="natural_language",
        top_k=5,
        audience="elder",
        purpose="general_information",
        governed_citations=True,
        allow_needs_review=False,
        public_knowledge_mode=True,
        search_result_limit=50,
        bm25_weight=0.4,
        vector_weight=0.6,
        min_score=0.7,
    )
    for sql in (POSTGRES_PUBLIC_KNOWLEDGE_SEARCH_SQL, POSTGRES_HYBRID_SEARCH_SQL):
        parameters = backend._parameters(plan)
        compiled = (
            text(sql)
            .bindparams(**{key: parameters[key] for key in text(sql)._bindparams})
            .compile(dialect=postgresql.dialect())
        )
        assert set(compiled.params) <= set(parameters)
        assert "spac" not in compiled.params
    hits = await backend.search(plan)
    assert len(hits) == 1
    assert connection.sql == POSTGRES_PUBLIC_KNOWLEDGE_SEARCH_SQL
    assert connection.parameters["retired_block_reasons"] == list(RETIRED_BLOCK_REASONS)
    assert connection.parameters["require_current"] is False
    assert connection.parameters["policy_candidate_chunk_ids"] == []
    assert connection.parameters["top_k"] == 50
    assert await backend.search(plan.model_copy(update={"require_current": True})) == []


@pytest.mark.parametrize(
    "url",
    [
        "https://gov.tw.example.com/source",
        "https://user:secret@example.gov.tw/source",
        "https://example.gov.tw:99999/source",
        "https://example.gov.tw:bad/source",
        "https://example.gov.tw/source space",
        "ftp://example.gov.tw/source",
    ],
)
def test_runtime_official_url_validation(url):
    assert not evaluate(source(direct_official_source_url=url)).allowed


def test_official_url_precedence_matches_sql_and_citation():
    assert not evaluate(source(official_source_page_url="https://external.test/source")).allowed
    assert evaluate(source(direct_official_source_url="https://example.gov.tw:443/source")).allowed


@pytest.mark.parametrize("source_id", LEGACY_PUBLIC_PROJECT_SOURCE_IDS)
def test_legacy_public_project_documents_preserve_original_internal_metadata(source_id):
    row = source(
        source_id=source_id, data_classification="internal", distribution_scope="internal_knowledge"
    )
    assert evaluate(row).allowed
    assert row["data_classification"] == "internal"
    assert not evaluate({**row, "source_id": "unlisted-internal"}).allowed
    assert not evaluate({**row, "data_classification": "restricted"}).allowed
    assert not evaluate(
        {**row, "direct_official_source_url": "https://external.test/source"}
    ).allowed


def test_elder_and_older_adult_are_synonyms_but_caregiver_is_not():
    assert evaluate(source(allowed_audiences=["older_adult"])).allowed
    assert evaluate_public_knowledge(
        source(), audience="older_adult", purpose="general_information"
    ).allowed
    assert not evaluate(source(allowed_audiences=["caregiver"])).allowed
