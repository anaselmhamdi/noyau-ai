"""Pydantic schemas for podcast generation."""

from datetime import date, datetime

from pydantic import BaseModel, Field

# -----------------------------------------------------------------------------
# Podcast Script Schemas
# -----------------------------------------------------------------------------


class PodcastStorySegment(BaseModel):
    """A single story segment within a podcast episode."""

    transition: str = Field(
        description="Transition phrase (e.g., 'First up...', 'Moving on...', 'And finally...')"
    )
    headline: str = Field(description="Brief headline for chapter markers (max 50 chars)")
    body: str = Field(description="Main narration for this story, ~60-80 seconds of speech")
    source_attribution: str = Field(
        description="Brief source attribution (e.g., 'via GitHub', 'reported by TechCrunch')"
    )


class PodcastScript(BaseModel):
    """Full script for a podcast episode (~8 minutes)."""

    intro: str = Field(
        description="Opening segment: hook + date + preview of stories (30-45 seconds)"
    )
    stories: list[PodcastStorySegment] = Field(
        min_length=1, max_length=10, description="Story segments, typically 5 for daily digest"
    )
    outro: str = Field(description="Closing segment: sign-off + subscribe CTA (15-20 seconds)")


class PodcastScriptResult(BaseModel):
    """Result of script generation including token usage."""

    script: PodcastScript
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


# -----------------------------------------------------------------------------
# Audio Generation Schemas
# -----------------------------------------------------------------------------


class ChapterMarker(BaseModel):
    """A chapter marker for podcast players."""

    title: str
    start_time: float  # seconds
    end_time: float | None = None


class PodcastAudioResult(BaseModel):
    """Result of podcast audio generation."""

    audio_path: str
    duration_seconds: float
    chapters: list[ChapterMarker]


# -----------------------------------------------------------------------------
# Podcast Episode Schemas (for API responses)
# -----------------------------------------------------------------------------


class PodcastEpisode(BaseModel):
    """Podcast episode data for API responses."""

    issue_date: date
    episode_number: int
    title: str
    description: str
    audio_url: str
    youtube_url: str | None = None
    duration_seconds: float
    published_at: datetime

    class Config:
        from_attributes = True


class PodcastFeedInfo(BaseModel):
    """Podcast feed metadata for API responses."""

    title: str
    description: str
    author: str
    feed_url: str
    website_url: str
    artwork_url: str
    category: str
    episode_count: int
    latest_episode: PodcastEpisode | None = None


# -----------------------------------------------------------------------------
# Generation Result Schemas
# -----------------------------------------------------------------------------


class PodcastGenerationResult(BaseModel):
    """Complete result of podcast generation pipeline."""

    issue_date: date
    audio_path: str
    audio_url: str  # S3 URL
    duration_seconds: float
    youtube_video_id: str | None = None
    youtube_url: str | None = None
    chapters: list[ChapterMarker]
    script: PodcastScript
