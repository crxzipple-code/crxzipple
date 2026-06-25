from __future__ import annotations

from fastapi import APIRouter

from crxzipple.modules.operations.interfaces.http_action_routes_access import (
    router as access_router,
)
from crxzipple.modules.operations.interfaces.http_action_routes_audit import (
    router as audit_router,
)
from crxzipple.modules.operations.interfaces.http_action_routes_daemon_memory import (
    router as daemon_memory_router,
)
from crxzipple.modules.operations.interfaces.http_action_routes_skills import (
    router as skills_router,
)

router = APIRouter()

router.include_router(skills_router)
router.include_router(access_router)
router.include_router(daemon_memory_router)
router.include_router(audit_router)

