"""Privacy-safe identifiers used by the deletion workflow."""

from __future__ import annotations

from hashlib import sha256
from uuid import UUID


def hash_subject_ref(tenant_id: UUID, elder_id: UUID) -> str:
    """Return a stable opaque subject marker without retaining the raw IDs."""
    return sha256(f"tenant:{tenant_id}:elder:{elder_id}".encode()).hexdigest()


def hash_resource_ref(resource_type: str, resource_id: UUID) -> str:
    """Return the marker used to suppress replay of one deleted aggregate."""
    normalized_type = resource_type.strip().upper()
    return sha256(f"resource:{normalized_type}:{resource_id}".encode()).hexdigest()
