from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from agent_runtime.rag.models import HybridSearchPlan


@dataclass(frozen=True, slots=True)
class SearchHit:
    """Provider-neutral search result consumed by the bounded retriever."""

    score: float
    source: Mapping[str, object]


@runtime_checkable
class SearchBackend(Protocol):
    """Boundary implemented by OpenSearch today and other stores later."""

    async def search(self, plan: HybridSearchPlan) -> list[SearchHit]: ...

    async def aclose(self) -> None: ...
