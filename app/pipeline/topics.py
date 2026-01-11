"""Shared topic detection logic for clusters.

This module consolidates topic detection used across the pipeline
(issue building, distillation, and video generation).
"""

from app.models.cluster import DominantTopic

# Keywords for topic detection
SECURITY_KEYWORDS = frozenset({"security", "cve", "exploit", "vulnerability"})
AI_KEYWORDS = frozenset({"openai", "anthropic", "llm", "gpt", "claude"})


def detect_topic_from_identity(identity: str, is_viral: bool = False) -> str:
    """
    Detect topic category from canonical identity.

    Args:
        identity: Canonical identity of the cluster
        is_viral: Whether the cluster is marked as viral

    Returns:
        Topic string: "sauce", "security", "oss", "ai", or "dev"
    """
    if is_viral:
        return "sauce"

    identity_lower = identity.lower()

    # Check for security keywords or CVE pattern
    if any(kw in identity_lower for kw in SECURITY_KEYWORDS) or "cve:" in identity:
        return "security"

    # Check for GitHub/OSS indicator
    if "github:" in identity:
        return "oss"

    # Check for AI keywords
    if any(kw in identity_lower for kw in AI_KEYWORDS):
        return "ai"

    return "dev"


def topic_to_dominant_topic(topic_str: str) -> DominantTopic:
    """
    Convert topic string to DominantTopic enum.

    Args:
        topic_str: Topic string from detect_topic_from_identity()

    Returns:
        Corresponding DominantTopic enum value
    """
    topic_map = {
        "sauce": DominantTopic.SAUCE,
        "security": DominantTopic.SECURITY,
        "oss": DominantTopic.OSS,
        "ai": DominantTopic.DEV,  # AI maps to dev for now
        "dev": DominantTopic.DEV,
        "general": DominantTopic.DEV,  # Video module uses "general"
    }
    return topic_map.get(topic_str, DominantTopic.DEV)
