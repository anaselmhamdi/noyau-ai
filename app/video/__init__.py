"""Video generation module for creating short-form content from daily digest."""

from app.video.orchestrator import generate_videos_for_issue
from app.video.platforms import Platform, get_platform_spec

__all__ = ["generate_videos_for_issue", "Platform", "get_platform_spec"]
