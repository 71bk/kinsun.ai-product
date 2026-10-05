"""Bounded developer smoke diagnostics, not a semantic accuracy benchmark."""

from __future__ import annotations

import asyncio
import json
import math
import re
import time
import unicodedata
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from agent_runtime.rag.evidence_models import RetrievalRequestV3

MAX_CASES = 16


class KnowledgeEvaluationError(ValueError):
    """Fixed sanitized error code without connection or provider details."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise KnowledgeEvaluationError(code)


def _object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _constant(_value):
    raise KnowledgeEvaluationError("NONFINITE_JSON_NUMBER")


def _finite(value):
    if isinstance(value, float):
        require(math.isfinite(value), "NONFINITE_JSON_NUMBER")
    elif isinstance(value, dict):
        for item in value.values():
            _finite(item)
    elif isinstance(value, list):
        for item in value:
            _finite(item)


def read_json(path: Path):
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_object, parse_constant=_constant
        )
        _finite(value)
        return value
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise KnowledgeEvaluationError("UNREADABLE_JSON") from exc


@dataclass(frozen=True, slots=True)
class SmokeCase:
    id: str
    query: str
    audience: str
    purpose: str
    expectation: str
    anchor_source_ids: tuple[str, ...]
    anchor_text_any: tuple[str, ...]
    notes: str


def load_cases(path: Path, selected_ids: Sequence[str] = ()) -> tuple[str, tuple[SmokeCase, ...]]:
    document = read_json(path)
    require(
        isinstance(document, dict)
        and set(document) == {"schema_version", "cases_version", "cases"}
        and document["schema_version"] == "knowledge-smoke-v1",
        "INVALID_CASES_DOCUMENT",
    )
    require(
        isinstance(document["cases_version"], str) and bool(document["cases_version"].strip()),
        "INVALID_CASES_VERSION",
    )
    rows = document["cases"]
    require(isinstance(rows, list) and 1 <= len(rows) <= MAX_CASES, "CASE_LIMIT_EXCEEDED")
    names = set(SmokeCase.__dataclass_fields__)
    cases = []
    ids = set()
    for row in rows:
        require(isinstance(row, dict) and set(row) == names, "INVALID_CASE_SHAPE")
        for name in ("id", "query", "audience", "purpose", "expectation", "notes"):
            require(isinstance(row[name], str) and bool(row[name].strip()), "INVALID_CASE_TEXT")
        require(
            row["id"] not in ids
            and len(row["id"]) <= 100
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", row["id"]) is not None,
            "INVALID_CASE_ID",
        )
        ids.add(row["id"])
        require(len(row["query"]) <= 2000, "QUERY_LIMIT_EXCEEDED")
        require(
            row["audience"] in {"elder", "family_caregiver", "care_professional", "system_admin"},
            "INVALID_CASE_AUDIENCE",
        )
        require(
            row["purpose"] in {"general_information", "legal_reference"}, "INVALID_CASE_PURPOSE"
        )
        require(
            row["expectation"] in {"answer", "no_data", "safety", "partial_or_no_data"},
            "INVALID_CASE_EXPECTATION",
        )
        for name in ("anchor_source_ids", "anchor_text_any"):
            require(
                isinstance(row[name], list)
                and len(row[name]) <= 30
                and all(
                    isinstance(value, str) and 0 < len(value.strip()) <= 512 for value in row[name]
                ),
                "INVALID_CASE_ANCHORS",
            )
        cases.append(
            SmokeCase(
                **{
                    **row,
                    "anchor_source_ids": tuple(row["anchor_source_ids"]),
                    "anchor_text_any": tuple(row["anchor_text_any"]),
                }
            )
        )
    require(
        len(set(selected_ids)) == len(selected_ids) and set(selected_ids) <= ids,
        "INVALID_CASE_SELECTION",
    )
    return document["cases_version"], tuple(
        case for case in cases if not selected_ids or case.id in selected_ids
    )


@dataclass(slots=True)
class CallCounts:
    query_embeddings: int = 0
    generations: int = 0

    def reset(self):
        self.query_embeddings = self.generations = 0


class CountedEmbedding:
    def __init__(self, inner, counts: CallCounts):
        self.inner, self.counts = inner, counts

    @property
    def dimension(self):
        return self.inner.dimension

    async def embed_query(self, query):
        require(self.counts.query_embeddings < 1, "QUERY_EMBEDDING_CALL_LIMIT")
        self.counts.query_embeddings += 1
        return await self.inner.embed_query(query)

    async def aclose(self):
        await self.inner.aclose()


class CountedProvider:
    def __init__(self, inner, counts: CallCounts):
        self.inner, self.counts = inner, counts
        self.reset_diagnostics()

    def reset_diagnostics(self):
        # Private memory only: never serialize raw output into smoke reports.
        self._last_raw_output = None
        self._exception_type = None
        self._timed_out = False
        self._generation_metadata = None

    async def generate_reply(self, request, context_manifest, language):
        from agent_runtime.models.generation_diagnostics import capture_generation_diagnostics

        require(self.counts.generations < 1, "GENERATION_CALL_LIMIT")
        self.counts.generations += 1
        with capture_generation_diagnostics() as diagnostics:
            try:
                raw = await self.inner.generate_reply(request, context_manifest, language)
                self._last_raw_output = raw
                return raw
            except BaseException as exc:
                self._exception_type = type(exc).__name__
                self._timed_out = isinstance(exc, TimeoutError)
                raise
            finally:
                if diagnostics:
                    self._generation_metadata = asdict(diagnostics[-1])

    async def aclose(self):
        await self.inner.aclose()


class CandidateRecorder:
    def __init__(self, inner):
        self.inner = inner
        self.results = []

    async def load_public_candidates(self, request, *, require_current):
        self.results = await self.inner.load_public_candidates(
            request, require_current=require_current
        )
        return self.results


def _quote_diagnostics(raw, results):
    """Compare anchors without exporting generated quotes or relaxing validation."""
    if not isinstance(raw, str) or len(raw) > 20_000:
        return None
    try:
        document = json.loads(raw)
    except (ValueError, RecursionError):
        return None
    if not isinstance(document, dict) or not isinstance(document.get("support_quotes"), list):
        return None
    sources = {item.chunk_id: item.text for item in results}
    categories = Counter()
    for item in document["support_quotes"][:20]:
        if not isinstance(item, dict):
            categories["content-mismatch"] += 1
            continue
        quote, cid = item.get("quote"), item.get("chunk_id")
        text = sources.get(cid) if isinstance(cid, str) else None
        if not isinstance(quote, str) or not quote.strip() or text is None:
            category = "content-mismatch"
        elif quote in text:
            category = "exact"
        elif re.sub(r"\s+", "", quote) in re.sub(r"\s+", "", text):
            category = "whitespace-only"
        elif unicodedata.normalize("NFKC", quote) in unicodedata.normalize("NFKC", text):
            category = "unicode-normalization-only"
        elif re.sub(r"\s+", "", unicodedata.normalize("NFKC", quote)) in re.sub(
            r"\s+", "", unicodedata.normalize("NFKC", text)
        ):
            category = "unicode-and-whitespace"
        else:
            category = "content-mismatch"
        categories[category] += 1
    return dict(categories)


def _candidate(result) -> dict:
    require(len(result.text) <= 50_000, "REPORTED_SOURCE_TEXT_LIMIT")
    return {
        "chunk_id": result.chunk_id,
        "source_id": result.source_id,
        "title": result.title,
        "text": result.text,
        "source_locator": result.source_locator,
        "source_version": result.source_version,
        "current_status": result.current_status,
        "warnings": list(result.warnings),
        "source_url": result.source_url,
    }


def _expectation_observation(case: SmokeCase, response) -> bool:
    if case.expectation == "answer":
        return response.status == "SUCCESS"
    if case.expectation == "no_data":
        return response.status == "NO_DATA"
    if case.expectation == "safety":
        return response.status == "NO_DATA" and "SAFETY_GATE" in response.reason_codes
    return response.decision in {"PARTIAL", "INSUFFICIENT", "UNKNOWN", "CLARIFY"}


async def evaluate_cases(
    service,
    cases: Sequence[SmokeCase],
    *,
    cases_version: str,
    counts: CallCounts,
    recorder: CandidateRecorder,
    clock: Callable[[], float] = time.monotonic,
    retrieval_only: bool = False,
) -> dict:
    require(1 <= len(cases) <= MAX_CASES, "CASE_LIMIT_EXCEEDED")
    rows = []
    for case in cases:
        counts.reset()
        recorder.results = []
        provider = getattr(service, "provider", None)
        if isinstance(provider, CountedProvider):
            provider.reset_diagnostics()
        request = RetrievalRequestV3(
            schema_version="3.0.0",
            request_id=f"smoke-{case.id}",
            query=case.query,
            query_profile="legal" if case.purpose == "legal_reference" else "natural_language",
            audience=case.audience,
            purpose=case.purpose,
            top_k=5,
        )
        start = clock()
        try:
            if retrieval_only:
                from agent_runtime.common.enums import SafetyDecision
                from agent_runtime.rag.evidence_service import (
                    _public_generation_request,
                    requires_current_source,
                )

                safety = service.safety.evaluate(_public_generation_request(request), "")
                if safety.decision != SafetyDecision.ALLOW:
                    response = service._no_data(
                        request, reason="SAFETY_GATE", message=safety.safe_reply
                    )
                    status, decision, reasons = (
                        response.status,
                        response.decision,
                        list(response.reason_codes),
                    )
                else:
                    async with asyncio.timeout(30):
                        await recorder.load_public_candidates(
                            request,
                            require_current=requires_current_source(case.query, case.purpose),
                        )
                    response = None
                    status, decision, reasons = "RETRIEVAL_ONLY", None, []
            else:
                response = await service.retrieve_v3(request)
                status, decision, reasons = (
                    response.status,
                    response.decision,
                    list(response.reason_codes),
                )
            classification = None
            if status == "FAILED":
                classification = (
                    "GENERATION_OR_ENVELOPE_FAILED" if counts.generations else "RETRIEVAL_FAILED"
                )
        except Exception:
            # Never report exception strings (SDK/driver failures may echo secrets).
            response = None
            status, decision, reasons, classification = (
                "FAILED",
                "FAILED",
                ["SMOKE_CASE_FAILED"],
                "EXECUTION_FAILED",
            )
        elapsed = max(0.0, clock() - start)
        diagnostic = None
        exception_type = None
        quote_diagnostics = None
        if status == "FAILED" and counts.generations and isinstance(provider, CountedProvider):
            exception_type = provider._exception_type
            if provider._timed_out:
                diagnostic = "GENERATION_TIMEOUT"
            elif provider._last_raw_output is not None:
                quote_diagnostics = _quote_diagnostics(provider._last_raw_output, recorder.results)
                from agent_runtime.rag.grounded_answer import (
                    GroundedAnswerError,
                    parse_grounded_answer,
                )

                try:
                    parse_grounded_answer(provider._last_raw_output, recorder.results)
                    diagnostic = "POST_GENERATION_SERVICE_FAILURE"
                except GroundedAnswerError as exc:
                    diagnostic = str(exc)  # Production parser emits fixed reason codes only.
                    if (
                        diagnostic == "INVALID_GENERATION_JSON"
                        and provider._generation_metadata
                        and provider._generation_metadata.get("finish_reason") == "MAX_TOKENS"
                    ):
                        diagnostic = "GENERATION_JSON_TRUNCATED_MAX_TOKENS"
            elif exception_type:
                diagnostic = "GENERATION_PROVIDER_EXCEPTION"
        candidates = [_candidate(result) for result in recorder.results]
        source_ids = {result["source_id"] for result in candidates}
        combined_text = "\n".join(result["text"] for result in candidates)
        rows.append(
            {
                "id": case.id,
                "request": {
                    "query": case.query,
                    "audience": case.audience,
                    "purpose": case.purpose,
                },
                "expectation": case.expectation,
                "notes": case.notes,
                "status": status,
                "decision": decision,
                "reason_codes": reasons,
                "retrieved_candidates": candidates,
                "selected_chunk_ids": [item.chunk_id for item in response.results]
                if response
                else [],
                "answer_text": response.answer_text if response else None,
                "fallback_message": response.fallback_message if response else None,
                "missing_facets": list(response.missing_facets) if response else [],
                "elapsed_ms": round(elapsed * 1000, 2),
                "calls": asdict(counts),
                "failure_category": classification,
                "generation_diagnostic_code": diagnostic,
                "generation_exception_type": exception_type,
                "generation_quote_matches": quote_diagnostics,
                "generation_metadata": provider._generation_metadata
                if isinstance(provider, CountedProvider)
                else None,
                "anchor_proxy": {
                    "source_id_any": bool(set(case.anchor_source_ids) & source_ids)
                    if case.anchor_source_ids
                    else None,
                    "text_any": any(anchor in combined_text for anchor in case.anchor_text_any)
                    if case.anchor_text_any
                    else None,
                    "semantic_ground_truth": False,
                },
                "expected_outcome_observed": _expectation_observation(case, response)
                if response
                else None,
            }
        )
    return {
        "schema_version": "knowledge-smoke-report-v1",
        "cases_version": cases_version,
        "mode": "LIVE_RETRIEVAL_ONLY" if retrieval_only else "LIVE_GROUNDED",
        "database_write_performed": False,
        "activation_performed": False,
        "semantic_accuracy_verified": False,
        "anchor_metrics": "DIAGNOSTIC_OR_PROXY_ONLY",
        "quality_score": None,
        "summary": {
            "case_count": len(rows),
            "statuses": dict(Counter(row["status"] for row in rows)),
            "query_embedding_calls": sum(row["calls"]["query_embeddings"] for row in rows),
            "generation_calls": sum(row["calls"]["generations"] for row in rows),
        },
        "cases": rows,
    }
