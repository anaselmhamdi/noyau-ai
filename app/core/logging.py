import logging
import sys
from typing import Any

from loguru import logger

from app.config import get_settings


class InterceptHandler(logging.Handler):
    """Intercept stdlib logging and redirect to loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        # Get corresponding Loguru level if it exists
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


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
        # JSON format for production (structured logging)
        logger.add(
            sys.stderr,
            level="INFO",
            serialize=True,
            backtrace=True,
            diagnose=False,
        )

        # File logging with rotation for production
        import os

        log_dir = settings.log_dir
        os.makedirs(log_dir, exist_ok=True)
        logger.add(
            f"{log_dir}/app.log",
            level="INFO",
            rotation="100 MB",
            retention="7 days",
            compression="gz",
            serialize=True,
        )

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
