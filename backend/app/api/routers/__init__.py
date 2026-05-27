from fastapi import APIRouter

from .calendar import router as calendar_router
from .drafts import router as drafts_router
from .emails import router as emails_router
from .followups import router as followups_router
from .local_auth import router as local_auth_router
from .oauth import router as oauth_router
from .root import router as root_router
from .settings import router as settings_router

api_router = APIRouter(prefix="/api")
api_router.include_router(settings_router)
api_router.include_router(local_auth_router)
api_router.include_router(oauth_router)
api_router.include_router(emails_router)
api_router.include_router(followups_router)
api_router.include_router(drafts_router)
api_router.include_router(calendar_router)

__all__ = ["api_router", "root_router"]
