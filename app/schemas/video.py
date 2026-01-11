"""Pydantic schemas for video generation."""

from typing import Literal

from pydantic import BaseModel, Field


class VideoScript(BaseModel):
    """Script for a short-form video."""

    hook: str = Field(
        description="Opening hook, 2-3 seconds, attention-grabbing question or statement"
    )
    intro: str = Field(description="Story introduction, 5-8 seconds")
    body: str = Field(description="Main content, 20-25 seconds")
    cta: str = Field(description="Call-to-action, 3-5 seconds, encourage subscription/engagement")
    visual_keywords: list[str] = Field(
        description="5-8 keywords for stock footage search (e.g., 'coding', 'server room', 'cybersecurity')"
    )
    topic: Literal["dev", "security", "oss", "ai", "cloud", "general"] = Field(
        description="Primary topic category for visual styling"
    )


class VideoScriptResult(BaseModel):
    """Result of script generation including token usage."""

    script: VideoScript
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class StockVideo(BaseModel):
    """A stock video from Pexels."""

    id: int
    duration: float
    width: int
    height: int
    url: str
    video_files: list[dict]
    user: str


class VideoClip(BaseModel):
    """A video clip with timing information."""

    path: str
    start_time: float
    duration: float


class VideoGenerationInput(BaseModel):
    """Input for video generation from a cluster summary."""

    headline: str
    teaser: str
    takeaway: str
    why_care: str | None
    bullets: list[str]
    topic: str
    rank: int
    canonical_identity: str


class VideoGenerationResult(BaseModel):
    """Result of video generation."""

    video_path: str
    duration_seconds: float
    script: VideoScript
    thumbnail_path: str | None = None
    s3_url: str | None = None
    youtube_video_id: str | None = None
    youtube_url: str | None = None


class YouTubeMetadata(BaseModel):
    """Metadata for YouTube upload."""

    title: str = Field(max_length=100)
    description: str
    tags: list[str] = Field(default_factory=list)
    category_id: str = "28"  # Science & Technology
    privacy_status: Literal["public", "unlisted", "private"] = "unlisted"
    made_for_kids: bool = False
