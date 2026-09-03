from __future__ import annotations

import asyncio
import concurrent.futures
import ipaddress
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
        *,
        timeout_seconds: float = 5.0,
        max_concurrency: int = 4,
    ) -> None:
        if not 0 < timeout_seconds <= 30:
            raise ValueError("OpenSearch timeout_seconds must be between zero and 30")
        if not 1 <= max_concurrency <= 16:
            raise ValueError("OpenSearch max_concurrency must be between one and 16")
        self._transport = transport
        self._settings = settings
        self._timeout_seconds = timeout_seconds
        self._max_concurrency = max_concurrency
        self._capacity = asyncio.Semaphore(max_concurrency)
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_concurrency,
            thread_name_prefix="rag-opensearch",
        )
        self._closed = False

    async def search(self, plan: HybridSearchPlan) -> list[SearchHit]:
        if self._closed:
            raise OpenSearchClientError("OpenSearch client is closed")
        profile = self._settings.for_profile(plan.profile)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._timeout_seconds
        try:
            await asyncio.wait_for(
                self._capacity.acquire(),
                timeout=_remaining_seconds(loop, deadline),
            )
        except TimeoutError as exc:
            raise OpenSearchClientError("OpenSearch search deadline exceeded") from exc

        if self._closed:
            self._capacity.release()
            raise OpenSearchClientError("OpenSearch client is closed")
        try:
            worker = self._executor.submit(
                self._transport.search,
                index=self._settings.index_alias,
                body=build_opensearch_search_body(plan),
                params={"search_pipeline": profile.search_pipeline},
            )
        except Exception as exc:
            self._capacity.release()
            raise OpenSearchClientError(
                f"OpenSearch search could not start: {type(exc).__name__}"
            ) from exc
        worker.add_done_callback(
            lambda _: _release_capacity_when_worker_finishes(loop, self._capacity)
        )
        try:
            response = await asyncio.wait_for(
                asyncio.shield(asyncio.wrap_future(worker)),
                timeout=_remaining_seconds(loop, deadline),
            )
        except TimeoutError as exc:
            raise OpenSearchClientError("OpenSearch search deadline exceeded") from exc
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise OpenSearchClientError(f"OpenSearch search failed: {type(exc).__name__}") from exc
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
        if self._closed:
            return
        self._closed = True
        close = getattr(self._transport, "close", None)
        try:
            if close is not None:
                await asyncio.wait_for(
                    asyncio.to_thread(close),
                    timeout=self._timeout_seconds,
                )
        finally:
            self._executor.shutdown(wait=False, cancel_futures=True)


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
        ssl_assert_hostname=parsed.scheme == "https",
        connection_class=RequestsHttpConnection,
        timeout=settings.search_timeout_seconds,
        max_retries=0,
        retry_on_timeout=False,
        pool_maxsize=settings.max_concurrency,
    )
    return cast(OpenSearchTransport, transport)


def build_opensearch_client(
    settings: OpenSearchConnectionSettings,
    hybrid_settings: HybridSearchSettings,
) -> OpenSearchClient:
    return OpenSearchClient(
        build_opensearch_transport(settings),
        hybrid_settings,
        timeout_seconds=settings.search_timeout_seconds,
        max_concurrency=settings.max_concurrency,
    )


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
    if parsed.scheme == "http" and not _is_loopback_host(parsed.hostname):
        raise OpenSearchClientError("OPENSEARCH_HOST must use HTTPS for non-loopback hosts")
    return parsed


def _is_loopback_host(hostname: str) -> bool:
    if hostname.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _remaining_seconds(loop: asyncio.AbstractEventLoop, deadline: float) -> float:
    remaining = deadline - loop.time()
    if remaining <= 0:
        raise TimeoutError
    return remaining


def _release_capacity_when_worker_finishes(
    loop: asyncio.AbstractEventLoop,
    capacity: asyncio.Semaphore,
) -> None:
    try:
        loop.call_soon_threadsafe(capacity.release)
    except RuntimeError:
        # The request loop may already be closed during process shutdown.
        pass
