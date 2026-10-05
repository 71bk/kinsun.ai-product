"""Scripted offline natural RAG tests; not real model-quality evaluation."""

import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

import agent_runtime.app as app_module
from agent_runtime.app import build_configured_evidence_service
from agent_runtime.common.errors import ModelDependencyError
from agent_runtime.rag.evidence_models import (
    RetrievalRequestV3,
    RetrievalResponseV3,
    RetrievalResultV3,
)
from agent_runtime.rag.evidence_service import EvidenceService
from agent_runtime.rag.models import RetrievalResultV2
from agent_runtime.settings import Settings

ROOT = Path(__file__).resolve().parents[4]
TEXT = "申請長照服務可以撥打1966，由照管專員到府評估。"


def citation(**changes):
    row = json.loads(
        (ROOT / "contracts/examples/valid/retrieval-response-v3.json").read_text(encoding="utf-8")
    )["data"]["results"][0]
    row.update(
        chunk_id="source-1", text=TEXT, review_status="needs_review", production_approved=False
    )
    row.update(changes)
    return RetrievalResultV3.model_validate(row)


def request(query="我想幫媽媽申請長照，第一步該怎麼做？", **changes):
    data = dict(
        schema_version="3.0.0",
        request_id="natural-request",
        query=query,
        query_profile="natural_language",
        top_k=5,
        audience="family_caregiver",
        purpose="general_information",
    )
    data.update(changes)
    return RetrievalRequestV3(**data)


class Loader:
    def __init__(self, rows=None, failure=False):
        self.rows = [citation()] if rows is None else rows
        self.failure, self.calls = failure, []

    async def load_public_candidates(self, req, *, require_current):
        self.calls.append((req, require_current))
        if self.failure:
            raise RuntimeError("private-database-secret")
        return self.rows


class Provider:
    def __init__(self, output=None, failure=False):
        self.output = output or dict(
            status="ANSWER",
            answer_text="可以先撥打1966申請長照。",
            citation_ids=["source-1"],
            support_quotes=[dict(chunk_id="source-1", quote="申請長照服務可以撥打1966")],
            missing_facets=[],
        )
        self.failure, self.calls = failure, []

    async def generate_reply(self, req, context_manifest, language):
        self.calls.append((req, context_manifest, language))
        if self.failure:
            raise RuntimeError("private-provider-secret")
        return json.dumps(self.output, ensure_ascii=False)


def service(loader=None, provider=None):
    return EvidenceService(
        retriever=loader or Loader(),
        provider=provider or Provider(),
        release_id="local-release",
        embedding_profile_id="google-1024",
    )


def failure_events(caplog):
    records = [r for r in caplog.records if r.name == "agent_runtime.rag.diagnostics"]
    assert all(r.exc_info is None and r.stack_info is None for r in records)
    return [json.loads(r.getMessage()) for r in records]


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["retrieval", "generation", "json", "citation"])
async def test_failure_diagnostics_classify_without_content(caplog, phase):
    class InvalidJson(Provider):
        async def generate_reply(self, *args):
            return "private-model-output"

    loader, provider = Loader(), Provider()
    expected = (phase, f"{phase.upper()}_FAILED")
    if phase == "retrieval":
        loader.failure = True
    elif phase == "generation":
        provider.failure = True
    elif phase == "json":
        provider = InvalidJson()
        expected = ("validation", "JSON_REJECTED")
    else:
        provider.output["support_quotes"][0]["quote"] = "private-forged-quote"
        expected = ("validation", "CITATION_REJECTED")
    req = request(request_id="private-request-id")
    response = await service(loader, provider).retrieve_v3(req)
    assert response.status == "FAILED"
    [event] = failure_events(caplog)
    assert (event["stage"], event["code"]) == expected
    assert event["request_tag"] == hashlib.sha256(req.request_id.encode()).hexdigest()[:16]
    assert event["elapsed_ms"] >= 0
    assert set(event) == {"event", "request_tag", "stage", "code", "elapsed_ms"}
    assert "private-" not in caplog.text
    assert req.query not in caplog.text
    assert TEXT not in caplog.text


@pytest.mark.asyncio
async def test_wrapped_provider_timeout_is_classified_without_traceback(caplog):
    class TimedOut(Provider):
        async def generate_reply(self, *args):
            try:
                raise httpx.ReadTimeout("private-url-and-prompt")
            except httpx.ReadTimeout as exc:
                raise ModelDependencyError("private-wrapper") from exc

    assert (await service(provider=TimedOut()).retrieve_v3(request())).status == "FAILED"
    [event] = failure_events(caplog)
    assert (event["stage"], event["code"]) == ("generation", "GENERATION_TIMEOUT")
    assert "private-" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("external", [False, True])
async def test_deadline_and_cancellation_are_distinct_and_emit_once(caplog, monkeypatch, external):
    entered = asyncio.Event()

    class Blocked(Provider):
        async def generate_reply(self, *args):
            entered.set()
            await asyncio.Event().wait()

    if not external:
        original_timeout = asyncio.timeout
        monkeypatch.setattr(asyncio, "timeout", lambda _: original_timeout(0.03))
    task = asyncio.create_task(service(provider=Blocked()).retrieve_v3(request()))
    await entered.wait()
    if external:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        assert (await task).status == "FAILED"
    [event] = failure_events(caplog)
    assert event["stage"] == "generation"
    assert event["code"] == ("REQUEST_CANCELLED" if external else "DEADLINE_EXCEEDED")
    caplog.clear()
    assert (await service().retrieve_v3(request())).status == "SUCCESS"
    assert failure_events(caplog) == []


@pytest.mark.asyncio
async def test_concurrent_requests_keep_failure_stage_and_tag_isolated(caplog):
    entered, release = asyncio.Event(), asyncio.Event()

    class Interleaved(Provider):
        async def generate_reply(self, *args):
            entered.set()
            await release.wait()
            raise RuntimeError("private-interleaved-prompt")

    first = asyncio.create_task(
        service(provider=Interleaved()).retrieve_v3(request(request_id="generation-request"))
    )
    await entered.wait()
    second = await service(loader=Loader(failure=True)).retrieve_v3(
        request(request_id="retrieval-request")
    )
    release.set()
    assert (await first).status == second.status == "FAILED"
    events = failure_events(caplog)
    assert len(events) == 2
    for event, stage in zip(events, ["retrieval", "generation"], strict=True):
        assert event["stage"] == stage
        assert event["code"] == f"{stage.upper()}_FAILED"
        assert event["request_tag"] == hashlib.sha256(f"{stage}-request".encode()).hexdigest()[:16]
    assert "private-" not in caplog.text


@pytest.mark.asyncio
async def test_unknown_validation_reason_never_enters_logs(caplog, monkeypatch):
    import agent_runtime.rag.grounded_answer as grounded

    def rejected(*args):
        raise grounded.GroundedAnswerError("private-unknown-validation-reason")

    monkeypatch.setattr(grounded, "parse_grounded_answer", rejected)
    assert (await service().retrieve_v3(request())).status == "FAILED"
    [event] = failure_events(caplog)
    assert event["code"] == "VALIDATION_REJECTED"
    assert "private-" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["retrieval", "context", "response"])
async def test_other_pipeline_failures_keep_their_actual_stage(caplog, monkeypatch, phase):
    import agent_runtime.rag.evidence_service as evidence
    import agent_runtime.rag.grounded_answer as grounded

    loader = Loader()
    if phase == "retrieval":

        async def fail(*args, **kwargs):
            raise TimeoutError("private-retrieval-timeout")

        monkeypatch.setattr(loader, "load_public_candidates", fail)
        expected = "RETRIEVAL_TIMEOUT"
    elif phase == "context":

        def fail(*args, **kwargs):
            raise grounded.GroundedAnswerError("private-context-error")

        monkeypatch.setattr(grounded, "build_grounded_context", fail)
        expected = "CONTEXT_REJECTED"
    else:

        def fail(*args, **kwargs):
            raise ValueError("private-response-error")

        monkeypatch.setattr(evidence, "append_citations", fail)
        expected = "RESPONSE_FAILED"
    assert (await service(loader=loader).retrieve_v3(request())).status == "FAILED"
    [event] = failure_events(caplog)
    assert (event["stage"], event["code"]) == (phase, expected)
    assert "private-" not in caplog.text


@pytest.mark.asyncio
async def test_expected_no_data_and_safety_denial_are_not_failure_logs(caplog):
    assert (await service(loader=Loader(rows=[])).retrieve_v3(request())).status == "NO_DATA"
    assert (await service().retrieve_v3(request("我要自行停藥，怎麼做？"))).status == "NO_DATA"
    assert failure_events(caplog) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query", ["我想幫媽媽申請長照，第一步該怎麼做？", "家中長輩需要照顧，要找哪裡申請？"]
)
async def test_natural_paraphrase_one_unreviewed_source_is_enough(query):
    loader, provider = Loader(), Provider()
    response = await service(loader, provider).retrieve_v3(request(query))
    assert response.status == "SUCCESS"
    assert response.decision == "SUFFICIENT"
    assert len(response.results) == 1
    assert response.results[0].review_status == "needs_review"
    assert response.policy_version == "public-knowledge-v1"
    assert response.embedding_profile_id == "google-1024"
    assert loader.calls[0][0].query == query
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_five_irrelevant_results_do_not_force_an_answer():
    rows = [citation(chunk_id=f"irrelevant-{i}", text="這是營養飲食資訊。") for i in range(5)]
    provider = Provider(
        dict(
            status="INSUFFICIENT",
            answer_text=None,
            citation_ids=[],
            support_quotes=[],
            missing_facets=["申請方式"],
        )
    )
    response = await service(Loader(rows), provider).retrieve_v3(request())
    assert response.status == "NO_DATA"
    assert response.answer_text is None
    assert response.results == []


@pytest.mark.asyncio
async def test_partial_answer_keeps_supported_part_and_names_gap():
    provider = Provider(
        dict(
            status="PARTIAL",
            answer_text="可先撥打1966；費用資料不足。",
            citation_ids=["source-1"],
            support_quotes=[dict(chunk_id="source-1", quote="申請長照服務可以撥打1966")],
            missing_facets=["服務費用"],
        )
    )
    response = await service(provider=provider).retrieve_v3(request("如何申請，費用多少？"))
    assert response.status == "SUCCESS"
    assert response.decision == "PARTIAL"
    assert response.missing_facets == ["服務費用"]
    assert len(response.results) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["retrieval", "generation"])
async def test_provider_failure_is_explicit_without_private_details(boundary):
    response = await service(
        Loader(failure=boundary == "retrieval"), Provider(failure=boundary == "generation")
    ).retrieve_v3(request())
    assert response.status == "FAILED"
    assert response.results == []
    assert response.answer_text is None
    assert "private-" not in response.model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["citation", "quote"])
async def test_false_citations_fail_closed(defect):
    provider = Provider()
    if defect == "citation":
        provider.output["citation_ids"] = ["invented-source"]
    else:
        provider.output["support_quotes"][0]["quote"] = "這句話不存在於來源。"
    response = await service(provider=provider).retrieve_v3(request())
    assert response.status != "SUCCESS"
    assert response.answer_text is None
    assert response.results == []


def test_v3_currency_is_explicit_without_widening_v2_contract():
    row = citation(current_status="unknown")
    assert row.current_status == "unknown"
    with pytest.raises(ValidationError):
        RetrievalResultV2.model_validate(row.model_dump())
    with pytest.raises(ValidationError):
        citation(current_status="superseded")
    payload = row.model_dump()
    del payload["current_status"]
    with pytest.raises(ValidationError):
        RetrievalResultV3.model_validate(payload)


def test_partial_wire_requires_missing_facets():
    with pytest.raises(ValidationError):
        RetrievalResponseV3(
            request_id="test-request",
            status="SUCCESS",
            decision="PARTIAL",
            results=[citation()],
            answer_text="有來源支持的文字。",
            release_id="release",
            embedding_profile_id="profile",
            policy_version="public-knowledge-v1",
        )


@pytest.mark.asyncio
async def test_unknown_currency_is_exposed_without_inventing_current_status():
    loader = Loader([citation(current_status="unknown", warnings=["SOURCE_CURRENCY_UNKNOWN"])])
    response = await service(loader=loader).retrieve_v3(request())
    assert response.status == "SUCCESS"
    assert response.results[0].current_status == "unknown"
    assert response.results[0].warnings
    assert "尚未確認是否仍為現行版本" in response.answer_text
    assert loader.calls[0][1] is False


@pytest.mark.asyncio
async def test_legal_request_requires_current_sources():
    loader = Loader([])
    response = await service(loader=loader).retrieve_v3(
        request("法律規定是什麼？", purpose="legal_reference", query_profile="legal")
    )
    assert loader.calls[0][1] is True
    assert response.status == "NO_DATA"


def test_request_profile_still_matches_purpose():
    with pytest.raises(ValidationError):
        request(purpose="legal_reference", query_profile="natural_language")


@pytest.mark.parametrize(
    "url",
    [
        "https://user:password@mohw.gov.tw/guide",
        "https://example.test/guide",
        "https://mohw.gov.tw.example.test/guide",
        "https://mohw.gov.tw/has space",
    ],
)
def test_v3_selected_source_url_must_be_public_government_url(url):
    with pytest.raises(ValidationError):
        citation(official_source_page_url=url)


def test_v3_rejects_credentials_even_on_nonselected_url():
    with pytest.raises(ValidationError):
        citation(source_page_url="https://user:password@example.test/guide")


def test_v3_rejects_nonofficial_source():
    with pytest.raises(ValidationError):
        citation(
            is_official_source=False, direct_official_source_url=None, official_source_page_url=None
        )


def startup_settings(**changes):
    values = dict(
        _env_file=None,
        APP_ENV="test",
        RAG_EVIDENCE_V3_ENABLED=True,
        RAG_MODE="staging",
        RAG_SEARCH_BACKEND="postgresql",
        RAG_POSTGRES_RELEASE_ID="local-release",
        RAG_POSTGRES_EMBEDDING_PROFILE_ID="google-1024",
        RAG_STAGING_ALLOW_ALL_AUDIENCES=False,
    )
    values.update(changes)
    return Settings(**values)


def startup_loader(**changes):
    values = dict(public_release_id="local-release", public_embedding_profile_id="google-1024")
    values.update(changes)
    return SimpleNamespace(**values)


def test_v3_disabled_by_default():
    assert build_configured_evidence_service(Settings(_env_file=None), None, None) is None


def test_v3_startup_needs_no_old_manual_policy_paths():
    result = build_configured_evidence_service(startup_settings(), startup_loader(), Provider())
    assert isinstance(result, EvidenceService)


@pytest.mark.parametrize("defect", ["release", "profile", "provider", "production", "override"])
def test_v3_rejects_configuration_drift_or_unsafe_startup(defect):
    settings, loader, provider = startup_settings(), startup_loader(), Provider()
    if defect == "release":
        loader.public_release_id = "different-release"
    elif defect == "profile":
        loader.public_embedding_profile_id = "different-profile"
    elif defect == "provider":
        provider = None
    elif defect == "production":
        settings = startup_settings(APP_ENV="production")
    else:
        settings = startup_settings(RAG_STAGING_ALLOW_ALL_AUDIENCES=True)
    with pytest.raises(ValueError):
        build_configured_evidence_service(settings, loader, provider)


@pytest.mark.asyncio
async def test_conflicting_current_versions_refuse_without_model_call():
    loader = Loader(
        [citation(source_version="2024"), citation(chunk_id="source-2", source_version="2025")]
    )
    provider = Provider()
    response = await service(loader, provider).retrieve_v3(request())
    assert response.status == "NO_DATA"
    assert "SOURCE_VERSION_CONFLICT" in response.reason_codes
    assert not provider.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["今年可以領多少補助？", "目前長照給付額度是多少？"])
async def test_current_benefit_questions_reject_unknown_sources(query):
    loader, provider = Loader([citation(current_status="unknown")]), Provider()
    response = await service(loader, provider).retrieve_v3(request(query))
    assert response.status == "NO_DATA"
    assert loader.calls[0][1] is True
    assert not provider.calls


@pytest.mark.asyncio
async def test_unsafe_medication_text_in_partial_gap_is_blocked():
    provider = Provider(
        dict(
            status="PARTIAL",
            answer_text="可先撥打1966申請長照。",
            citation_ids=["source-1"],
            support_quotes=[dict(chunk_id="source-1", quote="申請長照服務可以撥打1966")],
            missing_facets=["建議先停藥"],
        )
    )
    response = await service(provider=provider).retrieve_v3(request())
    assert response.status == "NO_DATA"
    assert "SAFETY_GATE" in response.reason_codes
    assert response.results == []
    assert response.answer_text is None


def stub_factory(monkeypatch, settings, *, policy=None):
    calls = []
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    runtime = SimpleNamespace(embedding=SimpleNamespace(provider="test"), allow_all_audiences=False)
    monkeypatch.setattr(app_module.RagRuntimeSettings, "from_config_files", lambda **kw: runtime)

    def load_policy(*args, **kwargs):
        calls.append("policy")
        if policy is None:
            raise FileNotFoundError("synthetic historical policy unavailable")
        return policy

    def build(*args, **kwargs):
        calls.append(kwargs)
        return startup_loader()

    monkeypatch.setattr(app_module, "load_source_family_runtime_policy", load_policy)
    monkeypatch.setattr(app_module, "build_retriever", build)
    return calls


@pytest.mark.parametrize(
    "path,hash_value",
    [
        ("missing-old-policy.json", None),
        (None, "a" * 64),
        ("missing-old-policy.json", "a" * 64),
    ],
)
def test_v3_factory_ignores_leftover_legacy_policy_configuration(monkeypatch, path, hash_value):
    settings = startup_settings(
        RAG_SOURCE_FAMILY_POLICY_PATH=path, RAG_SOURCE_FAMILY_POLICY_EXPECTED_SHA256=hash_value
    )
    calls = stub_factory(monkeypatch, settings)
    assert app_module.build_configured_rag_retriever() is not None
    assert len(calls) == 1
    assert calls[0]["source_family_policy"] is None


@pytest.mark.parametrize(
    "path,hash_value",
    [
        ("missing-old-policy.json", None),
        (None, "a" * 64),
        ("missing-old-policy.json", "a" * 64),
    ],
)
def test_v3_disabled_factory_still_enforces_legacy_policy_configuration(
    monkeypatch, path, hash_value
):
    settings = startup_settings(
        RAG_EVIDENCE_V3_ENABLED=False,
        RAG_SOURCE_FAMILY_POLICY_PATH=path,
        RAG_SOURCE_FAMILY_POLICY_EXPECTED_SHA256=hash_value,
    )
    calls = stub_factory(monkeypatch, settings)
    assert app_module.build_configured_rag_retriever() is None
    assert not any(isinstance(call, dict) for call in calls)


def test_v3_disabled_factory_keeps_loaded_legacy_overlay(monkeypatch):
    settings = startup_settings(
        RAG_EVIDENCE_V3_ENABLED=False,
        RAG_SOURCE_FAMILY_POLICY_PATH="old-policy.json",
        RAG_SOURCE_FAMILY_POLICY_EXPECTED_SHA256="a" * 64,
    )
    policy = SimpleNamespace(
        document=SimpleNamespace(runtime_policy_version="v004"),
        candidate_chunk_ids=["historical-candidate"],
    )
    calls = stub_factory(monkeypatch, settings, policy=policy)
    assert app_module.build_configured_rag_retriever() is not None
    assert calls[0] == "policy"
    assert calls[1]["source_family_policy"] is policy


@pytest.mark.parametrize(
    "changes",
    [
        {"APP_ENV": "production"},
        {"RAG_MODE": "disabled"},
        {"RAG_SEARCH_BACKEND": "opensearch"},
        {"RAG_STAGING_ALLOW_ALL_AUDIENCES": True},
    ],
)
def test_v3_factory_restrictions_prevent_adapter_construction(monkeypatch, changes):
    calls = stub_factory(monkeypatch, startup_settings(**changes))
    assert app_module.build_configured_rag_retriever() is None
    assert calls == []
