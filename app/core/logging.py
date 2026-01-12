import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from app.config import get_settings


class InterceptHandler(logging.Handler):
    """Intercept stdlib logging and redirect to loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        # Get corresponding Loguru level if it exists
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back  # type: ignore[assignment]
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def _health_log_filter(record: dict[str, Any]) -> bool:
    """Filter health check logs - only show at DEBUG level."""
    message = record.get("message", "")
    if "/health" in message:
        return bool(record["level"].no <= 10)  # DEBUG level
    return True


def _upload_rotated_log_to_s3(log_path: str) -> None:
    """Upload rotated log file to S3 bucket."""
    try:
        from app.services.storage_service import get_storage_service

        storage = get_storage_service()
        if storage.is_configured():
            # Run async upload in sync context
            asyncio.get_event_loop().run_until_complete(
                storage.archive_log_file(Path(log_path), compress=True)
            )
            logger.info(f"Uploaded rotated log to S3: {log_path}")
    except Exception as e:
        # Don't fail if S3 upload fails - just log to stderr
        print(f"Failed to upload log to S3: {e}", file=sys.stderr)


def setup_logging() -> None:
    """Configure loguru for the application."""
    settings = get_settings()

    # Remove default handler
    logger.remove()

    # Console output with colors in debug, JSON in production
    if settings.debug:
        logger.add(
            sys.stderr,
            level="DEBUG",
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "<level>{message}</level>"
            ),
            backtrace=True,
            diagnose=True,
        )
    else:
        # Human-readable format for production - logs go to stderr (docker logs)
        logger.add(
            sys.stderr,
            level="INFO",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
            filter=_health_log_filter,
            backtrace=True,
            diagnose=False,
        )
        # Note: For log archival to S3, use docker logging driver
        # or run: docker logs api-1 > app.log && upload to S3

    # Intercept stdlib logging (uvicorn, sqlalchemy, httpx, etc.)
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for name in [
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "sqlalchemy.engine",
        "httpx",
        "aiohttp",
    ]:
        logging.getLogger(name).handlers = [InterceptHandler()]


def get_logger(name: str) -> Any:
    """Get a logger bound to a name (for compatibility with existing code)."""
    return logger.bind(name=name)
