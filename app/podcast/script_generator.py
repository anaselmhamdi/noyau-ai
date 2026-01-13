"""LLM-based podcast script generation from cluster summaries."""

from datetime import date

import backoff
from httpx import HTTPStatusError
from openai import AsyncOpenAI, RateLimitError

from app.config import get_settings
from app.core.logging import get_logger
from app.schemas.llm import ClusterDistillOutput
from app.schemas.podcast import PodcastScript, PodcastScriptResult

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are a podcast host for "Noyau Daily", a tech news podcast.
Your audience is experienced software engineers who want a quick daily briefing on what matters in tech.

Your voice is:
- Conversational but knowledgeable (like chatting with a senior engineer colleague)
- Opinionated when appropriate (share practical takes on the news)
- Efficient - no filler words, get to the point
- Occasionally witty, never corny

Script structure:
- INTRO (30-45 seconds): Start with today's date and a punchy hook, then briefly preview what's coming
- STORIES (5 segments, ~90 seconds each):
  - transition: Natural phrase to introduce the story
  - headline: Brief title for chapter markers (max 50 chars)
  - body: Main content - what happened, why it matters, what engineers should know
  - source_attribution: Brief attribution (e.g., "via GitHub", "from the Kubernetes blog")
- OUTRO (15-20 seconds): Sign off and remind listeners to subscribe

Writing guidelines:
- Target ~1200-1500 words total (~8 minutes at 150 words/minute)
- Each story body should be ~200-250 words
- Use conversational language suitable for spoken delivery
- Include specific technical details that engineers care about
- When relevant, mention version numbers, dates, or specific improvements
- Create smooth transitions between stories

Output format is strictly JSON matching the schema provided."""


@backoff.on_exception(
    backoff.expo,
    (RateLimitError, HTTPStatusError),
    max_tries=5,
    max_time=120,
)
async def generate_podcast_script(
    summaries: list[ClusterDistillOutput],
    topics: list[str],
    issue_date: date,
    client: AsyncOpenAI | None = None,
) -> PodcastScriptResult | None:
    """
    Generate a podcast script from cluster summaries.

    Args:
        summaries: List of distilled cluster summaries (typically 5)
        topics: List of topic categories for each story
        issue_date: The date of the digest
        client: Optional OpenAI client

    Returns:
        PodcastScriptResult with script and token usage, or None if generation fails
    """
    if not summaries:
        logger.warning("podcast_script_no_summaries")
        return None

    if not client:
        settings = get_settings()
        if not settings.openai_api_key:
            logger.warning("openai_api_key_not_set_for_podcast_script")
            return None
        client = AsyncOpenAI(api_key=settings.openai_api_key)

    # Build user prompt with all stories
    story_blocks = []
    for i, (summary, topic) in enumerate(zip(summaries, topics), start=1):
        citations_text = (
            ", ".join(c.label for c in summary.citations[:2])
            if summary.citations
            else "various sources"
        )
        story_blocks.append(f"""
STORY {i} (Topic: {topic}):
HEADLINE: {summary.headline}
TEASER: {summary.teaser}
TAKEAWAY: {summary.takeaway}
WHY IT MATTERS: {summary.why_care or "Not specified"}
KEY POINTS:
- {summary.bullets[0] if summary.bullets else "See details"}
- {summary.bullets[1] if len(summary.bullets) > 1 else ""}
SOURCES: {citations_text}
""")

    formatted_date = issue_date.strftime("%A, %B %d, %Y")  # e.g., "Monday, January 13, 2026"

    user_prompt = f"""Create an 8-minute podcast script for Noyau Daily, covering the top {len(summaries)} tech stories of the day.

DATE: {formatted_date}

STORIES TO COVER:
{"".join(story_blocks)}

Create an engaging, conversational script that flows naturally between all {len(summaries)} stories. Each story should be approximately equal length (~90 seconds of speech).

Remember:
- Open with the date and a hook
- Provide practical, engineer-focused analysis
- Keep transitions smooth and natural
- End with a brief sign-off"""

    try:
        response = await client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format=PodcastScript,
            temperature=0.7,  # Slightly higher for natural-sounding speech
        )

        result = response.choices[0].message.parsed
        usage = response.usage

        if result and usage:
            headlines = [s.headline[:30] for s in result.stories]
            logger.info(
                f"podcast_script_generated | stories={len(result.stories)} | headlines={headlines} | tokens={usage.total_tokens}"
            )
            return PodcastScriptResult(
                script=result,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
            )

        logger.warning("podcast_script_no_result")
        return None

    except Exception as e:
        logger.bind(error=str(e)).error("podcast_script_generation_error")
        return None


def estimate_script_duration(script: PodcastScript) -> float:
    """
    Estimate the duration of a podcast script based on word count.

    Assumes ~150 words per minute speaking rate (2.5 words/second).
    """
    total_words = len(script.intro.split()) + len(script.outro.split())
    for story in script.stories:
        total_words += len(story.transition.split())
        total_words += len(story.body.split())
        total_words += len(story.source_attribution.split())

    return total_words / 2.5  # seconds
