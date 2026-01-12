"""Tests for timezone-aware digest dispatch service."""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from app.models.digest_delivery import DigestDelivery
from app.services.digest_dispatch import (
    get_users_ready_for_delivery,
    record_delivery,
    send_digest_immediately,
)

pytestmark = pytest.mark.asyncio


class TestGetUsersReadyForDelivery:
    """Tests for get_users_ready_for_delivery."""

    async def test_returns_users_in_delivery_window(self, db_session, user_factory):
        """Should return users whose delivery window is active."""
        # Create user in delivery window
        user = await user_factory(
            timezone="America/New_York",
            delivery_time="08:00",
        )
        user.is_subscribed = True
        await db_session.flush()

        with (
            patch("app.services.digest_dispatch.is_in_delivery_window", return_value=True),
            patch("app.services.digest_dispatch.has_delivery_window_passed", return_value=False),
        ):
            ready = await get_users_ready_for_delivery(db_session, date.today())

        assert len(ready) == 1
        assert ready[0].id == user.id

    async def test_excludes_unsubscribed_users(self, db_session, user_factory):
        """Should not return unsubscribed users."""
        user = await user_factory()
        user.is_subscribed = False
        await db_session.flush()

        with (
            patch("app.services.digest_dispatch.is_in_delivery_window", return_value=True),
            patch("app.services.digest_dispatch.has_delivery_window_passed", return_value=False),
        ):
            ready = await get_users_ready_for_delivery(db_session, date.today())

        assert len(ready) == 0

    async def test_excludes_already_delivered_users(self, db_session, user_factory):
        """Should not return users who already received today's digest."""
        user = await user_factory()
        user.is_subscribed = True
        await db_session.flush()

        # Record delivery
        from app.core.datetime_utils import utc_now

        delivery = DigestDelivery(
            user_id=user.id,
            issue_date=date.today(),
            delivered_at=utc_now(),
        )
        db_session.add(delivery)
        await db_session.flush()

        with (
            patch("app.services.digest_dispatch.is_in_delivery_window", return_value=True),
            patch("app.services.digest_dispatch.has_delivery_window_passed", return_value=False),
        ):
            ready = await get_users_ready_for_delivery(db_session, date.today())

        assert len(ready) == 0

    async def test_includes_users_with_passed_window_catchup(self, db_session, user_factory):
        """Should include users whose window passed (catch-up logic)."""
        user = await user_factory()
        user.is_subscribed = True
        await db_session.flush()

        # Window passed but not in window
        with (
            patch("app.services.digest_dispatch.is_in_delivery_window", return_value=False),
            patch("app.services.digest_dispatch.has_delivery_window_passed", return_value=True),
        ):
            ready = await get_users_ready_for_delivery(db_session, date.today())

        assert len(ready) == 1


class TestRecordDelivery:
    """Tests for record_delivery."""

    async def test_creates_delivery_record(self, db_session, user_factory):
        """Should create a DigestDelivery record."""
        user = await user_factory()
        issue_date = date.today()

        delivery = await record_delivery(db_session, user, issue_date)

        assert delivery.user_id == user.id
        assert delivery.issue_date == issue_date
        assert delivery.delivered_at is not None


class TestSendDigestImmediately:
    """Tests for send_digest_immediately (catch-up on signup)."""

    async def test_skips_if_already_delivered(self, db_session, user_factory):
        """Should return False if digest already delivered today."""
        user = await user_factory()

        # Record delivery
        from app.core.datetime_utils import utc_now

        delivery = DigestDelivery(
            user_id=user.id,
            issue_date=date.today(),
            delivered_at=utc_now(),
        )
        db_session.add(delivery)
        await db_session.flush()

        result = await send_digest_immediately(db_session, user, date.today())

        assert result is False

    async def test_returns_false_if_no_issue(self, db_session, user_factory):
        """Should return False if no issue exists for the date."""
        user = await user_factory()

        with patch(
            "app.services.digest_dispatch.get_issue_items_for_date",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await send_digest_immediately(db_session, user, date.today())

        assert result is False

    async def test_sends_and_records_delivery(self, db_session, user_factory):
        """Should send email and record delivery."""
        user = await user_factory()
        user.is_subscribed = True
        await db_session.flush()

        mock_items = [{"headline": "Test", "teaser": "Test teaser", "bullets": [], "citations": []}]

        with (
            patch(
                "app.services.digest_dispatch.get_issue_items_for_date",
                new_callable=AsyncMock,
                return_value=mock_items,
            ),
            patch(
                "app.services.digest_dispatch.get_missed_from_yesterday",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "app.services.digest_dispatch.send_daily_digest",
                new_callable=AsyncMock,
            ) as mock_send,
        ):
            result = await send_digest_immediately(db_session, user, date.today())

        assert result is True
        mock_send.assert_called_once()
