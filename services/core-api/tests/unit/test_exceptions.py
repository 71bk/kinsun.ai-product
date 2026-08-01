"""Unit tests for the domain exception hierarchy (app/core/exceptions.py).

Validates:
- Exception inheritance relationships
- Message parameter handling
- ValidationError details attribute
- OptimisticConcurrencyError inherits from ConflictError
"""

from app.core.exceptions import (
    AuthenticationError,
    AuthorizationDeniedError,
    ConflictError,
    DomainException,
    NotFoundError,
    OptimisticConcurrencyError,
    ServiceUnavailableError,
    TenantImmutabilityError,
    TenantScopeError,
    ValidationError,
)


class TestDomainException:
    """Tests for the DomainException base class."""

    def test_is_exception(self):
        assert issubclass(DomainException, Exception)

    def test_default_message_is_empty(self):
        exc = DomainException()
        assert exc.message == ""
        assert str(exc) == ""

    def test_custom_message(self):
        exc = DomainException("something went wrong")
        assert exc.message == "something went wrong"
        assert str(exc) == "something went wrong"


class TestNotFoundError:
    """Tests for NotFoundError."""

    def test_inherits_from_domain_exception(self):
        assert issubclass(NotFoundError, DomainException)

    def test_message(self):
        exc = NotFoundError("entity not found")
        assert exc.message == "entity not found"

    def test_is_catchable_as_domain_exception(self):
        try:
            raise NotFoundError("missing")
        except DomainException as e:
            assert isinstance(e, NotFoundError)


class TestConflictError:
    """Tests for ConflictError."""

    def test_inherits_from_domain_exception(self):
        assert issubclass(ConflictError, DomainException)

    def test_message(self):
        exc = ConflictError("duplicate key")
        assert exc.message == "duplicate key"


class TestOptimisticConcurrencyError:
    """Tests for OptimisticConcurrencyError."""

    def test_inherits_from_conflict_error(self):
        assert issubclass(OptimisticConcurrencyError, ConflictError)

    def test_inherits_from_domain_exception(self):
        assert issubclass(OptimisticConcurrencyError, DomainException)

    def test_is_catchable_as_conflict_error(self):
        try:
            raise OptimisticConcurrencyError("stale version")
        except ConflictError as e:
            assert isinstance(e, OptimisticConcurrencyError)
            assert e.message == "stale version"

    def test_is_catchable_as_domain_exception(self):
        try:
            raise OptimisticConcurrencyError("stale")
        except DomainException as e:
            assert isinstance(e, OptimisticConcurrencyError)


class TestValidationError:
    """Tests for ValidationError."""

    def test_inherits_from_domain_exception(self):
        assert issubclass(ValidationError, DomainException)

    def test_requires_details(self):
        details = [{"field": "email", "reason": "invalid format"}]
        exc = ValidationError(details)
        assert exc.details == details
        assert exc.message == "Validation failed"

    def test_custom_message(self):
        details = [{"field": "name", "reason": "too short"}]
        exc = ValidationError(details, message="Input invalid")
        assert exc.message == "Input invalid"
        assert exc.details == details

    def test_multiple_details(self):
        details = [
            {"field": "email", "reason": "invalid format"},
            {"field": "age", "reason": "must be positive"},
        ]
        exc = ValidationError(details)
        assert len(exc.details) == 2
        assert exc.details[0]["field"] == "email"
        assert exc.details[1]["field"] == "age"

    def test_empty_details_list(self):
        exc = ValidationError([])
        assert exc.details == []


class TestAuthorizationDeniedError:
    """Tests for AuthorizationDeniedError."""

    def test_inherits_from_domain_exception(self):
        assert issubclass(AuthorizationDeniedError, DomainException)

    def test_message(self):
        exc = AuthorizationDeniedError("access denied")
        assert exc.message == "access denied"


class TestAuthenticationError:
    """Tests for AuthenticationError."""

    def test_inherits_from_domain_exception(self):
        assert issubclass(AuthenticationError, DomainException)

    def test_message(self):
        exc = AuthenticationError("invalid token")
        assert exc.message == "invalid token"


class TestServiceUnavailableError:
    """Tests for ServiceUnavailableError."""

    def test_inherits_from_domain_exception(self):
        assert issubclass(ServiceUnavailableError, DomainException)

    def test_message(self):
        exc = ServiceUnavailableError("Database is unavailable")
        assert exc.message == "Database is unavailable"


class TestTenantScopeError:
    """Tests for TenantScopeError."""

    def test_inherits_from_domain_exception(self):
        assert issubclass(TenantScopeError, DomainException)

    def test_message(self):
        exc = TenantScopeError("missing tenant context")
        assert exc.message == "missing tenant context"


class TestTenantImmutabilityError:
    """Tests for TenantImmutabilityError."""

    def test_inherits_from_domain_exception(self):
        assert issubclass(TenantImmutabilityError, DomainException)

    def test_message(self):
        exc = TenantImmutabilityError("cannot change tenant_id")
        assert exc.message == "cannot change tenant_id"
