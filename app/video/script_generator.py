"""LLM-based video script generation from cluster summaries."""

import backoff
from httpx import HTTPStatusError
from openai import AsyncOpenAI, RateLimitError

from app.config import get_settings
from app.core.logging import get_logger
from app.schemas.llm import ClusterDistillOutput
from app.schemas.video import VideoScript, VideoScriptResult

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
