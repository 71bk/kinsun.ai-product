"""Versioned Argon2id password hashing and verification."""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from cryptography.exceptions import InvalidKey
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id


@dataclass(frozen=True)
class Argon2idPolicy:
    parameter_version: int
    memory_cost_kib: int
    iterations: int
    lanes: int
    salt_length: int = 16
    hash_length: int = 32

    def __post_init__(self) -> None:
        if self.parameter_version < 1:
            raise ValueError("Argon2id parameter version must be positive")
        if not 8_192 <= self.memory_cost_kib <= 1_048_576:
            raise ValueError("Argon2id memory cost must be between 8192 and 1048576 KiB")
        if not 1 <= self.iterations <= 10:
            raise ValueError("Argon2id iterations must be between 1 and 10")
        if not 1 <= self.lanes <= 16:
            raise ValueError("Argon2id lanes must be between 1 and 16")
        if not 16 <= self.salt_length <= 64:
            raise ValueError("Argon2id salt length must be between 16 and 64 bytes")
        if not 16 <= self.hash_length <= 64:
            raise ValueError("Argon2id hash length must be between 16 and 64 bytes")


class PasswordHasher:
    """Hash passwords to standard PHC strings without retaining plaintext."""

    def __init__(self, policy: Argon2idPolicy) -> None:
        self.policy = policy
        self._dummy_hash = self.hash("Kinsun timing equalization credential")

    @staticmethod
    def validate_password(password: str) -> bytes:
        if not 12 <= len(password) <= 128:
            raise ValueError("Password must contain between 12 and 128 characters")
        encoded = password.encode("utf-8")
        if len(encoded) > 1024 or "\x00" in password:
            raise ValueError("Password encoding is invalid")
        return encoded

    def hash(self, password: str) -> str:
        material = self.validate_password(password)
        policy = self.policy
        return Argon2id(
            salt=secrets.token_bytes(policy.salt_length),
            length=policy.hash_length,
            iterations=policy.iterations,
            lanes=policy.lanes,
            memory_cost=policy.memory_cost_kib,
        ).derive_phc_encoded(material)

    @staticmethod
    def verify(password: str, password_hash: str) -> bool:
        try:
            material = PasswordHasher.validate_password(password)
            Argon2id.verify_phc_encoded(material, password_hash)
        except (InvalidKey, ValueError):
            return False
        return True

    def verify_dummy(self, password: str) -> None:
        self.verify(password, self._dummy_hash)
