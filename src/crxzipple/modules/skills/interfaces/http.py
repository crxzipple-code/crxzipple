from __future__ import annotations

from fastapi import APIRouter

from crxzipple.modules.skills.interfaces.http_draft_routes import (
    router as draft_router,
)
from crxzipple.modules.skills.interfaces.http_skill_routes import (
    router as skill_router,
)
from crxzipple.modules.skills.interfaces.http_source_routes import (
    router as source_router,
)

router = APIRouter()
router.include_router(source_router)
router.include_router(draft_router)
# FastAPI rejects include_router for a child router with an empty root path.
# Append skill routes last so static routes like /install and /drafts win first.
router.routes.extend(skill_router.routes)
