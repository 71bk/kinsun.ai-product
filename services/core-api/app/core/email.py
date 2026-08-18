"""Shared, validation-free email text normalization."""

from __future__ import annotations


def normalize_email_text(value: str) -> str:
    """Trim and case-fold an email-shaped value without validating its shape."""
    return value.strip().casefold()
