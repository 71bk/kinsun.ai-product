"""Shared admission for opt-in public knowledge; human review remains provenance."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

POLICY_VERSION = "public-knowledge-v1"
# These official documents retain historical internal labels. Source-level public
# project-use evidence is recorded in data/rag-v3/governance/source-family-policy/
# candidates/v002/source-family-policy-map.json: OWNER_REVIEWED_PUBLIC_USE or
# RECORDED_LICENSE_EVIDENCE, both scoped to STAGING_PROJECT_USE. No row scope is granted.
LEGACY_PUBLIC_PROJECT_SOURCE_IDS = (
    "mohw_a_unit_case_manager_manual_20230719",
    "mohw_a_unit_case_manager_manual_appendix_20230719",
    "mohw_home_care_service_supervisor_manual_forms_appendix_20260529",
    "moj_long_term_care_services_act_20210609",
)
RETIRED_BLOCK_REASONS = (
    "human_source_review_pending",
    "source_version_review_pending",
    "successor_not_authorized",
    "requires_official_assessment_missing",
    "requires_professional_assessment_missing",
)


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    allowed: bool
    block_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    requires_official_assessment: bool | None
    requires_professional_assessment: bool | None


def evaluate_public_knowledge(
    source: Mapping[str, object],
    *,
    audience: str,
    purpose: str,
    require_current: bool = False,
) -> AdmissionDecision:
    reasons: list[str] = []
    warnings: list[str] = []
    public_scope = (
        source.get("data_classification") == "public"
        and source.get("distribution_scope") == "public_knowledge"
    )
    legacy_project_scope = (
        source.get("data_classification") == "internal"
        and source.get("distribution_scope") == "internal_knowledge"
        and source.get("source_id") in LEGACY_PUBLIC_PROJECT_SOURCE_IDS
    )
    if not (public_scope or legacy_project_scope):
        reasons.append("public_scope_required")
    if source.get("is_official_source") is not True:
        reasons.append("official_source_required")
    url = next(
        (
            source.get(field)
            for field in (
                "official_source_page_url",
                "direct_official_source_url",
                "source_page_url",
                "direct_source_url",
            )
            if source.get(field) is not None
        ),
        None,
    )
    try:
        parsed = urlsplit(url) if isinstance(url, str) else None
        valid_url = (
            parsed is not None
            and parsed.scheme in {"http", "https"}
            and parsed.hostname is not None
            and (parsed.hostname == "gov.tw" or parsed.hostname.endswith(".gov.tw"))
            and parsed.username is None
            and parsed.password is None
            and (parsed.port is None or 1 <= parsed.port <= 65535)
            and not any(char.isspace() for char in url)
            and re.fullmatch(
                r"https?://([a-z0-9-]+\.)*gov\.tw(:[0-9]{1,5})?([/?#]\S*)?", url, re.IGNORECASE
            )
            is not None
        )
    except ValueError:
        valid_url = False
    if not valid_url:
        reasons.append("official_source_url_invalid")
    if source.get("stop_normal_rag") is not False:
        reasons.append("stop_normal_rag")
    if source.get("risk_level") not in ("low", "medium"):
        reasons.append("risk_level_not_allowed")
    for field, value in (("allowed_audiences", audience), ("allowed_purposes", purpose)):
        scope = source.get(field)
        matching_scope = scope
        if field == "allowed_audiences" and isinstance(scope, list | tuple):
            matching_scope = ["elder" if item == "older_adult" else item for item in scope]
            value = "elder" if value == "older_adult" else value
        if (
            not isinstance(scope, list | tuple)
            or not scope
            or any(not isinstance(item, str) or not item.strip() for item in scope)
            or not isinstance(value, str)
            or not value.strip()
            or value not in matching_scope
        ):
            reasons.append(f"{field}_not_allowed")
    currency = source.get("current_status")
    unknown_allowed = (
        currency == "unknown" and purpose == "general_information" and not require_current
    )
    if currency != "current" and not unknown_allowed:
        reasons.append("current_status_not_current")
    elif unknown_allowed:
        warnings.append("source_currency_unknown")
    blocks = source.get("retrieval_block_reasons")
    if not isinstance(blocks, list | tuple) or any(
        not isinstance(item, str) or not item for item in blocks
    ):
        reasons.append("invalid_retrieval_block_reasons")
        blocks = ()
    allowed_blocks = set(RETIRED_BLOCK_REASONS)
    if unknown_allowed:
        allowed_blocks.add("current_status_not_current")
    reasons.extend(block for block in blocks if block not in allowed_blocks)
    eligible = source.get("retrieval_eligible")
    if eligible is not True and not (
        eligible is False and blocks and all(block in allowed_blocks for block in blocks)
    ):
        reasons.append("retrieval_not_eligible")
    assessment = []
    for field in ("requires_official_assessment", "requires_professional_assessment"):
        value = source.get(field)
        if value is not None and type(value) is not bool:
            reasons.append("invalid_assessment_metadata")
        if value is None:
            warnings.append(f"{field}_unknown")
        assessment.append(value is not False)
    return AdmissionDecision(
        allowed=not reasons,
        block_reasons=tuple(dict.fromkeys(reasons)),
        warnings=tuple(warnings),
        requires_official_assessment=assessment[0],
        requires_professional_assessment=assessment[1],
    )


OFFICIAL_URL_SQL = """coalesce(
    projection.citation ->> 'official_source_page_url',
    projection.citation ->> 'direct_official_source_url',
    projection.citation ->> 'source_page_url',
    projection.citation ->> 'direct_source_url'
)"""


# Bound values use the same retired reasons and currency condition as the Python
# decision. Only this fixed predicate is inserted into the fixed search template.
PUBLIC_KNOWLEDGE_SQL_PREDICATE = """
(
    (projection.governance ->> 'data_classification' = 'public'
     AND projection.governance ->> 'distribution_scope' = 'public_knowledge')
    OR (projection.governance ->> 'data_classification' = 'internal'
        AND projection.governance ->> 'distribution_scope' = 'internal_knowledge'
        AND projection.source_id = ANY(CAST(:legacy_public_project_source_ids AS text[])))
)
AND projection.provenance -> 'is_official_source' = 'true'::jsonb
AND projection.stop_normal_rag IS FALSE
AND projection.risk_level IN ('low', 'medium')
AND cardinality(projection.allowed_audiences) > 0
AND NOT EXISTS (SELECT 1 FROM unnest(projection.allowed_audiences) AS audience_scope(value)
    WHERE audience_scope.value IS NULL OR btrim(audience_scope.value) = '')
AND (
    CAST(:audience AS text) = ANY(projection.allowed_audiences)
    OR (CAST(:audience AS text) = ANY(ARRAY['elder', 'older_adult']::text[])
        AND projection.allowed_audiences && ARRAY['elder', 'older_adult']::text[])
)
AND cardinality(projection.allowed_purposes) > 0
AND NOT EXISTS (SELECT 1 FROM unnest(projection.allowed_purposes) AS purpose_scope(value)
    WHERE purpose_scope.value IS NULL OR btrim(purpose_scope.value) = '')
AND CAST(:purpose AS text) = ANY(projection.allowed_purposes)
AND (
    projection.current_status = 'current'
    OR (projection.current_status = 'unknown'
        AND CAST(:purpose AS text) = 'general_information'
        AND CAST(:require_current AS boolean) IS FALSE)
)
AND jsonb_typeof(projection.retrieval_policy -> 'retrieval_block_reasons') = 'array'
AND NOT EXISTS (
    SELECT 1 FROM jsonb_array_elements(
        CASE WHEN jsonb_typeof(projection.retrieval_policy -> 'retrieval_block_reasons') = 'array'
        THEN projection.retrieval_policy -> 'retrieval_block_reasons' ELSE '[]'::jsonb END
    ) AS reason(value)
    WHERE jsonb_typeof(reason.value) <> 'string'
       OR NOT (
           reason.value #>> '{}' = ANY(CAST(:retired_block_reasons AS text[]))
           OR (reason.value #>> '{}' = 'current_status_not_current'
               AND projection.current_status = 'unknown'
               AND CAST(:purpose AS text) = 'general_information'
               AND CAST(:require_current AS boolean) IS FALSE)
       )
)
AND (
    projection.retrieval_eligible IS TRUE
    OR (projection.retrieval_eligible IS FALSE
        AND jsonb_array_length(
            CASE WHEN jsonb_typeof(
                projection.retrieval_policy -> 'retrieval_block_reasons') = 'array'
            THEN projection.retrieval_policy -> 'retrieval_block_reasons' ELSE '[]'::jsonb END
        ) > 0)
)
"""

PUBLIC_KNOWLEDGE_SQL_PREDICATE += (
    "\nAND "
    + OFFICIAL_URL_SQL
    + r" ~* '^https?://([a-z0-9-]+\.)*gov\.tw(:[0-9]{1,5})?([/?#]\S*)?$'"
    + "\nAND (substring(lower("
    + OFFICIAL_URL_SQL
    + r" ) from '^https?://[^/?#:]+:([0-9]{1,5})(?:[/?#]|$)') IS NULL OR CAST(substring(lower("
    + OFFICIAL_URL_SQL
    + r" ) from '^https?://[^/?#:]+:([0-9]{1,5})(?:[/?#]|$)') AS integer) BETWEEN 1 AND 65535)"
)
