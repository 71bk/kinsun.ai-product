"""Authorization policies (RBAC + ABAC) for the Core API.

This package contains policy modules that evaluate access decisions.
All policies implement deny-by-default logic.
"""

from __future__ import annotations

from app.core.exceptions import AuthorizationDeniedError, DomainException
from app.policies.elder_access import (
    ElderAccessDecision,
    ElderAccessPolicy,
    ElderAccessRequest,
)


class ElderNotFoundError(AuthorizationDeniedError):
    """Elder not found or actor not authorized — non-disclosure.

    Maps to HTTP 404. The same response is returned whether the Elder
    does not exist or the actor lacks authorization, preventing
    information leakage about Elder existence.
    """

    pass


class RoleModeIncompatibleError(DomainException):
    """Actor role is incompatible with the requested mode.

    Raised when the actor's role does not match the requested
    authorized-elders mode (e.g. HOME_CARE_WORKER requesting mode=daycare).
    Maps to HTTP 403.
    """

    pass


class ActorInactiveError(DomainException):
    """Actor status is not ACTIVE.

    Raised when an actor with INACTIVE or SUSPENDED status attempts
    a business operation. Maps to HTTP 403.
    """

    pass


__all__ = [
    "ActorInactiveError",
    "ElderAccessDecision",
    "ElderAccessPolicy",
    "ElderAccessRequest",
    "ElderNotFoundError",
    "RoleModeIncompatibleError",
]
