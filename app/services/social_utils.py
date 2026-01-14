"""
Shared utilities for social media services.

Common functions used by tiktok_service.py and instagram_service.py.
"""

from datetime import date
from typing import Any


def build_social_caption(
    item: dict[str, Any],
    rank: int,
    *,
    include_date: bool = False,
    issue_date: date | None = None,
    hashtags: list[str] | None = None,
    max_length: int | None = None,
    cta: str = "More signal, less noise: noyau.news",
) -> str:
    """
    Build a social media caption from an issue item.

    Args:
        item: Issue item with headline, teaser, etc.
        rank: Story rank (1-10)
        include_date: Whether to include date in caption
        issue_date: Date of the issue (defaults to today if include_date=True)
        hashtags: List of hashtags to append (without # prefix)
        max_length: Maximum caption length (truncates with ... if exceeded)
        cta: Call-to-action text to append

    Returns:
        Formatted caption for social media
    """
    headline = item.get("headline", "")
    teaser = item.get("teaser", "")

    # Build base caption
    if include_date:
        if issue_date is None:
            issue_date = date.today()
        date_str = issue_date.strftime("%b %d, %Y")
        caption = f"{date_str} | {headline}\n\n{teaser}"
    else:
        caption = f"{headline}\n\n{teaser}"

    # Add hashtags if provided
    if hashtags:
        hashtag_str = " ".join(f"#{tag}" for tag in hashtags)
        caption = f"{caption}\n\n{hashtag_str}"

    # Add CTA
    if cta:
        caption = f"{caption}\n\n{cta}"

    # Apply length limit if specified
    if max_length and len(caption) > max_length:
        caption = caption[: max_length - 3] + "..."

    return caption
