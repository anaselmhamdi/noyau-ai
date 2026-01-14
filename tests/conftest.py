"""
Pytest configuration and fixtures for NoyauAI tests.

Provides:
- Async test database with SQLite
- Test client for API testing
- Factory fixtures for creating test data
"""

import asyncio
import uuid
from collections.abc import AsyncGenerator
from datetime import date, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import StaticPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings, get_settings
from app.core.database import get_db
from app.core.datetime_utils import utc_now
from app.core.security import generate_ref_code, generate_token, hash_token
from app.main import app
from app.models import Base
from app.models.cluster import Cluster, ClusterItem, ClusterSummary, ConfidenceLevel, DominantTopic
from app.models.content import ContentItem, ContentSource, MetricsSnapshot
from app.models.issue import Issue
from app.models.user import MagicLink, Session, User

# Test database URL (in-memory SQLite)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


# Override settings for testing
class TestSettings(Settings):
    database_url: str = TEST_DATABASE_URL
    debug: bool = True
    openai_api_key: str = "test-key"
    resend_api_key: str = "test-key"
    secret_key: str = "test-secret-key"
    base_url: str = "http://localhost:8000"
    # Email validation disabled in tests (uses NullValidator)
    verifalia_username: str = ""
    verifalia_password: str = ""


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_engine():
    """Create async test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create async database session for tests."""
    session_factory = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create async test client with database override."""
    from app.core.rate_limit import limiter

    async def override_get_db():
        yield db_session

    def override_get_settings():
        return TestSettings()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = override_get_settings

    # Reset rate limiter storage before each test
    limiter.reset()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ============================================================================
# Factory Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def user_factory(db_session: AsyncSession):
    """Factory for creating test users."""

    async def _create_user(
        email: str = None,
        timezone: str = "Europe/Paris",
        delivery_time: str = "08:00",
    ) -> User:
        if email is None:
            email = f"test-{uuid.uuid4().hex[:8]}@example.com"

        user = User(
            email=email,
            timezone=timezone,
            delivery_time_local=delivery_time,
            ref_code=generate_ref_code(),
        )
        db_session.add(user)
        await db_session.flush()
        return user

    return _create_user


@pytest_asyncio.fixture
async def session_factory(db_session: AsyncSession, user_factory):
    """Factory for creating test sessions."""

    async def _create_session(user: User = None) -> Session:
        if user is None:
            user = await user_factory()

        session = Session(
            user_id=user.id,
            expires_at=utc_now() + timedelta(days=30),
        )
        db_session.add(session)
        await db_session.flush()
        return session

    return _create_session


@pytest_asyncio.fixture
async def magic_link_factory(db_session: AsyncSession):
    """Factory for creating test magic links."""

    async def _create_magic_link(
        email: str = "test@example.com",
        redirect_path: str = "/",
        expired: bool = False,
        used: bool = False,
    ) -> tuple[MagicLink, str]:
        token = generate_token()
        token_hash = hash_token(token)

        expires_at = utc_now() + timedelta(minutes=-15 if expired else 15)
        used_at = utc_now() if used else None

        magic_link = MagicLink(
            token_hash=token_hash,
            email=email,
            redirect_path=redirect_path,
            expires_at=expires_at,
            used_at=used_at,
        )
        db_session.add(magic_link)
        await db_session.flush()
        return magic_link, token

    return _create_magic_link


@pytest_asyncio.fixture
async def content_item_factory(db_session: AsyncSession):
    """Factory for creating test content items."""

    async def _create_content_item(
        source: ContentSource = ContentSource.RSS,
        url: str = None,
        title: str = "Test Article",
        author: str = "Test Author",
        text: str = "Test content text",
        published_at: datetime = None,
        metrics: dict = None,
    ) -> ContentItem:
        if url is None:
            url = f"https://example.com/article-{uuid.uuid4().hex[:8]}"
        if published_at is None:
            published_at = utc_now() - timedelta(hours=2)

        item = ContentItem(
            source=source,
            source_id=uuid.uuid4().hex,
            url=url,
            title=title,
            author=author,
            published_at=published_at,
            text=text,
        )
        db_session.add(item)
        await db_session.flush()

        # Add metrics snapshot if provided
        if metrics:
            snapshot = MetricsSnapshot(
                item_id=item.id,
                metrics_json=metrics,
            )
            db_session.add(snapshot)
            await db_session.flush()

        return item

    return _create_content_item


@pytest_asyncio.fixture
async def cluster_factory(db_session: AsyncSession, content_item_factory):
    """Factory for creating test clusters with summaries."""

    async def _create_cluster(
        issue_date: date = None,
        identity: str = None,
        score: float = 1.0,
        items: list[ContentItem] = None,
        with_summary: bool = True,
    ) -> Cluster:
        if issue_date is None:
            issue_date = date.today()
        if identity is None:
            identity = f"https://example.com/{uuid.uuid4().hex[:8]}"

        cluster = Cluster(
            issue_date=issue_date,
            canonical_identity=identity,
            dominant_topic=DominantTopic.DEV,
            cluster_score=score,
        )
        db_session.add(cluster)
        await db_session.flush()

        # Add items
        if items is None:
            items = [await content_item_factory()]

        for rank, item in enumerate(items):
            cluster_item = ClusterItem(
                cluster_id=cluster.id,
                item_id=item.id,
                rank_in_cluster=rank,
            )
            db_session.add(cluster_item)

        # Add summary
        if with_summary:
            summary = ClusterSummary(
                cluster_id=cluster.id,
                headline="Test Headline",
                teaser="Test teaser for the cluster.",
                takeaway="Key takeaway for engineers.",
                why_care="Why this matters to you.",
                bullets_json=["First bullet point", "Second bullet point"],
                citations_json=[{"url": "https://example.com", "label": "Source"}],
                confidence=ConfidenceLevel.HIGH,
            )
            db_session.add(summary)

        await db_session.flush()
        return cluster

    return _create_cluster


@pytest_asyncio.fixture
async def issue_factory(db_session: AsyncSession, cluster_factory):
    """Factory for creating test issues with clusters."""

    async def _create_issue(
        issue_date: date = None,
        num_clusters: int = 10,
    ) -> Issue:
        if issue_date is None:
            issue_date = date.today()

        issue = Issue(
            issue_date=issue_date,
            public_url=f"https://noyau.news/daily/{issue_date}",
        )
        db_session.add(issue)
        await db_session.flush()

        # Create clusters
        for i in range(num_clusters):
            await cluster_factory(
                issue_date=issue_date,
                score=10.0 - i,  # Descending scores
            )

        return issue

    return _create_issue


# ============================================================================
# Mock Fixtures
# ============================================================================


@pytest.fixture
def mock_openai_response():
    """Mock response for OpenAI structured output."""
    return {
        "headline": "Major Release: Python 3.13 Now Available",
        "teaser": "Python 3.13 brings significant performance improvements.",
        "takeaway": "Upgrade to benefit from 10-20% faster execution.",
        "why_care": "Directly impacts your CI/CD pipeline speed.",
        "bullets": [
            "New JIT compiler improves numeric workloads",
            "Better error messages for debugging",
        ],
        "citations": [
            {"url": "https://python.org/downloads", "label": "Python Downloads"},
        ],
        "confidence": "high",
    }


@pytest.fixture
def sample_rss_feed():
    """Sample RSS feed content for testing."""
    return """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
        <channel>
            <title>Test Feed</title>
            <link>https://example.com</link>
            <item>
                <title>Test Article</title>
                <link>https://example.com/article-1</link>
                <description>Test description</description>
                <pubDate>Mon, 10 Jan 2026 10:00:00 GMT</pubDate>
            </item>
        </channel>
    </rss>
    """


@pytest.fixture
def mock_email_validator():
    """Factory for creating mock email validators."""
    from unittest.mock import AsyncMock

    from app.services.email_validation import ValidationResult, ValidationStatus

    def _create_mock(
        status: ValidationStatus = ValidationStatus.VALID,
        is_deliverable: bool = True,
        is_disposable: bool = False,
        is_role_based: bool = False,
        reason: str | None = None,
    ) -> AsyncMock:
        mock = AsyncMock()
        mock.provider_name = "mock"

        mock.validate.return_value = ValidationResult(
            email="test@example.com",
            status=status,
            provider="mock",
            is_deliverable=is_deliverable,
            is_disposable=is_disposable,
            is_role_based=is_role_based,
            reason=reason,
        )

        mock.validate_batch.return_value = [mock.validate.return_value]

        # Default should_allow based on status
        mock.should_allow.return_value = status != ValidationStatus.INVALID

        return mock

    return _create_mock


# ============================================================================
# In-Memory Test Helpers (no DB)
# ============================================================================


@pytest.fixture
def make_content_item():
    """
    Factory for creating in-memory ContentItem objects (no DB).

    Use this fixture for unit tests that need ContentItem instances
    without database persistence.
    """

    def _make(
        source: ContentSource = ContentSource.RSS,
        url: str = "https://example.com/test",
        title: str = "Test",
        text: str = "",
        published_at: datetime = None,
        metrics: dict = None,
        published_hours_ago: int = None,
    ) -> ContentItem:
        if published_hours_ago is not None:
            published = utc_now() - timedelta(hours=published_hours_ago)
        elif published_at is not None:
            published = published_at
        else:
            published = utc_now() - timedelta(hours=2)

        item = ContentItem(
            source=source,
            url=url,
            title=title,
            text=text,
            published_at=published,
        )
        item.metrics_snapshots = []

        if metrics:
            snapshot = MetricsSnapshot(
                item_id=item.id,
                captured_at=utc_now(),
                metrics_json=metrics,
            )
            item.metrics_snapshots.append(snapshot)

        return item

    return _make


@pytest.fixture
def make_content_item_with_snapshots():
    """
    Factory for creating in-memory ContentItem with multiple metric snapshots.

    Use for testing velocity calculations and time-series metrics.
    """

    def _make(
        source: ContentSource,
        snapshots_data: list[dict],
        url: str = "https://example.com/test",
        title: str = "Test",
        published_hours_ago: int = 4,
    ) -> ContentItem:
        item = ContentItem(
            source=source,
            url=url,
            title=title,
            published_at=utc_now() - timedelta(hours=published_hours_ago),
        )
        item.metrics_snapshots = []

        for i, metrics in enumerate(snapshots_data):
            snapshot = MetricsSnapshot(
                item_id=item.id,
                captured_at=utc_now() - timedelta(hours=len(snapshots_data) - i),
                metrics_json=metrics,
            )
            item.metrics_snapshots.append(snapshot)

        return item

    return _make


@pytest.fixture
def mock_aiohttp_session():
    """
    Factory for creating mock aiohttp ClientSession objects.

    Simplifies HTTP mocking for ingest tests.
    """
    from unittest.mock import AsyncMock, MagicMock

    def _create_mock(
        response_text: str = "",
        response_json: dict = None,
        status: int = 200,
        raise_error: Exception = None,
    ) -> MagicMock:
        mock_session = MagicMock()
        mock_response = AsyncMock()
        mock_response.status = status
        mock_response.text = AsyncMock(return_value=response_text)

        if response_json is not None:
            mock_response.json = AsyncMock(return_value=response_json)

        if raise_error:
            mock_cm = MagicMock()
            mock_cm.__aenter__ = AsyncMock(side_effect=raise_error)
            mock_cm.__aexit__ = AsyncMock(return_value=None)
        else:
            mock_cm = MagicMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
            mock_cm.__aexit__ = AsyncMock(return_value=None)

        mock_session.get = MagicMock(return_value=mock_cm)
        mock_session.post = MagicMock(return_value=mock_cm)

        return mock_session

    return _create_mock
