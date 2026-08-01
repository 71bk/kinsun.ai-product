from fastapi import APIRouter

from agent_runtime.settings import get_settings

router = APIRouter()


@router.get("/health")
async def get_health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "service": "agent-runtime",
        "version": settings.API_VERSION,
    }
