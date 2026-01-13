from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = Field(default="postgresql+asyncpg://noyau:password@localhost:5432/noyau")

    # API Keys
    openai_api_key: str = Field(default="")
    resend_api_key: str = Field(default="")
    elevenlabs_api_key: str = Field(default="")

    # LLM Configuration
    llm_model: str = Field(default="gpt-4o")

    # Email Validation (Verifalia)
    verifalia_username: str = Field(default="")
    verifalia_password: str = Field(default="")
    verifalia_quality: str = Field(default="Standard")
    verifalia_timeout: int = Field(default=30)
    verifalia_cache_ttl_hours: int = Field(default=24)

    # Security
    secret_key: str = Field(default="change-me-in-production")

    # Application
    base_url: str = Field(default="https://noyau.news")
    email_domain: str = Field(default="noyau.news")
    dev_email: str = Field(default="")  # Email address for testing templates
    debug: bool = Field(default=False)
    log_dir: str = Field(default="./logs")

    # Scheduler
    scheduler_enabled: bool = Field(default=True)

    # Discord (webhook for channel posting)
    discord_webhook_url: str = Field(default="")
    discord_error_webhook_url: str = Field(default="")

    # Discord Bot (for DM subscriptions)
    discord_bot_token: str = Field(default="")
    discord_application_id: str = Field(default="")

    # Slack App (for DM subscriptions)
    slack_client_id: str = Field(default="")
    slack_client_secret: str = Field(default="")
    slack_signing_secret: str = Field(default="")

    # Video Generation
    video_enabled: bool = Field(default=False)
    video_output_dir: str = Field(default="./output/videos")
    pexels_api_key: str = Field(default="")
    freesound_client_id: str = Field(default="")  # For background music
    freesound_client_secret: str = Field(default="")  # Used as API token
    youtube_client_id: str = Field(default="")
    youtube_client_secret: str = Field(default="")
    youtube_refresh_token: str = Field(default="")
    tts_provider: str = Field(default="edge")

    # S3 Storage
    s3_bucket_name: str = Field(default="")
    s3_region: str = Field(default="us-east-1")
    s3_access_key_id: str = Field(default="")
    s3_secret_access_key: str = Field(default="")
    s3_endpoint_url: str = Field(default="")  # For S3-compatible storage (MinIO, R2, etc.)
    s3_public_url: str = Field(default="")  # Public URL for social media (Instagram/TikTok)

    # Twitter/Nitter credentials for session token generation
    twitter_username: str = Field(default="")
    twitter_password: str = Field(default="")
    twitter_totp_secret: str = Field(default="")  # Optional: for 2FA accounts

    # Twitter API v2 credentials for posting
    twitter_api_key: str = Field(default="")
    twitter_api_secret: str = Field(default="")
    twitter_access_token: str = Field(default="")
    twitter_access_token_secret: str = Field(default="")

    # TikTok Content Posting API credentials
    tiktok_client_key: str = Field(default="")
    tiktok_client_secret: str = Field(default="")
    tiktok_access_token: str = Field(default="")
    tiktok_refresh_token: str = Field(default="")
    tiktok_redirect_uri: str = Field(default="")

    # Instagram Graph API credentials
    instagram_app_id: str = Field(default="")
    instagram_app_secret: str = Field(default="")
    instagram_business_account_id: str = Field(default="")
    instagram_access_token: str = Field(default="")


class SourceThresholdConfig:
    """Source-specific threshold configuration."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.min_reactions: int = data.get("min_reactions", 0)
        self.low_engagement_penalty: float = data.get("low_engagement_penalty", 0.0)


class RankingConfig:
    """Ranking configuration from config.yml."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.half_life_hours: float = data.get("half_life_hours", 18)
        self.weights: dict[str, float] = data.get(
            "weights",
            {"recency": 0.30, "engagement": 0.20, "velocity": 0.25, "echo": 0.25},
        )
        self.echo_window_hours: int = data.get("echo_window_hours", 12)
        self.viral: dict[str, Any] = data.get(
            "viral",
            {"engagement_pctl": 90, "velocity_pctl": 90, "echo_accounts": 3},
        )
        self.practical_boost_keywords: list[str] = data.get(
            "practical_boost_keywords",
            ["release", "changelog", "benchmark", "postmortem"],
        )
        self.practical_boost_value: float = data.get("practical_boost_value", 0.15)
        self.already_seen_penalty: float = data.get("already_seen_penalty", 0.30)
        self.source_thresholds: dict[str, SourceThresholdConfig] = {
            source: SourceThresholdConfig(threshold_data)
            for source, threshold_data in data.get("source_thresholds", {}).items()
        }


class DigestConfig:
    """Digest configuration from config.yml."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.max_items: int = data.get("max_items", 10)
        self.send_time_default_local: str = data.get("send_time_default_local", "08:00")
        web_gate = data.get("web_soft_gate", {})
        self.free_items: int = web_gate.get("free_items", 5)


class FilterConfig:
    """Filter configuration from config.yml."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.exclude_politics: bool = data.get("exclude_politics", True)
        self.politics_keywords: list[str] = data.get(
            "politics_keywords",
            ["election", "senate", "parliament", "candidate"],
        )


class SeedsConfig:
    """Seeds configuration from config.yml."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.rss_feeds: list[dict[str, str]] = data.get("rss_feeds", [])
        self.github_release_feeds: list[dict[str, str]] = data.get("github_release_feeds", [])
        self.x_accounts: list[dict[str, str]] = data.get("x_accounts", [])
        self.reddit_subreddits: list[dict[str, str]] = data.get("reddit_subreddits", [])
        self.devto_tags: list[str] = data.get("devto_tags", [])
        self.youtube_channels: list[dict[str, str]] = data.get("youtube_channels", [])
        self.bluesky_accounts: list[dict[str, str]] = data.get("bluesky_accounts", [])


class NitterConfig:
    """Nitter configuration from config.yml."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.enabled: bool = data.get("enabled", True)
        self.instances: list[str] = data.get(
            "instances",
            ["nitter.poast.org", "nitter.privacydev.net"],
        )
        self.timeout_seconds: int = data.get("timeout_seconds", 10)
        self.max_retries: int = data.get("max_retries", 3)


class DiscordConfig:
    """Discord configuration from config.yml and environment."""

    def __init__(self, data: dict[str, Any], settings: "Settings") -> None:
        self.enabled: bool = data.get("enabled", False)
        self.webhook_url: str = settings.discord_webhook_url
        self.error_webhook_url: str = settings.discord_error_webhook_url
        self.invite_url: str = data.get("invite_url", "")
        self.post_time_utc: str = data.get("post_time_utc", "07:30")


class DiscordBotConfig:
    """Discord Bot configuration for DM subscriptions."""

    def __init__(self, data: dict[str, Any], settings: "Settings") -> None:
        self.enabled: bool = data.get("enabled", False)
        self.bot_token: str = settings.discord_bot_token
        self.application_id: str = settings.discord_application_id
        self.post_time_utc: str = data.get("post_time_utc", "07:30")
        self.invite_url: str = data.get("invite_url", "")


class SlackConfig:
    """Slack App configuration for DM subscriptions."""

    def __init__(self, data: dict[str, Any], settings: "Settings") -> None:
        self.enabled: bool = data.get("enabled", False)
        self.client_id: str = settings.slack_client_id
        self.client_secret: str = settings.slack_client_secret
        self.signing_secret: str = settings.slack_signing_secret
        self.post_time_utc: str = data.get("post_time_utc", "07:30")
        self.scopes: list[str] = data.get(
            "scopes", ["chat:write", "users:read", "users:read.email"]
        )


class TwitterConfig:
    """Twitter configuration from config.yml and environment."""

    def __init__(self, data: dict[str, Any], settings: "Settings") -> None:
        self.enabled: bool = data.get("enabled", False)
        self.intro_template: str = data.get(
            "intro_template",
            "{date} Tech Briefing\n\n10 things worth knowing today. No fluff.\n\nLet's go ↓",
        )
        self.outro_template: str = data.get(
            "outro_template",
            "That's your daily briefing.\n\nGet this in your inbox → noyau.news\nFollow for tomorrow's thread\n\nSee you tomorrow ✌️",
        )
        self.include_hashtags: bool = data.get("include_hashtags", True)
        self.retry_delay_seconds: int = data.get("retry_delay_seconds", 5)
        self.max_retries: int = data.get("max_retries", 3)

        # Credentials from environment
        self.api_key: str = settings.twitter_api_key
        self.api_secret: str = settings.twitter_api_secret
        self.access_token: str = settings.twitter_access_token
        self.access_token_secret: str = settings.twitter_access_token_secret


class TikTokConfig:
    """TikTok configuration from config.yml and environment."""

    def __init__(self, data: dict[str, Any], settings: "Settings") -> None:
        self.enabled: bool = data.get("enabled", False)
        self.videos_per_day: int = data.get("videos_per_day", 1)
        self.privacy_level: str = data.get("privacy_level", "PUBLIC_TO_EVERYONE")
        self.disable_duet: bool = data.get("disable_duet", False)
        self.disable_comment: bool = data.get("disable_comment", False)
        self.disable_stitch: bool = data.get("disable_stitch", False)
        self.include_hashtags: bool = data.get("include_hashtags", True)
        self.default_hashtags: list[str] = data.get(
            "default_hashtags",
            ["technews", "programming", "developer", "noyau"],
        )
        self.retry_delay_seconds: int = data.get("retry_delay_seconds", 5)
        self.max_retries: int = data.get("max_retries", 3)

        # Redirect URI for OAuth (env takes precedence over config.yml)
        self.redirect_uri: str = settings.tiktok_redirect_uri or data.get(
            "redirect_uri",
            "https://noyau.news/auth/tiktok/callback",
        )

        # Credentials from environment
        self.client_key: str = settings.tiktok_client_key
        self.client_secret: str = settings.tiktok_client_secret
        self.access_token: str = settings.tiktok_access_token
        self.refresh_token: str = settings.tiktok_refresh_token


class InstagramConfig:
    """Instagram configuration from config.yml and environment."""

    def __init__(self, data: dict[str, Any], settings: "Settings") -> None:
        self.enabled: bool = data.get("enabled", False)
        self.reels_per_day: int = data.get("reels_per_day", 1)
        self.include_hashtags: bool = data.get("include_hashtags", True)
        self.default_hashtags: list[str] = data.get(
            "default_hashtags",
            ["technews", "programming", "developer", "reels", "tech"],
        )

        # Credentials from environment
        self.app_id: str = settings.instagram_app_id
        self.app_secret: str = settings.instagram_app_secret
        self.business_account_id: str = settings.instagram_business_account_id
        self.access_token: str = settings.instagram_access_token


class VideoFormatConfig:
    """Video format settings."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.width: int = data.get("width", 1080)
        self.height: int = data.get("height", 1920)
        self.fps: int = data.get("fps", 30)
        self.duration_target: int = data.get("duration_target", 45)
        self.max_duration: int = data.get("max_duration", 60)


class VideoStyleConfig:
    """Video style settings."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.font: str = data.get("font", "Inter")
        self.font_size: int = data.get("font_size", 48)
        self.font_color: str = data.get("font_color", "#FFFFFF")
        self.background_color: str = data.get("background_color", "#0A0A0A")
        self.accent_color: str = data.get("accent_color", "#FF6B35")


class VideoYouTubeConfig:
    """YouTube upload settings."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.category_id: str = data.get("category_id", "28")
        self.privacy_status: str = data.get("privacy_status", "unlisted")
        self.made_for_kids: bool = data.get("made_for_kids", False)
        self.default_language: str = data.get("default_language", "en")
        self.default_tags: list[str] = data.get(
            "default_tags", ["tech news", "programming", "noyau"]
        )


class VideoConfig:
    """Video generation configuration from config.yml and environment."""

    def __init__(self, data: dict[str, Any], settings: "Settings") -> None:
        # Combine env and config.yml settings
        self.enabled: bool = settings.video_enabled and data.get("enabled", False)
        self.count: int = data.get("count", 3)
        self.output_dir: str = settings.video_output_dir or data.get(
            "output_dir", "./output/videos"
        )
        self.tts_provider: str = settings.tts_provider

        # Combined video mode settings
        self.combined_mode: bool = data.get("combined_mode", False)
        self.combined_duration_target: int = data.get("combined_duration_target", 60)

        # Sub-configs from config.yml
        self.format = VideoFormatConfig(data.get("format", {}))
        self.style = VideoStyleConfig(data.get("style", {}))
        self.youtube = VideoYouTubeConfig(data.get("youtube", {}))

        # Stock footage settings
        stock_data = data.get("stock_footage", {})
        self.stock_footage_provider: str = stock_data.get("provider", "pexels")
        self.stock_footage_orientation: str = stock_data.get("orientation", "portrait")
        self.stock_footage_fallback_queries: list[str] = stock_data.get(
            "fallback_queries", ["technology", "coding", "futuristic"]
        )


class PodcastTTSConfig:
    """Podcast TTS configuration."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.provider: str = data.get("provider", "openai")
        self.voice: str = data.get("voice", "nova")
        self.model: str = data.get("model", "tts-1-hd")


class PodcastAudioConfig:
    """Podcast audio configuration."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.background_music_volume: float = data.get("background_music_volume", 0.03)
        self.output_dir: str = data.get("output_dir", "./output/podcasts")


class PodcastYouTubeConfig:
    """Podcast YouTube upload configuration."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.category_id: str = data.get("category_id", "28")
        self.privacy_status: str = data.get("privacy_status", "public")
        self.made_for_kids: bool = data.get("made_for_kids", False)


class PodcastFeedConfig:
    """Podcast RSS feed configuration."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.title: str = data.get("title", "Noyau Daily Tech Digest")
        self.description: str = data.get(
            "description",
            "Your daily briefing on what matters in tech. Top 5 stories in under 10 minutes.",
        )
        self.author: str = data.get("author", "Noyau News")
        self.email: str = data.get("email", "hello@noyau.news")
        self.category: str = data.get("category", "Technology")
        self.subcategory: str = data.get("subcategory", "Tech News")
        self.language: str = data.get("language", "en-us")
        self.explicit: bool = data.get("explicit", False)
        self.artwork_url: str = data.get("artwork_url", "https://noyau.news/podcast-artwork.jpg")


class PodcastConfig:
    """Podcast generation configuration from config.yml."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.enabled: bool = data.get("enabled", False)
        self.story_count: int = data.get("story_count", 5)
        self.target_duration_minutes: int = data.get("target_duration_minutes", 8)

        self.tts = PodcastTTSConfig(data.get("tts", {}))
        self.audio = PodcastAudioConfig(data.get("audio", {}))
        self.youtube = PodcastYouTubeConfig(data.get("youtube", {}))
        self.feed = PodcastFeedConfig(data.get("feed", {}))


class AppConfig:
    """Combined application configuration from .env and config.yml."""

    def __init__(self) -> None:
        self.settings = Settings()
        self._load_yaml()

    def _load_yaml(self) -> None:
        config_path = Path("config.yml")
        if config_path.exists():
            with open(config_path) as f:
                data = yaml.safe_load(f) or {}
        else:
            data = {}

        self.digest = DigestConfig(data.get("digest", {}))
        self.filters = FilterConfig(data.get("filters", {}))
        self.ranking = RankingConfig(data.get("ranking", {}))
        self.seeds = SeedsConfig(data.get("seeds", {}))
        self.nitter = NitterConfig(data.get("nitter", {}))
        self.discord = DiscordConfig(data.get("discord", {}), self.settings)
        self.discord_bot = DiscordBotConfig(data.get("discord_bot", {}), self.settings)
        self.slack = SlackConfig(data.get("slack", {}), self.settings)
        self.twitter = TwitterConfig(data.get("twitter", {}), self.settings)
        self.tiktok = TikTokConfig(data.get("tiktok", {}), self.settings)
        self.instagram = InstagramConfig(data.get("instagram", {}), self.settings)
        self.video = VideoConfig(data.get("video", {}), self.settings)
        self.podcast = PodcastConfig(data.get("podcast", {}))


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


@lru_cache
def get_config() -> AppConfig:
    """Get cached full config instance."""
    return AppConfig()
