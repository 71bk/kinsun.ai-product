"""Dependency-neutral helpers for nested restricted-key checks."""

from __future__ import annotations

from collections.abc import Collection


def contains_restricted_key(value: object, forbidden_keys: Collection[str]) -> bool:
    """Return whether a nested dict/list contains a case-insensitive forbidden key."""
    if isinstance(value, dict):
        return any(
            str(key).lower() in forbidden_keys or contains_restricted_key(item, forbidden_keys)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(contains_restricted_key(item, forbidden_keys) for item in value)
    return False
