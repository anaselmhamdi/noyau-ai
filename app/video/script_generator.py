"""LLM-based video script generation from cluster summaries."""

import backoff
from httpx import HTTPStatusError
from openai import AsyncOpenAI, RateLimitError

from app.config import get_settings
from app.core.logging import get_logger
from app.schemas.llm import ClusterDistillOutput
from app.schemas.video import (
    CombinedVideoScript,
    CombinedVideoScriptResult,
    VideoScript,
    VideoScriptResult,
)

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are a short-form video scriptwriter for a tech news channel called "Noyau".
Your job is to convert tech news summaries into engaging 45-second video scripts.

Rules for the script:
- HOOK (2-3 seconds): Start with a punchy question, bold statement, or surprising fact
  - Examples: "Python just changed everything.", "This vulnerability affects millions.", "You're using this wrong."
- INTRO (5-8 seconds): Briefly set up what happened
- BODY (20-25 seconds): Explain why it matters, what developers should know
- CTA (3-5 seconds): End with engagement prompt
  - Examples: "Follow for daily tech updates.", "What do you think? Comment below."

Writing style:
- Conversational, not formal
- Short sentences for easy narration
- Avoid jargon when possible, explain terms briefly if needed
- Use "you" to speak directly to the viewer
- Create natural pauses with sentence breaks

Visual keywords:
- Provide 5-8 specific, searchable terms for B-roll footage
- Focus on tech-related visuals: "coding on laptop", "data center", "cybersecurity lock"
- Include at least one abstract/mood keyword: "futuristic", "technology particles"

Output format is strictly JSON matching the schema provided."""


@backoff.on_exception(
    backoff.expo,
    (RateLimitError, HTTPStatusError),
    max_tries=5,
    max_time=120,
)
async def generate_script(
    summary: ClusterDistillOutput,
    topic: str,
    rank: int,
    client: AsyncOpenAI | None = None,
) -> VideoScriptResult | None:
    """
    Generate a video script from a cluster summary.

    Args:
        summary: The distilled cluster summary
        topic: Topic category (dev, security, oss, etc.)
        rank: Rank in today's digest (1-3)
        client: Optional OpenAI client

    Returns:
        VideoScriptResult with script and token usage, or None if generation fails
    """
    if not client:
        settings = get_settings()
        if not settings.openai_api_key:
            logger.warning("openai_api_key_not_set_for_video_script")
            return None
        client = AsyncOpenAI(api_key=settings.openai_api_key)

    user_prompt = f"""Create a 45-second video script for this tech news story.

HEADLINE: {summary.headline}
TEASER: {summary.teaser}
TAKEAWAY: {summary.takeaway}
WHY IT MATTERS: {summary.why_care or "Not specified"}
KEY POINTS:
{chr(10).join(f"- {bullet}" for bullet in summary.bullets)}

Topic category: {topic}
Ranking: #{rank} story of the day

Create an engaging script that captures attention in the first 3 seconds."""

    try:
        response = await client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format=VideoScript,
            temperature=0.7,  # Slightly higher for creative scripts
        )

        result = response.choices[0].message.parsed
        usage = response.usage

        if result and usage:
            logger.info(
                f"video_script_generated: {summary.headline[:50]} | tokens={usage.total_tokens}"
            )
            return VideoScriptResult(
                script=result,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
            )

        logger.bind(headline=summary.headline[:50]).warning("video_script_no_result")
        return None

    except Exception as e:
        logger.bind(headline=summary.headline[:50], error=str(e)).error(
            "video_script_generation_error"
        )
        return None


def estimate_script_duration(script: VideoScript) -> float:
    """
    Estimate the duration of a script based on word count.

    Assumes ~150 words per minute speaking rate (2.5 words/second).
    """
    total_words = sum(
        len(section.split()) for section in [script.hook, script.intro, script.body, script.cta]
    )
    return total_words / 2.5  # seconds


# -----------------------------------------------------------------------------
# Combined Multi-Story Script Generation
# -----------------------------------------------------------------------------

COMBINED_SYSTEM_PROMPT = """You are a short-form video scriptwriter for a tech news channel called "Noyau".
Your job is to convert THREE tech news summaries into a single engaging 60-second daily digest video.

Structure (total ~60 seconds):
- HOOK (2-3 seconds): Punchy opening that teases all 3 stories
  - Examples: "Three stories shaking up tech today.", "Your daily tech briefing starts now."
- INTRO (3-5 seconds): Quick setup for the digest format
  - Example: "Here's what you need to know."
- STORY 1 (~18 seconds):
  - transition: "Story one." or "First up."
  - headline_text: 5-8 word summary for visual overlay
  - body: Main content for this story
- STORY 2 (~18 seconds):
  - transition: "Next up." or "Story two."
  - headline_text: 5-8 word summary for visual overlay
  - body: Main content for this story
- STORY 3 (~18 seconds):
  - transition: "And finally." or "Last but not least."
  - headline_text: 5-8 word summary for visual overlay
  - body: Main content for this story
- CTA (3-5 seconds): Single closing call-to-action
  - Example: "Follow for your daily tech briefing."

Writing style:
- Fast-paced but clear
- Short sentences for easy narration
- Each story body should be self-contained
- Create smooth flow between stories
- Use "you" to speak directly to the viewer

Visual keywords:
- Provide 2-3 specific keywords per story for B-roll
- Focus on variety across all 3 stories
- Include tech-related visuals: "coding", "server room", "cybersecurity"

Output format is strictly JSON matching the schema provided."""


@backoff.on_exception(
    backoff.expo,
    (RateLimitError, HTTPStatusError),
    max_tries=5,
    max_time=120,
)
async def generate_combined_script(
    summaries: list[ClusterDistillOutput],
    topics: list[str],
    client: AsyncOpenAI | None = None,
) -> CombinedVideoScriptResult | None:
    """
    Generate a combined video script from 3 cluster summaries.

    Args:
        summaries: List of exactly 3 distilled cluster summaries
        topics: List of topic categories for each story
        client: Optional OpenAI client

    Returns:
        CombinedVideoScriptResult with script and token usage, or None if failed
    """
    if len(summaries) != 3:
        logger.warning(f"combined_script_requires_3_summaries, got {len(summaries)}")
        return None

    if not client:
        settings = get_settings()
        if not settings.openai_api_key:
            logger.warning("openai_api_key_not_set_for_combined_script")
            return None
        client = AsyncOpenAI(api_key=settings.openai_api_key)

    # Build user prompt with all 3 stories
    story_blocks = []
    for i, (summary, topic) in enumerate(zip(summaries, topics), start=1):
        story_blocks.append(f"""
STORY {i} (Topic: {topic}):
HEADLINE: {summary.headline}
TEASER: {summary.teaser}
TAKEAWAY: {summary.takeaway}
KEY POINTS: {", ".join(summary.bullets)}
""")

    user_prompt = f"""Create a 60-second combined daily digest video script for these 3 tech stories:
{"".join(story_blocks)}
Create an engaging script that flows smoothly between all 3 stories. Each story should be approximately equal length (~18 seconds each)."""

    try:
        response = await client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": COMBINED_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format=CombinedVideoScript,
            temperature=0.7,
        )

        result = response.choices[0].message.parsed
        usage = response.usage

        if result and usage:
            headlines = [s.headline[:30] for s in summaries]
            logger.info(
                f"combined_script_generated | stories={headlines} | tokens={usage.total_tokens}"
            )
            return CombinedVideoScriptResult(
                script=result,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
            )

        logger.warning("combined_script_no_result")
        return None

    except Exception as e:
        logger.bind(error=str(e)).error("combined_script_generation_error")
        return None


def estimate_combined_script_duration(script: CombinedVideoScript) -> float:
    """
    Estimate the duration of a combined script based on word count.

    Assumes ~150 words per minute speaking rate (2.5 words/second).
    """
    words = len(script.hook.split()) + len(script.intro.split()) + len(script.cta.split())
    for story in script.stories:
        words += len(story.transition.split()) + len(story.body.split())
    return words / 2.5  # seconds
