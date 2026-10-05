"""Synthetic I/O exercises the real V3 retriever/service without external calls."""

import importlib.util
import json
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_runtime.rag.evidence_models import RetrievalResultV3
from agent_runtime.rag.evidence_service import EvidenceService
from agent_runtime.rag.hybrid_search import HybridSearch
from agent_runtime.rag.knowledge_evaluation import (
    CallCounts,
    CandidateRecorder,
    CountedEmbedding,
    CountedProvider,
    KnowledgeEvaluationError,
    SmokeCase,
    _quote_diagnostics,
    _selected_support_spans,
    evaluate_cases,
    load_cases,
)
from agent_runtime.rag.models import HybridProfileSettings, HybridSearchSettings
from agent_runtime.rag.retriever import Retriever
from agent_runtime.rag.search_backend import SearchHit

ROOT = Path(__file__).resolve().parents[4]
SPEC = importlib.util.spec_from_file_location(
    "evaluate_knowledge", ROOT / "scripts/rag/evaluate_knowledge.py"
)
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)
PROFILE = {
    "profile_id": "ep-google-synthetic",
    "provider": "google",
    "model_id": "synthetic-001",
    "model_version": "synthetic-001",
    "dimension": 1024,
    "document_task_type": "RETRIEVAL_DOCUMENT",
    "config_version": "1.0.0",
}


@pytest.mark.parametrize(
    "quote,category",
    [
        ("public evidence", "exact"),
        ("public\n evidence", "whitespace-only"),
        ("ＡＢＣ", "unicode-normalization-only"),
        ("Ａ Ｂ\nＣ", "unicode-and-whitespace"),
        ("SECRET_QUOTE", "content-mismatch"),
    ],
)
def test_quote_diagnostics_only_export_counts(quote, category):
    raw = json.dumps({"support_quotes": [{"chunk_id": "one", "quote": quote}]})
    diagnostics = _quote_diagnostics(
        raw, [SimpleNamespace(chunk_id="one", text="public evidence ABC")]
    )
    assert diagnostics == {category: 1}
    assert quote not in json.dumps(diagnostics)


def test_span_diagnostics_export_only_validated_source_ids_and_counts():
    from agent_runtime.rag.grounded_answer import evidence_quote_spans

    source = result()
    span_id = next(iter(evidence_quote_spans(source.text)))
    support = {"chunk_id": source.chunk_id, "span_id": span_id}
    document = {
        "status": "ANSWER",
        "answer_text": "Synthetic answer.",
        "citation_ids": [source.chunk_id],
        "support_quotes": [support],
        "missing_facets": [],
    }
    raw = json.dumps(document)
    assert _quote_diagnostics(raw, [source]) == {"source-span": 1}
    assert _selected_support_spans(raw, [source]) == [support]
    document["support_quotes"] = [{"chunk_id": source.chunk_id, "span_id": "SECRET_FAKE_ID"}]
    raw = json.dumps(document)
    assert _quote_diagnostics(raw, [source]) == {"unknown-span": 1}
    assert _selected_support_spans(raw, [source]) == []


def case(identifier="first", **changes):
    return SmokeCase(
        **{
            "id": identifier,
            "query": "如何申請測試服務？",
            "audience": "elder",
            "purpose": "general_information",
            "expectation": "answer",
            "anchor_source_ids": ("synthetic_official_guide",),
            "anchor_text_any": ("eligibility",),
            "notes": "Synthetic developer diagnostic, not semantic ground truth.",
            **changes,
        }
    )


def result():
    document = json.loads(
        (ROOT / "contracts/examples/valid/retrieval-response-v3.json").read_text(encoding="utf-8")
    )
    return RetrievalResultV3.model_validate(document["data"]["results"][0])


class FakeEmbedding:
    dimension = 1024

    async def embed_query(self, query):
        return [0.1] * self.dimension

    async def aclose(self):
        pass


class FakeProvider:
    def __init__(self, failure=None):
        self.failure = failure

    async def generate_reply(self, request, manifest, language):
        if self.failure:
            raise self.failure
        source = result()
        return json.dumps(
            {
                "status": "ANSWER",
                "answer_text": "這是合成的申請說明。",
                "citation_ids": [source.chunk_id],
                "support_quotes": [{"chunk_id": source.chunk_id, "quote": source.text}],
                "missing_facets": [],
            },
            ensure_ascii=False,
        )

    async def aclose(self):
        pass


def runtime(failure=None):
    sample = result()
    source = {
        **sample.model_dump(),
        "release_id": "synthetic-release",
        "embedding_profile_id": PROFILE["profile_id"],
        "text_sha256": sha256(sample.text.encode()).hexdigest(),
        "data_classification": "public",
        "distribution_scope": "public_knowledge",
        "stop_normal_rag": False,
        "risk_level": "low",
        "retrieval_eligible": True,
        "retrieval_block_reasons": [],
        "requires_official_assessment": None,
        "requires_professional_assessment": False,
        "allowed_audiences": ["elder"],
        "allowed_purposes": ["general_information"],
    }

    class Backend:
        def __init__(self):
            self.calls = []

        async def search(self, plan):
            self.calls.append(plan)
            return [SearchHit(0.9, source, raw_vector_score=0.9)]

        async def aclose(self):
            pass

    def profile(name):
        return HybridProfileSettings(
            profile=name,
            search_pipeline=f"synthetic-{name}",
            bm25_weight=0.4,
            vector_weight=0.6,
            vector_min_score=0.7,
            top_k=5,
            agent_chunk_min=3,
            agent_chunk_max=5,
        )

    counts = CallCounts()
    backend = Backend()
    retriever = Retriever(
        embedding_provider=CountedEmbedding(FakeEmbedding(), counts),
        search_backend=backend,
        hybrid_search=HybridSearch(
            HybridSearchSettings(
                natural_language=profile("natural_language"),
                legal=profile("legal"),
            )
        ),
        public_release_id="synthetic-release",
        public_embedding_profile_id=PROFILE["profile_id"],
    )
    recorder = CandidateRecorder(retriever)
    service = EvidenceService(
        retriever=recorder,
        provider=CountedProvider(FakeProvider(failure), counts),
        release_id="synthetic-release",
        embedding_profile_id=PROFILE["profile_id"],
    )
    return service, counts, recorder, backend


def test_default_plan_makes_no_external_calls_loads_no_settings_or_writes(
    tmp_path, monkeypatch, capsys
):
    def forbidden(*args, **kwargs):
        raise AssertionError("live runtime must not run")

    monkeypatch.setattr(CLI, "run_live", forbidden)
    destination = tmp_path / "not-created.json"
    assert (
        CLI.main(
            ["--case-id", "apply-family", "law-article3-definition", "--output", str(destination)]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["case_count"] == 2
    assert output["settings_loaded"] is False
    assert output["query_embedding_calls"] == output["generation_calls"] == 0
    assert not destination.exists()


def test_cases_limit_and_selection_are_explicit(tmp_path):
    path = tmp_path / "cases.json"
    document = json.loads(
        (ROOT / "config/rag/knowledge-smoke-queries.json").read_text(encoding="utf-8")
    )
    path.write_text(json.dumps(document), encoding="utf-8")
    assert len(load_cases(path)[1]) == 16
    with pytest.raises(KnowledgeEvaluationError, match="INVALID_CASE_SELECTION"):
        load_cases(path, ["not-a-case"])
    document["cases"].append(document["cases"][0])
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(KnowledgeEvaluationError, match="CASE_LIMIT_EXCEEDED"):
        load_cases(path)


def test_mock_is_rejected_without_constructing_generation_client():
    with pytest.raises(KnowledgeEvaluationError, match="REAL_GENERATION_PROVIDER_REQUIRED"):
        CLI._generation_provider(SimpleNamespace(MODEL_PROVIDER="mock"))


def test_cli_sanitizes_unexpected_live_failure_without_creating_report(monkeypatch, capsys):
    async def fail(*args, **kwargs):
        raise RuntimeError("SECRET_DATABASE_PASSWORD")

    monkeypatch.setattr(CLI, "run_live", fail)
    assert (
        CLI.main(
            [
                "--live",
                "--case-id",
                "apply-family",
                "--output",
                str(ROOT / ".rag-work/test-unused-report.json"),
            ]
        )
        == 1
    )
    output = capsys.readouterr().out
    assert "SECRET_DATABASE_PASSWORD" not in output
    assert json.loads(output)["error"] == "SMOKE_EXECUTION_FAILED"
    assert not (ROOT / ".rag-work/test-unused-report.json").exists()


@pytest.mark.asyncio
async def test_real_retriever_service_are_sequential_bounded_and_report_honest_proxies():
    service, counts, recorder, backend = runtime()
    clock_values = iter([1.0, 1.25, 2.0, 2.5])
    report = await evaluate_cases(
        service,
        [case(), case("second")],
        cases_version="synthetic-v1",
        counts=counts,
        recorder=recorder,
        clock=lambda: next(clock_values),
    )
    assert report["summary"]["query_embedding_calls"] == report["summary"]["generation_calls"] == 2
    assert report["summary"]["statuses"] == {"SUCCESS": 2}
    assert report["cases"][0]["elapsed_ms"] == 250
    assert report["cases"][1]["elapsed_ms"] == 500
    assert len(backend.calls) == 2
    row = report["cases"][0]
    assert row["retrieved_candidates"][0]["text"] == result().text
    assert row["anchor_proxy"]["source_id_any"] is True
    assert row["anchor_proxy"]["text_any"] is True
    assert row["anchor_proxy"]["semantic_ground_truth"] is False
    assert report["semantic_accuracy_verified"] is False and report["quality_score"] is None
    assert "引用來源" in row["answer_text"]
    assert row["expected_outcome_observed"] is True


@pytest.mark.asyncio
async def test_provider_failure_is_sanitized_and_classified():
    service, counts, recorder, _ = runtime(RuntimeError("SECRET_API_KEY and connection URL"))
    report = await evaluate_cases(
        service,
        [case()],
        cases_version="synthetic",
        counts=counts,
        recorder=recorder,
    )
    row = report["cases"][0]
    assert row["status"] == "FAILED"
    assert row["failure_category"] == "GENERATION_OR_ENVELOPE_FAILED"
    assert "SECRET_API_KEY" not in json.dumps(report)
    assert row["answer_text"] is None
    assert row["generation_diagnostic_code"] == "GENERATION_PROVIDER_EXCEPTION"
    assert row["generation_exception_type"] == "RuntimeError"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_kind,expected",
    [
        ("json", "INVALID_GENERATION_JSON"),
        ("quote", "SUPPORT_QUOTE_NOT_IN_SOURCE"),
    ],
)
async def test_generation_diagnostics_are_fixed_codes_and_reset_without_raw_leaks(
    invalid_kind, expected
):
    service, counts, recorder, _ = runtime()
    valid = await FakeProvider().generate_reply(None, None, "zh-TW")
    if invalid_kind == "json":
        invalid = "SECRET_RAW_PROVIDER_OUTPUT{"
    else:
        document = json.loads(valid)
        document["support_quotes"][0]["quote"] = "SECRET_RAW_PROVIDER_OUTPUT"
        invalid = json.dumps(document)
    outputs = iter([invalid, valid])

    async def generate(*args):
        return next(outputs)

    service.provider.inner.generate_reply = generate
    report = await evaluate_cases(
        service,
        [case(), case("second")],
        cases_version="synthetic",
        counts=counts,
        recorder=recorder,
    )
    assert report["cases"][0]["generation_diagnostic_code"] == expected
    assert report["cases"][1]["generation_diagnostic_code"] is None
    assert report["cases"][1]["status"] == "SUCCESS"
    assert "SECRET_RAW_PROVIDER_OUTPUT" not in json.dumps(report)
    assert report["summary"]["generation_calls"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "finish_reason,expected",
    [
        ("MAX_TOKENS", "GENERATION_JSON_TRUNCATED_MAX_TOKENS"),
        ("STOP", "INVALID_GENERATION_JSON"),
    ],
)
async def test_truncation_requires_provider_finish_reason(finish_reason, expected):
    from agent_runtime.models.generation_diagnostics import record_generation_diagnostics

    service, counts, recorder, _ = runtime()

    async def generate(*args):
        raw = "SECRET_PROVIDER_REPLY{"
        record_generation_diagnostics(
            SimpleNamespace(
                text=raw,
                candidates=[SimpleNamespace(finish_reason=finish_reason)],
                usage_metadata=SimpleNamespace(prompt_token_count=100, candidates_token_count=40),
            )
        )
        return raw

    service.provider.inner.generate_reply = generate
    report = await evaluate_cases(
        service, [case()], cases_version="synthetic", counts=counts, recorder=recorder
    )
    row = report["cases"][0]
    assert row["generation_diagnostic_code"] == expected
    assert row["generation_metadata"]["finish_reason"] == finish_reason
    assert row["generation_metadata"]["prompt_token_count"] == 100
    assert "SECRET_PROVIDER_REPLY" not in json.dumps(report)
    assert report["summary"]["generation_calls"] == 1


@pytest.mark.asyncio
async def test_safety_case_stops_before_embedding_or_generation():
    service, counts, recorder, backend = runtime()
    report = await evaluate_cases(
        service,
        [case(query="我想停藥，該怎麼停？", expectation="safety")],
        cases_version="synthetic",
        counts=counts,
        recorder=recorder,
    )
    assert report["summary"]["query_embedding_calls"] == report["summary"]["generation_calls"] == 0
    assert report["cases"][0]["expected_outcome_observed"] is True
    assert not backend.calls


@pytest.mark.asyncio
async def test_retrieval_only_preserves_the_same_safety_precheck():
    service, counts, recorder, backend = runtime()
    report = await evaluate_cases(
        service,
        [case(query="請給我停藥建議", expectation="safety")],
        cases_version="synthetic",
        counts=counts,
        recorder=recorder,
        retrieval_only=True,
    )
    assert report["cases"][0]["expected_outcome_observed"] is True
    assert not backend.calls
    assert counts.query_embeddings == counts.generations == 0


@pytest.mark.asyncio
async def test_call_wrappers_refuse_a_second_call_per_case():
    counts = CallCounts()
    embedding = CountedEmbedding(FakeEmbedding(), counts)
    provider = CountedProvider(FakeProvider(), counts)
    await embedding.embed_query("synthetic")
    await provider.generate_reply(None, None, "zh-TW")
    with pytest.raises(KnowledgeEvaluationError, match="QUERY_EMBEDDING_CALL_LIMIT"):
        await embedding.embed_query("synthetic")
    with pytest.raises(KnowledgeEvaluationError, match="GENERATION_CALL_LIMIT"):
        await provider.generate_reply(None, None, "zh-TW")
    assert counts.query_embeddings == counts.generations == 1


class FakeReadonlyConnection:
    def __init__(self, readonly="on", default_readonly="off", set_failure=None):
        self.readonly = readonly
        self.default_readonly = default_readonly
        self.set_failure = set_failure
        self.statements = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def execute(self, statement, parameters=None):
        sql = str(statement).strip()
        self.statements.append((sql, parameters))
        if sql.startswith("SET TRANSACTION"):
            if self.set_failure:
                raise self.set_failure
            return SimpleNamespace()
        if sql.startswith("SHOW"):
            return SimpleNamespace(
                scalar_one=lambda: (
                    self.default_readonly if "default_transaction" in sql else self.readonly
                )
            )
        row = {
            **PROFILE,
            "embedding_profile_id": PROFILE["profile_id"],
            "release_id": CLI.DEFAULT_RELEASE,
            "release_status": "STAGING_CANDIDATE",
            "production_approved": False,
            "chunk_count": 726,
            "projection_count": 726,
            "vector_count": 726,
            "matching_vector_count": 726,
        }
        return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: [row]))


@pytest.mark.asyncio
async def test_preflight_verifies_read_only_and_exact_profile_and_coverage():
    connection = FakeReadonlyConnection()
    backend = SimpleNamespace(
        _engine=SimpleNamespace(connect=lambda: connection),
        _settings=SimpleNamespace(statement_timeout_ms=10000),
    )
    preflight = await CLI.read_only_preflight(
        backend,
        release_id=CLI.DEFAULT_RELEASE,
        profile=PROFILE,
        expected_count=726,
    )
    assert preflight["read_only_enforced"] is True
    assert preflight["read_only_enforcement"] == "EXPLICIT_TRANSACTION"
    assert preflight["default_transaction_read_only_observed_on"] is False
    assert preflight["dataset"] == "EXISTING_V004_726"
    assert preflight["v007_658_dataset_tested"] is False
    assert connection.statements[0][0] == "SET TRANSACTION READ ONLY"
    assert all(
        sql.startswith(("SET TRANSACTION", "SHOW", "SELECT")) for sql, _ in connection.statements
    )
    assert connection.statements[-1][1] == {
        "release_id": CLI.DEFAULT_RELEASE,
        "profile_id": PROFILE["profile_id"],
    }
    with pytest.raises(KnowledgeEvaluationError, match="DATABASE_PROFILE_METADATA_MISMATCH"):
        await CLI.read_only_preflight(
            backend,
            release_id=CLI.DEFAULT_RELEASE,
            profile={**PROFILE, "model_id": "different"},
            expected_count=726,
        )


@pytest.mark.asyncio
async def test_preflight_refuses_nonreadonly_connection():
    connection = FakeReadonlyConnection(readonly="off")
    backend = SimpleNamespace(
        _engine=SimpleNamespace(connect=lambda: connection),
        _settings=SimpleNamespace(statement_timeout_ms=10000),
    )
    with pytest.raises(KnowledgeEvaluationError, match="DATABASE_CONNECTION_NOT_READ_ONLY"):
        await CLI.read_only_preflight(
            backend,
            release_id=CLI.DEFAULT_RELEASE,
            profile=PROFILE,
            expected_count=726,
        )
    assert not any("FROM rag_public" in sql for sql, _ in connection.statements)


@pytest.mark.asyncio
async def test_preflight_readonly_configuration_failure_never_selects_source_data():
    connection = FakeReadonlyConnection(set_failure=RuntimeError("SECRET connection detail"))
    backend = SimpleNamespace(
        _engine=SimpleNamespace(connect=lambda: connection),
        _settings=SimpleNamespace(statement_timeout_ms=10000),
    )
    with pytest.raises(RuntimeError):
        await CLI.read_only_preflight(
            backend,
            release_id=CLI.DEFAULT_RELEASE,
            profile=PROFILE,
            expected_count=726,
        )
    assert len(connection.statements) == 1
    assert connection.statements[0][0] == "SET TRANSACTION READ ONLY"


@pytest.mark.asyncio
async def test_retrieval_only_performs_no_generation():
    service, counts, recorder, _ = runtime()
    report = await evaluate_cases(
        service,
        [case()],
        cases_version="synthetic",
        counts=counts,
        recorder=recorder,
        retrieval_only=True,
    )
    assert report["summary"]["query_embedding_calls"] == 1
    assert report["summary"]["generation_calls"] == 0
    assert report["cases"][0]["status"] == "RETRIEVAL_ONLY"
    assert report["cases"][0]["answer_text"] is None
