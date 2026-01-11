from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.config import get_settings
from app.core.logging import setup_logging
from app.core.scheduler import start_scheduler, stop_scheduler

# UI static files directory (built by Docker)
UI_DIR = Path(__file__).parent.parent / "public"

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


# Serve static UI files (only if built UI exists)
if UI_DIR.exists():
    # Mount static assets (js, css, images)
    app.mount("/_astro", StaticFiles(directory=UI_DIR / "_astro"), name="astro_assets")

    @app.get("/{path:path}")
    async def serve_spa(request: Request, path: str) -> FileResponse:
        """Serve static files or fall back to index.html for SPA routing."""
        file_path = UI_DIR / path

        # Serve exact file if it exists
        if file_path.is_file():
            return FileResponse(file_path)

        # Try with .html extension (Astro generates /about -> /about.html)
        html_path = UI_DIR / f"{path}.html"
        if html_path.is_file():
            return FileResponse(html_path)

        # Fall back to index.html for SPA routing
        return FileResponse(UI_DIR / "index.html")
