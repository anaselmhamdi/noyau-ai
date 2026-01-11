import ssl
from collections.abc import AsyncGenerator
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

settings = get_settings()


def _fix_neon_url(url: str) -> tuple[str, dict]:
    """
    Fix Neon connection URL for asyncpg compatibility.

    Neon includes params like sslmode, channel_binding that asyncpg
    doesn't accept. We strip them and handle SSL via connect_args.
    """
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    # Remove unsupported asyncpg params
    unsupported = ["sslmode", "channel_binding", "options"]
    for param in unsupported:
        params.pop(param, None)

    # Rebuild URL without unsupported params
    new_query = urlencode(params, doseq=True)
    clean_url = urlunparse(parsed._replace(query=new_query))

    # SSL context for Neon
    ssl_context = ssl.create_default_context()
    connect_args = {"ssl": ssl_context}

    return clean_url, connect_args


clean_url, connect_args = _fix_neon_url(settings.database_url)


engine = create_async_engine(
    clean_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    connect_args=connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that provides a database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            logger.bind(error=str(e)).error("database_transaction_rollback")
            await session.rollback()
            raise
