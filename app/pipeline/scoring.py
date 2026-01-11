import math
from datetime import datetime
from typing import Any

import numpy as np

from app.config import AppConfig, get_config
from app.core.datetime_utils import get_cutoff, utc_now
from app.core.logging import get_logger
from app.ingest.normalizer import extract_canonical_identity
from app.metrics.engagement import get_item_engagement, get_snapshot_engagement
from app.models.content import ContentItem

logger = get_logger(__name__)


class HistoricalMetrics:
    """Stores historical engagement data for percentile calculations."""

    def __init__(self) -> None:
        self.distributions: dict[str, list[float]] = {}

    def add_distribution(self, source: str, values: list[float]) -> None:
        """Add engagement distribution for a source."""
        self.distributions[source] = sorted(values)

    def get_percentile(self, source: str, value: float) -> float:
        """Get percentile rank of value within source distribution."""
        dist = self.distributions.get(source, [])
        if not dist:
            return 50.0  # Default to median if no data

        # Binary search for position
        pos = np.searchsorted(dist, value)
        percentile = (pos / len(dist)) * 100
        return min(percentile, 100.0)


class ClusterScorer:
    """
    Scores clusters for ranking in the daily digest.

    Score formula:
    score = (
        0.30 * recency +
        0.20 * engagement_pctl +
        0.25 * velocity_pctl +
        0.25 * echo_scaled +
        practical_boost -
        already_seen_penalty
    )

    If viral: score *= viral_multiplier (default 1.35)
    """

    def __init__(
        self,
        config: AppConfig | None = None,
        historical: HistoricalMetrics | None = None,
        x_items: list[ContentItem] | None = None,
        yesterday_clusters: set[str] | None = None,
    ) -> None:
        """
        Initialize scorer.

        Args:
            config: App configuration
            historical: Historical metrics for percentile calculations
            x_items: X/Twitter items for echo detection
            yesterday_clusters: Set of canonical identities from yesterday
        """
        self.config = config or get_config()
        self.historical = historical or HistoricalMetrics()
        self.x_items = x_items or []
        self.yesterday_clusters = yesterday_clusters or set()

        # Pre-build echo index for O(1) lookup: identity -> set of authors
        self._echo_index = self._build_echo_index()

    def _build_echo_index(self) -> dict[str, set[str]]:
        """
        Pre-build index of canonical identity -> authors who mentioned it.

        This converts echo lookup from O(n*m) to O(1) per cluster.
        """
        cutoff = get_cutoff(hours=self.config.ranking.echo_window_hours)
        index: dict[str, set[str]] = {}

        for item in self.x_items:
            if item.published_at < cutoff:
                continue

            identity = extract_canonical_identity(item.url, item.text or "")
            if identity and item.author:
                index.setdefault(identity, set()).add(item.author)

        return index

    def compute_recency(self, published_at: datetime) -> float:
        """
        Compute recency score using exponential decay.

        recency = exp(-age_hours / half_life_hours)
        """
        age = utc_now() - published_at
        age_hours = age.total_seconds() / 3600
        half_life = self.config.ranking.half_life_hours
        return math.exp(-age_hours / half_life)

    def compute_velocity(self, item: ContentItem) -> float:
        """
        Compute velocity from metrics snapshots.

        velocity = (eng_now - eng_prev) / dt_hours
        """
        snapshots = item.metrics_snapshots
        if len(snapshots) < 2:
            return 0.0

        latest = snapshots[-1]
        prev = snapshots[-2]

        dt = (latest.captured_at - prev.captured_at).total_seconds() / 3600
        if dt == 0:
            return 0.0

        eng_now = get_snapshot_engagement(latest, item.source.value)
        eng_prev = get_snapshot_engagement(prev, item.source.value)

        return max(0, (eng_now - eng_prev) / dt)

    def compute_echo(self, canonical_identity: str) -> int:
        """
        Count distinct X accounts mentioning this cluster.

        Uses pre-built index for O(1) lookup instead of O(n*m) iteration.
        """
        return len(self._echo_index.get(canonical_identity, set()))

    def compute_practical_boost(self, items: list[ContentItem]) -> float:
        """Check for practical engineering keywords."""
        keywords = self.config.ranking.practical_boost_keywords

        for item in items:
            text = f"{item.title} {item.text or ''}".lower()
            if any(kw.lower() in text for kw in keywords):
                return self.config.ranking.practical_boost_value

        return 0.0

    def is_viral(
        self,
        engagement_pctl: float,
        velocity_pctl: float,
        echo: int,
    ) -> bool:
        """Check if cluster meets viral criteria."""
        viral_config = self.config.ranking.viral
        return bool(
            engagement_pctl >= viral_config["engagement_pctl"]
            or velocity_pctl >= viral_config["velocity_pctl"]
            or echo >= viral_config["echo_accounts"]
        )

    def score_cluster(
        self,
        canonical_identity: str,
        items: list[ContentItem],
    ) -> dict[str, Any]:
        """
        Score a cluster of items.

        Returns:
            Dict with score and component values
        """
        if not items:
            return {"score": 0.0}

        # Get best item for metrics
        best_item = max(items, key=lambda x: get_item_engagement(x))

        # Compute components
        recency = self.compute_recency(best_item.published_at)
        engagement = get_item_engagement(best_item)
        velocity = self.compute_velocity(best_item)

        # Get percentiles
        source = best_item.source.value
        engagement_pctl = self.historical.get_percentile(source, engagement)
        velocity_pctl = self.historical.get_percentile(source, velocity)

        # Echo and boosts
        echo = self.compute_echo(canonical_identity)
        echo_scaled = math.log1p(echo)
        practical_boost = self.compute_practical_boost(items)

        # Already seen penalty
        already_seen_penalty = (
            self.config.ranking.already_seen_penalty
            if canonical_identity in self.yesterday_clusters
            else 0.0
        )

        # Compute final score
        weights = self.config.ranking.weights
        score = (
            weights["recency"] * recency
            + weights["engagement"] * (engagement_pctl / 100)
            + weights["velocity"] * (velocity_pctl / 100)
            + weights["echo"] * echo_scaled
            + practical_boost
            - already_seen_penalty
        )

        # Viral boost
        is_viral = self.is_viral(engagement_pctl, velocity_pctl, echo)
        if is_viral:
            score *= self.config.ranking.viral.get("multiplier", 1.35)

        return {
            "score": score,
            "recency": recency,
            "engagement": engagement,
            "engagement_pctl": engagement_pctl,
            "velocity": velocity,
            "velocity_pctl": velocity_pctl,
            "echo": echo,
            "echo_scaled": echo_scaled,
            "practical_boost": practical_boost,
            "already_seen_penalty": already_seen_penalty,
            "is_viral": is_viral,
        }


def rank_clusters(
    clusters: dict[str, list[ContentItem]],
    scorer: ClusterScorer,
    top_n: int = 10,
) -> list[tuple[str, list[ContentItem], dict]]:
    """
    Rank clusters by score and return top N.

    Args:
        clusters: Dict mapping canonical identity to items
        scorer: ClusterScorer instance
        top_n: Number of top clusters to return

    Returns:
        List of (identity, items, score_info) tuples, sorted by score desc
    """
    scored = []

    for identity, items in clusters.items():
        score_info = scorer.score_cluster(identity, items)
        scored.append((identity, items, score_info))

    # Sort by score descending
    scored.sort(key=lambda x: x[2]["score"], reverse=True)

    logger.bind(total=len(scored), top_n=top_n).info("clusters_ranked")

    return scored[:top_n]
