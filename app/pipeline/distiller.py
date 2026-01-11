import backoff
from httpx import HTTPStatusError
from openai import AsyncOpenAI, RateLimitError

from app.config import get_settings
from app.core.logging import get_logger
from app.models.content import ContentItem
from app.pipeline.topics import detect_topic_from_identity
from app.schemas.llm import (
    ClusterDistillInput,
    ClusterDistillOutput,
    ClusterItemInput,
    DistillResult,
)

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are a technical editor for a daily engineering digest called "Noyau".
Your job is to distill clusters of related content into concise, actionable summaries.

Rules:
- Bias toward practical engineering: releases, postmortems, CVEs, benchmarks, migrations
- No politics whatsoever - if you detect political content, output minimal summary with low confidence
- No factual claims without citations from the provided sources
- If uncertain about accuracy, state uncertainty and set confidence to "low"
- Headlines should be concise and attention-grabbing (max 90 characters)
- Teasers should be single sentences that hook the reader
- Takeaways should explain WHY this matters to engineers
- Bullets should be actionable implications, not just facts
- Only cite URLs from the provided sources

Output format is strictly JSON matching the schema provided."""


def format_cluster_input(
    identity: str,
    items: list[ContentItem],
    dominant_topic: str = "dev",
) -> ClusterDistillInput:
    """Format cluster data for LLM input."""
    item_inputs = []

    for item in items[:5]:  # Limit to 5 items for context
        # Get metrics summary
        metrics_str = "no metrics"
        if item.metrics_snapshots:
            latest = item.metrics_snapshots[-1].metrics_json
            metrics_str = ", ".join(
                f"{k}: {v}" for k, v in latest.items() if isinstance(v, int | float)
            )

        item_inputs.append(
            ClusterItemInput(
                title=item.title,
                url=item.url,
                text_excerpt=(item.text or "")[:500],
                published_at=item.published_at.isoformat(),
                metrics_summary=metrics_str,
            )
        )

    return ClusterDistillInput(
        dominant_topic=dominant_topic,
        canonical_identity=identity,
        items=item_inputs,
    )


@backoff.on_exception(
    backoff.expo,
    (RateLimitError, HTTPStatusError),
    max_tries=5,
    max_time=120,
)
async def distill_cluster(
    identity: str,
    items: list[ContentItem],
    client: AsyncOpenAI,
    dominant_topic: str = "dev",
) -> DistillResult | None:
    """
    Use LLM to distill a cluster into a structured summary.

    Args:
        identity: Canonical identity of the cluster
        items: Content items in the cluster
        client: OpenAI async client
        dominant_topic: Topic category for the cluster

    Returns:
        DistillResult with output and token usage, or None if distillation fails
    """
    input_data = format_cluster_input(identity, items, dominant_topic)

    user_prompt = f"""Distill this cluster of related content into a structured summary.

Cluster topic: {input_data.dominant_topic}
Canonical identity: {input_data.canonical_identity}

Items ({len(input_data.items)}):
"""

    for i, item in enumerate(input_data.items, 1):
        user_prompt += f"""
{i}. {item.title}
   URL: {item.url}
   Published: {item.published_at}
   Excerpt: {item.text_excerpt}
   Metrics: {item.metrics_summary}
"""

    user_prompt += "\nProduce a JSON summary following the schema."

    settings = get_settings()

    try:
        response = await client.beta.chat.completions.parse(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format=ClusterDistillOutput,
            temperature=0.3,
        )

        result = response.choices[0].message.parsed
        usage = response.usage

        if result and usage:
            logger.info(
                f"cluster_distilled: {identity[:50]} | {result.headline[:50]} | "
                f"tokens={usage.total_tokens} (prompt={usage.prompt_tokens}, completion={usage.completion_tokens})"
            )
            return DistillResult(
                output=result,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
            )

        logger.bind(identity=identity[:50]).warning("cluster_distill_no_result")
        return None

    except Exception as e:
        logger.bind(identity=identity[:50], error=str(e)).error("cluster_distill_error")
        return None


async def distill_top_clusters(
    ranked_clusters: list[tuple[str, list[ContentItem], dict]],
    client: AsyncOpenAI | None = None,
) -> list[tuple[str, list[ContentItem], dict, DistillResult | None]]:
    """
    Distill all top-ranked clusters.

    Args:
        ranked_clusters: List of (identity, items, score_info) tuples
        client: Optional OpenAI client

    Returns:
        List of (identity, items, score_info, distill_result) tuples
    """
    if not client:
        settings = get_settings()
        if not settings.openai_api_key:
            logger.warning("openai_api_key_not_set")
            return [(i, it, s, None) for i, it, s in ranked_clusters]
        client = AsyncOpenAI(api_key=settings.openai_api_key)

    results = []
    total_tokens = 0

    for identity, items, score_info in ranked_clusters:
        # Determine dominant topic from score info
        dominant_topic = detect_topic_from_identity(identity, score_info.get("is_viral", False))

        distill_result = await distill_cluster(
            identity=identity,
            items=items,
            client=client,
            dominant_topic=dominant_topic,
        )

        if distill_result:
            total_tokens += distill_result.total_tokens

        results.append((identity, items, score_info, distill_result))

    logger.info(
        f"distillation_complete: {len(results)} clusters | "
        f"{sum(1 for _, _, _, r in results if r)} successful | "
        f"total_tokens={total_tokens}"
    )

    return results
