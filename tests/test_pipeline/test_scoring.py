"""Tests for cluster scoring."""

from datetime import timedelta

import pytest

from app.core.datetime_utils import utc_now
from app.metrics.engagement import get_item_engagement
from app.models.content import ContentSource
from app.pipeline.scoring import ClusterScorer, HistoricalMetrics, rank_clusters


class TestHistoricalMetrics:
    """Tests for historical metrics percentile calculations."""

    def test_get_percentile_empty_distribution(self):
        """Should return 50 for empty distribution."""
        historical = HistoricalMetrics()
        assert historical.get_percentile("unknown", 100) == 50.0

    def test_get_percentile_calculates_correctly(self):
        """Should calculate percentile correctly."""
        historical = HistoricalMetrics()
        historical.add_distribution("reddit", [10, 20, 30, 40, 50, 60, 70, 80, 90, 100])

        # Value 50 is at index 4 out of 10, so 40th percentile
        assert historical.get_percentile("reddit", 50) == 40.0

        # Value 90 is at index 8 out of 10, so 80th percentile
        assert historical.get_percentile("reddit", 90) == 80.0

        # Value below minimum
        assert historical.get_percentile("reddit", 5) == 0.0

        # Value above maximum
        assert historical.get_percentile("reddit", 150) == 100.0


class TestClusterScorer:
    """Tests for cluster scoring logic."""

    @pytest.fixture
    def scorer(self):
        """Create scorer with default config."""
        return ClusterScorer()

    def test_compute_recency_recent_item(self, scorer):
        """Should give high recency score for recent items."""
        published = utc_now() - timedelta(hours=1)
        recency = scorer.compute_recency(published)

        # Should be close to 1 for very recent
        assert recency > 0.9

    def test_compute_recency_old_item(self, scorer):
        """Should give low recency score for old items."""
        published = utc_now() - timedelta(hours=72)
        recency = scorer.compute_recency(published)

        # Should be low for old items
        assert recency < 0.1

    def test_compute_engagement_x(self, make_content_item):
        """Should compute X engagement correctly."""
        item = make_content_item(
            source=ContentSource.X,
            metrics={"likes": 100, "retweets": 50, "replies": 25},
        )

        engagement = get_item_engagement(item)

        # likes + 2*retweets + replies = 100 + 100 + 25 = 225
        assert engagement == 225

    def test_compute_engagement_reddit(self, make_content_item):
        """Should compute Reddit engagement correctly."""
        item = make_content_item(
            source=ContentSource.REDDIT,
            metrics={"upvotes": 500, "comments": 100},
        )

        engagement = get_item_engagement(item)

        # upvotes + 2*comments = 500 + 200 = 700
        assert engagement == 700

    def test_compute_velocity_single_snapshot(self, make_content_item):
        """Should return 0 velocity for single snapshot."""
        scorer = ClusterScorer()
        item = make_content_item(source=ContentSource.REDDIT, metrics={"upvotes": 100})

        velocity = scorer.compute_velocity(item)
        assert velocity == 0.0

    def test_compute_velocity_increasing_engagement(self, make_content_item_with_snapshots):
        """Should compute positive velocity for increasing engagement."""
        scorer = ClusterScorer()
        item = make_content_item_with_snapshots(
            source=ContentSource.REDDIT,
            snapshots_data=[
                {"upvotes": 100, "comments": 10},  # t-2h
                {"upvotes": 200, "comments": 20},  # t-1h
            ],
        )

        velocity = scorer.compute_velocity(item)
        assert velocity > 0

    def test_compute_practical_boost_with_keywords(self, make_content_item):
        """Should apply boost for practical keywords."""
        scorer = ClusterScorer()
        items = [
            make_content_item(source=ContentSource.RSS, title="New release v2.0 available"),
        ]

        boost = scorer.compute_practical_boost(items)
        assert boost > 0

    def test_compute_practical_boost_without_keywords(self, make_content_item):
        """Should not apply boost without practical keywords."""
        scorer = ClusterScorer()
        items = [
            make_content_item(source=ContentSource.RSS, title="Opinion piece on tech"),
        ]

        boost = scorer.compute_practical_boost(items)
        assert boost == 0.0

    def test_is_viral_high_engagement(self):
        """Should detect viral by engagement percentile."""
        scorer = ClusterScorer()
        assert scorer.is_viral(95, 50, 0) is True

    def test_is_viral_high_velocity(self):
        """Should detect viral by velocity percentile."""
        scorer = ClusterScorer()
        assert scorer.is_viral(50, 95, 0) is True

    def test_is_viral_high_echo(self):
        """Should detect viral by echo count."""
        scorer = ClusterScorer()
        assert scorer.is_viral(50, 50, 5) is True

    def test_is_viral_none(self):
        """Should not detect viral for normal metrics."""
        scorer = ClusterScorer()
        assert scorer.is_viral(50, 50, 1) is False

    def test_score_cluster_applies_viral_boost(self, make_content_item):
        """Should apply 1.35x boost for viral clusters."""
        historical = HistoricalMetrics()
        historical.add_distribution("reddit", list(range(100)))

        scorer = ClusterScorer(historical=historical)

        # Create high-engagement item
        items = [
            make_content_item(
                source=ContentSource.REDDIT,
                metrics={"upvotes": 1000, "comments": 500},
            ),
        ]

        score_info = scorer.score_cluster("test-identity", items)

        # Should be marked as viral
        assert score_info["is_viral"] is True


class TestRankClusters:
    """Tests for cluster ranking."""

    def test_rank_clusters_returns_top_n(self, make_content_item):
        """Should return only top N clusters."""
        scorer = ClusterScorer()

        clusters = {f"identity-{i}": [make_content_item()] for i in range(20)}

        ranked = rank_clusters(clusters, scorer, top_n=10)

        assert len(ranked) == 10

    def test_rank_clusters_sorted_by_score(self, make_content_item):
        """Should sort clusters by score descending."""
        scorer = ClusterScorer()

        clusters = {
            "low": [make_content_item(published_hours_ago=48)],
            "high": [make_content_item(published_hours_ago=1)],
        }

        ranked = rank_clusters(clusters, scorer, top_n=10)

        # High recency should be first
        assert ranked[0][0] == "high"
