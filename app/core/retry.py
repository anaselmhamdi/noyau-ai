"""Retry and backoff utilities for resilient operations.

This module provides exponential backoff retry functionality for async operations,
particularly useful for network requests and external API calls.
"""

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    backoff_base: float = 1.0
    backoff_max: float = 30.0
    jitter: bool = True
    retryable_exceptions: tuple[type[Exception], ...] = field(default_factory=lambda: (Exception,))


async def retry_with_backoff[T](
    fn: Callable[[], Awaitable[T]],
    config: RetryConfig | None = None,
    operation_name: str = "operation",
) -> T:
    """
    Execute async function with exponential backoff retry.

    Uses exponential backoff with optional jitter to retry failed operations.
    Each retry waits for: min(backoff_base * 2^attempt, backoff_max) seconds,
    with random jitter applied if enabled.

    Args:
        fn: Async function to execute (no arguments)
        config: Retry configuration, uses defaults if not provided
        operation_name: Name for logging purposes

    Returns:
        Result of fn()

    Raises:
        Exception: The last exception if all retries are exhausted

    Example:
        ```python
        config = RetryConfig(max_attempts=3, retryable_exceptions=(aiohttp.ClientError,))
        result = await retry_with_backoff(
            lambda: fetch_url(url),
            config=config,
            operation_name=f"fetch:{url}",
        )
        ```
    """
    config = config or RetryConfig()
    last_exception: Exception | None = None

    for attempt in range(config.max_attempts):
        try:
            return await fn()
        except config.retryable_exceptions as e:
            last_exception = e

            if attempt + 1 == config.max_attempts:
                logger.error(
                    "retry_exhausted",
                    operation=operation_name,
                    attempts=config.max_attempts,
                    error=str(e),
                )
                raise

            # Calculate backoff with optional jitter
            delay = min(config.backoff_base * (2**attempt), config.backoff_max)
            if config.jitter:
                delay *= 0.5 + random.random()

            logger.warning(
                "retry_attempt",
                operation=operation_name,
                attempt=attempt + 1,
                max_attempts=config.max_attempts,
                delay_seconds=round(delay, 2),
                error=str(e),
            )
            await asyncio.sleep(delay)

    # This should never be reached, but satisfies type checker
    if last_exception is not None:
        raise last_exception
    raise RuntimeError("Unexpected state in retry_with_backoff")
