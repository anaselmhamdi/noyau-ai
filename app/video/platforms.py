"""Platform configurations for different short-form video platforms."""

from dataclasses import dataclass
from enum import Enum


class Platform(str, Enum):
    """Supported video platforms."""

    YOUTUBE_SHORTS = "youtube"
    TIKTOK = "tiktok"
    INSTAGRAM_REELS = "reels"
    ALL = "all"  # Generate for all platforms


@dataclass
class PlatformSpec:
    """Video specifications for a platform."""

    name: str
    width: int
    height: int
    fps: int
    max_duration: int  # seconds
    min_duration: int  # seconds
    aspect_ratio: str
    file_format: str
    max_file_size_mb: int
    hashtag_prefix: str  # Platform-specific hashtag


# Platform specifications
PLATFORM_SPECS: dict[Platform, PlatformSpec] = {
    Platform.YOUTUBE_SHORTS: PlatformSpec(
        name="YouTube Shorts",
        width=1080,
        height=1920,
        fps=30,
        max_duration=60,
        min_duration=15,
        aspect_ratio="9:16",
        file_format="mp4",
        max_file_size_mb=256,
        hashtag_prefix="#shorts",
    ),
    Platform.TIKTOK: PlatformSpec(
        name="TikTok",
        width=1080,
        height=1920,
        fps=30,
        max_duration=180,  # 3 minutes for most accounts
        min_duration=5,
        aspect_ratio="9:16",
        file_format="mp4",
        max_file_size_mb=287,
        hashtag_prefix="#fyp",
    ),
    Platform.INSTAGRAM_REELS: PlatformSpec(
        name="Instagram Reels",
        width=1080,
        height=1920,
        fps=30,
        max_duration=90,
        min_duration=15,
        aspect_ratio="9:16",
        file_format="mp4",
        max_file_size_mb=250,
        hashtag_prefix="#reels",
    ),
}


def get_platform_spec(platform: Platform) -> PlatformSpec:
    """Get the spec for a platform."""
    return PLATFORM_SPECS.get(platform, PLATFORM_SPECS[Platform.YOUTUBE_SHORTS])


def get_all_platforms() -> list[Platform]:
    """Get all individual platforms (excluding ALL)."""
    return [p for p in Platform if p != Platform.ALL]


@dataclass
class PlatformResult:
    """Result of uploading to a platform."""

    platform: Platform
    success: bool
    video_id: str | None = None
    video_url: str | None = None
    error: str | None = None


# Platform-specific CTA templates
PLATFORM_CTAS: dict[Platform, str] = {
    Platform.YOUTUBE_SHORTS: "Subscribe for daily tech updates!",
    Platform.TIKTOK: "Follow for more tech news!",
    Platform.INSTAGRAM_REELS: "Follow @noyau.news for more!",
}


def get_platform_cta(platform: Platform) -> str:
    """Get the CTA text for a platform."""
    return PLATFORM_CTAS.get(platform, "Follow for more!")


# Platform-specific hashtags by topic
PLATFORM_HASHTAGS: dict[Platform, dict[str, list[str]]] = {
    Platform.YOUTUBE_SHORTS: {
        "dev": ["#coding", "#programming", "#developer", "#tech"],
        "security": ["#cybersecurity", "#hacking", "#infosec"],
        "ai": ["#ai", "#artificialintelligence", "#machinelearning"],
        "oss": ["#opensource", "#github", "#devtools"],
        "general": ["#technews", "#techtrends"],
    },
    Platform.TIKTOK: {
        "dev": ["#coding", "#programmer", "#softwareengineering", "#learntocode", "#techcareer"],
        "security": ["#cybersecurity", "#hacker", "#techsafety"],
        "ai": ["#ai", "#chatgpt", "#aiart", "#machinelearning"],
        "oss": ["#opensource", "#github", "#coding"],
        "general": ["#tech", "#techtok", "#learnontiktok"],
    },
    Platform.INSTAGRAM_REELS: {
        "dev": ["#coding", "#programmer", "#webdeveloper", "#softwaredeveloper"],
        "security": ["#cybersecurity", "#ethicalhacking", "#infosec"],
        "ai": ["#artificialintelligence", "#aitools", "#machinelearning"],
        "oss": ["#opensource", "#developertools", "#github"],
        "general": ["#tech", "#technology", "#technews"],
    },
}


def get_platform_hashtags(platform: Platform, topic: str) -> list[str]:
    """Get hashtags for a platform and topic."""
    platform_tags = PLATFORM_HASHTAGS.get(platform, {})
    return platform_tags.get(topic, platform_tags.get("general", []))
