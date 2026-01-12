from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from app.api.router import api_router
from app.config import get_settings
from app.core.logging import setup_logging
from app.core.scheduler import start_scheduler, stop_scheduler

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown."""
    # Startup
    setup_logging()
    await start_scheduler()
    yield
    # Shutdown
    await stop_scheduler()


app = FastAPI(
    title="NoyauAI",
    description="Daily tech digest API for noyau.news",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.debug else None,
    redoc_url="/api/redoc" if settings.debug else None,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.base_url, "http://localhost:4321"],  # Astro dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint for load balancers."""
    return {"status": "healthy"}


@app.get("/tiktok5jv3QAzhtw6g0bwbctXEnI0OoLYipkiu.txt")
async def tiktok_verification() -> PlainTextResponse:
    """TikTok domain verification file."""
    return PlainTextResponse("tiktok-developers-site-verification=5jv3QAzhtw6g0bwbctXEnI0OoLYipkiu")
