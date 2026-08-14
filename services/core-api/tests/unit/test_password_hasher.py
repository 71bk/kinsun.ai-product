from __future__ import annotations

import pytest

from app.services.password_hasher import Argon2idPolicy, PasswordHasher


@pytest.fixture(scope="module")
def hasher() -> PasswordHasher:
    return PasswordHasher(
        Argon2idPolicy(
            parameter_version=1,
            memory_cost_kib=8_192,
            iterations=1,
            lanes=1,
        )
    )


def test_argon2id_phc_hash_uses_unique_salts(hasher: PasswordHasher) -> None:
    first = hasher.hash("a sufficiently long password")
    second = hasher.hash("a sufficiently long password")

    assert first.startswith("$argon2id$v=19$")
    assert second.startswith("$argon2id$v=19$")
    assert first != second
    assert hasher.verify("a sufficiently long password", first) is True
    assert hasher.verify("the wrong long password", first) is False


@pytest.mark.parametrize("password", ["too-short", "x" * 129, "valid-length\x00password"])
def test_password_policy_rejects_invalid_values(
    hasher: PasswordHasher,
    password: str,
) -> None:
    with pytest.raises(ValueError):
        hasher.hash(password)
