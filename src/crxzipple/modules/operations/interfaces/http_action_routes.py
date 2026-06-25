from __future__ import annotations

from fastapi import APIRouter

from crxzipple.modules.operations.interfaces.http_action_routes_channels import (
    router as channels_router,
)
from crxzipple.modules.operations.interfaces.http_action_routes_events import (
    router as events_router,
)
from crxzipple.modules.operations.interfaces.http_action_routes_execution import (
    router as execution_router,
)
from crxzipple.modules.operations.interfaces.http_action_routes_resources import (
    router as resources_router,
)

router = APIRouter()
router.include_router(execution_router)
router.include_router(resources_router)
router.include_router(channels_router)
router.include_router(events_router)
