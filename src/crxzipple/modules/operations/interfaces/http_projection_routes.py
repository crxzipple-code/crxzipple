from __future__ import annotations

from fastapi import APIRouter

from crxzipple.modules.operations.interfaces.http_projection_detail_routes import (
    router as detail_router,
)
from crxzipple.modules.operations.interfaces.http_projection_overview_routes import (
    router as overview_router,
)
from crxzipple.modules.operations.interfaces.http_projection_runtime_routes import (
    router as runtime_router,
)
from crxzipple.modules.operations.interfaces.http_projection_support_routes import (
    router as support_router,
)

router = APIRouter()

router.include_router(runtime_router)
router.include_router(support_router)
router.include_router(detail_router)
router.include_router(overview_router)
