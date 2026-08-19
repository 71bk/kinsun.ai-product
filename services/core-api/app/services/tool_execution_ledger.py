"""Persistence ledger for Tool execution audit and replay."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ActorContext
from app.core.exceptions import ConflictError
from app.models.agent import AgentRun, AgentToolCall
from app.models.idempotency import IdempotencyRecord
from app.repositories.idempotency_repo import IdempotencyRepository
from app.schemas.tool import ToolRequest, ToolResult


class ToolExecutionLedger:
    """Own persisted Tool call identity, replay, and audit records."""

    def __init__(
        self,
        session: AsyncSession,
        actor_context: ActorContext,
    ) -> None:
        self._session = session
        self._actor = actor_context

    async def find_tool_call(self, tool_call_id: UUID) -> AgentToolCall | None:
        return await self._session.get(AgentToolCall, tool_call_id)

    async def find_bound_run(self, request: ToolRequest) -> AgentRun | None:
        return await self._session.scalar(
            select(AgentRun).where(
                AgentRun.agent_run_id == request.agent_run_id,
                AgentRun.tenant_id == self._actor.tenant_id,
                AgentRun.elder_id == request.elder_id,
                AgentRun.actor_id == self._actor.actor_id,
            )
        )

    @staticmethod
    def request_fingerprint(request: ToolRequest) -> str:
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

    def validate_replay_request(
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
            or payload.get("request_fingerprint") != self.request_fingerprint(request)
        ):
            raise ConflictError("Tool call cannot be replayed with a different request")

    @staticmethod
    def replayed_result(existing_call: AgentToolCall) -> ToolResult:
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

    async def record_result(
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
                    "request_fingerprint": self.request_fingerprint(request),
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
