"""Video generation configuration."""

import platform
from dataclasses import dataclass, field
from pathlib import Path


def get_default_font() -> str:
    """Get a default system font path based on OS."""
    # Check for custom Montserrat Bold font first (trendy, modern look)
    custom_font = Path(__file__).parent.parent.parent / "assets" / "fonts" / "Montserrat-Bold.ttf"
    if custom_font.exists():
        return str(custom_font)

    system = platform.system()

    if system == "Darwin":  # macOS
        candidates = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/Library/Fonts/Arial Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/Library/Fonts/Arial.ttf",
        ]
    elif system == "Linux":
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    else:  # Windows
        candidates = [
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/Arial.ttf",
        ]

    for font_path in candidates:
        if Path(font_path).exists():
            return font_path

    # Fallback to font name (may work if font is installed)
    return "Arial"


@dataclass
class VideoFormatConfig:
    """Video format settings for YouTube Shorts."""

    width: int = 1080
    height: int = 1920
    fps: int = 30
    duration_target: int = 45
    max_duration: int = 60


@dataclass
class VideoStyleConfig:
    """Visual style settings for videos."""

    font: str = ""  # Will be set in __post_init__
    font_size: int = 56  # Increased for better visibility on mobile
    font_color: str = "#FFFFFF"
    background_color: str = "#0A0A0A"
    accent_color: str = "#FF6B35"
    logo_path: str = "assets/logo.png"

    def __post_init__(self):
        if not self.font:
            self.font = get_default_font()


@dataclass
class StockFootageConfig:
    """Stock footage settings."""

    provider: str = "pexels"
    orientation: str = "portrait"
    per_page: int = 5
    fallback_queries: list[str] = field(
        default_factory=lambda: ["technology", "coding", "futuristic"]
    )


@dataclass
class YouTubeConfig:
    """YouTube upload settings."""

    category_id: str = "28"  # Science & Technology
    privacy_status: str = "public"
    made_for_kids: bool = False
    default_language: str = "en"
    default_tags: list[str] = field(
        default_factory=lambda: ["tech news", "programming", "software", "noyau"]
    )


@dataclass
class VideoConfig:
    """Combined video configuration."""

    enabled: bool = False
    count: int = 3
    output_dir: str = "./output/videos"
    combined_mode: bool = False  # Single combined video vs individual videos
    combined_duration_target: int = 60  # Target duration for combined video (seconds)
    format: VideoFormatConfig = field(default_factory=VideoFormatConfig)
    style: VideoStyleConfig = field(default_factory=VideoStyleConfig)
    stock_footage: StockFootageConfig = field(default_factory=StockFootageConfig)
    youtube: YouTubeConfig = field(default_factory=YouTubeConfig)

    @classmethod
    def from_dict(cls, data: dict) -> "VideoConfig":
        """Create VideoConfig from config.yml data."""
        return cls(
            enabled=data.get("enabled", False),
            count=data.get("count", 3),
            output_dir=data.get("output_dir", "./output/videos"),
            combined_mode=data.get("combined_mode", False),
            combined_duration_target=data.get("combined_duration_target", 60),
            format=VideoFormatConfig(**data.get("format", {})),
            style=VideoStyleConfig(**data.get("style", {})),
            stock_footage=StockFootageConfig(**data.get("stock_footage", {})),
            youtube=YouTubeConfig(**data.get("youtube", {})),
        )
