"""Shared repository types.

Defines data structures returned by multiple repository methods,
avoiding duplicate definitions across modules.
"""

from __future__ import annotations

from typing import NamedTuple
from uuid import UUID


class AuthorizedElderRow(NamedTuple):
    """Lightweight projection for authorized elder listing.

    Returned by both CareRelationshipRepository and CareAssignmentRepository
    to avoid loading full ORM objects when only display info is needed.
    """

    elder_id: UUID
    display_name: str
    care_unit_name: str | None
