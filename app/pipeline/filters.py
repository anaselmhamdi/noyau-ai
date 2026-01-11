from openai import AsyncOpenAI

from app.config import get_config
from app.core.logging import get_logger
from app.models.content import ContentItem

logger = get_logger(__name__)


def keyword_filter(text: str) -> bool:
    """
    Fast keyword check for political content.

    Returns True if text contains any politics keywords.
    """
    config = get_config()
    keywords = config.filters.politics_keywords
    text_lower = text.lower()

    return any(kw.lower() in text_lower for kw in keywords)


async def llm_politics_check(text: str, client: AsyncOpenAI) -> bool:
    """
    LLM context validation for edge cases.

    Returns True if content is actually political.
    """
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a content classifier. "
                        "Determine if the content is about politics, elections, "
                        "government policy, or political figures. "
                        "Respond ONLY with 'political' or 'not_political'. "
                        "Technical terms like 'leader election' in distributed systems "
                        "or 'election algorithm' are NOT political."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Classify this content:\n\n{text[:1000]}",
                },
            ],
            max_tokens=10,
            temperature=0,
        )

        result = (response.choices[0].message.content or "").strip().lower()
        # Check for exact "political" response, not "not_political"
        return result == "political"

    except Exception as e:
        logger.bind(error=str(e)).warning("llm_politics_check_error")
        # Default to not political if LLM fails
        return False


async def filter_political_items(
    items: list[ContentItem],
    client: AsyncOpenAI | None = None,
) -> list[ContentItem]:
    """
    Two-stage filter for political content.

    Stage 1: Fast keyword match
    Stage 2: LLM validation for keyword matches (to catch false positives)

    Args:
        items: List of content items to filter
        client: Optional OpenAI client for LLM validation

    Returns:
        Filtered list with political content removed
    """
    config = get_config()

    if not config.filters.exclude_politics:
        return items

    filtered = []

    for item in items:
        text = f"{item.title} {item.text or ''}"

        if not keyword_filter(text):
            # No keywords matched - keep item
            filtered.append(item)
        elif client:
            # Keywords matched - validate with LLM
            is_political = await llm_politics_check(text, client)
            if not is_political:
                filtered.append(item)
            else:
                logger.bind(url=item.url, title=item.title[:50]).debug("political_content_filtered")
        else:
            # No LLM available - use keyword match only
            logger.bind(url=item.url, title=item.title[:50]).debug(
                "political_content_filtered_keyword"
            )

    logger.bind(
        input_count=len(items),
        output_count=len(filtered),
        removed_count=len(items) - len(filtered),
    ).info("political_filter_applied")

    return filtered


async def filter_political_clusters(
    clusters: dict[str, list[ContentItem]],
    client: AsyncOpenAI | None = None,
) -> dict[str, list[ContentItem]]:
    """
    Filter political content from clusters.

    Args:
        clusters: Dict mapping canonical identity to items
        client: Optional OpenAI client for LLM validation

    Returns:
        Filtered clusters
    """
    config = get_config()

    if not config.filters.exclude_politics:
        return clusters

    filtered: dict[str, list[ContentItem]] = {}

    for identity, items in clusters.items():
        # Check if any item in cluster is political
        cluster_text = " ".join(f"{item.title} {item.text or ''}" for item in items)

        if not keyword_filter(cluster_text):
            filtered[identity] = items
        elif client:
            is_political = await llm_politics_check(cluster_text, client)
            if not is_political:
                filtered[identity] = items
            else:
                logger.bind(identity=identity[:50]).debug("political_cluster_filtered")
        else:
            logger.bind(identity=identity[:50]).debug("political_cluster_filtered_keyword")

    logger.bind(input_count=len(clusters), output_count=len(filtered)).info(
        "political_cluster_filter_applied"
    )

    return filtered
