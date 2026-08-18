"""Dispatch already-authorized Tool commands to bounded domain operations."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ActorContext
from app.core.exceptions import ValidationError
from app.repositories.care_assignment_repo import CareAssignmentRepository
from app.schemas.care_event import CreateCareEventCandidateRequest
from app.schemas.memory import CreateMemoryCandidateRequest
from app.schemas.summary import CreateSummaryDraftRequest
from app.schemas.tool import ToolRequest, ToolResult
from app.services.care_event_service import CareEventService
from app.services.memory_service import MemoryService
from app.services.summary_service import SummaryService


class ToolCommandDispatcher:
    """Map a gated Tool request to its domain operation."""

    def __init__(
        self,
        session: AsyncSession,
        actor_context: ActorContext,
    ) -> None:
        self._session = session
        self._actor = actor_context

    async def dispatch(self, request: ToolRequest, trace_id: str) -> ToolResult:
        if request.tool_name == "retrieve_confirmed_memory":
            service = MemoryService(self._session, self._actor.tenant_id)
            limit = self._bounded_limit(request.parameters.get("limit"), default=5, maximum=10)
            memories = await service.list_trusted_context(
                elder_id=request.elder_id,
                limit=limit,
            )
            data = [
                {
                    "memory_id": str(memory.memory_id),
                    "memory_type": memory.memory_type,
                    "content": memory.content,
                    "version": memory.version,
                }
                for memory in memories
            ]
            return ToolResult(
                result_status="SUCCESS" if data else "NO_DATA",
                data=data,
                source_refs=[memory.memory_id for memory in memories],
                trace_id=trace_id,
            )

        if request.tool_name == "retrieve_verified_event":
            service = CareEventService(self._session, self._actor.tenant_id)
            limit = self._bounded_limit(
                request.parameters.get("limit"),
                default=10,
                maximum=20,
            )
            events = await service.list_for_elder(
                elder_id=request.elder_id,
                statuses=["VERIFIED", "CORRECTED"],
                limit=limit,
                cursor=None,
            )
            data = []
            for event in events[:20]:
                version = await service.get_version(event)
                data.append(
                    {
                        "event_id": str(event.id),
                        "event_type": event.event_type,
                        "event_time": event.event_time,
                        "structured_payload": version.structured_payload,
                        "version": event.current_version,
                    }
                )
            return ToolResult(
                result_status="SUCCESS" if data else "NO_DATA",
                data=data,
                source_refs=[event.id for event in events[:20]],
                trace_id=trace_id,
            )

        if request.tool_name == "retrieve_daily_summary":
            service = SummaryService(self._session, self._actor.tenant_id)
            summaries = await service.list_for_date(
                elder_id=request.elder_id,
                summary_date=None,
                statuses=["READY"],
            )
            data = []
            for summary in summaries[:7]:
                version = await service.get_version(summary)
                data.append(
                    {
                        "summary_id": str(summary.id),
                        "summary_date": summary.summary_date,
                        "content": version.content,
                        "version": summary.current_version,
                    }
                )
            return ToolResult(
                result_status="SUCCESS" if data else "NO_DATA",
                data=data,
                source_refs=[summary.id for summary in summaries[:7]],
                trace_id=trace_id,
            )

        if request.tool_name == "get_assignment_context":
            assignment = await CareAssignmentRepository(
                self._session,
                self._actor.tenant_id,
            ).find_valid_for_worker(
                worker_id=self._actor.actor_id,
                elder_id=request.elder_id,
                current_time=datetime.now(UTC),
            )
            if assignment is None:
                return ToolResult(
                    result_status="NO_DATA",
                    reason_code="NO_VALID_ASSIGNMENT",
                    trace_id=trace_id,
                )
            return ToolResult(
                result_status="SUCCESS",
                data={
                    "assignment_id": str(assignment.id),
                    "service_scope": assignment.service_scope,
                    "expires_at": assignment.service_end,
                },
                resource_id=assignment.id,
                resource_version=assignment.version,
                source_refs=[assignment.id],
                trace_id=trace_id,
            )

        if request.tool_name == "create_event_candidate":
            parsed = CreateCareEventCandidateRequest.model_validate(request.parameters)
            event = await CareEventService(
                self._session,
                self._actor.tenant_id,
            ).create_candidate(
                elder_id=request.elder_id,
                actor_id=self._actor.actor_id,
                request=parsed,
                trace_id=trace_id,
                idempotency_key=request.idempotency_key,
            )
            return ToolResult(
                result_status="SUCCESS",
                resource_id=event.id,
                resource_version=event.current_version,
                trace_id=trace_id,
            )

        if request.tool_name == "create_memory_candidate":
            parsed = CreateMemoryCandidateRequest.model_validate(request.parameters)
            memory = await MemoryService(
                self._session,
                self._actor.tenant_id,
            ).create_candidate(
                elder_id=request.elder_id,
                actor_id=self._actor.actor_id,
                request=parsed,
                trace_id=trace_id,
                idempotency_key=request.idempotency_key,
            )
            return ToolResult(
                result_status="SUCCESS",
                resource_id=memory.id,
                resource_version=memory.current_version,
                trace_id=trace_id,
            )

        if request.tool_name == "create_summary_draft":
            parsed = CreateSummaryDraftRequest.model_validate(request.parameters)
            summary = await SummaryService(
                self._session,
                self._actor.tenant_id,
            ).create_draft(
                elder_id=request.elder_id,
                actor_id=self._actor.actor_id,
                request=parsed,
                trace_id=trace_id,
                idempotency_key=request.idempotency_key,
            )
            return ToolResult(
                result_status="SUCCESS",
                resource_id=summary.id,
                resource_version=summary.current_version,
                trace_id=trace_id,
            )

        raise ValidationError(
            details=[{"field": "tool_name", "reason": "tool is not dispatchable"}]
        )

    @staticmethod
    def _bounded_limit(value: object, *, default: int, maximum: int) -> int:
        if value is None:
            return default
        if isinstance(value, bool):
            raise ValidationError(
                details=[{"field": "parameters.limit", "reason": "limit must be an integer"}]
            )
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                details=[{"field": "parameters.limit", "reason": "limit must be an integer"}]
            ) from exc
        if parsed < 1:
            raise ValidationError(
                details=[{"field": "parameters.limit", "reason": "limit must be positive"}]
            )
        return min(parsed, maximum)
