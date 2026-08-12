"""Core-owned App Session lifecycle endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responses import success
from app.core.config import get_settings
from app.core.exceptions import AuthenticationError
from app.db.session import get_db_session
from app.services.app_session_service import AppSessionPolicy, AppSessionService
from app.services.app_session_tokens import AppSessionTokenCodec

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
_AUTHENTICATION_REQUIRED = "Authentication required"


class AppSessionLogoutResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["SIGNED_OUT"] = "SIGNED_OUT"


def app_session_bearer(request: Request) -> str:
    values = request.headers.getlist("authorization")
    if len(values) != 1:
        raise AuthenticationError(_AUTHENTICATION_REQUIRED)
    scheme, separator, token = values[0].partition(" ")
    if separator != " " or scheme.casefold() != "bearer":
        raise AuthenticationError(_AUTHENTICATION_REQUIRED)
    try:
        AppSessionTokenCodec().digest(token)
    except ValueError:
        raise AuthenticationError(_AUTHENTICATION_REQUIRED) from None
    return token


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout_app_session(
    response: Response,
    token: str = Depends(app_session_bearer),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Idempotently revoke one well-formed App Session credential."""
    await AppSessionService(
        session,
        AppSessionPolicy.from_settings(get_settings()),
    ).revoke(token)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return success(AppSessionLogoutResponse().model_dump(mode="json"))
