from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.events import router as events_router
from app.api.push import router as push_router
from app.api.schedule import router as schedule_router
from app.api.sync import router as sync_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(schedule_router)
api_router.include_router(events_router)
api_router.include_router(push_router)
api_router.include_router(sync_router)

__all__ = ["api_router"]

