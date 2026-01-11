from collections import defaultdict
from datetime import date

from app.core.logging import get_logger
from app.ingest.normalizer import extract_canonical_identity
from app.metrics.engagement import get_item_engagement
from app.models.content import ContentItem

logger = get_logger(__name__)


class ClusterBuilder:
    """
    Builds clusters of related content items using canonical identities.

    Clusters items by:
    1. GitHub repo (owner/repo)
    2. CVE ID
    3. Canonicalized URL
    """

    def __init__(self, items: list[ContentItem]) -> None:
        """
        Initialize cluster builder.

        Args:
            items: List of content items to cluster
        """
        self.items = items

    def build_clusters(self) -> dict[str, list[ContentItem]]:
        """
        Group items by canonical identity.

        Returns:
            Dict mapping canonical identity to list of items
        """
        clusters: dict[str, list[ContentItem]] = defaultdict(list)

        for item in self.items:
            identity = extract_canonical_identity(item.url, item.text or "")
            clusters[identity].append(item)

        logger.bind(item_count=len(self.items), cluster_count=len(clusters)).info("clusters_built")

        return dict(clusters)

    def get_top_items_per_cluster(
        self,
        clusters: dict[str, list[ContentItem]],
        max_items: int = 5,
    ) -> dict[str, list[ContentItem]]:
        """
        Get top N items per cluster by engagement.

        Args:
            clusters: Dict mapping identity to items
            max_items: Max items to keep per cluster

        Returns:
            Filtered clusters with top items
        """
        result = {}

        for identity, items in clusters.items():
            # Sort by latest metrics engagement (descending)
            sorted_items = sorted(
                items,
                key=lambda x: get_item_engagement(x),
                reverse=True,
            )
            result[identity] = sorted_items[:max_items]

        return result


def build_clusters_for_date(
    items: list[ContentItem],
    issue_date: date,
) -> dict[str, list[ContentItem]]:
    """
    Build and filter clusters for a specific date.

    Args:
        items: Content items from the time window
        issue_date: Date of the issue being built

    Returns:
        Dict mapping canonical identity to top items
    """
    builder = ClusterBuilder(items)
    clusters = builder.build_clusters()

    # Keep top 5 items per cluster for LLM context
    filtered = builder.get_top_items_per_cluster(clusters, max_items=5)

    logger.bind(date=str(issue_date), cluster_count=len(filtered)).info("clusters_filtered")

    return filtered
