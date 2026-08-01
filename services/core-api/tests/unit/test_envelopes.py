"""Unit tests for app.core.envelopes module."""

from datetime import UTC, datetime

from app.core.envelopes import (
    ErrorBody,
    ErrorEnvelope,
    ResponseMeta,
    SuccessEnvelope,
    ValidationDetail,
)


class TestResponseMeta:
    def test_creates_with_correlation_id_and_timestamp(self) -> None:
        ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        meta = ResponseMeta(correlation_id="abc-123", timestamp=ts)

        assert meta.correlation_id == "abc-123"
        assert meta.timestamp == ts

    def test_serializes_to_dict(self) -> None:
        ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        meta = ResponseMeta(correlation_id="req-456", timestamp=ts)
        data = meta.model_dump()

        assert data["correlation_id"] == "req-456"
        assert data["timestamp"] == ts


class TestSuccessEnvelope:
    def test_wraps_string_data(self) -> None:
        ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        meta = ResponseMeta(correlation_id="c-1", timestamp=ts)
        envelope = SuccessEnvelope[str](data="hello", meta=meta)

        assert envelope.data == "hello"
        assert envelope.meta.correlation_id == "c-1"

    def test_wraps_dict_data(self) -> None:
        ts = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        meta = ResponseMeta(correlation_id="c-2", timestamp=ts)
        payload = {"id": "123", "name": "Test"}
        envelope = SuccessEnvelope[dict](data=payload, meta=meta)

        assert envelope.data == payload
        assert envelope.meta.timestamp == ts

    def test_wraps_list_data(self) -> None:
        ts = datetime(2024, 3, 10, 8, 0, 0, tzinfo=UTC)
        meta = ResponseMeta(correlation_id="c-3", timestamp=ts)
        items = [1, 2, 3]
        envelope = SuccessEnvelope[list](data=items, meta=meta)

        assert envelope.data == items

    def test_serializes_to_json(self) -> None:
        ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        meta = ResponseMeta(correlation_id="c-json", timestamp=ts)
        envelope = SuccessEnvelope[str](data="value", meta=meta)
        json_str = envelope.model_dump_json()

        assert "value" in json_str
        assert "c-json" in json_str


class TestValidationDetail:
    def test_creates_with_field_and_reason(self) -> None:
        detail = ValidationDetail(field="email", reason="Invalid format")

        assert detail.field == "email"
        assert detail.reason == "Invalid format"

    def test_serializes_to_dict(self) -> None:
        detail = ValidationDetail(field="age", reason="Must be positive")
        data = detail.model_dump()

        assert data == {"field": "age", "reason": "Must be positive"}


class TestErrorBody:
    def test_creates_without_details(self) -> None:
        body = ErrorBody(
            code="NOT_FOUND",
            message="Resource not found",
            correlation_id="err-1",
        )

        assert body.code == "NOT_FOUND"
        assert body.message == "Resource not found"
        assert body.correlation_id == "err-1"
        assert body.details is None

    def test_creates_with_details(self) -> None:
        details = [
            ValidationDetail(field="name", reason="Required"),
            ValidationDetail(field="email", reason="Invalid format"),
        ]
        body = ErrorBody(
            code="VALIDATION_ERROR",
            message="Validation failed",
            correlation_id="err-2",
            details=details,
        )

        assert body.details is not None
        assert len(body.details) == 2
        assert body.details[0].field == "name"
        assert body.details[1].reason == "Invalid format"

    def test_details_defaults_to_none(self) -> None:
        body = ErrorBody(
            code="CONFLICT",
            message="Version mismatch",
            correlation_id="err-3",
        )

        assert body.details is None


class TestErrorEnvelope:
    def test_wraps_error_body(self) -> None:
        body = ErrorBody(
            code="SERVICE_UNAVAILABLE",
            message="Database unavailable",
            correlation_id="err-env-1",
        )
        envelope = ErrorEnvelope(error=body)

        assert envelope.error.code == "SERVICE_UNAVAILABLE"
        assert envelope.error.correlation_id == "err-env-1"

    def test_serializes_to_json(self) -> None:
        body = ErrorBody(
            code="AUTH_ERROR",
            message="Unauthorized",
            correlation_id="err-env-2",
        )
        envelope = ErrorEnvelope(error=body)
        json_str = envelope.model_dump_json()

        assert "AUTH_ERROR" in json_str
        assert "err-env-2" in json_str

    def test_serializes_with_validation_details(self) -> None:
        details = [ValidationDetail(field="password", reason="Too short")]
        body = ErrorBody(
            code="VALIDATION_ERROR",
            message="Validation failed",
            correlation_id="err-env-3",
            details=details,
        )
        envelope = ErrorEnvelope(error=body)
        data = envelope.model_dump()

        assert data["error"]["details"][0]["field"] == "password"
        assert data["error"]["details"][0]["reason"] == "Too short"
