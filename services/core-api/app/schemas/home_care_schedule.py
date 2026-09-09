"""Closed, content-free home-care schedule preview DTOs."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.identity import PaginationMeta


class HomeCareScheduleItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignment_id: UUID
    elder_id: UUID
    display_name: str
    scheduled_start: datetime
    scheduled_end: datetime
    status: Literal["CONFIRMED", "IN_PROGRESS"]
    timezone: str
    local_date: date


class HomeCareScheduleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[HomeCareScheduleItem]
    as_of: datetime
    page: PaginationMeta
