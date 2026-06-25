from __future__ import annotations

from fastapi import APIRouter

from crxzipple.modules.operations.interfaces.http_action_routes_llm import (
    router as llm_router,
)
from crxzipple.modules.operations.interfaces.http_action_routes_orchestration import (
    router as orchestration_router,
)
from crxzipple.modules.operations.interfaces.http_action_routes_tool import (
    router as tool_router,
)

router = APIRouter()

router.include_router(llm_router)
router.include_router(orchestration_router)
router.include_router(tool_router)

