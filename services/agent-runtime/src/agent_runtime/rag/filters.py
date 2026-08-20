from __future__ import annotations

from collections.abc import Mapping

from agent_runtime.rag.models import QueryProfile

NORMAL_RAG_RISK_LEVELS = ("low", "medium")


def build_normal_rag_filter(
    *,
    profile: QueryProfile,
    audience: str | None = None,
    purpose: str | None = None,
    governed_citations: bool = False,
    allow_needs_review: bool = False,
) -> dict[str, object]:
    """Return mandatory fail-closed filters for ordinary RAG answers."""

    must: list[dict[str, object]] = [
        {"term": {"current_status": "current"}},
        {"term": {"stop_normal_rag": False}},
        {"term": {"retrieval_eligible": True}},
        {"terms": {"risk_level": list(NORMAL_RAG_RISK_LEVELS)}},
    ]
    must.append(_scope_filter("allowed_audiences", audience))
    must.append(_scope_filter("allowed_purposes", purpose))
    if governed_citations:
        must.append(_governance_filter(allow_needs_review=allow_needs_review))
    bool_filter: dict[str, object] = {"must": must}
    return {"bool": bool_filter}


def is_normal_rag_eligible(
    source: Mapping[str, object],
    profile: QueryProfile,
    *,
    audience: str | None = None,
    purpose: str | None = None,
    governed_citations: bool = False,
    allow_needs_review: bool = False,
) -> bool:
    """Defence-in-depth after search; missing policy fields are denied."""

    if source.get("current_status") != "current":
        return False
    if source.get("stop_normal_rag") is not False:
        return False
    if source.get("retrieval_eligible") is not True:
        return False
    block_reasons = source.get("retrieval_block_reasons")
    if not isinstance(block_reasons, list) or block_reasons:
        return False
    if source.get("risk_level") not in NORMAL_RAG_RISK_LEVELS:
        return False
    if not isinstance(source.get("requires_official_assessment"), bool):
        return False
    if not isinstance(source.get("requires_professional_assessment"), bool):
        return False
    if not _scope_allows(source.get("allowed_audiences"), audience):
        return False
    if not _scope_allows(source.get("allowed_purposes"), purpose):
        return False
    if governed_citations and not _governance_allows(
        source,
        allow_needs_review=allow_needs_review,
    ):
        return False
    return True


def _scope_allows(raw_allowed: object, requested: str | None) -> bool:
    if not isinstance(raw_allowed, list) or any(
        not isinstance(value, str) or not value.strip() for value in raw_allowed
    ):
        return False
    if not raw_allowed:
        return False
    return isinstance(requested, str) and bool(requested.strip()) and requested in raw_allowed


def _scope_filter(field: str, requested: str | None) -> dict[str, object]:
    """Require an explicit caller scope and an exact allowlist match."""

    if not isinstance(requested, str) or not requested.strip():
        return {"match_none": {}}
    return {"term": {field: requested}}


def _governance_filter(*, allow_needs_review: bool) -> dict[str, object]:
    if not allow_needs_review:
        return {
            "bool": {
                "must": [
                    {"term": {"review_status": "verified"}},
                    {"term": {"production_approved": True}},
                ]
            }
        }
    return {
        "bool": {
            "should": [
                {"term": {"review_status": "verified"}},
                {
                    "bool": {
                        "must": [
                            {"term": {"review_status": "needs_review"}},
                            {"term": {"production_approved": False}},
                        ]
                    }
                },
            ],
            "minimum_should_match": 1,
        }
    }


def _governance_allows(source: Mapping[str, object], *, allow_needs_review: bool) -> bool:
    review_status = source.get("review_status")
    production_approved = source.get("production_approved")
    if review_status == "verified":
        return production_approved is True or (allow_needs_review and production_approved is False)
    return allow_needs_review and review_status == "needs_review" and production_approved is False
