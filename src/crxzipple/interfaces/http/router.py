from __future__ import annotations

from fastapi import APIRouter

from crxzipple.core.config import load_settings
from crxzipple.interfaces.http.conversations import router as conversations_router
from crxzipple.interfaces.http.turns import router as turns_router
from crxzipple.modules.agent.interfaces.http import router as agent_router
from crxzipple.modules.authorization.interfaces.http import router as authorization_router
from crxzipple.modules.dispatch.interfaces.http import router as dispatch_router
from crxzipple.modules.llm.interfaces.http import router as llm_router
from crxzipple.modules.memory.interfaces.http import router as memory_router
from crxzipple.modules.orchestration.interfaces.http import (
    router as orchestration_router,
)
from crxzipple.modules.session.interfaces.http import router as session_router
from crxzipple.modules.tool.interfaces.http import router as tool_router


api_router = APIRouter()


@api_router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@api_router.get("/about")
def about() -> dict[str, str]:
    settings = load_settings()
    return {
        "app_name": settings.app_name,
        "environment": settings.environment,
    }


api_router.include_router(tool_router, prefix="/tools", tags=["tools"])
api_router.include_router(conversations_router, tags=["conversations"])
api_router.include_router(turns_router, tags=["turns"])
api_router.include_router(dispatch_router, prefix="/dispatch", tags=["dispatch"])
api_router.include_router(
    orchestration_router,
    prefix="/orchestration",
    tags=["orchestration"],
)
api_router.include_router(session_router, prefix="/sessions", tags=["sessions"])
api_router.include_router(llm_router, prefix="/llms", tags=["llms"])
api_router.include_router(memory_router, tags=["memory"])
api_router.include_router(agent_router, prefix="/agents", tags=["agents"])
api_router.include_router(
    authorization_router,
    prefix="/authorization",
    tags=["authorization"],
)
