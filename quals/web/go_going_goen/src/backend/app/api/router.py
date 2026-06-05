from fastapi import APIRouter

from app.api.routes.admin import router as admin_router
from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.shared import router as shared_router
from app.stages.stage1.dependencies import (
    get_current_user_id,
    get_pinpoint_service,
    get_stage1_guess_gate,
    get_stage1_reset_gate,
)
from app.stages.stage1.router import create_pinpoint_router
from app.stages.stage3.dependencies import (
    get_current_user_id as get_stage3_user_id,
    get_stage3_submission_gate,
    get_tango_service,
)
from app.stages.stage3.router import create_tango_router
from app.stages.stage2.dependencies import (
    get_current_user_id as get_stage2_user_id,
    get_queens_service,
    get_stage2_submission_gate,
)
from app.stages.stage2.router import create_queens_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router, prefix="/api")
api_router.include_router(admin_router, prefix="/api")
api_router.include_router(shared_router, prefix="/api")
api_router.include_router(
    create_pinpoint_router(
        get_service=get_pinpoint_service,
        get_current_user_id=get_current_user_id,
        get_guess_gate=get_stage1_guess_gate,
        get_reset_gate=get_stage1_reset_gate,
    )
)
api_router.include_router(
    create_queens_router(
        get_service=get_queens_service,
        get_current_user_id=get_stage2_user_id,
        get_submission_gate=get_stage2_submission_gate,
    )
)
api_router.include_router(
    create_tango_router(
        get_service=get_tango_service,
        get_current_user_id=get_stage3_user_id,
        get_submission_gate=get_stage3_submission_gate,
    )
)
