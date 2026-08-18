"""Core-owned Tool allowlist and second authorization gate."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ActorContext
from app.core.correlation import get_correlation_id
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.domain.consent import ConsentPurpose
from app.models.agent import AgentRun, AgentToolCall
from app.models.idempotency import IdempotencyRecord
from app.repositories.idempotency_repo import IdempotencyRepository
from app.schemas.tool import ToolRequest, ToolResult
from app.services.authorization_service import authorize_elder
from app.services.consent_service import ConsentService
from app.services.tool_dispatcher import ToolCommandDispatcher

TOOL_ALLOWLIST: dict[str, tuple[str, ConsentPurpose | None, bool]] = {
    "retrieve_confirmed_memory": ("memory:read", ConsentPurpose.LONG_TERM_MEMORY, False),
    "retrieve_verified_event": (
        "care_event:read",
        ConsentPurpose.CARE_EVENT_EXTRACTION,
        False,
    ),
    "retrieve_daily_summary": (
        "summary:read",
        ConsentPurpose.CARE_EVENT_EXTRACTION,
        False,
    ),
    "get_assignment_context": ("assignment:read", None, False),
    "create_event_candidate": (
        "care_event:candidate:create",
        ConsentPurpose.CARE_EVENT_EXTRACTION,
        True,
    ),
    "create_memory_candidate": (
        "memory:candidate:create",
        ConsentPurpose.LONG_TERM_MEMORY,
        True,
    ),
    "create_summary_draft": (
        "summary:draft:create",
        ConsentPurpose.CARE_EVENT_EXTRACTION,
        True,
    ),
}

BLOCKED_COMMAND_TOOLS = {
    "confirm_memory",
    "review_event",
    "publish_report",
    "withdraw_report",
    "send_notification",
    "revoke_consent",
    "create_deletion_request",
    "create_care_action",
}

READ_PARAMETER_KEYS = {
    "retrieve_confirmed_memory": {"limit"},
    "retrieve_verified_event": {"limit"},
    "retrieve_daily_summary": set(),
    "get_assignment_context": set(),
}


class ToolExecutionService:
    def __init__(
        self,
        session: AsyncSession,
        actor_context: ActorContext,
    ) -> None:
        self._session = session
        self._actor = actor_context
        self._dispatcher = ToolCommandDispatcher(session, actor_context)

    async def execute(self, request: ToolRequest) -> ToolResult:
        trace_id = get_correlation_id()
        existing_call = await self._session.get(AgentToolCall, request.tool_call_id)

        run = await self._session.scalar(
            select(AgentRun).where(
                AgentRun.agent_run_id == request.agent_run_id,
                AgentRun.tenant_id == self._actor.tenant_id,
                AgentRun.elder_id == request.elder_id,
                AgentRun.actor_id == self._actor.actor_id,
            )
        )
        if run is None:
            raise NotFoundError("Resource not found")
        if existing_call is not None:
            self._validate_replay_request(existing_call, request)
        elif run.result_status != "RUNNING":
            raise ConflictError("Tool execution requires a RUNNING AgentRun")
        if run.policy_version != request.policy_version:
            if existing_call is not None:
                raise ConflictError("Tool call cannot be replayed under a different policy version")
            return await self._record_result(
                request=request,
                result=ToolResult(
                    result_status="BLOCKED",
                    reason_code="POLICY_VERSION_MISMATCH",
                    retryable=False,
                    trace_id=trace_id,
                ),
            )

        if request.tool_name in BLOCKED_COMMAND_TOOLS or request.tool_name not in TOOL_ALLOWLIST:
            if existing_call is not None:
                raise ConflictError("Blocked tool calls cannot be replayed")
            return await self._record_result(
                request=request,
                result=ToolResult(
                    result_status="BLOCKED",
                    reason_code="TOOL_NOT_ALLOWLISTED",
                    retryable=False,
                    trace_id=trace_id,
                ),
            )

        action, purpose, is_write = TOOL_ALLOWLIST[request.tool_name]
        expected_purpose = purpose.value if purpose is not None else "CARE_ASSIGNMENT"
        if request.purpose != expected_purpose:
            if existing_call is not None:
                raise ConflictError("Tool call cannot be replayed with a different purpose")
            return await self._record_result(
                request=request,
                result=ToolResult(
                    result_status="BLOCKED",
                    reason_code="PURPOSE_NOT_ALLOWED",
                    retryable=False,
                    trace_id=trace_id,
                ),
            )
        allowed_parameter_keys = READ_PARAMETER_KEYS.get(request.tool_name)
        if allowed_parameter_keys is not None and not set(request.parameters).issubset(
            allowed_parameter_keys
        ):
            if existing_call is not None:
                raise ConflictError("Tool call cannot be replayed with different parameters")
            return await self._record_result(
                request=request,
                result=ToolResult(
                    result_status="BLOCKED",
                    reason_code="PARAMETERS_NOT_ALLOWED",
                    retryable=False,
                    trace_id=trace_id,
                ),
            )
        await authorize_elder(
            self._session,
            self._actor,
            request.elder_id,
            action,
        )
        if purpose is not None:
            consent = await ConsentService(
                self._session,
                self._actor.tenant_id,
            ).require_active(
                elder_id=request.elder_id,
                purpose=purpose,
            )
            if consent.version != request.consent_version:
                if existing_call is not None:
                    raise ConflictError(
                        "Tool call cannot be replayed with an inactive consent version"
                    )
                return await self._record_result(
                    request=request,
                    result=ToolResult(
                        result_status="BLOCKED",
                        reason_code="CONSENT_VERSION_MISMATCH",
                        retryable=False,
                        trace_id=trace_id,
                    ),
                )
        if is_write and not request.idempotency_key:
            if existing_call is not None:
                raise ConflictError("Tool call cannot be replayed without its idempotency key")
            return await self._record_result(
                request=request,
                result=ToolResult(
                    result_status="BLOCKED",
                    reason_code="IDEMPOTENCY_KEY_REQUIRED",
                    retryable=False,
                    trace_id=trace_id,
                ),
            )

        if existing_call is not None:
            return self._replayed_result(existing_call)

        idempotency: IdempotencyRepository | None = None
        replayed_resource_id = None
        if is_write:
            idempotency = IdempotencyRepository(
                self._session,
                self._actor.tenant_id,
                self._actor.actor_id,
            )
            replay = await idempotency.begin(
                key=request.idempotency_key,
                operation=f"tool:{request.tool_name}",
                payload={
                    "agent_run_id": request.agent_run_id,
                    "elder_id": request.elder_id,
                    "purpose": request.purpose,
                    "consent_version": request.consent_version,
                    "parameters": request.parameters,
                },
            )
            replayed_resource_id = replay.resource_id if replay.replayed else None
            if replay.replayed:
                return await self._record_result(
                    request=request,
                    result=ToolResult(
                        result_status="SUCCESS",
                        resource_id=replayed_resource_id,
                        trace_id=trace_id,
                    ),
                )

        try:
            result = await self._dispatch(request, trace_id)
        except PydanticValidationError as exc:
            raise ValidationError(
                details=[
                    {
                        "field": ".".join(str(part) for part in error["loc"]),
                        "reason": error["msg"],
                    }
                    for error in exc.errors()
                ]
            ) from exc
        if (
            idempotency is not None
            and request.idempotency_key is not None
            and result.resource_id is not None
        ):
            await idempotency.complete(
                key=request.idempotency_key,
                resource_type=request.tool_name,
                resource_id=result.resource_id,
                response_status=200,
                response_body={
                    "resource_id": str(result.resource_id),
                    "resource_version": result.resource_version,
                },
            )
        return await self._record_result(request=request, result=result)

    async def _dispatch(self, request: ToolRequest, trace_id: str) -> ToolResult:
        return await self._dispatcher.dispatch(request, trace_id)

    @staticmethod
    def _bounded_limit(value: object, *, default: int, maximum: int) -> int:
        return ToolCommandDispatcher._bounded_limit(value, default=default, maximum=maximum)

    @staticmethod
    def _request_fingerprint(request: ToolRequest) -> str:
        """Fingerprint semantic replay identity without persisting parameters."""
        return IdempotencyRepository.fingerprint(
            operation="tool_execution",
            payload={
                "agent_run_id": request.agent_run_id,
                "tool_name": request.tool_name,
                "tool_version": request.tool_version,
                "elder_id": request.elder_id,
                "purpose": request.purpose,
                "consent_version": request.consent_version,
                "policy_version": request.policy_version,
                "idempotency_key": request.idempotency_key,
                "expected_resource_version": request.expected_resource_version,
                "parameters": request.parameters,
            },
        )

    def _validate_replay_request(
        self,
        existing_call: AgentToolCall,
        request: ToolRequest,
    ) -> None:
        payload = existing_call.request_payload
        if not isinstance(payload, dict):
            raise ConflictError("Recorded tool call cannot be replayed")

        if (
            existing_call.agent_run_id != request.agent_run_id
            or existing_call.actor_id != self._actor.actor_id
            or existing_call.tool_name != request.tool_name
            or existing_call.tool_version != request.tool_version
            or payload.get("elder_id") != str(request.elder_id)
            or payload.get("purpose") != request.purpose
            or payload.get("parameter_keys") != sorted(request.parameters)
            or payload.get("request_fingerprint") != self._request_fingerprint(request)
        ):
            raise ConflictError("Tool call cannot be replayed with a different request")

    @staticmethod
    def _replayed_result(existing_call: AgentToolCall) -> ToolResult:
        response_payload = existing_call.response_payload
        if not isinstance(response_payload, dict):
            raise ConflictError("Recorded tool call cannot be replayed")

        try:
            return ToolResult.model_validate(
                {
                    "result_status": response_payload.get("result_status"),
                    "resource_id": response_payload.get("resource_id"),
                    "resource_version": response_payload.get("resource_version"),
                    "source_refs": response_payload.get("source_refs"),
                    "reason_code": existing_call.reason_code,
                    "retryable": existing_call.retryable,
                    "trace_id": existing_call.trace_id,
                }
            )
        except PydanticValidationError as exc:
            raise ConflictError("Recorded tool call cannot be replayed") from exc

    async def _record_result(
        self,
        *,
        request: ToolRequest,
        result: ToolResult,
    ) -> ToolResult:
        now = datetime.now(UTC)
        persisted_idempotency_key = None
        if request.idempotency_key:
            persisted_idempotency_key = await self._session.scalar(
                select(IdempotencyRecord.idempotency_key).where(
                    IdempotencyRecord.idempotency_key == request.idempotency_key,
                    IdempotencyRecord.tenant_id == self._actor.tenant_id,
                    IdempotencyRecord.actor_id == self._actor.actor_id,
                )
            )
        self._session.add(
            AgentToolCall(
                tool_call_id=request.tool_call_id,
                agent_run_id=request.agent_run_id,
                actor_id=self._actor.actor_id,
                idempotency_key=persisted_idempotency_key,
                tool_name=request.tool_name,
                tool_version=request.tool_version,
                request_payload={
                    "elder_id": str(request.elder_id),
                    "purpose": request.purpose,
                    "parameter_keys": sorted(request.parameters),
                    "request_fingerprint": self._request_fingerprint(request),
                },
                result_status="SUCCESS"
                if result.result_status == "NO_DATA"
                else result.result_status,
                response_payload={
                    "result_status": result.result_status,
                    "resource_id": str(result.resource_id) if result.resource_id else None,
                    "resource_version": result.resource_version,
                    "source_refs": [str(item) for item in result.source_refs],
                },
                reason_code=result.reason_code,
                retryable=result.retryable,
                trace_id=result.trace_id,
                completed_at=now,
            )
        )
        await self._session.flush()
        return result
