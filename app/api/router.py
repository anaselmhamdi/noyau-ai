from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.dispatch import router as dispatch_router
from app.api.events import router as events_router
from app.api.issues import router as issues_router
from app.api.jobs import router as jobs_router
from app.api.podcast import router as podcast_router
from app.api.slack import router as slack_router
from app.api.users import router as users_router

api_router = APIRouter()

# Auth routes at /auth/*
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(slack_router, prefix="/auth/slack", tags=["slack"])

# API routes at /api/*
api_router.include_router(users_router, prefix="/api", tags=["users"])
api_router.include_router(issues_router, prefix="/api", tags=["issues"])
api_router.include_router(events_router, prefix="/api", tags=["events"])
api_router.include_router(jobs_router, prefix="/api", tags=["jobs"])
api_router.include_router(dispatch_router, prefix="/api", tags=["dispatch"])
api_router.include_router(podcast_router, prefix="/api", tags=["podcast"])
