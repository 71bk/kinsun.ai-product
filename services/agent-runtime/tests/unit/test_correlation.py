from __future__ import annotations

from uuid import UUID

from agent_runtime.middleware.correlation import (
    normalize_correlation_id,
    resolve_correlation_id,
)


def test_only_canonical_uuid_v4_is_accepted_from_a_caller() -> None:
    valid = "abcdefab-cdef-4abc-8def-abcdefabcdef"

    assert normalize_correlation_id(valid) == valid
    for invalid in (
        None,
        "",
        "abc-123",
        "11111111-1111-1111-8111-111111111111",
        valid.upper(),
        "a" * 200,
        "11111111-1111-4111-7111-111111111111",
    ):
        assert normalize_correlation_id(invalid) is None

    generated = resolve_correlation_id("not-a-correlation-id")
    assert UUID(generated).version == 4
    assert generated != "not-a-correlation-id"
