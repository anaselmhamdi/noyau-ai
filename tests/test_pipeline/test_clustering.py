"""Tests for content clustering."""

from datetime import date

from app.pipeline.clustering import ClusterBuilder, build_clusters_for_date


class TestClusterBuilder:
    """Tests for cluster building."""

    def test_groups_by_canonical_identity(self, make_content_item):
        """Should group items with same canonical identity."""
        items = [
            make_content_item(url="https://example.com/article"),
            make_content_item(url="https://example.com/article?utm_source=test"),
            make_content_item(url="https://other.com/different"),
        ]

        builder = ClusterBuilder(items)
        clusters = builder.build_clusters()

        # First two URLs should canonicalize to same identity
        assert len(clusters) == 2

    def test_groups_github_urls_by_repo(self, make_content_item):
        """Should group GitHub URLs by repo."""
        items = [
            make_content_item(url="https://github.com/owner/repo/releases/tag/v1.0"),
            make_content_item(url="https://github.com/owner/repo/issues/123"),
            make_content_item(url="https://github.com/other/project"),
        ]

        builder = ClusterBuilder(items)
        clusters = builder.build_clusters()

        # First two should be grouped as github:owner/repo
        assert "github:owner/repo" in clusters
        assert len(clusters["github:owner/repo"]) == 2

    def test_groups_by_cve(self, make_content_item):
        """Should group items mentioning same CVE."""
        items = [
            make_content_item(
                url="https://blog1.com/security",
                text="Fix for CVE-2024-1234",
            ),
            make_content_item(
                url="https://blog2.com/update",
                text="CVE-2024-1234 patched",
            ),
        ]

        builder = ClusterBuilder(items)
        clusters = builder.build_clusters()

        assert "cve:CVE-2024-1234" in clusters
        assert len(clusters["cve:CVE-2024-1234"]) == 2

    def test_get_top_items_sorts_by_engagement(self, make_content_item):
        """Should return top items sorted by engagement."""
        items = [
            make_content_item(url="https://example.com/a", metrics={"likes": 10}),
            make_content_item(url="https://example.com/b", metrics={"likes": 100}),
            make_content_item(url="https://example.com/c", metrics={"likes": 50}),
        ]

        builder = ClusterBuilder(items)
        clusters = builder.build_clusters()
        top_clusters = builder.get_top_items_per_cluster(clusters, max_items=2)

        # Should only keep top 2 by engagement
        for identity, cluster_items in top_clusters.items():
            assert len(cluster_items) <= 2


class TestBuildClustersForDate:
    """Tests for date-based cluster building."""

    def test_filters_to_max_items(self, make_content_item):
        """Should limit items per cluster."""
        items = [make_content_item(url=f"https://example.com/article?id={i}") for i in range(20)]

        clusters = build_clusters_for_date(items, date.today())

        for identity, cluster_items in clusters.items():
            assert len(cluster_items) <= 5  # Default max_items
