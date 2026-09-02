"""Fail-closed HTTP boundary for staging knowledge retrieval."""

from fastapi import APIRouter, Request

from agent_runtime.core.envelopes import ResponseMeta, SuccessEnvelope
from agent_runtime.middleware.correlation import get_correlation_id
from agent_runtime.rag.fallback import failed_response, failed_response_v2
from agent_runtime.rag.models import (
    RetrievalRequestV1,
    RetrievalRequestV2,
    RetrievalResponseV1,
    RetrievalResponseV2,
)
from agent_runtime.security.service_identity import SERVICE_CREDENTIAL_HEADER

router = APIRouter(tags=["rag"])


@router.post(
    "/api/v1/rag/retrievals",
    response_model=SuccessEnvelope[RetrievalResponseV1],
)
async def retrieve_knowledge(
    request: Request,
    payload: RetrievalRequestV1,
) -> SuccessEnvelope[RetrievalResponseV1]:
    """Retrieve approved staging chunks or return an explicit no-guess fallback.

    A missing provider configuration is a knowledge outcome rather than an
    invitation for the Agent to improvise. Provider failures are similarly
    converted by ``Retriever`` into a ``FAILED`` response with no partial
    chunks.
    """

    await request.app.state.service_identity_verifier.verify(
        request.headers.get(SERVICE_CREDENTIAL_HEADER),
        method=request.method,
        path=request.url.path,
        body=await request.body(),
        correlation_id=get_correlation_id(),
    )

    retriever = getattr(request.app.state, "rag_retriever", None)
    result = (
        failed_response(payload.request_id)
        if retriever is None
        else await retriever.retrieve(payload)
    )
    return SuccessEnvelope(
        data=result,
        meta=ResponseMeta(correlation_id=get_correlation_id()),
    )


@router.post(
    "/api/v2/rag/retrievals",
    response_model=SuccessEnvelope[RetrievalResponseV2],
)
async def retrieve_governed_knowledge(
    request: Request,
    payload: RetrievalRequestV2,
) -> SuccessEnvelope[RetrievalResponseV2]:
    """Retrieve complete governed citations or fail the entire batch closed."""

    await request.app.state.service_identity_verifier.verify(
        request.headers.get(SERVICE_CREDENTIAL_HEADER),
        method=request.method,
        path=request.url.path,
        body=await request.body(),
        correlation_id=get_correlation_id(),
    )

    retriever = getattr(request.app.state, "rag_retriever", None)
    result = (
        failed_response_v2(payload.request_id)
        if retriever is None
        else await retriever.retrieve_v2(payload)
    )
    return SuccessEnvelope(
        data=result,
        meta=ResponseMeta(correlation_id=get_correlation_id()),
    )
