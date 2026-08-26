from __future__ import annotations

import asyncio
import inspect
from collections.abc import Mapping
from typing import Protocol, cast
from urllib.parse import urlparse

import boto3
from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection

from agent_runtime.rag.filters import build_normal_rag_filter
from agent_runtime.rag.models import (
    HybridSearchPlan,
    HybridSearchSettings,
    OpenSearchConnectionSettings,
)
from agent_runtime.rag.search_backend import SearchHit

# opensearch-py defaults to 10s, which a hybrid query over the staging
# collection exceeds. That surfaced only as a bare ConnectionTimeout that
# Retriever converted into the public "knowledge unavailable" fallback, so
# every retrieval failed silently. This is a fail-safe ceiling, not a latency
# budget: the voice path needs its own measured target.
SEARCH_TIMEOUT_SECONDS = 60

_V1_SOURCE_FIELDS = [
    "chunk_id",
    "text",
    "document_name",
    "section",
    "page_start",
    "page_end",
    "source_url",
    "current_status",
    "stop_normal_rag",
    "risk_level",
    "requires_official_assessment",
    "requires_professional_assessment",
    "allowed_audiences",
    "allowed_purposes",
    "retrieval_eligible",
    "retrieval_block_reasons",
]

_V2_SOURCE_FIELDS = [
    "source_id",
    "artifact_version",
    "title",
    "publisher",
    "physical_page_start",
    "physical_page_end",
    "printed_page_start",
    "printed_page_end",
    "source_locator",
    "direct_official_source_url",
    "official_source_page_url",
    "direct_source_url",
    "source_page_url",
    "is_official_source",
    "source_version",
    "source_version_date",
    "version_published_at",
    "source_page_updated_at",
    "published_at",
    "last_verified_at",
    "review_status",
    "production_approved",
]


class OpenSearchClientError(RuntimeError):
    """OpenSearch did not return a usable search response."""


class OpenSearchTransport(Protocol):
    def search(self, **kwargs: object) -> Mapping[str, object]: ...


class OpenSearchClient:
    """SearchBackend adapter that owns all executable OpenSearch DSL."""

    def __init__(
        self,
        transport: OpenSearchTransport,
        settings: HybridSearchSettings,
    ) -> None:
        self._transport = transport
        self._settings = settings

    async def search(self, plan: HybridSearchPlan) -> list[SearchHit]:
        profile = self._settings.for_profile(plan.profile)
        response = await asyncio.to_thread(
            self._transport.search,
            index=self._settings.index_alias,
            body=build_opensearch_search_body(plan),
            params={"search_pipeline": profile.search_pipeline},
        )
        if inspect.isawaitable(response):
            response = await response
        if not isinstance(response, Mapping):
            raise OpenSearchClientError("OpenSearch response must be an object")
        hits_container = response.get("hits")
        if not isinstance(hits_container, Mapping):
            raise OpenSearchClientError("OpenSearch response is missing hits")
        hits = hits_container.get("hits")
        if not isinstance(hits, list):
            raise OpenSearchClientError("OpenSearch hits must be a list")
        if any(not isinstance(hit, Mapping) for hit in hits):
            raise OpenSearchClientError("OpenSearch returned a malformed hit")
        return _to_search_hits(cast(list[Mapping[str, object]], hits))

    async def aclose(self) -> None:
        close = getattr(self._transport, "close", None)
        if close is None:
            return
        response = await asyncio.to_thread(close)
        if inspect.isawaitable(response):
            await response


def build_opensearch_transport(settings: OpenSearchConnectionSettings) -> OpenSearchTransport:
    """Build a SigV4-authenticated OpenSearch transport for the configured staging host."""

    parsed = _parse_host(settings.host)
    session = boto3.Session(region_name=settings.region)
    credentials = session.get_credentials()
    if credentials is None:
        raise OpenSearchClientError("AWS credentials are unavailable from the provider chain")
    service = "aoss" if ".aoss." in parsed.hostname else "es"
    auth = AWSV4SignerAuth(credentials, settings.region, service)
    transport = OpenSearch(
        hosts=[
            {
                "host": parsed.hostname,
                "port": parsed.port or (443 if parsed.scheme == "https" else 80),
            }
        ],
        http_auth=auth,
        use_ssl=parsed.scheme == "https",
        verify_certs=parsed.scheme == "https",
        connection_class=RequestsHttpConnection,
        timeout=SEARCH_TIMEOUT_SECONDS,
    )
    return cast(OpenSearchTransport, transport)


def build_opensearch_client(
    settings: OpenSearchConnectionSettings,
    hybrid_settings: HybridSearchSettings,
) -> OpenSearchClient:
    return OpenSearchClient(build_opensearch_transport(settings), hybrid_settings)


def build_opensearch_search_body(plan: HybridSearchPlan) -> dict[str, object]:
    """Compile a bounded provider-neutral plan into adapter-owned OpenSearch DSL."""

    source_fields = _V1_SOURCE_FIELDS + (_V2_SOURCE_FIELDS if plan.governed_citations else [])
    return {
        "size": plan.search_result_limit,
        "_source": source_fields,
        "query": {
            "hybrid": {
                "queries": [
                    {"match": {"text": {"query": plan.query}}},
                    {
                        "knn": {
                            "embedding": {
                                "vector": plan.query_vector,
                                # OpenSearch Serverless accepts only `k` here.
                                # The normalized score floor remains in Retriever.
                                "k": plan.search_result_limit,
                            }
                        }
                    },
                ],
                "filter": build_normal_rag_filter(
                    profile=plan.profile,
                    audience=plan.audience,
                    purpose=plan.purpose,
                    governed_citations=plan.governed_citations,
                    allow_needs_review=plan.allow_needs_review,
                    allow_all_audiences=plan.allow_all_audiences,
                    policy_candidate_chunk_ids=plan.policy_candidate_chunk_ids,
                ),
            }
        },
    }


def _to_search_hits(hits: list[Mapping[str, object]]) -> list[SearchHit]:
    converted: list[SearchHit] = []
    for hit in hits:
        score = hit.get("_score")
        source = hit.get("_source")
        if isinstance(score, bool) or not isinstance(score, int | float):
            continue
        if not isinstance(source, Mapping):
            continue
        converted.append(SearchHit(score=float(score), source=source))
    return converted


def _parse_host(host: str):
    candidate = host if "://" in host else f"https://{host}"
    parsed = urlparse(candidate)
    if (
        parsed.hostname is None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise OpenSearchClientError("OPENSEARCH_HOST must contain only a host and optional port")
    if parsed.scheme not in {"http", "https"}:
        raise OpenSearchClientError("OPENSEARCH_HOST must use http or https")
    return parsed
