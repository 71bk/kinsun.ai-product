"""Health endpoint for process liveness checks.

GET /health returns 200 with {"status": "ok", "uptime_seconds": N}.
No database dependency, no authentication required.
Non-GET methods return 405 (handled automatically by FastAPI).
"""

import time

from fastapi import APIRouter

router = APIRouter()

_start_time = time.time()


@router.get("/health")
async def health() -> dict:
    """Process liveness check.

    Always returns 200 while the process is alive.
    Does NOT access the database — no DB dependency whatsoever.
    """
    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - _start_time),
    }
