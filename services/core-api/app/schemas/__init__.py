"""Pydantic request/response schemas for the Core API.

Re-exports all schema classes for convenient imports.
"""

from app.schemas.elder import AccessContextResponse, ElderResponse
from app.schemas.identity import (
    AuthorizedElderItem,
    AuthorizedEldersResponse,
    ElderMode,
    MeResponse,
    PaginationMeta,
)

__all__ = [
    "AccessContextResponse",
    "AuthorizedElderItem",
    "AuthorizedEldersResponse",
    "ElderMode",
    "ElderResponse",
    "MeResponse",
    "PaginationMeta",
]
