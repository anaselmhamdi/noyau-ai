"""Shared engagement calculation utilities.

This module provides a single source of truth for calculating engagement
scores from metrics across different content sources.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.content import ContentItem, MetricsSnapshot


def calculate_engagement(metrics: dict[str, Any], source: str) -> float:
    """
    Calculate weighted engagement score from metrics.

    Formulas by source:
    - X: likes + 2*retweets + replies
    - Reddit: upvotes + 2*comments
    - YouTube: views/1000 + 2*comments
    - GitHub: stars + forks
    - dev.to: reactions + 2*comments
    - RSS/other: 0.0

    Args:
        metrics: Dict of source-specific metrics (likes, upvotes, etc.)
        source: Content source identifier (x, reddit, youtube, etc.)

    Returns:
        Weighted engagement score as float
    """
    if source == "x":
        return float(
            metrics.get("likes", 0) + 2 * metrics.get("retweets", 0) + metrics.get("replies", 0)
        )
    elif source == "reddit":
        return float(metrics.get("upvotes", 0) + 2 * metrics.get("comments", 0))
    elif source == "youtube":
        return float(metrics.get("views", 0)) / 1000 + 2 * float(metrics.get("comments", 0))
    elif source == "github":
        return float(metrics.get("stars", 0) + metrics.get("forks", 0))
    elif source == "devto":
        return float(metrics.get("reactions", 0) + 2 * metrics.get("comments", 0))
    elif source == "bluesky":
        return float(
            metrics.get("likes", 0) + 2 * metrics.get("reposts", 0) + metrics.get("replies", 0)
        )
    return 0.0


def get_item_engagement(item: "ContentItem") -> float:
    """
    Get engagement score from a content item's latest snapshot.

    Args:
        item: ContentItem with metrics_snapshots relationship loaded

    Returns:
        Engagement score from latest snapshot, or 0.0 if no snapshots
    """
    if not item.metrics_snapshots:
        return 0.0
    latest = item.metrics_snapshots[-1]
    return calculate_engagement(latest.metrics_json, item.source.value)


def get_snapshot_engagement(snapshot: "MetricsSnapshot", source: str) -> float:
    """
    Get engagement score from a specific metrics snapshot.

    Args:
        snapshot: MetricsSnapshot with metrics_json
        source: Content source identifier

    Returns:
        Engagement score for the snapshot
    """
    return calculate_engagement(snapshot.metrics_json, source)
