"""Hash-only, tenant-owned workforce invitation."""

from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel, TenantScopedMixin, VersionedMixin


class StaffInvitation(BaseModel, TenantScopedMixin, VersionedMixin):
    __tablename__ = "staff_invitation"
    __pk_name__ = "staff_invitation_id"
    __mapper_args__ = {"eager_defaults": True}

    issued_by_actor_id: Mapped[UUID] = mapped_column(sa.Uuid, nullable=False)
    care_unit_id: Mapped[UUID] = mapped_column(sa.Uuid, nullable=False)
    display_name: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    role_code: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    email_digest: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    digest_key_version: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    token_digest: Mapped[str] = mapped_column(sa.String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(sa.String(16), nullable=False, server_default="ISSUED")
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    accepted_by_actor_id: Mapped[UUID | None] = mapped_column(sa.Uuid)
    accepted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
