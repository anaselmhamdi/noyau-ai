from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime

from pydantic import BaseModel


class RawContent(BaseModel):
    """Normalized content item from any source."""

    source: str  # x, reddit, github, youtube, devto, rss
    source_id: str | None = None
    url: str
    title: str
    author: str | None = None
    published_at: datetime
    text: str | None = None
    metrics: dict  # Source-specific metrics (likes, upvotes, stars, etc.)


class BaseFetcher(ABC):
    """Abstract base class for content fetchers."""

    source_name: str = "unknown"

    @abstractmethod
    async def fetch(self) -> AsyncIterator[RawContent]:
        """
        Fetch and yield normalized content items from this source.

        Yields:
            RawContent items with normalized fields
        """
        yield  # type: ignore
