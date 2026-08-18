"""Regression tests for the shared request-correlation context."""

from uuid import UUID

from app.api.error_handlers import _get_correlation_id as get_error_correlation_id
from app.api.responses import get_correlation_id as get_response_correlation_id
from app.core.correlation import correlation_id_var, get_correlation_id
from app.middleware.logging import correlation_id_var as middleware_correlation_id_var


def test_generated_correlation_id_is_stable_in_the_current_context() -> None:
    token = correlation_id_var.set("")
    try:
        generated = get_correlation_id()

        assert UUID(generated).version == 4
        assert get_correlation_id() == generated
    finally:
        correlation_id_var.reset(token)


def test_http_boundaries_share_the_core_correlation_context() -> None:
    assert middleware_correlation_id_var is correlation_id_var

    token = correlation_id_var.set("shared-correlation-id")
    try:
        assert get_response_correlation_id() == "shared-correlation-id"
        assert get_error_correlation_id() == "shared-correlation-id"
    finally:
        correlation_id_var.reset(token)
