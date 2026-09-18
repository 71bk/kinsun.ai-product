"""Minimal workforce invitation commands and receipts."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.schemas.kinsun_email_auth import PasswordLoginRequest

StaffRole = Literal["DAYCARE_CARE_WORKER", "HOME_CARE_WORKER"]


class CreateStaffInvitationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    email: str = Field(min_length=3, max_length=254)
    display_name: str = Field(min_length=1, max_length=120)
    role_code: StaffRole
    care_unit_id: UUID

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return PasswordLoginRequest.validate_email(value)


class AcceptStaffInvitationRequest(PasswordLoginRequest):
    invitation_token: SecretStr = Field(json_schema_extra={"pattern": r"^wi1_[A-Za-z0-9_-]{43}$"})
    password: SecretStr = Field(json_schema_extra={"minLength": 12, "maxLength": 128})

    @field_validator("invitation_token")
    @classmethod
    def validate_token(cls, value: SecretStr) -> SecretStr:
        import re

        if not re.fullmatch(r"wi1_[A-Za-z0-9_-]{43}", value.get_secret_value()):
            raise ValueError("invalid invitation credential")
        return value


class RevokeStaffInvitationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)


class StaffInvitationView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invitation_id: UUID
    display_name: str
    role_code: StaffRole
    care_unit_id: UUID
    status: Literal["ISSUED", "ACCEPTED", "REVOKED", "EXPIRED"]
    expires_at: datetime
    version: int = Field(ge=1)


class CreatedStaffInvitationResponse(StaffInvitationView):
    invitation_token: str = Field(pattern=r"^wi1_[A-Za-z0-9_-]{43}$")


class StaffInvitationListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[StaffInvitationView]
    next_cursor: str | None


class StaffCareUnitView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    care_unit_id: UUID
    name: str
    unit_type: Literal["DAYCARE_CENTER", "COMMUNITY_SITE", "HOME_CARE_AGENCY"]


class StaffCareUnitListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[StaffCareUnitView]
    next_cursor: str | None


class AcceptedStaffInvitationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ACTIVATED"] = "ACTIVATED"
