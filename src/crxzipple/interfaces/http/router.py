from __future__ import annotations

from fastapi import APIRouter

from crxzipple.core.config import load_settings
from crxzipple.interfaces.http.conversations import router as conversations_router
from crxzipple.interfaces.http.turns import router as turns_router
from crxzipple.interfaces.http.ui import router as ui_router
from crxzipple.modules.access.interfaces.http import router as access_router
from crxzipple.modules.access.interfaces.ui_http import router as ui_access_router
from crxzipple.modules.agent.interfaces.http import router as agent_router
from crxzipple.modules.artifacts.interfaces.http import router as artifacts_router
from crxzipple.modules.browser.interfaces.http import router as browser_router
from crxzipple.modules.authorization.interfaces.http import router as authorization_router
from crxzipple.modules.channels.interfaces.http import router as channels_router
from crxzipple.modules.context_workspace.interfaces.http import (
    router as context_workspace_router,
)
from crxzipple.modules.dispatch.interfaces.http import router as dispatch_router
from crxzipple.modules.daemon.interfaces.http import router as daemon_router
from crxzipple.modules.events.interfaces.http import router as events_router
from crxzipple.modules.llm.interfaces.http import router as llm_router
from crxzipple.modules.memory.interfaces.http import router as memory_router
from crxzipple.modules.mobile.interfaces.http import router as mobile_router
from crxzipple.modules.ocr.interfaces.http import router as ocr_router
from crxzipple.modules.operations.interfaces.http import router as operations_router
from crxzipple.modules.orchestration.interfaces.http import (
    router as orchestration_router,
)
from crxzipple.modules.session.interfaces.http import router as session_router
from crxzipple.modules.settings.interfaces.http import router as settings_router
from crxzipple.modules.skills.interfaces.http import router as skills_router
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
api_router.include_router(artifacts_router, prefix="/artifacts", tags=["artifacts"])
api_router.include_router(browser_router, prefix="/browser", tags=["browser"])
api_router.include_router(channels_router, prefix="/channels", tags=["channels"])
api_router.include_router(
    context_workspace_router,
    prefix="/context-workspaces",
    tags=["context-workspaces"],
)
api_router.include_router(mobile_router, prefix="/mobile", tags=["mobile"])
api_router.include_router(ocr_router, prefix="/ocr", tags=["ocr"])
api_router.include_router(daemon_router, prefix="/daemon", tags=["daemon"])
api_router.include_router(events_router, prefix="/events", tags=["events"])
api_router.include_router(conversations_router, tags=["conversations"])
api_router.include_router(turns_router, tags=["turns"])
api_router.include_router(dispatch_router, prefix="/dispatch", tags=["dispatch"])
api_router.include_router(
    orchestration_router,
    prefix="/orchestration",
    tags=["orchestration"],
)
api_router.include_router(operations_router, prefix="/operations", tags=["operations"])
api_router.include_router(session_router, prefix="/sessions", tags=["sessions"])
api_router.include_router(llm_router, prefix="/llms", tags=["llms"])
api_router.include_router(memory_router, tags=["memory"])
api_router.include_router(agent_router, prefix="/agents", tags=["agents"])
api_router.include_router(skills_router, prefix="/skills", tags=["skills"])
api_router.include_router(settings_router, prefix="/settings", tags=["settings"])
api_router.include_router(access_router, prefix="/access", tags=["access"])
api_router.include_router(ui_access_router, prefix="/ui/access", tags=["ui", "access"])
api_router.include_router(
    settings_router,
    prefix="/ui/settings",
    tags=["ui", "settings"],
)
api_router.include_router(
    authorization_router,
    prefix="/authorization",
    tags=["authorization"],
)
api_router.include_router(ui_router, prefix="/ui", tags=["ui"])
