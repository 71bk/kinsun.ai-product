"""Domain exception hierarchy for the Core API.

Defines all domain-specific exceptions used across the application.
Each exception maps to a specific HTTP status code via the error handler
registration (see app/api/error_handlers.py or app/main.py).

Exception hierarchy:
    DomainException (base)
    ├── NotFoundError              → HTTP 404
    ├── ConflictError              → HTTP 409
    │   └── OptimisticConcurrencyError → HTTP 409
    ├── ValidationError            → HTTP 422 (with details array)
    ├── AuthorizationDeniedError   → HTTP 404 (hides resource existence)
    ├── AuthenticationError        → HTTP 401
    ├── ServiceUnavailableError    → HTTP 503 (degraded mode)
    ├── TenantScopeError           → HTTP 401
    └── TenantImmutabilityError    → HTTP 500 (internal bug)
"""

from __future__ import annotations


class DomainException(Exception):
    """Base for all domain-specific exceptions."""

    def __init__(self, message: str = "") -> None:
        self.message = message
        super().__init__(message)


class NotFoundError(DomainException):
    """Entity not found or access denied (returns 404)."""

    pass


class ConflictError(DomainException):
    """Concurrent modification or duplicate (returns 409)."""

    pass


class ValidationError(DomainException):
    """Input validation failure (returns 422).

    Attributes:
        details: A list of dicts, each containing at minimum 'field' and 'reason'
                 keys describing individual validation failures.
    """

    def __init__(self, details: list[dict], message: str = "Validation failed") -> None:
        self.details = details
        super().__init__(message)


class AuthorizationDeniedError(DomainException):
    """Access denied — mapped to 404 to hide resource existence."""

    pass


class AuthenticationError(DomainException):
    """Authentication failure (returns 401)."""

    pass


class ServiceUnavailableError(DomainException):
    """Service dependency unavailable (returns 503)."""

    pass


class TenantScopeError(DomainException):
    """Missing or invalid tenant context."""

    pass


class OptimisticConcurrencyError(ConflictError):
    """Stale version on update (returns 409)."""

    pass


class TenantImmutabilityError(DomainException):
    """Attempt to modify tenant_id after creation."""

    pass
