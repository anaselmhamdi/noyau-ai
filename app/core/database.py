from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

settings = get_settings()


def _fix_neon_url(url: str) -> str:
    """Convert sslmode to ssl for asyncpg compatibility with Neon."""
    return url.replace("sslmode=", "ssl=")


engine = create_async_engine(
    _fix_neon_url(settings.database_url),
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
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
